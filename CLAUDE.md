# SMB AI Video Pipeline — multi-gen architecture (project guide)

> This file is read automatically by Claude Code every session. **The pipeline is BUILT and iterating** —
> this doc captures what the system is + how to work on it (not a build-from-scratch plan). For the live
> state use **`docs/ARCHITECTURE.md`** (current snapshot) and **`DECISIONS.md`** (the running record,
> D1–D51 — the source of truth). Read alongside `WHY.md` (purpose + quality bar).
> The previous single-call architecture is preserved in `_reference/old_pipeline/` for reference
> only — do not modify, do not import from. Reuse PATTERNS, not code.

> **Current capabilities (D42–D51), beyond the original build:** stages run in parallel + the `Run` object
> is thread-safe (D45); the editor critic loop is disabled / single-pass (D42); before/after is a
> deliberate adjacent reveal with a bold BEFORE/AFTER stamp + whip (D43); a de-AI pass makes generated
> shots read phone-captured (keyframe realism + ffmpeg grain/vignette/jitter — color untouched, D47);
> business-aware voice routing (gender > region > vertical) + optional performed-emotion audio tags (D48);
> the voiceover is hard-capped at 1.2× and the editor escalates a too-short video back to the Director
> instead of crushing the audio (D50/D51); ad length is **25–30s**.

---

## The one-paragraph "what this is"
Turn a local small business's messy raw assets (a few mediocre phone photos, maybe a video clip,
maybe no logo, a one-line brief) into ONE finished 25–30s vertical video ad. The pipeline is a
sequence of LLM "thinking" stages that decide what the ad should be, plus a multi-shot generation
flow that produces and assembles the actual video. Quality bar: "would a small-business owner
believe this brings them more traffic?" — see `WHY.md`.

---

## The pipeline (multi-gen architecture)
```
triage -> concept -> director -> enhance -> keyframes -> shots -> music -> voice -> editor -> review
```
(Stages run in parallel where deps allow: enhance ∥ concept+director, music ∥ keyframes+shots; keyframes
and shots fan out internally. D45.)
- **triage** — local CV, no LLM. Per-asset salvage plan (upscale/sharpen/relight). Parses
  before/after from the brief. Surfaces the highest-value gap. Handles photos AND videos.
- **concept** — Gemini, multimodal. Brainstorms freely, names + rejects clichés, self-selects the
  boldest *feasible* concept. Fights generic output. Hard feasibility gate on real assets.
- **director** — Gemini, multimodal, runs on the agent loop. EXECUTES the chosen concept: picks
  format (from 8 options), plans shots, writes script, decides `pacing` / `editing_feel`, assigns
  asset anchors per shot. Decides intent only — does not write prompts or edit plans.
- **enhance** — fal.ai. Applies triage's per-asset remediation (upscale/sharpen/relight). Targeted.
- **keyframes** — Nano Banana 2. Generates a CONSISTENT SET of per-shot start frames (preserve real
  / generate-from-real / generate). Holds visual coherence across independent shots. Verify at
  build (`docs/nano_banana_findings.md`).
- **shots** — Shot Agent. PER SHOT: compose per-shot Seedance prompt -> generate (silent, audio
  off) -> Gemini Flash JUDGES the rendered clip as video -> approve or retry up to 3x with judge
  feedback baked into the next attempt -> flag to operator after 3 failures. NEVER silent accept.
  Each approved clip gets a de-AI ffmpeg pass (grain/vignette/jitter, color untouched; D47).
- **music** — a curated royalty-free LIBRARY pick matched to pacing/energy + a librosa beat grid (the
  editor snaps cuts to it). Not generation ($0). (D26)
- **voice** — one ElevenLabs v3 call (fal): voiceover + word-level timestamps (caption sync). Voice is
  ROUTED by business (gender > region > vertical), with optional ≤1 performed-emotion audio tag (D48).
- **editor** — Editor Agent emits a structured EDIT PLAN (JSON: video/audio/caption tracks);
  Remotion (separate render service in `editor_render/`) renders the plan to mp4. Phase 1 scope:
  cuts + captions + audio mux + simple transitions. Phase 2 (later): motion graphics, kinetic text,
  beat-sync.
- **review** — extracts frames of the final assembled video + mechanical checks (playable,
  duration, not black). Per-shot quality judgment already happened in `shots`; don't duplicate it.
  Creative judgment is the OPERATOR's via `06_operator_review.json` for the first ~20 runs.

---

## The recurring split — DO NOT BREAK
Every stage with a "what" and a "how" splits across two minds:
- Concept (judgment) → Director (execution of concept)
- Director (intent) → Translator/Shot Agent (per-shot prompt craft)
- Director's `pacing`/`editing_feel` (intent) → Editor Agent (concrete edit plan)
- Editor Agent (plan) → Remotion renderer (deterministic execution)

