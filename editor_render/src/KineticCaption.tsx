// Caption system (SPEC_remotion_design_system §1) — FOUR distinct caption aesthetics the Editor picks
// from, so captions don't pattern-match as one preset. `KineticCaption` is the router; each style is a
// sub-component. The highlight always tracks the SPOKEN word (most-recently-started word in the on-
// screen group). Palette is GUARDED: accent is only used when bright enough to read, else white (a grey
// brand color must never produce the dim-spoken-word reversal we hit before).
//
//   bold_center    — Inter Black, centered, big; spoken word white (emphasis word = guarded accent),
//                    rest grey. Absorbs the legacy clean_pop / emphasis / karaoke sub-modes.
//   minimal_lower  — Inter Medium, 48px, bottom-left over a subtle gradient band; the phrase fades in as
//                    a BLOCK (not per-word); spoken word full white, rest 50%.
//   handwritten    — Caveat, centered, 2–3 words; words land with a slight random rotation + jitter
//                    (hand-placed feel); the spoken word gets an underline (not a color change).
//   sparse_keyword — Inter Black 96px; only KEY words (stop words dropped); ONE word at a time SLAMS in
//                    (scale 1.4→1.0). The rest is heard, not read. (Our legacy `sparse` aliases here.)
import {AbsoluteFill, interpolate, random, spring, useCurrentFrame, useVideoConfig} from 'remotion';
import {loadFont as loadInter} from '@remotion/google-fonts/Inter';
import {loadFont as loadCaveat} from '@remotion/google-fonts/Caveat';

const INTER = loadInter('normal', {weights: ['500', '700', '900']}).fontFamily;
const CAVEAT = loadCaveat('normal', {weights: ['700']}).fontFamily;

export type Word = {w: string; start_s: number; end_s: number};
type Props = {words: Word[]; style?: string; palette?: string[]; cutoffS?: number | null};

// --- shared helpers --------------------------------------------------------
const lum = (hex?: string): number => {
  if (!hex) return 0;
  const h = hex.replace('#', '');
  if (h.length < 6) return 999;     // unknown -> treat as bright (use it)
  return 0.299 * parseInt(h.slice(0, 2), 16) + 0.587 * parseInt(h.slice(2, 4), 16) + 0.114 * parseInt(h.slice(4, 6), 16);
};
// accent guard: only use palette[0] as text when it's bright enough to read on dark footage, else white.
const accentText = (palette?: string[]) => {
  const a = palette && palette[0];
  return a && lum(a) > 110 ? a : '#ffffff';
};
const STOPWORDS = new Set([
  'the','a','an','and','or','but','of','to','in','on','at','for','with','from','by','as','is','are','am',
  'be','been','was','were','do','does','did','it','its','this','that','these','those','so','if','then',
  'i','my','me','we','us','our','you','your','he','she','they','them','his','her','their','will','can',
  'just','not','no','has','have','had','up','out','about','into','over','than','too','very','also','here',
]);
const isKey = (w: string): boolean => {
  const bare = w.replace(/[^A-Za-z0-9]/g, '');
  if (!bare) return false;
  if (/[0-9]/.test(bare) || /[A-Z]/.test(bare)) return true;
  return bare.length >= 3 && !STOPWORDS.has(bare.toLowerCase());
};
const chunkWords = (ws: Word[], n: number): Word[][] => {
  const out: Word[][] = [];
  for (let i = 0; i < ws.length; i += n) out.push(ws.slice(i, i + n));
  return out;
};
const useActive = (words: Word[], n: number) => {
  const frame = useCurrentFrame();
  const {fps} = useVideoConfig();
  const t = frame / fps;
  const groups = chunkWords(words, n);
  const active = groups.find((g) => t >= g[0].start_s - 0.15 && t < g[g.length - 1].end_s + 0.25);
  const currentIdx = active ? active.reduce((acc, w, i) => (t >= w.start_s ? i : acc), -1) : -1;
  return {frame, fps, t, active, currentIdx};
};
const SHADOW = '0 3px 14px rgba(0,0,0,0.9)';

