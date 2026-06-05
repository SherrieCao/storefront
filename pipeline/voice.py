"""Stage: Voice (ElevenLabs TTS on fal) — voiceover fit to the assembled timeline, real timestamps.

Visuals-first spine: the editor fixes the visual timeline to the Director's `total_duration_s` FIRST,
then this stage generates the voice to FIT that timeline (length `timeline.total_s`). ElevenLabs
eleven-v3 returns word/character-level timestamps (`timestamps: true`), so caption lines are timed to
the real audio (not estimated), and the voice never outlasts the video.

If the render overshoots the timeline, re-render once at a higher (clamped) speed; ElevenLabs `speed`
caps at 1.2, so the Director also sizes the script to the duration (scaffold) to fit naturally.

Stubs offline (no FAL_KEY): a silent mp3 of `total_s` + evenly-split lines, so the Editor still runs.

NOT for: creative decisions or assembly.
"""
from __future__ import annotations
import json, re, subprocess, urllib.request
from typing import Any
from . import config, budget
from .tracing import Run

VOICE_DIR = "06_voice"
RESULT_FILE = "06_voice/voice.json"
_DEFAULT_VOICE = "Laura"      # general fallback (see _select_voice)

# --- Voice routing (operator policy): gender > region > vertical --------------------------------
# All voices are eleven-v3 named presets (each verified to return timestamps). stability per voice
# tunes delivery: lower = more expressive (energetic), higher = smoother/steadier (calming). The old
# flat "Rachel" @0.5 read as DULL — this picks a voice + expressiveness that fits the business.
_SOUTHERN_STATES = {  # 2-letter codes + full names, lowercased; matched against the location string
    "tx", "fl", "ga", "nc", "sc", "tn", "al", "ms", "la", "ar", "ky", "va", "wv", "ok",
    "texas", "florida", "georgia", "north carolina", "south carolina", "tennessee", "alabama",
    "mississippi", "louisiana", "arkansas", "kentucky", "virginia", "west virginia", "oklahoma"}
# vertical/audience keyword groups (matched against business NAME + operator BRIEF, lowercased)
_MALE_CASUAL  = ("fitness", "gym", "crossfit", "barber", "barbershop", "food truck", "skate",
                 "tattoo", "brewery", "sports bar", "smoke shop")
_MALE_PREMIUM = ("dealership", "car dealer", "auto ", "automotive", "motors", "steakhouse",
                 "fine dining", "whiskey", "cigar", "golf", "watch ", "menswear")
_MASSAGE      = ("massage", "therapy", "therapist", "chiropract", "physio", "acupunctur")
_SPA          = ("spa", "wellness", "skincare", "facial", "yoga", "pilates", "sauna", "medspa", "med spa")
_FAMILY       = ("bakery", "daycare", "day care", "florist", "flower", "preschool", "children", "family")
_TECH         = ("tech", "software", "saas", " app", "startup", "cybersecurity", "it services")
# voice -> stability (expressiveness). Energetic 0.3 · calming 0.5 · warm/neutral 0.4.
_STABILITY = {"Will": 0.3, "Charlie": 0.3, "Aria": 0.3, "Laura": 0.35,
              "Jessica": 0.5, "Sarah": 0.5, "Matilda": 0.4, "River": 0.4}


