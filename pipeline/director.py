"""Stage 1: Creative Director (Gemini 3.1 Pro, multimodal — SEES the assets).

Receives the actual photos AND videos plus the triage inventory + the chosen concept, and plans the
whole ad in one pass: a SEQUENCE OF MIXED SEGMENTS (seedance_shot / real_clip / moodboard / card),
the total duration (15-30s), the spoken script, mood, and the editing intent (pacing / editing_feel)
that feeds the EDITOR. Decides intent only — does not write per-shot prompts or the edit plan.

Mixed segments + the Seedance/Remotion bright line: see SPEC_followup_mixed_segments.md (D19-D21).
The Director plans creatively and NEVER reasons about cost (the $5 ceiling is a silent safety net).

NOT for: writing per-shot Seedance prompts (the per-shot composer) or the edit plan (the Editor).
"""
from __future__ import annotations
import json, re
from pathlib import Path
from typing import Any
from . import config
from .tracing import Run
from .llm import parse_json
from .translator import _usable_assets
from .agent.loop import run_agent_loop
from .agent import tools as agent_tools
from . import reviewers                       # 4-lens creative critic (self-correct loop)

BRIEF_FILE = "02_creative_brief.json"
SEGMENT_TYPES = {"seedance_shot", "real_clip", "moodboard", "card"}


