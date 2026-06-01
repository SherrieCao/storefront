"""Verify the highlight tracks the SPOKEN word, using run 0009's REAL word timings + voiceover.
Renders emphasis captions over filler visuals, then we extract frames at known times and check the
accented word == the most-recently-started (spoken) word.
"""
import json
from pathlib import Path
from pipeline import editor

V = json.load(open("runs/0009/06_voice/voice.json"))
words = [{"w": w["w"], "start_s": w["start_s"], "end_s": w["end_s"]} for w in V["words"]]
voice = "runs/0009/06_voice/voiceover.mp3"
img = "spikes/out/nb_text.png"; vid = "spikes/out/seedance_shot.mp4"

class FakeRun:
    run_id = "_capverify"
    dir = Path("spikes/out/_capverify");
    def log(self, m): pass
    def trace(self, d): pass
    def reason(self, *a, **k): pass
    def add_cost(self, *a, **k): pass
run = FakeRun(); run.dir.mkdir(parents=True, exist_ok=True)

# filler visuals covering ~13s (the voice length); content doesn't matter, only the caption track does
sources = {"a.mp4": vid, "b.png": img, "voiceover.mp3": voice}
segs = [
    {"type": "seedance_shot", "duration_s": 4.0, "transition_in": "hard_cut", "src": "a.mp4", "motion": "handheld_jitter", "start_s": 0, "end_s": 4},
    {"type": "moodboard", "duration_s": 5.0, "transition_in": "hard_cut", "src": "b.png", "start_s": 4, "end_s": 9},
    {"type": "seedance_shot", "duration_s": 4.7, "transition_in": "hard_cut", "src": "a.mp4", "start_s": 9, "end_s": 13.7},
]
plan = {"fps": 30, "width": 1080, "height": 1920, "segments": segs,
        "audio": {"src": "voiceover.mp3", "gain": 1.0}, "music": None,
        "captions": [], "words": words, "caption_style": "sparse",
        "palette": ["#0b6e4f", "#f4c542", "#15324b"]}

# print expected current word at the probe times
CHUNK = 4
def current_word(tt):
    grp = next((words[i:i+CHUNK] for i in range(0, len(words), CHUNK)
                if tt >= words[i]["start_s"] - 0.15 and tt < words[min(i+CHUNK, len(words))-1]["end_s"] + 0.25), None)
    if not grp: return None
    cur = [w for w in grp if tt >= w["start_s"]]
    return cur[-1]["w"] if cur else None
for tt in (1.0, 2.1, 2.6, 5.0):
    print(f"  t={tt}s -> expected highlighted word: {current_word(tt)!r}")

out = str(run.dir / "cap.mp4")
editor._render(run, plan, sources, out)
print("RENDERED:", out)
