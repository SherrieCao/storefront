"""Stage 0: Asset Triage (salvage operation, not a bouncer).

Assesses every provided asset (photos AND videos), and instead of rejecting weak
ones, writes a REMEDIATION plan: what's wrong + what enhancement should fix it.
Genuinely unrecoverable assets are flagged honestly. Parses explicit before/after
statements from the brief.

NOT for: creative decisions, prompt writing, generation.
"""
from __future__ import annotations

import json
import shutil
from pathlib import Path
from typing import Any

from .tracing import Run, traced_tool, set_active_run

TRIAGE_FILE = "00_triage.json"
IMG_EXTS = {".png", ".jpg", ".jpeg", ".webp"}
VID_EXTS = {".mp4", ".mov", ".webm", ".m4v"}


@traced_tool
def assess_image(image_path: str) -> dict[str, Any]:
    """Assess a photo and produce a REMEDIATION plan (not a pass/fail verdict).

    Returns: {path, resolution, blur_score, lighting_score, remediation: [...],
              recoverable: bool, note}
    NOT for: editing the image — assessment + remediation planning only.
    """
    try:
        from PIL import Image, ImageFilter
        import statistics
        img = Image.open(image_path).convert("RGB")
        w, h = img.size
        gray = img.convert("L").filter(ImageFilter.FIND_EDGES)
        px = list(gray.getdata())[:10000]
        blur = min(100, int(statistics.variance(px) / 2))
        bright = sum(px) / len(px)
        lighting = 100 - int(abs(bright - 128) / 1.28)

        remediation = []
        if w < 720 or h < 720:        remediation.append("upscale")
        if blur < 30:                 remediation.append("sharpen")
        if lighting < 45:             remediation.append("relight_brighten")
        if bright > 200:              remediation.append("relight_reduce")
        # recoverable unless catastrophically small AND blurry
        recoverable = not (max(w, h) < 400 and blur < 10)
        note = "good as-is" if not remediation else f"needs: {', '.join(remediation)}"
        if not recoverable:
            note = "likely unrecoverable even with enhancement — use only if nothing better"
        return {"path": image_path, "type": "image", "resolution": f"{w}x{h}",
                "blur_score": blur, "lighting_score": lighting,
                "remediation": remediation, "recoverable": recoverable, "note": note}
    except Exception as e:
        return {"path": image_path, "type": "image", "recoverable": False,
                "remediation": [], "note": f"unreadable: {e}"}


@traced_tool
def assess_video(video_path: str) -> dict[str, Any]:
    """Assess a provided video clip for use as a Seedance @Video reference.

    Returns: {path, duration_s, resolution, usable_as_reference, note}
    Usable if a sane source (readable, <=1920px, <=50MB) — length is NOT a gate: the Director SEES the
    full clip and picks the best ~2s window (clip_start_s), which trim_video_refs cuts for the @Video ref.
    NOT for: editing or trimming — assessment only.
    """
    try:
        import subprocess
        r = subprocess.run(
            ["ffprobe", "-v", "quiet", "-print_format", "json",
             "-show_format", "-show_streams", video_path],
            capture_output=True, text=True, timeout=15)
        info = json.loads(r.stdout)
        vstream = next((s for s in info.get("streams", []) if s.get("codec_type") == "video"), {})
        dur = float(info.get("format", {}).get("duration", 0))
        w, h = int(vstream.get("width", 0)), int(vstream.get("height", 0))
        size_mb = float(info.get("format", {}).get("size", 0)) / 1e6
        usable = dur > 0 and max(w, h) <= 1920 and size_mb <= 50   # any length — the Director clips ~2s
        note = (f"usable as @Video reference ({dur:.0f}s) — Director picks the ~2s window" if usable
                else f"unusable source ({w}x{h}, {size_mb:.0f}MB)")
        return {"path": video_path, "type": "video", "duration_s": round(dur, 1),
                "resolution": f"{w}x{h}", "size_mb": round(size_mb, 1),
                "usable_as_reference": usable, "note": note}
    except FileNotFoundError:
        return {"path": video_path, "type": "video", "usable_as_reference": True,
                "note": "ffprobe missing — assumed usable, verify at build"}
    except Exception as e:
        return {"path": video_path, "type": "video", "usable_as_reference": False,
                "note": f"unreadable: {e}"}


