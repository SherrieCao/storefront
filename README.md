# Storefront

**Turn a local business's messy photos and clips into one polished video ad — ready to post.**

> *Mom-and-pop shops, posting with confidence.*

A few mediocre phone photos, maybe a short clip, and a one-line description of the business go in.
**One finished, well-edited 25–30s vertical ad comes out** — in about **ten minutes**, for about
**two dollars**.

---

## The problem

Most small and local businesses are invisible online. They know they *should* post — but making good
social content is a job in itself, so they post rarely, or never, and when they do it gets **under 500
views**. They can't afford a marketing team or an agency. And the tools that exist assume things a corner
salon doesn't have: a product feed, brand assets, a script, a clean studio shoot.

So the bakery, the nail studio, the dog daycare, the auto shop compete for attention against companies
with hundred-person growth teams — with four blurry photos and a sentence.

## What Storefront does

You hand it the little you have — a folder of real photos and clips, and a one-line brief. It hands back
**one polished vertical ad that shows off the best of your business**: concepted, shot, scored, voiced,
edited, and quality-checked. No production experience required, no marketing budget.

- **~10 minutes**, end to end.
- **~$2 per ad** (hard-capped at $5 — it will never quietly run up a bill).
- **Ready to post** to Reels / TikTok / Shorts.

## Enhanced, not generated — *this is the promise*

Every shot in the ad comes from a service or product the business **actually provides**. The footage is
**enhanced** — upscaled, relit, recomposed, cut to rhythm — **never fabricated**. Nothing is conjured out
of thin air:

- **No stock, no AI-invented scenes.** Generated motion is always anchored to one of *your* real photos.
- **No invented claims, prices, hours, phone numbers, or handles** — if you didn't provide it, it's not
  on screen.
- The creative angle is anchored on the business's **real Google reviews** — a named stylist, a signature
  service, the thing customers actually rave about.

It's *your* storefront, made to look its best — not a glossy fake of someone else's.

## The goal

Give small-business owners the confidence to show up online — a real social presence **without paying for
a marketing team**. The bar isn't "does this look professional." It's the only one an owner cares about:

> **"Would this bring me more traffic?"**

Phone calls. Walk-ins. Bookings. If the ad brings in **10× the traffic**, the job is done.

---

## Under the hood

The rest of this is for the technically curious. The short version: it behaves like a seasoned marketing
director who can make something great out of almost nothing — and it's engineered so the output never
feels generic or fake.

### Streamlined, end to end

