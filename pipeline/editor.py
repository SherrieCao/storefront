"""Stage: Editor (Editor Agent + Remotion) — assemble the final ad.

Two halves of the split (D2):
  - Editor Agent (LLM): realizes the Director's pacing/editing_feel into an EDIT PLAN — segment order,
    per-segment duration aligned to the voiceover, hard_cut/crossfade transitions, caption track.
  - Renderer (deterministic): editor.py resolves each plan segment to its actual asset (per the bright
    line D21 — Seedance clips from the Shot Agent; everything else assembled here), stages assets into
    the Remotion project, writes 07_edit_plan.json, and runs `npx remotion render` -> 09_output/final.mp4.

Flagged/failed shots are simply absent from the usable set, so the Editor assembles around them.
Stubs offline: the Editor Agent falls back to a deterministic plan; Remotion still renders locally.

NOT for: generating/fixing shots (Shot Agent) or creative concept (Director).
"""
from __future__ import annotations
import json, shutil, subprocess
from pathlib import Path
from typing import Any
from . import config
from .tracing import Run, log_llm_call
from .llm import call_claude, parse_json
from .translator import resolve_ref

EDIT_PLAN_FILE = "07_edit_plan.json"
OUTPUT_FILE = "09_output/final.mp4"
_TRANSITIONS = {"hard_cut", "crossfade"}


def run_editor(run: Run, brief: dict[str, Any], shots_result: dict[str, Any],
               voice: dict[str, Any], keyframes_map: dict[str, Any], inventory: dict[str, Any],
               *, use_cache: bool = False) -> str:
    out = run.dir / OUTPUT_FILE
    if use_cache and out.exists():
        run.log("Editor: loaded from cache"); return str(out)

    by_n = {str(s.get("n")): s for s in brief.get("segments", [])}
    clips = shots_result.get("clips", {})
    usable = _usable_segments(brief, clips, keyframes_map, inventory)
    if not usable:
        raise RuntimeError("Editor: no usable segments to assemble (all shots flagged?)")
    run.log(f"Editor: {len(usable)} usable segments; designing edit plan")

    plan = _editor_agent(run, usable, voice, brief)            # LLM order/durations/transitions/captions
    render_plan, sources = _resolve(run, plan, by_n, clips, keyframes_map, inventory, voice)
    (run.dir / EDIT_PLAN_FILE).write_text(json.dumps(
        {"plan": render_plan, "agent_plan": plan, "reasoning": plan.get("reasoning", "")}, indent=2))
    run.reason("Editor", None, plan.get("reasoning") or "Assembled the timeline to the voiceover.")

    out.parent.mkdir(parents=True, exist_ok=True)
    _render(run, render_plan, sources, str(out))
    run.log(f"Editor: rendered {out}")
    return str(out)


def _usable_segments(brief, clips, keyframes_map, inventory) -> list[dict[str, Any]]:
    """The Director's segments whose assets actually exist (drops flagged shots, missing refs)."""
    usable = []
    for s in brief.get("segments", []):
        n, t = str(s.get("n")), s.get("type")
        if t == "seedance_shot" and not clips.get(n):
            continue
        if t == "moodboard" and not (keyframes_map.get(n) or {}).get("path"):
            continue
        if t == "real_clip" and not resolve_ref(inventory, str(s.get("clip_ref", ""))):
            continue
        usable.append(s)
    return usable


def _editor_agent(run: Run, usable: list[dict], voice: dict, brief: dict) -> dict[str, Any]:
    """Editor Agent: LLM edit plan (order/durations/transitions/captions). Deterministic fallback."""
    user = json.dumps({
        "segments": [{"n": s.get("n"), "type": s.get("type"), "intent": s.get("intent", ""),
                      "duration_s": s.get("duration_s")} for s in usable],
        "voice": {"duration_s": round((voice.get("duration_ms") or 0) / 1000, 2),
                  "lines": voice.get("lines", [])},
        "pacing": brief.get("pacing"), "editing_feel": brief.get("editing_feel"),
        "total_duration_s": brief.get("total_duration_s"),
    }, indent=2)
    scaffold = (config.SCAFFOLDS_DIR / "editor.md").read_text()
    raw, thinking, in_tok, out_tok = call_claude(
        config.MODEL_ROUTER["editor_agent"], scaffold, user,
        stub=lambda: json.dumps(_fallback_plan(usable, voice)))
    log_llm_call(run, "editor", config.MODEL_ROUTER["editor_agent"], scaffold[:300] + "...",
                 raw, in_tok, out_tok, 0, thinking)
    plan = parse_json(raw)
    if not plan.get("segments"):
        plan = _fallback_plan(usable, voice)
    return plan


