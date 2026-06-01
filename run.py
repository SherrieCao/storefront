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
        step = "concept";  concept = concept_.run_concept(run, inventory, use_cache=cached("concept"))
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
        if not a.no_gate and not cached("director"):
            return _approval_gate(run)
        step = "enhance";   enh.enhance_assets(run, inventory, use_cache=cached("enhance"))
        step = "keyframes"; keyframes = kf_.run_keyframes(run, brief, inventory, use_cache=cached("keyframes"))
        step = "shots";     shots = shots_.run_shots(run, brief, inventory, keyframes, use_cache=cached("shots"))
        step = "music";     music = music_.run_music(run, brief, use_cache=cached("music"))
        # Visuals-first spine: fix the visual timeline to the Director's length, THEN fit the voice to
        # it, THEN render. plan_timeline runs whenever voice or editor will run fresh; it snaps cuts to
        # the music beat grid (music["beats"]).
        need_timeline = (not cached("voice")) or (not cached("editor"))
        timeline = (ed_.plan_timeline(run, brief, shots, keyframes, inventory, beats=music.get("beats"))
                    if need_timeline else {})
        step = "voice";     voice = voice_.run_voice(run, brief, timeline, use_cache=cached("voice"))
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


def _meta(d: Path, k: str):
    m = d / "meta.json"
    return json.loads(m.read_text()).get(k) if m.exists() else None


def _load(p: Path) -> dict:
    return json.loads(p.read_text()) if p.exists() else {}


if __name__ == "__main__":
    raise SystemExit(main())
