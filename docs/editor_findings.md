# Spike findings — Editor render service (Remotion)

**Date:** 2026-05-28 · **Status:** VERIFIED LIVE — a real mixed-segment mp4 was rendered offline and
inspected. Remotion is **confirmed** as the editor (D7).

## What was proven
Stood up a minimal real Remotion project in `editor_render/` and rendered a vertical 9:16 ad from an
**edit-plan props object** containing three of the four segment types + audio + captions:
- `seedance_shot` → the spike's Seedance clip via `<OffthreadVideo>` (objectFit cover). ✓
- `moodboard` → Nano Banana keyframe animated with a **Ken Burns push** (`interpolate` on `scale`). ✓
- `card` → `OfferBanner` template (colored bg + bold centered text). ✓
- **Burned-in captions** time-synced (`useCurrentFrame`/fps), styled, bottom-anchored. ✓
- **Audio mux** — voiceover.mp3 via `<Audio>`; output has an AAC stream. ✓
- **crossfade** transition between segments via overlap + opacity fade (`<FadeWrap>`). ✓

Render: `npx remotion render Ad out/final.mp4` → `8.26s`, h264+aac, 246 frames @30fps, ~10.7MB.
Frames extracted and visually verified (clip+caption, card, moodboard).

## Verified API / environment facts (Remotion 4.0.468, current)
- **Versions pinned exact** across `remotion` + `@remotion/cli` (`4.0.468`); React 19. **Node ≥18**
  (have v20.20.1).
- Entry point `src/index.ts` → `registerRoot(RemotionRoot)`. Root holds `<Composition id="Ad" …>`.
- **Dynamic duration:** `calculateMetadata={({props}) => ({durationInFrames, fps, width, height})}`
  computes length from the plan at render time — exactly what variable-length (15–30s) ads need.
  `durationInFrames = round((Σ seg durations − Σ crossfade overlaps) × fps)`.
- **Input props = the edit plan:** pass via `--props=./07_edit_plan.json` (JSON file path) or
  `--props='{...}'`. defaultProps holds a sample plan for Studio/dev.
- **Use `<OffthreadVideo>`** (not `<Video>`) for clips during render. Trim real clips with
  `startFrom`/`endAt` (frames). Local assets via `staticFile()` from `editor_render/public/`.
  → the Editor stage must stage clips/keyframes/voiceover into `public/` (or a render input dir)
  before invoking the CLI.
- Sequential layout via `<Sequence from durationInFrames>`; crossfade = start the incoming sequence
  `xfadeFrames` early and fade its opacity in.

## Remotion vs JSON-API alternatives (D7 confirmation)
Remotion gives full React/programmatic control: custom `<MoodboardSegment>`, a growable card
template library, frame-accurate Ken Burns/parallax, and a clear Phase-2 path to kinetic typography
/ motion graphics / beat-sync. JSON-API renderers (JSON2Video, Rendervid) are faster to start but
cap exactly at the motion-graphics ceiling we know we'll need, and switching editors mid-project is
painful. The spike confirms Remotion's effort is justified — the mixed-segment render was
straightforward and the polish ceiling is ours to raise. **Decision stands: Remotion.**

## Build implications (carried into Phase 4d)
- The spike files ARE the renderer skeleton: `package.json`, `tsconfig.json`, `src/{index.ts,
  Root.tsx,AdComposition.tsx,types.ts}`. Phase 4d grows them: the **card template library**
  (`EndCard`, `PriceTag`, `LocationPin`, `OfferBanner`, `Title`) and a polished `<MoodboardSegment>`.
- `editor.py` writes `07_edit_plan.json`, stages assets into `editor_render/public/` (or a per-run
  input dir), runs `npx remotion render Ad <out> --props=<plan>`, returns the mp4 path.
- v0 = local Remotion CLI. Upgrade path (documented, not built): `@remotion/lambda` for parallel
  cloud renders / SSR (`@remotion/renderer renderMedia()`), behind the same `editor.py` interface.
- `node_modules/` and `editor_render/out/` are gitignored.
