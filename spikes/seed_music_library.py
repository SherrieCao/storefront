"""ONE-TIME seeder for assets/music_library/ (E3). Generates a few royalty-free, instrumental,
UP-TEMPO beds (CassetteAI on fal), measures real BPM/beats with librosa, and writes manifest.json.
Runtime (pipeline/music.py) then PICKS from these — it never generates. Re-run only to add/refresh
tracks. The operator can also drop their own royalty-free files in + add a manifest entry by hand.

Run:  PYTHONPATH=. ./.venv/bin/python spikes/seed_music_library.py
"""
import json, subprocess, urllib.request
from pathlib import Path
from pipeline import config
from pipeline import music as music_

LIB = config.MUSIC_LIBRARY_DIR
LIB.mkdir(parents=True, exist_ok=True)
DUR = config.MAX_DURATION_S   # cover the longest ad; shorter ads just use the head

# intended energy + a fast-tempo prompt (CassetteAI is instrumental-only; we still say "no vocals").
SPECS = [
    ("track_upbeat_pop.mp3", "high", ["warm", "happy", "feel_good"],
     "upbeat warm acoustic indie pop, bright and cheerful, driving FAST tempo around 124 BPM, claps and "
     "light percussion, energetic feel-good, instrumental, no vocals no lyrics"),
    ("track_punchy_electro.mp3", "high", ["modern", "confident", "hype"],
     "energetic modern pop with electronic elements, punchy FAST tempo around 128 BPM, bright synths and "
     "a driving beat, confident and hype, instrumental, no vocals no lyrics"),
    ("track_warm_groove.mp3", "mid", ["warm", "friendly", "relaxed"],
     "warm friendly acoustic groove, medium-up tempo around 108 BPM, positive and relaxed, light guitar "
     "and soft percussion, instrumental, no vocals no lyrics"),
]
SOURCE = "cassetteai/music-generator (fal) — generated for this project"
LICENSE = "Royalty-free for commercial use (fal/CassetteAI output). No attribution required."

assert config.FAL_KEY, "FAL_KEY required to seed the library"
import fal_client

manifest = []
for fname, energy, tags, prompt in SPECS:
    dst = LIB / fname
    print(f"\n=== {fname} ({energy}) ===\n  prompt: {prompt[:70]}...", flush=True)
    res = fal_client.subscribe("cassetteai/music-generator",
                               arguments={"prompt": prompt, "duration": int(DUR)}, with_logs=False)
    af = res.get("audio_file") or res.get("audio")
    url = af.get("url") if isinstance(af, dict) else af
    raw = LIB / (dst.stem + ".src")
    urllib.request.urlretrieve(url, raw)
    subprocess.run(["ffmpeg", "-y", "-i", str(raw), "-codec:a", "libmp3lame", "-b:a", "192k", str(dst)],
                   capture_output=True)   # mp3 keeps the repo lean (~0.7MB vs ~5MB WAV)
    raw.unlink(missing_ok=True)
    dur = subprocess.run(["ffprobe", "-v", "error", "-show_entries", "format=duration", "-of",
                          "default=nw=1:nk=1", str(dst)], capture_output=True, text=True).stdout.strip()
    bpm, beats = music_._beat_grid(str(dst), LIB)
    print(f"  saved {dst.name}: {dur}s | {bpm:.0f} BPM | {len(beats)} beats", flush=True)
    manifest.append({"file": fname, "energy": energy, "mood_tags": tags,
                     "bpm": round(bpm, 1), "beats": [round(b, 3) for b in beats],
                     "duration_s": round(float(dur or 0), 2), "source": SOURCE, "license": LICENSE})

# clean the librosa temp wav
(LIB / "beat_22k.wav").unlink(missing_ok=True)
(LIB / "manifest.json").write_text(json.dumps(manifest, indent=2))
print(f"\nWrote {LIB/'manifest.json'} with {len(manifest)} tracks.")
for m in manifest:
    print(f"  - {m['file']:26} {m['energy']:4} {m['bpm']:>5} BPM  {len(m['beats'])} beats")
