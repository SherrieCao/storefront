# Spec — De-AI Pass: Keyframe Aesthetics + Temporal Post-Processing

> Two layers that work together to make generated footage read as phone-captured:
> **Layer 1 (keyframes)** — Nano Banana generates start frames that already look like phone photos
> (practical lighting, muted color, deep DoF, casual composition). Seedance inherits and preserves
> this look during animation. Sets the visual baseline.
> **Layer 2 (post-processing)** — ffmpeg applies temporal degradation (grain, jitter, vignette) to
> the animated clip. Adds the frame-to-frame imperfection a still keyframe can't convey.
>
> Layer 1 is probably the bigger lever — it shifts the starting point rather than degrading the
> output. Layer 2 handles what a single frame can't (temporal noise, micro-motion, AE flicker).
>
> Applied ONLY to `seedance_shot` segments. Not to real_clip, card, or moodboard.
> Layer 1: zero cost (prompt changes only). Layer 2: ~1-2s per clip (ffmpeg, zero API cost).

---

## LAYER 1 — Keyframe aesthetics (Nano Banana prompt changes)

### The problem
The current `_STYLE_SUFFIX` in `keyframes.py` is:
```
"Consistent warm documentary style, soft natural light, authentic and lo-fi,
 vertical 9:16 composition. Absolutely NO on-screen text..."
```
"Authentic and lo-fi" is vague enough that Nano Banana interprets it as "a beautifully-styled
version of lo-fi" — still professional-looking. It needs to describe the actual physics of a
phone camera, and strongly negate the AI-beautiful defaults.

### 1a. Replace `_STYLE_SUFFIX` (the global style instruction)
Replace with something like (tune the exact wording at build):
```
Phone-camera realism: mixed color-temperature indoor lighting (warm lamp + cool daylight),
deep depth of field (everything roughly in focus, no bokeh), slightly overexposed highlights,
muted flat color (not color-graded), visible ambient environment (not clean studio isolation),
slightly off-center casual composition. Authentic, NOT polished. Vertical 9:16 composition.
Absolutely NO on-screen text, NO watermarks, NO signs, NO readable words.
```

Key changes from the current suffix:
- "mixed color-temperature" replaces "soft natural light" — mixed light is THE indoor phone signal
- "deep depth of field" added — phone cameras can't do shallow DoF without portrait mode; shallow
  DoF/bokeh is an AI tell
- "slightly overexposed highlights" — phones blow highlights; AI doesn't
- "muted flat color" replaces "warm" — warm is fine but "warm" + Nano Banana = golden-hour beauty
- "slightly off-center casual composition" — phone shots aren't perfectly composed
- "NOT polished" is explicit

### 1b. Negative prompt addition
If Nano Banana supports a negative prompt (verify at build), add:
```
No studio lighting, no dramatic shadows, no rim light, no backlit halo, no golden hour,
no vivid saturated colors, no shallow depth of field, no bokeh, no professional photography,
no perfect symmetry, no clean isolated backgrounds, no lens flare, no 3D render, no glossy,
no plastic skin
```
This is sourced from Alvin Ding's anti-AI-palette recipe (from the research report). Each item
is a specific Nano Banana default that pushes toward "AI-beautiful."

If no negative prompt is supported, fold the critical ones into the positive prompt as
"absolutely NOT": "absolutely NOT studio-lit, NOT shallow-DoF, NOT vivid/saturated."

### 1c. Fix `generate_from_real` mode (THE single most impactful change)
The current prompt for `generate_from_real` says:
```
"Reframe and clean up the attached real photo into a polished 9:16 still frame"
```
**"Polished" is exactly the wrong instruction.** It tells the model to "improve" the phone photo
into a professional-looking image — undoing the natural phone aesthetics we want to preserve.

Replace with:
```
"Reframe the attached real photo into a 9:16 still frame. PRESERVE the photo's natural
lighting, color temperature, and exposure character — do NOT brighten, saturate, smooth,
or stylize. The photo's imperfections (mixed light, slight noise, casual framing) are
FEATURES, not defects. Match the reframed output to the original photo's look."
```

This is probably the single highest-impact change in the whole spec. When `generate_from_real`
preserves the real photo's phone-camera look instead of "polishing" it, Seedance inherits
authentic lighting/color from frame 1.

