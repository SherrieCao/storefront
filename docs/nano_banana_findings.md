# Spike findings — Keyframes (Nano Banana 2 on fal)

**Date:** 2026-05-28 · **Status:** VERIFIED LIVE (text-to-image + real-photo edit, outputs inspected)

## Decision
Use Nano Banana 2 on **fal** for keyframes:
- `MODEL_ROUTER["keyframe"]            = "fal-ai/nano-banana-2"`        (generate mode)
- `MODEL_ROUTER["keyframe_edit"]       = "fal-ai/nano-banana-2/edit"`   (generate_from_real mode)

(Nano Banana 2 is Google's Gemini 3.1 Flash Image; also reachable directly via the Gemini API as
`gemini-3.1-flash-image` — chose fal to keep the generation stack + cost accounting in one place and
match the `_reference` fal-upload pattern.)

## Verified capabilities
- **Text-to-image** (`fal-ai/nano-banana-2`): prompt + `aspect_ratio: "9:16"` + `num_images`.
  Output `{images:[{url, content_type}], description}`. ~13.7s, $0.08/image.
- **Real-photo conditioning** (`fal-ai/nano-banana-2/edit`): `image_urls: [<uploaded real photo>]`
  + prompt. **Identity is preserved** — the real dog's face/markings carried through into a
  restyled 9:16 keyframe (inspected `spikes/out/nb_edit.png`). This is the `generate_from_real`
  mode that holds authenticity. ~15.2s.
- **Consistency:** built-in "character consistency across generations" + `seed` for reproducibility;
  for a consistent SET, pass a shared style anchor / reference image + fixed seed across calls.
- **Resolution/aspect:** 1K/2K/4K (2K=1.5×, 4K=2×, 0.5K=0.75× cost); aspect ratio controllable
  (used 9:16). Default 1K is fine for keyframes (Seedance start frame).

## ⚠️ Gotcha (verified)
Nano Banana **renders on-screen text when the prompt is loose** — the edit output added
"The New Morning Standard" / "Clean | Bright | Daycare" overlays unbidden. **Keyframe prompts MUST
explicitly forbid text/words/captions/logos** (same rule as the translator's no-text discipline).
Captions are the Editor's job, burned in post.

## Per-shot modes (maps to SPEC_tier3)
- **preserve** — real photo used as-is (no Nano Banana call).
- **generate_from_real** — `/edit` with the real photo as `image_urls` (keeps real product/identity).
- **generate** — `fal-ai/nano-banana-2` text-to-image (atmosphere / b-roll / moodboard cutouts).

## Cost
$0.08/image @ 1K. A 4–5 keyframe set ≈ $0.32–0.40. Counts toward the run ceiling.
