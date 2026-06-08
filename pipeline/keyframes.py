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
import json, re, shutil, threading, urllib.request
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from typing import Any
from . import config, budget
from .tracing import Run
from .translator import resolve_ref, _usable_assets
from .triage import role_from_name

KEYFRAMES_DIR = "04_keyframes"
# Held constant across the set so the frames share a look (+ Nano Banana's built-in consistency).
# De-AI (D47): describe the PHYSICS of a phone camera, not "lo-fi" (which Nano Banana renders as a pretty
# version of lo-fi). Negatives folded into the prompt (nano-banana-2 has no negative_prompt). COLOR is
# deliberately NOT muted — "natural, not over-graded" keeps a genuinely vivid result vivid (D41).
# Split so the no-text ban is OPT-IN (D56): shot keyframes + synthetic assets MUST stay text-free (Seedance
# seeds shouldn't carry text), but the moodboard wants decorative scrapbook words/letters. Shots use the
# full _STYLE_SUFFIX (base + no-text); the moodboard uses _STYLE_BASE + its own narrower text rule.
_STYLE_BASE = ("Phone-camera realism: mixed color-temperature indoor light (warm lamp + cool daylight), "
               "deep depth of field (everything roughly in focus, no bokeh), slightly overexposed "
               "highlights, natural color that is true to life and NOT over-graded (a genuinely vivid "
               "subject stays vivid), slightly off-center casual composition, authentic and NOT polished. "
               "Vertical 9:16. Absolutely NOT studio-lit, NOT shallow depth of field or bokeh, NOT "
               "golden-hour, NOT a glossy 3D render.")
_NO_TEXT = " Absolutely NO on-screen text, words, captions, logos, watermarks, or signage."
_STYLE_SUFFIX = _STYLE_BASE + _NO_TEXT


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
            lead_urls = [p for p in assets if p]
            # before/after (D43): a `before` photo is the raw PROBLEM-STATE image — show it PLAIN, not a
            # beautified Nano Banana composition (it should read as the unglamorous starting point). If
            # every photo in this beat is before-role, use the raw photo directly (also skips a fal call).
            if lead_urls and all(role_from_name(Path(p).name) == "before" for p in lead_urls):
                shutil.copyfile(lead_urls[0], dst)
                with lock:
                    kf_map[str(n)] = {"path": str(dst), "mode": "preserve_before", "segment_type": seg["type"]}
                run.log(f"Keyframes: segment {n} [preserve_before] -> {dst.name} (plain before photo, no composition)")
                return
            # Enrich: a real moodboard is DENSE, so add other distinct real photos (deduped by clip) to the
            # Director's lead assets — not just 2 near-identical frames (D55).
            image_urls = _moodboard_tiles(inventory, seg) or lead_urls
            mode, prompt = "moodboard", _moodboard_prompt(seg, mood)
            run.log(f"Keyframes: segment {n} moodboard composing {len(image_urls)} distinct tiles")

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


def _clip_base(path: str) -> str:
    """Dedup key so a moodboard doesn't tile two near-identical frames of the same shot. Video-extracted
    frames (D52) are named 'frame_<clipstem>_<i>.ext' (maybe with an 'enh_' prefix) — collapse them to one
    key per source clip. Regular photos each get their own key (their stem)."""
    name = Path(path).name
    if name.startswith("enh_"):
        name = name[4:]
    stem = Path(name).stem
    if stem.startswith("frame_"):
        return "clip:" + re.sub(r"_\d+$", "", stem[len("frame_"):])
    return "file:" + stem


def _moodboard_tiles(inventory: dict[str, Any], seg: dict[str, Any]) -> list[str]:
    """The real photo tiles for a moodboard beat. The Director's chosen assets come FIRST, then the board
    is ENRICHED with other distinct real photos so it reads like an actual dense moodboard — not 2 near-
    identical frames from one clip (D55). Deduped by source clip (twin frames collapse); `before`-role
    problem photos are excluded (don't pull an unglamorous before into a beauty board — D44). Faithful
    real photos only, never invented; capped at MOODBOARD_TILE_TARGET."""
    lead = [resolve_ref(inventory, t) for t in seg.get("moodboard_assets", [])]
    pool = [resolve_ref(inventory, t) for t, _ in _usable_assets(inventory) if t.startswith("@Image")]
    seen: set[str] = set()
    tiles: list[str] = []
    for p in [x for x in lead if x] + [x for x in pool if x]:
        if role_from_name(Path(p).name) == "before":   # keep before-state photos out of beauty boards
            continue
        k = _clip_base(p)
        if k in seen:
            continue
        seen.add(k)
        tiles.append(p)
        if len(tiles) >= config.MOODBOARD_TILE_TARGET:
            break
    return tiles


