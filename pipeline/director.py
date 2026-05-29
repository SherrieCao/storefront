"""Stage 1: Creative Director (Gemini 3.1 Pro, multimodal — SEES the assets).

Receives the actual photos AND videos plus the triage inventory + the chosen concept, and plans the
whole ad in one pass: a SEQUENCE OF MIXED SEGMENTS (seedance_shot / real_clip / moodboard / card),
the total duration (15-30s), the spoken script, mood, and the editing intent (pacing / editing_feel)
that feeds the EDITOR. Decides intent only — does not write per-shot prompts or the edit plan.

Mixed segments + the Seedance/Remotion bright line: see SPEC_followup_mixed_segments.md (D19-D21).
The Director plans creatively and NEVER reasons about cost (the $5 ceiling is a silent safety net).

NOT for: writing per-shot Seedance prompts (the per-shot composer) or the edit plan (the Editor).
"""
from __future__ import annotations
import json
from pathlib import Path
from typing import Any
from . import config
from .tracing import Run
from .llm import parse_json
from .translator import _usable_assets
from .agent.loop import run_agent_loop
from .agent import tools as agent_tools
from . import reviewers                       # 4-lens creative critic (self-correct loop)

BRIEF_FILE = "02_creative_brief.json"
SEGMENT_TYPES = {"seedance_shot", "real_clip", "moodboard", "card"}


def run_director(run: Run, inventory: dict[str, Any], concept: dict[str, Any] | None = None,
                 *, use_cache: bool = False) -> dict[str, Any]:
    cache = run.dir / BRIEF_FILE
    if use_cache and cache.exists():
        run.log("Director: loaded from cache"); return json.loads(cache.read_text())

    run.log("Director: planning mixed segments + duration + script (multimodal)")
    scaffold = _load_scaffold(inventory)
    model = config.MODEL_ROUTER["creative_director"]

    tokened = _usable_assets(inventory)
    image_paths = [p for tok, p in tokened if tok.startswith("@Image")]
    video_paths = [p for tok, p in tokened if tok.startswith("@Video")]
    if inventory.get("logo_path"): image_paths.insert(0, inventory["logo_path"])

    base_payload = {
        "business": inventory["business"], "brief": inventory["brief"],
        "has_before_after": inventory["has_before_after"],
        "has_logo": inventory["has_logo"], "palette": inventory["palette"],
        "chosen_concept": (concept or {}).get("chosen", {}),   # EXECUTE this (don't re-ideate)
        "asset_summary": _asset_summary(inventory),
        "duration_bounds_s": [config.MIN_DURATION_S, config.MAX_DURATION_S],
    }
    ctx = {"business": inventory["business"], "brief": inventory["brief"]}

    def _produce(fb: str | None) -> tuple[dict[str, Any] | None, str | None]:
        payload = dict(base_payload)
        if fb:
            payload["prior_attempt_failed_review"] = {"fix_these": fb}
        agent_tools.set_assets(inventory)
        raw, thinking, _i, _o = run_agent_loop(
            run, "director", scaffold, model, ["inspect_asset", "trend_lookup", "design_hook"],
            user_text=json.dumps(payload, indent=2), image_paths=image_paths, video_paths=video_paths,
            max_iterations=6,
            stub=lambda: (_stub_director(inventory), "STUB thinking: no GEMINI_API_KEY set", 0, 0))
        return _validate(parse_json(raw)), thinking

    # self-correcting critic loop: produce -> review (4 lenses) -> regenerate with feedback
    fb, brief, thinking, verdict = None, None, None, {}
    for attempt in range(1, config.MAX_CREATIVE_RETRIES + 1):
        brief, thinking = _produce(fb)
        if brief is None:                       # invalid/empty brief — treat as a fail, regenerate
            fb = "Output was not a valid brief. Return the required JSON with a non-empty segments[]."
            run.log(f"Director: attempt {attempt} produced an invalid brief — regenerating")
            continue
        verdict = reviewers.review(run, "director", brief, ctx)
        if verdict["pass"]:
            break
        fb = verdict["improvement"]
        run.log(f"Director: review attempt {attempt} FAIL ({verdict['failed_lenses']}) — regenerating")
    if brief is None:
        raise RuntimeError("Director returned an empty/invalid brief after retries")

    brief["_review"] = {"passed": verdict.get("pass", True), "scores": verdict.get("scores", {}),
                        "failed_lenses": verdict.get("failed_lenses", []),
                        "improvement": verdict.get("improvement", "")}
    cache.write_text(json.dumps(brief, indent=2))

    segs = brief.get("segments", [])
    counts = _type_counts(segs)
    rationale = (f"**Total duration:** {brief.get('total_duration_s')}s\n\n"
                 f"**Composition:** {brief.get('composition_reasoning','')}\n\n"
                 f"**Angle:** {brief.get('creative_angle','')}\n\n"
                 f"**Script:** {brief.get('script_reasoning','')}\n\n"
                 f"**Segments** ({', '.join(f'{k}×{v}' for k, v in counts.items())}):\n"
                 + "\n".join(f"- {s.get('n')}. [{s.get('type')}] {s.get('intent','')} — {s.get('why','')}"
                             for s in segs))
    run.reason("Director (Gemini)", thinking, rationale)
    run.log(f"Director: {len(segs)} segments ({counts}), {brief.get('total_duration_s')}s, "
            f"angle='{str(brief.get('creative_angle',''))[:60]}'")
    return brief


