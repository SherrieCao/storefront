"""D5 verify: render a synthetic timeline exercising every D3/D4 feature through the REAL editor._render
(staging + prefix + Remotion). Uses spike asset files. Proves the renderer compiles + runs the new
transitions, motion, overlays, ducked music, and karaoke captions end to end."""
import os
from pathlib import Path
from pipeline import editor

OUT = "spikes/out"
vid = f"{OUT}/seedance_shot.mp4"; img = f"{OUT}/nb_text.png"; img2 = f"{OUT}/nb_edit.png"
music = f"{OUT}/music.wav"; voice = f"{OUT}/voiceover.mp3"
for p in (vid, img, img2, music, voice):
    assert Path(p).exists(), f"missing spike asset {p}"

class FakeRun:
    run_id = "_d4test"
    dir = Path(OUT) / "_d4test_run"
    def log(self, m): print("[log]", m)
    def trace(self, d): pass
    def reason(self, *a, **k): pass
    def add_cost(self, *a, **k): pass

run = FakeRun(); run.dir.mkdir(parents=True, exist_ok=True)

sources = {"shot_1.mp4": vid, "clip_2.mp4": vid, "moodboard_3.png": img,
           "cardbg_4.png": img2, "voiceover.mp3": voice, "music.mp3": music}
segs = [
  {"type": "seedance_shot", "duration_s": 1.6, "transition_in": "hard_cut", "src": "shot_1.mp4",
   "playback_rate": 1.25, "motion": "punch_in", "start_s": 0.0, "end_s": 1.6},
  {"type": "real_clip", "duration_s": 1.5, "transition_in": "whip", "src": "clip_2.mp4",
   "playback_rate": 1.25, "motion": "parallax",
   "overlay": {"kind": "badge", "text": "★4.9", "position": "tr", "accent": "#0b6e4f"},
   "start_s": 1.6, "end_s": 3.1},
  {"type": "moodboard", "duration_s": 2.4, "transition_in": "dip_to_black", "src": "moodboard_3.png",
   "overlay": {"kind": "lower_third", "text": "Open 7 days"}, "start_s": 3.1, "end_s": 5.5},
  {"type": "card", "duration_s": 2.6, "transition_in": "zoom", "card_template": "EndCard",
   "card_text": "Carol's Dog Daycare | Walk-ins welcome", "card_animation": "scale_pop",
   "bg_src": "cardbg_4.png", "start_s": 5.5, "end_s": 8.1},
]
words = [{"w": w, "start_s": 0.4 + i * 0.42, "end_s": 0.4 + i * 0.42 + 0.4}
         for i, w in enumerate("Right off the one oh one drop your pup with people who know them".split())]
plan = {"fps": 30, "width": 1080, "height": 1920, "segments": segs,
        "audio": {"src": "voiceover.mp3", "gain": 1.0},
        "music": {"src": "music.mp3", "gain": 0.18},
        "captions": [], "words": words, "caption_style": "karaoke",
        "palette": ["#0b6e4f", "#f4c542", "#15324b"]}

out = str(run.dir / "d4_test.mp4")
editor._render(run, plan, sources, out)
print("RENDERED:", out, "| size:", os.path.getsize(out), "bytes")
