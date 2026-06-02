import {
  AbsoluteFill, Audio, Img, OffthreadVideo, Sequence, interpolate, random,
  staticFile, useCurrentFrame, useVideoConfig,
} from 'remotion';
import {Caption, EditPlan, Segment} from './types';
import {Card} from './templates/Cards';
import {KineticCaption} from './KineticCaption';
import {OverlayLayer} from './Overlay';

const CROSSFADE_S = 0.3; // Batch C: 0.4->0.3, snappier. MUST match pipeline/editor.py _CROSSFADE_S
const TRANS_S = 0.35; // non-overlap entrance length (dip/slide/whip/zoom/speed_ramp_in/light_leak)
// Overlap transitions reveal over the prior segment (need the overlap window); the rest animate
// within the segment's own window. MUST match pipeline/editor.py _OVERLAP_TRANSITIONS.
const OVERLAP_TRANSITIONS = ['crossfade', 'scale_reveal'];

// --- segment renderers -----------------------------------------------------

const VideoSegment: React.FC<{src: string; trim?: [number, number]; rate?: number}> = ({src, trim, rate}) => {
  const {fps} = useVideoConfig();
  return (
    <OffthreadVideo
      src={staticFile(src)}
      muted              // the ad's only audio is the VO + music bed — never a clip's own/original sound
      playbackRate={rate ?? 1}
      startFrom={trim ? Math.round(trim[0] * fps) : undefined}
      endAt={trim ? Math.round(trim[1] * fps) : undefined}
      style={{width: '100%', height: '100%', objectFit: 'cover'}}
    />
  );
};

// Moodboard: Nano Banana composition keyframe animated by Remotion (a punchier Ken Burns push).
const MoodboardSegment: React.FC<{src: string; durationInFrames: number}> = ({src, durationInFrames}) => {
  const frame = useCurrentFrame();
  const scale = interpolate(frame, [0, durationInFrames], [1.06, 1.28], {extrapolateRight: 'clamp'});
  return (
    <AbsoluteFill style={{backgroundColor: '#000', overflow: 'hidden'}}>
      <Img src={staticFile(src)} style={{width: '100%', height: '100%', objectFit: 'cover', transform: `scale(${scale})`}} />
    </AbsoluteFill>
  );
};

// Card segment -> the card system (templates/Cards.tsx): a card STYLE rendering 4 typographic tiers.
const CardSegment: React.FC<{style?: string; tiers?: any; template?: string; text?: string;
  bg?: string; palette?: string[]; animation?: string}> = (p) => <Card {...p} />;

// Punch-in: a slow scale push across the segment (energy on otherwise-static or locked footage).
const PunchIn: React.FC<{durationInFrames: number; children: React.ReactNode}> = ({durationInFrames, children}) => {
  const frame = useCurrentFrame();
  const scale = interpolate(frame, [0, durationInFrames], [1.0, 1.14], {extrapolateRight: 'clamp'});
  return <AbsoluteFill style={{transform: `scale(${scale})`, overflow: 'hidden'}}>{children}</AbsoluteFill>;
};

// Parallax: a slow horizontal drift (over-scaled so edges never show) — a single-plane pan that reads
// as motion on otherwise-locked footage.
const Pan: React.FC<{durationInFrames: number; children: React.ReactNode}> = ({durationInFrames, children}) => {
  const frame = useCurrentFrame();
  const x = interpolate(frame, [0, durationInFrames], [-4, 4], {extrapolateRight: 'clamp'});
  return <AbsoluteFill style={{transform: `scale(1.14) translateX(${x}%)`, overflow: 'hidden'}}>{children}</AbsoluteFill>;
};

// Handheld jitter: subtle per-frame micro-movement (deterministic via Remotion's seeded random, so the
// render is reproducible) — makes too-perfectly-locked footage read as real phone footage, not AI.
const Jitter: React.FC<{children: React.ReactNode}> = ({children}) => {
  const frame = useCurrentFrame();
  const A = 1.6; // px amplitude
  const x = (random(`jx${frame}`) - 0.5) * 2 * A;
  const y = (random(`jy${frame}`) - 0.5) * 2 * A;
  const rot = (random(`jr${frame}`) - 0.5) * 0.6; // deg
  return <AbsoluteFill style={{transform: `scale(1.04) translate(${x}px, ${y}px) rotate(${rot}deg)`, overflow: 'hidden'}}>{children}</AbsoluteFill>;
};

