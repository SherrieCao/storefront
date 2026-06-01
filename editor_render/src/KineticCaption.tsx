// Kinetic captions — word-by-word, timed to the voice word timestamps. The HIGHLIGHT always tracks
// the word currently being spoken: within the on-screen line, exactly one word is highlighted — the
// most-recently-STARTED word (advances on each word's start_s, persists through inter-word gaps, never
// double-highlights). This invariant holds for EVERY style; styles differ only in how words reveal/sit,
// not in WHAT gets highlighted. The highlight is by BRIGHTNESS: the spoken word is bright WHITE, every
// other word is GREY (no brand-color accent — a grey palette[0] once reversed it).
//   clean_pop — words fade + scale in as spoken; the spoken word is white, the rest grey.
//   emphasis  — same reveal; the spoken word is white AND pops larger (a moving emphasis).
//   karaoke   — whole line shown at once; the spoken word is white, the rest grey + a small lift.
//   sparse    — only the KEY words appear (function/stop words dropped), so the screen isn't wall-to-
//               wall text; the rest is heard, not read. Often the most native-feeling for social.
import {AbsoluteFill, interpolate, spring, useCurrentFrame, useVideoConfig} from 'remotion';

export type Word = {w: string; start_s: number; end_s: number};

const FONT = 'Helvetica, Arial, sans-serif';
const CHUNK = 4;   // words shown together (one line)
const SIZE = 64;   // uniform base size — no static big words (keeps the baseline stable)

// `sparse` shows only key words — drop common function/stop words + 1–2 char fillers (kept: numbers,
// anything capitalised/proper, and any non-stopword >=3 chars). Deterministic; no LLM needed.
const STOPWORDS = new Set([
  'the','a','an','and','or','but','of','to','in','on','at','for','with','from','by','as','is','are','am',
  'be','been','was','were','do','does','did','it','its','this','that','these','those','so','if','then',
  'i','my','me','we','us','our','you','your','he','she','they','them','his','her','their','will','can',
  'just','not','no','has','have','had','up','out','about','into','over','than','too','very','also','here',
]);
const isKey = (w: string): boolean => {
  const bare = w.replace(/[^A-Za-z0-9]/g, '');
  if (!bare) return false;
  if (/[0-9]/.test(bare) || /[A-Z]/.test(bare)) return true;   // numbers + proper/capitalised words
  return bare.length >= 3 && !STOPWORDS.has(bare.toLowerCase());
};

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

  // `sparse`: render only the key words (drop stop/filler words); other styles render every word.
  const display = style === 'sparse' ? words.filter((w) => isKey(w.w)) : words;
  if (display.length === 0) return null;
  const groups = chunk(display, CHUNK);
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
