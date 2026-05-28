"""Agent loop — Hermes idiom on native model function-calling (Gemini in v0).

run_agent_loop() sends (system + multimodal user message + registered tool schemas) to the
model; while the model returns function calls it executes them via the registry, appends the
results, and loops; when the model returns text it parses and returns. Enforces a max-iteration
cap and the per-stage token budget from config.TOKEN_BUDGETS. Every model call goes through
log_llm_call and every tool execution through run.trace — same run-directory artifacts as the
rest of the pipeline (no parallel logging).

Provider dispatch is on the model id: only the Gemini adapter exists in v0 (the Director is the
sole agentic consumer; the Translator is intentionally a single Claude call). A non-Gemini model
raises NotImplementedError — the clean extension point for a future Claude adapter.

NOT for: creative decisions (the tools/scaffold own those) or prompt composition.
"""
from __future__ import annotations
import mimetypes, time
from pathlib import Path
from typing import Callable, Sequence

from .. import config
from ..tracing import Run, log_llm_call, set_active_run
from ..llm import _thinking_config          # reuse the proven Gemini-3.x vs 2.5 thinking config
from . import registry

DEFAULT_MAX_ITERS = 4


def run_agent_loop(run: Run, step: str, system: str, model: str, tool_names: list[str], *,
                   user_text: str = "", image_paths: Sequence[str] = (),
                   video_paths: Sequence[str] = (), stub: Callable[[], tuple] | None = None,
                   max_iterations: int = DEFAULT_MAX_ITERS) -> tuple[str, str | None, int, int]:
    """Run the tool-calling loop. Returns (final_text, thinking, in_tok, out_tok) — the same
    shape callers got from a single llm call, so downstream parsing is unchanged."""
    if "gemini" not in model:
        raise NotImplementedError(
            f"agent loop: only the Gemini adapter exists in v0 (got '{model}'). "
            f"Add a Claude adapter here when a Claude stage needs the loop.")
    if not config.GEMINI_API_KEY:
        return stub() if stub else ("", None, 0, 0)   # preserve offline behavior

    from google import genai
    from google.genai import types
    client = genai.Client(api_key=config.GEMINI_API_KEY)

    contents = [types.Content(role="user",
                              parts=_input_parts(client, types, image_paths, video_paths, user_text))]
    tool_defs = registry.gemini_tool_defs(tool_names)
    budget = config.TOKEN_BUDGETS.get(step, 12_000)
    all_thinking, total_in, total_out = "", 0, 0

    set_active_run(run)   # so tools executed in the loop (e.g. design_hook) log into this run
    for it in range(max_iterations):
        # last allowed turn, or output budget spent → drop tools so the model must answer in text.
        # Gate on OUTPUT only: large multimodal INPUT (long videos, many images) is fixed-cost and must
        # NOT prematurely force the final turn (that caused empty briefs); output is the runaway risk.
        force_final = it == max_iterations - 1 or total_out > budget
        cfg = types.GenerateContentConfig(
            system_instruction=system,
            thinking_config=_thinking_config(types, model),
            tools=None if force_final else (tool_defs or None),
            automatic_function_calling=types.AutomaticFunctionCallingConfig(disable=True))

        t0 = time.time()
        resp = client.models.generate_content(model=model, contents=contents, config=cfg)
        ms = int((time.time() - t0) * 1000)
        text, thinking, calls = _extract(resp)
        in_tok, out_tok = _tokens(resp)
        total_in += in_tok; total_out += out_tok
        if thinking:
            all_thinking += thinking + "\n"
        log_llm_call(run, step, model, f"[loop it={it}{' final' if force_final else ''}] {system[:200]}...",
                     text or f"(tool calls: {[c.name for c in calls]})", in_tok, out_tok, ms, thinking or None)

        if force_final or not calls:
            if not calls and not text and not force_final:
                # empty turn (model produced only thinking, no answer and no tool call) — don't pass an
                # empty result downstream; nudge it to finalize and keep looping.
                contents.append(resp.candidates[0].content)
                contents.append(types.Content(role="user", parts=[types.Part.from_text(
                    text="Now output the final JSON result — no tool calls, no preamble.")]))
                continue
            set_active_run(None)
            return text, (all_thinking or None), total_in, total_out

        # echo the model's content verbatim (preserves function_call parts + thought signatures),
        # then run each requested tool and feed results back
        contents.append(resp.candidates[0].content)
        result_parts = []
        for c in calls:
            args = dict(c.args or {})
            run.trace({"step": step, "type": "tool_call", "tool": c.name, "args": args})
            try:
                result = registry.execute(c.name, args)
            except Exception as e:
                result = {"error": str(e)}
            run.trace({"step": step, "type": "tool_result", "tool": c.name, "output": str(result)[:2000]})
            run.log(f"{step}: tool {c.name}({args}) -> {str(result)[:80]}")
            result_parts.append(types.Part.from_function_response(
                name=c.name, response=result if isinstance(result, dict) else {"result": result}))
        contents.append(types.Content(role="user", parts=result_parts))

    set_active_run(None)
    return "", (all_thinking or None), total_in, total_out   # unreachable (loop always returns)


def _input_parts(client, types, image_paths, video_paths, user_text):
    """Multimodal first-turn parts: images inline, videos via Files API (poll ACTIVE), then text.
    Mirrors pipeline/llm.call_gemini_multimodal."""
    parts = []
    for p in image_paths:
        mime = mimetypes.guess_type(p)[0] or "image/jpeg"
        parts.append(types.Part.from_bytes(data=Path(p).read_bytes(), mime_type=mime))
    for p in video_paths:
        f = client.files.upload(file=p)
        while getattr(f.state, "name", None) != "ACTIVE":
            time.sleep(2); f = client.files.get(name=f.name)
        parts.append(types.Part.from_uri(file_uri=f.uri, mime_type=f.mime_type))
    if user_text:
        parts.append(types.Part.from_text(text=user_text))
    return parts


def _extract(resp) -> tuple[str, str, list]:
    """Pull (answer text, thinking text, [function_calls]) from one Gemini response.
    Uses the proven part.thought boolean + part.text (not part.thought.text)."""
    text, thinking, calls = "", "", []
    cand = resp.candidates[0] if getattr(resp, "candidates", None) else None
    for part in (getattr(getattr(cand, "content", None), "parts", None) or []):
        fc = getattr(part, "function_call", None)
        if fc:
            calls.append(fc); continue
        if getattr(part, "text", None):
            if getattr(part, "thought", False):
                thinking += part.text
            else:
                text += part.text
    return text, thinking, calls


def _tokens(resp) -> tuple[int, int]:
    u = getattr(resp, "usage_metadata", None)
    if not u:
        return 0, 0
    return (u.prompt_token_count or 0,
            (u.candidates_token_count or 0) + (getattr(u, "thoughts_token_count", 0) or 0))
