import {
  AbsoluteFill, Audio, Img, OffthreadVideo, Sequence, interpolate,
  staticFile, useCurrentFrame, useVideoConfig,
} from 'remotion';
import {Caption, EditPlan, Segment} from './types';
import {CARD_TEMPLATES} from './templates/Cards';
import {KineticCaption} from './KineticCaption';
import {OverlayLayer} from './Overlay';

const CROSSFADE_S = 0.4;
const TRANS_S = 0.35; // non-crossfade entrance length (dip/slide/whip/zoom)

// --- segment renderers -----------------------------------------------------

const VideoSegment: React.FC<{src: string; trim?: [number, number]; rate?: number}> = ({src, trim, rate}) => {
  const {fps} = useVideoConfig();
  return (
    <OffthreadVideo
      src={staticFile(src)}
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

// Card segment -> the template library (templates/Cards.tsx). Photo-backed + palette accents.
const CardSegment: React.FC<{template?: string; text?: string; bg?: string; palette?: string[]; animation?: string}> =
  ({template, text, bg, palette, animation}) => {
  const Card = CARD_TEMPLATES[template ?? 'EndCard'] ?? CARD_TEMPLATES.EndCard;
  return <Card text={text} bg={bg} palette={palette} animation={animation} />;
};

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

const withMotion = (seg: Segment, dur: number, child: React.ReactNode) => {
  if (seg.motion === 'punch_in') return <PunchIn durationInFrames={dur}>{child}</PunchIn>;
  if (seg.motion === 'parallax') return <Pan durationInFrames={dur}>{child}</Pan>;
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
      return <CardSegment template={seg.card_template} text={seg.card_text} bg={seg.bg_src}
                          palette={palette} animation={seg.card_animation} />;
  }
};

// --- caption track ---------------------------------------------------------

const CaptionTrack: React.FC<{captions: Caption[]}> = ({captions}) => {
  const frame = useCurrentFrame();
  const {fps} = useVideoConfig();
  const t = frame / fps;
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
    const isXfade = seg.transition_in === 'crossfade';
    const from = isXfade ? Math.max(0, cursor - xfadeFrames) : cursor;
    cursor = from + dur;
    return {seg, from, dur, isXfade};
  });

  return (
    <AbsoluteFill style={{backgroundColor: '#000'}}>
      {placed.map(({seg, from, dur, isXfade}, i) => (
        <Sequence key={i} from={from} durationInFrames={dur} name={`${seg.type}-${i}`}>
          <TransitionWrap kind={i === 0 ? 'hard_cut' : seg.transition_in}
                          frames={isXfade ? xfadeFrames : Math.round(TRANS_S * fps)}>
            {renderSegment(seg, dur, plan.palette)}
          </TransitionWrap>
          {seg.overlay && <OverlayLayer overlay={seg.overlay} palette={plan.palette} />}
        </Sequence>
      ))}
      {plan.words && plan.words.length > 0
        ? <KineticCaption words={plan.words} style={plan.caption_style} palette={plan.palette} />
        : (plan.captions && plan.captions.length > 0 ? <CaptionTrack captions={plan.captions} /> : null)}
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
    default: // hard_cut
      return <AbsoluteFill>{children}</AbsoluteFill>;
  }
};
