// Edit-plan schema the renderer consumes (produced by the Editor Agent).
import {OverlaySpec} from './Overlay';
export type SegmentType = 'seedance_shot' | 'real_clip' | 'moodboard' | 'card';
export type Transition = 'hard_cut' | 'crossfade' | 'dip_to_black' | 'slide' | 'whip' | 'zoom'
  | 'speed_ramp_in' | 'scale_reveal' | 'light_leak'; // design-system Batch C

export type Segment = {
  type: SegmentType;
  duration_s: number;
  src?: string; // staticFile name for seedance_shot / real_clip / moodboard keyframe
  trim_s?: [number, number]; // real_clip trim window
  playback_rate?: number; // speed-ramp for seedance_shot / real_clip (energy)
  motion?: 'punch_in' | 'parallax' | 'handheld_jitter' | 'scale_breath' | 'drift'; // kinetic treatment for video (Ken Burns is automatic on moodboard)
  overlay?: OverlaySpec; // lower-third / badge motion graphic on top of this segment
  card_template?: string; // legacy: EndCard | PriceTag | LocationPin | OfferBanner | Title (aliased to a style)
  card_style?: string;    // glass | type_only | photo_backed | minimal_bar
  card_tiers?: {name?: string; tagline?: string; info?: string; cta?: string; cta_style?: string};
  card_text?: string;     // legacy flat string ("Name | Location | Book") — still rendered (name + info)
  card_animation?: string; // scale_pop | slide_in | fade
  bg_src?: string; // staticFile name for a card's photo background
  transition_in?: Transition;
};

export type Caption = {text: string; start_s: number; end_s: number};
export type Word = {w: string; start_s: number; end_s: number};

export type EditPlan = {
  fps: number;
  width: number;
  height: number;
  segments: Segment[];
  audio?: {src: string; gain?: number} | null;
  music?: {src: string; gain?: number} | null; // mood bed ducked under the voice (beat-synced cuts)
  captions?: Caption[];
  words?: Word[]; // word-level timings for kinetic captions
  caption_style?: string; // clean_pop | emphasis
  palette?: string[]; // brand palette hex colors (card accents)
};

export const DEFAULT_PLAN: EditPlan = {
  fps: 30,
  width: 1080,
  height: 1920,
  segments: [
    {type: 'seedance_shot', src: 'clip1.mp4', duration_s: 3.5, transition_in: 'hard_cut'},
    {type: 'moodboard', src: 'moodboard1.png', duration_s: 3, transition_in: 'crossfade'},
    {type: 'card', card_template: 'OfferBanner', card_text: 'Right off the 101 — walk-ins welcome', duration_s: 2.5, transition_in: 'crossfade'},
  ],
  audio: {src: 'voiceover.mp3', gain: 1},
  captions: [
    {text: 'Right off the 101.', start_s: 0, end_s: 2.2},
    {text: 'Drop your pup with people who know them.', start_s: 2.2, end_s: 5.5},
    {text: "Carol's Dog Daycare — walk-ins welcome.", start_s: 5.5, end_s: 9},
  ],
};