// --- bold_center (clean_pop / emphasis / karaoke / bold_center) ------------
const BoldCenter: React.FC<Props> = ({words, style = 'bold_center', palette}) => {
  const {frame, fps, t, active, currentIdx} = useActive(words, 4);
  if (!active) return null;
  const accent = accentText(palette);
  const isEmph = style === 'emphasis' || style === 'bold_center';
  return (
    <AbsoluteFill style={{justifyContent: 'flex-end', alignItems: 'center', paddingBottom: 240}}>
      <div style={{display: 'flex', flexWrap: 'wrap', justifyContent: 'center', alignItems: 'baseline',
                   gap: '12px 16px', maxWidth: '92%'}}>
        {active.map((word, i) => {
          const isCurrent = i === currentIdx;
          const reveal = spring({frame: frame - word.start_s * fps, fps, config: {damping: 12, stiffness: 200, mass: 0.5}});
          if (style === 'karaoke') {
            return <span key={i} style={{fontFamily: INTER, fontWeight: isCurrent ? 900 : 800, fontSize: 64,
              lineHeight: 1.1, color: isCurrent ? '#fff' : 'rgba(255,255,255,0.45)',
              transform: `translateY(${isCurrent ? interpolate(reveal, [0, 1], [6, -4]) : 0}px)`, textShadow: SHADOW}}>{word.w}</span>;
          }
          const shown = t >= word.start_s - 0.12;
          const big = isEmph && word.w.replace(/[^A-Za-z0-9]/g, '').length >= 6;
          const color = isCurrent ? (isEmph ? accent : '#fff') : 'rgba(255,255,255,0.45)';
          const scale = (shown ? interpolate(reveal, [0, 1], [0.6, 1.0]) : 0.6) * (isEmph && isCurrent ? 1.12 : 1.0);
          return <span key={i} style={{fontFamily: INTER, fontWeight: 900, fontSize: big ? 84 : 72,
            lineHeight: 1.1, color, opacity: shown ? interpolate(reveal, [0, 1], [0, 1]) : 0,
            transform: `scale(${scale})`, transformOrigin: 'center bottom', textShadow: SHADOW}}>{word.w}</span>;
        })}
      </div>
    </AbsoluteFill>
  );
};

// --- minimal_lower ---------------------------------------------------------
const MinimalLower: React.FC<Props> = ({words}) => {
  const {frame, fps, t, active, currentIdx} = useActive(words, 6);
  if (!active) return null;
  const block = spring({frame: frame - active[0].start_s * fps, fps, config: {damping: 18, stiffness: 120}});
  return (
    <AbsoluteFill style={{justifyContent: 'flex-end', alignItems: 'flex-start'}}>
      <AbsoluteFill style={{background: 'linear-gradient(0deg, rgba(0,0,0,0.45) 0%, transparent 15%)'}} />
      <div style={{opacity: interpolate(block, [0, 1], [0, 1]), padding: '0 0 90px 86px', maxWidth: '80%',
        display: 'flex', flexWrap: 'wrap', gap: '6px 12px'}}>
        {active.map((word, i) => (
          <span key={i} style={{fontFamily: INTER, fontWeight: 500, fontSize: 48, lineHeight: 1.25,
            color: i === currentIdx ? '#fff' : 'rgba(255,255,255,0.5)'}}>{word.w}</span>
        ))}
      </div>
    </AbsoluteFill>
  );
};

