"""Render each caption_style over filler footage with real 0009 word timings; extract a frame each."""
import json
from pathlib import Path
from pipeline import editor

V = json.load(open("runs/0009/06_voice/voice.json"))
words = [{"w": w["w"], "start_s": w["start_s"], "end_s": w["end_s"]} for w in V["words"]]
voice = "runs/0009/06_voice/voiceover.mp3"; vid = "spikes/out/seedance_shot.mp4"

class R:
    run_id = "_capsty"; dir = Path("spikes/out/_capsty")
    def log(s, m): pass
    def trace(s, d): pass
    def reason(s, *a, **k): pass
    def add_cost(s, *a, **k): pass
run = R(); run.dir.mkdir(parents=True, exist_ok=True)

for style in ["bold_center", "minimal_lower", "handwritten", "sparse_keyword"]:
    sources = {"a.mp4": vid, "voiceover.mp3": voice}
    segs = [{"type": "seedance_shot", "duration_s": 13.0, "transition_in": "hard_cut", "src": "a.mp4", "start_s": 0, "end_s": 13}]
    plan = {"fps": 30, "width": 1080, "height": 1920, "segments": segs,
            "audio": {"src": "voiceover.mp3", "gain": 1.0}, "music": None,
            "captions": [], "words": words, "caption_style": style, "palette": ["#0b6e4f", "#f4c542", "#15324b"]}
    editor._render(run, plan, sources, str(run.dir / f"cap_{style}.mp4"))
    print("rendered", style)
