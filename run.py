#!/usr/bin/env python3
"""CLI entry — SMB AI video pipeline (multi-gen: Shot Agent + Editor + coupled keyframes).

Usage:
    python run.py --business carol_dog --input ./inputs/carol_dog/
    python run.py --replay 0001 --from-step shots
    python run.py --replay 0001 --from-step editor      # re-edit without re-generating shots

Pipeline: triage → concept → director → enhance → keyframes → shots → voice → editor → review
The cost ceiling ($5) is a silent safety net; the Director never sees cost.
"""
from __future__ import annotations
import argparse, json, sys
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from dotenv import load_dotenv
load_dotenv()

from pipeline import config
from pipeline.tracing import setup_run
from pipeline import (triage as tri, concept as concept_, director as dir_, enhance as enh,
                      keyframes as kf_, shots as shots_, music as music_, voice as voice_,
                      editor as ed_, review as rev, lineage as lin, history as hist_, errors)
from pipeline.budget import CostCeilingExceeded

# "music" runs after shots, before the timeline is planned (the editor snaps cuts to its beat grid).
STEPS = ["triage", "concept", "director", "enhance", "keyframes", "shots", "music",
         "voice", "editor", "review"]


def main() -> int:
    a = _parse()
    if a.final:
        config.RESOLUTION, config.SEEDANCE_TIER = "720p", "standard"
    if a.replay:
        run_dir = config.RUNS_DIR / a.replay
        if not run_dir.exists():
            print(f"error: run {a.replay} not found", file=sys.stderr); return 1
        business = _meta(run_dir, "business") or "unknown"
        input_dir = run_dir / "input_snapshot"
        run_id, from_step = a.replay, (a.from_step or "triage")
    else:
        if not (a.business and a.input):
            print("error: --business and --input required", file=sys.stderr); return 1
        if not Path(a.input).exists():
            print(f"error: input not found: {a.input}", file=sys.stderr); return 1
        run_id, business, input_dir, from_step = a.run_id, a.business, Path(a.input), "triage"

    start = STEPS.index(from_step)
    cached = lambda s: STEPS.index(s) < start

    run = setup_run(run_id, business)
    if a.replay: run.log(f"REPLAY from '{from_step}'")

    step = "triage"
    try:
        inventory = tri.run_triage(run, input_dir, use_cache=cached("triage"))
        if inventory.get("gap_ask"):
            run.log(f"[OPERATOR ACTION] {inventory['gap_ask']}")
        # enhance only needs `inventory` (from triage) — run it in the BACKGROUND while concept + director
        # think; it finishes well before keyframes need the enhanced photos. (D45)
        step = "concept"
        with ThreadPoolExecutor(max_workers=1) as bg:
            enhance_future = bg.submit(enh.enhance_assets, run, inventory, use_cache=cached("enhance"))
            concept = concept_.run_concept(run, inventory, use_cache=cached("concept"))
            step = "director"; brief = dir_.run_director(run, inventory, concept, use_cache=cached("director"))
            # creative-reviewer escalation: a brief that fails its reviewer after self-retries re-rolls the
            # upstream concept (with the director's feedback), then re-plans. Bounded; fresh runs only.
            esc = 0
            while (not brief.get("_review", {}).get("passed", True) and esc < config.CREATIVE_MAX_ESCALATIONS
                   and not cached("concept") and not cached("director")):
                esc += 1
                run.log(f"[ESCALATION {esc}] director review unresolved — re-rolling concept with feedback")
                concept = concept_.run_concept(run, inventory, feedback=brief["_review"].get("improvement"))
                brief = dir_.run_director(run, inventory, concept)
            _collect_creative_flags(run, concept, brief)
            step = "enhance"; enhance_future.result()   # collect before the gate (re-raises a thread error here)
        if not a.no_gate and not cached("director"):
            return _approval_gate(run)
        # Visuals-first spine + VOICE-FIT ESCALATION (D51): build the back-half (music ∥ keyframes→shots →
        # plan_timeline), generate the voice, and if the REALIZED video is too short for the voice (>1.2×),
        # re-plan via the Director (add beats / cut script), bounded. The voice is never crushed past the cap.
        esc, asset_gen_used = 0, False
        while True:
            # music only needs the brief — run it in the BACKGROUND during keyframes + shots (D45)
            with ThreadPoolExecutor(max_workers=1) as bg2:
                music_future = bg2.submit(music_.run_music, run, brief, use_cache=cached("music"))
                step = "keyframes"; keyframes = kf_.run_keyframes(run, brief, inventory, use_cache=cached("keyframes"))
                step = "shots";     shots = shots_.run_shots(run, brief, inventory, keyframes, use_cache=cached("shots"))
                step = "music";     music = music_future.result()
            need_timeline = (not cached("voice")) or (not cached("editor"))
            timeline = (ed_.plan_timeline(run, brief, shots, keyframes, inventory, beats=music.get("beats"))
                        if need_timeline else {})
            step = "voice";     voice = voice_.run_voice(run, brief, timeline, inventory, use_cache=cached("voice"))
            # escalate only on a fresh run (no-op on replay from a later step) + bounded + only if underbuilt
            loop_live = (not cached("director")) and (not cached("voice"))
            if not loop_live or esc >= config.EDITOR_MAX_ESCALATIONS or _voice_fits(timeline, voice):
                break
            esc += 1
            unused = _unused_usable_assets(inventory, brief)
            fb = _voicefit_replan_feedback(timeline, voice, len(unused))
            run.log(f"[VOICE-FIT ESCALATION {esc}] realized video too short for the voice — "
                    f"re-planning ({len(unused)} unused assets)")
            if len(unused) < config.ASSET_STARVED_UNUSED_THRESHOLD and not asset_gen_used:
                asset_gen_used = True                       # last resort, one-shot: synthesize a fill asset
                _try_asset_gen(run, inventory, brief, timeline)
            step = "director"; brief = dir_.run_director(run, inventory, concept, feedback=fb)
        step = "editor";    final = ed_.render(run, timeline, voice, music=music, use_cache=cached("editor"))
        _flag_editor(run, timeline)            # surface an unresolved editor review (like creative flags)
        step = "review"
        edit_doc = _load(run.dir / "07_edit_plan.json")
        # final length is now deterministic (= the planned timeline); check the render against it.
        expected_s = float(edit_doc.get("total_s") or brief.get("total_duration_s") or 15)
        review = rev.run_review(run, final, expected_s)
        lin.build_lineage(run, brief, concept, keyframes, shots, voice,
                          edit_doc.get("plan", {}), review, final)
        # Topic history: log this run's concept/angle/ending so future runs steer away from repeats.
        hist_.record_run(run, concept, brief, _load(run.dir / "01_research.json"))
        if shots.get("flagged"):
            run.log(f"[OPERATOR ACTION] {len(shots['flagged'])} shot(s) flagged — see flagged_shots.json")
        run.finalize()
    except CostCeilingExceeded as exc:
        run.trace({"step": step, "type": "cost_ceiling", "error": str(exc)})
        run._write_meta("halted_cost_ceiling", {"halted_step": step, "error": str(exc)})
        run.log(f"HALTED at '{step}': {exc}")
        print(f"\nRun {run.run_id} HALTED — cost ceiling (${config.COST_CEILING_USD:.2f}) reached at "
              f"'{step}'. Partial run + COST.md written.", file=sys.stderr)
        return 2
    except Exception as exc:
        cls = errors.classify_api_error(exc)
        if cls is None:
            raise
        run.fail(step, exc, cls)
        print(f"\nPipeline stopped at '{step}': {cls['message']}", file=sys.stderr)
        print(f"Resume without re-spending upstream:\n"
              f"  python run.py --replay {run.run_id} --from-step {step}", file=sys.stderr)
        return 1

    print(f"\n{'='*60}")
    print(f"Run {run.run_id} complete")
    print(f"  Output:    {final}")
    print(f"  Edit plan: {run.dir}/07_edit_plan.json")
    print(f"  Reasoning: {run.reasoning_path}")
    print(f"  Cost:      {run.cost_md_path}")
    print(f"  Lineage:   {run.lineage_path}")
    print(f"\nNext: watch the video, then fill {run.dir}/06_operator_review.json")
    print(f"      bar: 'would a small-business owner believe this brings them traffic?'")
    return 0