def run_director(run: Run, inventory: dict[str, Any], concept: dict[str, Any] | None = None,
                 *, use_cache: bool = False) -> dict[str, Any]:
    cache = run.dir / BRIEF_FILE
    if use_cache and cache.exists():
        run.log("Director: loaded from cache"); return json.loads(cache.read_text())

    run.log("Director: planning mixed segments + duration + script (multimodal)")
    scaffold = _load_scaffold(inventory)
    model = config.MODEL_ROUTER["creative_director"]

    tokened = _usable_assets(inventory)
    image_paths = [p for tok, p in tokened if tok.startswith("@Image")]
    video_paths = [p for tok, p in tokened if tok.startswith("@Video")]
    if inventory.get("logo_path"): image_paths.insert(0, inventory["logo_path"])

    base_payload = {
        "business": inventory["business"], "location": inventory.get("location", ""),
        "brief": inventory["brief"],
        "has_before_after": inventory["has_before_after"],
        "has_logo": inventory["has_logo"], "palette": inventory["palette"],
        "chosen_concept": (concept or {}).get("chosen", {}),   # EXECUTE this (don't re-ideate)
        "asset_summary": _asset_summary(inventory),
        "duration_bounds_s": [config.MIN_DURATION_S, config.MAX_DURATION_S],
    }
    # (D38) No ending-variety pressure — the ad always closes on a consistent branded info card.
    ctx = {"business": inventory["business"], "brief": inventory["brief"]}

    def _produce(fb: str | None) -> tuple[dict[str, Any] | None, str | None]:
        payload = dict(base_payload)
        if fb:
            payload["prior_attempt_failed_review"] = {"fix_these": fb}
        agent_tools.set_assets(inventory)
        raw, thinking, _i, _o = run_agent_loop(
            run, "director", scaffold, model,
            ["inspect_asset", "trend_lookup", "design_hook"],
            user_text=json.dumps(payload, indent=2), image_paths=image_paths, video_paths=video_paths,
            max_iterations=4, thinking_level=config.DIRECTOR_THINKING_LEVEL,   # D46: faster director loop
            stub=lambda: (_stub_director(inventory), "STUB thinking: no GEMINI_API_KEY set", 0, 0))
        return _validate(parse_json(raw)), thinking

    # self-correcting critic loop: produce -> review (4 lenses) + deterministic guards -> regenerate.
    # Keep the BEST attempt (a passing one if any, else the highest-scoring) — not just the last.
    fb, brief, thinking, verdict, attempts, cands = None, None, None, {}, [], []
    for attempt in range(1, config.MAX_CREATIVE_RETRIES + 1):
        brief, thinking = _produce(fb)
        if brief is None:                       # invalid/empty brief — treat as a fail, regenerate
            fb = "Output was not a valid brief. Return the required JSON with a non-empty segments[]."
            attempts.append({"attempt": attempt, "passed": False, "failed_lenses": ["invalid_json"],
                             "improvement": fb})
            run.log(f"Director: attempt {attempt} produced an invalid brief — regenerating")
            continue
        verdict = reviewers.review(run, "director", brief, ctx)
        # Deterministic guards (run alongside the creative review): pacing (E2) + moodboard photo reuse +
        # voice coverage + perspective (deprioritize 1st-person on third-party-shot assets).
        pace_fb = _pacing_feedback(run, brief, inventory)
        mood_fb = _moodboard_feedback(run, brief, inventory)
        clip_fb = _clip_reuse_feedback(run, brief, inventory)
        cov_fb = _voice_coverage_feedback(run, brief)
        vlen_fb = _voice_length_feedback(run, brief)
        persp_fb = _perspective_feedback(run, brief)
        ba_fb = _before_after_feedback(run, brief, inventory)
        passed = (verdict["pass"] and not pace_fb and not mood_fb and not clip_fb and not cov_fb
                  and not vlen_fb and not persp_fb and not ba_fb)
        lenses = (list(verdict["failed_lenses"]) + (["pacing_too_slow"] if pace_fb else [])
                  + (["moodboard_reuse"] if mood_fb else []) + (["clip_reuse"] if clip_fb else [])
                  + (["voice_undercovers"] if cov_fb else [])
                  + (["voice_crushed" ] if vlen_fb else [])
                  + (["first_person_mismatch"] if persp_fb else [])
                  + (["before_after_not_obvious"] if ba_fb else []))
        attempts.append({"attempt": attempt, "passed": passed, "scores": verdict["scores"],
                         "failed_lenses": lenses, "improvement": verdict["improvement"]})
        cands.append((passed, _mean_score(verdict["scores"]), brief, thinking, verdict))
        if passed:
            break
        fb = "  ".join(p for p in (verdict["improvement"] if not verdict["pass"] else "",
                                   pace_fb or "", mood_fb or "", clip_fb or "", cov_fb or "",
                                   vlen_fb or "", persp_fb or "", ba_fb or "") if p)
        run.log(f"Director: attempt {attempt} regenerating ({lenses})")
    if not cands:
        raise RuntimeError("Director returned an empty/invalid brief after retries")
    _, _, brief, thinking, verdict = max([c for c in cands if c[0]] or cands, key=lambda c: c[1])

    brief["_review"] = {"passed": verdict.get("pass", True), "scores": verdict.get("scores", {}),
                        "failed_lenses": verdict.get("failed_lenses", []),
                        "improvement": verdict.get("improvement", ""), "attempts": attempts}
    cache.write_text(json.dumps(brief, indent=2))

    segs = brief.get("segments", [])
    counts = _type_counts(segs)
    rationale = (f"**Total duration:** {brief.get('total_duration_s')}s\n\n"
                 f"**Composition:** {brief.get('composition_reasoning','')}\n\n"
                 f"**Angle:** {brief.get('creative_angle','')}\n\n"
                 f"**Script:** {brief.get('script_reasoning','')}\n\n"
                 f"**Segments** ({', '.join(f'{k}×{v}' for k, v in counts.items())}):\n"
                 + "\n".join(f"- {s.get('n')}. [{s.get('type')}] {s.get('intent','')} — {s.get('why','')}"
                             for s in segs))
    run.reason("Director (Gemini)", thinking, rationale)
    run.log(f"Director: {len(segs)} segments ({counts}), {brief.get('total_duration_s')}s, "
            f"angle='{str(brief.get('creative_angle',''))[:60]}'")
    return brief


