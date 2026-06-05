# DECISIONS — key architectural choices and their reasoning

> When Claude Code asks "should I do X?" and the answer depends on context that isn't in the
> spec, look here. Each decision is one paragraph: what we decided, why, and what it means in
> practice. If you (Claude Code or operator) want to revisit one, fine — but read the reasoning
> first so the same trade-offs aren't re-discovered.

## D1. Multi-generation, not single-call Seedance
We previously generated the whole 15s ad in one Seedance multi-shot call. Real testing showed two
ceilings: failure rate on a full 15s generation is too high, and polish is capped (no real edit
control, no clean transitions, robotic native voice). We moved to one Seedance call per shot, each
judged by a cheaper Gemini and retried up to 3x, then assembled by a real editor (Remotion). This
costs more per run, takes more latency, and reintroduces a real assembly stage — all worth it
because the previous architecture had a quality ceiling we'd hit. Keep the old single-call code
path behind a feature flag for fallback while multi-gen stabilizes. Both decisions were correct in
context; do not re-litigate without new evidence.

## D2. Director-plans / Translator-composes (the recurring pattern)
Every place we have a "what" and a "how," we split them across two LLM calls — judgment + taste in
one, craft + execution in another. Concept decides the bold idea; Director executes it into a plan;
Translator composes the per-shot prompt; Shot Agent regenerates and judges; Editor Agent decides
the edit plan. This separation is non-negotiable because fusing judgment and execution selects for
SAFE output (the model defends what's easy to defend, which is the cliché). Don't merge stages to
"save a call" — the split IS the quality lever.

## D3. The Concept stage runs BEFORE the Director, and self-selects
A bold idea must be chosen before structured planning, because the act of filling in a JSON schema
pulls the model toward the safest defensible option. So we ideate freely (prose, 5 concepts, name
and reject the first 2 as clichés, push to 4-5), then self-select the boldest *feasible* concept.
The Director then EXECUTES the chosen concept and cannot drift back to the cliché. Feasibility is a
hard gate: every concept declares which real assets it uses and what would need to be generated; a
concept that needs footage you don't have and can't plausibly generate is rejected at ideation.

## D4. The Director is multimodal (Gemini) and SEES the assets
The Director receives the actual photos and videos, not text descriptions of them. A director who
can't see what it's directing is directing blind, which produces generic plans. Gemini is chosen for
native multimodal + video understanding. NOTE: Gemini "Omni" is a video GENERATION model (a Seedance
competitor) — do NOT use it for the director brain. Use Gemini Pro for understanding/direction;
Seedance for generation.

## D5. Per-shot judge with 3 retries, then flag — never silent acceptance
The Shot Agent judges each generated shot with cheaper Gemini Flash (verify exact id at build).
Three retries max. If all three fail, flag the shot to the operator — never silently accept a
"least-bad" shot. Silent acceptance is how quality regressions get hidden. The judge feeds its
reasons back into the next-attempt prompt so retries are informed, not random.

## D6. $5 hard cost ceiling per run
We cap each run at $5 and track cost in real time. If a run approaches the ceiling, log a warning;
if it exceeds, halt remaining work and flag to operator. The economics: ~5 shots × ~3s × ~$0.18/s
Seedance + LLMs + TTS + judge + keyframes ≈ $4 base, leaving ~1 retry averaged across the run before
the ceiling. The judge must be strict enough to catch bad shots but not so paranoid that everything
retries 3x. Cost discipline is a feature, not a constraint to bypass.

## D7. Editor is Remotion (Phase 1: simple, Phase 2: motion graphics)
Phase 1 editor scope: cuts + burned-in captions + audio mux + simple transitions. Phase 2: kinetic
typography, motion graphics, beat-sync (separate spec, later). Remotion was chosen over JSON-API
alternatives (Rendervid, JSON2Video) because the ceiling for true motion-graphics polish is higher,
and we know we want motion graphics eventually — switching editors mid-project is painful. Do a
1-hour spike (`docs/editor_findings.md`) to verify Remotion vs. alternatives before committing the
build, in case real-world output changes the calculus.

## D8. Voice is a separate TTS call, not Seedance's native voice
Seedance's native voice sounds robotic in real testing. With multi-gen we generate shots silent
(`generate_audio=False`), TTS the script separately (one call, fal TTS endpoint — verify id at
build), and the Editor muxes voice over silent video. This also gives caption sync from TTS line
timestamps for free.

## D9. Keyframes (Nano Banana) coupled with multi-gen, not before/after
Independent per-shot generation produces visual drift across shots (lighting, palette, identity).
The keyframe stage (Nano Banana 2 generates a consistent set of per-shot start frames) is the
mechanism that holds the look together. Build it WITH the multi-gen rearchitecture, not as a
separate later tier — they're one architectural change. Verify Nano Banana's real capabilities at
build (`docs/nano_banana_findings.md`); the design assumes consistency control + photo-as-reference,
which must be confirmed against live docs.

## D10. Triage is salvage, not a bouncer
Triage assesses every provided asset and produces a per-asset REMEDIATION plan (upscale, sharpen,
relight) — NOT a pass/fail verdict. The enhancement step then APPLIES the remediation per asset.
Genuinely unrecoverable assets are flagged honestly. The reason: SMB businesses hand you mediocre
photos; throwing any away is exactly wrong, because you might discard the only shot of the actual
product. Triage assesses; enhancement repairs; nothing gets dropped just for being weak.

## D11. Before/after is a HARD GATE
The before_after format (and any before/after framing inside other formats) is available ONLY if
the operator's brief explicitly states which photo is "before" and which is "after." Plain language
in the brief is the source of truth — no inferred detection. The reason: a heuristic detector that
sometimes thinks two unrelated photos look similar would let the model pick a format the assets
can't support, and the model would then construct a fake before/after from generated footage. The
hard gate makes this impossible by design.
> **AMENDED (D37):** explicit `before_`/`after_` FILENAME prefixes now also count as an operator
> statement and unlock the gate (≥1 of each). This is still an explicit operator LABEL, not pixel
> inference — the operator named the files. Pixel-content inference remains forbidden.

## D12. Format menu is the Motion guide's 8, with availability gates
Director picks ONE of: testimonial, demo, listicle, montage, split_screen, behind_the_scenes,
tutorial, unboxing. Each carries selection criteria (when to choose / audience fit / messaging /
trade-off). Availability gates: `testimonial` only with a real testimonial source; `unboxing` only
with a packaged product; `before/after` variants only behind the hard gate. Montage is allowed but
the scaffold names the "wallpaper" failure mode explicitly so the model avoids defaulting to it.

## D13. The Motion data is a STRONG PRIOR, not gospel
Motion's findings come from $14B/yr of DTC Meta ad spend. They transfer well to local SMBs on the
craft level (hooks, authenticity, format selection) but NOT on the volume thesis (ship 50 variants
and let the algorithm pick winners — an SMB cannot play this game). When applying Motion findings,
ask: does this make sense for "drive walk-ins to a local salon," or only for "maximize ROAS on a
$1M DTC account"? Operator verdicts calibrate the prior over time.

## D14. Hermes-IDIOM agent loop, not Hermes-the-application
The agent loop mirrors the Nous Research Hermes Agent's registry+loop pattern (tools register at
import via decorator; loop dispatches based on native function-calling), but it runs on the Gemini
and Claude function-calling APIs directly. We do NOT import Hermes-the-application internals.
Future bridge to the real Nous Hermes runtime is via exposing this pipeline as an MCP server, not
embedding Hermes as a library.

