"""Stage: Music (CassetteAI on fal) + beat detection (librosa) — Phase 2 / Workstream D.

Generates a royalty-free, instrumental-only, mood-matched bed (prompt from the Director's mood/
editing_feel) at the ad's length, then extracts the BEAT GRID (librosa) so the editor can snap cuts ON
the beat and duck the music under the voice. Runs after shots, before the editor plans the timeline.
(CassetteAI replaced Beatoven, whose fal endpoint submitted but hung in Queued forever — see findings.)

Bright line holds: this is NOT footage generation — it's audio + an analysis grid the editor uses.
Stubs offline (no FAL_KEY): no music, empty beat grid → the editor renders exactly as before.

NOT for: footage (Seedance) or assembly (the editor).
"""
from __future__ import annotations
import json, subprocess, urllib.request
from typing import Any
from . import config, budget
from .tracing import Run

MUSIC_DIR = "music"
RESULT_FILE = "music/music.json"


def run_music(run: Run, brief: dict[str, Any], *, use_cache: bool = False) -> dict[str, Any]:
    out_dir = run.dir / MUSIC_DIR
    out_dir.mkdir(parents=True, exist_ok=True)
    cache = run.dir / RESULT_FILE
    if use_cache and cache.exists():
        run.log("Music: loaded from cache"); return json.loads(cache.read_text())

    target_s = max(5.0, min(150.0, float(brief.get("total_duration_s") or config.MIN_DURATION_S)))
    prompt = _music_prompt(brief)

    if not config.FAL_KEY:
        run.log("Music: STUB (no FAL_KEY) — no music bed, empty beat grid")
        result = {"music_path": None, "bpm": 0.0, "beats": []}
        cache.write_text(json.dumps(result, indent=2)); return result

    budget.check_ceiling(run, config.MUSIC_COST, "music")
    import fal_client
    res = fal_client.subscribe(config.MODEL_ROUTER["music"], arguments={
        "prompt": prompt, "duration": int(round(target_s))}, with_logs=False)
    run.add_cost("music", config.MUSIC_COST)
    url = _audio_url(res)
    if not url:
        run.log(f"Music: no audio in response ({list(res.keys())}) — proceeding without music")
        result = {"music_path": None, "bpm": 0.0, "beats": []}
        cache.write_text(json.dumps(result, indent=2)); return result
    track = out_dir / ("music.wav" if ".wav" in url else "music.mp3")
    urllib.request.urlretrieve(url, track)
    run.trace({"step": "music", "type": "fal_output", "prompt": prompt, "url": url})

    bpm, beats = _beat_grid(str(track), out_dir)
    result = {"music_path": str(track), "bpm": round(bpm, 1), "beats": [round(b, 3) for b in beats],
              "prompt": prompt}
    cache.write_text(json.dumps(result, indent=2))
    run.reason("Music", None, f"Beatoven instrumental ({target_s:.0f}s) — '{prompt}'. "
               f"librosa: {bpm:.0f} BPM, {len(beats)} beats for beat-synced cutting.")
    run.log(f"Music: {bpm:.0f} BPM, {len(beats)} beats")
    return result


def _music_prompt(brief: dict[str, Any]) -> str:
    mood = brief.get("mood", "") or "warm, upbeat"
    feel = brief.get("editing_feel", "") or ""
    pacing = brief.get("pacing", "brisk")
    # CassetteAI is instrumental-only, but state "no vocals" explicitly so it never sings over the VO.
    return (f"{mood}. Instrumental background music for a {pacing}, social-media short ad. "
            f"{feel} No vocals, no spoken word, no lyrics; sits under a voiceover.").strip()


def _beat_grid(track: str, out_dir) -> tuple[float, list[float]]:
    """librosa beat tracking → (bpm, beat timestamps). Resample to a mono 22.05kHz wav first for a
    reliable backend. librosa 0.11 returns tempo as a 1-element array, so coerce via atleast_1d."""
    try:
        import numpy as np, librosa
        wav = str(out_dir / "beat_22k.wav")
        subprocess.run(["ffmpeg", "-y", "-i", track, "-ar", "22050", "-ac", "1", wav], capture_output=True)
        y, sr = librosa.load(wav, sr=22050)
        tempo, frames = librosa.beat.beat_track(y=y, sr=sr)
        times = librosa.frames_to_time(frames, sr=sr)
        return float(np.atleast_1d(tempo)[0]), [float(t) for t in times]
    except Exception:
        return 0.0, []   # beat-sync becomes a no-op; music still plays


def _audio_url(res: dict[str, Any]) -> str | None:
    a = res.get("audio")
    if isinstance(a, dict) and a.get("url"):
        return a["url"]
    if isinstance(a, str):
        return a
    for k in ("audio_url", "url", "audio_file"):
        v = res.get(k)
        if isinstance(v, dict) and v.get("url"):
            return v["url"]
        if isinstance(v, str):
            return v
    return None