### 1d. Fix `generate` mode (fully-generated keyframes)
For shots where no real photo exists (atmosphere, b-roll), the style suffix does all the work.
Additionally, the per-shot prompt should include a specific light source:
```
"lit by overhead fluorescent panels and a window on the left wall"  (nail studio)
"lit by warm pendant lamps, daylight through the front door"  (cafe)
"outdoor midday, slightly overcast, no dramatic shadows"  (dog park)
```
The Translator already has "describe the actual light source in the room" guidance. Reinforce
in the keyframe prompt builder: ALWAYS include a concrete light source description, never rely
on the model's default lighting.

### 1e. `preserve` mode — no change needed
When the keyframe IS the real photo (just copied), no de-AI is needed. The photo already has
phone-camera aesthetics. Don't process it.

---

## LAYER 2 — Temporal post-processing (ffmpeg, after Shot Agent)

### Where it sits
```
shots (Shot Agent approves clip) → [de-AI pass] → editor (assembles the de-AI'd clips)
```

Applied to each approved `seedance_shot` clip. Writes to `shot_<n>_deai.mp4` alongside the
raw `shot_<n>.mp4` (preserved for comparison). The Editor receives the `_deai` versions.

### Implementation: `pipeline/deai.py`

`deai_clip(src: str, dst: str, intensity: str = "moderate") -> str`

Single-pass ffmpeg filter chain:

#### Filter 1 — Film grain / sensor noise (highest impact)
```
noise=c0s=8:c0f=t+u
```
- `c0s=8` — intensity (8 = phone in decent light; 12 = indoor/dim)
- `c0f=t+u` — temporal + uniform (t = varies per frame like real sensor; u = uniform distribution)
- MUST be temporal (per-frame). Static grain = obvious fake.

#### Filter 2 — Color desaturation + warm shift
```
eq=saturation=0.85,colorbalance=rs=0.02:gs=0.01:bs=-0.01
```
- 15% desaturation (Seedance over-saturates even from a muted keyframe)
- Tiny warm cast (phone auto-WB tends warm indoors)

NOTE: with Layer 1 keyframe changes, Seedance may already produce more muted color. If the
keyframe changes land well, reduce this to `saturation=0.90` or skip. Tune after seeing the
combined result.

#### Filter 3 — Lens vignette
```
vignette=PI/5
```
Subtle edge darkening. Real phone lenses do this.

#### Filter 4 — Slight softness
```
unsharp=3:3:-0.3:3:3:-0.3
```
Negative amount = slight blur. Removes the uncanny razor sharpness of rendered footage.

NOTE: with Layer 1 producing less sharp keyframes, Seedance output may already be softer. Same
tuning note — reduce or skip if the combined result is already soft enough.

#### Filter 5 — Handheld micro-jitter
Tiny random per-frame translate via overscan + random crop:
```
scale=1102:1958,crop=1080:1920:iw/2-540+random(0)*4-2:ih/2-960+random(0)*4-2
```
±2px random offset per frame. Overscan hides edge gaps.

NOTE: if the Remotion `handheld_jitter` motion is already applied at the composition level,
this may be redundant. Check: does `handheld_jitter` move the clip container (visible edges
stay still) or the pixels (the whole frame drifts)? If container-only, the ffmpeg version adds
per-pixel authenticity. If both, pick one — I lean ffmpeg because it's baked into the footage
before the Editor touches it.

#### Filter 6 — AE micro-fluctuation (optional, lowest priority)
```
eq=brightness=0.01*sin(2*PI*t/2.5)
```
±1% brightness wave, ~2.5s period. Only on clips ≥4s. Skip on short clips.

