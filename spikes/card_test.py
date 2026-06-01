"""Render each card_style with the 4-tier card_tiers, extract a frame, to spot-check the typography."""
from pathlib import Path
from pipeline import editor

img = "spikes/out/nb_edit.png"   # a real photo for photo_backed/bg
class R:
    run_id = "_cardtest"; dir = Path("spikes/out/_cardtest")
    def log(s, m): pass
    def trace(s, d): pass
    def reason(s, *a, **k): pass
    def add_cost(s, *a, **k): pass
run = R(); run.dir.mkdir(parents=True, exist_ok=True)

tiers = {"name": "Conway Nail Bar", "tagline": "the salon that nails your Pinterest screenshot",
         "info": "2235 Dave Ward Dr · Walk-ins Tue–Sat", "cta": "Book today", "cta_style": "pill"}
for style in ["glass", "type_only", "photo_backed", "minimal_bar"]:
    sources = {"cardbg.png": img}
    seg = {"type": "card", "duration_s": 3.0, "transition_in": "hard_cut", "card_style": style,
           "card_tiers": tiers, "bg_src": "cardbg.png", "start_s": 0, "end_s": 3}
    plan = {"fps": 30, "width": 1080, "height": 1920, "segments": [seg], "audio": None, "music": None,
            "captions": [], "words": [], "palette": ["#0b6e4f", "#f4c542", "#15324b"]}
    out = str(run.dir / f"card_{style}.mp4")
    editor._render(run, plan, sources, out)
    print("rendered", style)
