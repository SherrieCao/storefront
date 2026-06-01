# Follow-Up Spec — Mixed Segments + Clean Seedance/Remotion Boundary

> This is a FOLLOW-UP to `SPEC_multigen_rearchitecture.md`. The main spec is already being built;
> this one amends two things in the in-flight work. Apply these changes on top.

## What changes (two things, both small but architecturally clean)

### Change A — Mixed segment composition (variable length, mixed types)
The ad is composed of HETEROGENEOUS SEGMENTS, not a fixed list of N Seedance shots. The Director
picks total length (15–30s) and mixes segment types based on the concept.

### Change B — One clean rule for what generates what
**Seedance generates ONLY what genuinely needs video generation. Everything else is Remotion.**
- Seedance: `seedance_shot` segments (new generated video footage).
- Remotion: moodboard rendering & motion, real-clip trimming, cards, transitions, captions, audio
  mux. Anything composition/animation/editing that isn't "generate new footage from a prompt."

This is the single bright line. No fuzzy middle. If you're tempted to use Seedance for non-shot
work (e.g. animating a moodboard, looping a real clip with a Ken Burns effect), use Remotion instead.

---

## Director schema changes (backward-compatible)
Replace `shots[]` with `segments[]`. Each segment:
```
{
  "n": 1,
  "type": "seedance_shot|real_clip|moodboard|card",
  "duration_s": 3.0,
  "intent": "...",
  "why": "...",
  // type-specific fields:
  "asset_ref": "@Image1|@Video1|generated",   // seedance_shot
  "action": "...", "camera": "...",            // seedance_shot
  "clip_ref": "@Video2", "trim_s": [2,5],     // real_clip
  "moodboard_assets": ["@Image1","@Image3"],  // moodboard
  "card_text": "...", "card_template": "..."   // card
}
```
Plus on the Director output:
- `total_duration_s` (between 15 and 30; Director justifies — short punchy offer = 15s, ambitious
  transformation = 30s).
- `composition_reasoning` — why this mix of segment types serves the concept.

