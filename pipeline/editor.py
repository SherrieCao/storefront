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
import json, re, shutil, subprocess
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
# Transition vocabulary the Editor Agent may pick from (D4 + design-system Batch C). Overlap
# transitions reveal over the prior segment (crossfade, scale_reveal); the rest are in-window
# entrances. MUST match editor_render/src/types.ts Transition + AdComposition TransitionWrap.
_TRANSITIONS = {"hard_cut", "crossfade", "dip_to_black", "slide", "whip", "zoom",
                "speed_ramp_in", "scale_reveal", "light_leak"}
_OVERLAP_TRANSITIONS = {"crossfade", "scale_reveal"}   # start before the prior ends (need overlap window)
_MOTIONS = {"punch_in", "parallax", "handheld_jitter",   # kinetic treatment for video segments (D4 + Batch2)
            "scale_breath", "drift"}                      # design-system Batch C: subtle pulse / slow diagonal drift
_OVERLAY_KINDS = {"lower_third", "badge"}
_BADGE_POS = {"tl", "tr", "bl", "br"}
_CROSSFADE_S = 0.3    # MUST match editor_render/src/AdComposition.tsx CROSSFADE_S (Batch C: 0.4->0.3, snappier)
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
    # Context for the reviewer's `ending` lens: the ad always closes on a designed branded info card the
    # editor builds (D38/D39) — judge that the close LANDS (lead-in doesn't deflate it), not its form.
    ending_context = {"voice_style": brief.get("voice_style", "")}

    attempts = []
    if not config.EDITOR_CRITIC_LOOP:
        # Editor critic loop DISABLED (D42) — it was the dominant latency (~12 min / 3 retries) and the
        # agent's single pass is already good enough. One plan, no reviewer, no retries.
        agent = _editor_agent(run, usable, brief, limits)
        verdict = {"pass": True, "scores": {}, "failed_lenses": [], "improvement": ""}
        attempts.append({"attempt": 1, "passed": True, "scores": {}, "failed_lenses": [], "improvement": ""})
        run.log("Editor: critic loop disabled (single-pass plan; set config.EDITOR_CRITIC_LOOP=True to re-enable)")
    else:
        # self-correcting editor critic loop: plan -> review -> regenerate. Keep the BEST attempt — a parse
        # failure can drop _editor_agent to a weak fallback, so the LAST attempt isn't necessarily the best.
        fb, cands, last_valid = None, [], None
        for attempt in range(1, config.MAX_CREATIVE_RETRIES + 1):
            agent = _editor_agent(run, usable, brief, limits, feedback=fb, prev_valid=last_valid)
            if agent.get("segments") and not agent.get("_fallback"):
                last_valid = agent                   # remember the last good LLM plan to reuse on a parse-fail
            verdict = reviewers.review(run, "edit", {**agent, "ending_context": ending_context}, ctx)
            attempts.append({"attempt": attempt, "passed": verdict["pass"], "scores": verdict["scores"],
                             "failed_lenses": verdict["failed_lenses"], "improvement": verdict["improvement"]})
            cands.append((bool(verdict["pass"]), _mean_score(verdict.get("scores", {})), agent, verdict))
            if verdict["pass"]:
                break
            fb = verdict["improvement"]
            run.log(f"Editor: edit-review attempt {attempt} FAIL ({verdict['failed_lenses']}) — replanning")
        agent, verdict = _pick_best(cands)           # accept-BEST (not accept-last) + flag
        if not verdict.get("pass"):
            run.log(f"Editor: no attempt passed in {len(cands)} — shipping best "
                    f"(score {_mean_score(verdict.get('scores', {})):.2f})")

    segs, sources = _build_segments(agent, by_n, clips, keyframes_map, inventory, limits)
    _realize_before_after(run, segs, by_n, inventory)       # D43: obvious before->after sequential reveal
    _realize_ending(run, segs, sources, inventory)          # closing beat = a designed branded info card (D38)
    _fit_to_total(run, segs, target)                        # clamp + reconcile durations to target
    _snap_to_beats(run, segs, beats)                        # nudge cuts onto the music beat grid (D3)
    total_s = _assign_timestamps(segs)                      # cumulative start/end (crossfade-aware)

    timeline = {"fps": config.FPS, "width": 1080, "height": 1920,
                "segments": segs, "sources": sources, "total_s": round(total_s, 2),
                "palette": inventory.get("palette", []), "reasoning": agent.get("reasoning", ""),
                "caption_style": agent.get("caption_style", "bold_center"),
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
    # The closing brand card plays CLEAN — the voice + captions must end before it (no overlap). Fit the
    # VO to the region BEFORE the card, not the whole video.
    _last = timeline["segments"][-1]
    ending_card_s = float(_last.get("duration_s") or 0.0) if _last.get("type") == "card" else 0.0
    vo_region = max(1.0, round(video_len - ending_card_s, 3))

    # Fit the voice to the video by time-stretching it (pitch-preserving), NOT by stretching the video.
    audio, captions = None, [dict(text=l["text"], start_s=l["start_s"], end_s=l["end_s"])
                             for l in voice.get("lines", [])]
    words = [dict(w=w["w"], start_s=w["start_s"], end_s=w["end_s"]) for w in voice.get("words", [])]
    vpath = voice.get("audio_path")
    if vpath and Path(vpath).exists():
        voice_dur = (voice.get("duration_ms") or 0) / 1000 or video_len
        # F1: the freed script (VO = hook + idea, no CTA) is intentionally shorter than the video — the
        # closing card + music carry the tail. Only warn if the post-voice tail is NOT covered by
        # card/moodboard beats (i.e. the short VO actually leaves dead video, not a deliberate card tail).
        tail_segs = [s for s in timeline["segments"] if s.get("end_s", 0.0) > voice_dur + 0.3]
        tail_covered = bool(tail_segs) and all(s.get("type") in ("card", "moodboard") for s in tail_segs)
        if voice_dur and voice_dur < 0.6 * video_len and not tail_covered:
            run.log(f"[PACING WARNING] voice {voice_dur:.1f}s < 60% of the {video_len:.1f}s timeline and "
                    f"the tail isn't covered by card/moodboard beats — likely dead video at the end.")
        tempo = 1.0
        if voice_dur > vo_region + 0.1:                  # fit the VO to END before the clean ending card
            tempo = min(round(voice_dur / vo_region, 3), config.VOICE_MAX_ATEMPO)
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
                    f"(fit before the {ending_card_s:.0f}s card; vo region {vo_region:.1f}s of {video_len:.1f}s)")
            vstaged = str(fitted)
            # if capped (voice still longer than the VO region), push the spill into the lead-IN beat
            # before the card so the card itself stays clean.
            fitted_dur = voice_dur / tempo
            if fitted_dur > vo_region + 0.3:
                ext = next((s for s in reversed(segs[:-1]) if s["type"] in ("card", "moodboard")), segs[-2] if len(segs) > 1 else segs[-1])
                ext["duration_s"] = round(ext["duration_s"] + (fitted_dur - vo_region), 2)
                run.log(f"Editor: voice still {fitted_dur:.1f}s at atempo cap — extended pre-card "
                        f"{ext['type']} so the ending card stays clean.")
        else:
            vstaged = vpath
        # Light dynamic-range compression evens out the VO and kills the "digital stiffness" of synthetic
        # speech — closer to phone-recorded voice. Subtle; falls back to the uncompressed file on error.
        compressed = run.dir / "06_voice/voiceover_vo.mp3"
        if _compress_vo(vstaged, str(compressed)):
            vstaged = str(compressed)
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
    # HARD cutoff at the closing card's start: a caption's fade-out / keyword linger renders PAST its
    # end_s (KineticCaption holds a group ~0.25s, sparse_keyword ~1.2s), which bleeds the last word into
    # the clean card. The renderer hides any caption at/after this time so the card stays clean.
    last_seg = timeline["segments"][-1]
    caption_cutoff_s = float(last_seg.get("start_s")) if last_seg.get("type") == "card" else None

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
                   "caption_style": timeline.get("caption_style", "bold_center"),
                   "caption_cutoff_s": caption_cutoff_s,   # hide captions at/after the closing card
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


