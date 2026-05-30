// Kinetic captions — TikTok-style word-by-word reveal, timed to the voice word timestamps.
// Styles: clean_pop (each word fades + scales in), emphasis (key words enlarged + accent color),
// karaoke (whole line shown; the current word fills with the accent + lifts — sing-along feel).
import {AbsoluteFill, interpolate, spring, useCurrentFrame, useVideoConfig} from 'remotion';

export type Word = {w: string; start_s: number; end_s: number};

const FONT = 'Helvetica, Arial, sans-serif';
const CHUNK = 4; // words shown together

const chunk = (words: Word[], n: number): Word[][] => {
  const out: Word[][] = [];
  for (let i = 0; i < words.length; i += n) out.push(words.slice(i, i + n));
  return out;
};

export const KineticCaption: React.FC<{words: Word[]; style?: string; palette?: string[]}> =
  ({words, style = 'clean_pop', palette}) => {
  const frame = useCurrentFrame();
  const {fps} = useVideoConfig();
  const t = frame / fps;
  if (!words || words.length === 0) return null;

  const groups = chunk(words, CHUNK);
  const active = groups.find((g) => t >= g[0].start_s - 0.15 && t < g[g.length - 1].end_s + 0.25);
  if (!active) return null;
  const accent = (palette && palette[0]) || '#FFE14D';

  return (
    <AbsoluteFill style={{justifyContent: 'flex-end', alignItems: 'center', paddingBottom: 240}}>
      {/* alignItems:baseline keeps mixed font sizes (emphasis) on one baseline — no vertical jump */}
      <div style={{display: 'flex', flexWrap: 'wrap', justifyContent: 'center', alignItems: 'baseline',
                   gap: '12px 16px', maxWidth: '92%'}}>
        {active.map((word, i) => {
          const s = spring({frame: frame - word.start_s * fps, fps,
                            config: {damping: 12, stiffness: 200, mass: 0.5}});
          const isCurrent = t >= word.start_s && t < word.end_s + 0.2;
          // karaoke: the whole chunk is on screen from the start; the current word fills/lifts.
          if (style === 'karaoke') {
            const past = t >= word.start_s - 0.05;
            return (
              <span key={i} style={{
                fontFamily: FONT, fontWeight: 800, fontSize: 64, lineHeight: 1.1,
                color: isCurrent ? accent : past ? 'white' : 'rgba(255,255,255,0.55)',
                transform: `translateY(${isCurrent ? interpolate(s, [0, 1], [6, -4]) : 0}px)`,
                textShadow: '0 3px 14px rgba(0,0,0,0.9)',
              }}>{word.w}</span>
            );
          }
          const shown = t >= word.start_s - 0.12;
          const big = style === 'emphasis' && word.w.replace(/[^A-Za-z0-9]/g, '').length >= 6;
          const color = style === 'emphasis' && (big || isCurrent) ? accent : 'white';
          // Reveal pop only (0.6 -> 1.0); NO persistent 1.12 on the current word — that breathing
          // shoved neighbors around and, with mixed emphasis sizes, read as misalignment. Emphasis is
          // now signalled by size + accent color, not by per-frame scaling.
          const scale = shown ? interpolate(s, [0, 1], [0.6, 1.0]) : 0.6;
          return (
            <span key={i} style={{
              fontFamily: FONT, fontWeight: 800, color,
              fontSize: big ? 76 : 64, lineHeight: 1.1,
              opacity: shown ? interpolate(s, [0, 1], [0, 1]) : 0,
              transform: `scale(${scale})`,
              textShadow: '0 3px 14px rgba(0,0,0,0.9)',
            }}>{word.w}</span>
          );
        })}
      </div>
    </AbsoluteFill>
  );
};