@traced_tool
def detect_logo(image_path: str) -> dict[str, Any]:
    """Heuristic: does this image look like a logo? NOT for: extracting it."""
    try:
        from PIL import Image
        img = Image.open(image_path)
        alpha = img.mode in ("RGBA", "LA") or "transparency" in img.info
        w, h = img.size; aspect = w / h if h else 1
        # transparency is the reliable logo signal; only also treat a SMALL near-square opaque
        # image as a logo. (The old <2000px rule false-flagged ordinary phone photos as logos.)
        return {"path": image_path,
                "looks_like_logo": alpha or (max(w, h) <= 512 and 0.3 < aspect < 3.0),
                "has_transparency": alpha}
    except Exception as e:
        return {"path": image_path, "looks_like_logo": False, "error": str(e)}


@traced_tool
def extract_palette(image_path: str, k: int = 4) -> list[str]:
    """Dominant hex colors for brand palette. NOT for: applying colors."""
    try:
        from PIL import Image
        from collections import Counter
        img = Image.open(image_path).convert("RGB").resize((128, 128))
        q = img.quantize(colors=k, method=Image.Quantize.MEDIANCUT)
        pal = q.getpalette()[:k*3]
        out = []
        for idx, _ in Counter(q.getdata()).most_common(k):
            r, g, b = pal[idx*3:idx*3+3]; out.append(f"#{r:02X}{g:02X}{b:02X}")
        return out
    except Exception:
        return []


@traced_tool
def _load_brief(snap, fallback_business: str) -> tuple[str, str, str]:
    """Input contract: prefer `brief.json` {name, location, brief}; fall back to free-text `brief.txt`
    (+ the --business label as the name). `name` gives the research lookup a clean business name;
    `location` disambiguates it; `brief` is the free-text creative ask (carries everything else)."""
    bj = snap / "brief.json"
    if bj.exists():
        try:
            d = json.loads(bj.read_text())
            return (str(d.get("name") or fallback_business).strip(),
                    str(d.get("location") or "").strip(),
                    str(d.get("brief") or "").strip())
        except Exception:
            pass
    txt = (snap / "brief.txt").read_text().strip() if (snap / "brief.txt").exists() else ""
    return fallback_business, "", txt


def role_from_name(name: str) -> str | None:
    """An EXPLICIT before/after label the operator put in the filename (e.g. before_1.jpg / after-2.png).
    Returns "before" | "after" | None. This is an operator statement, not inference about pixels."""
    stem = Path(name).stem.lower()
    if stem.startswith("before") and (len(stem) == 6 or stem[6] in "_- 0123456789"):
        return "before"
    if stem.startswith("after") and (len(stem) == 5 or stem[5] in "_- 0123456789"):
        return "after"
    return None


def parse_before_after(brief: str, image_names: list[str] | None = None) -> dict[str, Any]:
    """Unlock the before/after format ONLY on an EXPLICIT operator statement (D11, amended): either the
    brief text says before+after in plain language, OR the operator labeled files with before_/after_
    prefixes (≥1 of each). Filename prefixes are an explicit label, not inference about the pixels.
    Returns {has_before_after, source}.
    NOT for: inferring before/after from image CONTENT.
    """
    roles = [role_from_name(n) for n in (image_names or [])]
    if "before" in roles and "after" in roles:
        return {"has_before_after": True, "source": "filenames",
                "note": "operator labeled before_/after_ files (≥1 of each)"}
    if brief:
        bl = brief.lower()
        if "before" in bl and "after" in bl:
            return {"has_before_after": True, "source": "brief",
                    "note": "operator stated before/after in brief"}
    return {"has_before_after": False, "source": "none",
            "note": "no explicit before/after statement; format gated off"}


