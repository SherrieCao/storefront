"""Stage: Editor (Editor Agent + Remotion) — assemble the final ad.

Split into two halves (visuals-first spine, D2):
  - plan_timeline(): the Editor Agent (LLM) decides order + transitions + relative durations; this
    function then ENFORCES a deterministic timeline whose length = the Director's `total_duration_s`
    — video segments capped to their real clip length (no last-frame freeze), card/moodboard capped
    at EDITOR_MAX_EXTENSIBLE_S. Returns per-segment start/end timestamps. NO voice, NO render.
  - render(): one Remotion pass over the fixed timeline + the fitted voiceover + timestamp-accurate
    captions -> 09_output/final.mp4.

The voice is generated BETWEEN these two (voice.run_voice fits the timeline), so the video length is
the master clock and the voice fits it — not the reverse (which caused run 0003's 15s static card).

NOT for: generating/fixing shots (Shot Agent) or creative concept (Director).
"""
from __future__ import annotations
import json, shutil, subprocess
from pathlib import Path
from typing import Any
from . import config
from .tracing import Run, log_llm_call
from .llm import call_claude, parse_json
from .translator import resolve_ref, _usable_assets
from . import reviewers                       # edit-plan critic loop

EDIT_PLAN_FILE = "07_edit_plan.json"
OUTPUT_FILE = "09_output/final.mp4"
VOICE_DIR_FIT = "06_voice/voiceover_fit.mp3"
# Transition vocabulary the Editor Agent may pick from (D4). Only crossfade overlaps; the rest are
# in-window entrances. MUST match editor_render/src/types.ts Transition + AdComposition TransitionWrap.
_TRANSITIONS = {"hard_cut", "crossfade", "dip_to_black", "slide", "whip", "zoom"}
_MOTIONS = {"punch_in", "parallax"}                 # kinetic treatment for video segments (D4)
_OVERLAY_KINDS = {"lower_third", "badge"}
_BADGE_POS = {"tl", "tr", "bl", "br"}
_CROSSFADE_S = 0.4    # MUST match editor_render/src/AdComposition.tsx CROSSFADE_S
_MIN_SEG_S = 1.2


# --- PLAN: fix the visual timeline to total_duration_s (no voice, no render) -----------------------

def plan_timeline(run: Run, brief: dict[str, Any], shots_result: dict[str, Any],
                  keyframes_map: dict[str, Any], inventory: dict[str, Any],
                  beats: list[float] | None = None) -> dict[str, Any]:
    by_n = {str(s.get("n")): s for s in brief.get("segments", [])}
    clips = shots_result.get("clips", {})
    usable = _usable_segments(brief, clips, keyframes_map, inventory)
    if not usable:
        raise RuntimeError("Editor: no usable segments to assemble (all shots flagged?)")
    target = float(brief.get("total_duration_s") or config.MIN_DURATION_S)
    run.log(f"Editor: planning timeline for {len(usable)} segments to {target:.0f}s")

    limits = _video_limits(usable, clips, inventory)        # {n: max display s} for video segments
    ctx = {"business": inventory.get("business", ""), "brief": inventory.get("brief", "")}

    # self-correcting editor critic loop: plan -> review (editing craft) -> regenerate with feedback
    fb, agent, verdict, attempts = None, {}, {}, []
    for attempt in range(1, config.MAX_CREATIVE_RETRIES + 1):
        agent = _editor_agent(run, usable, brief, limits, feedback=fb)
        verdict = reviewers.review(run, "edit", agent, ctx)
        attempts.append({"attempt": attempt, "passed": verdict["pass"], "scores": verdict["scores"],
                         "failed_lenses": verdict["failed_lenses"], "improvement": verdict["improvement"]})
        if verdict["pass"]:
            break
        fb = verdict["improvement"]
        run.log(f"Editor: edit-review attempt {attempt} FAIL ({verdict['failed_lenses']}) — replanning")

    segs, sources = _build_segments(agent, by_n, clips, keyframes_map, inventory, limits)
    _fit_to_total(run, segs, target)                        # clamp + reconcile durations to target
    _snap_to_beats(run, segs, beats)                        # nudge cuts onto the music beat grid (D3)
    total_s = _assign_timestamps(segs)                      # cumulative start/end (crossfade-aware)

    timeline = {"fps": config.FPS, "width": 1080, "height": 1920,
                "segments": segs, "sources": sources, "total_s": round(total_s, 2),
                "palette": inventory.get("palette", []), "reasoning": agent.get("reasoning", ""),
                "caption_style": agent.get("caption_style", "clean_pop"),
                "_review": {"passed": verdict.get("pass", True), "scores": verdict.get("scores", {}),
                            "failed_lenses": verdict.get("failed_lenses", []), "attempts": attempts}}
    run.log(f"Editor: timeline {total_s:.1f}s — "
            + ", ".join(f"{s['type']}:{s['duration_s']:.1f}s" for s in segs))
    return timeline