def _parse():
    p = argparse.ArgumentParser(description="SMB AI video pipeline (multi-gen)")
    p.add_argument("--business"); p.add_argument("--input")
    p.add_argument("--run-id"); p.add_argument("--replay")
    p.add_argument("--from-step", choices=STEPS)
    p.add_argument("--final", action="store_true",
                   help="720p standard-tier keeper (default: cheap 480p/fast draft)")
    p.add_argument("--no-gate", action="store_true",
                   help="skip the post-Director approval gate and run straight through")
    return p.parse_args()


def _approval_gate(run) -> int:
    run.pause("director")
    print(f"\n{'='*60}")
    print(f"Run {run.run_id} — creative direction ready for your review:")
    print(f"  Concept:   {run.dir}/01_concept.md")
    print(f"  Brief:     {run.dir}/02_creative_brief.json")
    print(f"  Reasoning: {run.reasoning_path}")
    print(f"\nApprove & render:  python run.py --replay {run.run_id} --from-step enhance")
    print(f"Re-roll direction: python run.py --replay {run.run_id} --from-step concept")
    return 0


def _collect_creative_flags(run, concept, brief) -> None:
    """Gather any creative-stage reviews still unresolved after retries -> creative_flags.json + a
    surfaced operator note (parallel to flagged_shots; never blocks)."""
    flags = []
    for stage, art in (("concept", concept), ("director", brief)):
        rv = (art or {}).get("_review", {})
        if rv and not rv.get("passed", True):
            flags.append({"stage": stage, "failed_lenses": rv.get("failed_lenses", []),
                          "improvement": rv.get("improvement", "")})
    hook = (brief or {}).get("hook", {})
    hrv = hook.get("_review", {}) if isinstance(hook, dict) else {}
    if hrv and not hrv.get("passed", True):
        flags.append({"stage": "hook", "improvement": hrv.get("improvement", "")})
    if flags:
        run.write_creative_flags(flags)
        run.log(f"[OPERATOR ACTION] {len(flags)} creative review(s) unresolved after retries "
                f"({', '.join(f['stage'] for f in flags)}) — see creative_flags.json")


