"""Central config: model routing, paths, constants. One-line model swaps.

Multi-gen architecture. All external model ids below were VERIFIED LIVE in the Phase-0 spikes —
see docs/{judge,nano_banana,seedance,voice,editor}_findings.md. Do not change them on training
recall; re-verify against live docs/spikes.
"""
from __future__ import annotations
import os
from pathlib import Path
from dotenv import load_dotenv

REPO_ROOT     = Path(__file__).resolve().parent.parent
load_dotenv(REPO_ROOT / ".env")        # secrets from the repo-root .env (gitignored)

RUNS_DIR        = REPO_ROOT / "runs"
INPUTS_DIR      = REPO_ROOT / "inputs"
SCAFFOLDS_DIR   = REPO_ROOT / "scaffolds"
EDITOR_RENDER_DIR = REPO_ROOT / "editor_render"

# ---------------------------------------------------------------------------
# Model router — change a model by editing one line.
# ---------------------------------------------------------------------------
MODEL_ROUTER = {
    # Concept + Director: multimodal, SEE the actual photos + videos (Gemini Pro). Never a Gemini
    # video-GENERATION model for the brain.
    "concept":           "gemini-3.1-pro-preview",
    "creative_director": "gemini-3.1-pro-preview",
    "hook_designer":     "gemini-3.1-pro-preview",
    "business_research": "gemini-3.1-pro-preview",
    # Per-shot prompt composition (the refactored translator) — strong instruction-following.
    "prompt_translator": "claude-sonnet-4-6",
    # Editor Agent: emits the edit-plan JSON. Claude Sonnet (structured-JSON fidelity); validate at
    # build, swap to Gemini if edit-plan quality warrants.
    "editor_agent":      "claude-sonnet-4-6",
    # Per-shot judge: cheap Gemini Flash that accepts VIDEO input (VERIFIED, docs/judge_findings.md).
    "shot_judge":        "gemini-3-flash-preview",
    # Review (mechanical) on the final assembled video.
    "review_judge":      "gemini-3.1-pro-preview",
    # Per-shot video generation: Seedance 2.0 image-to-video, single-shot, audio OFF (VERIFIED).
    "seedance_image":      "bytedance/seedance-2.0/image-to-video",
    "seedance_image_fast": "bytedance/seedance-2.0/fast/image-to-video",
    "seedance_text":       "bytedance/seedance-2.0/text-to-video",       # fallback when no keyframe
    "seedance_text_fast":  "bytedance/seedance-2.0/fast/text-to-video",
    # Keyframes: Nano Banana 2 on fal (VERIFIED, docs/nano_banana_findings.md).
    "keyframe":          "fal-ai/nano-banana-2",        # generate mode (text-to-image)
    "keyframe_edit":     "fal-ai/nano-banana-2/edit",   # generate_from_real (real-photo conditioning)
    # Voice: MiniMax TTS on fal (VERIFIED, docs/voice_findings.md).
    "tts":               "fal-ai/minimax/speech-02-hd",
    # Enhancement (targeted salvage of weak real assets).
    "enhance_upscale":   "fal-ai/clarity-upscaler",
}

CAPTURE_THINKING = True

# Token budgets per agentic LLM call.
TOKEN_BUDGETS = {"director": 18_000, "shot_prompt": 4_000, "editor": 10_000, "review": 8_000}

