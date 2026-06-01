# Ending Agent — BUILT (gate met: Director defaulted to `card` 3/3 runs)

Captured from SPEC_anti_ai_tells.md §10. **Gate met early:** runs 0013/0015/0016 all defaulted to a
`card` ending despite full `ending_type` flexibility, so the dedicated ending designer was built. It is
`design_ending` — a Director tool mirroring `design_hook` (`pipeline/agent/tools.py`): the Director
calls it after planning segments + voice_style, gets `{ending_type, on_screen_text, caption_suggestion,
why}`, realizes it in the LAST segment (card / lower_third overlay / bare visual for callback/tag/
linger), and copies it into the brief's `ending` object. Lean: one Gemini call, no internal reviewer
(the creative reviewer already checks the ending). Watch whether endings now actually vary across runs.

Design (for the future spec):
- **Pattern:** a tool the Director calls (like `design_hook`) — or a separate post-Director stage —
  that designs the final ~2–3s.
- **Five ending types:** `card`, `overlay`, `callback`, `tag`, `linger` (see creative_director.md §2b).
- **Selection criteria:** `voice_style` + concept drive the choice. `social_native`/`influencer_pov` →
  softer endings (overlay/callback/tag/linger); `local_ad` → `card` is fine.
- **Invariant:** the ending must deliver the conversion info SOMEHOW (on-screen card/overlay, or
  deliberately in caption/bio for callback/tag). The card-every-time pattern is a structural tell that
  "the video is an ad."
- **Discrete object:** like the hook, the ending is its own object in the brief — inspectable,
  iterable, separately A/B-testable.

Current state (Batch 1): `ending_type` is a Director output field; `overlay` endings render via the
existing `lower_third` overlay; `callback`/`tag`/`linger` leave the info off-screen (caption/bio). No
dedicated agent yet.