Fusing judgment + execution selects for SAFE output. The split IS the quality lever.
See `DECISIONS.md` D2.

---

## Hard rules (these are non-negotiable; cross-reference DECISIONS.md)
- **Before/after is a HARD GATE.** Only available if the operator's brief states which photo is
  before / which is after, in plain language. No inferred detection unlocks it. (D11)
- **Director SEES the assets.** Multimodal call with the real photos+videos attached. Blind
  ideation is forbidden. (D4)
- **Per-shot judge with 3 retries, then flag.** Never silently accept a least-bad shot. (D5)
- **$5 hard cost ceiling per run.** Track in real time; halt + flag if exceeded mid-run. (D6)
- **Authenticity beats polish.** Bias toward real, lo-fi, specific. Cinematic gloss = AI look. (WHY)
- **Reasoning + observability are mandatory.** Every LLM call logs full prompt, raw response, and
  thinking trace. Every stage writes a numbered artifact. (D16)
- **Caveat about agent reasoning:** stated reasoning is the model's *account* of its reasoning,
  not ground truth. The OUTPUT is the real verdict. Use REASONING.md to iterate, not to over-trust
  a clean-sounding justification.

---

## Run directory contract (what every run writes)
```
runs/NNNN/
  input_snapshot/         frozen copy of inputs for replay
  00_triage.json          per-asset remediation plan + gap ask
  01_concept.json         rejected clichés + chosen concept + feasibility
  00_concept.md           human-readable concept narrative
  02_creative_brief.json  director's format + shot plan + script + pacing
  03_enhanced/            remediated real photos
  04_keyframes/           consistent per-shot start frames + map
  05_shots/               approved per-shot mp4s, per-attempt thumbnails, attempt logs
  06_voice/               voiceover.mp3 + line timestamps
  07_edit_plan.json       editor agent's edit plan
  08_assembly/            remotion intermediate
  09_output/final.mp4     final assembled video
  09_output/frames/       extracted final-video frames for review
  PROMPT.md               the per-shot prompts, human-readable
  REASONING.md            how every agent decided (narrative + thinking)
  lineage.json            concept -> plan -> keyframes -> shots -> edit -> output -> verdict
  COST.md                 per-stage cost + total + ceiling status
  trace.jsonl             every LLM/tool call: full prompt, raw response, thinking, cost
  cost.json               per-step + total
  run.log                 human-readable timeline
  meta.json               run_id, business, scaffold versions, model ids, timestamps
  flagged_shots.json      shots that failed 3 retries (if any)
  06_operator_review.json YOUR creative verdict — fill after watching
```

Replay: `python run.py --replay NNNN --from-step <stage>`. Cached artifacts before the named stage
are reused. Scaffold iteration = replay from `concept` or `director`. Editor tuning = replay from
`editor`. Cheap and fast.

---

## Pre-build spikes  _(HISTORICAL — these were done; the spikes are complete and the findings live in
## `docs/*_findings.md`. Kept for context. The live model/endpoint list is in `docs/ARCHITECTURE.md`.)_
These external surfaces must be verified against live docs; do NOT trust training-data recall.
Write findings into docs files so we don't re-research later:

1. **`docs/editor_findings.md`** — generate one example via Remotion AND one via a JSON-API
   alternative (Rendervid or JSON2Video) for the cuts+captions case. Confirm Remotion's polish
   ceiling justifies the heavier integration. (~1 hour)
2. **`docs/judge_findings.md`** — confirm exact Gemini Flash-tier model id that accepts VIDEO input
   and is cheaper than the Director's model. Document the request shape.
3. **`docs/nano_banana_findings.md`** — confirm current Nano Banana 2 model id / endpoint, real
   photo conditioning, consistent-set generation across multiple calls, cutout/segmentation support
   for moodboard, output resolution/aspect-ratio control, cost per image.
4. **`docs/seedance_findings.md`** — confirm the per-shot (single-shot, not multi-shot) usage of
   Seedance 2.0: image_to_video endpoint id with `generate_audio: false`, start-frame from keyframe,
   reference image limits, cost per second. We're using Seedance differently now than the old
   architecture did.

If any spike's findings invalidate the design, ADJUST THE SPEC before coding, don't paper over it.

---

## What to reuse from `_reference/old_pipeline/`
These are good and worth using as PATTERNS (not direct imports):
- `pipeline/agent/{registry,loop,tools}.py` — the Hermes-idiom registry + loop. Real function-calling.
- `pipeline/tracing.py` — Run dataclass, traced_tool, log_llm_call, REASONING capture.
- `pipeline/errors.py` — provider-specific error classifier (Gemini 400-for-bad-key, Anthropic
  billing_error). Saves hours of debugging.
