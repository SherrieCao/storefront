"""Stage: Keyframes (Nano Banana 2 on fal) — a consistent set of per-segment frames.

Two jobs (SPEC_tier3 + SPEC_followup_mixed_segments):
  1. seedance_shot start frames — the frame Seedance animates. Modes:
       generate_from_real : asset_ref is a real @Image -> Nano Banana /edit conditions on that photo
                            (keeps the real subject's identity), reframed clean to 9:16.
       generate           : asset_ref == "generated" -> Nano Banana text-to-image from the shot intent.
  2. moodboard composition frames — Nano Banana arranges the segment's real photos as a designed
     cutout composition in ONE 9:16 frame. This frame is handed to REMOTION to animate (NOT Seedance).
real_clip and card segments need no keyframe.

Consistency is held by Nano Banana's character consistency + a shared style suffix + a per-run seed.
Prompts MUST forbid on-screen text (verified spike gotcha — Nano Banana renders text unbidden).
Stubs offline (no FAL_KEY): writes placeholder frames so downstream stages still run.

NOT for: video generation (Shot Agent) or creative decisions (the Director).
"""
from __future__ import annotations
import json, shutil, threading, urllib.request
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from typing import Any
from . import config, budget
from .tracing import Run
from .translator import resolve_ref
from .triage import role_from_name

KEYFRAMES_DIR = "04_keyframes"
# Held constant across the set so the frames share a look (+ Nano Banana's built-in consistency).
# De-AI (D47): describe the PHYSICS of a phone camera, not "lo-fi" (which Nano Banana renders as a pretty
# version of lo-fi). Negatives folded into the prompt (nano-banana-2 has no negative_prompt). COLOR is
# deliberately NOT muted — "natural, not over-graded" keeps a genuinely vivid result vivid (D41).
_STYLE_SUFFIX = ("Phone-camera realism: mixed color-temperature indoor light (warm lamp + cool daylight), "
                 "deep depth of field (everything roughly in focus, no bokeh), slightly overexposed "
                 "highlights, natural color that is true to life and NOT over-graded (a genuinely vivid "
                 "subject stays vivid), slightly off-center casual composition, authentic and NOT polished. "
                 "Vertical 9:16. Absolutely NOT studio-lit, NOT shallow depth of field or bokeh, NOT "
                 "golden-hour, NOT a glossy 3D render. Absolutely NO on-screen text, words, captions, "
                 "logos, watermarks, or signage.")


def run_keyframes(run: Run, brief: dict[str, Any], inventory: dict[str, Any],
                  *, use_cache: bool = False) -> dict[str, Any]:
    out_dir = run.dir / KEYFRAMES_DIR
    out_dir.mkdir(parents=True, exist_ok=True)
    cache = out_dir / "map.json"
    if use_cache and cache.exists():
        run.log("Keyframes: loaded from cache"); return json.loads(cache.read_text())

    segments = brief.get("segments", [])
    mood = brief.get("mood", "")
    seed = int(run.run_id) if str(run.run_id).isdigit() else 7  # per-run seed -> set coherence
    kf_map: dict[str, dict[str, Any]] = {}

    need = [s for s in segments if s.get("type") in ("seedance_shot", "moodboard")]
    run.log(f"Keyframes: {len(need)} frames to build "
            f"({sum(1 for s in need if s['type']=='seedance_shot')} shot start frames, "
            f"{sum(1 for s in need if s['type']=='moodboard')} moodboard compositions)")

    # Frames are independent fal calls — generate them CONCURRENTLY (mirror shots.py). The shared per-run
    # `seed` is KEPT (set coherence; concurrency needs no distinct seed). A lock guards the kf_map write;
    # _make_keyframe's own budget.check_ceiling + add_cost/trace are thread-safe via the Run lock. (D45)
    lock = threading.Lock()

    def do_keyframe(seg: dict[str, Any]) -> None:
        n = seg.get("n")
        dst = out_dir / f"kf_{n}.png"
        if seg["type"] == "seedance_shot":
            ref = str(seg.get("asset_ref", "generated"))
            real_path = resolve_ref(inventory, ref) if ref.startswith("@Image") else None
            if real_path:
                mode, prompt, image_urls = "generate_from_real", _shot_prompt(seg, mood), [real_path]
            else:
                mode, prompt, image_urls = "generate", _shot_prompt(seg, mood), []
        else:  # moodboard
            assets = [resolve_ref(inventory, t) for t in seg.get("moodboard_assets", [])]
            image_urls = [p for p in assets if p]
            # before/after (D43): a `before` photo is the raw PROBLEM-STATE image — show it PLAIN, not a
            # beautified Nano Banana composition (it should read as the unglamorous starting point). If
            # every photo in this beat is before-role, use the raw photo directly (also skips a fal call).
            if image_urls and all(role_from_name(Path(p).name) == "before" for p in image_urls):
                shutil.copyfile(image_urls[0], dst)
                with lock:
                    kf_map[str(n)] = {"path": str(dst), "mode": "preserve_before", "segment_type": seg["type"]}
                run.log(f"Keyframes: segment {n} [preserve_before] -> {dst.name} (plain before photo, no composition)")
                return
            mode, prompt = "moodboard", _moodboard_prompt(seg, mood)

        _make_keyframe(run, mode, prompt, image_urls, str(dst), seed)
        with lock:
            kf_map[str(n)] = {"path": str(dst), "mode": mode, "segment_type": seg["type"]}
        run.log(f"Keyframes: segment {n} [{mode}] -> {dst.name}")

    workers = max(1, min(config.MAX_KEYFRAME_CONCURRENCY, len(need)))
    with ThreadPoolExecutor(max_workers=workers) as ex:
        list(ex.map(do_keyframe, need))            # ex.map re-raises the first worker exception here

    cache.write_text(json.dumps(kf_map, indent=2))
    run.reason("Keyframes", None,
               f"Built {len(kf_map)} frames (seed={seed}) for shot start frames + moodboard "
               f"compositions; consistency via Nano Banana + shared style; no on-screen text.")
    return kf_map


