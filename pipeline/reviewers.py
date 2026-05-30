"""Creative reviewer — a critic on the thinking stages (concept / director / hook).

A SEPARATE mind (Claude) judges each creative stage's output through 4 lenses (audience sense,
attention, SMB fit, + actionable improvement) against the "brings more traffic" bar. The producing
stage uses the verdict to self-correct (generate -> review -> regenerate with feedback), mirroring the
Shot Agent. Vertical-agnostic: the lenses + the injected SMB/hook/format references apply to any local
business, not one category.

NOT for: generating creative (that's the producer) or mechanical/technical checks (that's review.py).
"""
from __future__ import annotations
import json
from typing import Any
from . import config, budget
from .tracing import Run, log_llm_call
from .llm import call_claude, parse_json
from .refs import reference_block

_STAGE_DESC = {
    "concept": "the chosen creative CONCEPT — the idea / angle / POV, before shot planning.",
    "director": "the creative BRIEF — the spoken script, the segment plan, the mood/pacing, the hook.",
    "hook": "the opening ~3-second HOOK (hook_line + hook_visual + mechanic) that must stop the scroll.",
    "edit": "the EDIT PLAN — segment order, durations, transitions, motion, and caption style.",
}
_LENSES = ("audience", "attention", "smb_fit")
# the edit reviewer judges editing craft, not copy -> its own scaffold + lenses
_SCAFFOLD = {"edit": "editing_reviewer.md"}


def review(run: Run, stage: str, artifact: dict[str, Any], context: dict[str, Any]) -> dict[str, Any]:
    """Review one creative artifact. Returns {pass, scores, failed_lenses, improvement}. Stub -> pass
    offline (no key) so the pipeline still runs without a reviewer."""
    if not config.ANTHROPIC_API_KEY:
        return {"pass": True, "scores": {l: 0.9 for l in _LENSES}, "failed_lenses": [],
                "improvement": "", "_stub": True}

    budget.check_ceiling(run, 0.03, f"{stage}_review")
    scaffold = ((config.SCAFFOLDS_DIR / _SCAFFOLD.get(stage, "creative_reviewer.md")).read_text()
                .replace("{{stage}}", stage)
                .replace("{{stage_desc}}", _STAGE_DESC.get(stage, stage))
                .replace("{{business}}", str(context.get("business", "")))
                .replace("{{brief}}", str(context.get("brief", "")))
                + reference_block(["smb_verticals.md", "hooks.md", "ad_formats.md", "script_craft.md"]))
    user = json.dumps({"stage": stage, "artifact": artifact}, indent=2, default=str)

    raw, thinking, in_tok, out_tok = call_claude(config.MODEL_ROUTER["reviewer"], scaffold, user)
    log_llm_call(run, f"{stage}_review", config.MODEL_ROUTER["reviewer"], scaffold[:300] + "...",
                 raw, in_tok, out_tok, 0, thinking)
    v = _normalize(parse_json(raw))

    status = "PASS" if v["pass"] else f"FAIL ({', '.join(v['failed_lenses']) or 'unspecified'})"
    run.reason(f"{stage.capitalize()} reviewer", thinking,
               f"**{status}** — scores {v['scores']}."
               + (f"\n\n**Improvement:** {v['improvement']}" if not v["pass"] else ""))
    return v


def _normalize(v: dict[str, Any]) -> dict[str, Any]:
    """Coerce the model's JSON into the contract (lens-agnostic — keeps whatever scores keys the stage
    uses); on parse failure, fail-open to pass (don't block a run on a flaky review)."""
    if not isinstance(v, dict) or "pass" not in v:
        return {"pass": True, "scores": {}, "failed_lenses": [],
                "improvement": "", "_review_parse_error": True}
    scores = v.get("scores") if isinstance(v.get("scores"), dict) else {}
    return {"pass": bool(v.get("pass")),
            "scores": {k: float(x or 0.0) for k, x in scores.items() if isinstance(x, (int, float))},
            "failed_lenses": list(v.get("failed_lenses") or []),
            "improvement": str(v.get("improvement") or "")}