- `pipeline/triage.py` — salvage logic, before/after parsing, gap-ask surfacing.
- `pipeline/llm.py` — Gemini multimodal + Claude call patterns with stub fallbacks.
- `pipeline/lineage.py` — the lineage.json builder shape.
- Scaffolds in `scaffolds/` — particularly `creative_director.md` and `prompt_translator.md`. The
  shot-level prompting work transfers; the multi-shot prompt construction does not.
- The run-directory pattern, replay, and observability discipline.

These are NEW builds (no equivalent in the old repo):
- `pipeline/concept.py` + `scaffolds/concept.md`
- `pipeline/keyframes.py` (Nano Banana)
- `pipeline/shots.py` + `scaffolds/shot_agent.md` (the Shot Agent)
- `pipeline/voice.py` (separate TTS)
- `pipeline/editor.py` + `scaffolds/editor.md` + `editor_render/` (Editor Agent + Remotion service)
- Cost ceiling enforcement (new `pipeline/budget.py` or extend tracing)

---

## Models (behind MODEL_ROUTER — one-line swaps)
- Concept + Director: `gemini-3.1-pro` (multimodal, sees photos AND videos; 3.5 Pro when it ships)
- Translator / per-shot prompt composition: `claude-sonnet-4-6` (instruction-following under scaffold)
- Shot judge: cheaper Gemini Flash that accepts video — VERIFY at build
- Keyframe image: Nano Banana 2 — VERIFY at build
- Video generation: Seedance 2.0 image-to-video, per shot, audio OFF — VERIFY at build
- TTS: fal — VERIFY current endpoint
- Editor render: Remotion (Node-based, separate service in `editor_render/`)
- Editor Agent (plan): Claude or Gemini — choose at build based on edit-plan JSON quality

NOTE: Gemini "Omni" is a video GENERATION model (Seedance competitor). Do NOT use it for the
Director or Concept brain. Use Gemini Pro for understanding/direction; Seedance for generation.

---

## Build order  _(HISTORICAL — the build is complete; all stages below shipped. Kept for context;
## ongoing work is decision-driven, see `DECISIONS.md` D1–D51.)_
Follow `docs/Specs/SPEC_multigen_rearchitecture.md` step by step. Suggested order:
0. Pre-build spikes (above). Block on findings.
1. Repo scaffolding: copy patterns from `_reference/` (tracing, agent loop, errors, run-dir).
2. Cost ceiling enforcement (`pipeline/budget.py`) — wire it in early; check on every paid call.
3. Triage (port from `_reference/` mostly as-is).
4. Concept stage + scaffold + acceptance check.
5. Director stage (multimodal, on the loop) + scaffold + acceptance check.
6. Enhance stage (port from `_reference/`).
7. Keyframes stage (Nano Banana) + acceptance check. New build.
8. Shots stage (Shot Agent: generate + judge + retry + flag) + scaffold + acceptance check.
9. Voice stage (TTS) + acceptance check.
10. Editor stage (Editor Agent + Remotion render service) + scaffold + acceptance check.
11. Review stage (final assembled video, mechanical checks only).
12. Wire `run.py` end-to-end + replay + ARCHITECTURE.md updated.
13. End-to-end test on Carol_Dog with real keys; iterate.

Run acceptance checks after EACH stage. Do not write all of them then run once.

---

## Conventions
- Agent only where dynamic reasoning earns its cost. Else plain Python.
- Every tool has a one-line "NOT for:" in its docstring.
- Scaffolds are thin entry files; deep prompt detail in `scaffolds/references/`.
- Model choices behind `MODEL_ROUTER` — never hard-coded.
- Secrets from `.env` only. Never committed.
- Stubs work when keys are absent — pipeline runs end-to-end offline.
- Verify every external surface (model ids, endpoints, API shapes) against LIVE docs at build,
  not training-data recall. Especially: Seedance endpoints, Gemini thinking tokens, Nano Banana API,
  Remotion CLI/render API, fal TTS endpoint.
- The answer to any failure is one directory away. Optimize for that.

---

## Quality bar reminders (because they're easy to forget)
- "Would a small-business owner believe this brings them more traffic?" — NOT "looks non-AI."
- Authenticity beats polish.
- Generic montage is the failure mode. POV > polish. The Concept stage exists because of this.
- Cost ceiling is $5; over budget = halt + flag. Treat as a hard constraint.
- Per-shot judge MUST flag failures, not silently accept.
