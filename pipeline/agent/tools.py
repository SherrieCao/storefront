"""Agent tool implementations — self-register with the registry on import.

- inspect_asset: exposes triage's per-asset technical assessment to the Director on demand
  (data it can't read off the pixels). Reads a per-run context set by the caller.
- trend_lookup: a STUB demonstrating how a live tool plugs in end-to-end (no real dependency).

NOT for: creative decisions (the scaffold owns those) or generation.
"""
from __future__ import annotations
import json
from pathlib import Path
from typing import Any
from .registry import tool

# Per-run context: filename -> triage assessment. Set by the Director before the loop runs.
_ASSETS: dict[str, dict] = {}


def set_assets(inventory: dict[str, Any]) -> None:
    _ASSETS.clear()
    for a in inventory.get("images", []) + inventory.get("videos", []):
        name = Path(str(a.get("path", ""))).name
        if name:
            _ASSETS[name] = a


@tool("inspect_asset",
      "Get triage's technical assessment of ONE provided photo/video by filename — resolution, "
      "blur and lighting scores, the remediation plan, recoverable flag, and a note. Use it to "
      "decide whether an asset is strong enough to anchor a shot.",
      {"type": "object",
       "properties": {"filename": {"type": "string",
                                   "description": "asset filename, e.g. 'photo_1.jpg'"}},
       "required": ["filename"]},
      not_for="editing or enhancing the asset (that's the enhance stage)")
def inspect_asset(filename: str) -> dict[str, Any]:
    a = _ASSETS.get(filename) or _ASSETS.get(Path(str(filename)).name)
    if not a:
        return {"error": f"no asset named '{filename}'", "available": sorted(_ASSETS)}
    keep = ("path", "type", "resolution", "blur_score", "lighting_score",
            "remediation", "recoverable", "usable_as_reference", "note")
    return {k: a[k] for k in keep if k in a}


@tool("trend_lookup",
      "Look up current short-form video trends for a business vertical (e.g. 'salon', 'bakery') "
      "— trending hooks, audio styles, and pacing — to inform the creative angle. STUB: returns "
      "canned data; this is the template for wiring a real trends source later.",
      {"type": "object",
       "properties": {"vertical": {"type": "string",
                                   "description": "business vertical, e.g. 'salon'"}},
       "required": ["vertical"]},
      not_for="fabricating prices/hours/offers (only the operator's brief is authoritative for those)")
def trend_lookup(vertical: str) -> dict[str, Any]:
    # STUB — canned, no external dependency. Replace with a real trends API later.
    return {
        "vertical": vertical,
        "trending_hooks": ["before/after reveal in first 2s", "POV: you booked the appointment",
                           "satisfying process close-up (ASMR)"],
        "audio_style": "upbeat pop with a beat drop on the reveal",
        "pacing": "hard cuts every 1.5-2s, front-loaded payoff",
        "_stub": True,
    }


# --- Hook Designer: the opening ~3s. A mandatory tool the Director calls (and may re-call). ---
# FUTURE: because the hook is a discrete object, N variants can later be regenerated against the
# same ad body for cheap A/B testing (Motion's winning mechanism). Not built here.
_HOOK_SYSTEM = """You are a short-form video-ad Hook Designer. Design ONLY the opening ~3 seconds
(the thumb-stop hook) for ONE social ad, given the business, chosen format, creative angle, brief,
and top assets. Output JSON only: {"hook_visual","hook_line","mechanic","why","cut_dead_first_second"}.

Rules (from ~$14B/yr Meta data):
- CUT THE DEAD FIRST SECOND: no logo, no slow zoom, no static opener. Put motion in the first ~8
  frames — a zoom, a swipe, a hand/subject entering, or a face. (cut_dead_first_second = true)
- A human FACE/subject in frame one beats product-only for thumb-stop (~30% lift) when assets allow.
- On-screen text in the first second (a problem/claim) strengthens the hook and is added in POST — but
  the generator renders no text, so the visual must ALSO thumb-stop on its own (motion/face) and the
  generated cut opens on the spoken hook_line.
- Concrete/offer mechanics WIN (newness, price, urgency, offer) — they beat clever. The five
  big-brand mechanics (confession, bold_claim, relatability, contrast, curiosity) are secondary for
  local SMBs.
- hook_line MUST use a SPECIFIC detail from the brief (location, price, owner, quirk) — never generic.
mechanic is one of: confession|bold_claim|relatability|contrast|curiosity|newness|price|urgency|offer.
hook_visual = what fills frame 0-3s (motion/face/problem in frame ONE). hook_line = the opening words,
tight and speakable. why = why this stops the scroll for THIS business."""


