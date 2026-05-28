# Spike findings — Per-shot Judge (Gemini Flash, video input)

**Date:** 2026-05-28 · **Status:** VERIFIED LIVE (real call, real test clip)

## Decision
Use **`gemini-3-flash-preview`** as the per-shot judge (`MODEL_ROUTER["shot_judge"]`).

## Why
- Accepts **video** input (uploaded via the Gemini Files API, polled to `ACTIVE`).
- Returns clean structured JSON when asked (`{"pass": bool, "score": 0..1, "reasons": [...]}`).
- **Cheaper than the Director** (`gemini-3.1-pro-preview` @ $2/$12 per Mtok): Flash is
  **$0.50 input / $3.00 output per Mtok**. Video bills at ~258 tokens/sec @ 1fps.
- Real judge call measured: **in=792, out=64 tok, ~5.3s, ≈$0.0006/call.** Negligible vs the
  ~$1 Seedance gen it gates.

## Request shape (verified)
```python
from google import genai
client = genai.Client(api_key=GEMINI_API_KEY)
f = client.files.upload(file=clip_path)          # poll client.files.get(name=f.name) until state==ACTIVE
resp = client.models.generate_content(
    model="gemini-3-flash-preview",
    contents=[f, JUDGE_PROMPT],                  # video part + text prompt
)
# resp.text -> JSON; resp.usage_metadata.prompt_token_count / candidates_token_count
```

## Flash-tier models confirmed available on this key (live `models.list()`)
`gemini-3-flash-preview`, `gemini-3.5-flash`, `gemini-3.1-flash-lite`/`-lite-preview`,
`gemini-3.1-flash-image`/`-image-preview` (= Nano Banana 2 native), `gemini-2.5-flash`, …
- `gemini-3.5-flash` exists (newer) but `gemini-3-flash-preview` is the documented cheap tier and is
  proven here; stick with it. `*-flash-lite` is even cheaper if the judge proves over-budget, but
  lite may be weaker at artifact detection — only downgrade if cost forces it.

## Build notes
- Reuse the Files-API upload+poll pattern from `_reference` `review.py:check_motion_physics`.
- Judge prompt must demand JSON-only and enumerate checks: prompt adherence, artifacts
  (hands/faces/objects), temporal coherence, **keyframe-identity consistency**.
- Cost per judge call is tiny; the retry budget is dominated by Seedance, not the judge.
