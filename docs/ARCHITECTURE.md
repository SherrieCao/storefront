# Architecture — Multi-Generation Pipeline

> Current through **DECISIONS D51**. `DECISIONS.md` is the running source of truth; this file is the
> snapshot. Target ad length **25–30s**.

## The pipeline
```
triage → concept → director → enhance → keyframes → shots → music → voice → editor → review
```
- **triage** — local CV, no LLM. Per-asset salvage/remediation plan; before/after gate (operator brief
  text OR `before_`/`after_` filename prefixes — never pixel inference, D11/D37); per-asset `role`
  tagging; gap-ask. Frozen `input_snapshot/`.
- **concept** — Gemini multimodal. Diverge, name + reject clichés, anchor on a real Google-review detail
  (cached per business), self-select one bold, feasible, **appealing** concept (the appeal gate, D41).
- **director** — Gemini multimodal, on the agent loop. EXECUTES the concept into MIXED SEGMENTS
  (`seedance_shot` / `real_clip` / `moodboard` / `card`), **25–30s**, the spoken script (may carry ≤1
  performed-emotion audio tag, D48), `pacing`/`editing_feel`, and a mandatory hook. Plans creatively;
  never sees cost. **Deterministic guards run inside its self-correct loop** (prose doesn't bind; code
  does): pacing, moodboard reuse, clip reuse, voice coverage, **voice length** (script must fit the video
  ≤1.2×, D50), perspective (asset-grounded, deprioritize 1st-person), **before/after adjacency** (a
  before beat must be immediately followed by its after, D43). Accept-best across bounded retries.