def _mean_score(scores: dict) -> float:
    vals = [float(v) for v in (scores or {}).values() if isinstance(v, (int, float))]
    return sum(vals) / len(vals) if vals else 0.0


def _pick_best(cands: list[tuple]) -> tuple[dict, dict]:
    """From [(passed, mean_score, agent, verdict), ...] pick the best: a passing attempt if any, else the
    highest mean-score one. Prevents a crashed/weak later attempt from overwriting a strong earlier one."""
    pool = [c for c in cands if c[0]] or cands
    best = max(pool, key=lambda c: c[1])
    return best[2], best[3]


def _editor_agent(run: Run, usable: list[dict], brief: dict, limits: dict[str, float],
                  feedback: str | None = None, prev_valid: dict | None = None) -> dict[str, Any]:
    """Editor Agent: order + per-segment duration + transitions + caption_style (NOT caption text —
    that comes from the voice word timestamps). Durations enforced to target afterward; this is the
    creative pass for pacing. `feedback` (from the edit reviewer) is baked into the regen. On a parse
    failure, reuse the prior valid plan (`prev_valid`) rather than the deterministic fallback. Stub offline."""
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
    if not plan.get("segments"):                     # harden: pull the first {...} object out of any prose
        plan = _extract_json_object(raw) or plan
    if not plan.get("segments"):                     # still nothing → reuse the last good plan, else fallback
        plan = prev_valid or _fallback_plan(usable)
    return plan


