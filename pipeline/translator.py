"""Per-shot prompt composer (Claude + few-shot scaffold) — composes ONE single-shot Seedance prompt.

Multi-gen: the old whole-ad multi-shot Translator is replaced by compose_shot_prompt(), called by
the Shot Agent once per seedance_shot segment (and again per retry, with the judge's feedback baked
in). Each prompt is SINGLE-SHOT: one subject, one action, one camera, no labeled cuts, no speech
(voice is a separate TTS stage; generate_audio=False), no on-screen text (captions are the Editor's
job). Inter-shot transitions are gone — the Editor owns them now.

Also exposes _usable_assets / _build_reference_files: the single source of truth for @-token ->
asset-path mapping, shared by the Director and the keyframes/shots stages.

NOT for: creative decisions (the Director made those), choosing the shot list, or generation.
"""
from __future__ import annotations
import json
from typing import Any
from . import config
from .tracing import Run, log_llm_call
from .llm import call_claude, parse_json


def compose_shot_prompt(run: Run, segment: dict[str, Any], keyframe_path: str | None,
                        inventory: dict[str, Any], brief: dict[str, Any],
                        *, attempt: int = 1, feedback: list[str] | None = None) -> dict[str, Any]:
    """Compose a single-shot Seedance prompt for one seedance_shot segment.

    keyframe_path -> image_to_video (start frame); None -> text_to_video. On a retry, `feedback`
    carries the judge's reasons so the next attempt is informed, not random. Returns a dict with
    seedance_prompt, endpoint, duration, aspect_ratio, resolution, generate_audio (False), and
    prompt_reasoning. Stubs offline."""
    scaffold = (config.SCAFFOLDS_DIR / "prompt_translator.md").read_text()
    model = config.MODEL_ROUTER["prompt_translator"]

    duration = max(config.SEEDANCE_MIN_SHOT_S, int(round(float(segment.get("duration_s") or
                                                              config.SEEDANCE_MIN_SHOT_S))))
    has_keyframe = bool(keyframe_path)
    user = json.dumps({
        "segment": {
            "n": segment.get("n"),
            "intent": segment.get("intent", ""),
            "action": segment.get("action", ""),
            "camera": segment.get("camera", ""),
            "asset_ref": segment.get("asset_ref", "generated"),
        },
        "mood": brief.get("mood", ""),
        "has_keyframe_start_frame": has_keyframe,
        "duration_s": duration,
        "aspect_ratio": config.ASPECT_RATIO,
        "attempt": attempt,
        "judge_feedback": feedback or [],   # incorporate these on a retry (artifacts to avoid, etc.)
    }, indent=2)

    raw, thinking, in_tok, out_tok = call_claude(
        model, scaffold, user, stub=lambda: _stub_shot_prompt(segment, has_keyframe))
    log_llm_call(run, "shot_prompt", model, scaffold[:300] + "...", raw, in_tok, out_tok, 0, thinking)

    result = parse_json(raw)
    prompt = result.get("seedance_prompt", "")
    if not prompt:
        # never send an empty prompt to a paid gen — fall back to a deterministic single-shot line
        result = _stub_shot_prompt(segment, has_keyframe, parsed=True)
        prompt = result["seedance_prompt"]
    result["endpoint"] = "image_to_video" if has_keyframe else "text_to_video"
    result["duration"] = str(duration)
    result["aspect_ratio"] = config.ASPECT_RATIO
    result["resolution"] = config.RESOLUTION
    result["generate_audio"] = False          # voice is separate; ambient handled by the Editor
    result["_keyframe"] = keyframe_path
    return result


def _stub_shot_prompt(segment: dict[str, Any], has_keyframe: bool, parsed: bool = False) -> Any:
    """Deterministic single-shot prompt for offline runs / empty-LLM fallback."""
    intent = segment.get("intent", "the subject")
    action = segment.get("action", "a small natural motion")
    camera = segment.get("camera", "slow push-in")
    text = (f"Vertical 9:16. {intent}. {action}; {camera}. Natural light, authentic handheld feel, "
            f"one continuous shot, no cuts, no on-screen text. Concrete ambient sound.")
    obj = {"seedance_prompt": text,
           "prompt_reasoning": "STUB: single subject/action/camera; no speech; no on-screen text.",
           "_stub": True}
    return obj if parsed else json.dumps(obj)


# --- shared asset-token mapping (used by Director, keyframes, shots) --------

def _usable_assets(inventory: dict) -> list[tuple[str, str]]:
    """Single source of truth: ordered (token, original_path) for assets that can anchor a segment —
    recoverable photos -> @Image1.. (<=MAX_REF_IMAGES); usable videos -> @Video1.. (<=MAX_REF_VIDEOS).
    Used by the Director (which @-tokens exist), keyframes (real-photo conditioning), and the ref map
    below, so they never disagree."""
    out: list[tuple[str, str]] = []
    imgs = [a for a in inventory.get("images", []) if a.get("recoverable")]
    for i, a in enumerate(imgs[:config.MAX_REF_IMAGES], 1):
        out.append((f"@Image{i}", a["path"]))
    vids = [v for v in inventory.get("videos", []) if v.get("usable_as_reference")]
    for i, v in enumerate(vids[:config.MAX_REF_VIDEOS], 1):
        out.append((f"@Video{i}", v["path"]))
    return out


def _build_reference_files(inventory: dict) -> dict[str, str]:
    """Canonical @Token -> actual (enhanced) path, resolving enhanced photo paths via
    _enhancement_map. Built deterministically from the assets (decoupled from the Director's exact
    asset_ref strings, which it can fumble)."""
    enhanced = inventory.get("_enhancement_map", {})
    return {tok: enhanced.get(p, p) for tok, p in _usable_assets(inventory)}


def resolve_ref(inventory: dict, token: str) -> str | None:
    """Resolve a single @-token (e.g. '@Image2', '@Video1') to its enhanced/actual path, or None."""
    return _build_reference_files(inventory).get(token)
