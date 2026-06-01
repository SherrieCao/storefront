# Spec — Remotion Design System (editing techniques, captions, motion, cards)

> Companion to SPEC_anti_ai_tells.md. That spec changes what the agents THINK about; this one
> changes what the renderer can actually DO. Remotion components, visual design, animation curves,
> fonts, parameterization. The anti-template goal applies here too: the component library must
> support enough VARIATION that output doesn't pattern-match as "one template."
>
> This is a DESIGN + IMPLEMENTATION spec for `editor_render/`. It defines new components, updates
> existing ones, and establishes a visual design system. Claude Code should read the current
> `editor_render/` source first.

---

## 1. Caption Design System

The current KineticCaption is ONE look (64/76px, white/grey, palette accent, one font). Social
content uses wildly different caption aesthetics. Build a system of **4 distinct styles** the
Editor Agent can pick from — each with its own font, size, position, animation, and color logic.

### Style definitions

#### `bold_center` (the current default, refined)
- Font: **Inter Black** (or Montserrat Black — heavy, geometric sans)
- Size: 72px base, emphasis words 88px
- Position: centered vertically in lower 40% of frame
- Color: spoken word = white; unspoken = rgba(255,255,255,0.35); emphasis = palette[0]
- Animation: word fades in (opacity 0→1, scale 0.85→1.0, spring tension ~180) timed to word start
- Line grouping: 3–4 words per line; line changes on natural phrase breaks
- Drop shadow: 2px black at 60% opacity (readability over busy footage)
- Use when: high-energy, punchy, hype — the "CapCut bold" look but de-templated via palette color

#### `minimal_lower` (native/subtle)
- Font: **Inter Medium** (clean, lighter weight)
- Size: 48px uniform (no emphasis sizing)
- Position: bottom-left corner, 8% margin from edges
- Color: white with 85% opacity; no accent color; spoken word = full white, rest = 50% opacity
- Animation: entire phrase fades in as a block (not per-word), holds, fades out. No scale/bounce.
- Line grouping: full phrase (5–8 words), one line at a time
- No drop shadow; use a subtle dark gradient band (0→30% black) across the bottom 15% of frame
- Use when: social_native, understated, the visual is strong enough to carry

#### `handwritten` (creator/personal)
- Font: **Caveat** or **Patrick Hand** (a real handwriting font — NOT Comic Sans, NOT perfectly
  uniform script)
- Size: 56px base
- Position: centered, lower 35%
- Color: off-white (#F5F0E8) on dark footage; dark (#2A2A2A) on light footage (auto-detect from
  frame luminance or accept a `caption_bg` hint from the Editor)
- Animation: words appear with a slight random rotation (±2°) and position jitter (±3px), as if
  hand-placed. Spoken word gets a subtle highlight underline (not color change).
- Line grouping: 2–3 words per line (feels scrawled)
- Use when: influencer_pov, personal, lo-fi, diary-feel

#### `sparse_keyword` (the new `sparse` style from the scaffold spec)
- Font: **Inter Black**
- Size: 96px (BIG — one word dominates)
- Position: centered in frame (vertically + horizontally)
- Color: white; optional palette[0] accent on the single most important word per phrase
- Animation: word SLAMS in (scale 1.4→1.0, opacity 0→1, duration 4 frames — fast and hard).
  Holds. Cuts to black (2 frames). Next keyword slams in.
- Content: NOT every spoken word — only 1–2 KEYWORDS per phrase (the Editor Agent picks them,
  or a simple heuristic: longest content word per caption chunk). The rest is heard, not read.
- Use when: hype, offer, price-anchor, impact — when you want ONE word to hit hard

