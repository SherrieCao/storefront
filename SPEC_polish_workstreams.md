# Spec — Polish Workstreams (pacing + script craft + editor reviewer)

> Three workstreams targeting observed quality gaps in real runs: editing too simple, scripts feel
> like "local ads not social-native," videos not fast-paced enough. Build A → B → C in that order;
> A and B are cheap scaffold work that likely closes most of the gap. C is bigger and worth doing
> after seeing how much A+B alone shifts perceived quality.
>
> Build against the CURRENT architecture (with critic loops, plan_timeline, voice-fit-to-length,
> Remotion bright line). Do NOT introduce new pipeline stages in A or B.

---

## WORKSTREAM A — Pacing tightening (cheapest, ship first)

**Goal:** the final video reads as fast-paced and social-native, not deliberate / radio-spot pacing.
Today the rendering supports it (1.25× ramp, ~2s beats) but upstream planning isn't pushing hard
enough.

### A1. Tighten script word cap in the Director scaffold
- Word ceiling drops to ~30 words for 15s, ~50 for 30s (linear-ish in between).
- Update `scaffolds/creative_director.md` script section: state new ceilings explicitly with a
  rationale line ("white space is part of pacing; tight scripts allow tight cuts").
- Director's script_reasoning must note word count and why it earns it (no padding).

### A2. Stricter pacing defaults
- The Director's `pacing` field defaults to `brisk` for most formats, `frenetic` for
  offer/urgency/announcement concepts. `measured` is allowed only with explicit justification
  (genuine BTS, testimonial, slow-reveal demo).
- Scaffold names the failure mode: "mid-tempo cutting is the default trap; choose deliberately."

### A3. Verify the speed-ramp doesn't over-stretch
- With shorter scripts the voice will be shorter; atempo capped at 1.55 should rarely be hit, but
  check: if scripts get too short, the ramp can flatten energy. Add a sanity check in
  `editor.render`: if voice <  60% of planned length, log a warning (probably script too short for
  the chosen total_duration_s — Director should regenerate with a tighter total_duration_s).

### A4. Playbook reflects the change
- Update `scaffolds/references/smb_verticals.md` (or the relevant playbook ref) so fast pacing /
  short script / brisk cutting is the social-native default. Mid-pacing is the exception.

### A5. Length stays 15–30s (NOT lowered to 8s)
- Confirm Director scaffold range remains 15–30s; do not lower the floor.

### Acceptance
- A test run produces a 15s ad with ≤30 spoken words, `pacing` = brisk or frenetic, final video
  feels fast on playback. (Operator subjective; no automated check.)
- Atempo logs no over-stretch warnings on a normal-script run; warning fires correctly on a
  deliberately too-short script test.

---

## WORKSTREAM B — Script craft (voice styles + playbook injection)

**Goal:** scripts stop reading as local-ad-radio voice. Director picks a voice style appropriate to
the business and concept; a craft reference document teaches what good social-native ad writing
sounds like.

