# Build Spec — Multi-Generation Rearchitecture (Shot Agent + Editor + coupled Keyframes)

## Why
Real testing shows single-call 15s Seedance gens fail too often, and the architecture caps polish.
This spec replaces the single Seedance call with a multi-shot generation flow (one Seedance call
per shot, each judged + retried) and adds a real Editor stage (Remotion) that assembles shots +
voice + b-roll into a polished final video. Voice becomes a dedicated TTS call (fixes the robotic
native voice). Tier 3 keyframes (Nano Banana, consistent set) are coupled IN because independent
shots otherwise drift visually.

THIS IS THE BIGGEST ARCHITECTURAL CHANGE TO DATE. It reverses the earlier single-call decision.
Both decisions were right at their time — single-call got us to working; multi-gen + editor is
the path to polish. Capture this reversal in `docs/ARCHITECTURE.md`.

Tier 0/1/2 (concept, formats/POV, hook) remain prereqs and should be in place first.

## The new pipeline
```
concept -> director -> enhance -> keyframes -> shots -> voice -> editor -> review
```
- **keyframes** (Nano Banana): consistent set of per-shot keyframes (Tier 3 work, see SPEC_tier3).
- **shots** (NEW Shot Agent): per-shot generate + judge + retry.
- **voice** (NEW): single TTS call from Director's script.
- **editor** (NEW Editor Agent + Remotion): assembles shots + voice + b-roll into final mp4.

Note: editor/transitions in-prompt (SPEC_editing_transitions) becomes mostly obsolete — the Editor
owns transitions now. Keep the Director's `pacing` / `editing_feel` intent fields; they now feed the
Editor instead of the Translator. Remove the Translator's transition vocabulary section (or scope it
to within-shot only).

## Decisions locked (reflect in code/scaffolds)
- Per-shot judge: **Gemini, cheaper tier (Flash class) — VERIFY current id and that it accepts
  video input at build**. Stub if absent.
- Per-shot retries: **3**. On 3rd failure, flag the shot to the operator (do NOT silently accept).
- Editor: **Remotion** (verify against Rendervid/JSON2Video in a 1-hour spike before commit).
  Start with cuts + captions + audio mux + simple transitions; Phase 2 adds motion graphics /
  kinetic text / beat-sync.
- Shot Agent and Editor Agent are EACH their own stage with their own scaffold.
- Cost ceiling: **$5/run**. Track in real time; abort/flag if exceeded mid-run.

## Pre-build spikes (do these BEFORE writing pipeline code)
1. **Editor spike (~1 hour):** generate one example with Remotion AND one with Rendervid/JSON2Video.
   Compare output polish for the simple cuts+captions case. Confirm Remotion choice (or revise).
   Write findings to `docs/editor_findings.md`.
2. **Judge model verification:** confirm exact Gemini Flash-tier id that supports video input
   and is cheaper than the Director's model. Write to `docs/judge_findings.md`.
3. **Nano Banana verification** (from SPEC_tier3 Step 0): also required here. Do not skip.

## Before you start
Read all existing specs (Tier 0/1/2/3, editing_transitions) and:
`pipeline/agent/loop.py`, `pipeline/agent/registry.py`, `pipeline/director.py`,
`pipeline/translator.py`, `pipeline/execution.py`, `pipeline/review.py`, `pipeline/tracing.py`,
`pipeline/config.py`, `run.py`, `scaffolds/creative_director.md`, `scaffolds/prompt_translator.md`.

## STEP 1 — config
- `MODEL_ROUTER["shot_judge"]` (cheap Gemini Flash, verified) and `MODEL_ROUTER["tts"]` (fal TTS,
  verified endpoint).
- `MAX_SHOT_RETRIES = 3`; `COST_CEILING_USD = 5.00`.
- Cost constants for per-shot Seedance, judge, TTS, Remotion render.
- Editor render service config (Remotion CLI/Lambda/SSR — choose at spike; default to local CLI
  for v0, document upgrade path).