# ---------------------------------------------------------------------------
# Cost tables
# ---------------------------------------------------------------------------
COST_PER_MTOK: dict[str, tuple[float, float]] = {
    "gemini-3.1-pro-preview": (2.0, 12.0),
    "gemini-3.5-pro":         (2.0, 12.0),
    "gemini-3-flash-preview": (0.50, 3.0),   # judge — VERIFIED pricing (docs/judge_findings.md)
    "claude-sonnet-4-6":      (3.0, 15.0),
    "claude-haiku-4-5":       (1.0,  5.0),
}
# Seedance 2.0 per-second rates ($/s @ 720p). image = image/text-ref gens. 480p treated as 720p
# here (fal hasn't published a separate 480p rate) → 480p cost is a slight over-estimate.
SEEDANCE_RATE = {
    "standard": {"image": 0.3024},
    "fast":     {"image": 0.2419},
}
NANO_BANANA_COST_PER_IMAGE = 0.08    # @1K (docs/nano_banana_findings.md); 2K=1.5x, 4K=2x
TTS_COST_PER_1K_CHARS      = 0.10    # MiniMax speech-02-hd (docs/voice_findings.md)
FAL_ENHANCE_COST           = 0.03    # per remediated photo (clarity-upscaler)
REMOTION_RENDER_COST       = 0.0     # local CLI render — no API cost (compute only)

# ---------------------------------------------------------------------------
# Output / generation spec  (mixed segments, variable length — SPEC_followup_mixed_segments.md)
# ---------------------------------------------------------------------------
ASPECT_RATIO      = "9:16"
MIN_DURATION_S    = 15               # Director picks total_duration_s within [MIN, MAX]
MAX_DURATION_S    = 30
RESOLUTION        = "480p"           # cheap-draft default; run.py --final bumps to 720p
SEEDANCE_TIER     = "fast"           # "fast" (cheap draft) | "standard" (--final keeper)
SEEDANCE_MIN_SHOT_S = 4              # VERIFIED: Seedance image-to-video min duration ~4s
FPS               = 30

# Asset enumeration caps (how many real assets to surface to the Director as @-tokens).
MAX_REF_IMAGES    = 9                # recoverable photos offered as @Image1..N (keyframe/moodboard inputs)
MAX_REF_VIDEOS    = 3                # usable videos offered as @Video1..N (real_clip sources)
MAX_VIDEO_CLIP_S  = 5.0              # max real_clip trim length (Remotion trims in the editor)

# ---------------------------------------------------------------------------
# Multi-gen shot policy + cost ceiling (D5, D6)
# ---------------------------------------------------------------------------
MAX_SHOT_RETRIES  = 3                # per seedance_shot: generate + judge, retry up to 3, then flag
COST_CEILING_USD  = 5.00             # SILENT safety net (D6/D19): Director never sees cost
COST_WARN_FRACTION = 0.8             # log a warning once cost crosses this fraction of the ceiling
MAX_SHOT_CONCURRENCY = 4             # Seedance is ~2min/gen — fan shots out concurrently

# ---------------------------------------------------------------------------
# Editor render service (Remotion — VERIFIED 4.0.468, docs/editor_findings.md)
# ---------------------------------------------------------------------------
REMOTION_COMPOSITION_ID = "Ad"
# v0 = local Remotion CLI (`npx remotion render`). Upgrade path: @remotion/lambda for parallel
# cloud renders, behind the same editor.py interface.

# ---------------------------------------------------------------------------
# Review / retry policy
# ---------------------------------------------------------------------------
MAX_REGEN_RETRIES = 2

# ---------------------------------------------------------------------------
# Scaffold versions (stamped into meta.json)
# ---------------------------------------------------------------------------
SCAFFOLD_VERSIONS = {
    "concept":           "concept-v0.1",
    "creative_director": "director-v1.0",   # mixed-segment output
    "prompt_translator": "shot-prompt-v1.0", # per-shot composer
    "shot_agent":        "shot-agent-v0.1",
    "editor":            "editor-v0.1",
}

# ---------------------------------------------------------------------------
# Secrets — from .env only (loaded above)
# ---------------------------------------------------------------------------
ANTHROPIC_API_KEY = os.environ.get("ANTHROPIC_API_KEY", "")
GEMINI_API_KEY    = os.environ.get("GEMINI_API_KEY", "")
FAL_KEY           = os.environ.get("FAL_KEY", "")
GOOGLE_PLACES_API_KEY = os.environ.get("GOOGLE_PLACES_API_KEY", "")
YELP_API_KEY          = os.environ.get("YELP_API_KEY", "")