def _validate(brief: dict[str, Any]) -> dict[str, Any] | None:
    """Require a non-empty segments[] of known types and a total_duration_s in bounds. Clamp
    duration; default it from segment durations if missing. Returns the brief, or None to retry."""
    segs = brief.get("segments")
    if not isinstance(segs, list) or not segs:
        return None
    if any(s.get("type") not in SEGMENT_TYPES for s in segs):
        return None
    # F2: a seedance_shot MUST seed from a REAL photo (@Image…). A pure text-to-video shot ("generated"
    # or any non-@Image ref) reads as AI-stock and undercuts authenticity — drop it (safety net; the
    # scaffold already forbids it). If that empties the plan, return None to regenerate.
    segs = [s for s in segs
            if s.get("type") != "seedance_shot" or str(s.get("asset_ref", "")).startswith("@Image")]
    if not segs:
        return None
    brief["segments"] = segs
    dur = brief.get("total_duration_s")
    if not isinstance(dur, (int, float)) or dur <= 0:
        dur = sum(float(s.get("duration_s") or 0) for s in segs) or config.MIN_DURATION_S
    brief["total_duration_s"] = max(config.MIN_DURATION_S, min(config.MAX_DURATION_S, float(dur)))
    # Perspective fields (the Director SEES the assets). Default asset_perspective to third_party — the
    # SAFE assumption for SMB submissions (a photographer shot the work), which keeps the 1st-person guard
    # active when the field is omitted. narrative_person left "" if absent (the guard's text scan catches it).
    ap = str(brief.get("asset_perspective") or "").strip().lower()
    brief["asset_perspective"] = ap if ap in {"third_party", "first_person", "mixed"} else "third_party"
    np_ = str(brief.get("narrative_person") or "").strip().lower()
    brief["narrative_person"] = np_ if np_ in {"first", "second", "third"} else ""
    return brief


def _pacing_feedback(run: Run, brief: dict[str, Any], inventory: dict[str, Any]) -> str | None:
    """E2 pace guard: if the brief's average beat is too slow AND there are still unused usable assets
    (so more distinct beats are feasible), return regen feedback pushing more/shorter beats. Returns
    None when pace is fine or no spare assets exist (can't honestly add beats). Logs the metric always."""
    segs = brief.get("segments", [])
    n = len(segs)
    dur = float(brief.get("total_duration_s") or 0)
    if n == 0 or dur <= 0:
        return None
    avg = dur / n
    usable = len(_usable_assets(inventory))
    run.log(f"Director: pacing check — {n} beats / {dur:.0f}s = {avg:.1f}s avg ({usable} usable assets)")
    if avg <= config.PACING_MAX_AVG_BEAT_S or n >= usable:
        return None
    target_n = max(n + 2, int(dur / 1.8) + 1)
    return (f"PACING TOO SLOW: {n} beats over {dur:.0f}s ≈ {avg:.1f}s/beat. Social ads cut faster — aim "
            f"for ~{target_n}+ beats (~1.5–2s each). You have {usable} usable assets; turn more of them "
            f"into distinct short beats (split long holds; add real_clip / moodboard beats). Add MORE, "
            f"SHORTER segments — do NOT pad the existing ones.")


_SPOKEN_WPS = 2.4   # ~spoken words/second for the VO duration estimate


def _voice_coverage_feedback(run: Run, brief: dict[str, Any]) -> str | None:
    """Guard the freed-script length: the VO must roughly COVER the video, else the voice ends mid-ad
    and the back half plays silent (just music) — feels unfinished. Estimate spoken seconds from the
    word count; if it covers < ~65% of total_duration_s, regenerate (lengthen the script OR shorten the
    total). None if coverage is fine. (Inverse of the old voice-OVERRUN problem.)"""
    script = str(brief.get("speech") or brief.get("script") or "")
    words = len(script.split())
    total = float(brief.get("total_duration_s") or 0)
    if words == 0 or total <= 0:
        return None
    est_vo = words / _SPOKEN_WPS
    run.log(f"Director: voice-coverage check — {words} words ≈ {est_vo:.1f}s VO vs {total:.0f}s video")
    if est_vo >= 0.65 * total:
        return None
    target_words = int(0.85 * total * _SPOKEN_WPS)
    shorter = max(config.MIN_DURATION_S, int(est_vo / 0.85) + 1)
    fix_b = (f", or (b) drop total_duration_s to ~{shorter}s so the voice fills it"
             if shorter < total - 1 else "")
    return (f"VOICE UNDER-COVERS: the script is ~{words} words (~{est_vo:.0f}s spoken) but "
            f"total_duration_s is {total:.0f}s — the voice ends near the halfway point, leaving "
            f"~{total - est_vo:.0f}s of SILENT video. Fix it: (a) develop the idea to ~{target_words} "
            f"words (still hook + ONE idea, NO CTA — just more of the same thread){fix_b}. "
            f"Match length to content.")


