"""Stage: Shot Agent — per-shot generate → judge → retry → flag (the multi-gen core, D5).

Runs ONLY on `seedance_shot` segments (other segment types skip generation entirely). For each shot:
  1. compose_shot_prompt() -> single-shot Seedance prompt (judge feedback baked in on retries)
  2. Seedance image_to_video (keyframe start frame) / text_to_video, silent (generate_audio=False)
  3. JUDGE the rendered clip (cheap Gemini Flash, video input) -> {pass, score, reasons}
  4. pass -> approve (05_shots/shot_<n>.mp4); fail -> retry up to MAX_SHOT_RETRIES with the judge's
     reasons fed forward; after the last failure -> flag to the operator (NEVER silently accept).

Seedance is ~2 min/gen, so shots run CONCURRENTLY (the judge+retry loop is independent per shot); the
cost-ceiling check is serialized under a lock. If the $5 ceiling would be breached, remaining shots
are aborted and CostCeilingExceeded propagates (run.py finalizes a clean partial run).

NOT for: creative/composition decisions (the Director) or assembly (the Editor).
"""
from __future__ import annotations
import json, subprocess, threading, urllib.request
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from typing import Any
from . import config, budget
from .tracing import Run, log_llm_call
from .llm import call_gemini_video_judge, parse_json
from .translator import compose_shot_prompt

SHOTS_DIR = "05_shots"
RESULT_FILE = "05_shots/result.json"


def run_shots(run: Run, brief: dict[str, Any], inventory: dict[str, Any],
              keyframes_map: dict[str, Any], *, use_cache: bool = False) -> dict[str, Any]:
    out_dir = run.dir / SHOTS_DIR
    out_dir.mkdir(parents=True, exist_ok=True)
    cache = run.dir / RESULT_FILE
    if use_cache and cache.exists():
        run.log("Shots: loaded from cache"); return json.loads(cache.read_text())

    shots = [s for s in brief.get("segments", []) if s.get("type") == "seedance_shot"]
    run.log(f"Shots: {len(shots)} seedance_shot segments (other types skip generation)")
    judge_system = (config.SCAFFOLDS_DIR / "shot_agent.md").read_text()

    clips: dict[str, str | None] = {}
    flagged: list[dict[str, Any]] = []
    narrative: list[str] = []
    lock = threading.Lock()
    abort = threading.Event()

    def do_shot(seg: dict[str, Any]) -> None:
        n = seg.get("n")
        kf = (keyframes_map.get(str(n)) or {}).get("path")
        feedback: list[str] | None = None
        last_clip = None
        for attempt in range(1, config.MAX_SHOT_RETRIES + 1):
            if abort.is_set():
                return
            dur = max(config.SEEDANCE_MIN_SHOT_S, int(round(float(seg.get("duration_s") or 4))))
            try:
                with lock:   # gate the paid gen + judge against the ceiling, then reserve nothing else
                    budget.check_ceiling(run, budget.seedance_shot(dur) + budget.judge_call(),
                                         f"shots[shot {n} attempt {attempt}]")
            except budget.CostCeilingExceeded:
                abort.set()
                with lock:
                    flagged.append({"n": n, "reason": "cost_ceiling_aborted", "attempts": attempt - 1})
                return
            spec = compose_shot_prompt(run, seg, kf, inventory, brief,
                                       attempt=attempt, feedback=feedback)
            clip = _generate(run, spec, n, attempt, out_dir)
            last_clip = clip
            verdict = _judge(run, clip, seg, judge_system)
            if verdict.get("pass"):
                approved = out_dir / f"shot_{n}.mp4"
                _copy(clip, approved)
                with lock:
                    clips[str(n)] = str(approved)
                    narrative.append(f"- Shot {n}: passed on attempt {attempt} "
                                     f"(score {verdict.get('score')}).")
                run.log(f"Shots: shot {n} APPROVED on attempt {attempt}")
                return
            feedback = verdict.get("reasons") or ["unspecified quality issue"]
            run.log(f"Shots: shot {n} attempt {attempt} FAILED — {feedback}")
            with lock:
                narrative.append(f"- Shot {n}: attempt {attempt} failed ({'; '.join(feedback or [])}); "
                                 f"{'retrying with feedback' if attempt < config.MAX_SHOT_RETRIES else 'giving up'}.")
        # all attempts failed -> flag, never silently accept
        with lock:
            clips[str(n)] = None
            flagged.append({"n": n, "reason": "failed_judge", "attempts": config.MAX_SHOT_RETRIES,
                            "last_reasons": feedback, "last_clip": last_clip})
        run.log(f"Shots: shot {n} FLAGGED after {config.MAX_SHOT_RETRIES} attempts")

    if shots:
        workers = min(config.MAX_SHOT_CONCURRENCY, len(shots))
        with ThreadPoolExecutor(max_workers=workers) as ex:
            list(ex.map(do_shot, shots))

    run.write_flagged_shots(flagged)
    result = {"clips": clips, "flagged": flagged,
              "approved": sum(1 for v in clips.values() if v), "total": len(shots)}
    cache.write_text(json.dumps(result, indent=2))
    run.reason("Shot Agent", None,
               f"{result['approved']}/{result['total']} shots approved; "
               f"{len(flagged)} flagged.\n\n" + "\n".join(narrative))
    if abort.is_set():
        # remaining shots were aborted on the cost ceiling — surface it for a clean partial finalize
        raise budget.CostCeilingExceeded(run, "shots", 0.0)
    run.log(f"Shots: {result['approved']}/{result['total']} approved, {len(flagged)} flagged")
    return result


