# Spike findings — Per-shot Seedance 2.0 (image-to-video, silent)

**Date:** 2026-05-28 · **Status:** VERIFIED LIVE (real gen from a Nano Banana keyframe, probed output)

## Decision
Per-shot generation uses **`bytedance/seedance-2.0/image-to-video`** (standard) /
**`bytedance/seedance-2.0/fast/image-to-video`** (fast/draft), one call per video shot, the shot's
keyframe as the start frame, **`generate_audio: false`**.

## Verified request/response shape
```python
res = fal_client.subscribe("bytedance/seedance-2.0/fast/image-to-video", arguments={
    "image_url": <uploaded keyframe url>,   # start frame; JPEG/PNG/WebP, ≤30MB
    "prompt": "<single-shot motion: one subject, one action, one camera; no cuts>",
    "resolution": "480p",                   # 480p | 720p | 1080p
    "duration": "4",                        # 4..15 (or "auto")
    "aspect_ratio": "9:16",                 # auto|21:9|16:9|4:3|1:1|3:4|9:16
    "generate_audio": False,                # voice is separate; Editor handles ambient
    # "end_image_url": ...,                 # optional end frame for transitions (Phase 2)
    # "seed": ...,                          # reproducibility
})
# -> {"video": {"url", "content_type", "file_name", "file_size"}, "seed": int}
```

## Verified facts
- **`generate_audio: False` → the rendered mp4 has NO audio stream** (ffprobe: `['video']` only). ✓
  This is exactly what the architecture needs (voice is a separate TTS stage; ambient via Editor).
- A **Nano Banana keyframe works directly as the start frame** — keyframe→shot mechanic confirmed.
- **Minimum duration ≈ 4s.** Asked for `"4"`, got a **3.92s** clip. There is no sub-4s shot; the
  Editor trims shots down to voice timing. (The old architecture's ~2s shots are NOT achievable as
  standalone Seedance gens — design around ≥4s gens, trimmed in the edit.)

## ⚠️ Latency (important for the multi-shot architecture)
The single 4s/480p/fast gen took **~116 seconds (~2 min)**. With N shots × up to 3 retries each, a
**sequential** shot stage is many minutes of wall-clock. **Generate shots concurrently** (fan out
the per-shot loops; the judge+retry is per-shot independent) and only serialize the cost-ceiling
check. Standard tier / higher res will be slower still.

## Cost
fal fast image-to-video ≈ **~$1 per 4s clip** at draft settings; standard tier and 720p/1080p cost
more. This is the dominant cost in a run — see `docs/cost_model.md` / the ceiling discussion. Audio
generation is free on Seedance (but we keep it OFF regardless).

## Difference from the old single-call architecture
Old: ONE `reference-to-video` call rendered a labeled multi-shot 15s ad (cuts + ambient + native VO
in one pass). New: **one `image-to-video` call per shot, single-shot prompt, silent, keyframe start
frame**, judged + retried individually, then assembled by the Editor. Seedance is used as a per-shot
clip generator, not an in-model editor.