The Director should NOT reason about cost. Plan creatively, pick the right mix for the idea. The
pipeline enforces the cost ceiling as a safety net (D6), but creative decisions are not gated by
budget math. (If Phase 1 runs show cost is consistently a problem, we'll revisit then — not now.)

---

## Segment types — what each is for
- **`seedance_shot`** — generated video shot. Goes through the Shot Agent (generate, judge, retry).
  Use for hero moments needing motion the assets can't supply.
- **`real_clip`** — provided business video, trimmed by Remotion in the Editor stage. No generation.
  Use for authentic footage of the actual service/space.
- **`moodboard`** — composed keyframe (Nano Banana 2 produces the cutout composition), animated by
  Remotion (parallax across composition, slow push, gentle drift). Use to consolidate scattered
  assets into a designed composition.
- **`card`** — static or lightly-animated card rendered by Remotion from a small template library
  (`editor_render/templates/`). End card, price tag, location pin, offer banner, simple title.
  Keep template count small (~5–8) and visually consistent.

---

## Stage-level changes (apply to in-flight build)

### Shot Agent (`pipeline/shots.py`)
- Runs ONLY on `seedance_shot` segments. Other segment types skip generation entirely.
- Iterate through `segments[]`, filter to type=seedance_shot, run the existing generate→judge→retry
  flow on those. Skip everything else. The flagged-shots logic only applies to seedance_shot.

### Keyframes stage (`pipeline/keyframes.py`)
- Produces keyframes for `seedance_shot` segments (start frames, as already specced).
- ALSO produces moodboard composition keyframes for `moodboard` segments — Nano Banana 2 generates
  the cutout-arranged frame. These are NOT fed to Seedance; they're handed to Remotion to animate.
- Real clips and cards do not need keyframes.

### Editor (`pipeline/editor.py` + `editor_render/`)
The Editor Agent now plans a timeline with mixed segment types. The Remotion render service
handles each type:
- `seedance_shot` → insert the approved generated mp4 from `shots/`.
- `real_clip` → trim the provided video per `trim_s` (Remotion `<Video>` with `startFrom`/`endAt`).
- `moodboard` → animate the moodboard keyframe (parallax, slow push, drift) using Remotion
  components. Build a single reusable `<MoodboardSegment>` component that takes the keyframe and
  motion params.
- `card` → render from `editor_render/templates/`. Build the small template library:
  `EndCard`, `PriceTag`, `LocationPin`, `OfferBanner`, `Title` (5 to start; can grow). Each is a
  Remotion component taking text + style props.

Phase 1 transitions (hard cut + crossfade) apply across ALL segment-type pairs uniformly.

### Length bounds
- Min 15s, max 30s. Beyond 30s is Phase 2.
- Director picks within bounds and justifies; pipeline validates the chosen length.

---

## What this does NOT change
- $5 cost ceiling stays AS A SAFETY NET in `pipeline/budget.py`. The Director just doesn't reason
  about it. If a run actually exceeds $5, the ceiling still halts.
- Concept → Director → Shot Agent → Editor flow unchanged. Director still owns composition (no new
  agent for segment planning — D20).
- Shot Agent retry-and-flag logic unchanged for `seedance_shot` segments.
- Per-shot keyframe consistency requirement unchanged (Nano Banana 2 holds the look across shots).
- Phase 1 editor scope (cuts + captions + audio mux + simple transitions). Editor just handles
  more input types now.

---

## Director scaffold edits (`scaffolds/creative_director.md`)
Update to teach the new output:
- Output `segments[]` (not `shots[]`), with the schema above.
- Output `total_duration_s` (15–30) with reasoning.
- Output `composition_reasoning` — why this mix serves the concept.
- Teach what each segment type is for (the bullets above).
- Teach the bright line: Seedance for new footage; Remotion for everything else.
- DO NOT include cost guidance, budget rules, or per-segment cost numbers. Plan creatively.

---

## Acceptance check additions (on top of main spec)
1. Director output is `segments[]` with mixed types. A run with e.g. 3 seedance + 2 real_clip +
   1 moodboard + 1 card produces a 25–30s final ad.
2. Shot Agent skips non-seedance_shot segments cleanly (no errors, no wasted calls).
3. Keyframes stage produces both seedance start frames AND moodboard composition keyframes.
4. Remotion renders all four segment types in one timeline; transitions work between any pair.
5. The Remotion `templates/` directory contains at least the 5 named card templates as working
   components.
6. The $5 ceiling still aborts on overrun (safety net works), but the Director never sees cost
   numbers in its scaffold or input.

---

## DECISIONS.md additions (the new repo's DECISIONS.md)
Add two entries (already drafted as D19/D20 in our session — adapt to remove the cost-awareness
language since we just dropped that requirement):

**D19 (revised). Mixed-segment composition; Director picks length (15–30s).** The ad is composed of
heterogeneous segments: `seedance_shot` (generated, via Shot Agent), `real_clip` (provided video,
trimmed by Remotion), `moodboard` (Nano Banana keyframe animated by Remotion), `card` (Remotion
template). Director picks total length within 15–30s based on the concept, and mixes segment types
freely — no cost reasoning at planning time. The $5 ceiling remains as a safety net at the pipeline
level (D6), not as a creative constraint.

**D20. Director owns segment planning (no new agent).** Segment selection and ordering is one
creative composition decision; folding into the Director keeps responsibility intact. A separate
Composition Agent was considered and rejected as fragmenting a single creative decision.

**D21 (new). The Seedance/Remotion boundary is a single bright line.** Seedance generates new
video footage only (the `seedance_shot` segment type). Remotion handles EVERYTHING else —
moodboard composition + motion, real-clip trimming, card rendering, transitions, captions, audio
mux. If a task could plausibly be Seedance or Remotion, choose Remotion. This rule is the
architectural simplicity lever: no fuzzy middle, no per-task decision, just one clean split.

---

## Guardrails (apply to this follow-up)
- Backward-compatible schema changes preferred (segments[] replaces shots[] cleanly; downstream
  code reading shots[] needs the rename).
- The bright-line rule (Change B) is non-negotiable — don't introduce exceptions where "Seedance
  could do this too" creeps in.
- Director scaffold MUST NOT contain cost guidance.
- $5 ceiling enforcement stays exactly as specced — it just operates silently as a safety net now,
  not as a creative input.
