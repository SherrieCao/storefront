"""Stage: Music — pick a royalty-free bed from a curated LIBRARY + beat grid (librosa) — D / E3.

Picks an instrumental bed from `assets/music_library/` matched to the Director's `pacing`/`mood`
(brisk/frenetic → high energy, so the bed never drags), instead of GENERATING one per run. The library
is seeded once (see `spikes/seed_music_library.py`) and committed; the operator can drop in their own
royalty-free tracks anytime by adding a file + a manifest entry. Beat grid is read from the manifest
(precomputed) or computed on the fly via librosa for operator-added tracks, then cached.

Runs after shots, before the editor plans the timeline (the editor snaps cuts to the beat grid and
ducks the bed under the voice). Free + instant at runtime (no API call). Stubs when the library is
empty: no music, empty beats → the editor renders exactly as before.

NOT for: footage (Seedance) or assembly (the editor).
"""
from __future__ import annotations
import json, shutil, subprocess
from pathlib import Path
from typing import Any
from . import config
from .tracing import Run

MUSIC_DIR = "music"
RESULT_FILE = "music/music.json"
# pacing -> preferred energy, then fallbacks. brisk/frenetic bias HIGH so the bed never feels slow.
_ENERGY_FOR_PACING = {"frenetic": "high", "brisk": "high", "measured": "mid", "lingering": "low"}
_ENERGY_FALLBACK = {"high": ["high", "mid", "low"], "mid": ["mid", "high", "low"],
                    "low": ["low", "mid", "high"]}


def run_music(run: Run, brief: dict[str, Any], *, use_cache: bool = False) -> dict[str, Any]:
    out_dir = run.dir / MUSIC_DIR
    out_dir.mkdir(parents=True, exist_ok=True)
    cache = run.dir / RESULT_FILE
    if use_cache and cache.exists():
        run.log("Music: loaded from cache"); return json.loads(cache.read_text())

    lib = _load_library()
    if not lib:
        run.log("Music: STUB (empty library) — no music bed, empty beat grid")
        result = {"music_path": None, "bpm": 0.0, "beats": []}
        cache.write_text(json.dumps(result, indent=2)); return result

    entry = _pick(lib, brief, run)
    src = Path(entry["_path"])
    track = out_dir / f"music{src.suffix}"
    shutil.copy2(src, track)

    bpm = float(entry.get("bpm") or 0.0)
    beats = list(entry.get("beats") or [])
    if not beats:                                   # operator-added track w/o precomputed grid
        bpm, beats = _beat_grid(str(track), out_dir)

    result = {"music_path": str(track), "bpm": round(bpm, 1), "beats": [round(b, 3) for b in beats],
              "track": entry.get("file"), "energy": entry.get("energy")}
    cache.write_text(json.dumps(result, indent=2))
    run.reason("Music", None, f"Library bed '{entry.get('file')}' ({entry.get('energy')} energy, "
               f"{bpm:.0f} BPM) for {brief.get('pacing','brisk')} pacing — {len(beats)} beats for "
               f"beat-synced cutting. (royalty-free; no per-run generation.)")
    run.log(f"Music: '{entry.get('file')}' — {entry.get('energy')} energy, {bpm:.0f} BPM, {len(beats)} beats")
    return result


def _load_library() -> list[dict[str, Any]]:
    """Read assets/music_library/manifest.json; keep entries whose file exists (abs path in `_path`)."""
    man = config.MUSIC_LIBRARY_DIR / "manifest.json"
    if not man.exists():
        return []
    out: list[dict[str, Any]] = []
    for e in json.loads(man.read_text()):
        p = config.MUSIC_LIBRARY_DIR / e.get("file", "")
        if p.exists():
            e = dict(e); e["_path"] = str(p); out.append(e)
    return out


def _pick(lib: list[dict], brief: dict[str, Any], run: Run) -> dict[str, Any]:
    """Pick by pacing→energy; rotate by run index so consecutive runs vary the bed."""
    pacing = str(brief.get("pacing") or "brisk").lower()
    want = _ENERGY_FOR_PACING.get(pacing, "high")
    for energy in _ENERGY_FALLBACK[want]:
        cands = [e for e in lib if e.get("energy") == energy]
        if cands:
            return cands[_run_index(run) % len(cands)]
    return lib[_run_index(run) % len(lib)]


def _run_index(run: Run) -> int:
    digits = "".join(c for c in str(getattr(run, "run_id", "0")) if c.isdigit())
    return int(digits) if digits else 0


def _beat_grid(track: str, out_dir) -> tuple[float, list[float]]:
    """librosa beat tracking → (bpm, beat timestamps). Resample to mono 22.05kHz wav first for a
    reliable backend. librosa 0.11 returns tempo as a 1-element array — coerce via atleast_1d."""
    try:
        import numpy as np, librosa
        wav = str(Path(out_dir) / "beat_22k.wav")
        subprocess.run(["ffmpeg", "-y", "-i", track, "-ar", "22050", "-ac", "1", wav], capture_output=True)
        y, sr = librosa.load(wav, sr=22050)
        tempo, frames = librosa.beat.beat_track(y=y, sr=sr)
        times = librosa.frames_to_time(frames, sr=sr)
        return float(np.atleast_1d(tempo)[0]), [float(t) for t in times]
    except Exception:
        return 0.0, []   # beat-sync becomes a no-op; music still plays
