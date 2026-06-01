# Storefront — AI that turns a local business's scraps into one ad that actually works

> A handful of mediocre phone photos, maybe a short clip, maybe no logo, and a one-line
> description go in. **One finished 15–30s vertical video ad comes out** — concepted, directed,
> shot, scored, voiced, edited, and quality-checked. Built for the businesses that need advertising
> most and can do it least: the salon, the bakery, the dog daycare, the nail studio down the street.

The bar isn't "looks AI-made or not." The bar is the only one a small-business owner cares about:

> **"Would a small-business owner believe this brings them more traffic?"**

Phone calls. Walk-ins. Bookings. That's the product.

---

## Why this is hard (and why most tools don't solve it)

The hard part is **not** video generation. It's the **scarcity problem**: a local business hands you
almost nothing usable, and the system has to behave like a seasoned marketing director who makes
something professional *anyway*.

Every other tool in the space assumes clean inputs — a product URL, a script, brand assets, a
talking head. Real local businesses don't have those. They have four blurry photos and a sentence.
**This system is designed around bad inputs**, because bad inputs are the rule, not the exception.

Two failure modes dominate this category, and the whole architecture is organized to defeat them:

- **Generic montage / "wallpaper."** When a model picks the safest treatment, you get an ad that
  could be *any* business in the category. Forgettable. The pipeline names and *rejects* the cliché
  before the creative director ever sees the brief — so the cliché can't be the fallback.
- **The AI tell.** Cinematic gloss, metronomic cuts, tricolon scripts, a sudden "and now the ad
  part." **Authenticity beats polish** — a real, slightly imperfect, specific moment outperforms a
  glossy generated montage every time. The system is biased toward real, lo-fi, and specific.

---

## The core architectural bet: split judgment from execution

This is the idea the whole system is built on, and the reason the output doesn't feel generic.

**Every stage that has a "what" and a "how" is split across two separate minds.** One decides
*intent and judgment*; another renders *execution and craft*. They are never the same call.

| Decides intent (judgment) | Renders execution (craft) |
|---|---|
| **Concept** — picks the bold, feasible idea; kills the clichés | **Director** — executes that concept into a shot plan + script |
| **Director** — intent per shot, pacing, editing feel | **Shot Agent / Translator** — composes each per-shot prompt |
| **Director** — `pacing` / `editing_feel` | **Editor Agent** — a concrete, structured edit plan |
| **Editor Agent** — the plan | **Remotion** — deterministic render to mp4 |

Fusing judgment and execution selects for *safe* output — the model hedges toward the defensible
average. **The split is the quality lever.** It's enforced everywhere, on purpose.

---

## The pipeline

```
 triage → concept → director → enhance → keyframes → shots → music → voice → editor → review
   │         │         │          │          │         │       │       │        │        │
  local    Gemini    Gemini      fal      Nano     per-shot  beat-  fal TTS  Editor   frames
   CV     multimodal multimodal upscale  Banana 2  generate  matched +word-   Agent +  + mech
 salvage  ideation   directs    /relight consistent +JUDGE   library  stamps  Remotion checks
  plan    + kills      the      real      keyframes +retry            (sync           render
          clichés    concept   assets               3× /flag          captions)
```

- **triage** — local computer vision, no LLM. A per-asset *salvage* plan (upscale / sharpen /
  relight), not a pass/fail. Surfaces the highest-value gap ("you have no logo").
- **concept** — Gemini, *multimodal* (sees the real photos and videos). Brainstorms freely, names and
  rejects the category clichés, self-selects the boldest **feasible** idea. Anchored on a **real
  customer-review detail** pulled live from Google.
- **director** — Gemini, multimodal, on an agent loop. *Executes* the chosen concept: plans mixed
  segments, writes the script, sets pacing and editing feel, anchors each shot to a real asset.
- **enhance** — targeted remediation of the weak real photos.
- **keyframes** — Nano Banana 2. A *consistent set* of per-shot start frames that hold visual
  coherence across independently generated shots.
- **shots** — the Shot Agent. Per shot: compose the prompt → generate (silent) → **a separate model
  judges the rendered clip as video** → approve, or retry up to 3× with the judge's feedback baked
  in → flag to the operator after 3 failures. **Never silently accepts a least-bad shot.**
- **music** — picks a beat-matched bed from a curated royalty-free library; cuts snap to its beat grid.
- **voice** — one TTS call returning word-level timestamps that drive caption sync and shot timing.
- **editor** — the Editor Agent emits a structured JSON edit plan (video / audio / caption / card
  tracks); **Remotion** renders it deterministically. Designed cards, kinetic captions, motion.
- **review** — frames + mechanical checks on the finished video (playable, right length, not black).
  Creative judgment already happened per-shot; the final creative verdict is the operator's.

---

## What makes the output good (the quality machinery)

