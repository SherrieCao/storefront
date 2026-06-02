# Ad Formats Reference — the formats (8 from Motion's "Eight visual formats to test in 2026", + moodboard)

> Director reference. Source: Motion Creative Benchmarks (~$14B/yr Meta spend). CAVEAT: this is
> DTC/Meta data — a strong prior, NOT gospel for local-SMB foot-traffic. Operator review verdicts
> calibrate it over time. These are TREATMENTS the Director draws on — per segment or across the ad
> (an ad may combine them, e.g. a demo opening into a BTS middle), not a single forced choice. Justify
> the treatments in `creative_angle` + `composition_reasoning`.

| Format | When this treatment works | Audience fit | Messaging rule | Trade-off / caution |
|---|---|---|---|---|
| **testimonial** | A real person + genuine reaction exists; trust is the barrier | Skeptical / high-consideration | Let the customer tell it; lead with the *before* state (problem → tried → result) | Needs a real source — never fabricate a customer |
| **demo** | The action is visually satisfying/surprising, or rivals claim-but-don't-show | Curious / proof-driven | Show, don't tell; don't over-explain what's visible | Dull if the action isn't actually interesting |
| **listicle** | Multifunctional offering; educating; testing angles | Browsing / discovery | 3–5 standalone points, front-load the strongest | Can feel generic; better for discovery than hard conversion |
| **montage** | Brand IS the product / show versatility; you HAVE strong varied assets | Aspirational / lifestyle | Minimal/atmospheric; visuals carry it | **"Wallpaper" failure mode**: no tension or CTA → generic, non-converting. Only with a specific angle. |
| **split_screen** | A genuine, visible difference (us-vs-them, before-vs-after, problem-vs-solution) | Comparison shoppers | Make the contrast instant and legible | before/after variant HARD-GATED on real before/after assets |
| **behind_the_scenes** | Process is a differentiator; humanize; owner-led | Trust-seeking; values-driven | Transparency; conversational not scripted; imperfections are strengths | Rising in 2026; strong SMB fit |
| **tutorial** | Outcome-focused how-to; product as the tool to a goal | High-intent, problem-aware | Lead with the outcome, then the path; teach first, sell second | Needs a real teachable outcome |
| **unboxing** | Premium / packaging-led product; help viewer picture it in their life | Considered purchases | Build anticipation toward the reveal | Requires real product packaging appeal — weak for pure services |
| **moodboard** | Varied/scattered asset pile, no single strong hero clip; a designed composition beats a sequence | Aspirational / lifestyle | ONE composed scene (cutouts on a styled surface, single camera move) — not cuts; plan a `composition`, not `shots` | Composed by the keyframe stage (Nano Banana) SEEDED FROM the real photos (generate-from-real); still a generated composition — prefer a `real_clip` when exact subject likeness is critical. |

## Cross-format principle
**Authenticity beats polish.** Across every format above, lower-fi authentic execution out-performs
glossy production. For a local business, a real phone-shot moment of the actual owner/space/product
usually beats a polished generated montage. "Cinematic commercial" gloss reads as AI and as an ad.

## Availability (per run)
- Always available: demo, listicle, montage, moodboard, behind_the_scenes, tutorial, split_screen
  (us-vs-them / problem-solution variants).
- testimonial: only if a real testimonial/person source is in the inputs.
- unboxing: only if there's a real product with packaging (not a pure service).
- split_screen before/after variant + any explicit before/after framing: only if the operator
  stated before/after in the brief OR labeled files `before_*`/`after_*` (the `has_before_after`
  gate; D11 amended — filename prefixes count as an explicit operator label).
