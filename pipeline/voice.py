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
_VOICE_ID = "Rachel"


def run_voice(run: Run, brief: dict[str, Any], timeline: dict[str, Any],
              *, use_cache: bool = False) -> dict[str, Any]:
    out_dir = run.dir / VOICE_DIR
    out_dir.mkdir(parents=True, exist_ok=True)
    cache = run.dir / RESULT_FILE
    if use_cache and cache.exists():
        run.log("Voice: loaded from cache"); return json.loads(cache.read_text())

    text = (brief.get("speech") or brief.get("script") or "").strip()
    target_s = float(timeline.get("total_s") or brief.get("total_duration_s") or config.MIN_DURATION_S)
    mp3 = out_dir / "voiceover.mp3"

    if not text:
        run.log("Voice: no speech in brief — empty track")
        result = {"audio_path": None, "duration_ms": 0, "lines": []}
        cache.write_text(json.dumps(result, indent=2)); return result

    if not config.FAL_KEY:
        _silent_mp3(str(mp3), target_s)
        lines = _even_lines(text, target_s)
        run.log(f"Voice: STUB silent mp3 ({target_s:.1f}s, {len(lines)} lines)")
        result = {"audio_path": str(mp3), "duration_ms": int(target_s * 1000), "lines": lines}
        cache.write_text(json.dumps(result, indent=2)); return result

    # Generate ONE natural take. The editor time-stretches it (ffmpeg atempo, pitch-preserving) to fit
    # the fixed video length, so we don't fight ElevenLabs' 1.2 speed cap here.
    lines, dur_s = _eleven_render(run, text, str(mp3), 1.0)
    if dur_s > target_s * 1.6:
        run.log(f"Voice: {dur_s:.1f}s for a {target_s:.0f}s ad — editor atempo caps at "
                f"{config.VOICE_MAX_ATEMPO}× (Director should shorten the script).")

    result = {"audio_path": str(mp3), "duration_ms": int(dur_s * 1000), "lines": lines,
              "voice": _VOICE_ID, "timeline_total_s": target_s}
    cache.write_text(json.dumps(result, indent=2))
    run.reason("Voice", None,
               f"ElevenLabs natural take ({dur_s:.1f}s); the editor will atempo-fit it to the "
               f"{target_s:.1f}s timeline. {len(lines)} caption lines from real word timestamps.")
    run.log(f"Voice: {dur_s:.1f}s natural, {len(lines)} lines (editor will fit to {target_s:.1f}s)")
    return result


def _eleven_render(run: Run, text: str, dst: str, speed: float) -> tuple[list[dict], float]:
    """One ElevenLabs call (timestamps on). Saves the mp3, returns (caption lines, duration_s)."""
    budget.check_ceiling(run, budget.tts_call(len(text)), "voice")
    import fal_client
    res = fal_client.subscribe(config.MODEL_ROUTER["tts"], arguments={
        "text": text, "voice": _VOICE_ID, "stability": 0.5, "speed": speed,
        "timestamps": True}, with_logs=False)
    run.add_cost("voice", budget.tts_call(len(text)))
    audio = res.get("audio")
    url = audio.get("url") if isinstance(audio, dict) else audio
    urllib.request.urlretrieve(url, dst)
    run.trace({"step": "voice", "type": "fal_output", "speed": speed, "url": url})
    lines = _lines_from_timestamps(res.get("timestamps") or [])
    dur_s = _duration(dst) or (lines[-1]["end_s"] if lines else 0.0)
    return lines, dur_s


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