def _validate(brief: dict[str, Any]) -> dict[str, Any] | None:
    """Require a non-empty segments[] of known types and a total_duration_s in bounds. Clamp
    duration; default it from segment durations if missing. Returns the brief, or None to retry."""
    segs = brief.get("segments")
    if not isinstance(segs, list) or not segs:
        return None
    if any(s.get("type") not in SEGMENT_TYPES for s in segs):
        return None
    dur = brief.get("total_duration_s")
    if not isinstance(dur, (int, float)) or dur <= 0:
        dur = sum(float(s.get("duration_s") or 0) for s in segs) or config.MIN_DURATION_S
    brief["total_duration_s"] = max(config.MIN_DURATION_S, min(config.MAX_DURATION_S, float(dur)))
    return brief


def _type_counts(segs: list[dict]) -> dict[str, int]:
    out: dict[str, int] = {}
    for s in segs:
        t = str(s.get("type", "?"))
        out[t] = out.get(t, 0) + 1
    return out


def _asset_summary(inv: dict) -> list[dict]:
    """One row per usable asset, labeled with the @-token (ref) the Director uses to anchor a
    segment to it. Quality/remediation from triage; the model also sees the pixels."""
    by_path = {a["path"]: a for a in inv.get("images", []) + inv.get("videos", [])}
    out = []
    for tok, p in _usable_assets(inv):
        a = by_path.get(p, {})
        row = {"ref": tok, "file": Path(p).name, "kind": a.get("type"), "quality": a.get("note")}
        if a.get("type") == "image":
            row["remediation"] = a.get("remediation", [])
        elif a.get("type") == "video":
            row["length_s"] = a.get("duration_s")   # full source; real_clip trim_s picks the window
        out.append(row)
    return out


def _load_scaffold(inv: dict) -> str:
    # Inject the whole multi-vertical playbook (formats + per-vertical "what converts" + hooks) so the
    # Director reasons WITH Motion's data — vertical-agnostic; the model picks the row for this brief.
    from .refs import reference_block
    t = (config.SCAFFOLDS_DIR / "creative_director.md").read_text() \
        + reference_block(["ad_formats.md", "smb_verticals.md", "hooks.md"])
    return (t.replace("{{business}}", str(inv.get("business", "")))
             .replace("{{brief}}", str(inv.get("brief", "")))
             .replace("{{has_before_after}}", str(inv.get("has_before_after", False)))
             .replace("{{has_logo}}", str(inv.get("has_logo", False)))
             .replace("{{palette}}", ", ".join(inv.get("palette", [])) or "not detected")
             .replace("{{min_duration_s}}", str(config.MIN_DURATION_S))
             .replace("{{max_duration_s}}", str(config.MAX_DURATION_S)))


def _stub_director(inv: dict[str, Any] | None = None) -> str:
    """Vertical-NEUTRAL canned brief so offline/no-key runs complete for ANY business (the real loop
    runs only with a key). Uses the actual business name; no hardcoded vertical."""
    biz = (inv or {}).get("business", "this local business")
    return json.dumps({
        "creative_angle": f"STUB: an authentic, specific look at {biz} (offline placeholder).",
        "total_duration_s": 18,
        "composition_reasoning": "STUB: a real-footage open, distinct quick beats, a moodboard of real "
                                 "photos, a clean CTA card.",
        "script": f"STUB voiceover for {biz}: real, specific, and worth the trip. Come see for yourself.",
        "script_reasoning": "STUB placeholder script (offline).",
        "speech": f"STUB voiceover for {biz}: real, specific, and worth the trip. Come see for yourself.",
        "mood": "warm, authentic, local",
        "pacing": "brisk",
        "editing_feel": "fast clean hard cuts with one soft crossfade into the closing card",
        "hook": {"hook_visual": "the strongest real asset, in motion", "hook_line": "STUB hook line.",
                 "mechanic": "newness", "why": "stub", "cut_dead_first_second": True},
        "segments": [
            {"n": 1, "type": "real_clip", "duration_s": 2.5, "intent": "authentic opener",
             "clip_ref": "@Video1", "trim_s": [0, 2.5], "why": "real footage hooks"},
            {"n": 2, "type": "seedance_shot", "duration_s": 2.5, "intent": "hero motion beat",
             "action": "natural subject motion", "camera": "slow push-in", "asset_ref": "@Image1",
             "why": "motion the stills can't supply"},
            {"n": 3, "type": "moodboard", "duration_s": 3, "intent": "consolidate real photos",
             "moodboard_assets": ["@Image2", "@Image3"], "why": "scattered assets -> one designed frame"},
            {"n": 4, "type": "card", "duration_s": 3, "intent": "CTA", "card_template": "EndCard",
             "card_text": "Come see for yourself", "why": "land the CTA cleanly"},
        ],
        "_stub": True,
    })
