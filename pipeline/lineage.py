"""Build lineage.json: concept → plan → keyframes → shots → voice → edit_plan → output → verdict.

Pairs every stage's decision in one view so 20 runs become a dataset of what concepts/plans/edits
produce ads worth shipping (D16). Extended from the single-call lineage to the multi-gen chain.
"""
from __future__ import annotations
import json
from typing import Any
from .tracing import Run


def build_lineage(run: Run, brief: dict[str, Any], concept: dict[str, Any] | None,
                  keyframes_map: dict[str, Any], shots_result: dict[str, Any],
                  voice: dict[str, Any], edit_plan: dict[str, Any],
                  review: dict[str, Any], video_path: str) -> None:
    op_path = run.dir / "06_operator_review.json"
    operator = json.loads(op_path.read_text()) if op_path.exists() else {}
    _ch = (concept or {}).get("chosen", {}) or {}
    clips = shots_result.get("clips", {})
    lineage = {
        "run_id": run.run_id,
        "business": run.business,
        "concept": {"name": _ch.get("name"), "why_bold": _ch.get("why_bold")},
        "director_decision": {
            "angle": brief.get("creative_angle"),
            "total_duration_s": brief.get("total_duration_s"),
            "composition_reasoning": brief.get("composition_reasoning"),
            "pacing": brief.get("pacing"), "editing_feel": brief.get("editing_feel"),
            "script": brief.get("script"),
            "segments": [{"n": s.get("n"), "type": s.get("type"), "intent": s.get("intent"),
                          "asset_ref": s.get("asset_ref") or s.get("clip_ref")
                          or s.get("moodboard_assets") or s.get("card_template")}
                         for s in brief.get("segments", [])],
        },
        "keyframes": {n: {"mode": v.get("mode")} for n, v in (keyframes_map or {}).items()},
        "shots": {
            "approved": [n for n, c in clips.items() if c],
            "flagged": shots_result.get("flagged", []),
        },
        "voice": {"duration_ms": voice.get("duration_ms"),
                  "lines": [l.get("text") for l in voice.get("lines", [])]},
        "edit_plan": {
            "segments": [{"type": s.get("type"), "duration_s": s.get("duration_s"),
                          "transition_in": s.get("transition_in")}
                         for s in (edit_plan or {}).get("segments", [])],
            "caption_count": len((edit_plan or {}).get("captions", [])),
        },
        "output": video_path,
        "frames": review.get("frames", []),
        "mechanical_verdict": review.get("verdict"),
        "operator_verdict": operator.get("verdict") or "(pending — fill 06_operator_review.json)",
        "operator_brings_traffic": operator.get("brings_traffic"),
    }
    run.lineage_path.write_text(json.dumps(lineage, indent=2))
    run.log("Lineage: concept→plan→keyframes→shots→voice→edit→output→verdict written")