## STEP 2 — `pipeline/shots.py` (Shot Agent stage)
`run_shots(run, brief, seedance_plan, keyframes, inventory, *, use_cache) -> dict`:
- For each shot in the Director's plan, run an INNER agentic loop:
  1. Build a per-shot Seedance prompt (single-shot, NOT multi-shot — labeled shots removed; one
     subject, one action, one camera). Reuse Translator craft per shot (split the Translator into a
     per-shot call, OR have Shot Agent compose directly — recommend the latter to keep responsibilities
     clean: Translator becomes per-shot prompt composition called by Shot Agent).
  2. Call Seedance (image_to_video using the shot's keyframe as start frame; or text_to_video if
     no keyframe). `generate_audio=False` — voice is separate, ambient handled by Editor.
  3. JUDGE: cheap Gemini Flash inspects the rendered clip (as video) against the shot spec.
     Returns `{pass: bool, reasons: [...], score: 0-1}`. Check: prompt adherence, no obvious
     artifacts (hand/face/object integrity), matches keyframe identity (consistency).
  4. If pass -> approved; cache `shots/shot_<n>.mp4`. If fail -> retry up to 3 times with
     PROMPT FEEDBACK from the judge's reasons baked into the next attempt.
  5. After 3 failures -> add shot to `flagged_shots`, do NOT accept silently. Continue with
     remaining shots; surface flags to operator at end of run.
- Cost tracking: increment `run.add_cost("shots", ...)` and `run.add_cost("shot_judge", ...)` per
  call. After each shot, check accumulated cost — if approaching ceiling, log warning; if exceeding,
  abort remaining shots with a clear cost-ceiling error.
