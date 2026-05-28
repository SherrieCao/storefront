#!/usr/bin/env python3
"""Diff helper between two runs — multi-gen edition.

The "what changed" between runs now lives in the SEGMENT PLAN (Director) and the EDIT PLAN (Editor)
as much as in per-shot prompts. Diffs all three: script, segment plan, and edit plan.

Usage: python tools/diff.py 0007 0008
"""
from __future__ import annotations
import sys, json, difflib
from pathlib import Path


def _load(run_id: str, name: str) -> dict:
    p = Path("runs") / run_id / name
    return json.loads(p.read_text()) if p.exists() else {}


def _segment_lines(brief: dict) -> list[str]:
    out = [f"total_duration_s: {brief.get('total_duration_s')}",
           f"pacing: {brief.get('pacing')} | editing_feel: {brief.get('editing_feel')}"]
    for s in brief.get("segments", []):
        ref = s.get("asset_ref") or s.get("clip_ref") or s.get("moodboard_assets") or s.get("card_template")
        out.append(f"{s.get('n')}. [{s.get('type')}] {s.get('duration_s')}s {ref} :: {s.get('intent','')}")
    return out


def _editplan_lines(plan_doc: dict) -> list[str]:
    plan = plan_doc.get("plan", plan_doc)
    out = []
    for s in plan.get("segments", []):
        out.append(f"[{s.get('type')}] {s.get('duration_s')}s {s.get('transition_in')} "
                   f"{s.get('card_template','')}".rstrip())
    out.append(f"captions: {len(plan.get('captions', []))}")
    return out


def _print_diff(title: str, a_id: str, b_id: str, a: list[str], b: list[str]) -> None:
    print(f"\n=== {title}: {a_id} → {b_id} ===")
    diff = list(difflib.unified_diff(a, b, lineterm="", n=2))
    print("\n".join(diff[2:]) if len(diff) > 2 else "(no change)")


def main():
    if len(sys.argv) != 3:
        print("usage: python tools/diff.py <run_a> <run_b>"); sys.exit(1)
    a, b = sys.argv[1], sys.argv[2]
    ba, bb = _load(a, "02_creative_brief.json"), _load(b, "02_creative_brief.json")
    _print_diff("Script", a, b, (ba.get("script", "")).split(), (bb.get("script", "")).split())
    _print_diff("Segment plan", a, b, _segment_lines(ba), _segment_lines(bb))
    _print_diff("Edit plan", a, b,
                _editplan_lines(_load(a, "07_edit_plan.json")),
                _editplan_lines(_load(b, "07_edit_plan.json")))


if __name__ == "__main__":
    main()
