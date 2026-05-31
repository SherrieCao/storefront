// Kinetic captions — word-by-word, timed to the voice word timestamps. The HIGHLIGHT always tracks
// the word currently being spoken: within the on-screen line, exactly one word is highlighted — the
// most-recently-STARTED word (advances on each word's start_s, persists through inter-word gaps, never
// double-highlights). This invariant holds for EVERY style; styles differ only in how words reveal/sit,
// not in WHAT gets highlighted. The highlight is by BRIGHTNESS: the spoken word is bright WHITE, every
// other word is GREY (no brand-color accent — a grey palette[0] once reversed it).
//   clean_pop — words fade + scale in as spoken; the spoken word is white, the rest grey.
//   emphasis  — same reveal; the spoken word is white AND pops larger (a moving emphasis).
//   karaoke   — whole line shown at once; the spoken word is white, the rest grey + a small lift.
import {AbsoluteFill, interpolate, spring, useCurrentFrame, useVideoConfig} from 'remotion';

export type Word = {w: string; start_s: number; end_s: number};

const FONT = 'Helvetica, Arial, sans-serif';
const CHUNK = 4;   // words shown together (one line)
const SIZE = 64;   // uniform base size — no static big words (keeps the baseline stable)

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
  // Highlight by BRIGHTNESS, not brand color: the spoken word is bright white, the rest recede to grey.
  // (Using palette[0] as an accent backfired — a brand grey like #505558 made the spoken word the DIM
  // one and the rest white, i.e. reversed.)
  const LIVE = '#ffffff';
  const DIM = 'rgba(255,255,255,0.45)';

  // The highlighted word = the most-recently-started word in this line (tracks speech; exactly one,
  // no gaps, no overlaps). -1 during the brief pre-roll before the line's first word begins.
  const currentIdx = active.reduce((acc, w, i) => (t >= w.start_s ? i : acc), -1);

  return (
    <AbsoluteFill style={{justifyContent: 'flex-end', alignItems: 'center', paddingBottom: 240}}>
      {/* uniform size + alignItems:baseline -> stable line, no vertical jump */}
      <div style={{display: 'flex', flexWrap: 'wrap', justifyContent: 'center', alignItems: 'baseline',
                   gap: '12px 16px', maxWidth: '92%'}}>
        {active.map((word, i) => {
          const isCurrent = i === currentIdx;
          const reveal = spring({frame: frame - word.start_s * fps, fps,
                                 config: {damping: 12, stiffness: 200, mass: 0.5}});

          if (style === 'karaoke') {
            return (
              <span key={i} style={{
                fontFamily: FONT, fontWeight: isCurrent ? 900 : 800, fontSize: SIZE, lineHeight: 1.1,
                color: isCurrent ? LIVE : DIM,   // spoken word bright white; the rest grey
                transform: `translateY(${isCurrent ? interpolate(reveal, [0, 1], [6, -4]) : 0}px)`,
                textShadow: '0 3px 14px rgba(0,0,0,0.9)',
              }}>{word.w}</span>
            );
          }

          // clean_pop + emphasis: reveal each word as it's spoken; highlight the spoken word.
          const shown = t >= word.start_s - 0.12;
          const pop = style === 'emphasis' && isCurrent ? 1.12 : 1.0;   // emphasis pops the spoken word
          const scale = (shown ? interpolate(reveal, [0, 1], [0.6, 1.0]) : 0.6) * pop;
          return (
            <span key={i} style={{
              fontFamily: FONT, fontWeight: isCurrent ? 900 : 800, fontSize: SIZE, lineHeight: 1.1,
              color: isCurrent ? LIVE : DIM,   // spoken word bright white; the rest grey
              opacity: shown ? interpolate(reveal, [0, 1], [0, 1]) : 0,
              transform: `scale(${scale})`, transformOrigin: 'center bottom',
              textShadow: '0 3px 14px rgba(0,0,0,0.9)',
            }}>{word.w}</span>
          );
        })}
      </div>
    </AbsoluteFill>
  );
};