def render(run: Run, timeline: dict[str, Any], voice: dict[str, Any], *,
           music: dict[str, Any] | None = None, use_cache: bool = False) -> str:
    """One Remotion pass: fixed timeline + voice (atempo-fit to the video) + rescaled captions + a
    music bed ducked under the voice (D3)."""
    out = run.dir / OUTPUT_FILE
    if use_cache and out.exists():
        run.log("Editor: render loaded from cache"); return str(out)

    segs = [{k: v for k, v in s.items() if not k.startswith("_")} for s in timeline["segments"]]
    sources = dict(timeline["sources"])
    video_len = float(timeline.get("total_s") or sum(s["duration_s"] for s in segs))

    # Fit the voice to the video by time-stretching it (pitch-preserving), NOT by stretching the video.
    audio, captions = None, [dict(text=l["text"], start_s=l["start_s"], end_s=l["end_s"])
                             for l in voice.get("lines", [])]
    words = [dict(w=w["w"], start_s=w["start_s"], end_s=w["end_s"]) for w in voice.get("words", [])]
    vpath = voice.get("audio_path")
    if vpath and Path(vpath).exists():
        voice_dur = (voice.get("duration_ms") or 0) / 1000 or video_len
        if voice_dur and voice_dur < 0.6 * video_len:
            run.log(f"[PACING WARNING] voice {voice_dur:.1f}s < 60% of the {video_len:.1f}s timeline — "
                    f"script likely too short for total_duration_s; Director should pick a shorter total.")
        tempo = 1.0
        if voice_dur > video_len + 0.1:
            tempo = min(round(voice_dur / video_len, 3), config.VOICE_MAX_ATEMPO)
        fitted = run.dir / VOICE_DIR_FIT
        if tempo > 1.0:
            _atempo(vpath, str(fitted), tempo)
            # 3 dp: at 2 dp the rescaled per-word window can drift onto the wrong word (visible as the
            # emphasis highlight landing off the spoken word).
            captions = [{"text": c["text"], "start_s": round(c["start_s"] / tempo, 3),
                         "end_s": round(c["end_s"] / tempo, 3)} for c in captions]
            words = [{"w": w["w"], "start_s": round(w["start_s"] / tempo, 3),
                      "end_s": round(w["end_s"] / tempo, 3)} for w in words]
            run.log(f"Editor: voice {voice_dur:.1f}s atempo×{tempo} -> {voice_dur/tempo:.1f}s "
                    f"(video {video_len:.1f}s)")
            vstaged = str(fitted)
            # if capped (voice still longer than video), extend the last card so nothing clips
            fitted_dur = voice_dur / tempo
            if fitted_dur > video_len + 0.3:
                ext = next((s for s in reversed(segs) if s["type"] in ("card", "moodboard")), segs[-1])
                ext["duration_s"] = round(ext["duration_s"] + (fitted_dur - video_len), 2)
                run.log(f"Editor: voice still {fitted_dur:.1f}s at atempo cap — extended closing "
                        f"{ext['type']} to avoid clipping the CTA.")
        else:
            vstaged = vpath
        sources["voiceover.mp3"] = vstaged
        audio = {"src": "voiceover.mp3", "gain": 1.0}

    # Cards carry their own on-screen text — suppress the caption track over card windows so the two
    # don't collide. (Caption times are in the same video timeline as the segment start/end.)
    card_windows = [(s.get("start_s", 0.0), s.get("end_s", 0.0))
                    for s in timeline["segments"] if s.get("type") == "card"]
    def _over_card(c):
        mid = (c["start_s"] + c["end_s"]) / 2
        return any(a <= mid < b for a, b in card_windows)
    captions = [c for c in captions if not _over_card(c)]
    words = [w for w in words if not _over_card(w)]

    # Music bed: a second audio track ducked UNDER the voice (low gain when there's a VO, fuller if
    # there's none so the ad still carries). Beatoven generated it ≈ the timeline length.
    music_track = None
    mpath = (music or {}).get("music_path")
    if mpath and Path(mpath).exists():
        sources["music.mp3"] = mpath
        music_track = {"src": "music.mp3", "gain": 0.18 if audio else 0.55}
        run.log(f"Editor: music bed ducked under voice (gain {music_track['gain']})")

    render_plan = {"fps": timeline["fps"], "width": timeline["width"], "height": timeline["height"],
                   "segments": segs, "audio": audio, "music": music_track,
                   "captions": captions, "words": words,
                   "caption_style": timeline.get("caption_style", "clean_pop"),
                   "palette": timeline.get("palette", [])}
    (run.dir / EDIT_PLAN_FILE).write_text(json.dumps(
        {"plan": render_plan, "total_s": timeline["total_s"], "reasoning": timeline.get("reasoning", "")},
        indent=2))
    run.reason("Editor", None, timeline.get("reasoning")
               or f"Timeline fixed to {timeline['total_s']:.1f}s; voice fit to it; captions from word timestamps.")

    out.parent.mkdir(parents=True, exist_ok=True)
    _render(run, render_plan, sources, str(out))
    run.log(f"Editor: rendered {out}")
    return str(out)