def _flag_editor(run, timeline) -> None:
    """If the editor's critic loop never passed, merge it into creative_flags.json + surface it."""
    rv = (timeline or {}).get("_review", {})
    if not rv or rv.get("passed", True):
        return
    existing = json.loads(run.creative_flags_path.read_text()) if run.creative_flags_path.exists() else []
    existing.append({"stage": "editor", "failed_lenses": rv.get("failed_lenses", []),
                     "scores": rv.get("scores", {})})
    run.write_creative_flags(existing)
    run.log(f"[OPERATOR ACTION] editor review unresolved after retries ({rv.get('failed_lenses')}) "
            f"— accepted best; see creative_flags.json")


# --- D51: voice-fit escalation helpers ---------------------------------------------------------
def _voice_fits(timeline: dict, voice: dict) -> bool:
    """True if the script fits the realized video at ≤ VOICE_FIT_RATIO. Checks BOTH the editor's estimate
    (timeline._voice_fit.underbuilt) and the ACTUAL voice duration (the authority once voice exists)."""
    fit = (timeline or {}).get("_voice_fit") or {}
    if fit.get("underbuilt"):
        return False
    region = fit.get("vo_region") or 0.0
    vdur = (voice.get("duration_ms") or 0) / 1000
    if region and vdur:
        return (vdur / region) <= config.VOICE_FIT_RATIO + 0.05
    return True                                            # no data (cached/empty timeline) → don't loop


def _unused_usable_assets(inventory: dict, brief: dict) -> list:
    """Usable @-token assets the Director did NOT reference in any beat — the material a re-plan can add."""
    from pipeline.translator import _usable_assets
    used: set = set()
    for s in brief.get("segments", []):
        used.update(str(x) for x in (s.get("moodboard_assets") or []))
        if s.get("asset_ref"): used.add(str(s["asset_ref"]))
        if s.get("clip_ref"):  used.add(str(s["clip_ref"]))
    return [(t, p) for t, p in _usable_assets(inventory) if t not in used]


def _voicefit_replan_feedback(timeline: dict, voice: dict, n_unused: int) -> str:
    fit = (timeline or {}).get("_voice_fit") or {}
    region = fit.get("vo_region") or 0.0
    vdur = (voice.get("duration_ms") or 0) / 1000 or fit.get("est_vo") or 0.0
    target_words = int(region * config.VOICE_FIT_RATIO * config.SPOKEN_WPS)
    short = max(0.0, vdur / config.VOICE_FIT_RATIO - region)
    return (f"VIDEO TOO SHORT FOR THE VOICE: the realized video's spoken region is ~{region:.0f}s but the "
            f"voice is ~{vdur:.0f}s — it would be sped past {config.VOICE_FIT_RATIO}× (rushed). The video is "
            f"~{short:.0f}s too short. Fix BOTH ways toward a match: ADD beats (you have {n_unused} unused "
            f"assets — turn them into distinct short real_clip/moodboard beats) so the video fills "
            f"{config.MIN_DURATION_S}–{config.MAX_DURATION_S}s, AND/OR cut the script to ~{target_words} words. "
            f"Your beat durations must SUM to about total_duration_s — short trimmed clips clamp the realized "
            f"video shorter than planned, which is the usual cause.")


def _try_asset_gen(run, inventory: dict, brief: dict, timeline: dict) -> bool:
    """Last resort (one-shot): synthesize fill frames so the Director can add beats when genuinely out of
    distinct assets. Registers them as recoverable @Image assets. Bounded by ASSET_GEN_MAX_NEW_BEATS."""
    import math
    short = ((timeline or {}).get("_voice_fit") or {}).get("shortfall_s") or 0.0
    n = min(config.ASSET_GEN_MAX_NEW_BEATS, max(1, math.ceil(short / config.EDITOR_TARGET_BEAT_S)))
    base, added = len(inventory.get("images", [])), 0
    for i in range(n):
        p = kf_.generate_synthetic_asset(run, brief, base + i)
        if p:
            inventory.setdefault("images", []).append(
                {"path": p, "recoverable": True, "type": "image", "note": "synthesized (D51)", "_synthetic": True})
            added += 1
    if added:
        run.log(f"Asset-gen: registered {added} synthetic asset(s) for the Director to use (last resort)")
    return added > 0


def _meta(d: Path, k: str):
    m = d / "meta.json"
    return json.loads(m.read_text()).get(k) if m.exists() else None


def _load(p: Path) -> dict:
    return json.loads(p.read_text()) if p.exists() else {}


if __name__ == "__main__":
    raise SystemExit(main())