def _extract_json_object(raw: str) -> dict[str, Any] | None:
    """Best-effort recovery when the model wraps its JSON in prose/fences: grab the outermost {...}."""
    m = re.search(r"\{.*\}", raw or "", re.S)
    if not m:
        return None
    try:
        obj = json.loads(m.group(0))
        return obj if isinstance(obj, dict) else None
    except Exception:
        return None


# Motion cycle so even the fallback enlivens video beats (a motionless fallback auto-fails the reviewer).
_FALLBACK_MOTIONS = ["punch_in", "parallax", "scale_breath", "drift"]


def _fallback_plan(usable: list[dict]) -> dict[str, Any]:
    """Deterministic plan used only if the LLM truly can't produce one. Not catastrophic: alternates
    beat lengths + adds motion on video beats so it isn't an automatic rhythm/motion/template_feel fail.
    _fit_to_total + _snap_to_beats reconcile lengths afterward."""
    segs = []
    for i, s in enumerate(usable):
        d = float(s.get("duration_s") or 2.0) * (1.15 if i % 2 else 0.88)   # break metronomic uniformity
        seg = {"n": s.get("n"), "duration_s": round(max(0.8, d), 2),
               "transition_in": "hard_cut" if (i == 0 or i % 4) else "crossfade"}
        if s.get("type") in ("seedance_shot", "real_clip"):
            seg["motion"] = _FALLBACK_MOTIONS[i % len(_FALLBACK_MOTIONS)]
        segs.append(seg)
    return {"segments": segs, "caption_style": "bold_center",
            "reasoning": "Deterministic fallback: varied beat lengths + motion on video beats.",
            "_fallback": True}


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
    light_leak_used = False
    for i, ps in enumerate(agent.get("segments", [])):
        n = str(ps.get("n"))
        d = by_n.get(n)
        if not d:
            continue
        t = d.get("type")
        trans = ps.get("transition_in") if ps.get("transition_in") in _TRANSITIONS else "hard_cut"
        if i == 0:
            trans = "hard_cut"
        if trans == "light_leak":            # design-system Batch C: at most ONE light leak per ad (a flourish, not a tic)
            if light_leak_used:
                trans = "crossfade"
            else:
                light_leak_used = True
        seg: dict[str, Any] = {"type": t, "duration_s": max(0.5, float(ps.get("duration_s") or 3)),
                               "transition_in": trans, "_max_s": limits.get(n), "_n": n}
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
            seg["card_template"] = d.get("card_template", "EndCard")   # legacy alias
            seg["card_style"] = ps.get("card_style") or d.get("card_style") or "glass"
            if isinstance(d.get("card_tiers"), dict):
                seg["card_tiers"] = d["card_tiers"]        # structured tiers (name/tagline/info/cta)
            seg["card_text"] = d.get("card_text", "")      # legacy flat fallback (name + info)
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


