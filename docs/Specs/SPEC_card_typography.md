# Spec — CTA Card Typography System (addendum to SPEC_remotion_design_system.md)

> The current cards use one font, one size, one color. This makes them look like placeholders
> and kills the "designed" feel. This spec adds a real typography hierarchy to cards — multiple
> fonts, weights, sizes, and colors to visually separate business name / tagline / practical info
> / CTA action. Apply to ALL card styles (glass, type_only, photo_backed, minimal_bar).

---

## Typography hierarchy (4 levels)

Every card has up to 4 information tiers. Each gets distinct typographic treatment:

### Tier 1 — Business name (the anchor)
- Font: **Inter Black** (or the business's brand font if provided in brief.json — future)
- Size: 52–64px depending on card style and name length
- Color: **white** (on dark cards) or **palette[0]** (on light cards)
- Tracking: +2% letter-spacing (opens up, reads as a logo)
- Transform: uppercase
- This is the biggest, boldest element. It anchors the card.

### Tier 2 — Tagline / hook callback / the "one thing" (emotional)
- Font: **Caveat** (handwritten — contrasts the geometric name above)
- Size: 36–44px
- Color: **palette[0]** accent (or white if palette[0] is too dark on the background)
- Style: italic feel is inherent in the handwriting font
- This is the personality layer — a real review quote, the hook callback, or a short vibe line.
  NOT a generic tagline ("where quality meets care"). Something specific.

### Tier 3 — Practical info: location, hours, price (functional)
- Font: **Inter Medium**
- Size: 28–32px
- Color: **rgba(255,255,255,0.7)** (dimmer than the name — clearly secondary)
- Layout: single line or two lines, separated by a subtle divider dot (·) or line break
- Example: `123 Main St · Tue–Sat 9–7 · Cuts from $45`
- This is the "useful but not shouting" layer.

### Tier 4 — CTA action (the ask)
- Font: **Inter Bold**
- Size: 32–36px
- Color: **palette[0] background pill with white text** (inverted — the only element with a
  filled background, so it pops as a button-like action)
- Shape: pill/rounded-rect container, 8px vertical padding, 20px horizontal, border-radius 24px
- Example: `Book now` / `Walk-ins welcome` / `Order online`
- Alternatively for softer endings: just the @handle in Inter Medium at Tier 3 styling (no pill).
  The pill CTA is for `local_ad` voice_style; softer for `social_native`/`influencer_pov`.

---

## Per card-style application

### `glass`
- Dark blurred overlay background. All 4 tiers centered, stacked vertically with spacing:
  Tier 1 (24px gap) → Tier 2 (16px) → Tier 3 (20px) → Tier 4
- Tier 2 (Caveat) contrasts beautifully against the geometric Tier 1 on glass.

### `type_only`
- No background. Tiers left-aligned in lower-left quadrant.
- Tier 1: large, bold, high on the stack. Tier 2: handwritten underneath.
  Tier 3: small, dim, at the bottom. Tier 4: pill floats bottom-right.
- Drop shadow on all text (3px, 50% black) for readability.

### `photo_backed`
- Dimmed real photo behind. Tiers centered (like glass but warmer feel).
- Tier 2 (Caveat) in palette[0] really pops against the dimmed photo.

### `minimal_bar`
- The colored bar sits between Tier 1 (above) and Tier 3 (below).
  Tier 2 sits directly under Tier 1, above the bar. Tier 4 below Tier 3.
- Everything centered. Tight spacing — this style is restrained.

---

## Animation per tier (staggered entrance)

Don't animate everything at once — stagger reveals to create reading order:

1. **Frame 0–8:** Tier 1 (name) fades/slides in
2. **Frame 6–14:** Tier 2 (tagline) fades in (Caveat handwritten feel — slight rotate ±1° on enter)
3. **Frame 12–18:** Tier 3 (practical info) fades in at lower opacity
4. **Frame 16–22:** Tier 4 (CTA pill) scales in (0.8→1.0, spring) — last to appear, draws the eye

Overlap is intentional — creates a cascade, not a slideshow. Total entrance: ~22 frames (~0.9s at 24fps).

---

## Color logic

- Palette[0] used for: Tier 2 text, Tier 4 pill background, minimal_bar line
- White used for: Tier 1 text (dark backgrounds), Tier 4 pill text
- Dimmed white (70% opacity) used for: Tier 3
- Auto dark/light: if card background is light (photo_backed with bright photo, or type_only
  over bright footage), flip Tier 1 to palette[0] or near-black, Tier 3 to rgba(0,0,0,0.6)

---

## The Editor Agent's card_text schema (updated)

Currently `card_text` is probably a flat string. Replace with structured tiers:

```json
{
  "card_style": "glass",
  "card_tiers": {
    "name": "Conway Nail Bar",
    "tagline": "Where the 101 crowd gets their nails done",
    "info": "456 Harbor Blvd · Tue–Sat 10–7",
    "cta": "Book now",
    "cta_style": "pill"
  }
}
```

`cta_style` ∈ {pill, handle, subtle}:
- `pill` — the filled rounded-rect CTA (default for local_ad)
- `handle` — just @handle in Tier 3 styling (for social_native/influencer_pov)
- `subtle` — Tier 4 text only, no container (for linger/callback endings)

If `tagline` is empty, skip Tier 2 and tighten spacing. Not every card needs all 4 tiers.

---

## Implementation notes

- The `<Card>` component (or each card-style sub-component) receives `card_tiers` + `palette` +
  `card_style` as props and renders the hierarchy accordingly.
- Font loading: Inter is already present; Caveat was added in the caption spec. No new fonts.
- The stagger animation uses Remotion `interpolate()` with per-tier frame offsets — no springs
  needed except Tier 4's scale pop.
- Backward compat: if `card_text` is a flat string (old format), render it as Tier 1 only
  (name-style, centered). Graceful degradation.

---

## Acceptance checks
1. Each of the 4 card styles renders all 4 tiers with correct font/size/color per the spec.
2. Stagger animation is visible — tiers appear in sequence, not all at once.
3. Tier 2 (Caveat handwritten) visually contrasts with Tier 1 (Inter Black geometric).
4. Tier 4 pill CTA pops as the action element — it's the last to appear and visually distinct.
5. Auto dark/light detection flips text colors correctly on a bright vs. dark background.
6. `card_tiers` with missing `tagline` renders cleanly (3 tiers, tighter spacing).
7. Backward compat: a flat `card_text` string still renders (Tier 1 only).
8. Spot-check: does the card look *designed*, not like a text placeholder? Would you screenshot
   it and not be embarrassed?
