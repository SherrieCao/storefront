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