@tool("design_hook",
      "Design the opening ~3 seconds — the thumb-stop hook. Returns {hook_visual, hook_line, "
      "mechanic, why, cut_dead_first_second}. Call AFTER choosing format + angle (pass them in) so "
      "the hook fits; RE-CALL it if the returned hook is weak/generic. Then build shot 1 + the "
      "opening spoken line around it.",
      {"type": "object",
       "properties": {
           "business":   {"type": "string"},
           "format":     {"type": "string", "description": "the chosen ad format"},
           "angle":      {"type": "string", "description": "the creative angle / POV chosen"},
           "brief":      {"type": "string", "description": "the operator brief (for a specific detail)"},
           "top_assets": {"type": "string", "description": "strongest @-ref assets + notes"}},
       "required": ["business", "format", "angle", "brief"]},
      not_for="writing the full script or the Seedance prompt")
def design_hook(business: str = "", format: str = "", angle: str = "",
                brief: str = "", top_assets: str = "") -> dict[str, Any]:
    from .. import config
    payload = json.dumps({"business": business, "format": format, "angle": angle,
                          "brief": brief, "top_assets": top_assets}, indent=2)
    if not config.GEMINI_API_KEY:          # offline stub (the real loop only runs with a key)
        return {"hook_visual": "subject enters frame, quick push-in", "hook_line": "STUB hook",
                "mechanic": "curiosity", "why": "stub: no GEMINI_API_KEY",
                "cut_dead_first_second": True, "_stub": True}
    try:
        import time
        from google import genai
        from google.genai import types
        from ..tracing import get_active_run, log_llm_call
        from ..llm import parse_json
        from ..refs import reference_block
        from .. import reviewers
        model = config.MODEL_ROUTER.get("hook_designer", config.MODEL_ROUTER["creative_director"])
        client = genai.Client(api_key=config.GEMINI_API_KEY)
        # ground the hook in the full Motion hook playbook, not just the inline summary
        system = _HOOK_SYSTEM + reference_block(["hooks.md"])
        run = get_active_run()             # set by run_agent_loop so calls are logged + costed
        ctx = {"business": business, "brief": brief}

        def _produce(fb):
            p = json.loads(payload)
            if fb:
                p["prior_attempt_failed_review"] = {"fix_these": fb}
            t0 = time.time()
            resp = client.models.generate_content(
                model=model, contents=[json.dumps(p, indent=2)],
                config=types.GenerateContentConfig(system_instruction=system,
                                                   response_mime_type="application/json"))
            if run is not None:
                u = resp.usage_metadata
                log_llm_call(run, "hook_designer", model, "[design_hook]", resp.text or "",
                             (u.prompt_token_count or 0), (u.candidates_token_count or 0),
                             int((time.time() - t0) * 1000), None)
            return parse_json(resp.text)

        # self-correcting hook critic loop (skipped if no active run to review against)
        fb, spec, verdict = None, {}, {}
        for attempt in range(1, config.MAX_CREATIVE_RETRIES + 1):
            spec = _produce(fb)
            if not isinstance(spec, dict):   # Gemini sometimes returns a JSON array; don't index it as a dict
                spec = {"hook_line": "", "mechanic": "", "why": "non-object hook output", "_nonobject": True}
            if run is None:
                break
            verdict = reviewers.review(run, "hook", spec, ctx)
            if verdict.get("pass", True):
                break
            fb = verdict.get("improvement", "")
            run.log(f"Hook: review attempt {attempt} FAIL ({verdict.get('failed_lenses')}) — regenerating")
        spec["_review"] = {"passed": verdict.get("pass", True),
                           "improvement": verdict.get("improvement", "")}
        return spec
    except Exception as e:
        return {"hook_line": "", "mechanic": "", "why": f"hook_designer error: {e}",
                "cut_dead_first_second": True, "_error": str(e)}