One command runs the whole studio. Each stage is a focused "thinking" step with deterministic plumbing
between them. The arrows below are the *happy path* — but it is **not a one-pass cascade**: most stages
are self-correcting loops, and two stages can send the work *back upstream* (see [The loops](#the-loops--its-not-a-one-pass-cascade)).

```
 triage → concept → director → enhance → keyframes → shots → music → voice → editor → review
   │         │         │          │          │         │       │       │        │        │
  local    pick the   plan the   fix the   consistent per-shot beat-   TTS +   structured frames
   CV +    bold idea, shots +    weak real  start    generate matched +word-    edit plan + mech
 salvage   kill the   script +   photos     frames   + JUDGE  music   stamps   + Remotion checks
  plan     clichés    pacing                          + retry         (synced) render
```

- **triage** — local computer vision (no LLM): a per-asset *salvage* plan, not a pass/fail. Surfaces the
  biggest gap ("you have no logo").
- **concept** — multimodal; *sees* the real photos/videos. Brainstorms, **names and rejects the category
  clichés**, self-selects the boldest *feasible* idea, anchored on a real Google-review detail.
- **director** — *executes* that concept: mixed shot plan, script, pacing, perspective — each shot
  anchored to a real asset.
- **enhance** — targeted remediation of the weak photos.
- **keyframes** — a *consistent set* of per-shot start frames that hold visual coherence.
- **shots** — generate each shot silently, then **a separate model judges the rendered clip as video** →
  approve, or retry up to 3× with the judge's notes baked in → flag after 3 fails. **Never silently
  ships a least-bad shot.** Each approved clip gets a **de-AI pass** (phone-camera-realistic keyframes +
  ffmpeg grain/vignette/jitter, color untouched) so generated shots read phone-captured, not glossy-AI.
- **music / voice** — a beat-matched royalty-free bed; one TTS take with word-level timestamps that drive
  caption sync. The voice is **routed to fit the business** (gender / region / vertical), and is **never
  sped up past 1.2×** — if the video is too short for the script, the editor escalates instead of crushing.
- **editor** — an Editor Agent emits a structured JSON edit plan; **Remotion** renders it deterministically
  (designed cards, kinetic captions, motion, before→after reveals with a bold BEFORE/AFTER stamp).
- **review** — frames + mechanical checks on the finished video; the final creative call is the operator's.

### The core bet: split judgment from execution

The reason the output doesn't feel generic. **Every stage with a "what" and a "how" is split across two
separate minds** — one decides *intent*, another renders *craft*. Fusing them selects for safe, average
output; the split is the quality lever.

| Decides intent (judgment) | Renders execution (craft) |
|---|---|
| **Concept** — the bold, feasible idea; kills clichés | **Director** — turns it into a shot plan + script |
| **Director** — intent per shot, pacing | **Shot Agent** — composes each per-shot prompt |
| **Director** — `pacing` / `editing_feel` | **Editor Agent** — a concrete edit plan |
| **Editor Agent** — the plan | **Remotion** — deterministic render to mp4 |

### The loops — it's not a one-pass cascade

If the split is *who* decides, the **loops** are *how the system refuses to ship its first draft.* Almost
every "thinking" stage produces → gets critiqued by a separate mind (or a hard rule) → regenerates with
that feedback baked in — bounded, then **accept-best + flag** (nothing fails silently). And two stages
escalate *backwards* when they can't fix things locally.

```
        ┌── critic loop ──┐   ┌── critic loop + 7 guards ──┐   ┌─ judge loop (per shot) ─┐
triage → │    CONCEPT     │ → │         DIRECTOR           │ → │   SHOTS                  │ → music → voice → EDITOR → review
        └─────────────────┘   └────────────────────────────┘   └──────────────────────────┘                      │
                  ▲                      ▲                                                                          │
                  └─ re-roll concept ◀───┘ (brief fails review)        voice won't fit ≤1.2× → re-plan ◀───────────┘
```

- **Concept critic loop** — produces a concept, a *separate-mind* reviewer scores 4 lenses (audience /
  attention / SMB-fit / appeal); fail → regenerate with the critique; bounded retries → keep the best.
- **Director critic loop** — same produce→review→regenerate, **plus 7 deterministic guards** that bind in
  *code* (pacing, moodboard reuse, clip reuse, voice coverage, **script-fits-the-video**, asset-grounded
  perspective, **before/after adjacency**) — because prose guidance in a prompt doesn't reliably hold.
- **Concept ↔ Director escalation** — if the brief still fails its reviewer after the Director's own
  retries, the work is re-rolled at the *Concept* stage with the Director's feedback (the cliché can't be
  the fallback).
- **Shot Agent loop** — per shot: generate → a *different* model judges the rendered clip as video →
  approve, or retry ≤3 with the judge's reasons fed forward → flag after 3. Never silently ships a
  least-bad shot.
- **Voice-fit escalation** — the editor checks the *realized* video against the script; if the voice
  can't fit at ≤1.2×, it sends the plan **back to the Director** (add beats / cut script), then synthesizes
  fill assets as a last resort — rather than crushing the audio. Bounded; ships at the cap + a flag if
  truly impossible.

Bounded retries + accept-best + flags everywhere mean the loops *raise* the floor without ever hanging or
silently degrading. (The editor's own critic loop exists too but is currently single-pass for latency —
its deterministic realizers do the guaranteeing.)

### Why you can trust the output

- **Grounded, never fabricated** — real review detail, real-photo-anchored motion, no invented
  contact/claims (fabricated handles/URLs are stripped), before/after only when the operator states it.
- **A separate-mind quality judge per shot** — generate → judge → retry → flag; nothing fails silently.
- **Deterministic guards that bind in code** (pacing, asset reuse, voice coverage, asset-grounded
  perspective, before/after adjacency, **script-fits-the-video**) — because prose in a prompt doesn't
  reliably hold. When a guard can't be satisfied in-plan, the editor **escalates back to the Director**
  rather than shipping a compromise.
- **Phone-captured, not glossy-AI** — the de-AI pass shifts generated footage toward real phone aesthetics
  (practical light, grain, micro-jitter) so it blends with the real clips instead of "popping" as AI.
- **Authenticity over polish** — a real, specific, slightly imperfect moment beats a glossy generated
  montage, and reads as a *real business* rather than an ad.

### Observability + cost

Every run writes a complete, replayable record under `runs/NNNN/` — `00_triage.json`, `01_concept.json`,
`02_creative_brief.json`, `04_keyframes/`, `05_shots/`, `07_edit_plan.json`, `09_output/final.mp4`, plus
`REASONING.md`, `trace.jsonl` (every LLM/tool call: full prompt, raw response, cost), `lineage.json`, and
`COST.md`.

- **A hard $5 cost ceiling per run**, tracked live — halt and flag if exceeded. Creative stages never see
  cost; money is a silent safety net, not a creative constraint.
- **Replay any run from any stage** — `python run.py --replay NNNN --from-step editor` reuses cached
  upstream artifacts, so re-editing is cheap.

### The stack

| Role | Model / tool |
|---|---|
| Concept + Director brain (multimodal) | Gemini 3.x Pro |
| Per-shot prompt craft / structured JSON | Claude Sonnet |
| Per-shot video judge | Gemini Flash (accepts video) |
| Keyframes | Nano Banana 2 (fal) |
| Per-shot video generation | Seedance 2.0 image-to-video (fal) |
| Voice | ElevenLabs v3 (fal) — word-level timestamps |
| Music | curated royalty-free library + librosa beat grid |
| Render | Remotion (Node) — deterministic, CapCut-grade |
| Business research | Google Places (New) — real reviews |

Every model sits behind a one-line `MODEL_ROUTER` swap. Agents are used **only where dynamic reasoning
earns its cost**; plain Python everywhere else. The whole pipeline runs end-to-end offline with stubbed
providers, so there's always a working skeleton.

### Run it

```bash
python3.11 -m venv .venv && ./.venv/bin/pip install -r requirements.txt
cd editor_render && npm install && cd ..          # render service

cp .env.example .env   # add ANTHROPIC_API_KEY, GEMINI_API_KEY, FAL_KEY, GOOGLE_PLACES_API_KEY

# one ad, straight through
./.venv/bin/python run.py --business hue_salon --input inputs/hue_salon --no-gate

# re-edit without re-generating shots
./.venv/bin/python run.py --replay 0001 --from-step editor
```

The input contract is deliberately tiny — a folder of assets plus `brief.json`:

```json
{ "name": "Hue Hair Salon", "location": "San Francisco, CA",
  "brief": "San Francisco's top color specialist — balayage, highlights, fresh cuts.",

  "address": "1712 Fillmore St, SF",   "phone": "(415) 555-0123",
  "social": "@huehair",                "booking_url": "huehair.com/book" }
```

Only `name`, `location`, and `brief` are required. The optional `address` / `phone` / `social` /
`booking_url` appear on the closing brand card — operator-provided only, never fabricated.

---

<sub>Architecture and design decisions live in `CLAUDE.md`, `WHY.md`, and `DECISIONS.md`. Active research
build; model IDs and endpoints are verified against live docs at build time, not training recall.</sub>
