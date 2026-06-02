// Motion-graphics overlays (D4) — lower-thirds + corner badges that sit ON TOP of a segment.
// lower_third: an animated chip (slides in from the left) for a business name / location / handle.
// badge: a popped-in sticker (e.g. "OPEN", "NEW", "★4.9", "20% OFF") in a corner.
import {AbsoluteFill, interpolate, spring, useCurrentFrame, useVideoConfig} from 'remotion';

const FONT = 'Helvetica, Arial, sans-serif';

export type OverlaySpec = {
  kind: 'lower_third' | 'badge' | 'stamp';
  text: string;
  position?: 'tl' | 'tr' | 'bl' | 'br'; // badge corner (default tr)
  accent?: string;
  variant?: 'before' | 'after';         // stamp: 'before' = muted, 'after' = brand accent + harder hit
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

  if (overlay.kind === 'stamp') {
    // Bold kinetic stamp: big caps SLAM onto the frame (scale 1.35 -> 1.0). BEFORE is muted; AFTER hits
    // harder and in the brand accent — the transformation's punctuation, not a sticker.
    const isAfter = overlay.variant === 'after';
    const hit = spring({frame, fps, config: {damping: isAfter ? 9 : 13, stiffness: 210, mass: 0.7}});
    const scale = interpolate(hit, [0, 1], [1.35, 1.0]);
    const fade = interpolate(frame, [0, 4], [0, 1], {extrapolateRight: 'clamp'});
    return (
      <AbsoluteFill style={{justifyContent: 'flex-start', alignItems: 'center', paddingTop: 230}}>
        <div style={{transform: `scale(${scale})`, opacity: fade,
          color: isAfter ? accent : 'rgba(255,255,255,0.94)',
          fontFamily: FONT, fontWeight: 900, fontSize: isAfter ? 134 : 116,
          letterSpacing: isAfter ? 14 : 10, textTransform: 'uppercase', whiteSpace: 'nowrap',
          WebkitTextStroke: isAfter ? '2px rgba(255,255,255,0.30)' : '1px rgba(255,255,255,0.18)',
          textShadow: '0 5px 22px rgba(0,0,0,0.6)'}}>
          {overlay.text}
        </div>
      </AbsoluteFill>
    );
  }

  // badge — a popped circular sticker, slight tilt. Sized so short labels (BEFORE / AFTER / ★4.9)
  // fit comfortably on one line (was 150px/38px — too small, text clipped).
  const pop = interpolate(s, [0, 1], [0.4, 1]);
  return (
    <AbsoluteFill style={corner(overlay.position)}>
      <div style={{transform: `scale(${pop}) rotate(-7deg)`, opacity, backgroundColor: accent,
        color: '#fff', fontWeight: 900, fontSize: 42, fontFamily: FONT, width: 230, height: 230,
        borderRadius: '50%', display: 'flex', alignItems: 'center', justifyContent: 'center',
        textAlign: 'center', lineHeight: 1.05, padding: 18, border: '6px solid rgba(255,255,255,0.92)',
        boxShadow: '0 8px 22px rgba(0,0,0,0.5)'}}>
        {overlay.text}
      </div>
    </AbsoluteFill>
  );
};