// --- handwritten -----------------------------------------------------------
const Handwritten: React.FC<Props> = ({words}) => {
  const {frame, fps, t, active, currentIdx} = useActive(words, 3);
  if (!active) return null;
  return (
    <AbsoluteFill style={{justifyContent: 'flex-end', alignItems: 'center', paddingBottom: 320}}>
      <div style={{display: 'flex', flexWrap: 'wrap', justifyContent: 'center', alignItems: 'baseline', gap: '8px 18px', maxWidth: '84%'}}>
        {active.map((word, i) => {
          const shown = t >= word.start_s - 0.12;
          const reveal = spring({frame: frame - word.start_s * fps, fps, config: {damping: 13, stiffness: 160}});
          const rot = (random(`hw-r${i}-${Math.round(word.start_s * 10)}`) - 0.5) * 4;   // ±2°, fixed per word
          const jy = (random(`hw-y${i}-${Math.round(word.start_s * 10)}`) - 0.5) * 6;     // ±3px
          return <span key={i} style={{fontFamily: CAVEAT, fontWeight: 700, fontSize: 60, lineHeight: 1.1,
            color: '#F5F0E8', opacity: shown ? interpolate(reveal, [0, 1], [0, 1]) : 0,
            transform: `translateY(${jy}px) rotate(${rot}deg)`, textShadow: SHADOW,
            borderBottom: i === currentIdx ? '4px solid rgba(245,240,232,0.85)' : '4px solid transparent',
            paddingBottom: 2}}>{word.w}</span>;
        })}
      </div>
    </AbsoluteFill>
  );
};

// --- sparse_keyword --------------------------------------------------------
const SparseKeyword: React.FC<Props> = ({words, palette}) => {
  const frame = useCurrentFrame();
  const {fps} = useVideoConfig();
  const t = frame / fps;
  const keys = words.filter((w) => isKey(w.w));
  if (!keys.length) return null;
  // show the most-recently-started keyword, alone, big — until the next keyword starts.
  let idx = -1;
  for (let i = 0; i < keys.length; i++) if (t >= keys[i].start_s) idx = i;
  if (idx < 0) return null;
  const word = keys[idx];
  if (t > word.end_s + 1.2) return null;                 // clear after a keyword has lingered
  const slam = spring({frame: frame - word.start_s * fps, fps, config: {damping: 200, stiffness: 220, mass: 0.4}});
  const scale = interpolate(slam, [0, 1], [1.4, 1.0]);
  const accent = accentText(palette);
  return (
    <AbsoluteFill style={{justifyContent: 'center', alignItems: 'center'}}>
      <span style={{fontFamily: INTER, fontWeight: 900, fontSize: 96, color: idx % 3 === 1 ? accent : '#fff',
        textTransform: 'uppercase', letterSpacing: 1, opacity: interpolate(slam, [0, 0.4], [0, 1], {extrapolateRight: 'clamp'}),
        transform: `scale(${scale})`, textShadow: SHADOW, maxWidth: '88%', textAlign: 'center'}}>{word.w}</span>
    </AbsoluteFill>
  );
};

// --- router ----------------------------------------------------------------
export const KineticCaption: React.FC<Props> = ({words, style = 'bold_center', palette, cutoffS}) => {
  if (!words || words.length === 0) return null;
  return <CaptionCutoff cutoffS={cutoffS}>{
    style === 'minimal_lower' ? <MinimalLower words={words} palette={palette} />
    : style === 'handwritten' ? <Handwritten words={words} palette={palette} />
    : (style === 'sparse' || style === 'sparse_keyword') ? <SparseKeyword words={words} palette={palette} />
    : <BoldCenter words={words} style={style} palette={palette} />   /* clean_pop | emphasis | karaoke | bold_center */
  }</CaptionCutoff>;
};

// Hard cutoff: render nothing once the closing card begins, so a caption's fade-out / keyword linger
// (which draws PAST its end_s) can't bleed onto the clean ending card.
const CaptionCutoff: React.FC<{cutoffS?: number | null; children: React.ReactNode}> = ({cutoffS, children}) => {
  const {fps} = useVideoConfig();
  const t = useCurrentFrame() / fps;
  if (cutoffS != null && t >= cutoffS) return null;
  return <>{children}</>;
};