### B1. Director picks `voice_style` ∈ { local_ad | social_native | influencer_pov }
- New required field in Director output (backward-compatible: existing readers ignore unknown).
- Selection criteria the scaffold teaches:
  - **local_ad** — clear, warm, info-forward. Hits price/hours/location naturally. For trust-led
    businesses where customers need explicit reassurance (salon, daycare, cleaning when targeting
    cautious buyers).
  - **social_native** — concise, specific, slightly playful. Hook-driven, less explicit selling,
    info woven in. For product businesses and most service businesses on IG/TikTok.
  - **influencer_pov** — first-person, conversational, often POV-framed ("POV: you finally found
    a salon that…"). Strong angle, voice-led. For aspirational/lifestyle-fit businesses.
- Director justifies the choice in a new `voice_style_reasoning` field.

### B2. `scaffolds/references/script_craft.md` — framework doc + placeholder examples
- I'll provide a starter doc with:
  - **What to look for in a great social-style SMB ad** (hook types, voice quirks, pacing tells,
    what they omit, how info is woven not announced).
  - **Pattern categories** with brief named examples (Hook patterns: specific-detail, local-
    recognition, result-first, relatable-problem, sensory; Voice quirks: insider terms, specific
    proper nouns, restraint, white space).
  - **2-3 illustrative made-up example transcripts** marked clearly as placeholders, showing the
    framework applied. NOT presented as real ads — labeled "[ILLUSTRATIVE FRAMEWORK EXAMPLE]."
  - **A clear "ADD REAL EXAMPLES HERE" section** with operator instructions: as you scroll IG/
    TikTok / browse Meta Ad Library, save ads that make you stop, paste transcript + 1-line "what
    works here," replace placeholders as the library grows.
- `refs.py` injects this into Concept and Director.

### B3. Named anti-patterns in the Director scaffold
- Add an explicit "avoid these script tells" section:
  - Local-ad-radio voice ("Come on down to…", "For all your X needs…", "Family-owned since…")
  - Hype-deck filler ("Experience the difference," "Where quality meets care")
  - Mid-tempo info-listing ("We offer X, Y, and Z, conveniently located at…")
  - Generic CTA ("Call today!")
- This complements (doesn't replace) the existing banned-words list.

### B4. NO new reviewer in this workstream
- The existing creative reviewer pattern (`reviewers.py`, 4-lens) already critiques the script
  inside the director⟳ loop. Don't add a script-specific reviewer here. Fix the *input data*
  (playbook + style picker) first; if scripts still feel generic after a few runs, then consider a
  script reviewer with lenses specifically about voice and surprise (not safety).

### Acceptance
- Director output includes `voice_style` (one of the three) + `voice_style_reasoning`.
- `script_craft.md` exists with framework + placeholders + the "ADD REAL EXAMPLES" section; refs.py
  injects it; a real run shows the reference in the Concept and Director prompts (visible in
  trace.jsonl).
- A real run produces a script that picks a non-`local_ad` style for at least one test business
  where it fits (e.g. a nail studio or boutique bakery should land `social_native`, not `local_ad`).

---

## WORKSTREAM C — Editor reviewer + selective Phase 2 capabilities

**Goal:** the assembled video reads as polished, not "AI-edited" — at the level Remotion can
realistically reach without a full Phase 2 build.

### C1. `editor.plan_timeline⟳` — critic loop on the timeline plan
- Mirror the existing concept⟳/director⟳/hook⟳ pattern. Reuse `reviewers.py` infrastructure.
- The Editor Agent produces a timeline plan → reviewer critiques against editor-specific lenses
  → Editor regenerates with feedback → up to N attempts → accept-best+flag (same as other loops).
- Editor-specific reviewer lenses (in addition to / replacing the 4-lens default where useful):
  - **First-0.5s grab** — does the opening frame have motion / face / problem text? No dead static
    start.
  - **Rhythm** — are cuts consistently brisk; any dead air > 2.5s; do beats vary or is everything
    metronomic?
  - **Contrast** — visual contrast between adjacent segments (lighting / framing / subject change)
    so cuts feel intentional.
  - **Payoff** — does the final 2s deliver something (CTA, callback, visual punch), not just
    trail off?
- The reviewer must reward bold rhythm choices, not punish them. Same anti-safety principle as
  the existing creative reviewers.

### C2. Selective Phase 2 capabilities the reviewer can ask for
The reviewer is only as good as the toolkit. Add two Phase 2 capabilities NOW so the reviewer has
real tools to demand:

- **Kinetic captions (per-word reveal)** — use the existing voice word-level timestamps; build a
  Remotion `<KineticCaption>` component that reveals word-by-word (or phrase-by-phrase) timed to
  the voice. Two style presets to start: `clean_pop` (each word fades+scales in), `emphasis`
  (most words plain, key words enlarged/colored). Replaces or augments the current burned-in
  captions.
- **Animated card components** — upgrade existing Card templates from static to animated:
  slide-in from edge, scale-pop entrance, exit fade. Each card template gains an `animation` prop.

DEFER for a future Phase 2 spec: beat-sync to music bed, motion graphics templates beyond cards,
multi-style kinetic typography systems. Don't build these now; the reviewer can flag "this needs
beat-sync" as a known limitation.

### C3. Editor scaffold updates
- Editor scaffold teaches the new capabilities (kinetic caption presets, animated card props) so
  the Editor Agent uses them. Keep the bright line: Seedance for new footage, Remotion for
  everything else (animated captions and cards are Remotion).
- Editor scaffold also teaches what the reviewer will look for, so it generates with the lenses
  already in mind.

### C4. Phase 2 deferred list (document, don't build)
- Beat-sync (needs music bed system + librosa or equivalent — real subsystem).
- Motion graphics beyond cards (logos, lower-thirds, animated arrows, sticker call-outs).
- Multi-style kinetic typography (more than the two presets above).
- Music bed selection + audio ducking under VO.
Note these as "Phase 2 spec, when needed" in `docs/ARCHITECTURE.md`.

### Acceptance
- `editor.plan_timeline⟳` runs as a critic loop on every render; trace shows attempts + reviewer
  verdicts.
- Final videos use kinetic captions (not burned-in static text) and at least one animated card on
  most runs.
- Operator subjective check: editing reads as more polished than pre-workstream output on at least
  3 consecutive real runs.

---

## CROSS-WORKSTREAM NOTES

### Order
A → B → C. Build and ship A first (smallest), then B (medium), then C (largest). After A+B, run
5-10 real test runs and assess whether C's scope still feels right; the kinetic captions and
animated cards may be enough, or you may want to expand the deferred Phase 2 list. Don't pre-commit.

### DECISIONS.md additions
Three new entries (or compact versions thereof):

- **D22. Pacing defaults to brisk / frenetic; mid-pacing is the exception.** Word cap tightened to
  ~30 words for 15s ads, ~50 for 30s. White space is part of pacing.
- **D23. Director picks voice_style (local_ad / social_native / influencer_pov).** Different
  businesses want different voices; one default fits none well. Selection criteria in scaffold;
  the script_craft.md playbook teaches what each sounds like.
- **D24. Editor critic loop + selective Phase 2 capabilities (kinetic captions, animated cards).**
  The critic-loop pattern extends to the editor; the toolkit expands just enough that the
  reviewer has tools to ask for. Beat-sync and broader motion graphics are deferred Phase 2.

### What this does NOT change
- The Seedance/Remotion bright line (D21) — kinetic captions and animated cards are Remotion.
- The 15–30s length range (D19) — not lowering the floor.
- The voice-fit-to-length spine flip (timing model) — script tightening doesn't change the
  rendering model.
- The $5 cost ceiling (D6) as a safety net.
- Creative reviewer infrastructure (`reviewers.py`) — the editor reviewer uses it; no new framework.
- No new pipeline stages — all changes are within existing stages or scaffold/reference work.

### Guardrails
- Reviewers reward boldness and specificity, not safety. If a reviewer ever rejects an idea for
  being "risky" without also explaining how to make it stronger, the lens is wrong.
- The script_craft.md placeholders MUST be labeled as illustrative, not real ads. Replace as
  operator curates real examples.
- Don't add a script-specific reviewer in B. Fix input data first.
- C's kinetic captions / animated cards are the ONLY Phase 2 work in scope; resist scope creep
  into beat-sync or motion graphics.