### Implementation notes
- Build as a single `<CaptionSystem>` component that takes `style` prop and delegates to
  the appropriate sub-component. Keep the existing `KineticCaption` as the `bold_center` variant
  (refactor, don't rewrite from scratch).
- All styles receive the same `words[]` array (word + start_s + end_s). The `sparse_keyword`
  style filters internally (or receives a `keywords` array from the Editor plan).
- Font loading: include Inter (already likely present), Caveat, Patrick Hand via Google Fonts
  CDN in the Remotion bundle. Keep the font count small.
- The Editor Agent's `caption_style` field selects from: `bold_center | minimal_lower |
  handwritten | sparse_keyword`. The existing `clean_pop | emphasis | karaoke` map to
  `bold_center` variants (preserve backward compat by aliasing if needed).

---

## 2. Transition Library (expanded)

Current set: hard_cut, crossfade, dip_to_black, slide, whip, zoom. Functional but reads as
"preset pack" when multiple flashy ones are used. Expand with 3 more, and refine existing.

### New transitions

#### `speed_ramp_in`
- The incoming clip starts at 2× speed for the first ~6 frames, then eases to 1× (cubic-out).
  Creates a "snap into the moment" feel. Works as a cut replacement — the speed change IS the
  transition.
- Remotion: `playbackRate` interpolation on the incoming `<Video>` using `interpolate()`.
- Use: high-energy beats, especially entering a hero shot.

#### `scale_reveal`
- The outgoing clip scales up (1.0→1.3) while fading, revealing the incoming clip underneath
  (already at full size). A more organic "zoom through" than the current `zoom`.
- Remotion: `scale` + `opacity` interpolation on the outgoing `<Sequence>`.
- Use: transitioning from detail to wide, or into a card/moodboard.

#### `light_leak`
- A warm, semi-transparent gradient wipe (amber→transparent) sweeps across during the transition,
  simulating a lens flare / light leak. Subtle (20–30% opacity). Adds organic texture.
- Remotion: an `<AbsoluteFill>` with an animated linear-gradient overlay, timed to the cut point.
- Use: once per ad max. Between two warm/golden-lit segments. Never on a card transition.

### Refinements to existing

- `whip`: add motion blur (Remotion CSS `filter: blur(8px)` for 3 frames during the swipe).
  Currently it's a clean slide; real whip-pans blur.
- `crossfade`: shorten default duration from ~0.5s to ~0.3s. Long crossfades feel "slideshow."
- `hard_cut`: no change (it's correct — and should remain the majority of transitions).

### `transition_in` enum update
`{hard_cut, crossfade, dip_to_black, slide, whip, zoom, speed_ramp_in, scale_reveal, light_leak}`

---

## 3. In-Clip Motion Library (expanded)

Current: punch_in, parallax. Add:

#### `handheld_jitter`
- Subtle random micro-movement simulating a handheld camera. Applied as a Remotion `transform`
  on the clip's container.
- Parameters: amplitude 1–3px (x/y translation), ±0.3° rotation, update every 2–3 frames
  (not every frame — that's tremor, not handheld).
- Implementation: use `useCurrentFrame()` + a seeded pseudo-random (deterministic per render)
  to compute per-frame offsets. Slight scale to 101% to hide edge gaps from translation.
- Use: on any static or too-smooth clip. The default "add life" tool.

#### `scale_breath`
- Very slow, continuous scale oscillation: 1.0 → 1.03 → 1.0, over ~3s (one cycle per clip).
  Gives a subtle "breathing" pulse to static footage.
- Remotion: `scale` via `interpolate(frame, [0, dur/2, dur], [1, 1.03, 1])`.
- Use: on moodboards and held product shots. More subtle than punch_in.

#### `drift`
- Slow, continuous horizontal or vertical pan across a photo/moodboard (like a Ken Burns but
  smaller — ~5% of frame width over the clip duration).
- Remotion: `translateX` or `translateY` interpolation. Direction: random or specified per clip.
- Use: on moodboard segments and static photo-based clips.

### `motion` enum update
`{punch_in, parallax, handheld_jitter, scale_breath, drift}`

---

## 4. Card Template Visual Refresh

Current card templates (EndCard, PriceTag, LocationPin, OfferBanner, Title) likely use a
uniform style. Refresh for variation and de-templating.

### Design principles for cards
- Cards should feel like they BELONG to the ad's visual world, not like a branded end-slate
  pasted on. Use the business's palette, match the footage's warmth/coolness.
- No heavy branding chrome (thick borders, drop shadows, gradient backgrounds). Minimal.
- Text hierarchy: 1 hero line (large), 1–2 supporting lines (smaller), nothing else.

### Revised card styles (the Editor picks per card)

#### `glass` (modern, subtle)
- Semi-transparent dark overlay (rgba(0,0,0,0.55)) with backdrop-blur (12px).
- White text, Inter Medium, hero line 56px, supporting 36px.
- Rounded corners (16px). Centered in frame with 10% margin.
- Animation: fades in over 8 frames, text staggers in line-by-line (4-frame delay between lines).
- Feel: iOS notification / modern app. Clean without being "branded."

#### `type_only` (bold, no container)
- No background container at all. Just large white text directly on the footage (or on a
  solid-color last frame extracted from the palette).
- Inter Black, hero 80px, supporting 44px. Left-aligned, lower-left quadrant.
- Dark text shadow (2px, 50% opacity) for readability.
- Animation: hero line slides in from left (12 frames, ease-out); supporting fades in after.
- Feel: creator end-card. Raw, confident.

#### `photo_backed` (keep/refine existing if present)
- The card sits over a dimmed version of the last real photo (brightness 40%).
- White text centered. Similar to `glass` but the "background" is the real photo, not blur.
- Animation: photo dims in (brightness 100→40%, 10 frames), text fades in on top.
- Feel: warm, grounded in the real business.

#### `minimal_bar`
- A thin horizontal bar (palette[0] color, 4px) appears at center-screen. Text stacks above
  and below it (business name above, details below). Small, centered.
- Animation: bar draws in from center outward (like a reveal), text fades in after.
- Feel: boutique, restrained. Good for salon/florist/cafe.

### Card `animation` enum update (entrance animations)
Keep existing `scale_pop, slide_in, fade` but each card STYLE has its own default animation
(documented above). The Editor can override. Add:
- `stagger` — lines appear one by one with a short delay (works with glass, type_only).

### Card `card_style` field (NEW, optional)
Add to the Editor plan schema: `card_style` ∈ {glass, type_only, photo_backed, minimal_bar}.
Default: `glass`. The Editor picks based on the ad's mood and the footage.

---

## 5. Overlay Refresh (lower_third, badge)

### `lower_third`
- Current: unknown styling. Refresh:
- A slim, pill-shaped container (palette[0] background, white text, Inter Medium 28px).
  Positioned bottom-left with 6% margin. Max width 60% of frame.
- Animation: slides in from left edge (10 frames, ease-out), holds, slides back out.
- Optional: semi-transparent variant (rgba palette[0] at 70%) for subtlety.

### `badge`
- Current: unknown styling. Refresh:
- A small rounded-rect chip (white background, dark text, or palette[0] bg with white text).
  Inter Bold 24px. Positioned per the `position` field (tl/tr/bl/br) with 5% margin.
- Animation: pops in (scale 0.5→1.0, spring, 6 frames). Holds 2–3s. Fades out.
- Keep text ≤ 4 words. One per ad max for "badge"; lower_third can appear once additionally.

---

## 6. Color System

### Palette-driven theming
Every visual element (captions, cards, overlays, transitions) should pull from the business's
`palette[]` (extracted in triage, passed through the plan). Define a mapping:

- `palette[0]` = primary accent (highlight color, badge bg, card accent)
- `palette[1]` = secondary (used sparingly — a second badge, alternate emphasis)
- White (#FFFFFF) and near-black (#1A1A1A) are always available as neutrals.
- Caption text: always white or near-white for readability (accent only for highlight/emphasis).
- Card backgrounds: glass = dark translucent; type_only = none; photo_backed = dimmed photo;
  minimal_bar = palette[0] bar only.

### Auto dark/light detection
For `handwritten` captions and `type_only` cards, detect whether the underlying footage is
light or dark (sample center-frame luminance) and flip text color accordingly. Simple threshold:
avg luminance > 140 → dark text; else → white text.

---

## 7. Anti-Template Variation Rules

To prevent the component library itself from becoming a template:

- **The Editor Agent must NOT use the same caption_style + card_style + transition combo on
  consecutive runs for the same business.** (Enforce in the Editor scaffold, not in code — tell
  the agent to vary.)
- **No more than 2 of the same transition type in one ad** (already in the scaffold; reinforce
  in the component layer by logging a warning if violated).
- **Card style should match the ad's mood**, not default to one. The Editor scaffold should
  map: high-energy/hype → `type_only`; warm/personal → `photo_backed` or `glass`;
  boutique/minimal → `minimal_bar`.

---

## Acceptance checks
1. All 4 caption styles render correctly with test word-timing data. Visual spot-check: do they
   look like 4 genuinely different aesthetics, not 4 skins on the same template?
2. All 3 new transitions (speed_ramp_in, scale_reveal, light_leak) render. Whip now has motion
   blur. Crossfade is shorter.
3. All 3 new motion types (handheld_jitter, scale_breath, drift) render on a test clip.
   handheld_jitter: visibly adds micro-movement without looking like tremor.
4. All 4 card styles render with test card_text. Visual spot-check: each feels distinct.
5. Palette-driven theming: components pick up palette[0] correctly from the render plan.
6. Auto dark/light detection works on a light frame and a dark frame.
7. End-to-end: a full render with mixed caption_style + card_style + transitions + motion
   produces a video that does NOT feel like "one template."

## Guardrails
- Keep font count to 3 (Inter, Caveat, Patrick Hand). Don't add more without removing one.
- Every component must accept palette as a prop — no hard-coded colors except white/black.
- Animations use Remotion's `spring()` or `interpolate()` — no external animation libraries.
- Backward compat: existing `clean_pop/emphasis/karaoke` caption styles must still work
  (alias to `bold_center` variants or keep as sub-modes).
- Performance: handheld_jitter's per-frame random must be seeded/deterministic so re-renders
  produce identical output.
