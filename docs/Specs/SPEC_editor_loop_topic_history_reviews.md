# Spec — Editor Critic Loop + Topic History + Review Expansion

> Three changes that work together: the editor gets a real critic loop (matching the existing
> concept⟳/director⟳ pattern), a per-business history log tracks past concepts/review-details
> so the pipeline explores fresh angles, and Google Places review sourcing doubles from ~5 to
> ~8-10 unique reviews via a two-sort-mode fetch + caching.

---

## Part A — Editor Critic Loop

### Current state (confirm at build)
The editing_reviewer.md scaffold exists and is wired via reviewers.py. Confirm whether the
editor currently runs as: (a) a single pass with no retry, or (b) already looped. If (b),
this part is "improve the lenses" not "add the loop."

### The loop (if not already looped)
Mirror the concept⟳/director⟳ pattern exactly:
1. Editor Agent produces an edit plan (JSON timeline)
2. Editing reviewer (Claude, editing_reviewer.md) scores it on its lenses
3. If fail → Editor regenerates with `prior_attempt_failed_review.fix_these` feedback
4. Up to `MAX_CREATIVE_RETRIES` attempts (currently 3)
5. Accept-best + flag if none pass

Wire using the same `reviewers.review(run, "edit", plan, ctx)` call pattern used by
concept/director/hook. Log every attempt + verdict in REASONING.md and trace.jsonl.

### Lens updates (editing_reviewer.md)
Whether or not the loop is new, update the lenses. Current lenses: grab, rhythm, contrast,
payoff, motion_graphics. Add/update:

- **template_feel** (NEW, from anti-AI spec): are cuts metronomic (same length ±0.3s across
  3+ adjacent segments)? Are captions tracking every word identically? Are flashy transitions
  used on 3+ cuts? Does the ending feel like "and now the ad part"? YES to 2+ = FAIL.
- **rhythm** (UPDATE): change from "consistently brisk" to "deliberately VARIED — brisk overall
  but with intentional holds and punches. Adjacent beats must differ by ≥0.5s. Metronomic = FAIL
  even if fast."
- **ending** (NEW): does the ending type match the ad's voice_style and concept? A card for
  every social_native/influencer_pov ad = template tell. Is the ending_type varied across runs
  for the same business? (Requires topic history — see Part B.)

Add `template_feel` and `ending` to the scores object in the reviewer output schema.

---

## Part B — Topic History Log (per-business concept freshness)

### File: `inputs/<business>/history.json`
Created after first run, updated after every run. Schema:

```json
{
  "business": "Conway_Nail_Bar",
  "runs": [
    {
      "run_id": "0012",
      "date": "2026-05-28",
      "concept_name": "The 101 commuter's nail ritual",
      "concept_summary": "Anchor on the highway-adjacent convenience...",
      "review_detail_used": "right off the 101",
      "format": "demo",
      "voice_style": "social_native",
      "ending_type": "card",
      "operator_verdict": "ship"
    }
  ],
  "review_details_used": ["right off the 101", "insane color selection"],
  "concepts_used": ["The 101 commuter's nail ritual", "Conway's color wall"],
  "formats_used": ["demo", "behind_the_scenes"],
  "ending_types_used": ["card", "card"]
}
```

### Writer: update history after each run
In `run.py` (or `lineage.py`), after finalization: read `01_concept.json` + `02_creative_brief.json`
+ `06_operator_review.json`, append to `inputs/<business>/history.json`. Create the file on
first run. Use the business name from `brief.json` or `--business` to locate the input dir.

### Reader: inject history into Concept stage
In `concept.py`, when loading the scaffold + building the user message: read `history.json`
(if it exists) and inject a summary block:

```
## Previous runs for this business (de-weight these)
Concepts already explored: [list]
Review details already used: [list]
Formats used: [list]
Ending types used: [list]

Explore a DIFFERENT angle. Anchor on a DIFFERENT review detail. Try a format and ending type
you haven't used yet. Repetition across runs is a creative failure — unless the operator
explicitly requests a repeat in the brief.

If a previous concept got verdict "ship" and the operator wants more of that angle, they'll
say so in the brief. Otherwise, assume fresh territory.
```

### Also inject into Director (lighter touch)
The Director doesn't need the full history, but should see: "Ending types used in past runs:
[card, card, card]. Vary." — so it (or the Ending Agent) doesn't default to card every time.

### Don't inject into Translator/Editor/Shot Agent
They don't make concept-level decisions. Keep the history injection to Concept + Director only.

---

## Part C — Review Expansion (two-sort + cache + tracking)

### C1. Two-sort fetch in research.py
Currently `research_business` (or whatever calls Google Places) fetches reviews once with the
default sort (`most_relevant`). Change to:

1. Fetch with `reviews_sort=most_relevant` → up to 5 reviews
2. Fetch with `reviews_sort=newest` → up to 5 reviews
3. De-duplicate by review author + text (some may overlap)
4. Also fetch the **review summary** if using the Places API (New) — the `reviewSummary` field
   (GA since May 2025) gives a condensed synthesis across ALL reviews, not just the 5 returned.
   This captures themes the 5-review limit misses.
5. Return the union (~8-10 unique reviews + the summary)

### C2. Cache per business
Write the fetched reviews to `inputs/<business>/reviews_cache.json`:

```json
{
  "business": "Conway_Nail_Bar",
  "place_id": "ChIJ...",
  "fetched_at": "2026-05-28T14:00:00Z",
  "review_summary": "Customers praise the wide color selection and convenient location...",
  "reviews": [
    {
      "author": "Jane D.",
      "rating": 5,
      "text": "Love this place! Right off the 101, amazing color selection...",
      "time": "2026-04-15",
      "sort_source": "most_relevant"
    }
  ]
}
```

On subsequent runs: if `reviews_cache.json` exists AND is less than 7 days old, skip the API
call and use the cache. If older than 7 days, re-fetch (reviews change). The 7-day TTL is a
config constant (`REVIEW_CACHE_TTL_DAYS = 7`).

### C3. Track which review details have been used
`history.json` (Part B) already tracks `review_details_used`. The Concept stage reads this
and de-weights used details. The `_distill_system` in research.py should pass ALL reviews to
the distiller, and the distiller should return multiple candidate anchor details (not just one),
ranked by specificity. The Concept stage then picks one that hasn't been used before.

Change the distiller output from a single detail to:
```json
{
  "anchor_candidates": [
    {"detail": "right off the 101", "why_specific": "location-based, verifiable"},
    {"detail": "insane gel color wall — 200+ options", "why_specific": "product differentiator"},
    {"detail": "appointment with Lily, she remembered my last color", "why_specific": "named staff, personal"}
  ],
  "review_summary_themes": ["convenience", "color variety", "personal service"]
}
```

The Concept stage receives all candidates + the used-detail history, and picks accordingly.

### C4. Operator-supplied reviews (optional, future)
Note in the schema: `reviews_cache.json` can also contain an `"operator_supplied"` array of
reviews the business owner provides directly (screenshots transcribed, copy-pasted favorites).
These are never cached/expired and always available. Don't build the ingestion UI — just
document the schema so an operator can manually add entries.

---

## Implementation order
1. **C1-C2** (review expansion + cache) — smallest, unblocks the rest. Test: two calls return
   more reviews than one; cache works; re-fetch after TTL.
2. **B** (history log) — depends on having runs to log. Wire the writer first (updates after
   each run), then the reader (inject into Concept). Test: after 2 runs, third run's Concept
   sees the history and picks a different angle.
3. **C3** (multi-candidate distiller) — refine the research stage to return ranked candidates.
   Test: Concept picks an unused detail when history shows previous ones used.
4. **A** (editor critic loop) — independent of B/C. Wire the loop + update lenses. Test: trace
   shows editor attempts + reviewer verdicts; a deliberately bad plan gets rejected and improved.

---

## Acceptance checks
1. **Reviews:** a fetch for a real business returns ~8-10 reviews (not 5); `reviews_cache.json`
   is written; a second run within 7 days uses the cache (no API call in trace).
2. **History:** after 2+ runs for the same business, `history.json` exists with both runs logged;
   the third run's Concept scaffold includes the de-weighting injection.
3. **Distiller:** returns 3+ anchor candidates ranked by specificity (not just one).
4. **Concept freshness:** a third run for the same business demonstrably picks a different angle
   and different review detail than the first two (visible in `01_concept.json`).
5. **Editor loop:** trace shows editor plan → reviewer verdict → retry (if failed) → accept.
   A deliberately weak plan (e.g. all same-length cuts) gets template_feel FAIL and is revised.
6. **Ending variety:** over 3+ runs for the same business, at least 2 different ending_types
   are used (visible in history.json).

## Guardrails
- History is per-business, stored in `inputs/<business>/`, NOT in `runs/`. It persists across
  runs. Don't accidentally put it in the run directory (which is per-run).
- Review cache TTL is a config constant, not hard-coded.
- The de-weighting is a SOFT steer, not a hard ban. If the operator's brief says "do another
  angle like run 0012," respect it. The Concept scaffold should say "unless the brief requests
  a repeat."
- The distiller's multi-candidate output is backward-compatible — if downstream code currently
  reads a single `detail` field, alias it to `anchor_candidates[0].detail`.
- Editor loop uses the EXISTING `reviewers.review()` infrastructure — no parallel reviewer path.