def _select_voice(inventory: dict[str, Any]) -> tuple[str, float]:
    """Pick the TTS voice from the business, by operator policy: GENDER > REGION > VERTICAL.
    Reads the business NAME + operator BRIEF (the source of truth for what the business is) and the
    LOCATION; never the generated script (which could spuriously match). Returns (voice, stability)."""
    text = " ".join([str(inventory.get("business") or ""), str(inventory.get("brief") or "")]).lower()
    loc = str(inventory.get("location") or "").lower()
    state = loc.split(",")[-1].strip()
    in_south = state in _SOUTHERN_STATES or any(s in loc for s in _SOUTHERN_STATES if len(s) > 3)

    def has(words: tuple[str, ...]) -> bool:
        return any(w in text for w in words)

    if has(_MALE_CASUAL):       voice = "Will"        # 1. gender (male-target) — top priority
    elif has(_MALE_PREMIUM):    voice = "Charlie"
    elif in_south:              voice = "Aria"        # 2. region
    elif has(_MASSAGE):         voice = "Jessica"     # 3. vertical
    elif has(_SPA):             voice = "Sarah"
    elif has(_FAMILY):          voice = "Matilda"
    elif has(_TECH):            voice = "River"
    else:                       voice = _DEFAULT_VOICE  # 4. default
    return voice, _STABILITY.get(voice, 0.35)


# --- Non-verbal audio tags (D48) ---------------------------------------------------------------
# ElevenLabs v3 renders inline [bracketed] cues. PERFORMED-EMOTION/delivery tags land convincingly;
# synthetic body-sounds ([exhales]/[sighs]/[breathes]) read as FAKE (operator-verified) and are BANNED.
# Cap: ONE tag per script (more = obvious performance = a TTS tell). The fal endpoint echoes tags into the
# timestamp stream, so captions must strip them (_drop_tag_chars) — else "[excited]" shows on screen.
_TAG_RE = re.compile(r"\[([^\[\]]+)\]")
_VOICE_TAG_WHITELIST = {"excited", "laughs", "laughs softly", "chuckles", "casual",
                        "conversational", "warmly", "whispers"}


def _sanitize_voice_tags(speech: str) -> str:
    """Enforce the audio-tag policy on the Director's speech before TTS: keep only ONE whitelisted
    performed-emotion tag, drop the rest (banned body-sounds + any excess). Belt-and-suspenders over the
    Director scaffold's gating. If tags are disabled, strip them all."""
    if not config.VOICE_AUDIO_TAGS_ENABLED:
        return re.sub(r"\s{2,}", " ", _TAG_RE.sub("", speech)).strip()
    kept = 0
    def repl(m: "re.Match") -> str:
        nonlocal kept
        if kept == 0 and m.group(1).strip().lower() in _VOICE_TAG_WHITELIST:
            kept += 1
            return m.group(0)        # keep this one (sent to TTS to be performed)
        return ""                    # drop banned (e.g. [exhales]) or excess tags
    return re.sub(r"\s{2,}", " ", _TAG_RE.sub(repl, speech)).strip()


def _strip_tags(text: str) -> str:
    return re.sub(r"\s{2,}", " ", _TAG_RE.sub("", text)).strip()


def _drop_tag_chars(chars: list, starts: list, ends: list) -> tuple[list, list, list]:
    """Remove v3 audio-tag spans ('[laughs softly]') from the char timeline so tags never reach captions.
    The tag still occupies audio time (the voice performed it) — only the displayed text/words drop it."""
    out_c, out_s, out_e, in_tag = [], [], [], False
    for ch, s, e in zip(chars, starts, ends):
        if ch == "[":
            in_tag = True; continue
        if ch == "]":
            in_tag = False; continue
        if not in_tag:
            out_c.append(ch); out_s.append(s); out_e.append(e)
    return out_c, out_s, out_e


