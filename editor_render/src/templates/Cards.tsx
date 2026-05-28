// Card template library (Phase 1 — 5 starters; grow as needed). Each is a Remotion component taking
// text + style props. Kept visually consistent: bold sans, high contrast, vertical 9:16, no clutter.
import {AbsoluteFill, interpolate, useCurrentFrame} from 'remotion';

const FONT = 'Helvetica, Arial, sans-serif';

const Center: React.FC<{bg: string; children: React.ReactNode}> = ({bg, children}) => {
  const frame = useCurrentFrame();
  const opacity = interpolate(frame, [0, 8], [0, 1], {extrapolateRight: 'clamp'});
  return (
    <AbsoluteFill style={{backgroundColor: bg, justifyContent: 'center', alignItems: 'center',
                          padding: 90, opacity}}>
      {children}
    </AbsoluteFill>
  );
};

const Title: React.FC<{text?: string}> = ({text}) => (
  <Center bg="#111111">
    <div style={{color: 'white', fontSize: 96, fontWeight: 800, textAlign: 'center', lineHeight: 1.1, fontFamily: FONT}}>
      {text}
    </div>
  </Center>
);

const OfferBanner: React.FC<{text?: string}> = ({text}) => (
  <Center bg="#0b6e4f">
    <div style={{color: 'white', fontSize: 88, fontWeight: 800, textAlign: 'center', lineHeight: 1.15, fontFamily: FONT}}>
      {text}
    </div>
  </Center>
);

const PriceTag: React.FC<{text?: string}> = ({text}) => (
  <Center bg="#1d1d1f">
    <div style={{border: '8px solid #f5c518', borderRadius: 28, padding: '44px 64px'}}>
      <div style={{color: '#f5c518', fontSize: 104, fontWeight: 900, textAlign: 'center', fontFamily: FONT}}>
        {text}
      </div>
    </div>
  </Center>
);

const LocationPin: React.FC<{text?: string}> = ({text}) => (
  <Center bg="#15324b">
    <div style={{fontSize: 120, marginBottom: 16}}>📍</div>
    <div style={{color: 'white', fontSize: 78, fontWeight: 700, textAlign: 'center', lineHeight: 1.2, fontFamily: FONT}}>
      {text}
    </div>
  </Center>
);

const EndCard: React.FC<{text?: string}> = ({text}) => (
  <Center bg="#000000">
    <div style={{color: 'white', fontSize: 84, fontWeight: 800, textAlign: 'center', lineHeight: 1.2, fontFamily: FONT}}>
      {text}
    </div>
  </Center>
);

export const CARD_TEMPLATES: Record<string, React.FC<{text?: string}>> = {
  Title, OfferBanner, PriceTag, LocationPin, EndCard,
};
