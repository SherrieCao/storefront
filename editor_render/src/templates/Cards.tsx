// Card system (SPEC_remotion_design_system §4 + SPEC_card_typography). Four distinct card STYLES
// (glass | type_only | photo_backed | minimal_bar), each rendering up to four typographic TIERS
// (name / tagline / info / cta) with a staggered entrance. Real fonts (Inter geometric + Caveat
// handwriting) give a designed hierarchy instead of one flat placeholder line.
// Backward-compat: a flat `card_text` ("Name | Location | Book") still renders (name = first chunk,
// info = the rest). Text stays WHITE on the dark-backed styles (glass/photo_backed) + heavy shadow on
// the open styles, so we don't need live frame-luminance detection; palette[0] is used as an accent
// only where it's bright enough to read.
import {AbsoluteFill, Img, interpolate, spring, staticFile, useCurrentFrame, useVideoConfig} from 'remotion';
import {loadFont as loadInter} from '@remotion/google-fonts/Inter';
import {loadFont as loadCaveat} from '@remotion/google-fonts/Caveat';

const INTER = loadInter('normal', {weights: ['500', '700', '900']}).fontFamily;
const CAVEAT = loadCaveat('normal', {weights: ['700']}).fontFamily;

export type CardTiers = {name?: string; tagline?: string; info?: string; cta?: string; cta_style?: string};
type CardProps = {
  style?: string; tiers?: CardTiers; text?: string; bg?: string; palette?: string[]; animation?: string;
};

// --- color helpers ---------------------------------------------------------
const lum = (hex?: string): number => {
  if (!hex) return 0;
  const h = hex.replace('#', '');
  if (h.length < 6) return 0;
  const r = parseInt(h.slice(0, 2), 16), g = parseInt(h.slice(2, 4), 16), b = parseInt(h.slice(4, 6), 16);
  return 0.299 * r + 0.587 * g + 0.114 * b;
};
const accentOf = (palette?: string[]) => (palette && palette[0]) || '#0b6e4f';
// accent used as TEXT must be readable on a dark card; a dark/muted brand color falls back to white
// (this is the guard that avoids the grey-palette caption reversal we hit earlier).
const accentText = (palette?: string[]) => (lum(accentOf(palette)) > 90 ? accentOf(palette) : '#FFFFFF');

// --- tier normalization (structured tiers, or a flat "A | B | C" string) ---
const tiersFrom = (tiers?: CardTiers, text?: string): CardTiers => {
  if (tiers && (tiers.name || tiers.info || tiers.cta || tiers.tagline)) return tiers;
  const parts = (text || '').split(/\s*[|\n]\s*/).map((s) => s.trim()).filter(Boolean);
  if (!parts.length) return {};
  return {name: parts[0], info: parts.slice(1, -1).join(' · ') || undefined,
          cta: parts.length > 1 ? parts[parts.length - 1] : undefined, cta_style: 'subtle'};
};

// staggered entrance: returns {opacity, dy} for a tier that starts at `delay` frames
const useStagger = (delay: number) => {
  const frame = useCurrentFrame();
  const {fps} = useVideoConfig();
  const s = spring({frame: frame - delay, fps, config: {damping: 16, stiffness: 120, mass: 0.6}});
  return {opacity: interpolate(s, [0, 1], [0, 1]), dy: interpolate(s, [0, 1], [14, 0]), s};
};

// --- tier renderers --------------------------------------------------------
const SHADOW = '0 3px 10px rgba(0,0,0,0.55)';
const Name: React.FC<{t?: string; size?: number; align?: any; shadow?: boolean}> =
  ({t, size = 64, align = 'center', shadow}) => {
  if (!t) return null;
  const e = useStagger(0);
  return <div style={{fontFamily: INTER, fontWeight: 900, fontSize: size, color: '#fff', lineHeight: 1.05,
    letterSpacing: 1.3, textTransform: 'uppercase', textAlign: align, opacity: e.opacity,
    transform: `translateY(${e.dy}px)`, textShadow: shadow ? SHADOW : undefined}}>{t}</div>;
};
const Tagline: React.FC<{t?: string; palette?: string[]; align?: any; shadow?: boolean}> =
  ({t, palette, align = 'center', shadow}) => {
  if (!t) return null;
  const e = useStagger(6);
  return <div style={{fontFamily: CAVEAT, fontWeight: 700, fontSize: 44, color: accentText(palette),
    lineHeight: 1.1, textAlign: align, opacity: e.opacity,
    transform: `translateY(${e.dy}px) rotate(${interpolate(e.s, [0, 1], [-1.2, 0])}deg)`,
    textShadow: shadow ? SHADOW : undefined}}>{t}</div>;
};
const Info: React.FC<{t?: string; align?: any; shadow?: boolean}> = ({t, align = 'center', shadow}) => {
  if (!t) return null;
  const e = useStagger(12);
  return <div style={{fontFamily: INTER, fontWeight: 500, fontSize: 30, color: 'rgba(255,255,255,0.72)',
    lineHeight: 1.3, textAlign: align, opacity: e.opacity, textShadow: shadow ? SHADOW : undefined}}>{t}</div>;
};
const Cta: React.FC<{t?: string; ctaStyle?: string; palette?: string[]; shadow?: boolean}> =
  ({t, ctaStyle = 'pill', palette, shadow}) => {
  if (!t) return null;
  const e = useStagger(16);
  if (ctaStyle === 'pill') {
    return <div style={{fontFamily: INTER, fontWeight: 700, fontSize: 34, color: '#fff',
      backgroundColor: accentOf(palette), padding: '8px 22px', borderRadius: 24,
      opacity: e.opacity, transform: `scale(${interpolate(e.s, [0, 1], [0.8, 1])})`}}>{t}</div>;
  }
  // handle / subtle: text only (no container)
  return <div style={{fontFamily: INTER, fontWeight: ctaStyle === 'handle' ? 600 : 500, fontSize: 30,
    color: ctaStyle === 'handle' ? accentText(palette) : 'rgba(255,255,255,0.85)', opacity: e.opacity,
    textShadow: shadow ? SHADOW : undefined}}>{t}</div>;
};