// Scale-breath (Batch C): a slow 1.0 -> 1.03 -> 1.0 pulse across the clip — a barely-there "breathing"
// that keeps a held shot or moodboard alive without reading as a Ken Burns push.
const ScaleBreath: React.FC<{durationInFrames: number; children: React.ReactNode}> = ({durationInFrames, children}) => {
  const frame = useCurrentFrame();
  const scale = interpolate(frame, [0, durationInFrames / 2, durationInFrames], [1.0, 1.03, 1.0],
    {extrapolateRight: 'clamp'});
  return <AbsoluteFill style={{transform: `scale(${scale})`, overflow: 'hidden'}}>{children}</AbsoluteFill>;
};

// Drift (Batch C): a slow diagonal pan (~5%, over-scaled so edges never show) — distinct from parallax's
// horizontal-only move; reads as a gentle camera drift on locked footage.
const Drift: React.FC<{durationInFrames: number; children: React.ReactNode}> = ({durationInFrames, children}) => {
  const frame = useCurrentFrame();
  const x = interpolate(frame, [0, durationInFrames], [-2.5, 2.5], {extrapolateRight: 'clamp'});
  const y = interpolate(frame, [0, durationInFrames], [-2.5, 2.5], {extrapolateRight: 'clamp'});
  return <AbsoluteFill style={{transform: `scale(1.1) translate(${x}%, ${y}%)`, overflow: 'hidden'}}>{children}</AbsoluteFill>;
};

const withMotion = (seg: Segment, dur: number, child: React.ReactNode) => {
  if (seg.motion === 'punch_in') return <PunchIn durationInFrames={dur}>{child}</PunchIn>;
  if (seg.motion === 'parallax') return <Pan durationInFrames={dur}>{child}</Pan>;
  if (seg.motion === 'handheld_jitter') return <Jitter>{child}</Jitter>;
  if (seg.motion === 'scale_breath') return <ScaleBreath durationInFrames={dur}>{child}</ScaleBreath>;
  if (seg.motion === 'drift') return <Drift durationInFrames={dur}>{child}</Drift>;
  return child;
};

const renderSegment = (seg: Segment, durationInFrames: number, palette?: string[]) => {
  switch (seg.type) {
    case 'seedance_shot':
    case 'real_clip':
      return withMotion(seg, durationInFrames,
        <VideoSegment src={seg.src!} trim={seg.trim_s} rate={seg.playback_rate} />);
    case 'moodboard':
      return <MoodboardSegment src={seg.src!} durationInFrames={durationInFrames} />;
    case 'card':
      return <CardSegment style={seg.card_style} tiers={seg.card_tiers} template={seg.card_template}
                          text={seg.card_text} bg={seg.bg_src} palette={palette} animation={seg.card_animation} />;
  }
};

// --- caption track ---------------------------------------------------------

const CaptionTrack: React.FC<{captions: Caption[]; cutoffS?: number | null}> = ({captions, cutoffS}) => {
  const frame = useCurrentFrame();
  const {fps} = useVideoConfig();
  const t = frame / fps;
  if (cutoffS != null && t >= cutoffS) return null;        // clean closing card — no caption over it
  const active = captions.find((c) => t >= c.start_s && t < c.end_s);
  if (!active) return null;
  return (
    <AbsoluteFill style={{justifyContent: 'flex-end', alignItems: 'center', paddingBottom: 220}}>
      <div style={{maxWidth: '86%', textAlign: 'center', color: 'white', fontSize: 58, fontWeight: 700,
                   lineHeight: 1.2, fontFamily: 'Helvetica, Arial, sans-serif',
                   textShadow: '0 2px 12px rgba(0,0,0,0.85)', backgroundColor: 'rgba(0,0,0,0.35)',
                   padding: '16px 28px', borderRadius: 18}}>
        {active.text}
      </div>
    </AbsoluteFill>
  );
};

// --- composition -----------------------------------------------------------