- Return `{shot_id: clip_path or None}` + `flagged_shots: [...]`.
- Trace EVERY call; reasoning per shot lands in REASONING.md ("Shot Agent: shot 2, attempt 2 failed
  because [judge reason], retried with [adjustment], pass on attempt 3.").

### `scaffolds/shot_agent.md`
- Role: per-shot quality gate; iterate prompt based on judge feedback; know when to give up (3).
- Encodes how to incorporate judge feedback into the next-attempt prompt (e.g. judge says "hand
  has 6 fingers" -> add explicit negative + reduce hand visibility in next attempt).
- "NOT for:" creative judgment or composition decisions.

## STEP 3 — `pipeline/voice.py` (one TTS call)
`run_voice(run, brief, *, use_cache) -> dict`:
- Single call to fal TTS (verified endpoint) with Director's `speech` text + voice direction.
- Apply voice prompt tactics from SPEC_tier2 Part B1 (pacing cues, voice description).
- Output: `voice/voiceover.mp3` + line-level timestamps (request word/line timing if the TTS
  endpoint supports it; this drives the Editor's caption sync and shot timing).
- Stub when no key.

## STEP 4 — `pipeline/editor.py` (Editor Agent stage)
`run_editor(run, brief, shots, voice, inventory, *, use_cache) -> Path`:
- **Editor Agent (LLM):** generates the EDIT PLAN — a structured timeline describing the assembly:
  shot order + per-shot trim/duration aligned to voice timing, transitions between each pair,
  caption track (text + timing from voice timestamps), audio mix (voice lead, music bed optional
  off in v0, ambient mute), b-roll insertions.
- **Edit plan schema** (concrete, machine-renderable):
  ```
  {
    "duration_s": float,
    "tracks": [
      {"type":"video","clips":[{"src":"...","start_s":0,"end_s":3,"transition_out":"hard_cut"}, ...]},
      {"type":"audio","clips":[{"src":"voiceover.mp3","start_s":0,"end_s":15,"gain":1.0}]},
      {"type":"caption","clips":[{"text":"...","start_s":0,"end_s":2.3,"style":"default"}]}
    ]
  }
  ```
- **Renderer (deterministic):** takes the edit plan JSON and renders via Remotion (a small Remotion
  project in `editor_render/` with a single composition that reads the plan and lays out
  video/audio/caption tracks). Execute via Remotion CLI (`npx remotion render`).
- Phase 1 scope (this spec): cuts, simple transitions (hard cut + crossfade), burned-in captions
  styled minimally, audio mux. NOTHING fancier.
- Phase 2 (later spec): kinetic typography, beat-sync, motion graphics, multiple caption styles.

### `scaffolds/editor.md`
- Role: realize the Director's `pacing`/`editing_feel` intent into a concrete edit plan.
- Hard rules: voice timing drives shot durations; every caption pairs to a voice line; pacing
  budget honored; output must be valid edit-plan JSON only.
- "NOT for:" generating shots, fixing bad shots, creative concept.

### Remotion project (`editor_render/`)
- Minimal Remotion setup: `package.json`, `tsconfig.json`, `src/Root.tsx`, `src/Composition.tsx`.
- One composition that reads `edit_plan.json` and renders: stacked `<Video>` clips with `<Audio>`
  overlay and `<AbsoluteFill>` caption track. Use Remotion's `<Sequence>` for timing.
- Document the Node/npm version requirement; gitignore `node_modules`.
- VERIFY current Remotion API at build (props, render CLI flags); do not trust training-recall.

## STEP 5 — review stage adapts
`review.py` now reviews the FINAL ASSEMBLED VIDEO (Editor output), not per-shot. Keep mechanical
checks (playable, duration, frames not black). Per-shot judgment already happened in Shot Agent;
don't duplicate it here.

## STEP 6 — wire run.py
- STEPS: `["concept","director","enhance","keyframes","shots","voice","editor","review"]`.
- Each step honors `--from-step` cache; Editor depends on shots + voice both being present.
- Director schema gains: `pacing` (str), `editing_feel` (str) — already specced — these feed the
  Editor (not the Translator) now. Translator's transition vocabulary section is removed/scoped to
  within-shot motion only.

## STEP 7 — observability (extend, don't replace)
- Run dir adds: `shots/` (approved clips + per-attempt thumbnails), `voice/` (mp3 + timings),
  `editor_plan.json` (the edit plan), `editor_render/` symlinks or copies if useful.
- `lineage.json` extends to: concept -> plan -> keyframes -> shots[approved/flagged/attempts] ->
  voice -> edit_plan -> final -> verdict.
- REASONING.md gets per-stage sections: Shot Agent (per-shot attempts + judge reasons), Editor
  (why this edit plan realizes the Director's pacing).
- New `COST.md` (human-readable) showing per-stage cost with the $5 ceiling, so a $4.80 run is
  visible mid-flight.
- `tools/diff.py` extends to diff edit plans across runs (the new "what changed" between runs is
  often in the edit plan, not the prompt).

## Cost guardrail (the $5 ceiling)
- `tracing.py` exposes `run.cost_total()`.
- Before each Seedance/judge/TTS call, check `cost_total() + estimated_call_cost < COST_CEILING`.
- If exceeded mid-run: log clearly, halt remaining work, flag to operator, finalize partial run dir.
- Each retry estimated; after every shot, log running cost against ceiling.

## Migration plan (don't break existing runs)
- Keep the old `execution.generate_video` single-call code path behind a feature flag
  (`config.SINGLE_CALL_MODE`, default False). It can stay for fallback while multi-gen stabilizes.
- Existing tests stay; add new tests for the new stages.

## Acceptance checks
1. Pre-build spike files exist: `docs/editor_findings.md`, `docs/judge_findings.md`, Nano Banana
   findings (from SPEC_tier3).
2. Pipeline completes end-to-end on Carol_Dog with stubs (Shot Agent stubs each shot; voice stub;
   Editor renders a placeholder mp4 via Remotion with stub assets).
3. `--from-step shots` and `--from-step editor` replays work.
4. Shot Agent retries on judge failure; flagged shots after 3 attempts surface to operator and do
   not break the pipeline.
5. Cost ceiling enforced: a synthetic run hitting >$5 in stub cost halts and writes a clean
   ceiling-exceeded artifact.
6. With real keys (you run): shots are individually judged + approved; voice is separate and
   cleaner than native; final assembled video is visibly more polished than the previous single-call
   output; visual consistency across shots is acceptable thanks to keyframes.

## Out of scope (Phase 2 of editor)
Kinetic typography, motion graphics, beat-sync, multiple caption styles, hook-variant A/B
generation. Capture in a follow-up spec when Phase 1 is shipping.

## Guardrails
- Reverse the single-call decision EXPLICITLY in `docs/ARCHITECTURE.md`; do not just delete it.
  Record both "why we chose single-call then" and "why we moved to multi-gen now (real failure
  rate + polish ceiling)" so future you doesn't re-debate it without context.
- Verify ALL external surfaces at build: Gemini Flash video-input id, fal TTS endpoint, Remotion
  current CLI/API, Nano Banana endpoint. No training-recall.
- Reuse the existing agent loop / tracing / model_router / replay patterns.
- Schemas remain inspectable JSON. Stubs work offline. Cost-tracked every call.
- Phase 1 editor stays SIMPLE — cuts/captions/audio mux/basic transitions. Resist scope creep into
  motion graphics until Phase 1 ships and runs are stable.
