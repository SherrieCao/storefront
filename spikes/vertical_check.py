"""Generalization check: run concept + director (live, no Seedance) across 3 verticals and print the
concept + script + hook + segment mix, to confirm the writing is vertical-appropriate, authentic,
clear, and free of corporate-drift / dog-daycare bleed.
"""
import sys, json
from pathlib import Path
import pipeline.config as config
config.RUNS_DIR = config.REPO_ROOT / "_smoke_runs"
from pipeline.tracing import setup_run
from pipeline import triage, concept as C, director as D

CASES = [
    ("9101", "Carol_Dog",       "inputs/Carol_Dog"),
    ("9102", "Luxe Hair Studio","_reference/old_pipeline/inputs/example_salon"),
    ("9103", "Rosa's Bakery",   "inputs/bakery_test"),
]
for rid, biz, inp in CASES:
    run = setup_run(rid, biz)
    inv = triage.run_triage(run, Path(inp), use_cache=False)
    con = C.run_concept(run, inv, use_cache=False)
    brief = D.run_director(run, inv, con, use_cache=False)
    ch = con.get("chosen", {})
    print("\n" + "=" * 78)
    print(f"### {biz}  ({inv.get('image_count',0)} imgs / {inv.get('video_count',0)} vids)")
    print("CONCEPT:", ch.get("name"))
    print("  why_bold:", str(ch.get("why_bold",""))[:150])
    print("SCRIPT:", brief.get("script"))
    print("HOOK:", (brief.get("hook") or {}).get("hook_line"))
    print("segments:", [s.get("type") for s in brief.get("segments", [])])
    print("cost: $%.4f" % run.cost_total())
