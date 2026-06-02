# Spec — Scaffold Cleanup (conflicts, redundancy, stale content)

> An audit of all 11 scaffold + reference files found: 2 real conflicts, heavy redundancy (core
> rules stated 4-5 times across files), and stale content that predates recent changes. This spec
> resolves all three. No pipeline/code changes — scaffolds + references only.
>
> Core principle: **state each rule ONCE in its canonical home; other places reference, not restate.**
> Stage scaffolds own the RULES for that stage. Reference files own CONTEXT (what converts per
> vertical, how hooks work, what good scripts sound like). When a stage needs a rule that lives
> elsewhere, it says "see [ref]" — it does not copy the rule.

## Before you start
- Read ALL 11 files: concept.md, creative_director.md, creative_reviewer.md, editing_reviewer.md,
  editor.md, prompt_translator.md, shot_agent.md, references/ad_formats.md, references/hooks.md,
  references/script_craft.md, references/smb_verticals.md.
- After making changes, verify: no two files state the same hard rule in different words. Every
  hard rule has exactly ONE canonical home. References provide context, not rules.

---

## CONFLICT 1 — The ending (CRITICAL — resolve first)

### The problem
- Director (v1.13) says: "The ad ALWAYS closes on a designed, branded info card the EDITOR
  assembles... You do NOT choose or vary an ending form."
- Editor (v0.6) says: "the ad no longer always ends on a card (the Director sets `ending_type`).
  Do NOT force or assume a closing card."
- The Director title says "ending retired (editor builds it)" — but the Editor expects an
  `ending_type` from the Director that the Director never emits.
- The Ending Agent (`design_ending` tool) was built and shipped (b995c9c), but the Director
  scaffold doesn't call it.

### The fix (confirm which is the intended behavior, then make BOTH files match)
**Option A (recommended — matches the shipped Ending Agent + the anti-AI-tells spec):**
The Director picks the ending. Update the Director to:
- Remove "The ad ALWAYS closes on a designed, branded info card" and "You do NOT choose or vary
  an ending form."
- Add `design_ending` to the mandatory tool calls (alongside `design_hook`): "After finalizing
  segments, call `design_ending` to design the closing beat — it picks the ending type and writes
  the card tiers / overlay text. Copy its output into the brief."
- Add `ending_type` and `ending` to the output schema.
- The section becomes: "The ad delivers name/location/booking info in its ending. The
  `design_ending` tool picks the form (card / overlay / tag / linger); you call it and realize
  its choice as the final segment."

Editor scaffold: no change needed (it already expects `ending_type`).

**Option B (if you actually want card-always):**
Update the Editor to remove ending_type references, always render a card. Retire the
`design_ending` tool. This contradicts the shipped code — only pick this if you've decided
card-always is correct after testing.

**Claude Code: confirm with the operator which option before implementing. If unsure, go with
Option A (it matches the shipped code).**

---

## CONFLICT 2 — Formats: "pick ONE" vs "a palette you mix"

### The problem
- `ad_formats.md` says: "Pick the ONE format that fits THIS business... justify it in
  `creative_angle` + `format_reasoning`."
- Director says: "The 8 classic formats are TREATMENTS you draw on per segment or across the
  ad — not a single forced choice."

### The fix
Update `ad_formats.md`:
- Change the header guidance from "Pick the ONE format" to: "These are TREATMENTS the Director
  draws on — per segment or across the ad. An ad may combine treatments (a demo opening into a
  BTS middle). The Director justifies the chosen treatments in `creative_angle` +
  `composition_reasoning`."
- Remove `format_reasoning` references (the Director output schema uses `composition_reasoning`
  for the mixed-segment plan, not `format_reasoning`).
- Keep the per-format "when to choose / messaging / trade-off" rows — those are still valid
  context. Just reframe them as "when this treatment works" not "when to pick this one format."

---

## CONFLICT 3 — "Relatable problem hook" vs outcome-first mandate

### The problem
- `smb_verticals.md` lists: "The relatable problem hook: Name the frustration before offering
  the relief. 'Tired of fighting your hair every morning?'"
- Four other files mandate outcome-first and ban problem/fear leads: Concept, Director, Creative
  Reviewer, script_craft.md.
- The reviewer will FAIL a script that uses the hook pattern the verticals doc recommends.

### The fix
In `smb_verticals.md`, remove the "relatable problem hook" entry entirely. Replace with the
outcome-framed version that already exists in the same file:
- Keep: "The outcome/aspiration hook (PREFERRED — lead with the result the customer wants)"
- Remove: "The relatable problem hook: Name the frustration... 'Tired of fighting your hair?'"
- The principle is already stated correctly elsewhere; this is the stale version.

---

## REDUNDANCY FIXES — deduplicate by assigning canonical homes

