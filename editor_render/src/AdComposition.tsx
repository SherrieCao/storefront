import {
  AbsoluteFill, Audio, Img, OffthreadVideo, Sequence, interpolate,
  staticFile, useCurrentFrame, useVideoConfig,
} from 'remotion';
import {Caption, EditPlan, Segment} from './types';
import {CARD_TEMPLATES} from './templates/Cards';

const CROSSFADE_S = 0.4;

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
const CardSegment: React.FC<{template?: string; text?: string; bg?: string; palette?: string[]}> =
  ({template, text, bg, palette}) => {
  const Card = CARD_TEMPLATES[template ?? 'EndCard'] ?? CARD_TEMPLATES.EndCard;
  return <Card text={text} bg={bg} palette={palette} />;
};

const renderSegment = (seg: Segment, durationInFrames: number, palette?: string[]) => {
  switch (seg.type) {
    case 'seedance_shot':
    case 'real_clip':
      return <VideoSegment src={seg.src!} trim={seg.trim_s} rate={seg.playback_rate} />;
    case 'moodboard':
      return <MoodboardSegment src={seg.src!} durationInFrames={durationInFrames} />;
    case 'card':
      return <CardSegment template={seg.card_template} text={seg.card_text} bg={seg.bg_src} palette={palette} />;
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

  // Lay out sequences; crossfade segments start xfadeFrames before the previous ends.
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
          <FadeWrap fadeInFrames={isXfade ? xfadeFrames : 0}>
            {renderSegment(seg, dur, plan.palette)}
          </FadeWrap>
        </Sequence>
      ))}
      {plan.captions && plan.captions.length > 0 && <CaptionTrack captions={plan.captions} />}
      {plan.audio && <Audio src={staticFile(plan.audio.src)} volume={plan.audio.gain ?? 1} />}
    </AbsoluteFill>
  );
};

const FadeWrap: React.FC<{fadeInFrames: number; children: React.ReactNode}> = ({fadeInFrames, children}) => {
  const frame = useCurrentFrame();
  const opacity = fadeInFrames > 0 ? interpolate(frame, [0, fadeInFrames], [0, 1], {extrapolateRight: 'clamp'}) : 1;
  return <AbsoluteFill style={{opacity}}>{children}</AbsoluteFill>;
};