- **enhance** — local Pillow relight + fal upscale on recoverable photos (feeds keyframes/moodboard).
- **keyframes** — Nano Banana 2, **concurrent**. seedance_shot start frames (generate / generate_from_real)
  + moodboard composition frames. Holds cross-shot visual coherence; forbids on-screen text. **De-AI
  Layer 1 (D47):** phone-camera-realism prompt (mixed light, deep DoF, blown highlights, *not* polished;
  color kept true, not muted); `generate_from_real` PRESERVES the real photo (doesn't "polish" it); a
  `before`-role beat is shown as the PLAIN raw photo (`preserve_before`, no composition).
- **shots** — Shot Agent, **concurrent** (Seedance ~2 min/gen). Per `seedance_shot`: compose single-shot
  prompt → Seedance image-to-video (silent) → Gemini Flash judges the clip → approve or retry ≤3 with
  judge feedback → flag after 3 (never silent). **De-AI Layer 2 (D47):** each approved clip gets one
  ffmpeg pass — temporal grain + vignette + softness + handheld micro-jitter (color untouched, so vivid
  results stay vivid); the raw clip is kept for A/B.
- **music** — a **curated royalty-free LIBRARY pick** matched to pacing/energy (D26) + a librosa beat grid
  `{music_path, bpm, beats[]}`. Not generation ($0). Runs ∥ keyframes/shots so the editor can snap cuts.
  Stubs offline.
- **voice** — one ElevenLabs **v3** call (fal): voiceover + word-level timestamps (drive kinetic captions).
  **Business-aware voice routing** (`_select_voice`, gender > region > vertical) picks one of 8 voices +
  a per-voice stability. Performed-emotion audio tags (`[excited]`/`[laughs softly]`, ≤1, whitelisted,
  stripped from captions; body-sounds banned — D48).
- **editor** — Editor Agent emits an EDIT PLAN (order / durations / transitions / motion / overlays /
  caption style / card animation). **The editing-reviewer critic loop is DISABLED (D42, single-pass)** —
  the latency wasn't worth it; deterministic realizers do the guaranteeing instead: `_realize_before_after`
  (BEFORE/AFTER **bold kinetic stamp** + whip reveal, D43/D48), `_realize_ending` (always a designed
  branded info card from `brief.json`, D38), `_fit_to_total`, `_snap_to_beats`. **Remotion** renders the
  plan → mp4: kinetic word-by-word captions (`bold_center` / `minimal_lower` / `handwritten` /
  `sparse_keyword`), animated cards, beat-snapped cuts, a ducked music bed, transitions {hard_cut,
  crossfade, dip_to_black, slide, whip, zoom, speed_ramp_in, scale_reveal, light_leak}, video motion
  {punch_in, parallax, drift, scale_breath, handheld_jitter}, overlays {lower_third, badge, stamp}.
  The voiceover is atempo-fit to the video, **hard-capped at 1.2×** (D51 — never crushed). Overlay text
  with fabricated contact (a handle/URL/phone not in `brief.json`) is dropped (D44).
- **review** — mechanical checks only on the FINAL video (playable, duration, not black). Per-shot quality
  already judged in `shots`; creative judgment is the operator's (`06_operator_review.json`).

## The loops (it is NOT a one-pass cascade)
The arrows above are the happy path. Almost every thinking stage is a produce → separate-mind critique →
regenerate loop (bounded by `MAX_CREATIVE_RETRIES`/`MAX_SHOT_RETRIES`, then **accept-best + flag** — never
silent), and two stages escalate *backwards*:
- **Concept critic loop** — produce → 4-lens reviewer (`reviewers.review`) → regenerate.
- **Director critic loop** — produce → reviewer **+ 7 deterministic guards** (pacing / moodboard reuse /
  clip reuse / voice coverage / voice length D50 / perspective / before-after adjacency) → regenerate.
- **Concept ↔ Director escalation** — brief still fails review after the Director's retries → re-roll the
  *Concept* with feedback (`CREATIVE_MAX_ESCALATIONS`).
- **Shot Agent loop** — per shot: generate → a *separate* Gemini-Flash judge → retry ≤3 → flag.
- **Voice-fit escalation** (D50/D51) — editor checks the realized video vs the script → re-plan via the
  Director (→ one-shot asset-gen) → re-voice, bounded (`EDITOR_MAX_ESCALATIONS`); ship at the 1.2× cap +
  flag if impossible.
- (The editor's own critic loop exists but is single-pass / disabled for latency — D42; deterministic
  realizers guarantee the output instead.)

## Concurrency + thread safety (DECISIONS D45)
Stages that don't depend on each other run in parallel: **enhance ∥ concept+director**, **music ∥
keyframes+shots**, and keyframes/shots fan out internally. The `Run` object is thread-safe (a single
`RLock` guards `trace`/`log`/`reason`/`add_cost`/`cost_total`) so parallel stages can't interleave
`trace.jsonl` or lose a cost update (which could slip the ceiling).

## Voice-fit escalation — the voice is never crushed (DECISIONS D50/D51)
The voice paces from the script; if the realized video is too short to fit it at ≤1.2×, the editor does
NOT silently speed it up. It **escalates**: re-plan via the Director (add beats from unused assets / cut
the script — bounded, `EDITOR_MAX_ESCALATIONS`), then a one-shot synthetic asset-gen if genuinely
asset-starved, then ship at the 1.2× cap + a `voice_fit` flag. D50 is the cheap plan-time guard (script
vs *planned* beats); D51 is the realized-level backstop (what `_fit_to_total`'s clip clamps shrink below
plan). One shared `VOICE_FIT_RATIO` (1.2) + `SPOKEN_WPS`.

## The recurring split (the quality lever — DECISIONS D2)
Judgment and execution live in different minds:
concept (judgment) → director (executes concept) → per-shot composer / Shot Agent (per-shot craft) ;
director's `pacing`/`editing_feel` (intent) → Editor Agent (edit plan) → Remotion (deterministic render).
The editor escalates a too-short video back to the Director rather than inventing beats — beat authorship
stays with the Director.

## The Seedance/Remotion bright line (DECISIONS D21)
Seedance generates ONLY new footage (`seedance_shot`, always anchored to a real photo). Remotion does
EVERYTHING else — moodboard composition+motion, real-clip trimming, cards, transitions, captions, audio
mux. The only generated audio is none of the spine — voice is TTS, music is a library file.

## Cost ceiling (DECISIONS D6/D19)
$5 hard ceiling per run as a SILENT safety net: `tracing.Run.cost_total()` + `budget.check_ceiling()`
before every paid call (now thread-safe). A breach halts + finalizes a clean partial
(`halted_cost_ceiling`, `COST.md`). The Director never reasons about cost. Typical full run ~$1.3–$4 (0
seedance is cheapest; each seedance shot + retries is the main cost).

## Robustness notes
- **Non-ASCII filenames (D49/D49b):** SMB phones produce emoji/accented filenames; `llm.ascii_safe_path`
  copies to an ASCII temp before any fal **or** Gemini upload (the filename rides an HTTP header).
- **External calls** (fal/Gemini) lack per-call retry/timeout — a transient blip can fail a run; replay
  from the failed step. (Open hardening item.)

## The architectural reversal — single-call → multi-gen (read before re-litigating)
The old pipeline (`_reference/old_pipeline/`) generated the whole ad in ONE Seedance multi-shot call —
simpler, faster to ship, no assembly handoff. Real testing exposed two ceilings: (1) a full single
generation fails too often with no way to salvage one bad beat, and (2) you can't prompt your way to
clean transitions/captions/editing-rhythm/non-robotic voice. So we moved to one Seedance call PER SHOT
(judged + retried + flagged), Nano Banana keyframes for consistency, dedicated TTS voice, and a real
Remotion editor. Both decisions were correct in context (DECISIONS D1). No `SINGLE_CALL_MODE` flag — the
old path is not ported (D18); the fallback is to run `_reference/old_pipeline/` directly.

## Models (behind `MODEL_ROUTER`)
- Concept + Director: `gemini-3.1-pro-preview` (multimodal; Director runs the agent loop at thinking_level "high")
- Per-shot composer + Editor Agent + reviewers: `claude-sonnet-4-6`
- Shot judge: `gemini-3-flash-preview` (cheap, accepts video)
- Keyframes: `fal-ai/nano-banana-2` (+ `/edit`)
- Shots: `bytedance/seedance-2.0/image-to-video` (audio off), text-to-video fallback
- Voice: `fal-ai/elevenlabs/tts/eleven-v3` (word timestamps; supersedes MiniMax)
- Music: curated royalty-free library (no model) + librosa
- Editor render: Remotion (local CLI; `editor_render/`)

## Observability (DECISIONS D16)
Every run dir: numbered artifacts per stage, `trace.jsonl` (full prompt/response/thinking/cost),
`REASONING.md` (per-stage narrative incl. Shot Agent attempts + Editor rationale), `lineage.json`
(concept→plan→keyframes→shots→voice→edit→output→verdict), `COST.md` (per-stage vs ceiling),
`flagged_shots.json`, `creative_flags.json` (unresolved reviews / voice-fit). Replay:
`python run.py --replay NNNN --from-step <stage>` (cached upstream artifacts reused).
