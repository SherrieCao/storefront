"""Per-business topic history (SPEC_editor_loop_topic_history_reviews Part B).

After every successful run we append what the pipeline chose (concept, angle, review detail, voice
style, ending type) to inputs/<business>/history.json. Concept (and, lighter, the Director) read it
back to STEER AWAY from repeating themselves across runs — the fix for the observed "every Conway run
lands the same concept + a card ending." History lives in the business INPUT dir (persists across runs),
never in the per-run runs/ dir.

De-weighting is a SOFT steer, never a hard ban: if the operator's brief asks for a repeat, honor it.

NOT for: blocking a concept, or any creative judgment — it only surfaces what's already been used.
"""
from __future__ import annotations
import json
from datetime import datetime
from pathlib import Path
from typing import Any
from . import config


def _history_path(slug: str) -> Path:
    return config.INPUTS_DIR / slug / "history.json"


def load_history(slug: str) -> dict[str, Any] | None:
    p = _history_path(slug)
    if not slug or not p.exists():
        return None
    try:
        return json.loads(p.read_text())
    except Exception:
        return None


def _read_verdict(run_id: str) -> str:
    """The operator's verdict for a PAST run, if they've filled it in since (else 'pending')."""
    p = config.RUNS_DIR / run_id / "06_operator_review.json"
    if not p.exists():
        return "pending"
    try:
        return (json.loads(p.read_text()).get("verdict") or "").strip() or "pending"
    except Exception:
        return "pending"


def record_run(run, concept: dict[str, Any], brief: dict[str, Any],
               research: dict[str, Any] | None = None) -> None:
    """Append this run to inputs/<business>/history.json (idempotent on run_id). Also refreshes prior
    runs' operator verdicts from their run dirs (the operator fills those in after watching)."""
    slug = run.business
    if not slug:
        return
    chosen = (concept or {}).get("chosen", {}) or {}
    ending = (brief or {}).get("ending", {}) or {}
    entry = {
        "run_id": run.run_id,
        "date": datetime.now().strftime("%Y-%m-%d"),
        "concept_name": chosen.get("name", ""),
        "concept_summary": (chosen.get("concept", "") or "")[:200],
        "creative_angle": (brief or {}).get("creative_angle", ""),
        "review_detail_used": (research or {}).get("detail", ""),   # top anchor candidate (best-effort)
        "voice_style": (brief or {}).get("voice_style", ""),
        "ending_type": ending.get("ending_type") or (brief or {}).get("ending_type", ""),
        "pacing": (brief or {}).get("pacing", ""),
        "operator_verdict": _read_verdict(run.run_id),
    }
    hist = load_history(slug) or {"business": slug, "runs": []}
    hist["runs"] = [r for r in hist.get("runs", []) if r.get("run_id") != run.run_id] + [entry]
    for r in hist["runs"]:                                  # refresh past verdicts the operator has since filled
        r["operator_verdict"] = _read_verdict(r.get("run_id", ""))

    def _roll(key: str, keep_dupes: bool = False) -> list[str]:
        out: list[str] = []
        for r in hist["runs"]:
            v = r.get(key)
            if v and (keep_dupes or v not in out):
                out.append(v)
        return out

    hist["concepts_used"] = _roll("concept_name")
    hist["creative_angles_used"] = _roll("creative_angle")
    hist["review_details_used"] = _roll("review_detail_used")
    hist["voice_styles_used"] = _roll("voice_style")
    hist["ending_types_used"] = _roll("ending_type", keep_dupes=True)   # keep repeats so "card,card,card" shows

    p = _history_path(slug)
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(json.dumps(hist, indent=2))
    try:
        run.log(f"History: recorded run {run.run_id} → inputs/{slug}/history.json "
                f"({len(hist['runs'])} run(s); endings so far: {hist['ending_types_used']})")
    except Exception:
        pass


def concept_history_block(slug: str) -> dict[str, Any] | None:
    """Structured `previous_runs` block for the Concept payload. None on a first run (nothing to avoid)."""
    h = load_history(slug)
    if not h or not h.get("runs"):
        return None
    return {
        "concepts_used": h.get("concepts_used", []),
        "creative_angles_used": h.get("creative_angles_used", []),
        "review_details_used": h.get("review_details_used", []),
        "ending_types_used": h.get("ending_types_used", []),
        "note": ("Explore a DIFFERENT angle and anchor on a review detail you haven't used yet. "
                 "Repetition across runs is a creative failure — UNLESS the brief explicitly asks for a "
                 "repeat."),
    }


def director_ending_hint(slug: str) -> list[str] | None:
    """The ending types used in past runs, so the Director / Ending Agent stops defaulting to one."""
    h = load_history(slug)
    endings = (h or {}).get("ending_types_used", [])
    return endings or None
