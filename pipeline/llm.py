"""Shared LLM helpers: Gemini (multimodal brain + video judge) and Claude (per-shot prompt /
editor plan).

All call helpers return (text, thinking, in_tok, out_tok). `thinking` is the model's reasoning
trace when exposed (Gemini thinking / Claude extended thinking), else None. When the relevant key
is absent, a caller-supplied `stub` produces offline text so the pipeline runs end-to-end.

Verified request shapes against Phase-0 spikes (docs/{judge,voice,...}_findings.md).
"""
from __future__ import annotations
import json, mimetypes, time
from pathlib import Path
from typing import Any, Callable
from . import config


def call_gemini_multimodal(model: str, system: str, user_text: str,
                           image_paths: list[str], video_paths: list[str],
                           *, stub: Callable[[], str] | None = None,
                           ) -> tuple[str, str | None, int, int]:
    """Gemini with text + images + videos. Images inline (<20MB total); videos via the Files API
    (polled to ACTIVE). Thinking captured if CAPTURE_THINKING."""
    if not config.GEMINI_API_KEY:
        return (stub() if stub else "{}"), "STUB thinking: no GEMINI_API_KEY set", 800, 600

    from google import genai
    from google.genai import types
    client = genai.Client(api_key=config.GEMINI_API_KEY)

    contents: list[Any] = []
    for p in image_paths:
        mime = mimetypes.guess_type(p)[0] or "image/jpeg"
        contents.append(types.Part.from_bytes(data=Path(p).read_bytes(), mime_type=mime))
    for p in video_paths:
        f = client.files.upload(file=p)
        while getattr(f.state, "name", None) != "ACTIVE":
            time.sleep(2); f = client.files.get(name=f.name)
        contents.append(f)
    contents.append(user_text)

    resp = client.models.generate_content(
        model=model, contents=contents,
        config=types.GenerateContentConfig(
            system_instruction=system,
            thinking_config=_thinking_config(types, model)))

    text, thinking = "", ""
    for part in resp.candidates[0].content.parts:
        if not getattr(part, "text", None):
            continue
        if getattr(part, "thought", False):
            thinking += part.text
        else:
            text += part.text
    u = resp.usage_metadata
    in_tok  = u.prompt_token_count or 0
    out_tok = (u.candidates_token_count or 0) + (getattr(u, "thoughts_token_count", 0) or 0)
    return text, (thinking or None), in_tok, out_tok


def call_gemini_video_judge(model: str, system: str, video_path: str, user_text: str = "",
                            ) -> tuple[str, str | None, int, int]:
    """Judge a rendered clip with a cheap Gemini Flash model (VERIFIED: gemini-3-flash-preview
    accepts video). Uploads the clip via the Files API, polls ACTIVE, returns (text, thinking,
    in_tok, out_tok). The shot judge demands JSON-only. No key -> empty (caller stubs)."""
    if not config.GEMINI_API_KEY:
        return "", "STUB: no GEMINI_API_KEY", 0, 0
    from google import genai
    from google.genai import types
    client = genai.Client(api_key=config.GEMINI_API_KEY)
    f = client.files.upload(file=video_path)
    while getattr(f.state, "name", None) != "ACTIVE":
        time.sleep(2); f = client.files.get(name=f.name)
    contents: list[Any] = [f]
    if user_text:
        contents.append(user_text)
    resp = client.models.generate_content(
        model=model, contents=contents,
        config=types.GenerateContentConfig(system_instruction=system,
                                            response_mime_type="application/json"))
    u = resp.usage_metadata
    in_tok  = u.prompt_token_count or 0
    out_tok = u.candidates_token_count or 0
    return (resp.text or ""), None, in_tok, out_tok


def _thinking_config(types, model: str, level: str = "high"):
    """Gemini 3.x uses thinking_level; 2.5 uses thinking_budget (cannot be mixed). None if off.
    `level` lets a stage trade reasoning depth for latency (the Director runs lower; concept stays high)."""
    if not config.CAPTURE_THINKING:
        return None
    if "gemini-3" in model:
        return types.ThinkingConfig(include_thoughts=True, thinking_level=level)
    return types.ThinkingConfig(include_thoughts=True, thinking_budget=-1)


def call_claude(model: str, system: str, user: str,
                *, stub: Callable[[], str] | None = None, think: bool = True,
                ) -> tuple[str, str | None, int, int]:
    """Call Claude. Returns (text, thinking, in_tok, out_tok). `think=False` disables extended thinking
    — much faster; use it for judgment calls (reviewers) that don't need long reasoning."""
    if not config.ANTHROPIC_API_KEY:
        return (stub() if stub else "{}"), "STUB thinking: no ANTHROPIC_API_KEY set", 600, 500
    import anthropic
    client = anthropic.Anthropic(api_key=config.ANTHROPIC_API_KEY)
    kwargs: dict[str, Any] = dict(
        model=model, max_tokens=16000,
        system=[{"type": "text", "text": system, "cache_control": {"type": "ephemeral"}}],
        messages=[{"role": "user", "content": user}])
    if think:
        kwargs["thinking"] = {"type": "adaptive"}
    msg = client.messages.create(**kwargs)
    text = "".join(b.text for b in msg.content if getattr(b, "type", "") == "text")
    thinking = "".join(b.thinking for b in msg.content if getattr(b, "type", "") == "thinking") or None
    u = msg.usage
    in_tok = (u.input_tokens + (getattr(u, "cache_read_input_tokens", 0) or 0)
              + (getattr(u, "cache_creation_input_tokens", 0) or 0))
    return text, thinking, in_tok, u.output_tokens


def parse_json(raw: str) -> dict[str, Any]:
    clean = raw.strip()
    if clean.startswith("```"):
        clean = clean.split("```")[1]
        if clean.startswith("json"): clean = clean[4:]
    try:
        return json.loads(clean)
    except json.JSONDecodeError as e:
        return {"_parse_error": str(e), "_raw": raw}
