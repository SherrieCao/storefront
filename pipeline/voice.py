"""Stage: Voice (one MiniMax TTS call on fal) — clean voiceover + per-line caption timing.

A single fal call (fal-ai/minimax/speech-02-hd) turns the Director's `speech` into a clean mp3 —
fixing the robotic native Seedance voice (D8). Voice direction (speed/emotion) comes from the
Director's pacing/mood.

Line-level timestamps: the fal endpoint returns only {audio, duration_ms} (subtitle_enable is
silently ignored — verified, docs/voice_findings.md), so we DERIVE per-line timing locally: split
`speech` into sentences and distribute duration_ms weighted by character count. The Editor consumes
{audio_path, duration_ms, lines:[{text,start_s,end_s}]} and never assumes fal provided timing.

Stubs offline (no FAL_KEY): a real silent mp3 of estimated duration + evenly-split line timings, so
the Editor still assembles end-to-end.

NOT for: creative decisions or assembly.
"""
from __future__ import annotations
import json, re, subprocess, urllib.request
from typing import Any
from . import config, budget
from .tracing import Run

VOICE_DIR = "06_voice"
RESULT_FILE = "06_voice/voice.json"
_WORDS_PER_SEC = 3.3   # spike calibration: ~30 words -> 9.0s


def run_voice(run: Run, brief: dict[str, Any], *, use_cache: bool = False) -> dict[str, Any]:
    out_dir = run.dir / VOICE_DIR
    out_dir.mkdir(parents=True, exist_ok=True)
    cache = run.dir / RESULT_FILE
    if use_cache and cache.exists():
        run.log("Voice: loaded from cache"); return json.loads(cache.read_text())

    text = (brief.get("speech") or brief.get("script") or "").strip()
    mp3 = out_dir / "voiceover.mp3"
    speed = _speed_for(brief.get("pacing"))
    emotion = _emotion_for(brief.get("mood", ""))

    if not text:
        run.log("Voice: no speech in brief — empty track")
        result = {"audio_path": None, "duration_ms": 0, "lines": []}
        cache.write_text(json.dumps(result, indent=2)); return result

    if not config.FAL_KEY:
        duration_ms = int(len(text.split()) / _WORDS_PER_SEC * 1000)
        _silent_mp3(str(mp3), duration_ms / 1000)
        run.log(f"Voice: STUB silent mp3 (~{duration_ms/1000:.1f}s est for {len(text.split())} words)")
    else:
        budget.check_ceiling(run, budget.tts_call(len(text)), "voice")
        import fal_client
        res = fal_client.subscribe(config.MODEL_ROUTER["tts"], arguments={
            "text": text, "voice_id": "Wise_Woman", "speed": speed, "emotion": emotion,
            "output_format": "url"}, with_logs=False)
        duration_ms = int(res.get("duration_ms") or 0)
        urllib.request.urlretrieve(res["audio"]["url"], mp3)
        run.add_cost("voice", budget.tts_call(len(text)))
        run.trace({"step": "voice", "type": "fal_output", "duration_ms": duration_ms,
                   "url": res["audio"]["url"]})
        run.log(f"Voice: rendered {duration_ms/1000:.1f}s (speed={speed}, emotion={emotion})")

    lines = _line_timings(text, duration_ms)
    result = {"audio_path": str(mp3), "duration_ms": duration_ms, "lines": lines,
              "voice_id": "Wise_Woman", "speed": speed, "emotion": emotion}
    cache.write_text(json.dumps(result, indent=2))
    run.reason("Voice", None,
               f"One MiniMax TTS call ({duration_ms/1000:.1f}s); {len(lines)} caption lines timed "
               f"locally (char-weighted) since fal returns no timestamps.")
    return result


def _line_timings(text: str, duration_ms: int) -> list[dict[str, Any]]:
    """Split into sentences and distribute the total duration weighted by character count — the
    local caption timing the Editor uses (fal gives no per-line timestamps)."""
    parts = [s.strip() for s in re.split(r"(?<=[.!?])\s+", text) if s.strip()]
    if not parts:
        return []
    total_chars = sum(len(p) for p in parts) or 1
    dur_s = duration_ms / 1000.0
    out, cursor = [], 0.0
    for p in parts:
        span = dur_s * (len(p) / total_chars)
        out.append({"text": p, "start_s": round(cursor, 2), "end_s": round(cursor + span, 2)})
        cursor += span
    if out:
        out[-1]["end_s"] = round(dur_s, 2)   # snap the last line to the true end
    return out


def _speed_for(pacing: str | None) -> float:
    p = (pacing or "").lower()
    if "frenetic" in p: return 1.15
    if "brisk" in p:    return 1.05
    if "lingering" in p: return 0.9
    return 1.0


def _emotion_for(mood: str) -> str:
    m = mood.lower()
    if any(w in m for w in ("warm", "upbeat", "happy", "playful", "fun", "comedic")): return "happy"
    if any(w in m for w in ("calm", "soothing", "gentle")):                            return "neutral"
    return "neutral"


def _silent_mp3(dst: str, dur_s: float) -> None:
    subprocess.run(["ffmpeg", "-y", "-f", "lavfi", "-i", "anullsrc=r=44100:cl=mono",
                    "-t", f"{max(0.5, dur_s):.2f}", "-q:a", "9", dst], capture_output=True)
