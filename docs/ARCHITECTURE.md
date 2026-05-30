# Architecture — Multi-Generation Pipeline

## The pipeline
```
triage → concept → director → enhance → keyframes → shots → voice → editor → review
```
- **triage** — local CV. Per-asset salvage/remediation plan; before/after gate (text-only); gap-ask.
- **concept** — Gemini multimodal. Diverge, reject clichés, anchor on a real review detail, self-select
  one bold feasible concept.
- **director** — Gemini multimodal, on the agent loop. EXECUTES the concept into a sequence of MIXED
  SEGMENTS (`seedance_shot` / `real_clip` / `moodboard` / `card`), total length 15–30s, script,
  `pacing`/`editing_feel` (feed the Editor), and a mandatory hook. Plans creatively; never sees cost.
- **enhance** — local Pillow relight + fal upscale on recoverable photos (feeds keyframes/moodboard).
- **keyframes** — Nano Banana 2. seedance_shot start frames (generate / generate_from_real) + moodboard
  composition frames. Holds visual coherence; forbids on-screen text.
- **shots** — Shot Agent. Per `seedance_shot`: compose single-shot prompt → Seedance image-to-video
  (silent) → Gemini Flash judges the clip → approve or retry ≤3 with judge feedback → flag after 3.
  Runs shots concurrently (Seedance is ~2 min/gen).
- **voice** — one MiniMax TTS call (fal). Clean voiceover + locally-derived per-line caption timing.
- **editor** — Editor Agent emits an EDIT PLAN (order / durations / transitions / caption style / card
  animation), **critiqued by an editing reviewer loop** (`plan_timeline⟳`: first-0.5s grab / rhythm /
  contrast / payoff); Remotion (`editor_render/`) renders the plan → final mp4. Assembles all four
  segment types with **kinetic word-by-word captions** + **animated cards**. **Deferred to Phase 2
  (built only when the current polish proves insufficient):** music bed + beat-synced cuts (Beatoven +
  librosa), lower-thirds / stickers / broader motion graphics, multi-style kinetic typography. See
  DECISIONS D24/D25.
- **review** — mechanical checks only on the FINAL video (playable, duration, not black). Per-shot
  quality already judged in `shots`; creative judgment is the operator's (06_operator_review.json).

## THE ARCHITECTURAL REVERSAL — single-call → multi-gen (read before re-litigating)
This repo reverses the previous single-call decision. **Both decisions were correct in context.**

**Why single-call was right then.** The old pipeline (`_reference/old_pipeline/`) generated the whole
15s ad in ONE Seedance 2.0 multi-shot reference-to-video call — visuals, cuts, ambient, and native
voiceover in a single pass. It was simpler, faster to ship, had no timing/assembly handoff, and got us
to a working end-to-end system. At the time, "the Seedance prompt IS the product" was the right focus.

**Why multi-gen is right now.** Real testing exposed two hard ceilings:
1. **Failure rate** — a full 15s single generation fails too often (artifacts, warping, drift), with
   no way to salvage one bad beat without re-rolling the whole ad.
2. **Polish ceiling** — you cannot prompt your way to clean transitions, burned-in captions, editing
   rhythm, or a non-robotic voice. The native voice sounds robotic; there is no real edit control.

So we moved to: one Seedance call PER SHOT (each judged + retried + flagged), Nano Banana keyframes for
cross-shot consistency, a dedicated TTS voice, and a real Remotion editor that assembles everything.
This costs more and adds latency and a real assembly stage — all worth it because the previous
architecture had a quality ceiling we had hit. (See `WHY.md`, `DECISIONS.md` D1.)

**Spec correction (recorded so it isn't re-introduced):** the main spec's migration section says to
keep the old single-call path behind a `SINGLE_CALL_MODE` feature flag. We did NOT do this — per
operator decision, the new repo does not port single-call code (D18 forbids importing old code, and a
half-ported flag is exactly the entangled middle ground we're avoiding). The fallback, if ever needed,
is to run the old `_reference/old_pipeline/` pipeline directly. There is no `SINGLE_CALL_MODE`.

## The recurring split (the quality lever — DECISIONS D2)
Judgment and execution live in different minds:
concept (judgment) → director (executes concept) → per-shot composer / Shot Agent (per-shot craft) ;
director's `pacing`/`editing_feel` (intent) → Editor Agent (edit plan) → Remotion (deterministic render).

## The Seedance/Remotion bright line (DECISIONS D21)
Seedance generates ONLY new footage (`seedance_shot`). Remotion does EVERYTHING else — moodboard
composition+motion, real-clip trimming, cards, transitions, captions, audio mux. No fuzzy middle.

## Cost ceiling (DECISIONS D6/D19)
$5 hard ceiling per run as a SILENT safety net: `tracing.Run.cost_total()` + `budget.check_ceiling()`
before every paid call. If a paid call would breach it, the run halts and finalizes a clean partial
(meta status `halted_cost_ceiling`, `COST.md`). The Director never reasons about cost.

## Models (behind MODEL_ROUTER — all VERIFIED LIVE, see docs/*_findings.md)
- Concept + Director: `gemini-3.1-pro-preview` (multimodal)
- Per-shot composer + Editor Agent: `claude-sonnet-4-6`
- Shot judge: `gemini-3-flash-preview` (cheap, accepts video)
- Keyframes: `fal-ai/nano-banana-2` (+ `/edit`)
- Shots: `bytedance/seedance-2.0/image-to-video` (audio off), text-to-video fallback
- Voice: `fal-ai/minimax/speech-02-hd`
- Editor render: Remotion 4.0.468 (local CLI; Lambda is the documented upgrade path)

## Observability (DECISIONS D16)
Every run dir: numbered artifacts per stage, `trace.jsonl` (full prompt/response/thinking/cost),
`REASONING.md` (per-stage narrative incl. Shot Agent attempts + Editor rationale), `lineage.json`
(concept→plan→keyframes→shots→voice→edit→output→verdict), `COST.md` (per-stage vs ceiling),
`flagged_shots.json`. Replay: `python run.py --replay NNNN --from-step <stage>`.