def _moodboard_prompt(seg: dict[str, Any], mood: str) -> str:
    # Fidelity + density + decoration (D53/D55/D56). History: the old prompt let Nano Banana INVENT a whole
    # design (board had "nothing to do with the videos") — but the real culprit was BLACK input (D54), not
    # decoration freedom. D53/D55 then over-corrected: banning all invented "objects" + all text stripped the
    # pretty ephemera (flowers, swatches, decorative letters) the operator liked. Now that real photos are
    # guaranteed faithful, we let the model DECORATE AROUND the photos again (ephemera + small words), while
    # the photos THEMSELVES stay exactly as shot. Ends with _STYLE_BASE (no text ban) — decorative words OK.
    return ("Arrange ALL the attached real photos into ONE dense, art-directed scrapbook / mood board "
            "— the real photos laid out as overlapping Polaroid-style tiles and cut-outs, varied "
            "sizes, slight rotations, editorial collage, with tasteful tape, push-pins, and binder clips. "
            "Set the collage on a RICH, TEXTURED scrapbook background — e.g. a cork pinboard, kraft/craft "
            "paper, linen, or textured paper — that is interesting and should VARY from board to board; do "
            "NOT default to a flat plain surface or simply echo the photos' own backdrops. "
            "Decorate it like a real designer's mood board — you MAY add tasteful scrapbook ephemera in the "
            "gaps and margins around the photos: pressed flowers, sprigs, color/paint swatches, ribbons, "
            "gems, patterned washi tape, small decorative words, monogram letters, or little hand-lettered "
            "signs. Keep any decorative words SMALL and incidental (pretty accents, not headlines), and add "
            "no brand logos, watermarks, or ad-style caption bars. Make the board feel FULL, layered, and "
            "hand-made. These decorations go in the gaps and margins AROUND the photos only — they must "
            "NEVER cover, replace, alter, or be drawn onto the real photo tiles. PRESERVE each real photo's "
            "content exactly: the same subjects, designs, colors, textures, and details as shown — do NOT "
            "repaint, restyle, re-render, smooth, swap, or duplicate the photos; the real nail work stays "
            "exactly as shot. "
            f"{('Mood: ' + mood + '. ') if mood else ''}"
            + _STYLE_BASE)


def _fal_upload(path: str) -> str:
    """Upload to fal, robust to non-ASCII filenames. `fal_client.upload_file` ASCII-encodes the filename
    into the multipart header, so a photo named with emoji/accents (common from SMB phones — e.g. a nail
    studio's '🌊ocean.jpg') crashes every upload backend and gets MISreported as 'authentication failed'.
    Copy to an ASCII-safe temp name first when needed."""
    import fal_client
    from .llm import ascii_safe_path                    # shared fix: fal + Gemini uploads
    return fal_client.upload_file(ascii_safe_path(path))


def generate_synthetic_asset(run: Run, brief: dict[str, Any], idx: int) -> str | None:
    """D51 LAST RESORT: when the business is genuinely out of distinct assets to fill the video for the
    voice, synthesize ONE new text-to-image frame (Nano Banana, no real photo) from the brief's
    angle/mood, so the Director can add a beat. Returns the saved path (caller registers it in inventory)
    or None on failure. Capped + one-shot by the caller. Offline (no FAL_KEY) → a stub frame."""
    out_dir = run.dir / "asset_gen"
    out_dir.mkdir(parents=True, exist_ok=True)
    dst = out_dir / f"synth_{idx}.png"
    angle = str(brief.get("creative_angle") or brief.get("mood") or "")[:140]
    prompt = (f"A clean, candid still frame for a short ad about: {angle}. " + _STYLE_SUFFIX)
    seed = (int(run.run_id) if str(run.run_id).isdigit() else 7) + 7919 + idx
    try:
        _make_keyframe(run, "generate", prompt, [], str(dst), seed)
        if Path(dst).exists():
            run.log(f"Asset-gen: synthesized {dst.name} (text-to-image, no real photo) — last-resort fill")
            return str(dst)
    except Exception as e:
        run.log(f"Asset-gen: failed ({str(e)[:60]})")
    return None


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
