// Motion-graphics overlays (D4) — lower-thirds + corner badges that sit ON TOP of a segment.
// lower_third: an animated chip (slides in from the left) for a business name / location / handle.
// badge: a popped-in sticker (e.g. "OPEN", "NEW", "★4.9", "20% OFF") in a corner.
import {AbsoluteFill, interpolate, spring, useCurrentFrame, useVideoConfig} from 'remotion';

const FONT = 'Helvetica, Arial, sans-serif';

export type OverlaySpec = {
  kind: 'lower_third' | 'badge';
  text: string;
  position?: 'tl' | 'tr' | 'bl' | 'br'; // badge corner (default tr)
  accent?: string;
};

const corner = (p?: string): React.CSSProperties => ({
  justifyContent: p === 'tl' || p === 'tr' ? 'flex-start' : 'flex-end', // vertical (column main axis)
  alignItems: p === 'tl' || p === 'bl' ? 'flex-start' : 'flex-end',     // horizontal
  padding: '130px 60px 330px',
});

export const OverlayLayer: React.FC<{overlay: OverlaySpec; palette?: string[]}> = ({overlay, palette}) => {
  const frame = useCurrentFrame();
  const {fps} = useVideoConfig();
  const s = spring({frame, fps, config: {damping: 14, stiffness: 150, mass: 0.6}});
  const accent = overlay.accent || (palette && palette[0]) || '#0b6e4f';
  const opacity = interpolate(s, [0, 1], [0, 1]);

  if (overlay.kind === 'lower_third') {
    const x = interpolate(s, [0, 1], [-140, 0]);
    return (
      <AbsoluteFill style={{justifyContent: 'flex-end', alignItems: 'flex-start', padding: '0 0 360px 0'}}>
        <div style={{transform: `translateX(${x}px)`, opacity, backgroundColor: accent,
          padding: '16px 34px 16px 50px', borderRadius: '0 16px 16px 0', display: 'flex',
          alignItems: 'center', gap: 16, boxShadow: '0 6px 18px rgba(0,0,0,0.45)'}}>
          <div style={{width: 9, height: 46, backgroundColor: 'rgba(255,255,255,0.9)', borderRadius: 3}} />
          <span style={{color: '#fff', fontSize: 50, fontWeight: 800, fontFamily: FONT,
            letterSpacing: 0.5}}>{overlay.text}</span>
        </div>
      </AbsoluteFill>
    );
  }

  // badge — a popped circular sticker, slight tilt
  const pop = interpolate(s, [0, 1], [0.4, 1]);
  return (
    <AbsoluteFill style={corner(overlay.position)}>
      <div style={{transform: `scale(${pop}) rotate(-7deg)`, opacity, backgroundColor: accent,
        color: '#fff', fontWeight: 900, fontSize: 38, fontFamily: FONT, width: 150, height: 150,
        borderRadius: '50%', display: 'flex', alignItems: 'center', justifyContent: 'center',
        textAlign: 'center', lineHeight: 1.05, padding: 12, border: '5px solid rgba(255,255,255,0.92)',
        boxShadow: '0 8px 22px rgba(0,0,0,0.5)'}}>
        {overlay.text}
      </div>
    </AbsoluteFill>
  );
};