def _fallback_plan(usable: list[dict], voice: dict) -> dict[str, Any]:
    """Deterministic plan: keep order, scale durations to the voice, hard cuts, captions = voice lines."""
    total = (voice.get("duration_ms") or 0) / 1000 or sum(float(s.get("duration_s") or 4) for s in usable)
    raw_durs = [float(s.get("duration_s") or 4) for s in usable]
    scale = (total / sum(raw_durs)) if sum(raw_durs) else 1.0
    segs = [{"n": s.get("n"), "type": s.get("type"), "duration_s": round(d * scale, 2),
             "transition_in": "hard_cut" if i == 0 else "hard_cut"}
            for i, (s, d) in enumerate(zip(usable, raw_durs))]
    return {"segments": segs, "captions": voice.get("lines", []),
            "reasoning": "Deterministic fallback: Director order, durations scaled to the voiceover, "
                         "hard cuts, captions paired to voice lines."}


def _resolve(run: Run, plan: dict, by_n: dict, clips: dict, keyframes_map: dict,
             inventory: dict, voice: dict) -> tuple[dict[str, Any], dict[str, str]]:
    """Map the LLM plan's segments to real asset files (bright line: clips from Shot Agent; real_clip
    trimmed here; moodboard keyframe animated here; card from templates). Returns (render_plan,
    sources) where sources maps staged-filename -> absolute source path to stage into public/."""
    sources: dict[str, str] = {}
    seg_out: list[dict[str, Any]] = []
    for i, ps in enumerate(plan.get("segments", [])):
        n = str(ps.get("n"))
        d = by_n.get(n)
        if not d:
            continue
        t = d.get("type")
        trans = ps.get("transition_in") if ps.get("transition_in") in _TRANSITIONS else "hard_cut"
        if i == 0:
            trans = "hard_cut"
        dur = max(0.5, float(ps.get("duration_s") or d.get("duration_s") or 3))
        seg: dict[str, Any] = {"type": t, "duration_s": dur, "transition_in": trans}
        if t == "seedance_shot":
            seg["src"] = _stage(sources, f"shot_{n}.mp4", clips[n])
        elif t == "real_clip":
            src = resolve_ref(inventory, str(d.get("clip_ref", "")))
            seg["src"] = _stage(sources, f"clip_{n}.mp4", src)
            if d.get("trim_s"):
                seg["trim_s"] = d["trim_s"]
        elif t == "moodboard":
            seg["src"] = _stage(sources, f"moodboard_{n}.png", keyframes_map[n]["path"])
        elif t == "card":
            seg["card_template"] = d.get("card_template", "EndCard")
            seg["card_text"] = d.get("card_text", "")
        seg_out.append(seg)

    audio = None
    if voice.get("audio_path") and Path(voice["audio_path"]).exists():
        audio = {"src": _stage(sources, "voiceover.mp3", voice["audio_path"]), "gain": 1.0}

    render_plan = {"fps": config.FPS, "width": 1080, "height": 1920,
                   "segments": seg_out, "audio": audio,
                   "captions": plan.get("captions", voice.get("lines", []))}
    return render_plan, sources


def _stage(sources: dict[str, str], name: str, src: str | None) -> str:
    if src:
        sources[name] = src
    return name


def _render(run: Run, render_plan: dict, sources: dict[str, str], out_path: str) -> None:
    """Stage assets into editor_render/public/<run_id>/ and run `npx remotion render`. Renders the
    plan deterministically. No external API cost (local CLI)."""
    pub = config.EDITOR_RENDER_DIR / "public" / run.run_id
    if pub.exists():
        shutil.rmtree(pub)
    pub.mkdir(parents=True, exist_ok=True)
    # rewrite src/audio names to the per-run public subpath Remotion's staticFile resolves
    for name, src in sources.items():
        shutil.copy2(src, pub / name)
    prefixed = {**render_plan,
                "segments": [{**s, **({"src": f"{run.run_id}/{s['src']}"} if s.get("src") else {})}
                             for s in render_plan["segments"]],
                "audio": ({**render_plan["audio"], "src": f"{run.run_id}/{render_plan['audio']['src']}"}
                          if render_plan.get("audio") else None)}
    props = config.EDITOR_RENDER_DIR / "public" / f"_props_{run.run_id}.json"
    props.write_text(json.dumps({"plan": prefixed}))

    if not (config.EDITOR_RENDER_DIR / "node_modules").exists():
        run.log("Editor: installing Remotion deps (first run)…")
        subprocess.run(["npm", "install", "--no-audit", "--no-fund"],
                       cwd=config.EDITOR_RENDER_DIR, capture_output=True)
    cmd = ["npx", "remotion", "render", config.REMOTION_COMPOSITION_ID,
           str(Path(out_path).resolve()), f"--props={props.resolve()}"]
    run.log(f"Editor: {' '.join(cmd)}")
    r = subprocess.run(cmd, cwd=config.EDITOR_RENDER_DIR, capture_output=True, text=True)
    run.add_cost("editor", config.REMOTION_RENDER_COST)
    if r.returncode != 0:
        run.trace({"step": "editor", "type": "render_error", "stderr": r.stderr[-2000:]})
        raise RuntimeError(f"Remotion render failed:\n{r.stderr[-1500:]}")
    props.unlink(missing_ok=True)