def _shot_prompt(seg: dict[str, Any], mood: str) -> str:
    # A keyframe is a STILL start frame; MOTION (seg["action"]) is Seedance's job downstream. Putting a
    # motion verb here ("fingers tilt to show texture") asks an image model to depict motion on a still
    # and made Nano Banana refuse (no_media) on detail-heavy macros — so we describe the SCENE, not the
    # action.
    intent = seg.get("intent", "")
    base = f"A clean, still start frame for a short ad shot: {intent}. {('Mood: ' + mood + '. ') if mood else ''}"
    if seg.get("asset_ref", "").startswith("@Image"):
        # De-AI (D47): "polished" told Nano Banana to "improve" the phone photo into a pro-looking image —
        # undoing the authentic look Seedance should inherit. PRESERVE, don't polish.
        base = ("Reframe the attached real photo into a 9:16 still frame. PRESERVE the photo's natural "
                "lighting, color temperature, and exposure character — do NOT brighten, saturate, smooth, "
                "or stylize it. The photo's imperfections (mixed light, slight noise, casual framing) are "
                "FEATURES, not defects; match the reframed output to the original photo's look. Keep the "
                "EXACT same subject(s) and setting (preserve identity). " + base)
    return base + _STYLE_SUFFIX


def _moodboard_prompt(seg: dict[str, Any], mood: str) -> str:
    return ("Compose the attached real photos as cutouts arranged into ONE designed moodboard "
            "frame — subjects cut from their backgrounds and laid out like an art-directed "
            "scrapbook/pinboard on a warm textured surface, slightly overlapping, editorial layout. "
            f"{('Mood: ' + mood + '. ') if mood else ''}Keep each real subject's likeness. "
            + _STYLE_SUFFIX)


def _fal_upload(path: str) -> str:
    """Upload to fal, robust to non-ASCII filenames. `fal_client.upload_file` ASCII-encodes the filename
    into the multipart header, so a photo named with emoji/accents (common from SMB phones — e.g. a nail
    studio's '🌊ocean.jpg') crashes every upload backend and gets MISreported as 'authentication failed'.
    Copy to an ASCII-safe temp name first when needed."""
    import fal_client
    from .llm import ascii_safe_path                    # shared fix: fal + Gemini uploads
    return fal_client.upload_file(ascii_safe_path(path))


def _make_keyframe(run: Run, mode: str, prompt: str, image_urls: list[str], dst: str, seed: int) -> None:
    if not config.FAL_KEY:
        _stub_keyframe(mode, image_urls, dst)
        run.log(f"Keyframes: STUB {Path(dst).name} ({mode})")
        return
    import fal_client
    urls = [_fal_upload(p) for p in image_urls] if image_urls else []
    # Nano Banana intermittently returns no_media_generated for a given (prompt, image, seed); the result
    # is DETERMINISTIC per seed, so a plain retry would repeat it — vary the seed each attempt. If it
    # still won't generate, fall back to the real photo rather than killing the whole run (we already
    # have it for generate_from_real / moodboard); a flat generate falls back to a placeholder frame.
    for attempt in range(3):
        budget.check_ceiling(run, budget.keyframe_image(1), "keyframes")
        try:
            s = seed + attempt * 1009
            if urls:        # generate_from_real / moodboard -> /edit with real photos as references
                res = fal_client.subscribe(config.MODEL_ROUTER["keyframe_edit"],
                                           arguments={"prompt": prompt, "image_urls": urls,
                                                      "aspect_ratio": config.ASPECT_RATIO,
                                                      "num_images": 1, "seed": s}, with_logs=False)
            else:           # generate -> text-to-image
                res = fal_client.subscribe(config.MODEL_ROUTER["keyframe"],
                                           arguments={"prompt": prompt, "aspect_ratio": config.ASPECT_RATIO,
                                                      "num_images": 1, "seed": s}, with_logs=False)
            run.add_cost("keyframes", config.NANO_BANANA_COST_PER_IMAGE)
            url = res["images"][0]["url"]
            urllib.request.urlretrieve(url, dst)
            run.trace({"step": "keyframes", "type": "fal_output", "mode": mode, "url": url, "attempt": attempt + 1})
            return
        except Exception as e:
            run.log(f"Keyframes: {Path(dst).name} attempt {attempt + 1}/3 failed ({str(e)[:70]}) — "
                    f"{'retrying with a new seed' if attempt < 2 else 'falling back to the real photo'}")
    # exhausted retries: graceful fallback (real photo if we have one, else placeholder) — never block the run
    run.log(f"[OPERATOR ACTION] keyframe {Path(dst).name} ({mode}) wouldn't generate after 3 tries — "
            f"using the real photo/placeholder so the run continues.")
    _stub_keyframe(mode, image_urls, dst)


def _stub_keyframe(mode: str, image_urls: list[str], dst: str) -> None:
    """Offline placeholder: copy the first real reference if present, else a solid 9:16 frame."""
    from PIL import Image
    if image_urls and Path(image_urls[0]).exists():
        Image.open(image_urls[0]).convert("RGB").save(dst)
    else:
        Image.new("RGB", (1080, 1920), (40, 44, 48)).save(dst)