# --- helpers ---------------------------------------------------------------------------------------

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


def _video_limits(usable: list[dict], clips: dict, inventory: dict) -> dict[str, float]:
    """Max display seconds for each VIDEO segment (its real content length). Shown longer -> freeze."""
    rate = config.VIDEO_PLAYBACK_RATE          # sped clips cover less real time on screen
    limits: dict[str, float] = {}
    for s in usable:
        n, t = str(s.get("n")), s.get("type")
        if t == "seedance_shot":
            cl = _clip_duration(clips.get(n))
            if cl: limits[n] = round(cl / rate, 2)
        elif t == "real_clip":
            cl = _clip_duration(resolve_ref(inventory, str(s.get("clip_ref", ""))))
            trim = s.get("trim_s")
            cap = (trim[1] - trim[0]) if (isinstance(trim, list) and len(trim) == 2) else cl
            if cl and cap: cap = min(cap, cl)
            if cap: limits[n] = round(float(cap) / rate, 2)
    return limits


def _editor_agent(run: Run, usable: list[dict], brief: dict, limits: dict[str, float],
                  feedback: str | None = None) -> dict[str, Any]:
    """Editor Agent: order + per-segment duration + transitions + caption_style (NOT caption text —
    that comes from the voice word timestamps). Durations enforced to target afterward; this is the
    creative pass for pacing. `feedback` (from the edit reviewer) is baked into the regen. Stub offline."""
    payload = {
        "target_duration_s": brief.get("total_duration_s"),
        "segments": [{"n": s.get("n"), "type": s.get("type"), "intent": s.get("intent", ""),
                      "duration_s": s.get("duration_s"),
                      **({"max_s": limits[str(s.get("n"))]} if str(s.get("n")) in limits else {})}
                     for s in usable],
        "pacing": brief.get("pacing"), "editing_feel": brief.get("editing_feel"),
    }
    if feedback:
        payload["prior_attempt_failed_review"] = {"fix_these": feedback}
    user = json.dumps(payload, indent=2)
    scaffold = (config.SCAFFOLDS_DIR / "editor.md").read_text()
    raw, thinking, in_tok, out_tok = call_claude(
        config.MODEL_ROUTER["editor_agent"], scaffold, user,
        stub=lambda: json.dumps(_fallback_plan(usable)))
    log_llm_call(run, "editor", config.MODEL_ROUTER["editor_agent"], scaffold[:300] + "...",
                 raw, in_tok, out_tok, 0, thinking)
    plan = parse_json(raw)
    if not plan.get("segments"):
        plan = _fallback_plan(usable)
    return plan


def _fallback_plan(usable: list[dict]) -> dict[str, Any]:
    """Deterministic plan: Director order + durations, hard cuts. _fit_to_total reconciles lengths."""
    return {"segments": [{"n": s.get("n"), "duration_s": float(s.get("duration_s") or 4),
                          "transition_in": "hard_cut"} for s in usable],
            "reasoning": "Deterministic fallback: Director order + durations, hard cuts."}