def _voice_length_feedback(run: Run, brief: dict[str, Any]) -> str | None:
    """Guard the OTHER direction: a script too LONG for the video gets CRUSHED. The editor atempo-fits the
    voice to the video, capped at VOICE_MAX_ATEMPO — so an over-long script is sped up and sounds rushed/
    chipmunky (run 0032: ~28s script over a ~20s video = 1.55× = the cap). Compare the estimated spoken
    seconds to the video's spoken region = (SUM OF BEAT DURATIONS − ending card); the editor fits to the
    beats, NOT the stated total_duration_s, so a plan whose beats sum short is the real culprit. Fire above
    ~1.2× (a comfortable atempo). None if fine. Complements _voice_coverage_feedback (the UNDER case)."""
    segs = brief.get("segments", [])
    script = str(brief.get("speech") or brief.get("script") or "")
    words = len(script.split())
    if not segs or words == 0:
        return None
    vid = sum(float(s.get("duration_s") or 0) for s in segs)
    region = max(1.0, vid - config.ENDING_CARD_S)
    est_vo = words / _SPOKEN_WPS
    ratio = est_vo / region
    run.log(f"Director: voice-length check — {words} words ≈ {est_vo:.1f}s VO vs ~{region:.1f}s region "
            f"(beats sum {vid:.1f}s) = {ratio:.2f}×")
    if ratio <= 1.2:
        return None
    target_words = int(region * 1.1 * _SPOKEN_WPS)
    return (f"SCRIPT TOO LONG — THE VOICE WILL BE CRUSHED: ~{words} words (~{est_vo:.0f}s spoken) over a "
            f"video whose beats sum to only ~{vid:.0f}s (~{region:.0f}s before the "
            f"{config.ENDING_CARD_S:.0f}s card) — the voice gets sped up {ratio:.2f}× and sounds rushed. "
            f"Match the spoken length to the video: cut the script to ~{target_words} words, AND/OR add or "
            f"lengthen beats so the video fills {config.MIN_DURATION_S}–{config.MAX_DURATION_S}s. (Your "
            f"beat durations must also sum to about your total_duration_s.)")


