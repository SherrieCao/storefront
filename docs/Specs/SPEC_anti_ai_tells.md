# Spec — Anti-AI-Tell Scaffold Changes (research-informed)

> Consolidated scaffold changes across ALL stages to shift output from "reads as AI/ad" toward
> "reads as authentic content." Grounded in the 2026 diagnostic research (AI vs. authentic tells
> on Reels/TikTok for local SMBs). No new pipeline stages except the Ending Agent design notes.
> No Python changes — scaffolds + reference files only (verify backward-compat on schemas).
>
> Core principle: **template the intent, de-template the surface.** The internal pipeline structure
> (concept → director → shots → editor → card) stays rigid — it guarantees the message lands. The
> viewer-facing output (rhythm, captions, lighting, endings) varies enough to not pattern-match as
> a template. The structure is invisible; the packaging is visible.

## Before you start
- Read the full research report (the "AI vs. Authentic" diagnostic field guide) — it's the source
  for every change below. If a change seems arbitrary, the research explains why.
- Read ALL current scaffolds: concept.md, creative_director.md, prompt_translator.md, shot_agent.md,
  editor.md, creative_reviewer.md, editing_reviewer.md, and all references/*.md.
- These are scaffold-only changes. If any change implies a new output field, verify downstream
  consumers don't break (grep for field usage).

---

## 1. Concept Stage (concept.md)

### 1a. Human-anchor hard gate (NEW)
Add to the HARD GATES section:
> **Human-anchor rule:** the chosen concept must be ANCHORED on real first-party footage — at least
> one `real_clip` or real-photo-based segment as the ad's spine. A concept where every visual beat
> is AI-generated is INVALID. AI is for components (B-roll, motion, graphics, atmosphere); real
> footage of the actual business/product/people is the frame. "Use AI to elevate what's real, not
> replace it."
>
> Corollary: the concept must NEVER depend on AI depicting the actual product a customer will
> receive (the real food, the real nails, the real haircut, the real flower arrangement). AI
> standing in for the real product is the single strongest trust-killer for local businesses —
> "if you cut corners letting me see the product, you probably cut corners on the product."
> Use the real photo (enhanced if needed); generate atmosphere/motion/context around it.

### 1b. Verifiably local anchor (strengthen existing)
In the "Permission to be specific" bullet, add:
> Ground the concept in something VERIFIABLY LOCAL — a real place feature, a real customer behavior
> from the research detail, a named street/landmark. Generic "anywhere" imagery when the local
> audience knows the real place triggers the strongest backlash ("that's not here"). The concept
> should pass the test: "could a local regular watch this and nod, not squint?"

---

## 2. Director Stage (creative_director.md)

### 2a. Majority-real rule (NEW hard rule)
Add to the hard rules section:
> **Majority-real segments.** At least HALF of the non-card segments must be `real_clip` or
> `moodboard` (real-photo-based). `seedance_shot` is the accent — a hero motion moment — not the
> spine. An ad built mostly on generated footage reads as AI regardless of how good each clip is.
> The real footage IS the authenticity; generated footage supports it.

### 2b. Ending flexibility (REPLACE existing card mandate)
Replace "The LAST segment MUST be a card carrying the practical/conversion info" with:
> **The ad must deliver name/location/booking info — but HOW is a creative choice.** Options:
> - `card` — a closing info card (the current default; still valid, not always best)
> - `overlay` — name/location/handle as a text overlay on the final visual beat (softer, native)
> - `callback` — visual or verbal callback to the hook; info lives in caption/bio only
> - `tag` — a minimal location tag / @handle, Instagram-native
> - `linger` — the final shot holds; info is in the on-screen overlay or caption, no card
>
> Pick what fits the concept + voice_style. `social_native` and `influencer_pov` lean toward
> overlay/callback/tag; `local_ad` leans toward card. A branded card every time is a template tell
> — "the moment the video stops pretending to be content." The conversion info must EXIST; the
> packaging varies.
>
> The LAST segment is still REQUIRED and must carry the info somehow — but it is NOT required to
> be type=card. It can be any segment type with the info delivered via its overlay, card_text, or
> the segment's visual content.

Update the output schema doc: note that the last segment can be any type (not just card), and add
an optional `ending_type` field (one of: card | overlay | callback | tag | linger) for observability.

### 2c. Pacing variance (REPLACE uniform beat guidance)
Replace "Plan MANY SHORT beats (~1.5–2s each → aim for 8–14 segments)" with:
> **Plan MANY SHORT beats, but VARY the rhythm.** Aim for 8–14 segments at ~1.5–2s average, but
> NEVER uniform same-length cuts — metronomic rhythm is the #1 AI-editing tell. Specify each
> segment's `duration_s` with DELIBERATE VARIATION:
> - A 0.8s punch followed by a 2.4s hold followed by 1.2s — irregular, human-feeling
> - Clusters of 3 fast cuts (~1.0s) then one held beat (~2.5s)
> - Accelerating: starts ~2.5s, tightens to ~1.0s by end
>
> If your segment durations are all within ±0.3s of each other, the edit will feel robotic. Vary
> by at least 0.5s between adjacent segments. The Editor will refine, but your plan sets the shape.

### 2d. Script: ban the tricolon (ADD to banned patterns)
Add to the existing anti-pattern / banned-words section:
> **No three-part parallel lists in the spoken script.** The "rule of three" (tricolon) is the
> single most reliable LLM structural fingerprint — ~82% of AI text shares it. Write
> ASYMMETRICALLY: a fragment, then a longer thought, then a question. Sound like a person
> mid-thought, not a copywriter who outlined first. Also ban: hedge openers ("It's worth noting
> that..."), em-dash parentheticals that balance a sentence, and tidy resolution closers that
> wrap everything up. Humans trail off, digress, and leave things hanging.

### 2e. No AI depiction of the real product (ADD to hard rules)
> **Never plan a `seedance_shot` that depicts the actual product a customer will receive** — the
> real food, the real nails, the real haircut result, the real arrangement. Use the REAL photo
> (enhanced) for these. Generated product imagery is the local-SMB backlash epicenter. Generated
> atmosphere/motion/context AROUND the real product is fine.

---

## 3. Translator / Per-Shot Prompt Composer (prompt_translator.md)

### 3a. Lighting: practical/uneven, never "studio" (ADD to prompt conventions)
Add after the existing "How to compose the prompt" section:
> **Lighting direction (critical — the "AI afternoon" is a top tell):**
> Default to PRACTICAL, UNEVEN lighting — describe the actual light source in the room:
> "window light from the left, warm and slightly harsh" / "overhead fluorescents, slightly green"
> / "mixed: warm pendant lamp plus cool daylight from the door."
> NEVER prompt: "soft diffused light," "studio lighting," "cinematic lighting," "dramatic
> lighting," "golden hour glow," "backlit halo." These produce the flat, uniform, AI-signature
> "pleasant cloudy afternoon" look where every environment is lit identically. If the scene is a
> nail studio under fluorescents, describe THAT.

### 3b. Color: muted phone-camera, never vivid (ADD)
> **Color direction:** Muted, slightly underexposed, phone-camera-natural color. Add to EVERY
> prompt: "natural phone-camera color, slightly muted, not color-graded."
> NEVER prompt: "vibrant," "saturated," "vivid," "rich colors," "dramatic colors," "cinematic
> color." Over-saturated, video-game-grade color is a top-3 AI visual tell.

### 3c. Camera feel: handheld, never smooth (STRENGTHEN existing)
Strengthen the existing anti-warp guidance:
> **Camera feel:** Default to "slight handheld drift, natural micro-movement, not stabilized" for
> every shot. NEVER "smooth tracking," "steady dolly," "fluid motion," "stabilized." Unnaturally
> smooth motion with zero micro-jitter is the #1 subconscious AI-video tell — real phone footage
> is NEVER this smooth. Even tripod shots have micro-vibration.

### 3d. Compose around failure regions (STRENGTHEN existing)
Ensure these are explicit (some may already be present):
> - Hands below frame, behind the subject, or naturally out of focus — never featured.
> - No in-scene text, signage, menus, price cards, or readable words (added as Remotion overlay).
> - No mirrors, reflective glass, or chrome surfaces (reflections break down).
> - No background crowds or extras (they walk wrong).
> - Generated clips target ≤ ~3s to avoid object/identity drift.

---

## 4. Shot Agent / Judge (shot_agent.md)

### 4a. "Too polished" soft signal (ADD — not a hard fail)
Add after the existing calibration section:
> **"Too polished" signal (soft, not a hard fail):** if the clip looks unnaturally smooth
> (zero micro-jitter), uniformly lit (flat diffused light with no visible source), and
> over-saturated (vivid colors, "video-game grade") — note it in `reasons` as:
> "clip looks overly polished/synthetic — rougher lighting, muted color, and handheld feel would
> help." This is NOT a disqualifying artifact — don't fail the clip for it. It's feedback for the
> prompt composer on the next attempt to write a rougher prompt. Only apply this signal if the
> clip is clearly "AI-clean" (all three: smooth + uniform-lit + saturated); don't flag clips that
> are just well-shot.

---

## 5. Voice Stage (voice.py scaffold guidance / inline)

### 5a. Preserve breaths and disfluency
Add to voice-generation guidance (wherever the voice config is documented):
> **Do NOT strip breaths, filler sounds, or micro-pauses** from the generated VO. Continuous,
> breath-free delivery is a moderate-high AI-voice tell — real speakers breathe audibly every
> 5–10s. If the TTS model has a "natural mode" or "preserve breaths" setting, enable it.
> If not configurable, note as a known limitation.

### 5b. Post-processing: light compression
> **Apply light dynamic-range compression** (ffmpeg `acompressor`) to the VO track before muxing
> — this kills the "digital stiffness" of synthetic speech and brings it closer to phone-recorded
> voice. Subtle; don't over-compress.

### 5c. Script-as-speech reinforcement
> The script must be AWKWARD-PROOF when read aloud. If it sounds like writing (balanced clauses,
> tidy structure, no fragments), it will sound like AI when spoken. One idea per line. Punctuation
> as breath cues. Fragments are fine. Trailing off is fine.

### 5d. Future note: speech-to-speech (don't build)
> The highest-quality VO path is a human performing the line, then voice-converting via ElevenLabs
> speech-to-speech — inherits real cadence, breath, and disfluency. Note for future; don't build.

---

## 6. Editor Stage (editor.md)

### 6a. Rhythm profiles (REPLACE uniform beat guidance)
Replace "Video beats ~1.2–1.8s, never > `max_s`" with:
> **Choose a rhythm PROFILE, then vary within it.** Metronomic same-length cuts are the #1
> AI-editing tell — even at 1.5s, uniform = robotic. Pick one:
> - `punchy_irregular` (DEFAULT) — 0.8, 2.2, 1.0, 1.6, 0.9, 2.5 — no two adjacent beats the
>   same length, at least 0.5s difference between neighbors
> - `accelerating` — starts ~2.5s, tightens to ~0.8s by end (builds energy toward CTA/payoff)
> - `breath_and_burst` — clusters of 3 fast cuts (~0.8–1.2s), then one held beat (~2.5s), repeat
>
> State the chosen profile in `reasoning`. Video beats still ≤ `max_s`; cards/moodboards ≤ ~3s.
> The overall average should land ~1.5–2s but individual beats MUST vary.

### 6b. Caption sparsity option (ADD to caption_style)
Add a fourth caption style:
> - `sparse` — only the KEY PHRASE (3–5 words per line) appears on screen, not full verbatim
>   transcription. Human-placed emphasis on the most important words only. The rest is heard,
>   not read. Use when the visual is strong enough to carry without wall-to-wall text.
>
> `caption_style` ∈ {clean_pop, emphasis, karaoke, sparse}.
> Full-verbatim karaoke every time is a caption-preset tell. Vary across ads; `sparse` is often
> the most native-feeling for social.

### 6c. Room tone layer (ADD — if feasible in Remotion/ffmpeg)
> **Ambient room tone:** layer a subtle ambient room-tone track (a generic "indoor room tone"
> loop, very low volume) under the VO. Dead-silent backgrounds between spoken words read as
> synthetic — real rooms have texture. If a music bed is present and already fills the gaps,
> this is optional; if VO-only moments exist, add it.

### 6d. Micro-jitter on static clips (ADD to motion options)
Add to the motion vocabulary:
> - `handheld_jitter` — subtle random micro-movement added to an otherwise-static clip (Remotion
>   transform: slight x/y drift + rotation, ~1–2px amplitude, randomized). Use on `real_clip` or
>   `moodboard` segments that are too perfectly still. Unnaturally smooth/locked footage reads AI.
>
> `motion` ∈ {punch_in, parallax, handheld_jitter} (video/moodboard only, optional).

### 6e. Ending-type awareness (ADD)
> The Director may specify an `ending_type` (card | overlay | callback | tag | linger). If the
> last segment is NOT a card, realize the ending accordingly:
> - `overlay`: render name/location/handle as a text overlay on the final visual segment
> - `callback`: no info overlay; the visual/audio callbacks to the hook
> - `tag`: minimal location pin / @handle, native-style
> - `linger`: the final shot holds with a subtle overlay or caption-only info
> If `ending_type` is absent, default to `card` (backward-compatible).

---

## 7. Editor Reviewer (editing_reviewer.md)

### 7a. "Template feel" lens (ADD — new lens alongside existing 5)
Add as lens 6:
> 6. **Template feel** — does this edit feel like it came from a template tool or AI editor?
>    Check: (a) are cuts metronomic — same length ± 0.3s across 3+ adjacent segments? (b) are
>    captions tracking every single word identically with no variation? (c) are flashy transitions
>    (whip/slide/zoom) used on 3+ cuts? (d) does the ending feel like "and now the ad part"
>    (a sudden branded card after natural-feeling content)? If YES to 2+ of these, FAIL with
>    specific fixes: "vary beat 3–5 lengths," "switch to sparse captions," "drop the second
>    whip transition," "soften the ending to an overlay."

### 7b. Rhythm lens update (MODIFY existing)
Change the rhythm lens from "consistently brisk" to:
> **Rhythm** — are cuts DELIBERATELY VARIED (brisk overall but with intentional holds and
> punches)? Do adjacent beats differ by ≥0.5s? No dead air > ~2.5s. Metronomic = FAIL even if
> fast. Reward irregular, human-feeling rhythm.

### 7c. Update output schema
Add `template_feel` to the scores object:
> `"scores": {"grab": 0.0, "rhythm": 0.0, "contrast": 0.0, "payoff": 0.0, "motion_graphics": 0.0, "template_feel": 0.0}`

---

## 8. Creative Reviewer (creative_reviewer.md)

### 8a. "Reads as LLM" lens (ADD or fold into SMB-fit)
Add to the SMB-fit lens (lens 3), or as a sub-check:
> **LLM-script tells (sub-check of SMB-fit):** does the script contain: (a) a tricolon / three-
> part parallel list, (b) hedge openers ("It's worth noting..."), (c) em-dash parenthetical
> balance, (d) a tidy resolution closer that wraps everything up? These are the top 4 LLM
> structural fingerprints (~82% of AI text shares them). If the script has a tidy three-part
> anything, FAIL — humans don't speak in triplets. `improvement`: "break the parallel structure;
> make it asymmetric — a fragment, a longer thought, trail off."

### 8b. "Sounds like a person" test (STRENGTHEN)
Add to the existing voice/tone guidance:
> **Read-aloud test:** read the script out loud. Does it sound like a person mid-thought who
> happens to be saying something interesting? Or does it sound like a copywriter who outlined
> first? Fragments, tangents, and asymmetry = GOOD. Balanced, tidy, complete sentences with no
> rough edges = the tell. If every sentence is grammatically perfect and roughly the same length,
> flag it.

---

## 9. References (scaffolds/references/)

### 9a. script_craft.md — add anti-LLM-tell section
Add a new section after the existing anti-patterns:
> ## LLM-script tells to avoid (the structural fingerprints viewers pattern-match)
> These are the patterns that make a script read as "written by AI" even when the words themselves
> are fine. The top 4 (from Bloomberry Research, ~82% of AI text):
> 1. **Tricolon / rule of three** — "Fresh ingredients. Friendly staff. Fair prices." / any
>    three-part parallel list. The single most reliable giveaway. Write asymmetrically instead.
> 2. **Hedge openers** — "It's worth noting that..." / "Interestingly enough..." Kill on sight.
> 3. **Em-dash balance** — "The salon — known for its balayage — is open Tuesdays." A sentence
>    that tidily parenthesizes its own context. Humans don't do this when speaking.
> 4. **Resolution closers** — a final sentence that neatly wraps the whole thought ("And that's
>    what makes it special." / "Because at the end of the day..."). Real people trail off.
>
> Also avoid: "delve," "robust," "pivotal," "comprehensive," "elevate," "unlock," "nestled,"
> "It's important to note," compulsive both-sides balance.

### 9b. smb_verticals.md — add "AI-depiction danger zone" note
Add to the "What doesn't work" section:
> - AI depicting the actual product the customer will receive. Generated food/nails/hair/flowers
>   that isn't the real thing triggers the strongest local backlash — "if you cut corners letting
>   me see the product, you probably cut corners on the product." Use the real photo (enhanced);
>   generate atmosphere/context around it, never the product itself.

---

## 10. Ending Agent (DESIGN NOTES — don't build yet, capture for next spec)

The research validates a dedicated ending designer. Capture these design notes in a comment or
a `docs/ending_agent_notes.md` for the future spec:
> - Mirrors the Hook Designer pattern: a tool the Director calls (or a separate post-Director
>   stage) that designs the final ~2–3s.
> - Five ending types: card, overlay, callback, tag, linger (see Director §2b above).
> - Selection criteria: voice_style + concept drive the choice. social_native/influencer → softer
>   endings; local_ad → card is fine.
> - The ending must deliver the conversion info SOMEHOW — but "how" varies. The card-every-time
>   pattern is a structural tell that the video is an ad.
> - The ending is a discrete object in the brief (like the hook) — inspectable, iterable,
>   separately testable.
> - Don't build until the Director's ending flexibility (§2b) has run for 5–10 real runs and
>   you've seen whether the Director picks varied endings on its own or defaults to card.

---

## Acceptance checks
1. Pipeline completes end-to-end on stubs (schema changes backward-compatible).
2. Grep for any hard-coded assumptions about the last segment being type=card — fix any that break
   when the last segment is a real_clip with an overlay.
3. `caption_style` enum now includes `sparse`; downstream (KineticCaption.tsx or equivalent)
   handles it (may need a code change — flag if so, but the scaffold change is in scope here).
4. `motion` enum now includes `handheld_jitter`; Remotion handles it (may need a component —
   flag if so).
5. Editor reviewer output schema includes `template_feel` score; no downstream consumer breaks.
6. With real keys (you run): compare a pre-change run and a post-change run side by side. The
   post-change output should have: varied cut rhythm (not metronomic), practical/uneven lighting
   in generated shots, muted color, non-card ending on at least some runs, and no tricolons in
   the script.

## What this does NOT change
- The pipeline structure (concept → director → shots → editor → review). Template the intent.
- The hook designer or its mechanics (already strong).
- The $5 cost ceiling or budget enforcement.
- The Seedance/Remotion bright line (D21).
- The critic-loop pattern (produce → review → regen). Just adding/updating lenses.

## Guardrails
- Scaffolds + references only. Flag any implied code changes (sparse captions, handheld_jitter
  component, room-tone layer, VO compression) as "needs a small code change — build separately."
- Backward-compatible schemas. New optional fields only.
- The majority-real rule and no-AI-product rule are HARD GATES — same enforcement level as the
  before/after gate. Don't make them soft suggestions.
- The "too polished" shot-judge signal is SOFT (feedback, not fail). Don't let it burn retries.
- Don't over-constrain the Translator's lighting/color language to the point where every prompt
  sounds the same ("fluorescent, muted, handheld"). The key is to ban the AI defaults (soft
  diffused, vivid, smooth) and let the scene's real lighting drive the description.
