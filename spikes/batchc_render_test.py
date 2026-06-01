"""Batch C verify: render a synthetic timeline exercising every NEW design-system Batch C effect
through the REAL editor._render — transitions speed_ramp_in / scale_reveal / light_leak and motions
scale_breath / drift. Uses real assets from prior runs. Proves the renderer compiles + runs the new
vocabulary end to end."""
import os
from pathlib import Path
from pipeline import editor

ROOT = Path(__file__).resolve().parent.parent
OUT = ROOT / "spikes" / "out"
OUT.mkdir(parents=True, exist_ok=True)

vid1 = ROOT / "runs/0016/05_shots/shot_1.mp4"
vid2 = ROOT / "runs/0014/05_shots/shot_2.mp4"
img  = ROOT / "runs/0017/04_keyframes/kf_7.png"
img2 = ROOT / "runs/0016/04_keyframes/kf_5.png"
voice = ROOT / "runs/0017/06_voice/voiceover.mp3"
music = ROOT / "assets/music_library/track_upbeat_pop.mp3"
for p in (vid1, vid2, img, img2, voice, music):
    assert p.exists(), f"missing asset {p}"

class FakeRun:
    run_id = "_batchctest"
    dir = OUT / "_batchc_run"
    def log(self, m): print("[log]", m)
    def trace(self, d): pass
    def reason(self, *a, **k): pass
    def add_cost(self, *a, **k): pass

run = FakeRun(); run.dir.mkdir(parents=True, exist_ok=True)

sources = {"shot_1.mp4": str(vid1), "clip_2.mp4": str(vid2), "moodboard_3.png": str(img),
           "shot_4.mp4": str(vid1), "cardbg_5.png": str(img2),
           "voiceover.mp3": str(voice), "music.mp3": str(music)}
segs = [
  {"type": "seedance_shot", "duration_s": 1.6, "transition_in": "hard_cut", "src": "shot_1.mp4",
   "playback_rate": 1.25, "motion": "scale_breath", "start_s": 0.0, "end_s": 1.6},
  {"type": "real_clip", "duration_s": 1.5, "transition_in": "speed_ramp_in", "src": "clip_2.mp4",
   "playback_rate": 1.25, "motion": "drift", "start_s": 1.6, "end_s": 3.1},
  {"type": "moodboard", "duration_s": 2.2, "transition_in": "scale_reveal", "src": "moodboard_3.png",
   "start_s": 2.8, "end_s": 5.0},   # scale_reveal overlaps the prior (cursor - crossfade)
  {"type": "seedance_shot", "duration_s": 1.8, "transition_in": "light_leak", "src": "shot_4.mp4",
   "playback_rate": 1.25, "motion": "parallax", "start_s": 5.0, "end_s": 6.8},
  {"type": "card", "duration_s": 2.6, "transition_in": "zoom", "card_style": "glass",
   "card_tiers": {"name": "Conway Nail Bar", "info": "2235 Dave Ward Dr", "cta": "Walk-ins welcome"},
   "card_animation": "scale_pop", "bg_src": "cardbg_5.png", "start_s": 6.8, "end_s": 9.4},
]
words = [{"w": w, "start_s": 0.4 + i * 0.42, "end_s": 0.4 + i * 0.42 + 0.4}
         for i, w in enumerate("come see the wall two hundred colors and they remember your name".split())]
plan = {"fps": 30, "width": 1080, "height": 1920, "segments": segs,
        "audio": {"src": "voiceover.mp3", "gain": 1.0},
        "music": {"src": "music.mp3", "gain": 0.18},
        "captions": [], "words": words, "caption_style": "bold_center",
        "palette": ["#0b6e4f", "#f4c542", "#15324b"]}

out = str(run.dir / "batchc_test.mp4")
editor._render(run, plan, sources, out)
print("RENDERED:", out, "| size:", os.path.getsize(out), "bytes")