def _realize_ending(run: Run, segs: list[dict], sources: dict[str, str], inventory: dict) -> None:
    """The ad ALWAYS ends on a consistent, DESIGNED branded info card (D38). The closing beat is made a
    `card` (converted if it isn't) carrying: business NAME + a multi-line info block (address / phone /
    social, whatever the operator supplied — never fabricated) + a booking CTA. Consistent branding is
    the point, so there's no cross-run variety pressure. The name is always known, so the ad never ends
    anonymous."""
    if not segs:
        return
    name = str(inventory.get("business") or "").strip()
    if not name:
        return
    contact = inventory.get("contact") or {}
    address = str(contact.get("address") or inventory.get("location") or "").strip()
    if not address:                                  # last resort: the address Places matched (already fetched)
        try:
            address = str(json.loads((run.dir / "01_research.json").read_text())
                          .get("matched_address") or "").strip()
        except Exception:
            address = ""
    lines = [s for s in (address, contact.get("phone"), contact.get("social")) if s]
    info = "\n".join(lines)                           # stacked lines on the card (Cards.tsx splits on \n)
    booking = contact.get("booking_url")
    cta = "Book today" if booking else ("Visit us" if not lines else "Book today")

    last = segs[-1]
    if last.get("type") != "card":                    # convert the closing beat into a designed card
        last["type"] = "card"
        bg = _card_bg(inventory, set())               # a real after/neutral photo keeps the result on screen
        if bg:
            last["card_style"] = "photo_backed"
            last["bg_src"] = _stage(sources, f"endcard{Path(bg).suffix}", bg)
        else:
            last["card_style"] = "glass"              # palette gradient when no photo is free
        last["card_animation"] = last.get("card_animation") or "scale_pop"
        last.pop("motion", None); last.pop("playback_rate", None); last.pop("overlay", None)
    else:
        last.setdefault("card_style", "glass")
    tiers = dict(last.get("card_tiers") or {})
    tiers["name"] = name
    if info:
        tiers["info"] = info
    tiers.setdefault("cta", cta)
    tiers.setdefault("cta_style", "pill")
    last["card_tiers"] = tiers
    last["card_text"] = " · ".join([name] + lines)    # legacy flat fallback
    # Hold the card a fixed, clean ENDING_CARD_S — the voice + captions are fit to END before it (render()).
    last["_ending"] = True
    last["_max_s"] = None
    last["duration_s"] = config.ENDING_CARD_S
    run.log(f"Editor: ending card ({config.ENDING_CARD_S:.0f}s, clean) — {name}"
            + (f" · {' · '.join(lines)}" if lines else " (no contact info supplied)"))


def _realize_before_after(run: Run, segs: list[dict], by_n: dict, inventory: dict) -> None:
    """D43: when the operator gave before_/after_ photos, make the comparison OBVIOUS — a deliberate
    SEQUENTIAL REVEAL. Find an adjacent (before-role beat -> after-role beat) pair and stamp it: a
    'BEFORE' badge on the setup beat, an 'AFTER' badge + a `whip` reveal on the payoff beat. The Director
    guard (_before_after_feedback) makes the pair adjacent; this realizes the label + reveal
    deterministically so they don't depend on the (single-pass, D42) editor agent. No-op when there's no
    adjacent before->after pair. The before/after photos are the operator's REAL assets (never faked)."""
    if not inventory.get("has_before_after"):
        return
    by_path = {a["path"]: a for a in inventory.get("images", []) + inventory.get("videos", [])}
    ref_role = {tok: by_path.get(p, {}).get("role")
                for tok, p in _usable_assets(inventory)
                if by_path.get(p, {}).get("role") in ("before", "after")}

    def beat_role(seg: dict) -> str | None:
        d = by_n.get(str(seg.get("_n"))) or {}
        refs = list(d.get("moodboard_assets") or [])
        if d.get("asset_ref"):
            refs.append(d["asset_ref"])
        rs = {ref_role[r] for r in refs if r in ref_role}
        if rs == {"before"}:                       # a beat showing ONLY before photo(s) = the setup
            return "before"
        if "after" in rs:                          # any after photo present = the payoff/reveal
            return "after"
        return None

    roles = [beat_role(s) for s in segs]
    done = 0
    for i in range(len(segs) - 1):
        if roles[i] == "before" and roles[i + 1] == "after":
            before_seg, after_seg = segs[i], segs[i + 1]
            before_seg.setdefault("overlay", {"kind": "badge", "text": "BEFORE", "position": "tl"})
            after_seg.setdefault("overlay", {"kind": "badge", "text": "AFTER", "position": "tr"})
            if after_seg.get("transition_in") not in _OVERLAP_TRANSITIONS:
                after_seg["transition_in"] = "whip"   # the reveal cut into the after
            done += 1
    if done:
        run.log(f"Editor: before/after reveal — {done} BEFORE→AFTER pair(s) labeled + whip reveal")