## D15. The Seedance prompt is the product (within each shot)
This was true under single-call; it remains true per-shot under multi-gen. There is no assembly
step that can rescue a bad prompt for an individual shot. The Translator's per-shot prompts (or the
Shot Agent's, depending on how the split lands at build) are where quality lives, which is why we
have observability centered on them: PROMPT.md, prompt-diff tools, REASONING.md for the Translator,
per-attempt logs for the Shot Agent.

## D16. Observability is structured around (concept → plan → prompt → shot → edit → output → verdict)
A run is inspectable end-to-end: every stage writes a numbered artifact, every LLM call logs full
prompt + raw response + thinking trace, every tool call traces. `REASONING.md` carries the human
narrative; `lineage.json` carries the pairing for later analysis. The goal: 20 runs becomes a real
dataset of "what concepts/prompts produced ads worth shipping." Don't skip observability for speed —
it IS the iteration loop.

## D17. Operator (you) is the creative reviewer for ~20 runs
We do NOT build an automated creative judge in v0. After ~20 manual operator verdicts (filled into
`06_operator_review.json`), the data tells us what failure modes the judge should catch — at which
point we build the judge calibrated against that data. Building the judge earlier risks teaching it
to defend the wrong things.

## D18. New repo, old project kept as `_reference/`
This multi-gen rearchitecture is a new repository. The previous single-call repo is kept as a
read-only reference (`_reference/old_pipeline/`) — do not modify, do not import. The new project
reuses the agent loop, tracing, triage, errors module, and scaffold structure as PATTERNS to follow;
it does not import the old code. This is to avoid the half-built middle ground where new and old
architecture are entangled. NOTE: this also overrides the main spec's "keep single-call behind a
`SINGLE_CALL_MODE` flag" — we did NOT port single-call code; the fallback is running `_reference/`
directly. (Recorded in docs/ARCHITECTURE.md so it isn't re-introduced.)

## D19. Mixed-segment composition; Director picks length (15–30s)
The ad is composed of heterogeneous segments, not a fixed list of Seedance shots: `seedance_shot`
(generated, via the Shot Agent), `real_clip` (provided video, trimmed by Remotion), `moodboard`
(Nano Banana composition keyframe animated by Remotion), and `card` (Remotion template). The Director
picks total length within 15–30s based on the concept and mixes segment types freely. **The Director
never reasons about cost at planning time** — plan creatively; the $5 ceiling (D6) is a pipeline-level
safety net, not a creative constraint. (`SPEC_followup_mixed_segments.md`.)

## D20. Director owns segment planning (no new agent)
Segment selection and ordering is one creative composition decision, so it folds into the Director
rather than a separate Composition Agent — keeping the single creative decision intact. A separate
agent was considered and rejected as fragmenting one decision across two minds.

## D21. The Seedance/Remotion boundary is a single bright line
Seedance generates new video footage ONLY (the `seedance_shot` type). Remotion handles EVERYTHING
else — moodboard composition + motion, real-clip trimming, card rendering, transitions, captions,
audio mux. If a task could plausibly be either, choose Remotion. This one clean split is the
architectural-simplicity lever: no fuzzy middle, no per-task decision.

## D22. Pacing defaults to brisk/frenetic; mid-pacing is the exception
Script word cap tightened to ~30 words for 15s, ~50 for 30s — white space is part of pacing; a tight
script lets the editor cut tight. The Director's `pacing` defaults to `brisk` (most) / `frenetic`
(offer/urgency/announcement); `measured` is allowed only with explicit justification. Mid-tempo
cutting is the named default failure. (Length floor stays 15s, D19.)

## D23. Director picks a `voice_style` (local_ad / social_native / influencer_pov)
One default voice fits no business well. The Director chooses a voice style + justifies it; the
researched `scaffolds/references/script_craft.md` (injected into Concept + Director + reviewers)
teaches what each sounds like, plus creator-native craft and the "local-TV-ad" anti-patterns to avoid.
The creative reviewer rewards bold/specific/native voice and never sands ideas for safety.

## D24. The editor has a critic loop + selective Phase-2 capabilities
The critic-loop pattern (concept/director/hook) extends to the editor: `editor.plan_timeline⟳` —
plan → editing reviewer (first-0.5s grab / rhythm / contrast / payoff) → regenerate → accept-best.
The Remotion toolkit expanded just enough that the reviewer has tools to demand: kinetic word-by-word
captions (clean_pop / emphasis) replacing static caption blocks, and animated cards (scale_pop /
slide_in / fade). Beat-sync, music bed, and broader motion graphics are deferred (D25, when needed).

## D25 (SHIPPED — Phase 2 / Workstream D). Music bed + beat-sync + heavier motion-graphics
New `music` stage (after shots): an **instrumental-only** mood bed (`cassetteai/music-generator` on
fal, ~7s, ≤$0.01) → **librosa** beat grid `{music_path, bpm, beats[]}`. The editor snaps interior cuts
onto the beat grid (`_snap_to_beats`) and muxes the music **ducked** under the voice (a second Remotion
`<Audio>`, gain 0.18 with a VO / 0.55 without). Heavier motion-graphics: transitions extended to
{hard_cut, crossfade, dip_to_black, slide, whip, zoom}; per-video `motion` {punch_in, parallax};
`overlay` {lower_third, badge}; a `karaoke` caption style. The editor scaffold (v0.4) + editing
reviewer (v0.2, +`motion_graphics` lens) teach/judge them. Stubs offline (no FAL_KEY → no music, empty
beats → editor renders exactly as before). Bright line D21 holds: music is audio + a grid; all visuals
stay Remotion. Cost ceiling D6 unchanged.

### D25a. CassetteAI replaced Beatoven for the music bed
The original D plan used `beatoven/music-generation`. Its fal endpoint accepted requests but **hung in
`Queued` forever** (worker never picked up the job — confirmed by polling `fal_client.status`). Swapped
to `cassetteai/music-generator`: instrumental-only, ~7s latency, $0.02/min, output `{audio_file:{url}}`
(WAV). One-line `MODEL_ROUTER["music"]` swap if Beatoven recovers. See docs/music_findings.md.

## D26 (SHIPPED — Workstream E). Run-0008 operator polish: captions · pace · music library · writing
Tuning pass from the first live run's operator review (run 0008, Carol's Dog Daycare).
- **Music = a curated LIBRARY pick, not per-run generation.** Runtime picks a royalty-free instrumental
  bed from `assets/music_library/` (manifest: `{file, energy, mood_tags, bpm, beats[], source,
  license}`) matched to the Director's `pacing` (brisk/frenetic → **high** energy, so it never drags —
  the "too slow" fix), rotating by run index. Free + instant (`MUSIC_COST=0`), reproducible. Seeded once
  via `spikes/seed_music_library.py`; operators can drop in their own tracks (beats computed on the fly
  if absent). The librosa beat grid, ducking, and `run_music` signature are unchanged; generation
  survives as the seeder backend + a one-line fallback. (FreePD — the intended CC0 source — has shut
  down; archive.org CC0 audio isn't ad-bed material; current seeds are up-tempo CassetteAI instrumentals,
  royalty-free for commercial use.)