def _build_segments(agent: dict, by_n: dict, clips: dict, keyframes_map: dict,
                    inventory: dict, limits: dict[str, float]) -> tuple[list[dict], dict[str, str]]:
    """Resolve each agent segment to a render segment (bright line: clips from Shot Agent; real_clip
    trimmed here; moodboard keyframe; card template). Carries `_max_s` (None = extensible)."""
    sources: dict[str, str] = {}
    out: list[dict[str, Any]] = []
    # @Image refs already shown on screen (shot seeds + moodboard assets) — so a card bg doesn't repeat one
    used_refs = {str(d.get("asset_ref", "")) for d in by_n.values()}
    for d in by_n.values():
        used_refs.update(str(x) for x in (d.get("moodboard_assets") or []))
    for i, ps in enumerate(agent.get("segments", [])):
        n = str(ps.get("n"))
        d = by_n.get(n)
        if not d:
            continue
        t = d.get("type")
        trans = ps.get("transition_in") if ps.get("transition_in") in _TRANSITIONS else "hard_cut"
        if i == 0:
            trans = "hard_cut"
        seg: dict[str, Any] = {"type": t, "duration_s": max(0.5, float(ps.get("duration_s") or 3)),
                               "transition_in": trans, "_max_s": limits.get(n)}
        ov = _overlay(ps.get("overlay"))                  # lower-third / badge motion graphic (D4)
        if ov:
            seg["overlay"] = ov
        if t in ("seedance_shot", "real_clip") and ps.get("motion") in _MOTIONS:
            seg["motion"] = ps["motion"]                  # punch-in / parallax on video (D4)
        if t == "seedance_shot":
            seg["src"] = _stage(sources, f"shot_{n}.mp4", clips[n])
            seg["playback_rate"] = config.VIDEO_PLAYBACK_RATE
        elif t == "real_clip":
            seg["src"] = _stage(sources, f"clip_{n}.mp4", resolve_ref(inventory, str(d.get("clip_ref", ""))))
            seg["playback_rate"] = config.VIDEO_PLAYBACK_RATE
            if d.get("trim_s"):
                seg["trim_s"] = d["trim_s"]
        elif t == "moodboard":
            seg["src"] = _stage(sources, f"moodboard_{n}.png", keyframes_map[n]["path"])
        elif t == "card":
            seg["card_template"] = d.get("card_template", "EndCard")
            seg["card_text"] = d.get("card_text", "")
            seg["card_animation"] = ps.get("animation", "scale_pop")  # editor picks the entrance
            bg = _card_bg(inventory, used_refs)             # photo-backed cards (kill the flat look)
            if bg:
                seg["bg_src"] = _stage(sources, f"cardbg_{n}{Path(bg).suffix}", bg)
        out.append(seg)
    return out, sources


def _overlay(o: Any) -> dict[str, Any] | None:
    """Validate an Editor-Agent overlay spec (D4). Drops malformed/empty ones (fail-safe: no overlay
    rather than a broken render). Shape mirrors editor_render/src/Overlay.tsx OverlaySpec."""
    if not isinstance(o, dict) or o.get("kind") not in _OVERLAY_KINDS:
        return None
    text = str(o.get("text", "")).strip()
    if not text:
        return None
    out: dict[str, Any] = {"kind": o["kind"], "text": text[:60]}
    if o.get("position") in _BADGE_POS:
        out["position"] = o["position"]
    if isinstance(o.get("accent"), str) and o["accent"].startswith("#"):
        out["accent"] = o["accent"]
    return out


def _card_bg(inventory: dict, used_refs: set[str]) -> str | None:
    """A real hero photo to back a card (rich, on-brand look). Prefer an @Image NOT already shown on
    screen, so the card doesn't repeat a frame (e.g. the moodboard composition or a shot seed). Falls
    back to any usable photo, else None (the card uses a palette gradient)."""
    images = [(tok, resolve_ref(inventory, tok)) for tok, _ in _usable_assets(inventory)
              if tok.startswith("@Image")]
    images = [(tok, p) for tok, p in images if p and Path(p).exists()]
    for tok, p in images:                # first an unused photo
        if tok not in used_refs:
            return p
    return images[0][1] if images else None   # else any photo (better than a flat card)


def _fit_to_total(run: Run, segs: list[dict], target: float) -> None:
    """Make the timeline length = target (the Director's total_duration_s), in place:
    clamp video segs to their clip length and extensibles to EDITOR_MAX_EXTENSIBLE_S; then if the sum
    is short, grow extensibles up to their cap (log a shortfall if still short — don't stretch video);
    if the sum is long, shrink everything proportionally down to a floor."""
    cap_ext = config.EDITOR_MAX_EXTENSIBLE_S
    for s in segs:
        if s["_max_s"] is not None:                       # video — never exceed its real content
            s["duration_s"] = min(s["duration_s"], s["_max_s"])
        else:                                             # card/moodboard — short capped beat
            s["duration_s"] = min(s["duration_s"], cap_ext)
    total = sum(s["duration_s"] for s in segs)

    if total < target - 0.05:                             # grow extensibles toward the target
        deficit = target - total
        for s in segs:
            if s["_max_s"] is None and deficit > 0.05:
                add = min(cap_ext - s["duration_s"], deficit)
                s["duration_s"] += add; deficit -= add
        if deficit > 0.5:
            run.log(f"[coverage shortfall] visual timeline {target - deficit:.1f}s < target {target:.0f}s "
                    f"— Director under-planned coverage; ending at the visual length (not stretching).")
    elif total > target + 0.05:                           # shrink proportionally down to the floor
        excess = total - target
        room = sum(max(0.0, s["duration_s"] - _MIN_SEG_S) for s in segs)
        if room > 0:
            for s in segs:
                s["duration_s"] -= excess * (max(0.0, s["duration_s"] - _MIN_SEG_S) / room)
    for s in segs:
        s["duration_s"] = round(s["duration_s"], 2)


