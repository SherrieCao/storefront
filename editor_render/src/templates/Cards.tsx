// Card template library — photo-backed, scrim, spring-animated text in the brand palette.
// {text, bg?, palette?, animation?}. A `bg` renders behind a dark scrim with a Ken Burns push; else a
// palette gradient. Text enters per `animation` (scale_pop | slide_in | fade). No flat color cards.
import {AbsoluteFill, Img, interpolate, spring, staticFile, useCurrentFrame, useVideoConfig} from 'remotion';

const FONT = 'Helvetica, Arial, sans-serif';

type CardProps = {text?: string; bg?: string; palette?: string[]; animation?: string};

const accentOf = (palette?: string[]) => (palette && palette[0]) || '#0b6e4f';
const accent2Of = (palette?: string[]) => (palette && (palette[2] || palette[1])) || '#15324b';

const lines = (t?: string) => (t || '').split(/\s*[|\n]\s*/).map((s) => s.trim()).filter(Boolean);
const Stacked: React.FC<{text?: string}> = ({text}) => (
  <>{lines(text).map((ln, i) => <div key={i}>{ln}</div>)}</>
);

const Backdrop: React.FC<{bg?: string; palette?: string[]}> = ({bg, palette}) => {
  const frame = useCurrentFrame();
  const scale = 1.06 + frame * 0.0009;
  if (bg) {
    return (
      <AbsoluteFill style={{backgroundColor: '#000', overflow: 'hidden'}}>
        <Img src={staticFile(bg)} style={{width: '100%', height: '100%', objectFit: 'cover',
          transform: `scale(${scale})`}} />
        <AbsoluteFill style={{background:
          'linear-gradient(180deg, rgba(0,0,0,0.35) 0%, rgba(0,0,0,0.15) 45%, rgba(0,0,0,0.82) 100%)'}} />
      </AbsoluteFill>
    );
  }
  return <AbsoluteFill style={{background:
    `linear-gradient(150deg, ${accentOf(palette)} 0%, ${accent2Of(palette)} 100%)`}} />;
};

// Spring entrance, varied by animation kind.
const useEntrance = (delay = 0, animation = 'scale_pop'): React.CSSProperties => {
  const frame = useCurrentFrame();
  const {fps} = useVideoConfig();
  const s = spring({frame: frame - delay, fps, config: {damping: 14, stiffness: 120, mass: 0.6}});
  const opacity = interpolate(s, [0, 1], [0, 1]);
  if (animation === 'slide_in') return {opacity, transform: `translateX(${interpolate(s, [0, 1], [-90, 0])}px)`};
  if (animation === 'fade') return {opacity};
  return {opacity, transform: `scale(${interpolate(s, [0, 1], [0.82, 1])})`}; // scale_pop (default)
};

const Lower: React.FC<{children: React.ReactNode}> = ({children}) => (
  <AbsoluteFill style={{justifyContent: 'flex-end', alignItems: 'center', padding: '0 70px 200px'}}>
    {children}
  </AbsoluteFill>
);

const Big: React.FC<{text?: string; size?: number; delay?: number; color?: string; animation?: string}> =
  ({text, size = 92, delay = 0, color = 'white', animation}) => {
  const e = useEntrance(delay, animation);
  return <div style={{...e, color, fontSize: size, fontWeight: 800, textAlign: 'center', lineHeight: 1.18,
    fontFamily: FONT, textShadow: '0 4px 24px rgba(0,0,0,0.6)', display: 'flex', flexDirection: 'column',
    gap: 6}}><Stacked text={text} /></div>;
};

const Title: React.FC<CardProps> = ({text, bg, palette, animation}) => (
  <AbsoluteFill><Backdrop bg={bg} palette={palette} />
    <AbsoluteFill style={{justifyContent: 'center', alignItems: 'center', padding: 80}}>
      <Big text={text} size={104} animation={animation} /></AbsoluteFill></AbsoluteFill>
);

const OfferBanner: React.FC<CardProps> = ({text, bg, palette, animation}) => {
  const e = useEntrance(4, animation);
  return <AbsoluteFill><Backdrop bg={bg} palette={palette} /><Lower>
    <div style={{...e, backgroundColor: accentOf(palette), padding: '26px 44px', borderRadius: 22,
      transform: `${e.transform ?? ''} rotate(-2deg)`}}>
      <div style={{color: 'white', fontSize: 84, fontWeight: 900, textAlign: 'center', lineHeight: 1.18,
        fontFamily: FONT, display: 'flex', flexDirection: 'column', gap: 6}}><Stacked text={text} /></div>
      </div></Lower></AbsoluteFill>;
};

const PriceTag: React.FC<CardProps> = ({text, bg, palette, animation}) => {
  const e = useEntrance(4, animation);
  return <AbsoluteFill><Backdrop bg={bg} palette={palette} />
    <AbsoluteFill style={{justifyContent: 'center', alignItems: 'center', padding: 80}}>
      <div style={{...e, border: `8px solid ${accentOf(palette)}`, borderRadius: 28, padding: '40px 60px',
        backgroundColor: 'rgba(0,0,0,0.45)'}}>
        <div style={{color: 'white', fontSize: 100, fontWeight: 900, textAlign: 'center', lineHeight: 1.15,
          fontFamily: FONT, display: 'flex', flexDirection: 'column', gap: 6}}><Stacked text={text} /></div>
        </div></AbsoluteFill></AbsoluteFill>;
};

const LocationPin: React.FC<CardProps> = ({text, bg, palette, animation}) => (
  <AbsoluteFill><Backdrop bg={bg} palette={palette} /><Lower>
    <div style={{...useEntrance(4, animation), fontSize: 92, marginBottom: 8}}>📍</div>
    <Big text={text} size={74} delay={8} animation={animation} /></Lower></AbsoluteFill>
);

// EndCard / CTA — the strongest treatment: accent kicker + big animated CTA.
const EndCard: React.FC<CardProps> = ({text, bg, palette, animation}) => (
  <AbsoluteFill><Backdrop bg={bg} palette={palette} /><Lower>
    <div style={{width: 90, height: 8, borderRadius: 4, backgroundColor: accentOf(palette),
      marginBottom: 28, ...useEntrance(0, animation)}} />
    <Big text={text} size={86} delay={6} animation={animation} /></Lower></AbsoluteFill>
);

export const CARD_TEMPLATES: Record<string, React.FC<CardProps>> = {
  Title, OfferBanner, PriceTag, LocationPin, EndCard,
};