### Rule: "Lead with outcome, not problem"
**Canonical home: script_craft.md** (it's a script-writing rule).
- script_craft.md: KEEP the full "Lead with the BENEFIT / OUTCOME" section (it's well-written).
- Director: REPLACE the full paragraph with a one-liner: "LEAD WITH THE BENEFIT/OUTCOME — see
  the injected script_craft.md for the full rule and examples. A fear/problem/negative lead is
  a defect."
- Concept: REPLACE the §4 paragraph with: "Lead with the OUTCOME, not the problem (see
  script_craft.md). Frame the concept around the desirable result — never the pain/fear/risk."
- Creative Reviewer: KEEP the FAIL rule in lens 2 (the reviewer NEEDS to know what to catch) —
  but shorten: "PROBLEM/FEAR/NEGATIVE LEAD = FAIL. The hook/script must lead with the desirable
  outcome (see script_craft.md). Flag leads like 'tired of…', 'stop feeling guilty…', 'without
  the bad thing.' `improvement`: 'lead with the result they want.'"
- smb_verticals.md: REMOVE the outcome-hook paragraph (it's redundant with script_craft.md) and
  remove the contradicting problem-hook (Conflict 3 above).

### Rule: "Authenticity beats polish"
**Canonical home: ad_formats.md** (it's the cross-format principle).
- ad_formats.md: KEEP the "Cross-format principle" section.
- Concept §3 and §5: REPLACE with brief references: "Authenticity beats polish AND beats clever
  (see ad_formats.md cross-format principle)."
- Creative Reviewer: REPLACE with: "Authenticity beats polish (see ad_formats.md). A real,
  specific, lo-fi piece that's worth watching outperforms a slick or salesy one."
- smb_verticals.md "What doesn't work": KEEP the one mention ("Trying too hard to look like a
  national brand... authenticity and specificity outperforms"). This is vertical-specific context,
  not a restatement of the rule.
- Prompt Translator: KEEP (it's the execution-level application — "lo-fi specificity beats
  cinematic gloss" is how the Translator enacts the principle in prompt craft).

### Rule: "Spoken script doesn't sell / no CTA in VO"
**Canonical home: Director** (it's the stage that writes the script).
- Director: KEEP the full "THE SPOKEN SCRIPT DOES NOT SELL" paragraph.
- Creative Reviewer lens 3: KEEP the FAIL rule (the reviewer must catch this) — it's correctly
  stated and not overly long.
- Concept: SHORTEN to one line: "The spoken script does NOT sell (the ending carries the info —
  see the Director scaffold)."
- script_craft.md: SHORTEN the section to: "The spoken script does NOT carry the CTA or logistics
  — the Director scaffold defines this rule; the closing card carries name/location/hours/booking."
  Remove the full restatement.

### Rule: "No tricolon / rule of three"
**Canonical home: script_craft.md** (it's a writing anti-pattern).
- script_craft.md: KEEP (in the "Sound like a person" section — already well-placed).
- Director: SHORTEN to: "NO tricolon / three-part list in the script (see script_craft.md —
  it's the #1 LLM fingerprint)."
- Creative Reviewer: KEEP the brief mention in lens 3 (the reviewer catches it).

### Rule: "Metronomic cuts = AI-editing tell"
**Canonical home: Editor** (it's the stage that sets cut timing).
- Editor: KEEP the full treatment in §1 (rhythm profiles).
- Director: SHORTEN to: "NEVER uniform same-length cuts — metronomic rhythm is an AI-editing
  tell (the Editor scaffold defines the rhythm profiles). Specify varied `duration_s` per
  segment (adjacent beats differ by ≥0.5s)."
- Editing Reviewer: currently stated in BOTH lens 2 (rhythm) AND lens 6 (template_feel). FIX:
  lens 2 (rhythm) owns the metronomic check; lens 6 (template_feel) checks the COMBINED pattern
  (metronomic + uniform captions + flashy transitions + card-ending = template). Remove the
  metronomic detail from lens 6 and replace with: "cuts metronomic (already checked by rhythm
  lens — if rhythm passed, skip this sub-check)."

### Rule: "Perspective (1st person only if self-shot)"
**Canonical home: Director** (it decides the perspective).
- Director: KEEP the full "Voice style + PERSPECTIVE" section.
- script_craft.md: SHORTEN to: "Default to 2nd/3rd person; 1st person only when assets are
  genuinely self-shot (see the Director scaffold for the full rule)."
- Concept: KEEP the brief parenthetical in the output schema (it's a hint for the concept
  framing, not a full restatement).
- Creative Reviewer: already says "enforced deterministically... you don't need to police" —
  KEEP as-is (this is correct).

### Hook patterns (3 separate lists → 1)
**Canonical home: hooks.md** (it's the hook reference).
- hooks.md: KEEP as the single complete hook reference.
- script_craft.md "Hook patterns" section: REPLACE with: "Hook patterns — see the injected
  hooks.md for the full list. In the script, the hook is the opening ~3s — apply one mechanic
  from hooks.md, framed as an OUTCOME (not a problem)." Remove the full hook-patterns list.
- smb_verticals.md "Hook patterns that work for local SMB" section: REMOVE entirely. The hooks
  in this section overlap with hooks.md and some are stale (the problem hook). Add a one-liner:
  "For hook patterns, see the injected hooks.md."

---

## STALE CONTENT FIXES

### smb_verticals.md (the most stale file — 147 lines, several sections outdated)

1. **"Load-bearing info" framing in the Service businesses section:** currently implies price/
   hours/location is carried by the script/VO. UPDATE to: "Load-bearing info: price anchor,
   hours/availability, location signal — delivered via the ENDING CARD (not the spoken script).
   The ad must make what/where clear from visuals + the closing info card."

2. **"The 15-second structure" section (lines ~120-130):** says "13–15s: CTA — the one action
   you want them to take." This predates the freed-script work. REPLACE entire section with:
   "The ~15s structure: 0–2s HOOK (stop the scroll) → 2–12s BODY (develop one idea, build
   desire/trust) → 12–15s ENDING (a designed info card or overlay carries name/location/booking).
   The spoken script covers the hook + body; the ending card does the selling."

3. **"Hook patterns that work for local SMB" section:** REMOVE entirely (superseded by hooks.md;
   see dedup above). Replace with a one-line pointer.

4. **"Format & hook performance data" section (the Motion 2026 block):** partially overlaps with
   ad_formats.md. KEEP the Motion data (it's unique context — hit rates, asset-type finding,
   volume thesis caveat). But ADD a note: "For per-format selection criteria, see ad_formats.md."
   Don't duplicate the format descriptions.

5. **"AI depicting the actual product" paragraph in "What doesn't work":** this is correct and
   current. KEEP.

6. **"Slow / 'radio-spot' pacing" paragraph in "What doesn't work":** current. KEEP.

7. **Outcome hook entry:** currently has BOTH the old "relatable problem hook" (stale) and the
   new "outcome/aspiration hook" (current). Remove the problem hook (Conflict 3). Keep the
   outcome hook as context (but add "see hooks.md for the full list").

### ad_formats.md
- Reframe from "pick ONE" to "palette" (Conflict 2 fix above).
- The moodboard row says "NOT asset-faithful yet — cutouts are GENERATED" — verify if this is
  still true after the keyframe stage shipped. Update if the keyframe stage now preserves real
  photos in moodboard compositions.

---

## DENSITY REDUCTION (token budget)

After the dedup, verify approximate line counts. Target:
- Director: ~220 lines (down from 272 — the trimmed rule restatements save ~50 lines)
- Concept: ~95 lines (down from 113)
- script_craft.md: ~65 lines (down from 90 — hook patterns removed, rule restatements shortened)
- smb_verticals.md: ~110 lines (down from 147 — hook section removed, stale structure replaced,
  format data kept but trimmed)
- Everything else: minor trims only.

These are targets, not hard limits. The goal is that each file earns every line — no rule is
stated twice in the same prompt (the stage scaffold + its injected references).

---

## Acceptance checks
1. **No conflicts:** the ending behavior is consistent between Director and Editor. The format
   framing is consistent between ad_formats.md and Director. No hook pattern in any file
   contradicts the outcome-first mandate.
2. **No rule stated 3+ times across files.** Spot-check: grep for "authenticity beats polish",
   "spoken script does NOT sell", "metronomic", "tricolon", "lead with the outcome" — each
   should appear in full in exactly 1-2 files (the canonical home + the reviewer that catches
   violations). Other files reference, not restate.
3. **smb_verticals.md** no longer contains: the problem hook, the stale 15s CTA structure, or
   a hook-patterns section (just a pointer to hooks.md).
4. **ad_formats.md** says "palette/treatments" not "pick ONE format."
5. **Line counts** roughly hit the targets (±10%).
6. Pipeline still runs end-to-end on stubs (no schema changes in this spec — just text edits).

## Guardrails
- Scaffolds + references only. No Python changes.
- Don't remove rules — relocate them to canonical homes and shorten other mentions to references.
- The Creative Reviewer's FAIL rules must stay actionable (it needs to know what to catch, not
  just "see script_craft.md"). Keep reviewer FAIL conditions self-contained but brief.
- Don't over-trim the Director — it's the densest stage and the model needs the guidance. Trim
  restatements, not unique rules.
- Preserve all hard gates verbatim (before/after, human-anchor, no-AI-product). These are
  non-negotiable and should not be shortened to references.