- **Pace ≈20% faster via tighter cuts, not faster playback.** A deterministic **Director pacing guard**
  (`_pacing_feedback`) inside the existing self-correct loop: if `avg_beat > PACING_MAX_AVG_BEAT_S`
  (2.2s) and unused usable assets remain, it regenerates with "more, shorter beats" feedback (run 0008
  shipped 6 beats over 18s ≈ 3s/beat — exactly this trap). Editor holds tightened: `EDITOR_MAX_EXTENSIBLE_S`
  4→3, `EDITOR_TARGET_BEAT_S` 2→1.5; scaffolds name the slow-cadence anti-pattern. `VIDEO_PLAYBACK_RATE`
  stays 1.25 (motion natural).
- **Emphasis captions fixed (then re-fixed in E6).** First pass: `alignItems:baseline` + 3 dp word-time
  rescale. But the real bug was deeper — see **D27**.

## D27 (SHIPPED — E6). Caption highlight tracks the SPOKEN word, in every style
Operator: the highlight kept landing on the wrong word, or none. Root cause (diagnosed on runs 0008/0009,
NOT a timing bug — timings/atempo/offset all verified clean): `emphasis` colored every **long** word
(≥6 chars) statically, so the accent almost never sat on the word being spoken, and `clean_pop` had no
highlight at all. Fix (`editor_render/src/KineticCaption.tsx`): one invariant for ALL styles — the
highlighted word is the **most-recently-started word** in the on-screen line (`currentIdx = reduce`),
so exactly one word is lit, it's the spoken one, and it advances on each `start_s` (no gaps, no
double-highlights, no length-based coloring). Styles now differ only in reveal/layout: clean_pop
(reveal + accent), emphasis (+ the spoken word pops 1.12× via transform — no reflow), karaoke (whole
line, unspoken dim, spoken word accent + lift). Uniform 64px (no static big words) keeps the baseline
stable. Verified against run 0009's real word timings + audio (accent on commuters→guilt-free→drop-off
as the voice says them). The no-caption tail when voice < video is left silent (operator choice).
- **Writing: "commit to one idea."** Director scaffold (v1.1) + creative reviewer (v0.2) now attack the
  feature-list body directly — the body must EXTEND the hook's POV, not pivot to a brochure; a list-y
  body is a reviewer FAIL with a *sharpening* fix. Operator-supplied real transcripts slot into
  `script_craft.md` (the highest-leverage lever) — already wired into Concept/Director/Reviewer.

