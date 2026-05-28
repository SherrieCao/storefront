# Spike findings — Voice / TTS (MiniMax on fal)

**Date:** 2026-05-28 · **Status:** VERIFIED LIVE (real TTS call + timestamp probe).

## Decision
`MODEL_ROUTER["tts"] = "fal-ai/minimax/speech-02-hd"` (per operator instruction; MiniMax on fal).

## Verified params (fal API page)
- `text` (required, ≤5000 chars), `voice_id` (default "Wise_Woman"), `speed` (0.5–2.0),
  `vol` (0–10), `pitch` (−12..12), `emotion` (happy/sad/angry/fearful/disgusted/surprised/neutral),
  `audio_setting` (sample rate/bitrate/format mp3|pcm|flac), `language_boost`, `pronunciation_dict`,
  `output_format` ("url"|"hex").
- **Output (documented):** `audio` (File w/ url) + `duration_ms`. Cost **$0.10 / 1000 chars**.
- These params realize SPEC_tier2 Part B1 voice direction (concrete voice, pacing via `speed`,
  emotion).

## Line-level timestamps — RESOLVED (probed live)
The fal endpoint returns **only** `{"audio": {url}, "duration_ms"}`. Passing `subtitle_enable: true`
is **silently ignored** — no `subtitles`/`words`/timestamps appear in the output (verified: output
keys = `['audio','duration_ms']` with and without the flag). MiniMax's native subtitle feature is
**not exposed through fal.**

**Decision: derive caption timing locally.** `run_voice` splits `speech` into lines/sentences and
distributes `duration_ms` weighted by character count. Returns
`{"audio_path", "duration_ms", "lines": [{"text","start_s","end_s"}]}`. The Editor consumes that
shape and never assumes fal provides timing. (Optional later upgrade: a forced aligner over the
mp3 for tighter sync — not needed for Phase 1.)

Calibration from the spike: ~30 words rendered to **9.0s** (`duration_ms: 9000`), so the
char-weighted split lands close to real cadence.

## Stub
No `FAL_KEY` → emit a silent/placeholder mp3 of estimated duration + evenly-split line timings so the
Editor stage still runs offline.