**Critic loops with a separate mind.** Concept, Director, and Editor each run a *produce → review →
regenerate* loop where the reviewer is a different model with a different system prompt, prompted to
be skeptical. Feedback is baked verbatim into the next attempt. Bounded retries, then accept-best +
flag — nothing fails silently.

**Deterministic guards that actually bind.** Prose guidance in a prompt doesn't reliably bind, so the
rules that matter are enforced in code, inside the Director's self-correct loop:

- **Pacing** — too-slow average beat → regenerate with more, shorter beats.
- **Moodboard reuse** — the same photo in two moodboards reads as repetitive → cap and diversify.
- **Voice coverage** — the voiceover must actually *cover* the video, not end halfway.
- **Perspective** — *first-person narration over footage someone else clearly shot reads as fake.*
  The Director declares how the assets were shot and writes in the matching person; first-person is
  reserved for genuinely self-shot footage. Default to second/third person.

**Grounded in reality, never fabricated.**

- The concept anchors on a **real, specific detail** distilled from the business's actual Google
  reviews (named staff, a signature service, a quirk) — cached per business, ranked by specificity.
- Generated motion is always anchored to a **real photo** — never pure text-to-video stock.
- Practical info (name, location, hours, booking) is real or it isn't shown. No invented phone
  numbers, URLs, or handles. No invented first-person customer quotes.
- A **before/after** framing is only unlocked when the operator says so in plain language — never
  inferred.

**Cross-run freshness.** A per-business history log steers each new run away from repeating the last
one's concept, angle, review detail, voice, and ending — so a business's feed doesn't go same-y.

---

## Observability is not optional

Every run writes a complete, replayable record:

```
runs/NNNN/
  00_triage.json        per-asset remediation plan + the gap to ask the owner about
  01_concept.json       rejected clichés + the chosen concept + feasibility
  02_creative_brief.json the director's format, shot plan, script, pacing, perspective
  04_keyframes/         the consistent per-shot start frames
  05_shots/             approved clips + per-attempt thumbnails + judge logs
  06_voice/  07_edit_plan.json  08_assembly/  09_output/final.mp4
  REASONING.md          how every agent decided (narrative + raw thinking trace)
  trace.jsonl           every LLM/tool call: full prompt, raw response, thinking, cost
  lineage.json          concept → plan → keyframes → shots → edit → output → verdict
  COST.md               per-stage cost + total + ceiling status
```

- **Every LLM call** logs its full prompt, raw response, thinking trace, and cost.
- **A hard $5 cost ceiling per run**, tracked in real time — halt and flag if exceeded. The creative
  stages never see cost; money is a silent safety net, not a creative constraint.
- **Replay** any run from any stage: `python run.py --replay NNNN --from-step editor` reuses cached
  upstream artifacts. Iterating on the edit is cheap and fast; iterating on the concept is one flag.

A caveat the codebase takes seriously: an agent's stated reasoning is its *account*, not ground
truth. **The output is the verdict.** Reasoning traces are for iteration, not for trusting a
clean-sounding justification.

---

## The stack

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

Every model sits behind a one-line `MODEL_ROUTER` swap. Python orchestrates; agents are used **only
where dynamic reasoning earns its cost**, plain Python everywhere else. The whole pipeline runs
end-to-end offline with stubbed providers, so there's always a working skeleton.

---

## Running it

```bash
python3.11 -m venv .venv && ./.venv/bin/pip install -r requirements.txt
# editor render service
cd editor_render && npm install && cd ..

# secrets (never committed)
cp .env.example .env   # add ANTHROPIC_API_KEY, GEMINI_API_KEY, FAL_KEY, GOOGLE_PLACES_API_KEY

# one ad, straight through
./.venv/bin/python run.py --business hue_salon --input inputs/hue_salon --no-gate

# re-edit without re-generating shots
./.venv/bin/python run.py --replay 0001 --from-step editor
```

**Input contract** is deliberately tiny — a folder of assets plus `brief.json`:

```json
{ "name": "Hue Hair Salon", "location": "San Francisco, CA",
  "brief": "San Francisco's top color specialist — balayage, highlights, fresh cuts." }
```

---

## The point

Small businesses are where most people work and most communities live, and they are the worst-served
by modern advertising tooling — it's built for brands with budgets, agencies, and clean assets. The
result is that the corner salon competes for attention against companies with a hundred-person growth
team.

This is an attempt to collapse that gap: to let a local owner hand over the little they have and get
back something that earns attention and **changes how they advocate for their own business** — not a
glossy fake, but a real, specific, scroll-stopping ad that makes the phone ring.

---

<sub>Architecture and design decisions live in `CLAUDE.md`, `WHY.md`, and `DECISIONS.md`. This is an
active research build; model IDs and endpoints are verified against live docs at build time, not
training recall.</sub>
