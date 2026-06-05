# WHY — the project, in plain language

## What this project is
A pipeline that turns a local small business's raw assets (a handful of mediocre phone photos,
maybe a short video, maybe no logo, a one-line description) into ONE finished 25–30s vertical
video ad. Target customers: local service AND product businesses — hair salon, nails, dog daycare,
cleaning, bakery, restaurant, florist.

## The hard problem
The hard part is not video generation. The hard part is the SCARCITY problem: the business hands
you almost nothing usable, and the system has to act as a marketing director who makes something
professional anyway. Every product in this space (Higgsfield, HeyGen, LTX Studio) solves a different
problem — they assume clean inputs. This one is designed around bad inputs from local businesses
with no production experience.

## The quality bar (this is the single most important sentence)
> "Would a small-business owner believe this brings them more traffic?"

NOT "is this indistinguishable from human production." NOT "does this look non-AI." The bar is
local-business outcome — phone calls, walk-ins, bookings. That means:
- Hook in the first ~1.5–3s (stop the scroll)
- Clear value prop, with a specific POV — not generic
- Load-bearing practical info (price, hours, location, booking CTA)
- Not embarrassing / not amateur / not unmistakably AI

## What's different about how we approach it
- Pipeline of LLM "thinking" stages (concept, director, translator, etc.), with deterministic
  Python plumbing between them. Agents only where dynamic reasoning earns its cost.
- The same recurring split everywhere: ONE stage decides intent/judgment (concept, director),
  ANOTHER renders execution/craft (translator, editor). Don't break this pattern.
- Salvage every asset — triage produces a per-asset REMEDIATION plan, not a pass/fail verdict.
  Bad inputs are the rule, not the exception.
- The output bar is local-traffic, not viral DTC. We borrow heavily from Motion's Meta ad data
  ($14B/yr spend) as a STRONG PRIOR, but it's not gospel — operator (you) verdicts calibrate over
  time. Don't blindly chase DTC ROAS optimization; that game is volume + variant testing, which a
  one-ad SMB cannot play.

## Why this is being rebuilt now (the architectural reversal)
The previous architecture was a single Seedance multi-shot generation per ad. That was the right
call at the time — simpler, faster to ship, no timing handoff, Seedance can technically do
multi-shot. Real testing showed two ceilings:
1. The failure rate of a 15s single-call generation is too high.
2. Polish (real transitions, captions, editing rhythm) is capped — you can't prompt your way to
   CapCut-quality.

So the architecture moved to MULTI-GEN: one Seedance call per shot, each judged + retried,
assembled by a real editor (Remotion). Both decisions — single-call then, multi-gen now — were
correct in context. Capture both in ARCHITECTURE.md so this isn't re-litigated.

## What we are NOT trying to be
- We are NOT Higgsfield. They take a clean product URL and make a polished ad. Different problem.
- We are NOT HeyGen. They make talking-head avatar videos. Different format.
- We are NOT a viral-DTC volume tester. That game requires shipping 50 variants and letting Meta
  pick a winner; our SMB customer ships one or two ads.
- We are NOT making "indistinguishable from human" video. We are making "drives the phone to ring."

## The single most important creative principle
**Authenticity beats polish.** Across Motion's data and our own runs, lower-fi authentic execution
outperforms glossy production. A real phone-shot moment of the actual owner usually beats a polished
generated montage. Defaulting to "cinematic commercial" gloss is exactly what makes output read as
AI and as an ad. Bias toward real, specific, slightly imperfect.

## And the single biggest creative trap
**Generic montage / "wallpaper" output.** When the model picks the safest, most defensible
treatment, you get an ad that could be any business in the category. The Concept stage exists
specifically to name and reject the cliché before the Director sees the brief, so the cliché can't
be the fallback. POV > polish.