def run_voice(run: Run, brief: dict[str, Any], timeline: dict[str, Any],
              inventory: dict[str, Any] | None = None, *, use_cache: bool = False) -> dict[str, Any]:
    out_dir = run.dir / VOICE_DIR
    out_dir.mkdir(parents=True, exist_ok=True)
    cache = run.dir / RESULT_FILE
    if use_cache and cache.exists():
        run.log("Voice: loaded from cache"); return json.loads(cache.read_text())

    text = (brief.get("speech") or brief.get("script") or "").strip()
    text = _sanitize_voice_tags(text)   # ≤1 whitelisted performed-emotion tag; bans [exhales] etc. (D48)
    target_s = float(timeline.get("total_s") or brief.get("total_duration_s") or config.MIN_DURATION_S)
    mp3 = out_dir / "voiceover.mp3"
    voice_id, stability = _select_voice(inventory or {})   # gender > region > vertical (operator policy)

    if not text:
        run.log("Voice: no speech in brief — empty track")
        result = {"audio_path": None, "duration_ms": 0, "lines": []}
        cache.write_text(json.dumps(result, indent=2)); return result

    if not config.FAL_KEY:
        stub_s = target_s * config.VOICE_STUB_DURATION_MULT  # test seam: >1.2 reproduces a voice crush (D51)
        _silent_mp3(str(mp3), stub_s)
        clean = _strip_tags(text)                          # stub captions: no audio model to perform tags
        lines = _even_lines(clean, stub_s)
        words = _even_words(clean, stub_s)
        run.log(f"Voice: STUB silent mp3 ({stub_s:.1f}s, {len(lines)} lines)")
        result = {"audio_path": str(mp3), "duration_ms": int(stub_s * 1000),
                  "lines": lines, "words": words}
        cache.write_text(json.dumps(result, indent=2)); return result

    # Generate ONE natural take. The editor time-stretches it (ffmpeg atempo, pitch-preserving) to fit
    # the fixed video length, so we don't fight ElevenLabs' 1.2 speed cap here.
    run.log(f"Voice: '{voice_id}' (stability {stability}) — by policy gender>region>vertical")
    lines, words, dur_s = _eleven_render(run, text, str(mp3), 1.0, voice_id, stability)
    if dur_s > target_s * 1.6:
        run.log(f"Voice: {dur_s:.1f}s for a {target_s:.0f}s ad — editor atempo caps at "
                f"{config.VOICE_MAX_ATEMPO}× (Director should shorten the script).")

    result = {"audio_path": str(mp3), "duration_ms": int(dur_s * 1000), "lines": lines,
              "words": words, "voice": voice_id, "stability": stability, "timeline_total_s": target_s}
    cache.write_text(json.dumps(result, indent=2))
    run.reason("Voice", None,
               f"ElevenLabs '{voice_id}' take ({dur_s:.1f}s, stability {stability}); the editor will "
               f"atempo-fit it to the {target_s:.1f}s timeline. {len(lines)} caption lines from real "
               f"word timestamps.")
    run.log(f"Voice: {dur_s:.1f}s natural, {len(lines)} lines (editor will fit to {target_s:.1f}s)")
    return result


def _eleven_render(run: Run, text: str, dst: str, speed: float, voice: str = _DEFAULT_VOICE,
                   stability: float = 0.35) -> tuple[list[dict], list[dict], float]:
    """One ElevenLabs call (timestamps on). Saves the mp3, returns (caption lines, words, duration_s)."""
    budget.check_ceiling(run, budget.tts_call(len(text)), "voice")
    import fal_client
    res = fal_client.subscribe(config.MODEL_ROUTER["tts"], arguments={
        "text": text, "voice": voice, "stability": stability, "speed": speed,
        "timestamps": True}, with_logs=False)
    run.add_cost("voice", budget.tts_call(len(text)))
    audio = res.get("audio")
    url = audio.get("url") if isinstance(audio, dict) else audio
    urllib.request.urlretrieve(url, dst)
    run.trace({"step": "voice", "type": "fal_output", "speed": speed, "url": url})
    chunks = res.get("timestamps") or []
    lines = _lines_from_timestamps(chunks)
    words = _words_from_timestamps(chunks)
    dur_s = _duration(dst) or (lines[-1]["end_s"] if lines else 0.0)
    return lines, words, dur_s