# --- Ending Designer: the final ~2-3s. Mirrors the Hook Designer — a tool the Director calls, so the
# ending is a discrete, inspectable object. Forces a DELIBERATE ending instead of defaulting to a card
# (a branded card every time is a template tell). The Director realizes the returned ending in the
# LAST segment. Lean: one call, no internal reviewer (the creative reviewer already checks the ending).
_ENDING_SYSTEM = """You are the Ending Designer for a short-form social ad. You design ONLY the final
~2-3 seconds — HOW the ad delivers its real info (business name / location / booking) and lands. JSON only.

A branded info CARD every single time is a template tell — "the moment the video stops pretending to be
content." Pick the ONE ending that fits the voice_style + concept; do NOT default to card unless it
genuinely fits. Types:
- card: a clean closing info card (name | location | booking). Best for local_ad / trust-led.
- overlay: name/location/@handle as a lower-third text overlay on the final VISUAL beat — softer,
  native. Good for social_native / influencer_pov.
- callback: the final beat calls back to the hook (visual/verbal); the practical info lives in the
  CAPTION/bio, NOT on screen.
- tag: a minimal @handle / location-pin vibe; info mainly in the caption/bio.
- linger: the final real shot just holds; info via a small overlay or the caption.

Rules:
- The info must be delivered SOMEWHERE: on-screen (card/overlay) OR, for callback/tag/linger, in a
  caption you write (caption_suggestion).
- REAL info only — NEVER fabricate a phone/URL/handle (use one ONLY if it's verbatim in the brief);
  otherwise name + real location + a plain ask ("Book today").
- Match the voice: social_native/influencer_pov lean overlay/callback/tag/linger; local_ad leans card.

Output JSON:
{"ending_type":"card|overlay|callback|tag|linger",
 "on_screen_text":"card/overlay text — 'Name | Location | Book' — EMPTY for callback/tag/linger",
 "caption_suggestion":"the IG caption that carries the info (esp. for callback/tag/linger)",
 "why":"one line: why this ending fits the voice + concept"}"""


# DEPRECATED (D39): no longer wired into any agent's tool list. The EDITOR now deterministically builds
# the closing brand card from brief.json contact (editor._realize_ending), so the Director doesn't design
# the ending. Left registered (harmless) to avoid churn; safe to delete in a future cleanup.
@tool("design_ending",
      "Design the final ~2-3 seconds — how the ad delivers its name/location/booking and lands. Returns "
      "{ending_type, on_screen_text, caption_suggestion, why}. Call AFTER planning segments + setting "
      "voice_style; then make the LAST segment realize it (card -> a card with on_screen_text; overlay "
      "-> the last visual beat carries a lower_third overlay with on_screen_text; callback/tag/linger -> "
      "the last visual beat just plays, info goes to the caption). Copy it into the `ending` field.",
      {"type": "object",
       "properties": {
           "business":    {"type": "string"},
           "location":    {"type": "string", "description": "city/area (for the card/overlay)"},
           "voice_style": {"type": "string", "description": "local_ad | social_native | influencer_pov"},
           "angle":       {"type": "string", "description": "the creative angle / POV"},
           "hook_line":   {"type": "string", "description": "the hook (so a callback can echo it)"},
           "brief":       {"type": "string", "description": "operator brief (real info only)"}},
       "required": ["business", "voice_style"]},
      not_for="writing the script or the closing card's full layout (the editor renders it)")
def design_ending(business: str = "", location: str = "", voice_style: str = "", angle: str = "",
                  hook_line: str = "", brief: str = "") -> dict[str, Any]:
    from .. import config
    payload = json.dumps({"business": business, "location": location, "voice_style": voice_style,
                          "angle": angle, "hook_line": hook_line, "brief": brief}, indent=2)
    if not config.GEMINI_API_KEY:          # offline stub
        return {"ending_type": "card", "on_screen_text": f"{business} | {location} | Book today",
                "caption_suggestion": "", "why": "stub: no GEMINI_API_KEY", "_stub": True}
    try:
        import time
        from google import genai
        from google.genai import types
        from ..tracing import get_active_run, log_llm_call
        from ..llm import parse_json
        model = config.MODEL_ROUTER.get("hook_designer", config.MODEL_ROUTER["creative_director"])
        client = genai.Client(api_key=config.GEMINI_API_KEY)
        run = get_active_run()
        t0 = time.time()
        resp = client.models.generate_content(
            model=model, contents=[payload],
            config=types.GenerateContentConfig(system_instruction=_ENDING_SYSTEM,
                                               response_mime_type="application/json"))
        if run is not None:
            u = resp.usage_metadata
            log_llm_call(run, "ending_designer", model, "[design_ending]", resp.text or "",
                         (u.prompt_token_count or 0), (u.candidates_token_count or 0),
                         int((time.time() - t0) * 1000), None)
        spec = parse_json(resp.text)
        return spec if isinstance(spec, dict) else {"ending_type": "card", "_parse_error": True}
    except Exception as e:
        return {"ending_type": "card", "on_screen_text": f"{business} | {location} | Book today",
                "caption_suggestion": "", "why": f"ending_designer error: {e}", "_error": str(e)}
