# Ending Agent — design notes (DON'T BUILD YET)

Captured from SPEC_anti_ai_tells.md §10. The research validates a dedicated ending designer (mirrors
the Hook Designer). **Do not build until the Director's ending flexibility (Batch 1, §2b / `ending_type`)
has run for 5–10 real runs** and we've seen whether the Director picks varied endings on its own or
just defaults to `card`. If it defaults, a dedicated agent is worth it; if it varies well, skip it.

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
