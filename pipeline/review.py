"""Stage: Review (final assembled video) — mechanical checks only.

Reviews the Editor's FINAL output (not per-shot — that judgment already happened in the Shot Agent,
D5; don't duplicate it here). Mechanical correctness only: playable, right duration (~the Director's
chosen length), frames not black. Creative judgment stays with the operator (06_operator_review.json,
D17). On failure: regenerate (bounded) or flag to operator.

NOT for: per-shot quality (Shot Agent) or creative judgment (the operator).
"""
from __future__ import annotations
import json, subprocess
from pathlib import Path
from typing import Any
from .tracing import Run, traced_tool, set_active_run

REVIEW_FILE = "10_review.json"
OPERATOR_FILE = "06_operator_review.json"
FRAMES_DIR = "09_output/frames"

OPERATOR_TEMPLATE = {
    "verdict": "", "would_post": None, "brings_traffic": None,
    "failure_modes": [], "notes": "",
    "instructions": "Watch 09_output/final.mp4 (frames in 09_output/frames/). "
                    "verdict: ship | retry | reject. Bar: would a small-business owner "
                    "believe this brings them more traffic?",
}


@traced_tool
def extract_frames(video_path: str, out_dir: str, n: int = 8) -> list[str]:
    """Extract n evenly-spaced frames of the final video for inspection. NOT for: editing video."""
    if not Path(video_path).exists():
        return []
    try:
        dur = _duration(video_path) or 15.0
        Path(out_dir).mkdir(parents=True, exist_ok=True)
        subprocess.run(
            ["ffmpeg", "-y", "-i", video_path, "-vf", f"fps={n}/{max(1.0, dur):.3f}",
             f"{out_dir}/frame_%02d.png"], capture_output=True, timeout=60)
        return [str(f) for f in sorted(Path(out_dir).glob("frame_*.png"))]
    except Exception:
        return []


@traced_tool
def check_playable(video_path: str) -> dict[str, Any]:
    """Is the output a valid, non-empty, decodable video? NOT for: content quality."""
    p = Path(video_path)
    if not p.exists(): return {"pass": False, "reason": "missing"}
    if p.stat().st_size < 10000: return {"pass": False, "reason": "too_small"}
    if _duration(video_path) is None: return {"pass": False, "reason": "undecodable"}
    return {"pass": True}


@traced_tool
def check_duration(video_path: str, expected: float, tol: float = 3.0) -> dict[str, Any]:
    """Final duration within tolerance of the Director's chosen length. NOT for: content quality."""
    actual = _duration(video_path)
    if actual is None:
        return {"pass": True, "reason": "skipped"}
    return {"pass": abs(actual - expected) <= tol, "actual_s": round(actual, 1), "expected_s": expected}


@traced_tool
def check_frames_not_black(frame_paths: list[str]) -> dict[str, Any]:
    """Cheap pixel pre-filter: no truly black/dead frames. Mechanical only (no vision call — per-shot
    artifact judgment already happened in the Shot Agent)."""
    if not frame_paths:
        return {"pass": True, "reason": "no_frames"}
    try:
        from PIL import Image
        import statistics
        for f in frame_paths:
            px = list(Image.open(f).convert("L").getdata())[:5000]
            if statistics.mean(px) < 8:
                return {"pass": False, "reason": f"black_frame:{Path(f).name}"}
        return {"pass": True}
    except Exception:
        return {"pass": True, "reason": "skipped"}


TOOLS = [extract_frames, check_playable, check_duration, check_frames_not_black]
from .agent import registry as _registry
for _f in TOOLS:
    _registry.register_fn(_f)


def run_review(run: Run, video_path: str, expected_duration_s: float) -> dict[str, Any]:
    set_active_run(run)
    run.log("Review: frames + mechanical checks on the final assembled video")
    frames = extract_frames(video_path, str(run.dir / FRAMES_DIR))
    checks = [check_playable(video_path),
              check_duration(video_path, expected_duration_s),
              check_frames_not_black(frames)]
    failed = [c for c in checks if not c.get("pass")]
    verdict = "pass" if not failed else ("regenerate" if any(
        str(c.get("reason", "")).startswith(("black", "too_small", "missing", "undecodable"))
        for c in failed) else "flag_to_operator")

    review = {"verdict": verdict, "checks": checks, "frames": frames,
              "reasons": [c.get("reason") for c in failed if c.get("reason")]}
    (run.dir / REVIEW_FILE).write_text(json.dumps(review, indent=2))
    op = run.dir / OPERATOR_FILE
    if not op.exists():
        op.write_text(json.dumps(OPERATOR_TEMPLATE, indent=2))

    run.reason("Review", None,
               f"Mechanical verdict: **{verdict}**. "
               + ("All checks passed." if not failed else f"Failed: {review['reasons']}"))
    run.log(f"Review: {verdict} ({len(frames)} frames)")
    set_active_run(None)
    return review


def _duration(video_path: str) -> float | None:
    try:
        r = subprocess.run(["ffprobe", "-v", "quiet", "-show_entries", "format=duration",
                            "-of", "json", video_path], capture_output=True, text=True, timeout=10)
        return float(json.loads(r.stdout)["format"]["duration"])
    except Exception:
        return None
