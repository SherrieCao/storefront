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
        "business": inventory["business"], "location": inventory.get("location", ""),
        "brief": inventory["brief"],
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
    fb, brief, thinking, verdict, attempts = None, None, None, {}, []
    for attempt in range(1, config.MAX_CREATIVE_RETRIES + 1):
        brief, thinking = _produce(fb)
        if brief is None:                       # invalid/empty brief — treat as a fail, regenerate
            fb = "Output was not a valid brief. Return the required JSON with a non-empty segments[]."
            attempts.append({"attempt": attempt, "passed": False, "failed_lenses": ["invalid_json"],
                             "improvement": fb})
            run.log(f"Director: attempt {attempt} produced an invalid brief — regenerating")
            continue
        verdict = reviewers.review(run, "director", brief, ctx)
        # Deterministic guards (run alongside the creative review): pacing (E2) + moodboard photo reuse.
        pace_fb = _pacing_feedback(run, brief, inventory)
        mood_fb = _moodboard_feedback(run, brief, inventory)
        passed = verdict["pass"] and not pace_fb and not mood_fb
        lenses = (list(verdict["failed_lenses"]) + (["pacing_too_slow"] if pace_fb else [])
                  + (["moodboard_reuse"] if mood_fb else []))
        attempts.append({"attempt": attempt, "passed": passed, "scores": verdict["scores"],
                         "failed_lenses": lenses, "improvement": verdict["improvement"]})
        if passed:
            break
        fb = "  ".join(p for p in (verdict["improvement"] if not verdict["pass"] else "",
                                   pace_fb or "", mood_fb or "") if p)
        run.log(f"Director: attempt {attempt} regenerating ({lenses})")
    if brief is None:
        raise RuntimeError("Director returned an empty/invalid brief after retries")

    brief["_review"] = {"passed": verdict.get("pass", True), "scores": verdict.get("scores", {}),
                        "failed_lenses": verdict.get("failed_lenses", []),
                        "improvement": verdict.get("improvement", ""), "attempts": attempts}
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
    # F2: a seedance_shot MUST seed from a REAL photo (@Image…). A pure text-to-video shot ("generated"
    # or any non-@Image ref) reads as AI-stock and undercuts authenticity — drop it (safety net; the
    # scaffold already forbids it). If that empties the plan, return None to regenerate.
    segs = [s for s in segs
            if s.get("type") != "seedance_shot" or str(s.get("asset_ref", "")).startswith("@Image")]
    if not segs:
        return None
    brief["segments"] = segs
    dur = brief.get("total_duration_s")
    if not isinstance(dur, (int, float)) or dur <= 0:
        dur = sum(float(s.get("duration_s") or 0) for s in segs) or config.MIN_DURATION_S
    brief["total_duration_s"] = max(config.MIN_DURATION_S, min(config.MAX_DURATION_S, float(dur)))
    return brief


def _pacing_feedback(run: Run, brief: dict[str, Any], inventory: dict[str, Any]) -> str | None:
    """E2 pace guard: if the brief's average beat is too slow AND there are still unused usable assets
    (so more distinct beats are feasible), return regen feedback pushing more/shorter beats. Returns
    None when pace is fine or no spare assets exist (can't honestly add beats). Logs the metric always."""
    segs = brief.get("segments", [])
    n = len(segs)
    dur = float(brief.get("total_duration_s") or 0)
    if n == 0 or dur <= 0:
        return None
    avg = dur / n
    usable = len(_usable_assets(inventory))
    run.log(f"Director: pacing check — {n} beats / {dur:.0f}s = {avg:.1f}s avg ({usable} usable assets)")
    if avg <= config.PACING_MAX_AVG_BEAT_S or n >= usable:
        return None
    target_n = max(n + 2, int(dur / 1.8) + 1)
    return (f"PACING TOO SLOW: {n} beats over {dur:.0f}s ≈ {avg:.1f}s/beat. Social ads cut faster — aim "
            f"for ~{target_n}+ beats (~1.5–2s each). You have {usable} usable assets; turn more of them "
            f"into distinct short beats (split long holds; add real_clip / moodboard beats). Add MORE, "
            f"SHORTER segments — do NOT pad the existing ones.")


def _moodboard_feedback(run: Run, brief: dict[str, Any], inventory: dict[str, Any]) -> str | None:
    """Guard against a repetitive showcase: when moodboards REUSE the same photos (a photo appears in
    >1 moodboard), the moodboard frames look samey. Returns regen feedback capping the moodboard count
    to what the distinct-photo pool supports + demanding distinct photos per moodboard; None if clean.
    (The majority-real gate can over-produce moodboards on verticals with few photos — e.g. 4 moodboards
    from 5 photos forces reuse.)"""
    from collections import Counter
    mbs = [s for s in brief.get("segments", []) if s.get("type") == "moodboard"]
    if len(mbs) < 2:
        return None
    used = Counter(a for s in mbs for a in (s.get("moodboard_assets") or []))
    reused = sorted(a for a, c in used.items() if c > 1)
    if not reused:
        return None
    photos = len([a for a in inventory.get("images", []) if a.get("recoverable")])
    vids = len([v for v in inventory.get("videos", []) if v.get("usable_as_reference")])
    cap = max(1, photos // 2)
    run.log(f"Director: moodboard check — {len(mbs)} moodboards reuse photos {reused} "
            f"({photos} distinct photos, {vids} videos)")
    return (f"REPETITIVE MOODBOARDS: {len(mbs)} moodboards reuse the same photos ({', '.join(reused)} "
            f"appear in more than one) — the showcase looks repetitive. You only have {photos} distinct "
            f"photos. Use at most {cap} moodboard(s), each with DISTINCT photos (no photo in two "
            f"moodboards); turn the other real beats into `real_clip` windows (you have {vids} videos — "
            f"different trims are distinct beats) so the visuals stay varied.")


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
        + reference_block(["ad_formats.md", "smb_verticals.md", "hooks.md", "script_craft.md"])
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