## D28 (SHIPPED — Workstream F). The spoken script does NOT sell; the closing CARD sells
Operator audit: output still "read as a scripted ad" because the **spoken VO was forced to carry the
sale** — `creative_director.md` mandated price/hours/location/booking in the script, so even a strong
hook+idea got a brochure tail ("…losing their mind with joy. Carol's. Book their spot."). The moment the
voice pivots to logistics, it reads as an advertisement. Fix: the VO = HOOK + ONE true idea, and it
**ends on the idea** — NO CTA, NO logistics in the spoken script. ALL practical/conversion info
(name/location/hours/booking) moves to a **mandatory closing `card`** (the conversion surface that frees
the voice). Director scaffold v1.2 + concept gate + `script_craft.md` (structure + examples rewritten to
VO-idea-only) + creative reviewer v0.3: the bar is now **earned viewer attention** ("would a scroller
stop, watch to the end, not clock it as a desperate ad — while still knowing what/where from the card"),
and a **spoken CTA/logistics line in the VO is a FAIL** (info on the card is good; in the voice is the
defect). Also (F2): a `seedance_shot` MUST seed from a real `@Image` (image-to-video animating the
business's own photo); pure text-to-video ("generated") is banned (AI-stock undercuts authenticity) —
`director._validate` drops a non-@Image shot as a safety net. Pacing (E2) unchanged. Editor's short-VO
pacing warning relaxed (F3): a short VO is intentional when the tail is covered by card/moodboard beats.
This narrows toward the paid-ad path on purpose — the organic/`distribution_mode` pivot is researched +
parked for after a confident paid ad is tested against real traffic.

## D29 (SHIPPED — Workstream G). Input contract = `brief.json {name, location, brief}`; research queries the NAME
The Google review lookup silently failed on a real business (Conway Nail Bar, 2000+ reviews) because
`research_business` queried `f"{business} {brief}"` — the underscored run-label + the whole marketing
brief; a place-search API wants a NAME, not free-text copy (an Explore agent confirmed live: the brief's
"…on Google Map." phrase alone zeroes the search; the clean name matches instantly). Fix: query Google
with the **name (+ optional location to disambiguate)**, never the brief; de-underscore in case the name
came from a slug (`pipeline/research.py`). Input contract: `triage` now prefers **`brief.json`**
`{name, location, brief}` (falls back to free-text `brief.txt` + `--business`). Kept deliberately minimal
+ vertical-agnostic — only `name`/`location` are structured (what the pipeline mechanically needs);
everything business-specific stays in the free-text `brief` (no service-specific fields to overfit).
`location` also flows to the Director payload so the F closing card can carry the real location. Verified:
Conway → `found:true`, real detail ("recreates your reference photo exactly — snow leopard print").

## D30 (SHIPPED — anti-AI-tells, Batch 1: scaffolds only). "Template the intent, de-template the surface."
From SPEC_anti_ai_tells.md. The pipeline structure stays rigid (it guarantees the message); the
viewer-facing surface varies enough to not pattern-match as AI/template. Batch-1 (scaffold + reference
only, backward-compatible):
- **Human-anchor + no-AI-product (HARD GATE, concept + director):** ≥half of non-card segments are
  real_clip/moodboard; a `seedance_shot` never depicts the actual product the customer receives (use the
  real photo; AI does atmosphere/motion around it). *Degrades* gracefully when there's ~no real footage
  (don't deadlock — flag the gap). Verifiably-local anchor strengthened.
- **Ban LLM-script tells (director + creative_reviewer + script_craft.md):** no tricolon/"rule of three"
  (the #1 fingerprint), no hedge openers / em-dash balance / tidy resolution closers; write
  asymmetrically; read-aloud test. Reviewer FAILS a tricolon.
- **Varied rhythm, not metronomic (director + editor + editing_reviewer):** uniform same-length cuts are
  the #1 AI-editing tell; plan deliberate variation (≥0.5s between adjacent beats); editor picks a
  rhythm profile (punchy_irregular / accelerating / breath_and_burst); new `template_feel` reviewer lens.
- **Anti-AI LOOK in shot prompts (prompt_translator):** practical/uneven lighting (ban "studio/soft
  diffused/golden hour"), muted phone-camera color (ban "vivid/saturated/cinematic"), handheld micro-
  movement (ban "smooth/stabilized"), compose around failure regions (hands/text/mirrors/crowds). Shot
  judge gains a SOFT "too polished" signal (feedback, never a fail).
- **Flexible ENDING (REPLACES F's mandatory card; operator chose full flexibility incl. caption-only):**
  Director sets `ending_type` ∈ {card, overlay, callback, tag, linger}; the last segment need not be a
  card. Info must EXIST somewhere (on-screen card/overlay, or caption/bio for callback/tag) — VO still
  never sells. `overlay` endings reuse the existing `lower_third`; the rest leave info off-screen.
Scaffold versions bumped (concept-v0.1, director-v1.3, shot-prompt-v1.1, shot-agent-v0.3, editor-v0.5,
reviewer-v0.4, editing-reviewer-v0.3). **Deferred to Batch 2 (need code):** `sparse` captions,
`handheld_jitter` motion, room-tone layer, VO compression, preserve-breaths. **Deferred:** dedicated
Ending Agent (docs/ending_agent_notes.md) — gate on whether the Director varies endings on its own.

### D30a. No moodboard photo-reuse (follow-up — the majority-real gate over-produced moodboards)
First post-anti-tell run (0015, Conway) looked repetitive: the majority-real gate pushed 4 moodboards
from only 5 photos, so @Image1/@Image3/@Image5 each appeared in TWO moodboards. Added a deterministic
`director._moodboard_feedback` guard (in the existing regen loop, like the pacing guard): if any photo
appears in >1 moodboard, regenerate with a cap (≤ `photos//2` moodboards, distinct photos each, lean on
real_clip windows for variety). Scaffold (director-v1.4): a moodboard consumes its photos; no photo in
two moodboards; prefer one richer moodboard + real_clip windows when photos are scarce. Majority-real
rule unchanged (moodboards still count).

## D31 (SHIPPED — anti-AI-tells Batch 2: the code-requiring items)
The Batch-2 items from SPEC_anti_ai_tells.md that needed code (vs Batch-1's scaffold-only):
- **`handheld_jitter` motion** — a Remotion `Jitter` wrapper (subtle per-frame micro-shake, deterministic
  via Remotion's seeded `random` so renders reproduce) so too-perfectly-locked footage reads as real
  phone footage. Added to `Segment.motion` (types.ts), `_MOTIONS` (editor.py), editor scaffold.
- **`sparse` caption style** — `KineticCaption` drops function/stop words (deterministic content-word
  filter; keeps numbers + capitalised/proper + non-stopword ≥3 chars) so the screen shows only KEY
  words, not wall-to-wall verbatim. Added to the `caption_style` enum + editor scaffold. (Tunable — it
  can get quite minimal; a smarter editor-selected-key-spans version is a future refinement.)
- **Light VO compression** — `editor._compress_vo` (ffmpeg `acompressor`, gentle) on the staged voice
  before muxing, to soften synthetic "digital stiffness." Falls back to uncompressed on error.
**Skipped, with reasons:** room-tone layer (§6c) — we ALWAYS have a music-library bed now, so there are
no dead-silent backgrounds to fill; building it would mean sourcing a room-tone asset for ~no benefit.
Preserve-breaths (§5a) — ElevenLabs via fal exposes no explicit breaths toggle (`stability` is the only
related knob, and changing it risks consistency); the VO compression covers the stiffness it targeted.
**Deferred:** dedicated Ending Agent (still gated on whether the Director varies endings on its own).

## D32 (SHIPPED — Ending Agent / "Batch 3"). A dedicated ending designer
Gate met: runs 0013/0015/0016 all defaulted to a `card` ending despite full `ending_type` flexibility
(D30), so the Director wasn't varying endings on its own — exactly the spec's trigger to build the
agent. Built `design_ending` — a Director tool mirroring `design_hook` (`pipeline/agent/tools.py`,
`_ENDING_SYSTEM`): the Director calls it (MANDATORY) after planning segments + voice_style, gets
`{ending_type, on_screen_text, caption_suggestion, why}`, realizes it in the LAST segment (card with
`card_text` / a visual beat with a `lower_third` overlay / a bare visual for callback/tag/linger), and
copies it into the brief's new `ending` object. Lean: one Gemini call, no internal reviewer (the
creative reviewer already checks the ending; keeps cost/latency down). Director scaffold v1.5.
`MAX_CREATIVE_RETRIES` bumped 2→3 (the director now stacks reviewer + pacing + moodboard guards and was
exhausting 2 retries). Editor renders all ending forms already (card; overlay via the D4 lower_third;
callback/tag/linger leave info off-screen → caption). Verify: do endings actually vary across the next
several runs?

## D33 (SHIPPED — Remotion design system, Batch A: designed cards + typography)
From SPEC_remotion_design_system §4 + SPEC_card_typography. The old cards rendered a flat `card_text`
("A | B | C") in one font/size — placeholder-looking. Rebuilt `templates/Cards.tsx` as a card SYSTEM:
four distinct STYLES (`glass` translucent panel · `type_only` bold-on-footage · `photo_backed` over a
dimmed photo · `minimal_bar` accent bar), each rendering up to four TYPOGRAPHIC TIERS — `name` (Inter
Black, uppercase, tracked) / `tagline` (Caveat handwriting, contrasts the geometric name; a specific
line, not a slogan) / `info` (Inter Medium, dim) / `cta` (pill | handle | subtle) — with a staggered
entrance. Real fonts via `@remotion/google-fonts` (Inter + Caveat; added to package.json). Schema:
`card_style` + structured `card_tiers` (types.ts, editor.py threading, director scaffold v1.6 +
design_ending realizes a card into tiers). Backward-compat: a flat `card_text` still renders (name +
info); old `card_template` names alias to a style. **Palette guard kept** (operator's call): accent used
as TEXT falls back to white when `palette[0]` is too dark (lum ≤ 90), avoiding the grey-palette reversal;
white text on the dark-backed styles means no live video-luminance detection needed. Verified: all 4
styles render as distinct designed cards. **Deferred (later batches):** caption system §1 (keep
white/grey + palette guard), transitions §2, motion §3 expansions, live luminance detection.

## D34 (SHIPPED — Remotion design system, Batch B: 4-caption-style system)
From SPEC_remotion_design_system §1. Rebuilt `KineticCaption.tsx` from one look into a ROUTER over four
distinct caption aesthetics: `bold_center` (big Inter Black centered — default), `minimal_lower` (48px
Inter Medium, bottom-left over a gradient, phrase fades in as a block), `handwritten` (Caveat script,
2–3 words, hand-placed jitter + underline on the spoken word), `sparse_keyword` (only key words, ONE at
a time, 96px slam-in). The spoken word always highlights. **Palette guard kept (operator's call):**
accent used as text only when `lum(palette[0]) > 110`, else white — no grey-palette reversal. Legacy
`clean_pop`/`emphasis`/`karaoke` alias to `bold_center` sub-modes; `sparse` → `sparse_keyword` (backward
compat). Fonts reuse Inter + Caveat (no new font; stayed under the 3-font cap). `caption_style` enum +
editor scaffold v0.6 updated; editor default → `bold_center`. Verified: all 4 render as distinct looks.
**Still deferred:** transitions §2, motion §3 expansions (scale_breath/drift), live luminance detection.

## D35 (SHIPPED — design-system Batch C + editor-loop/history/reviews spec)
Closed the remaining design-system items + SPEC_editor_loop_topic_history_reviews in five batches.

- **Batch C (transitions + motion), SPEC_remotion_design_system §2–3.** Three transitions — `speed_ramp_in`
  (a "whoosh into place" settle; a CSS approximation since OffthreadVideo's playbackRate is static),
  `scale_reveal` (overlap reveal scaling into place), `light_leak` (a single amber sweep, **capped to 1
  per ad** in editor.py) — and two motions — `scale_breath` (subtle 1.0→1.03→1.0 pulse), `drift` (slow
  diagonal pan). Crossfade 0.4→0.3s. Wired through editor.py (`_TRANSITIONS`/`_MOTIONS`/
  `_OVERLAP_TRANSITIONS`), types.ts, AdComposition.tsx, editor.md (v0.7). Verified: tsc clean + a full
  render exercising all five.

- **Part C — review expansion.** Distiller now returns ranked `anchor_candidates[]` + `review_summary_themes`
  (was a single `detail`; back-compat alias `detail = anchor_candidates[0]`). Added Google `reviewSummary`
  to the field mask + a best-effort legacy newest-sort fetch (the Places API (New) has NO review-sort
  control, so the reliable wins are the AI summary + multi-candidate distillation; the legacy widen
  no-ops cleanly when only the New API is enabled). Per-business cache `inputs/<slug>/reviews_cache.json`
  (TTL `REVIEW_CACHE_TTL_DAYS=7`) skips the Google fetch on repeat runs; `operator_supplied[]` never
  expires. Concept passes `cache_key=run.business` (the slug, not the display name) + picks a fresh anchor.
  Verified live on Conway: 4 ranked candidates (named techs, a snow-leopard design), cache hit on run 2.

- **Part B — per-business topic history.** New `pipeline/history.py`: each successful run appends its
  concept/angle/review-detail/voice-style/ending to `inputs/<business>/history.json` (idempotent on
  run_id; refreshes past operator verdicts). Concept reads a `previous_runs` de-weight block; Director
  reads `endings_used_past_runs`. **Soft steer, never a hard ban** — honor a brief that asks for a repeat.
  Directly targets the observed Conway repetition (same concept + always-card ending). `ending_types_used`
  keeps duplicates so "card, card, card" is visible.

- **Part A — editor `ending` lens.** The editor critic loop + `template_feel` + varied-`rhythm` lenses
  already shipped (D24 + D30/D31), so Part A reduced to ONE new lens: `ending` (editing_reviewer v0.4) —
  does the ending fit `voice_style` and vary vs `endings_used_past_runs`? editor.py threads an
  `ending_context` into the edit-review artifact. Verified: a 3rd-consecutive card on an influencer ad
  FAILs (0.2, targeted fix); a fresh varied overlay PASSes (0.83).

Repo tidy: specs consolidated under `docs/Specs/`; CLAUDE.md paths fixed.

## D36 (SHIPPED — narrative perspective is grounded in the assets; deprioritize 1st-person)
Runs 0018 & 0019 both narrated first-person ("Conway moms…", an "I Love it!!!" caption) over footage a
THIRD PARTY clearly shot — a mismatch that reads as fake. Operator rule: **deprioritize first-person POV;
prefer 2nd/3rd person; first-person ONLY when the assets are genuinely first-person (selfie / phone-in-
hand).** The bias was systemic (concept asked for "the POV"; `social_native` was "the default";
`influencer_pov` is first-person; `script_craft` led with POV hooks), and nothing checked perspective
against the assets. Fix: the Director (which SEES the assets, D4) now declares `asset_perspective`
(third_party | first_person | mixed) + `narrative_person` (first | second | third); a deterministic
`_perspective_feedback` guard in the self-correct loop (alongside pacing/moodboard/voice) regenerates when
the script OR ending caption is first-person-singular while `asset_perspective != first_person`. Scaffolds
reweighted (director-v1.9, concept-v0.3, script_craft) so 2nd/3rd person is the default and
`influencer_pov` is gated to self-shot footage; no invented first-person customer voice — a REAL
attributed review quote is the one exception. Creative reviewer (v0.5) enforces it as an `smb_fit` FAIL.
`asset_perspective` defaults to `third_party` when omitted (the safe SMB assumption, keeps the guard
active). Verified: unit guard (6 cases), reviewer (1st-person FAILs / 2nd passes), live Director on Conway
→ `third_party` / `second` / fully 2nd-person "POV: you walk in…" script (vs the old first-person).

## D37 (SHIPPED — four fixes from the Hue_Salon run 0020)
- **Benefit/outcome-led narrative (ALL verticals).** Operator: lead with the desirable result, never the
  problem/fear, and never "X *without* the bad thing" ("vivid color that stays healthy" > "color without
  frying it off"). Reframed the `script_craft.md` "relatable problem" hook → benefit/outcome hook;
  rewrote `smb_verticals.md` "name the frustration"; added a concept gate + a director script rule;
  creative_reviewer (v0.6) FAILs a problem/fear/negative LEAD. A pain may be touched only in service of
  the outcome.
- **Editor critic loop: accept-BEST, not accept-last.** Root cause of repeated editor failures: a parse
  failure dropped `_editor_agent` to a motion-less `_fallback_plan`, and the loop shipped the LAST
  attempt — so a crashed fallback overwrote a good attempt 1. Fix (`editor.py`): track every attempt and
  ship the best (passing if any, else highest mean-score) via `_pick_best`; harden parsing
  (`_extract_json_object` pulls the `{...}` out of prose) + reuse the prior valid plan on parse-fail; and
  `_fallback_plan` now carries varied beat lengths + motion so even a true fallback isn't an auto-fail.
  Same accept-best applied to the concept + director loops. The 7-lens reviewer bar was NOT loosened.
- **Clip-reuse guard (`director.py` `_clip_reuse_feedback`).** Video analog of the moodboard photo-reuse
  guard: a single `@Video` source may back at most 2 real_clip beats and never two back-to-back
  (pinkhair.mp4 had appeared in 3 beats). Folded into the self-correct loop. Also relieves the editor's
  contrast/template_feel failures.
- **before/after filename roles (amends D11 — see above).** `triage.py` tags each image with a `role`
  from `before_`/`after_` filename prefixes and unlocks the before/after format when ≥1 of each exists;
  `_asset_summary` surfaces the role; `creative_director.md` forbids a `before` photo as hero / card /
  standalone showcase (use only paired as a transformation) and promotes the before→after reveal;
  `editor.py` `_card_bg` excludes `before` photos from the card hero (a "before" had landed behind the
  CTA card).

## D38 (SHIPPED — amends D35: the ad always ends on a consistent branded info card)
Operator: ending-type **consistency is good branding**, and the close must be a CLEAR designed card with
the real business info. So the D35 cross-run ending-*variety* enforcement is REMOVED — it also made the
editor loop unwinnable (the editor reviewer's `ending` lens penalized repeating the prior run's
`ending_type`, but `ending_type` is the Director's decision; the editor can only retime, so it failed
all 3 attempts). Now:
- **`editor._realize_ending`** ALWAYS makes the closing beat a designed `card` (converts it; `photo_backed`
  over a real after/neutral photo, else `glass`) carrying `card_tiers`: NAME + a multi-line `info` block
  (address / phone / social — whatever the operator supplied) + a booking CTA. Deterministic, so the
  ending never depends on the Director/editor-agent remembering. Never fabricated (name is the floor).
- **Contact is operator-provided** via OPTIONAL `brief.json` fields (`address`, `phone`, `social`,
  `booking_url`); minimum input stays `{name, location, brief}`. No Places contact-fetch. `inventory["contact"]`.
- **`Cards.tsx`** `info` tier now renders `\n`-split stacked lines (address / phone / social).
- **editing-reviewer v0.5**: `ending` lens reframed to "a clear branded close that lands after the
  payoff" — NO cross-run variety penalty (consistency is intended). **director-v1.12**: dropped the
  vary-the-ending hint; the closer is a consistent branded info card.

## D39 (SHIPPED — scaffold consolidation: one source of truth)
A 2-agent audit found ~180 lines of duplicated direction + one live contradiction. Consolidated:
- **Retired the vestigial ending fields.** Since `editor._realize_ending` deterministically builds the
  closing brand card from `brief.json` (D38), the Director's `ending_type` menu + the `design_ending`
  tool + the `ending` output field were dead AND contradicted the code ("pick an ending form" vs. the
  editor force-carding it). Removed all of them from `creative_director.md` + the director tool list;
  `design_ending` left registered-but-unwired (DEPRECATED). The editor owns the ending.
- **Killed a leftover fragmentation contradiction.** `creative_director.md` STILL told the model to
  "write asymmetrically… trail off… leave things hanging" (the cause of the incoherent copy) even after
  we fixed script_craft. The script-section collapse removed it; coherence-first now stands alone.
- **De-duped perspective.** Enforced by the deterministic `_perspective_feedback` guard, so the
  creative-reviewer's PERSPECTIVE-MISMATCH lens was removed (reviewer-v0.8) and the director scaffold
  trimmed to one line.
- **Slimmed `creative_director.md` 348 → ~250.** Deleted the misplaced "Point of view" section (re-gated
  the Concept stage; the ≥half-real rule survives in Hard Rules), collapsed the 79-line script section to
  its director-unique bits + a pointer to the injected `script_craft.md`, and trimmed the format-palette
  restatement.
- **Injection:** `ad_formats.md` dropped from the Concept stage (format is the Director's pick).
- **Kept (clean):** the deterministic guards (pacing/clip/moodboard/voice/perspective), the editing-
  reviewer `ending` lens (judges the lead-in/payoff, which the editor controls). Principle: each
  directive stated ONCE; deterministic guards enforce the mechanical rules; reviewers judge only what
  isn't guarded. No RULE was dropped — only de-duplicated. Versions: director-v1.13, concept-v0.4 (refs),
  reviewer-v0.8.

## D40 (SHIPPED — scaffold cleanup v2: SPEC_scaffold_cleanup, adapted)
Executed SPEC_scaffold_cleanup against the post-D37/D39 state. Skipped what was already done (the
"relatable problem" hook — D37; the Director dedup — D39). Resolved the ending conflict as the operator's
standing **Option B (card-always)**, NOT the spec's Option A:
- **Fixed the STALE `editor.md`** (D39 had missed it): lens 7 said "the ad no longer always ends on a
  card; the Director sets ending_type; don't force a card" — which contradicted the shipped
  `_realize_ending` (always builds the card). Rewrote to card-always: the pipeline builds the closing
  brand card; the editor animates it cleanly + lands the lead-in. (design_ending stays retired.)
- **`ad_formats.md`:** "pick the ONE format" → a PALETTE of treatments (may combine); dropped the
  dangling `format_reasoning`; fixed the stale moodboard row (keyframes now compose from real photos) and
  the before/after gate note (filename prefixes also unlock it, per D11-amended).
- **Canonical homes (dedup the files D39 didn't touch):** hook patterns → `hooks.md` (script_craft +
  smb_verticals sections collapsed to pointers); perspective + no-CTA → Director (script_craft → pointers);
  metronomic → editing-reviewer Rhythm lens (template_feel lens defers to it).
- **Stale `smb_verticals.md`:** replaced the "13–15s CTA" structure with the freed-script structure
  (hook → develop one idea → ending info CARD; no CTA in the VO); kept the Motion performance data + added
  an `ad_formats.md` pointer.
Versions: editor-v0.8, editing-reviewer-v0.6. Scaffolds/references only — no code. Principle holds: each
rule stated once in its canonical home; references point, don't restate.

## D41 (SHIPPED — APPEAL gate + dial back authenticity absolutism; caption-tail fix)
Run 0022's angle ("7 hours in the salon chair as proof of dedication") was UNAPPEALING — the Concept's
own why_bold admitted it bet on "reframing a friction point as a premium benefit," and it picked the
least-desirable of 4 review anchors. Root cause: no appeal/desirability gate, and the "authenticity beats
polish / lo-fi wins" language was absolute (so "authentic" licensed an unappealing, grind-focused message).
- **New APPEAL gate** (it's an ad — make them WANT it): concept gate #4 + director script + creative
  reviewer lens 2 now require an aspirational angle and FAIL any angle that sells the COST/EFFORT/TIME/
  friction ("7 hours in the chair", "the wait", "the hard work") even framed as "dedication." Concept now
  picks the most DESIRABLE review anchor (the result the customer wants), not the most impressive-to-the-
  business one.
- **Dialed back the authenticity absolutism** (rebalance, not remove): the canonical "Cross-format
  principle" (ad_formats.md) + reviewer bar + concept #5 + script_craft core-truth now say "real beats
  fake-glossy, BUT it's an ad — make it appealing + show the result at its best; authentic = real +
  specific, not low-effort/unflattering." Notably fixed prompt_translator's "muted color, NEVER vivid"
  (counterproductive for a color salon) → "true color, don't dull the hero result"; and shot_agent's
  "too polished" → "synthetic-only; never flag a clean/flattering/vivid result." Real footage stays the
  spine (no fake-glossy-AI, no generated actual-product) — only the LANGUAGE balance changed.
- **Caption-tail bug:** KineticCaption draws a caption PAST its end_s (group +0.25s; sparse_keyword
  +1.2s), bleeding the last word ~0.5s into the clean ending card. Added a hard `caption_cutoff_s` (=the
  card's start) threaded editor.py → render plan → AdComposition → KineticCaption + CaptionTrack: render
  nothing at/after the card. No VO-coverage loss.
Versions: concept-v0.5, director-v1.14, reviewer-v0.9, shot-prompt-v1.2, shot-agent-v0.4.

## D42 (SHIPPED — editor critic loop disabled for latency)
The editor critic loop was the dominant latency (run 0022: 742s / 12 min on 3 failed attempts) and
unreliable (failed all 3 → accept-best shipped ~0.56), while the editor agent's single pass was already
good enough. Gated it off behind `config.EDITOR_CRITIC_LOOP = False`: the editor now runs ONE pass (no
reviewer, no retries). The accept-best loop + `editing_reviewer.md` are kept intact in the `else` branch —
flip the flag to re-enable. Everything downstream (the branded ending card via `_realize_ending`,
`_fit_to_total`, beat-snap, voice-fit + caption cutoff, render) is unchanged. Concept + Director critic
loops untouched. Revisit if single-pass editing quality proves insufficient.

## D43 (SHIPPED — before/after is a deliberate, OBVIOUS sequential reveal)
Operator (runs 0022 + 0023): the before/after comparison wasn't *consciously* built — the Director
dropped a lone "before" moodboard with the afters scattered as generic b-roll, so the viewer never saw
the change. Root cause: the before/after gate unlocks in triage (filenames, D11), but it never became a
STRUCTURE — the "pair before with its after" rule was prose-only (no guard) and nothing made the
comparison obvious on screen (no labels, no reveal cut). Fix = a deliberate **SEQUENTIAL REVEAL**
(operator's choice over split-screen, which would need a new render component):
- **Director** (`creative_director.md` v1.15 + `_before_after_feedback` guard): when before_/after_
  photos exist, a `before` beat is ONLY valid as the SETUP half of an ADJACENT before→after pair (matched
  by number, `before_1`→`after_1`). The guard fires when a before beat isn't immediately followed by an
  after beat (the lone-before bug) and forces a regen. Using before/after isn't *forced* — but if a
  before photo is used, the reveal must be adjacent.
- **Editor** (`_realize_before_after`, editor-v0.9): detects the adjacent (before→after) pair via asset
  `role` and stamps it deterministically — a BEFORE badge (tl) + an AFTER badge (tr) + a `whip` reveal cut
  into the after beat. Built entirely from existing primitives (whip transition + badge overlays +
  `role_from_name`); NO new Remotion component. Independent of the (disabled, D42) editor critic loop.
The reveal uses the operator's REAL before/after photos — generated footage still never fakes one.

## D44 (SHIPPED — kill fabricated contact in overlays; before photo shown PLAIN)
Operator review of run 0026 caught two editor issues:
1. **Fabricated contact (hallucination).** The editor agent invented an `@colorstudio` handle in a
   lower_third overlay (Hue's REAL handle is `@huehairsf`). Rather than re-enable the slow editor critic
   loop (D42 latency), added a DETERMINISTIC guard: `_fabricated_contact` + `_overlay` now DROP any
   overlay whose text contains a handle / URL / email / phone NOT present in `inventory.contact`
   (allow-list against brief.json — real handle stays, invented one is dropped + logged). Fixed the
   scaffold example (`editor.md` lower_third no longer shows an invented `@handle`/fake hours) +
   added a no-fabrication rule. The reviewer remains the tool for BROADER hallucination (fake claims);
   this kills the contact-fabrication class for free.
2. **Before photo was beautified.** A `before`-role beat was rendered as a Nano Banana moodboard
   COMPOSITION (polished) — the opposite of a raw problem-state image. Keyframes now shows a before-only
   beat as the PLAIN raw photo (copyfile, no composition) — also skips a fal call. (Refines D43.)
editor-v0.10.

## D45 (SHIPPED — thread-safe Run + parallel orchestration; ~90s)
Per SPEC_parallelization. Stages waited behind dependencies they don't have. First fixed a **pre-existing
latent race**: the `Run` object appended to trace.jsonl/run.log/REASONING.md and mutated `costs` with NO
lock, yet `shots.py` already ran concurrently (its lock only guarded `budget.check_ceiling`, not
`add_cost`/`trace`/`log`) — so cost could undercount (→ silently slip the $5 ceiling) and trace.jsonl
interleave. Fix: a single `threading.RLock` on `Run` wrapping `trace`/`log`/`reason`/`add_cost`/
`cost_total` (stress-tested: 16×500 concurrent ops → exact cost, 0 corrupt lines). Then parallelized
`run.py`: **enhance ∥ concept+director** (bg thread, collected before the gate), **music ∥
keyframes+shots** (bg thread), and **keyframes concurrent internally** (ThreadPoolExecutor, shared per-run
seed KEPT for set coherence + output-identity — the spec's `seed+n` was rejected). Output-identical;
validated offline end-to-end (run 0027). `MAX_KEYFRAME_CONCURRENCY=4`.

## D46 (SHIPPED — director-loop latency: per-stage thinking + iteration cap)
The director was ~246s/run = 4+ multimodal Gemini calls at hardcoded `thinking_level="high"`. Made
thinking per-stage: `_thinking_config(types, model, level)` + a `thinking_level` kwarg through
`run_agent_loop`. The Director runs at `config.DIRECTOR_THINKING_LEVEL="low"` (it EXECUTES an
already-vetted concept); **Concept stays "high"** (protect ideation). Director agent loop capped 6→4.
Reversible (one config line). Quality to be sanity-checked on the next real run; revert to "high" if the
brief degrades. (Verify valid gemini-3 thinking_level values against live docs.)

**UPDATE (REVERTED to "high"):** real run 0029 showed NO latency win — the director ran 3 attempts
(~246s, same as before) because the loop is dominated by RETRY COUNT (review fails), not per-call
thinking; lower thinking also risks more fails. Set `DIRECTOR_THINKING_LEVEL="high"` (no downside, protects
quality). The per-stage thinking PLUMBING + the 6→4 iteration cap are RETAINED (harmless; cap is the
default and caused no issue). **The real director-latency lever is fewer retries, not thinking depth** —
the open follow-up. (Also newly visible in 0029: the single-pass editor-agent call is ~200s — a separate
latency sink worth a look.)

## D47 (SHIPPED — de-AI pass: phone-camera keyframes + temporal post-processing)
Per SPEC_deai_postprocess: seedance_shot clips read as "AI" next to the real footage. Two layers, applied
ONLY to seedance_shot:
- **Layer 1 (keyframes.py, prompt strings, zero cost):** `generate_from_real` no longer says "polished"
  (it told Nano Banana to "improve" the phone photo) → now "PRESERVE the photo's natural lighting/color/
  exposure; imperfections are FEATURES." `_STYLE_SUFFIX` rewritten to phone-camera physics (mixed
  color-temp light, deep DoF/no bokeh, blown highlights, casual composition, NOT polished) with the
  anti-AI negatives folded into the positive prompt (nano-banana-2 has no negative_prompt).
- **Layer 2 (new pipeline/deai.py + shots.py):** `deai_clip()` runs one ffmpeg pass on each APPROVED clip
  in the shot worker — temporal grain + vignette + slight softness + handheld micro-jitter. Raw
  `shot_N.mp4` preserved; the editor consumes `shot_N_deai.mp4` (clips map repointed). `DEAI_ENABLED`
  toggle; graceful fallback to raw on ffmpeg failure; ffmpeg-only (works offline; parallelized free in the
  worker). Presets light/moderate/heavy (default moderate).
- **COLOR DELIBERATELY PROTECTED (overrides the spec):** Layer 1 says "natural, not over-graded" (NOT
  "muted") and Layer 2 applies NO desaturation — de-AI is texture-only — so a genuinely vivid result
  (the salon's hair) stays vivid. This honors D41 (muting killed the money shot).
Validated: deai_clip → valid 1080x1920 mp4 for all presets; offline E2E (run 0028) fires de-AI, preserves
raw, editor uses _deai. PENDING real-run/operator: keyframe visual quality + seedance-vs-real_clip blend +
intensity tuning.

## D48 (SHIPPED — non-verbal voice cues: performed-emotion tags, gated)
Operator A/B (run 0029 line, Laura): ElevenLabs v3 renders PERFORMED-EMOTION tags convincingly
([excited] hook, [laughs softly] wry line) but a synthetic [exhales] sounds FAKE. And the fal endpoint
echoes tags into the timestamp stream → they'd show as caption TEXT. So:
- **Director (creative_director.md v1.18):** MAY place AT MOST ONE performed-emotion tag in `speech`, only
  when a beat earns it ([excited]/[laughs softly]/[whispers]/[casual]), at a natural pause; NEVER
  breath/body-sound tags ([exhales]/[sighs] — they read fake); default NONE.
- **voice.py enforcement (belt-and-suspenders):** `_sanitize_voice_tags` keeps only ONE whitelisted tag,
  drops banned/excess (and strips all if `VOICE_AUDIO_TAGS_ENABLED=False`). `_drop_tag_chars` strips
  `[...]` spans from the caption/word builders so tags are PERFORMED in audio but never appear on screen
  (the tag still occupies audio time). Stub path strips tags for its captions too.
Validated: sanitizer keeps [excited] only / bans [exhales]; a real fal call with [excited] → clean
captions, words intact. The breath route (real spliced samples) was rejected (the tag is fake; raw breaths
would be a separate heavier effort). PENDING: hear a Director-placed tag in a full real run.

## D49 (SHIPPED — fal upload robust to non-ASCII filenames)
Conway Nail Bar (run 0031) died at keyframes with "authentication failed" — a MISCLASSIFICATION. The real
cause: the nail photos were named with emoji (🌊ocean, 🌸floral). `fal_client.upload_file` ASCII-encodes
the filename into the multipart header, so every upload backend (fal_v3/cdn/fal) crashed with
"'ascii' codec can't encode character" and the error classifier mislabeled it as auth failure (sent us
chasing credits twice). Fix: `keyframes._fal_upload` copies the asset to an ASCII-safe temp name before
upload when the basename isn't ASCII. Verified: 0031 keyframes then cleared, run completed ($3.62, Aria
voice via region-first routing, 3/3 seedance approved). SMB phones routinely produce emoji/accented
filenames, so this is a real-world gate. (Follow-up: errors.classify_api_error should not map an
ascii-encode error to "authentication failed".)
> **EXTENDED (D49b):** the SAME bug hit Gemini's Files API video upload (THE MUSE SF, run 0032 — emoji-named .mp4 reels crashed concept with an UNCLASSIFIED UnicodeEncodeError in httpx). Hoisted the fix into a shared `llm.ascii_safe_path` applied at ALL upload sites: fal (keyframes) + Gemini video uploads (call_gemini_multimodal, call_gemini_video_judge, agent loop). Images are inline bytes so they were never affected. Verified: 0032 concept then cleared the upload and proceeded.

## D50 (SHIPPED — voice-length guard: script must fit the video, no atempo crush)
THE MUSE SF (run 0032) exposed two coupled defects: (1) the Director wrote a ~28s script for a video whose
beats summed to only ~20s, so the editor sped the voice to the 1.55× atempo CAP — rushed/chipmunky; (2)
relatedly the video ran short of the 25–30s target. The existing `_voice_coverage_feedback` only catches
the UNDER case (voice ends early → silent tail). Added `_voice_length_feedback` (the OVER case): estimate
spoken seconds (words / 2.4) vs the video's spoken region = (SUM OF BEAT DURATIONS − ending card) — the
editor fits to the BEATS, not the stated total_duration_s. Fire above ~1.2× (a comfortable atempo) →
regen feedback: cut the script AND/OR add/lengthen beats so the video fills 25–30s (and beat durations
must sum to ~total_duration_s). Catches both the crush and the short-video-fill in one guard. Unit-tested
(fires 67w/20s, quiet 36w/20s); director-v1.19. The 0032 video itself was hand-fixed (coherent ~36-word
script, voice now plays at natural speed) + re-rendered.

## D51 (SHIPPED — voice never crushed past 1.2×: editor detects + escalates)
Run 0032 crushed the voice to the 1.55× atempo cap (chipmunky) by cramming a long script onto a short
video — silently. Operator: the voice must NEVER exceed 1.2×; instead the editor detects a too-short
video and ESCALATES. Built a closed loop:
- `VOICE_MAX_ATEMPO 1.55→1.2` (hard cap). `render()` no longer silently stretches a beat — at the cap it
  absorbs only ≤1s and writes a `voice_fit` creative flag + `[VOICE CRUSH]` log (covers replay paths too).
- `editor._voice_fit_report` attaches `timeline["_voice_fit"]` (est_vo vs the REALIZED region — the gap
  D50's plan-time guard can't see, since `_fit_to_total` clamps clips shorter than planned).
- `run.py` bounded loop (`EDITOR_MAX_ESCALATIONS=2`): if the voice doesn't fit at ≤1.2× (estimate OR
  actual), re-run the Director with feedback ("video Xs too short — add beats from your N unused assets
  or cut the script to ~W words"); the Director (which owns beat decisions) re-plans → back-half re-runs.
  If genuinely asset-starved (unused < 1), one-shot `keyframes.generate_synthetic_asset` adds fill frames
  the Director can use. After the bound, ship at the 1.2× cap + flag. Replay-safe (no-op when cached);
  cost-ceiling-safe.
- Shared `config.VOICE_FIT_RATIO` + `config.SPOKEN_WPS` across D50 + the loop (one source of truth).
- `run_director` gained a `feedback` kwarg (seeds the first attempt). D50 stays as cheap plan-time
  prevention; this is the realized-level backstop.
Validated offline (run 0033, stub voice ×1.5): loop fired ×2, capped at 1.2×, flagged, completed. The
asset-gen branch is the rare last resort (unexercised in the test; import-validated). Real-run tuning
(does the Director resolve the loop; firing frequency) is the next operator check.