// --- the four card styles --------------------------------------------------
const Stack: React.FC<{children: React.ReactNode; align?: any; gap?: number; justify?: any; pad?: string}> =
  ({children, align = 'center', gap = 18, justify = 'center', pad = '0 90px'}) => (
  <AbsoluteFill style={{display: 'flex', flexDirection: 'column', justifyContent: justify,
    alignItems: align === 'center' ? 'center' : 'flex-start', gap, padding: pad, textAlign: align}}>
    {children}
  </AbsoluteFill>
);

const PhotoOrColor: React.FC<{bg?: string; palette?: string[]; dim?: number}> = ({bg, palette, dim = 0.45}) => {
  const frame = useCurrentFrame();
  const scale = 1.06 + frame * 0.0008;
  if (bg) return (
    <AbsoluteFill style={{backgroundColor: '#000', overflow: 'hidden'}}>
      <Img src={staticFile(bg)} style={{width: '100%', height: '100%', objectFit: 'cover',
        transform: `scale(${scale})`, filter: `brightness(${dim})`}} />
    </AbsoluteFill>
  );
  return <AbsoluteFill style={{background: `linear-gradient(150deg, #1a1a1a 0%, ${accentOf(palette)} 220%)`}} />;
};

const Glass: React.FC<CardProps> = ({tiers, palette}) => (
  <AbsoluteFill style={{justifyContent: 'center', alignItems: 'center', padding: 90}}>
    <div style={{backgroundColor: 'rgba(0,0,0,0.55)', backdropFilter: 'blur(12px)', borderRadius: 24,
      padding: '54px 56px', display: 'flex', flexDirection: 'column', alignItems: 'center', gap: 18,
      maxWidth: '84%'}}>
      <Name t={tiers?.name} /><Tagline t={tiers?.tagline} palette={palette} />
      <Info t={tiers?.info} /><Cta t={tiers?.cta} ctaStyle={tiers?.cta_style} palette={palette} />
    </div>
  </AbsoluteFill>
);

const TypeOnly: React.FC<CardProps> = ({tiers, palette}) => (
  <Stack align="left" justify="flex-end" pad="0 70px 200px" gap={16}>
    <Name t={tiers?.name} size={80} align="left" shadow />
    <Tagline t={tiers?.tagline} palette={palette} align="left" shadow />
    <Info t={tiers?.info} align="left" shadow />
    <Cta t={tiers?.cta} ctaStyle={tiers?.cta_style} palette={palette} shadow />
  </Stack>
);

const PhotoBacked: React.FC<CardProps> = ({tiers, palette}) => (
  <Stack gap={18}>
    <Name t={tiers?.name} shadow /><Tagline t={tiers?.tagline} palette={palette} shadow />
    <Info t={tiers?.info} shadow /><Cta t={tiers?.cta} ctaStyle={tiers?.cta_style} palette={palette} shadow />
  </Stack>
);

const MinimalBar: React.FC<CardProps> = ({tiers, palette}) => {
  const e = useStagger(4);
  return (
    <Stack gap={14}>
      <Name t={tiers?.name} size={56} shadow /><Tagline t={tiers?.tagline} palette={palette} shadow />
      <div style={{width: interpolate(e.s, [0, 1], [0, 120]), height: 4, borderRadius: 2,
        backgroundColor: accentOf(palette), margin: '6px 0'}} />
      <Info t={tiers?.info} shadow /><Cta t={tiers?.cta} ctaStyle={tiers?.cta_style} palette={palette} shadow />
    </Stack>
  );
};

const STYLES: Record<string, React.FC<CardProps>> = {glass: Glass, type_only: TypeOnly,
  photo_backed: PhotoBacked, minimal_bar: MinimalBar};
// old card_template names -> a style, so existing briefs still render
const TEMPLATE_ALIAS: Record<string, string> = {EndCard: 'glass', Title: 'glass', OfferBanner: 'type_only',
  PriceTag: 'glass', LocationPin: 'minimal_bar'};

export const Card: React.FC<CardProps & {template?: string}> = (props) => {
  const tiers = tiersFrom(props.tiers, props.text);
  const styleKey = props.style || (props.template ? TEMPLATE_ALIAS[props.template] : '') || 'glass';
  const Style = STYLES[styleKey] || Glass;
  // glass renders its own panel over a backdrop; the others sit over the photo (dimmed) or a gradient.
  const dim = styleKey === 'photo_backed' ? 0.4 : styleKey === 'glass' ? 0.7 : 0.5;
  return (
    <AbsoluteFill style={{backgroundColor: '#000'}}>
      <PhotoOrColor bg={props.bg} palette={props.palette} dim={dim} />
      <Style {...props} tiers={tiers} />
    </AbsoluteFill>
  );
};

// Backward-compat export (Adcomposition previously imported CARD_TEMPLATES[name]); every name now maps
// to the new Card via its style alias.
export const CARD_TEMPLATES: Record<string, React.FC<CardProps>> = new Proxy({}, {
  get: (_t, name: string) => (p: CardProps) => <Card {...p} template={name} />,
}) as any;