# --- generation ------------------------------------------------------------

def _generate(run: Run, spec: dict[str, Any], n: Any, attempt: int, out_dir: Path) -> str:
    """One Seedance gen (silent). Returns the per-attempt clip path. Stubs to a real (ffmpeg) clip
    from the keyframe so offline runs still produce a playable video the Editor can assemble."""
    dst = out_dir / f"shot_{n}_a{attempt}.mp4"
    endpoint = spec.get("endpoint", "text_to_video")
    keyframe = spec.get("_keyframe")
    dur = int(spec.get("duration", config.SEEDANCE_MIN_SHOT_S))

    if not config.FAL_KEY:
        _stub_clip(keyframe, str(dst), dur)
        run.log(f"Shots: STUB clip shot {n} a{attempt} ({endpoint}, {dur}s)")
    else:
        import fal_client
        base = "seedance_image" if endpoint == "image_to_video" else "seedance_text"
        key = f"{base}_fast" if config.SEEDANCE_TIER == "fast" else base
        model_id = config.MODEL_ROUTER.get(key) or config.MODEL_ROUTER[base]
        args: dict[str, Any] = {"prompt": spec.get("seedance_prompt", ""),
                                "resolution": config.RESOLUTION, "duration": str(dur),
                                "aspect_ratio": config.ASPECT_RATIO, "generate_audio": False}
        if endpoint == "image_to_video" and keyframe:
            args["image_url"] = fal_client.upload_file(keyframe)
        res = fal_client.subscribe(model_id, arguments=args, with_logs=True,
                                   on_queue_update=lambda u: _log_fal(run, u))
        run.add_cost("shots", budget.seedance_shot(dur))
        url = res["video"]["url"]
        urllib.request.urlretrieve(url, dst)
        run.trace({"step": "shots", "type": "fal_output", "shot": n, "attempt": attempt, "url": url})
    _thumbnail(str(dst), str(out_dir / f"shot_{n}_a{attempt}.jpg"))
    return str(dst)


def _judge(run: Run, clip_path: str, seg: dict[str, Any], judge_system: str) -> dict[str, Any]:
    """Judge the rendered clip (cheap Gemini Flash, video input). Stub -> pass when no key."""
    if not config.GEMINI_API_KEY:
        return {"pass": True, "score": 0.9, "reasons": [], "_stub": True}
    model = config.MODEL_ROUTER["shot_judge"]
    user = json.dumps({"shot_intent": seg.get("intent", ""), "action": seg.get("action", ""),
                       "camera": seg.get("camera", ""),
                       "had_start_frame": str(seg.get("asset_ref", "")).startswith("@Image")}, indent=2)
    raw, _think, in_tok, out_tok = call_gemini_video_judge(model, judge_system, clip_path, user)
    log_llm_call(run, "shot_judge", model, "[judge]", raw, in_tok, out_tok, 0, None)
    verdict = parse_json(raw)
    if "pass" not in verdict:   # parse failure -> treat as fail with the raw note, so we retry
        verdict = {"pass": False, "score": 0.0, "reasons": ["judge returned unparseable output"]}
    return verdict


# --- helpers ---------------------------------------------------------------

def _stub_clip(keyframe: str | None, dst: str, dur: int) -> None:
    """A real silent mp4 (so the Editor can assemble offline): the keyframe as a still video, else
    a solid color clip."""
    fps = config.FPS
    if keyframe and Path(keyframe).exists():
        cmd = ["ffmpeg", "-y", "-loop", "1", "-i", keyframe, "-t", str(dur), "-r", str(fps),
               "-vf", "scale=1080:1920:force_original_aspect_ratio=increase,crop=1080:1920",
               "-pix_fmt", "yuv420p", "-an", dst]
    else:
        cmd = ["ffmpeg", "-y", "-f", "lavfi", "-i",
               f"color=c=0x282C30:s=1080x1920:d={dur}:r={fps}", "-pix_fmt", "yuv420p", dst]
    subprocess.run(cmd, capture_output=True)


def _thumbnail(clip: str, dst: str) -> None:
    subprocess.run(["ffmpeg", "-y", "-i", clip, "-frames:v", "1", "-q:v", "3", dst],
                   capture_output=True)


def _copy(src: str, dst: Path) -> None:
    import shutil
    shutil.copy2(src, dst)


def _log_fal(run: Run, update: Any) -> None:
    for log in (getattr(update, "logs", None) or []):
        msg = log.get("message") if isinstance(log, dict) else None
        if msg: run.log(f"  [fal] {msg}")