def _card_bg(inventory: dict, used_refs: set[str]) -> str | None:
    """A real hero photo to back a card (rich, on-brand look). Prefer an @Image NOT already shown on
    screen, so the card doesn't repeat a frame (e.g. the moodboard composition or a shot seed). Falls
    back to any usable photo, else None (the card uses a palette gradient)."""
    from .triage import role_from_name
    images = [(tok, resolve_ref(inventory, tok)) for tok, _ in _usable_assets(inventory)
              if tok.startswith("@Image")]
    images = [(tok, p) for tok, p in images if p and Path(p).exists()]
    # A "before" photo is a problem-state image — never the card hero. Exclude it (a palette gradient
    # is better than a before-shot behind the CTA). Filename basename survives enhancement.
    images = [(tok, p) for tok, p in images if role_from_name(Path(p).name) != "before"]
    for tok, p in images:                # first an unused photo
        if tok not in used_refs:
            return p
    return images[0][1] if images else None   # else any non-before photo (better than a flat card)


def _fit_to_total(run: Run, segs: list[dict], target: float) -> None:
    """Make the timeline length = target (the Director's total_duration_s), in place:
    clamp video segs to their clip length and extensibles to EDITOR_MAX_EXTENSIBLE_S; then if the sum
    is short, grow extensibles up to their cap (log a shortfall if still short — don't stretch video);
    if the sum is long, shrink everything proportionally down to a floor."""
    cap_ext = config.EDITOR_MAX_EXTENSIBLE_S
    # The closing brand card is PINNED at ENDING_CARD_S and held out of the fit — the rest of the
    # timeline reconciles to (target - card), so the card always plays its full, clean hold.
    ending = next((s for s in segs if s.get("_ending")), None)
    if ending is not None:
        ending["duration_s"] = config.ENDING_CARD_S
        target = max(_MIN_SEG_S, target - config.ENDING_CARD_S)
    pool = [s for s in segs if s is not ending]
    for s in pool:
        if s["_max_s"] is not None:                       # video — never exceed its real content
            s["duration_s"] = min(s["duration_s"], s["_max_s"])
        else:                                             # card/moodboard — short capped beat
            s["duration_s"] = min(s["duration_s"], cap_ext)
    total = sum(s["duration_s"] for s in pool)

    if total < target - 0.05:                             # grow extensibles toward the target
        deficit = target - total
        for s in pool:
            if s["_max_s"] is None and deficit > 0.05:
                add = min(cap_ext - s["duration_s"], deficit)
                s["duration_s"] += add; deficit -= add
        if deficit > 0.5:
            run.log(f"[coverage shortfall] visual timeline {target - deficit:.1f}s < target {target:.0f}s "
                    f"— Director under-planned coverage; ending at the visual length (not stretching).")
    elif total > target + 0.05:                           # shrink proportionally down to the floor
        excess = total - target
        room = sum(max(0.0, s["duration_s"] - _MIN_SEG_S) for s in pool)
        if room > 0:
            for s in pool:
                s["duration_s"] -= excess * (max(0.0, s["duration_s"] - _MIN_SEG_S) / room)
    for s in segs:
        s["duration_s"] = round(s["duration_s"], 2)


def _assign_timestamps(segs: list[dict]) -> float:
    """Cumulative start/end per segment, accounting for crossfade overlap (mirrors the render). Returns
    the timeline's real length (what the voice must fit)."""
    cursor = 0.0
    for i, s in enumerate(segs):
        start = cursor if (i == 0 or s["transition_in"] not in _OVERLAP_TRANSITIONS) else max(0.0, cursor - _CROSSFADE_S)
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


def _compress_vo(src: str, dst: str) -> bool:
    """Light dynamic-range compression on the voiceover (ffmpeg acompressor) — softens synthetic
    'digital stiffness' toward phone-recorded voice. Subtle (gentle ratio + makeup). Returns True on
    success; False (caller keeps the uncompressed file) on any error."""
    try:
        r = subprocess.run(
            ["ffmpeg", "-y", "-i", src,
             "-af", "acompressor=threshold=-18dB:ratio=3:attack=15:release=180:makeup=2",
             dst], capture_output=True, timeout=60)
        return r.returncode == 0 and Path(dst).exists()
    except Exception:
        return False


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
