# Spec — De-AI Vocal Performance (make the voice ITSELF sound human)

> Companion to SPEC_deai_voice.md (which covers the acoustic environment — room reverb, phone-mic
> EQ, room tone). This spec covers the VOICE ITSELF: cadence, breath, pitch variation, emphasis,
> the "TTS plateau" where every sentence sits at the same prosodic level. Three layers:
> A (script-as-direction), B (ElevenLabs v3 settings + audio tags), C (post-processing the
> waveform). Build A+B together (they're both in the voice generation call), then add C after
> hearing the combined result.

---

## LAYER A — Script-as-performance-direction (the biggest lever, zero cost)

### The problem
TTS reads what it's given. If the script is balanced, grammatically complete sentences of
similar length, TTS delivers them at the same energy, pace, and pitch — the "TTS plateau."
The script structure IS the performance direction.

### A1. Script formatting rules (add to Director scaffold + script_craft.md)

The Director's `speech` field (the actual text sent to TTS) should be formatted for SPEAKING,
not reading. Add these rules:

**Line breaks = breath points.** Break the script into short lines (1 idea per line, max ~8
words). TTS uses line breaks as natural pause points. Don't write a paragraph; write a poem.

**Punctuation = delivery cues:**
- `...` = trail off / hesitate ("You know that feeling when..." creates anticipation)
- `—` = abrupt stop / pivot ("Not the cheap kind — the real stuff.")
- `?` = upward inflection (even rhetorical questions change the energy)
- `!` = genuine emphasis (use sparingly — once per script max)
- `,` = micro-pause. Strategic commas create breathing room.

**Contractions mandatory.** "gonna" not "going to." "It's" not "it is." "Y'all" not "you all."
No one speaks in full formal English. Every uncontracted word is a tell.

**Fragments > complete sentences.** "Right off the 101. Ten minutes from the bridge." beats
"We're located right off the 101, just ten minutes from the bridge." Fragments force varied
delivery because TTS can't sustain a monotone across a 3-word fragment.

**Vary sentence length dramatically.** A 2-word line. Then a 12-word line that takes its time
and lets the thought develop. Then 4 words. The TTS follows the shape. If every line is 6-8
words, every line sounds the same.

**Start mid-thought.** Don't open with a complete setup sentence. "So this place—" or "Okay
but like—" or "That thing where—" These feel like joining a conversation, not starting a
presentation.

### A2. Example transformation

Before (current style, reads as TTS):
```
New this season at Conway Nail Bar.
Walk-ins welcome, gel sets from forty-five.
Come see why the neighborhood keeps coming back.
```

After (formatted for performance):
```
Okay so...
there's this spot right off the 101.
You walk in—
gel sets from forty-five.
And they actually remember your name?
Yeah.
That place.
```

Same info. Completely different delivery. The fragments, the trailing "so...", the dash-pivot,
the rhetorical question, the 1-word confirmation "Yeah." — these force TTS into varied cadence.

### A3. The Director/Concept must write SPOKEN text, not WRITTEN text
Reinforce in the Director scaffold's speech section:
> The `speech` field is NOT a script — it's what someone would actually SAY. Write it by
> saying it aloud first. If it sounds "writerly" (balanced clauses, complete thoughts, tidy
> structure), rewrite it as fragments and pivots. The TTS follows your formatting — give it
> something worth performing.

---

## LAYER B — ElevenLabs v3 audio tags + parameter tuning

### B1. Model + parameter settings (voice.py config)
Verify current settings and update:

```python
VOICE_MODEL = "eleven_v3"           # NOT v2/turbo — v3 is the most expressive
VOICE_STABILITY = 0.38              # lower = more varied (0.35-0.45 range; default 0.50 is too stable)
VOICE_SIMILARITY = 0.75             # keep reasonably high for voice consistency
VOICE_STYLE_EXAGGERATION = 0.35    # 30-45% for marketing; above 60% introduces artifacts
VOICE_MODE = "natural"              # v3 modes: "natural" | "creative" | "robust"
                                    # natural = best for conversational; creative = more dramatic;
                                    # robust = most consistent but least responsive to cues
```

The key change: **drop stability from whatever it currently is to ~0.38.** Higher stability =
more consistent = more monotone = more TTS-sounding. Lower stability lets the model vary its
delivery across phrases, which is what real voices do.

### B2. Audio tags (v3 feature — inject into the speech text)
ElevenLabs v3 interprets `[bracketed]` cues in the text. The Director (or a post-processing
step on the speech field) can insert these:

- `[casual]` or `[conversational]` at the start — sets the overall register
- `[laughs softly]` or `[chuckles]` — after a wry line (use sparingly, max once)
- `[sighs]` — before a reflective moment
- `[whispers]` — for an aside or intimate moment
- `[excited]` — for the hook or a genuine enthusiasm beat
- `[pause]` — explicit pause (v3 handles better than `...` in some cases)

**Do NOT overload.** One or two tags per script max. Every tag = a moment the voice "acts,"
and too many acting moments = obvious performance = TTS tell. The goal is 1-2 micro-moments
of genuine expression, not a full dramatic reading.

Implementation: add a light post-processing step in `voice.py` that takes the Director's
`speech` text and optionally inserts 1-2 audio tags at natural points. Or: teach the Director
to include them directly in the speech field (simpler, but risks overuse). I lean toward a
separate `_add_voice_tags(speech, voice_style)` function that inserts tags conservatively:

```python
def _add_voice_tags(speech: str, voice_style: str) -> str:
    """Insert 1-2 v3 audio tags at natural points. Conservative — less is more."""
    tagged = speech
    if voice_style in ("social_native", "influencer_pov"):
        # Add conversational register
        tagged = "[casual] " + tagged
    # Add ONE expressive moment if there's a natural spot
    # (e.g., after "..." or before a short punchy line)
    # ... light heuristic here, or just the register tag and nothing else
    return tagged
```

### B3. Voice selection matters
From the research: Voice selection matters more than most settings. Testing multiple voices with the same sentence can dramatically improve realism.

The pipeline currently uses a fixed voice (verify which). For local SMB ads, the voice should
match the business's vibe:
- Warm, slightly older female → salon, florist
- Upbeat younger → nail studio, cafe
- Calm, reassuring → daycare, cleaning

This is a voice_style → ElevenLabs voice_id mapping. Don't build a full voice-selection system
now, but add a `VOICE_MAP` in config with 2-3 voice_ids mapped to voice_style, so different
business types get different voices. Test a few ElevenLabs voices and pick ones that sound
least "announcer."

```python
VOICE_MAP = {
    "local_ad":        "voice_id_warm_neutral",
    "social_native":   "voice_id_casual_younger",
    "influencer_pov":  "voice_id_conversational",
    "default":         "voice_id_warm_neutral",
}
```

---

## LAYER C — Post-processing the vocal performance (ffmpeg/sox)

These address what TTS fundamentally can't: the micro-imperfections of a real human vocal
tract.

### C1. Pitch micro-variation (the "voice wobble")
Real voices have involuntary pitch instability — micro-variations of ±5-15 cents within and
across phrases. TTS pitch contours are unnaturally smooth.

Using `rubberband` (via ffmpeg or sox):
```bash
# Sox approach (more control):
sox input.wav output.wav pitch $(python3 -c "import random; print(random.randint(-8, 8))")
```

But pitch-shifting the whole file uniformly doesn't help — it needs to VARY over time. Better
approach: split the audio at phrase boundaries (using the word timestamps you already have),
apply a different subtle pitch shift to each phrase (±5-10 cents, random per phrase), then
rejoin. This simulates the natural pitch drift between phrases.

```python
def _pitch_vary(src, dst, word_timestamps):
    """Apply per-phrase pitch micro-variation."""
    phrases = _group_into_phrases(word_timestamps)  # split on gaps > 200ms
    segments = []
    for phrase in phrases:
        shift_cents = random.uniform(-10, 10)  # ±10 cents per phrase
        seg = _extract_segment(src, phrase.start, phrase.end)
        shifted = _pitch_shift(seg, shift_cents)  # rubberband or sox
        segments.append(shifted)
    _concatenate(segments, dst)
```

This is the most complex filter. Build it ONLY if Layers A+B don't close enough of the gap.

### C2. Timing perturbation (inter-phrase pause variation)
TTS delivers phrases with metronomically even pauses between them. Real speech has irregular
gaps — sometimes rushing into the next thought, sometimes hanging.

Using the word timestamps: identify inter-phrase gaps (>200ms), then randomly stretch/compress
each by ±15-25%:
```python
for gap in inter_phrase_gaps:
    factor = random.uniform(0.75, 1.25)
    gap.duration *= factor
```

Reconstruct the audio with the varied gaps (pad with silence or trim). This is doable with
ffmpeg `apad`/`atrim` or sox `pad`/`trim`. The word timestamps must be recalculated after
perturbation (for caption sync).

**Caution:** timestamp recalculation adds complexity. If captions drift, this filter is the
likely cause. Test carefully.

### C3. Breath insertion
Real speakers breathe between phrases. TTS often doesn't. Insert subtle breath sounds at
natural pause points.

Ship 3-4 short breath samples in `assets/breaths/`:
- `breath_short.wav` — quick inhale (~0.3s)
- `breath_medium.wav` — normal inhale (~0.5s)
- `breath_long.wav` — deep breath before a longer phrase (~0.7s)

Insert at inter-phrase gaps longer than ~400ms, choosing breath length proportional to the gap.
Mix at -18dB to -22dB (barely audible — just fills the silence with a human presence).

```python
for gap in inter_phrase_gaps:
    if gap.duration > 0.4:
        breath = random.choice(breath_samples)
        _insert_at(audio, gap.midpoint, breath, gain=-20)
```

**Source breaths:** record yourself taking 10 breaths into your phone (literally 30 seconds of
work), trim to individual inhales. Or source from freesound.org (CC0). They must be: phone-mic
quality (not studio), varied (not the same breath repeated), and very short.

### C4. Mouth sounds / micro-noise (optional, lowest priority)
Real speech has tiny mouth clicks, lip pops, and tongue sounds between words. TTS strips these.
This is the most subtle layer — skip unless A+B+C1-C3 still sound too clean.

If needed: source a "mouth noise" sample library (freesound.org has these) and randomly insert
at ~10% of word boundaries at very low volume (-24dB).

---

## Build order (critically important — don't build everything at once)

1. **Layer A (script formatting)** — scaffold changes only, zero cost. Run a test and LISTEN.
   This alone may close 50% of the gap. It's the most reliable lever because it controls the
   model's input, not its output.

2. **Layer B (v3 settings + audio tags + voice selection)** — voice.py config changes + the
   light `_add_voice_tags` function. Run a test and LISTEN again. A+B together should produce
   notably more human-sounding delivery.

3. **ASSESS:** is the voice now "good enough for a scrolling feed"? If yes, stop. Layers C1-C4
   are diminishing returns and add complexity (especially C2's timestamp recalculation).

4. **Layer C1 (pitch variation)** — only if A+B aren't enough. The per-phrase pitch shift is
   the most impactful C-layer filter.

5. **Layer C3 (breath insertion)** — easy to add alongside C1 if you're already splitting by
   phrase.

6. **Layer C2 (timing perturbation)** — most complex due to timestamp recalculation. Only if
   everything else still sounds metronomic.

7. **Layer C4 (mouth sounds)** — skip unless obsessive polish is needed.

---

## Config additions

```python
# Layer B — ElevenLabs v3 settings
VOICE_MODEL = "eleven_v3"
VOICE_STABILITY = 0.38
VOICE_SIMILARITY = 0.75
VOICE_STYLE_EXAGGERATION = 0.35
VOICE_MODE = "natural"
VOICE_MAP = {
    "local_ad": "...",
    "social_native": "...",
    "influencer_pov": "...",
    "default": "...",
}
VOICE_AUDIO_TAGS_ENABLED = True     # insert 1-2 v3 audio tags

# Layer C — vocal post-processing
DEAI_VOCAL_ENABLED = False          # off by default; enable after A+B assessment
DEAI_VOCAL_PITCH_RANGE_CENTS = 10   # ±10 cents per phrase
DEAI_VOCAL_PAUSE_VARIATION = 0.25   # ±25% inter-phrase gap variation
DEAI_VOCAL_BREATHS_ENABLED = True   # insert breaths at phrase gaps
```

Note: `DEAI_VOCAL_ENABLED` defaults to **False**. Layer C is opt-in after assessing A+B.

---

## Interaction with SPEC_deai_voice.md (the acoustic environment spec)

The two specs operate on different aspects of the same audio file:
- **Acoustic environment** (previous spec): room reverb, phone-mic EQ, room tone, compression
- **Vocal performance** (this spec): cadence, pitch, pauses, breaths, delivery

Processing order: **vocal performance first → acoustic environment second.** Reason: the room
reverb should apply to the already-varied voice (with pitch shifts and breaths), not to the
flat TTS output. If reversed, the reverb would be applied to metronomic delivery, which sounds
wrong.

```
TTS → [Layer A: script already formatted] → [Layer B: v3 settings applied at generation]
    → raw TTS file
    → [Layer C: pitch/pause/breath post-processing] → performance-corrected file
    → [Acoustic environment: reverb/EQ/room-tone/compression] → final VO file
```

---

## Acceptance checks
1. **Layer A:** the Director's `speech` output uses fragments, contractions, varied line lengths,
   strategic punctuation (... — ? !). No balanced complete sentences. Read it aloud — does it
   sound like a person or a copywriter?
2. **Layer B:** voice.py uses v3 with stability ~0.38, natural mode, 1-2 audio tags inserted.
   Side-by-side listen vs. the default settings: is delivery more varied?
3. **Layer B:** different voice_styles produce different ElevenLabs voices (via VOICE_MAP).
4. **Layer C (if enabled):** pitch varies between phrases (verify with a pitch-tracking tool or
   just listen — adjacent phrases should not be at exactly the same pitch level). Breaths are
   audible between phrases (barely — -20dB). Pauses between phrases are not metronomic.
5. **Combined (all layers + acoustic environment):** listen to the final VO in the assembled
   video. Does it sound like "a real person recorded this on their phone in the business"?
   That's the bar. Not "studio podcast" and not "bad phone call" — "decent phone, real person."
6. **Captions still sync** after any timing perturbation (Layer C2). This is the regression
   risk — verify explicitly.

## What this does NOT fix
- The voice TIMBRE (the fundamental quality of the synthesized voice). That's ElevenLabs'
  model quality — choose a good voice_id, but you can't post-process timbre convincingly.
- Content/meaning of the script (that's the Director + Concept stages).
- The acoustic environment (that's the companion spec).

## Guardrails
- Audio tags: MAX 2 per script. More = obvious performance = TTS tell.
- Pitch variation: MAX ±15 cents per phrase. More = sounds like a pitch-correction artifact.
- Breaths: -18dB or quieter. If you can consciously hear the breath, it's too loud.
- Stability: don't go below 0.30 — too unstable produces artifacts and weird emphasis.
- Layer C defaults to OFF. Assess A+B first. Don't pre-commit to building all of Layer C.
- The speech-to-speech path (human performs → ElevenLabs converts) remains the nuclear option
  for maximum authenticity. Note it; don't build it in this spec.