### The full command (moderate preset)
```bash
ffmpeg -y -i input.mp4 \
  -vf "scale=1102:1958,
       crop=1080:1920:iw/2-540+random(0)*4-2:ih/2-960+random(0)*4-2,
       noise=c0s=8:c0f=t+u,
       eq=saturation=0.85,
       colorbalance=rs=0.02:gs=0.01:bs=-0.01,
       vignette=PI/5,
       unsharp=3:3:-0.3:3:3:-0.3" \
  -c:v libx264 -preset fast -crf 20 \
  -an \
  output_deai.mp4
```
Single pass. ~1-2s per clip. CRF 20 (grain needs bitrate — don't go above 23).

### Intensity presets

| Preset | Grain | Saturation | Vignette | Softness | Jitter | AE flicker |
|---|---|---|---|---|---|---|
| `light` | c0s=5 | 0.90 | PI/6 | -0.2 | ±1px | off |
| `moderate` (default) | c0s=8 | 0.85 | PI/5 | -0.3 | ±2px | off |
| `heavy` | c0s=12 | 0.80 | PI/4 | -0.4 | ±3px | on |

Default: `moderate`. The shot judge could eventually recommend intensity based on how
AI-looking the approved clip is. For now, `moderate` for all.

---

## LAYER INTERACTION — how they combine

The two layers address different tell categories:

| Tell | Layer 1 (keyframe) | Layer 2 (ffmpeg) |
|---|---|---|
| Flat/uniform lighting | ✓ mixed color-temp | |
| Over-saturated color | ✓ muted palette | ✓ desaturation (catches Seedance re-saturation) |
| Shallow DoF / bokeh | ✓ deep DoF instruction | |
| Perfect composition | ✓ casual off-center | |
| Razor sharpness | ✓ less sharp base | ✓ slight softness (catches Seedance re-sharpening) |
| No sensor noise | | ✓ film grain |
| No lens vignette | | ✓ vignette |
| Smooth motion / no jitter | | ✓ handheld micro-jitter |
| Consistent exposure | | ✓ AE flicker (optional) |
| "Polished" real-photo redo | ✓ preserve not polish | |

The overlap on color and sharpness is intentional — Seedance may partially undo the keyframe's
muted/soft look during animation (it optimizes for beauty). Layer 2 catches the drift. **Tune
Layer 2 intensity AFTER seeing how well Layer 1 alone works** — if the keyframe changes land
well, `light` may be enough for Layer 2.

---

## Config

```python
# Layer 1 — keyframe aesthetics
KEYFRAME_STYLE_SUFFIX = "..."    # the new suffix (build from §1a above)
KEYFRAME_NEGATIVE = "..."        # the negative prompt (§1b; empty string if not supported)

# Layer 2 — temporal post-processing
DEAI_ENABLED = True              # master toggle
DEAI_DEFAULT_INTENSITY = "moderate"
DEAI_CRF = 20
```

---

## Build order
1. **Layer 1 first** (keyframe prompt changes) — zero cost, highest expected impact, especially
   the `generate_from_real` "polished" → "preserve" fix (§1c). Run a few test keyframes and
   compare to current output before building Layer 2.
2. **Layer 2 second** (ffmpeg post-processing) — add and tune intensity after seeing how much
   Layer 1 alone improves the final video.
3. **Tune together** — once both layers are in, run the full pipeline and compare seedance_shots
   next to real_clips in the assembled video. The goal is that they blend. Dial Layer 2 intensity
   down if Layer 1 already closed most of the gap.

---

## Acceptance checks
1. **Layer 1:** a test keyframe (generate_from_real) preserves the original photo's lighting and
   color character instead of brightening/saturating it. Side-by-side: the keyframe looks like a
   reframed version of the real photo, not an "improved" version.
2. **Layer 1:** a test keyframe (generate mode) has mixed-temperature lighting, deep DoF, muted
   color — not the flat "AI afternoon" uniform light.
3. **Layer 2:** `deai_clip()` produces a valid mp4 for each intensity preset. Side-by-side: grain
   visible, color muted, edges slightly soft, vignette present.
4. **Layer 2:** the de-AI'd clip does NOT look bad/broken — it looks like decent phone footage,
   not corrupted video.
5. **Combined:** in a full assembled run, the seedance_shot segments blend visually with the
   real_clip segments. They should not "pop" as a different class of footage. This is THE real
   test.
6. **The `generate_from_real` prompt no longer says "polished."** Verify by grep.
7. Raw approved clips preserved alongside `_deai` versions for A/B comparison.
8. `DEAI_ENABLED = False` skips Layer 2 and the Editor gets raw clips (fallback).

## What this does NOT fix
- Object drift / identity shift on long clips (generation issue, not aesthetic)
- Hands, eyes, teeth, reflections (structural failures — shot judge catches these)
- Motion physics (Seedance's float-y camera moves — jitter helps mask, can't fix)
- The overall "AI ad structure" (that's the scaffold work in other specs)

## Guardrails
- Apply ONLY to `seedance_shot` clips. Never to real_clip, card, or moodboard.
- Layer 1: don't make the keyframe prompt SO degraded that Seedance produces ugly output. The
  goal is "phone in good light" not "phone from 2015." Test the balance.
- Layer 2: CRF ≤ 23. Grain needs bitrate.
- Layer 2: grain MUST be temporal. Static grain = obvious fake.
- Never overwrite raw approved clips.
- Tune Layer 2 AFTER Layer 1 is in. They interact; you may need less post-processing than
  expected.