def _moodboard_feedback(run: Run, brief: dict[str, Any], inventory: dict[str, Any]) -> str | None:
    """Guard against a repetitive showcase: when moodboards REUSE the same photos (a photo appears in
    >1 moodboard), the moodboard frames look samey. Returns regen feedback capping the moodboard count
    to what the distinct-photo pool supports + demanding distinct photos per moodboard; None if clean.
    (The majority-real gate can over-produce moodboards on verticals with few photos — e.g. 4 moodboards
    from 5 photos forces reuse.)"""
    from collections import Counter
    mbs = [s for s in brief.get("segments", []) if s.get("type") == "moodboard"]
    if len(mbs) < 2:
        return None
    used = Counter(a for s in mbs for a in (s.get("moodboard_assets") or []))
    reused = sorted(a for a, c in used.items() if c > 1)
    if not reused:
        return None
    photos = len([a for a in inventory.get("images", []) if a.get("recoverable")])
    vids = len([v for v in inventory.get("videos", []) if v.get("usable_as_reference")])
    cap = max(1, photos // 2)
    run.log(f"Director: moodboard check — {len(mbs)} moodboards reuse photos {reused} "
            f"({photos} distinct photos, {vids} videos)")
    return (f"REPETITIVE MOODBOARDS: {len(mbs)} moodboards reuse the same photos ({', '.join(reused)} "
            f"appear in more than one) — the showcase looks repetitive. You only have {photos} distinct "
            f"photos. Use at most {cap} moodboard(s), each with DISTINCT photos (no photo in two "
            f"moodboards); turn the other real beats into `real_clip` windows (you have {vids} videos — "
            f"different trims are distinct beats) so the visuals stay varied.")


_FIRST_PERSON_RE = re.compile(r"\bI\b|\bI'm\b|\bI've\b|\bI'd\b|\bI'll\b|\bmy\b|\bmine\b|\bme\b", re.IGNORECASE)


def _has_first_person_singular(text: str) -> bool:
    return bool(_FIRST_PERSON_RE.search(text or ""))


def _perspective_feedback(run: Run, brief: dict[str, Any]) -> str | None:
    """Perspective guard (deprioritize 1st-person). Most SMB assets are shot by a THIRD PARTY (a
    photographer filming the subject/work), so a first-person 'I / my / my-own-POV' narration reads as a
    mismatch. Fires when the script is first-person-singular (or narrative_person ==
    'first') WHILE asset_perspective != 'first_person'. None when consistent. (First-person stays valid
    for genuinely first-person/selfie footage; a REAL attributed review quote is the scaffold's exception.)"""
    ap = str(brief.get("asset_perspective") or "").strip().lower()
    np_ = str(brief.get("narrative_person") or "").strip().lower()
    script = str(brief.get("speech") or brief.get("script") or "")
    if ap == "first_person":
        return None
    first_person = (np_ == "first") or _has_first_person_singular(script)
    run.log(f"Director: perspective check — asset_perspective={ap or '?'}, narrative_person={np_ or '?'}, "
            f"first_person_text={first_person}")
    if not first_person:
        return None
    return ("PERSPECTIVE MISMATCH: the provided assets are clearly shot by a THIRD PARTY (someone filming "
            "the subject/space/work), so first-person 'I / my / my-own-POV' narration reads as fake. "
            "Rewrite the script AND any caption in SECOND person (address 'you') or THIRD person "
            "(observe/showcase) — drop 'I/my' and immersive self-POV; if you used influencer_pov, switch to "
            "social_native. Set narrative_person to 'second' or 'third'. (First-person is ONLY for "
            "genuinely first-person/selfie footage; a REAL attributed customer-review quote is the one "
            "exception.)")


def _clip_reuse_feedback(run: Run, brief: dict[str, Any], inventory: dict[str, Any]) -> str | None:
    """Guard against a repetitive showcase from the VIDEO side: the same source clip shown over and over
    (e.g. pinkhair.mp4 in 3 beats) reads as looping. Flags when one @Video source backs >2 real_clip
    beats OR two same-source real_clips sit back-to-back. Returns regen feedback; None if clean. (Video
    analog of _moodboard_feedback — different trims of one source still count as the same footage.)"""
    from collections import Counter
    segs = brief.get("segments", [])
    rc = [s for s in segs if s.get("type") == "real_clip" and s.get("clip_ref")]
    if len(rc) < 2:
        return None
    cap = 2
    counts = Counter(str(s.get("clip_ref")) for s in rc)
    over = sorted(r for r, c in counts.items() if c > cap)
    full = sorted(segs, key=lambda s: s.get("n", 0))
    btb = sorted({str(a.get("clip_ref")) for a, b in zip(full, full[1:])
                  if a.get("type") == "real_clip" and b.get("type") == "real_clip"
                  and a.get("clip_ref") and a.get("clip_ref") == b.get("clip_ref")})
    vids = len([v for v in inventory.get("videos", []) if v.get("usable_as_reference")])
    photos = len([a for a in inventory.get("images", []) if a.get("recoverable")])
    run.log(f"Director: clip-reuse check — sources {dict(counts)}, over-cap {over}, back-to-back {btb}")
    if not over and not btb:
        return None
    parts = []
    if over:
        parts.append(f"{', '.join(over)} used in >2 beats")
    if btb:
        parts.append(f"{', '.join(btb)} repeats back-to-back")
    return (f"REPETITIVE FOOTAGE: {'; '.join(parts)} — the same clip shown over and over reads as "
            f"repetitive/looping. Use each @Video source in AT MOST 2 beats, and NEVER two same-source "
            f"beats in a row. You have {vids} video(s) + {photos} photo(s): vary the sources, interleave "
            f"with real-photo (moodboard) or seedance beats, or cut to fewer real_clips. (Different trims "
            f"of one source still count as the same footage.)")


def _before_after_feedback(run: Run, brief: dict[str, Any], inventory: dict[str, Any]) -> str | None:
    """Before/after guard (D43): when the operator provided before_/after_ photos, a before-role beat is
    only valid as the SETUP half of an ADJACENT before->after REVEAL — so the transformation is obvious.
    Fires when a 'before' beat is NOT immediately followed by an 'after' beat (the lone-'before' bug — a
    before moodboard with the afters scattered elsewhere reads as no comparison at all). Returns regen
    feedback; None when clean, or when no before-role beat is used (using before/after isn't forced)."""
    if not inventory.get("has_before_after"):
        return None
    by_path = {a["path"]: a for a in inventory.get("images", []) + inventory.get("videos", [])}
    ref_role = {tok: by_path.get(p, {}).get("role")
                for tok, p in _usable_assets(inventory)
                if by_path.get(p, {}).get("role") in ("before", "after")}
    if "before" not in ref_role.values() or "after" not in ref_role.values():
        return None                                   # need at least one of each to build a reveal

    def beat_role(s: dict) -> str | None:
        refs = list(s.get("moodboard_assets") or [])
        if s.get("asset_ref"):
            refs.append(s["asset_ref"])
        rs = {ref_role[r] for r in refs if r in ref_role}
        if rs == {"before"}:
            return "before"
        if "after" in rs:
            return "after"
        return None

    segs = sorted(brief.get("segments", []), key=lambda s: s.get("n", 0))
    roles = [beat_role(s) for s in segs]
    if "before" not in roles:
        return None
    lone = [segs[i].get("n") for i, r in enumerate(roles)
            if r == "before" and (i + 1 >= len(roles) or roles[i + 1] != "after")]
    run.log(f"Director: before/after check — beat roles "
            f"{[(s.get('n'), r) for s, r in zip(segs, roles) if r]}, lone-before {lone}")
    if not lone:
        return None
    befores = sorted(t for t, r in ref_role.items() if r == "before")
    afters = sorted(t for t, r in ref_role.items() if r == "after")
    return (f"BEFORE/AFTER NOT OBVIOUS: beat(s) {lone} show a 'before' photo with NO matching 'after' "
            f"right after, so the viewer never sees the change. The operator gave you before photos "
            f"({', '.join(befores)}) and after photos ({', '.join(afters)}). Build a TRANSFORMATION "
            f"REVEAL: place a BEFORE beat IMMEDIATELY followed by its matching AFTER beat (pair by number "
            f"— before_1 → after_1), so the transformation is the payoff. A 'before' photo is ONLY ever "
            f"the setup half of an adjacent before→after pair — never a lone beat or scattered b-roll.")


def _mean_score(scores: dict) -> float:
    vals = [float(v) for v in (scores or {}).values() if isinstance(v, (int, float))]
    return sum(vals) / len(vals) if vals else 0.0


def _type_counts(segs: list[dict]) -> dict[str, int]:
    out: dict[str, int] = {}
    for s in segs:
        t = str(s.get("type", "?"))
        out[t] = out.get(t, 0) + 1
    return out


def _asset_summary(inv: dict) -> list[dict]:
    """One row per usable asset, labeled with the @-token (ref) the Director uses to anchor a
    segment to it. Quality/remediation from triage; the model also sees the pixels."""
    by_path = {a["path"]: a for a in inv.get("images", []) + inv.get("videos", [])}
    out = []
    for tok, p in _usable_assets(inv):
        a = by_path.get(p, {})
        row = {"ref": tok, "file": Path(p).name, "kind": a.get("type"), "quality": a.get("note")}
        if a.get("type") == "image":
            row["remediation"] = a.get("remediation", [])
            if a.get("role"):
                row["role"] = a["role"]          # before/after (operator filename label) — see hard rules
        elif a.get("type") == "video":
            row["length_s"] = a.get("duration_s")   # full source; real_clip trim_s picks the window
        out.append(row)
    return out


def _load_scaffold(inv: dict) -> str:
    # Inject the whole multi-vertical playbook (formats + per-vertical "what converts" + hooks) so the
    # Director reasons WITH Motion's data — vertical-agnostic; the model picks the row for this brief.
    from .refs import reference_block
    t = (config.SCAFFOLDS_DIR / "creative_director.md").read_text() \
        + reference_block(["ad_formats.md", "smb_verticals.md", "hooks.md", "script_craft.md"])
    return (t.replace("{{business}}", str(inv.get("business", "")))
             .replace("{{brief}}", str(inv.get("brief", "")))
             .replace("{{has_before_after}}", str(inv.get("has_before_after", False)))
             .replace("{{has_logo}}", str(inv.get("has_logo", False)))
             .replace("{{palette}}", ", ".join(inv.get("palette", [])) or "not detected")
             .replace("{{min_duration_s}}", str(config.MIN_DURATION_S))
             .replace("{{max_duration_s}}", str(config.MAX_DURATION_S)))


def _stub_director(inv: dict[str, Any] | None = None) -> str:
    """Vertical-NEUTRAL canned brief so offline/no-key runs complete for ANY business (the real loop
    runs only with a key). Uses the actual business name; no hardcoded vertical."""
    biz = (inv or {}).get("business", "this local business")
    return json.dumps({
        "creative_angle": f"STUB: an authentic, specific look at {biz} (offline placeholder).",
        "total_duration_s": 18,
        "composition_reasoning": "STUB: a real-footage open, distinct quick beats, a moodboard of real "
                                 "photos, a clean CTA card.",
        "script": f"STUB voiceover for {biz}: real, specific, and worth the trip. Come see for yourself.",
        "script_reasoning": "STUB placeholder script (offline).",
        "speech": f"STUB voiceover for {biz}: real, specific, and worth the trip. Come see for yourself.",
        "mood": "warm, authentic, local",
        "pacing": "brisk",
        "asset_perspective": "third_party",
        "narrative_person": "second",
        "editing_feel": "fast clean hard cuts with one soft crossfade into the closing card",
        "hook": {"hook_visual": "the strongest real asset, in motion", "hook_line": "STUB hook line.",
                 "mechanic": "newness", "why": "stub", "cut_dead_first_second": True},
        "segments": [
            {"n": 1, "type": "real_clip", "duration_s": 2.5, "intent": "authentic opener",
             "clip_ref": "@Video1", "trim_s": [0, 2.5], "why": "real footage hooks"},
            {"n": 2, "type": "seedance_shot", "duration_s": 2.5, "intent": "hero motion beat",
             "action": "natural subject motion", "camera": "slow push-in", "asset_ref": "@Image1",
             "why": "motion the stills can't supply"},
            {"n": 3, "type": "moodboard", "duration_s": 3, "intent": "consolidate real photos",
             "moodboard_assets": ["@Image2", "@Image3"], "why": "scattered assets -> one designed frame"},
            {"n": 4, "type": "card", "duration_s": 3, "intent": "CTA", "card_template": "EndCard",
             "card_text": "Come see for yourself", "why": "land the CTA cleanly"},
        ],
        "_stub": True,
    })
