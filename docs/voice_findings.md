# Spike findings — Voice / TTS

**Date:** 2026-05-28 · **Status:** VERIFIED LIVE.

## Decision (updated) — ElevenLabs on fal, with timestamps
`MODEL_ROUTER["tts"] = "fal-ai/elevenlabs/tts/eleven-v3"`. MiniMax (below) is SUPERSEDED: it returns no
timestamps via fal and padded a time-list script to 25.5s (run 0003's 15s-card bug). ElevenLabs gives
word/character timestamps AND paces naturally.

## Voice ROUTING (operator policy, 2026-06-02) — `pipeline/voice.py _select_voice`
The flat default ("Rachel" @ stability 0.5) read as DULL. We stay on eleven-v3 (it's the ONLY expressive
fal TTS that returns timestamps — Maya1 is more emotive but outputs no alignment → would break captions,
same reason MiniMax was dropped), and instead pick the VOICE + stability per business. Precedence:
**gender > region > vertical** (operator-confirmed). Matched against business NAME + operator BRIEF
(vertical/gender) and LOCATION (region) — never the generated script.
1. **Male-target (gender, top):** casual/young (fitness, gym, barber, food truck, tattoo, brewery) →
   **Will**; premium/older (dealership, auto, fine dining, steakhouse, whiskey, cigar, golf) → **Charlie**.
2. **Southern state (region):** TX FL GA NC SC TN AL MS LA AR KY VA WV OK → **Aria** (beats vertical).
3. **Vertical:** massage/therapy → **Jessica**; spa/wellness/skincare/yoga → **Sarah**;
   bakery/daycare/florist/family → **Matilda**; tech/SaaS/gender-neutral → **River**.
4. **Default → Laura.**
Stability per voice (expressiveness lever; lower = more expressive): Will/Charlie/Aria 0.3, Laura 0.35,
Matilda/River 0.4, Jessica/Sarah 0.5 (calming = smoother/steadier). eleven-v3 also supports inline audio
tags (`[excited]`, `[warmly]`, `[laughs]`) — available if we later want the script to carry emotion cues.
All 8 routed voices verified to return timestamps (sample set in `runs/0025/voice_ab/`).

### ElevenLabs eleven-v3 — VERIFIED LIVE
- Endpoint `fal-ai/elevenlabs/tts/eleven-v3`. Params: `text`, `voice` (default "Rachel"),
  `stability` (0–1), `similarity_boost`, `style`, **`speed` (0.7–1.2 ONLY — narrow, so size the
  script to fit; don't rely on speed)**, `apply_text_normalization` (auto/on/off — controls spelling
  out numbers like "9 AM"), `language_code`, **`timestamps: true`**.
- Output: `{audio:{url}, timestamps:[ {characters:[...], character_start_times_seconds:[...],
  character_end_times_seconds:[...]} , ... ]}` — **character-level alignment**, chunked into a list
  (first chunk may be empty). Reconstruct per-word / per-line timing by flattening chars across all
  chunks and taking the first char's start / last char's end of each line. This replaces the old
  char-weighted timing estimate with REAL timestamps for caption sync + line→segment alignment.
- **Pacing:** a 28-word FLOWING script → **13.6s** (~124 wpm, natural) vs MiniMax 25.5s for a 31-word
  time-list. Rule of thumb for script-sizing: **~2.3 words/sec** (17s ≈ 40 words, 30s ≈ 70).
- Cost: per-character (verify exact rate on first run; small vs Seedance). Keep the budget reserve.

---
## (Superseded) MiniMax on fal — kept for reference
`fal-ai/minimax/speech-02-hd`.

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