@traced_tool
def surface_gap_ask(inventory: dict[str, Any]) -> str | None:
    """Surface the ONE highest-value asset gap to the operator. NOT for: creative direction."""
    imgs = inventory.get("images", [])
    vids = inventory.get("videos", [])
    good = [a for a in imgs if not a.get("remediation") and a.get("recoverable")]
    btype = inventory.get("business_type", "")
    if not imgs and not vids:
        return "No usable assets at all. Ask for 3–5 photos or a short clip in good light."
    if not inventory.get("has_before_after") and btype in ("salon", "nail", "cleaning", "detailing"):
        return "Before/after shots would be the single most valuable addition for this vertical (state which is which in the brief)."
    if not inventory.get("has_logo"):
        return "No logo found. A transparent-background PNG logo would help."
    if len(good) < 1:
        return "All photos need enhancement. A couple of clean, well-lit shots would raise the ceiling."
    return None


TOOLS = [assess_image, assess_video, detect_logo, extract_palette,
         parse_before_after, surface_gap_ask]

# Register so they're loop-ready; triage stays deterministic orchestration in v0.
from .agent import registry as _registry
for _f in TOOLS:
    _registry.register_fn(_f)


def run_triage(run: Run, input_dir: Path, *, use_cache: bool = False) -> dict[str, Any]:
    cache = run.dir / TRIAGE_FILE
    if use_cache and cache.exists():
        run.log("Triage: loaded from cache"); return json.loads(cache.read_text())

    snap = run.dir / "input_snapshot"
    if snap.exists(): shutil.rmtree(snap)
    shutil.copytree(input_dir, snap)

    set_active_run(run)
    run.log("Triage: assessing + planning salvage for all assets")

    all_files = sorted(p for p in snap.rglob("*") if p.suffix.lower() in IMG_EXTS | VID_EXTS)
    images = [p for p in all_files if p.suffix.lower() in IMG_EXTS]
    videos = [p for p in all_files if p.suffix.lower() in VID_EXTS]

    # logo
    logo = None
    for name in ("logo.png", "logo.jpg", "logo.jpeg", "logo.webp"):
        if (snap / name).exists(): logo = str(snap / name); break
    if not logo:
        for img in images:
            if detect_logo(str(img)).get("looks_like_logo"): logo = str(img); break

    palette = extract_palette(logo) if logo else (extract_palette(str(images[0])) if images else [])

    photo_paths = [p for p in images if str(p) != logo]
    img_assessments = [assess_image(str(p)) for p in photo_paths]
    for a, p in zip(img_assessments, photo_paths):
        a["role"] = role_from_name(p.name)        # before/after from the operator's filename, or None
    vid_assessments = [assess_video(str(p)) for p in videos]

    biz_name, location, brief = _load_brief(snap, run.business)
    ba = parse_before_after(brief, [p.name for p in photo_paths])

    inventory = {
        "business": biz_name, "location": location, "brief": brief,
        "has_logo": logo is not None, "logo_path": logo, "palette": palette,
        "images": img_assessments, "videos": vid_assessments,
        "has_before_after": ba["has_before_after"], "before_after_source": ba["source"],
        "image_count": len(img_assessments), "video_count": len(vid_assessments),
        "good_as_is": sum(1 for a in img_assessments if not a.get("remediation") and a.get("recoverable")),
        "needs_enhancement": sum(1 for a in img_assessments if a.get("remediation") and a.get("recoverable")),
        "unrecoverable": sum(1 for a in img_assessments if not a.get("recoverable")),
    }
    inventory["gap_ask"] = surface_gap_ask(inventory)

    run.log(f"Triage: {inventory['image_count']} photos "
            f"({inventory['good_as_is']} good, {inventory['needs_enhancement']} salvageable, "
            f"{inventory['unrecoverable']} unrecoverable), {inventory['video_count']} videos, "
            f"logo={'y' if logo else 'n'}, before/after={'y' if ba['has_before_after'] else 'n'}")
    if inventory["gap_ask"]:
        run.log(f"Triage: GAP → {inventory['gap_ask']}")

    cache.write_text(json.dumps(inventory, indent=2))
    set_active_run(None)
    return inventory