def _words_from_timestamps(chunks: list[dict]) -> list[dict[str, Any]]:
    """Per-WORD timings (for kinetic captions) from the char-level timestamps: flatten chars, split on
    whitespace, each word timed first-char-start → last-char-end."""
    chars, starts, ends = [], [], []
    for c in chunks:
        chars += (c.get("characters") or [])
        starts += (c.get("character_start_times_seconds") or [])
        ends += (c.get("character_end_times_seconds") or [])
    chars, starts, ends = _drop_tag_chars(chars, starts, ends)   # tags never reach captions (D48)
    n = min(len(chars), len(starts), len(ends))
    out, buf, first = [], "", None
    for i in range(n):
        ch = chars[i]
        if ch.strip() == "":
            if buf:
                out.append({"w": buf, "start_s": round(starts[first], 2), "end_s": round(ends[i - 1], 2)})
                buf, first = "", None
            continue
        if first is None:
            first = i
        buf += ch
    if buf and first is not None:
        out.append({"w": buf, "start_s": round(starts[first], 2), "end_s": round(ends[n - 1], 2)})
    return out


def _lines_from_timestamps(chunks: list[dict]) -> list[dict[str, Any]]:
    """Reconstruct per-sentence caption lines from ElevenLabs char-level timestamps. Flattens the
    chunked character arrays, then splits into sentences on . ! ? — each line timed by its first
    char's start and last char's end (real audio timing, no estimate)."""
    chars: list[str] = []
    starts: list[float] = []
    ends: list[float] = []
    for c in chunks:
        cs = c.get("characters") or []
        chars += cs
        starts += (c.get("character_start_times_seconds") or [])
        ends += (c.get("character_end_times_seconds") or [])
    chars, starts, ends = _drop_tag_chars(chars, starts, ends)   # tags never reach captions (D48)
    n = min(len(chars), len(starts), len(ends))
    if not n:
        return []
    lines: list[dict[str, Any]] = []
    buf, first = "", None
    for i in range(n):
        ch = chars[i]
        if buf == "" and ch.strip() == "":
            continue                                  # skip leading whitespace
        if first is None:
            first = i
        buf += ch
        if ch in ".!?" and (i + 1 >= n or chars[i + 1].strip() == "" or chars[i + 1] in ".!?"):
            lines.append({"text": buf.strip(), "start_s": round(starts[first], 2),
                          "end_s": round(ends[i], 2)})
            buf, first = "", None
    if buf.strip() and first is not None:
        lines.append({"text": buf.strip(), "start_s": round(starts[first], 2),
                      "end_s": round(ends[n - 1], 2)})
    return lines


def _even_lines(text: str, total_s: float) -> list[dict[str, Any]]:
    """Offline stub: split into sentences, distribute total_s by character count."""
    parts = [s.strip() for s in re.split(r"(?<=[.!?])\s+", text) if s.strip()]
    if not parts:
        return []
    total_chars = sum(len(p) for p in parts) or 1
    out, cursor = [], 0.0
    for p in parts:
        span = total_s * (len(p) / total_chars)
        out.append({"text": p, "start_s": round(cursor, 2), "end_s": round(cursor + span, 2)})
        cursor += span
    if out:
        out[-1]["end_s"] = round(total_s, 2)
    return out


def _even_words(text: str, total_s: float) -> list[dict[str, Any]]:
    """Offline stub: evenly distribute words across total_s (so kinetic captions still render)."""
    ws = text.split()
    if not ws:
        return []
    step = total_s / len(ws)
    return [{"w": w, "start_s": round(i * step, 2), "end_s": round((i + 1) * step, 2)}
            for i, w in enumerate(ws)]


def _silent_mp3(dst: str, dur_s: float) -> None:
    subprocess.run(["ffmpeg", "-y", "-f", "lavfi", "-i", "anullsrc=r=44100:cl=mono",
                    "-t", f"{max(0.5, dur_s):.2f}", "-q:a", "9", dst], capture_output=True)


def _duration(path: str) -> float | None:
    try:
        r = subprocess.run(["ffprobe", "-v", "error", "-show_entries", "format=duration",
                            "-of", "default=nw=1:nk=1", path], capture_output=True, text=True, timeout=10)
        return float(r.stdout.strip())
    except Exception:
        return None