def _assign_timestamps(segs: list[dict]) -> float:
    """Cumulative start/end per segment, accounting for crossfade overlap (mirrors the render). Returns
    the timeline's real length (what the voice must fit)."""
    cursor = 0.0
    for i, s in enumerate(segs):
        start = cursor if (i == 0 or s["transition_in"] != "crossfade") else max(0.0, cursor - _CROSSFADE_S)
        s["start_s"] = round(start, 2)
        s["end_s"] = round(start + s["duration_s"], 2)
        cursor = s["end_s"]
    return cursor


def _snap_to_beats(run: Run, segs: list[dict], beats: list[float] | None) -> None:
    """Beat-sync (D3): nudge each interior cut to the nearest music beat, within half a beat, so cuts
    land ON the beat — the core of the social-native rhythmic feel. Adjusts durations in place,
    respecting each segment's cap (_max_s for video, EDITOR_MAX_EXTENSIBLE_S for cards) and the seg
    floor. The last segment is left to absorb residual drift. No beats -> no-op (offline/no music)."""
    grid = sorted(float(b) for b in (beats or []) if isinstance(b, (int, float)) and b > 0.3)
    if len(grid) < 2 or len(segs) < 2:
        return
    interval = (grid[-1] - grid[0]) / (len(grid) - 1)       # avg beat period
    tol = max(0.18, interval * 0.5)
    cursor, snapped = 0.0, 0
    for s in segs[:-1]:
        raw_end = cursor + s["duration_s"]
        nb = min(grid, key=lambda b: abs(b - raw_end))
        cap = s["_max_s"] if s["_max_s"] is not None else config.EDITOR_MAX_EXTENSIBLE_S
        if abs(nb - raw_end) <= tol:
            new_dur = max(_MIN_SEG_S, min(nb - cursor, cap))
            if abs(new_dur - s["duration_s"]) > 0.02:
                s["duration_s"] = round(new_dur, 2); snapped += 1
        cursor += s["duration_s"]
    if snapped:
        run.log(f"Editor: beat-snapped {snapped} cut(s) to the ~{60 / interval:.0f} BPM grid")


def _stage(sources: dict[str, str], name: str, src: str | None) -> str:
    if src:
        sources[name] = src
    return name


def _atempo(src: str, dst: str, tempo: float) -> None:
    """Pitch-preserving time-stretch with ffmpeg atempo (chain for tempo > 2.0)."""
    t, filters = tempo, []
    while t > 2.0:
        filters.append("atempo=2.0"); t /= 2.0
    filters.append(f"atempo={round(t, 3)}")
    subprocess.run(["ffmpeg", "-y", "-i", src, "-filter:a", ",".join(filters), dst],
                   capture_output=True)


def _clip_duration(path: str | None) -> float | None:
    if not path or not Path(path).exists():
        return None
    try:
        r = subprocess.run(["ffprobe", "-v", "error", "-show_entries", "format=duration",
                            "-of", "default=nw=1:nk=1", path], capture_output=True, text=True, timeout=10)
        return float(r.stdout.strip())
    except Exception:
        return None


def _render(run: Run, render_plan: dict, sources: dict[str, str], out_path: str) -> None:
    """Stage assets into editor_render/public/<run_id>/ and run `npx remotion render`."""
    pub = config.EDITOR_RENDER_DIR / "public" / run.run_id
    if pub.exists():
        shutil.rmtree(pub)
    pub.mkdir(parents=True, exist_ok=True)
    for name, src in sources.items():
        shutil.copy2(src, pub / name)
    def _pref(s: dict) -> dict:
        s = dict(s)
        for k in ("src", "bg_src"):
            if s.get(k):
                s[k] = f"{run.run_id}/{s[k]}"
        return s
    prefixed = {**render_plan,
                "segments": [_pref(s) for s in render_plan["segments"]],
                "audio": ({**render_plan["audio"], "src": f"{run.run_id}/{render_plan['audio']['src']}"}
                          if render_plan.get("audio") else None),
                "music": ({**render_plan["music"], "src": f"{run.run_id}/{render_plan['music']['src']}"}
                          if render_plan.get("music") else None)}
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
