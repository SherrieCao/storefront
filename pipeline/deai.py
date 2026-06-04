"""De-AI temporal post-processing (D47).

After the Shot Agent APPROVES a seedance_shot clip, run a single ffmpeg pass that adds the frame-to-frame
imperfection a generated clip lacks — so it reads as phone-captured, not AI. Applied ONLY to seedance_shot
clips (called from shots.py after approval). Color is DELIBERATELY NOT touched — texture only (grain,
vignette, softness, handheld micro-jitter) — so a genuinely vivid result (the salon's hair, a bakery's
golden crust) stays vivid (D41). Zero API cost. Graceful: any ffmpeg failure returns the source clip.

NOT for: real_clip, card, or moodboard segments (already real / templated).
"""
from __future__ import annotations
import subprocess
from pathlib import Path

from . import config
from .tracing import Run

# Per-intensity TEXTURE knobs. Saturation is intentionally omitted — color is untouched (D41); de-AI here
# is grain + vignette + softness + jitter only.
_PRESETS = {
    #             grain(c0s)  vignette   softness    jitter(px)
    "light":    {"grain": 5,  "vig": "PI/6", "soft": -0.2, "jit": 1},
    "moderate": {"grain": 8,  "vig": "PI/5", "soft": -0.3, "jit": 2},
    "heavy":    {"grain": 12, "vig": "PI/4", "soft": -0.4, "jit": 3},
}


def _filter_chain(p: dict) -> str:
    j = p["jit"]
    # Handheld micro-jitter: overscan, then a per-frame random crop offset of ±j px. ffmpeg's random(idx)
    # advances its state each evaluation, so the offset varies PER FRAME (a constant would be static = an
    # obvious fake). The 2px overscan margin keeps the crop in-bounds at the random extremes.
    jitter = (f"scale={1080 + 2*j + 2}:{1920 + 2*j + 2},"
              f"crop=1080:1920:'(iw-1080)/2+random(1)*{2*j}-{j}':'(ih-1920)/2+random(2)*{2*j}-{j}'")
    grain = f"noise=c0s={p['grain']}:c0f=t+u"            # temporal (t) — per-frame sensor noise
    vignette = f"vignette={p['vig']}"                    # subtle lens edge-darkening
    soft = f"unsharp=3:3:{p['soft']}:3:3:{p['soft']}"    # negative amount = slight blur (kills razor sharpness)
    return ",".join([jitter, grain, vignette, soft])


def deai_clip(run: Run, src: str, dst: str, intensity: str | None = None) -> str:
    """De-AI texture pass `src` -> `dst` (one ffmpeg pass). Returns `dst` on success, else `src` (never
    block the run on a cosmetic post-process). Color is NOT altered (D41)."""
    name = intensity or config.DEAI_DEFAULT_INTENSITY
    preset = _PRESETS.get(name, _PRESETS["moderate"])
    try:
        r = subprocess.run(
            ["ffmpeg", "-y", "-i", src, "-vf", _filter_chain(preset),
             "-c:v", "libx264", "-preset", "fast", "-crf", str(config.DEAI_CRF), "-an", dst],
            capture_output=True, timeout=120)
        if r.returncode == 0 and Path(dst).exists():
            run.log(f"De-AI: {Path(src).name} -> {Path(dst).name} ({name})")
            return dst
        run.log(f"De-AI: ffmpeg failed on {Path(src).name} (rc={r.returncode}) — using the raw clip")
    except Exception as e:
        run.log(f"De-AI: error on {Path(src).name} ({str(e)[:60]}) — using the raw clip")
    return src
