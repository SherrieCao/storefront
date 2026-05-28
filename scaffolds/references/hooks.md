# Hooks Reference — the opening ~3 seconds (condensed from Motion's hook data)

> The first ~3s is the single highest-leverage surface of the ad. The `design_hook` tool encodes
> these rules; this doc is the shared reference for the Director and Translator.

## The non-negotiables
- **Cut the dead first second.** No logo, no slow zoom on a static shot, no establishing wide.
  Put motion in the first ~8 frames: a zoom, a swipe, a hand or subject entering frame, or a face.
- **A human face/subject in frame one beats product-only** for thumb-stop (~30% lift) — use one
  when the assets allow.
- **On-screen text in the first second** (a problem/claim) is a strong hook element — it's added in post,
  so pair it with motion/a face, since the generator itself renders no text.
- **The hook line uses a SPECIFIC detail from the brief** (location, price, owner, a quirk) — never
  generic. ("Right off the 101" beats "the best care.")

## Mechanics (pick one; concrete beats clever for local SMBs)
Concrete / offer-driven (PRIMARY for SMBs — these convert):
- **newness** — "Just opened…", "New this week…"
- **price** — a concrete number / anchor ("walk-ins from $35")
- **urgency** — "this week only", limited slots
- **offer** — a specific deal

Big-brand mechanics (SECONDARY — use when there's a real reason):
- **confession** — "I almost didn't…"; **bold_claim**; **relatability** ("if you're a … you know");
  **contrast** (the wrong way vs the right way); **curiosity** (open a loop the ad closes).

## How it lands in the ad
- The Director calls `design_hook` (mandatory), may re-call until strong, then **shot 1 + the opening
  spoken line realize the hook**. The Translator makes the first labeled shot a thumb-stop and opens
  on the hook line (in quotes), with no dead first second.
- The hook is recorded as a discrete `hook` object in the brief — so it's inspectable and (later)
  cheap to A/B as variants against the same ad body.