export const AdComposition: React.FC<{plan: EditPlan}> = ({plan}) => {
  const {fps} = useVideoConfig();
  const xfadeFrames = Math.round(CROSSFADE_S * fps);

  // Lay out sequences; crossfade segments start xfadeFrames before the previous ends (overlap). Other
  // transitions animate the entrance WITHIN the segment's own window (no overlap).
  let cursor = 0;
  const placed = plan.segments.map((seg) => {
    const dur = Math.round(seg.duration_s * fps);
    const isOverlap = OVERLAP_TRANSITIONS.includes(seg.transition_in ?? '');
    const from = isOverlap ? Math.max(0, cursor - xfadeFrames) : cursor;
    cursor = from + dur;
    return {seg, from, dur, isOverlap};
  });

  return (
    <AbsoluteFill style={{backgroundColor: '#000'}}>
      {placed.map(({seg, from, dur, isOverlap}, i) => (
        <Sequence key={i} from={from} durationInFrames={dur} name={`${seg.type}-${i}`}>
          <TransitionWrap kind={i === 0 ? 'hard_cut' : seg.transition_in}
                          frames={isOverlap ? xfadeFrames : Math.round(TRANS_S * fps)}>
            {renderSegment(seg, dur, plan.palette)}
          </TransitionWrap>
          {seg.overlay && <OverlayLayer overlay={seg.overlay} palette={plan.palette} />}
        </Sequence>
      ))}
      {plan.words && plan.words.length > 0
        ? <KineticCaption words={plan.words} style={plan.caption_style} palette={plan.palette} cutoffS={plan.caption_cutoff_s} />
        : (plan.captions && plan.captions.length > 0 ? <CaptionTrack captions={plan.captions} cutoffS={plan.caption_cutoff_s} /> : null)}
      {plan.music && <Audio src={staticFile(plan.music.src)} volume={plan.music.gain ?? 0.18} />}
      {plan.audio && <Audio src={staticFile(plan.audio.src)} volume={plan.audio.gain ?? 1} />}
    </AbsoluteFill>
  );
};

// Segment entrance transitions (D4). crossfade overlaps the prior segment (handled in layout); the
// rest animate within the segment's own window: dip_to_black (fade up from black), slide (in from the
// right), whip (fast slide + motion blur), zoom (push out of a scale). hard_cut = instant.
const TransitionWrap: React.FC<{kind?: string; frames: number; children: React.ReactNode}> =
  ({kind, frames, children}) => {
  const frame = useCurrentFrame();
  const f = Math.max(1, frames);
  const p = interpolate(frame, [0, f], [0, 1], {extrapolateRight: 'clamp'});
  switch (kind) {
    case 'crossfade':
      return <AbsoluteFill style={{opacity: p}}>{children}</AbsoluteFill>;
    case 'dip_to_black':
      return (
        <AbsoluteFill>{children}
          <AbsoluteFill style={{backgroundColor: '#000', opacity: interpolate(p, [0, 1], [1, 0])}} />
        </AbsoluteFill>
      );
    case 'slide':
      return <AbsoluteFill style={{transform: `translateX(${interpolate(p, [0, 1], [100, 0])}%)`}}>{children}</AbsoluteFill>;
    case 'whip':
      return (
        <AbsoluteFill style={{transform: `translateX(${interpolate(p, [0, 1], [55, 0])}%)`,
          filter: `blur(${interpolate(p, [0, 1], [14, 0])}px)`, opacity: interpolate(p, [0, 0.4], [0.4, 1], {extrapolateRight: 'clamp'})}}>
          {children}
        </AbsoluteFill>
      );
    case 'zoom':
      return <AbsoluteFill style={{transform: `scale(${interpolate(p, [0, 1], [1.45, 1])})`, opacity: p}}>{children}</AbsoluteFill>;
    case 'scale_reveal':
      // Overlap transition: the incoming reveals over the prior segment, scaling 1.3 -> 1.0 as it fades up.
      return <AbsoluteFill style={{transform: `scale(${interpolate(p, [0, 1], [1.3, 1])})`, opacity: p}}>{children}</AbsoluteFill>;
    case 'speed_ramp_in': {
      // CSS approximation of a speed ramp: the clip rushes in (over-scaled + motion blur) and snaps to
      // rest in the first third of the window. (OffthreadVideo's playbackRate is static, so a true
      // temporal 2x->1x ramp isn't available — this gives the same "whoosh into place" read.)
      const pr = interpolate(frame, [0, f * 0.5], [0, 1], {extrapolateRight: 'clamp'});
      return (
        <AbsoluteFill style={{transform: `scale(${interpolate(pr, [0, 1], [1.12, 1])})`,
          filter: `blur(${interpolate(pr, [0, 1], [8, 0])}px)`}}>
          {children}
        </AbsoluteFill>
      );
    }
    case 'light_leak':
      // The segment is fully present; an amber gradient sweeps across once and fades out (a flourish —
      // capped to one per ad in pipeline/editor.py).
      return (
        <AbsoluteFill>{children}
          <AbsoluteFill style={{
            background: 'linear-gradient(105deg, transparent 30%, rgba(255,176,87,0.55) 50%, transparent 70%)',
            transform: `translateX(${interpolate(p, [0, 1], [-120, 120])}%)`,
            opacity: interpolate(p, [0, 0.5, 1], [0, 0.9, 0], {extrapolateRight: 'clamp'}),
            mixBlendMode: 'screen', pointerEvents: 'none'}} />
        </AbsoluteFill>
      );
    default: // hard_cut
      return <AbsoluteFill>{children}</AbsoluteFill>;
  }
};
