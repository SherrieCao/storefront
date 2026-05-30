# Music spike findings (Workstream D / Phase 2)

Goal: a royalty-free, **instrumental-only**, mood-matched music bed at the ad's length, plus a **beat
grid** so the editor can snap cuts onto the beat and duck the music under the voice.

## Model: `cassetteai/music-generator` (fal) — VERIFIED ✅

| | |
|---|---|
| Endpoint | `cassetteai/music-generator` |
| Input | `prompt` (string), `duration` (int seconds) |
| Output | `{"audio_file": {"url": "...generated.wav", "content_type", "file_name", "file_size"}}` — **44.1kHz WAV** |
| Latency | **~7.5s** for a 16s track (spec: 30s in <2s, 3min in <10s) |
| Cost | **$0.02 / output minute** → ≤ $0.01 for a 15–30s bed. `MUSIC_COST = 0.02` (conservative per-request) |
| Vocals | Instrumental-only by design — won't sing over the voiceover. We still pass "no vocals/lyrics" in the prompt. |

Live spike (`spikes/music_diag.py`): prompt = *"upbeat warm acoustic indie pop, bright and playful,
social media ad energy, light percussion, no vocals"*, duration 16 → returned a 16.000s WAV in 7.5s.

## Rejected: `beatoven/music-generation` ❌ (was the original D plan)
Endpoint id is correct and documented ($0.10/req, 5s–2.5min, prompt + negative_prompt + duration +
refinement + creativity + seed). But **every request submitted successfully and then hung in `Queued`
forever** — the worker never picked the job up (confirmed by polling `fal_client.status`: stuck at
`Queued`, never `InProgress`/`Completed`, across multiple attempts and several minutes each). A broken/
stalled endpoint on fal's side, not our call. Switched to CassetteAI, which is also faster + cheaper +
instrumental-only. If Beatoven recovers it's a one-line `MODEL_ROUTER["music"]` swap back.

Other fal options if needed: `fal-ai/lyria2` (Google, $0.10/30s, fixed 30s, negative prompt),
`stable-audio 2.5` (up to 190s, $0.20).

## Beat detection: `librosa` 0.11.0 — VERIFIED ✅
`librosa.beat.beat_track(y, sr)` → tempo + beat frames; `frames_to_time` → timestamps. Resample the
track to mono 22.05kHz wav (via ffmpeg) first for a reliable backend.

Live result on the 16s bed: **99.4 BPM, 25 beats, ~0.6s interval**, evenly spaced — clean grid.

**Gotcha:** librosa 0.11 returns `tempo` as a **1-element numpy array**, not a scalar. `float(tempo)`
raises `TypeError: only 0-dimensional arrays can be converted to Python scalars`. Coerce with
`float(np.atleast_1d(tempo)[0])` (handled in `music.py:_beat_grid`).

## Wiring (how the pipeline uses this)
- `pipeline/music.py` `run_music(run, brief, *, use_cache)` → `{music_path, bpm, beats[], prompt}`.
  Stubs offline (no `FAL_KEY` → no music, empty beats → editor renders exactly as before). Tolerant
  audio-url parser (`audio_file` / `audio` / `audio_url`). Budget-gated; never raises on a bad response.
- `run.py` STEPS: `…, shots, music, voice, editor, …` — music runs after shots, before the timeline is
  planned (the editor needs the beat grid).
- `editor.plan_timeline(..., beats=)` → `_snap_to_beats` nudges each interior cut to the nearest beat
  (within half a beat), respecting segment caps. No beats → no-op.
- `editor.render(..., music=)` → adds a second `<Audio>` track ducked under the voice (gain 0.18 with a
  VO, 0.55 if there's none).
