"""Enhance: apply triage's per-asset remediation to recoverable photos.

Targeted salvage, not blanket. Relight is LOCAL (Pillow brightness/contrast — content-preserving,
no hallucination); upscale/sharpen uses fal clarity-upscaler. The enhanced photos feed the
keyframes stage (preserve / generate_from_real start frames) and moodboard compositions.

Multi-gen note: there is no Seedance video-reference trimming here anymore. Per the bright line
(D21), real_clip segments are trimmed by REMOTION in the editor (startFrom/endAt), and seedance_shot
segments are generated from image keyframes — neither needs a pre-trimmed @Video clip. The old
single-call path's trim_video_refs/generate_video are intentionally not ported.

NOT for: creative decisions, prompt composition, or video generation.
"""
from __future__ import annotations
import json, shutil
from pathlib import Path
from typing import Any
from . import config
from .tracing import Run

ENHANCED_DIR = "03_enhanced"


def enhance_assets(run: Run, inventory: dict[str, Any], *, use_cache: bool = False) -> dict[str, str]:
    """Apply triage's per-asset remediation (upscale/sharpen/relight) to recoverable photos.
    Returns {original_path: enhanced_path} and merges it into inventory["_enhancement_map"] so
    downstream stages (keyframes/moodboard) resolve real photos to their enhanced versions."""
    out_dir = run.dir / ENHANCED_DIR
    out_dir.mkdir(parents=True, exist_ok=True)
    cache = out_dir / "map.json"
    if use_cache and cache.exists():
        mapping = json.loads(cache.read_text())
        inventory.setdefault("_enhancement_map", {}).update(mapping)
        run.log("Enhance: loaded from cache"); return mapping

    to_fix = [a for a in inventory.get("images", [])
              if a.get("recoverable") and a.get("remediation")]
    run.log(f"Enhance: {len(to_fix)} photos need targeted remediation")
    mapping = {}
    for a in to_fix:
        src = a["path"]
        dst = out_dir / f"enh_{Path(src).name}"
        rem = a.get("remediation", [])
        if not config.FAL_KEY:
            run.log(f"Enhance: STUB {Path(src).name} ({', '.join(rem)})")
            shutil.copy2(src, dst)
        else:
            _enhance_one(run, src, str(dst), rem)
        mapping[src] = str(dst)
    run.add_cost("enhance", round(len(to_fix) * config.FAL_ENHANCE_COST, 6))
    inventory.setdefault("_enhancement_map", {}).update(mapping)
    cache.write_text(json.dumps(mapping, indent=2))
    return mapping


def _is_degenerate(path: str) -> bool:
    """True if `path` isn't a usable image: unopenable, empty, near-black, or near-uniform. The fal
    upscaler intermittently returns a BLACK/error frame (run 0035: it overwrote good relit frames with
    pitch-black, which then fed Nano Banana and produced moodboards unrelated to the real photos). A
    legit dark-but-detailed photo has real variance (high stddev), so we gate on BOTH low mean AND low
    stddev to avoid rejecting a genuinely moody shot."""
    from PIL import Image, ImageStat
    try:
        g = Image.open(path).convert("L")
        st = ImageStat.Stat(g)
        return st.mean[0] < 10 and st.stddev[0] < 8
    except Exception:
        return True


def _enhance_one(run: Run, src: str, dst: str, remediation: list[str]) -> None:
    """Apply triage's remediation. Relight is done LOCALLY with Pillow brightness/contrast —
    content-preserving, no API, no hallucination. Upscale/sharpen uses fal clarity-upscaler; when
    both apply, the locally-relit file is what gets upscaled. The fal result is VALIDATED — a black/
    degenerate upscale never overwrites the good relit/source image (D54)."""
    from PIL import Image, ImageEnhance
    relight = any(r.startswith("relight") for r in remediation)
    upscale = any(r in ("upscale", "sharpen") for r in remediation)
    if relight:
        factor = 1.35 if "relight_brighten" in remediation else 0.8
        img = ImageEnhance.Brightness(Image.open(src).convert("RGB")).enhance(factor)
        img = ImageEnhance.Contrast(img).enhance(1.08)
        img.save(dst)
        run.log(f"Enhance: relit locally (brightness x{factor}) {Path(src).name}")
    if upscale:
        import fal_client, urllib.request, tempfile
        from .llm import ascii_safe_path
        pre = dst if relight else src                      # the best image we have BEFORE upscaling
        try:
            res = fal_client.subscribe(config.MODEL_ROUTER["enhance_upscale"],
                                       arguments={"image_url": fal_client.upload_file(ascii_safe_path(pre)),
                                                  "upscale_factor": 2})
            tmp = tempfile.NamedTemporaryFile(suffix=Path(dst).suffix or ".jpg", delete=False)
            tmp.close()
            urllib.request.urlretrieve(res["image"]["url"], tmp.name)
            if _is_degenerate(tmp.name):                   # upscaler returned black/error — DON'T ship it
                if not relight:
                    shutil.copy2(src, dst)                 # ensure dst exists (source is the fallback)
                run.log(f"[OPERATOR ACTION] Enhance: upscaler returned a degenerate (black/blank) frame for "
                        f"{Path(src).name} — kept the {'relit' if relight else 'original'} image instead.")
            else:
                shutil.move(tmp.name, dst)
                run.log(f"Enhance: upscaled {Path(src).name}")
        except Exception as e:
            if not relight:
                shutil.copy2(src, dst)                      # never leave dst missing / half-written
            run.log(f"Enhance: upscale failed for {Path(src).name} ({str(e)[:60]}) — kept "
                    f"{'relit' if relight else 'original'} image.")
    elif not relight:
        shutil.copy2(src, dst)
    # final safety net: whatever path ran, dst must be a usable image (never a black frame downstream)
    if _is_degenerate(dst):
        shutil.copy2(src, dst)
        run.log(f"[OPERATOR ACTION] Enhance: result for {Path(src).name} was degenerate — reverted to the raw asset.")
