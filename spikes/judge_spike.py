"""Spike: verify a cheap Gemini Flash-tier model accepts VIDEO input and can judge a clip.

Confirms: (1) which flash model ids exist, (2) video upload via Files API works,
(3) the model returns a structured judgment, (4) token usage -> cost.
"""
import json, os, sys, time
from dotenv import load_dotenv

load_dotenv()
from google import genai
from google.genai import types

KEY = os.environ["GEMINI_API_KEY"]
client = genai.Client(api_key=KEY)

CANDIDATES = ["gemini-3-flash-preview", "gemini-3.1-flash-preview",
              "gemini-3.1-flash-lite-preview", "gemini-flash-latest", "gemini-3.5-flash"]

# 1) Which flash models are actually available?
print("=== available flash-tier models ===")
available = []
try:
    for m in client.models.list():
        name = m.name.split("/")[-1]
        if "flash" in name.lower():
            available.append(name)
            print(" ", name)
except Exception as e:
    print("  list() failed:", repr(e))

# pick the first candidate that's available, else first candidate
model = next((c for c in CANDIDATES if c in available), CANDIDATES[0])
print("\nUsing judge model:", model)

# 2) upload a real test clip
video = sys.argv[1]
print("Uploading:", video)
f = client.files.upload(file=video)
for _ in range(30):
    f = client.files.get(name=f.name)
    if f.state.name == "ACTIVE":
        break
    time.sleep(2)
print("file state:", f.state.name)

# 3) judge call with a structured prompt
JUDGE_PROMPT = (
    "You are a per-shot quality judge for AI-generated ad clips. Inspect this video clip.\n"
    "Return ONLY JSON: {\"pass\": bool, \"score\": 0..1, \"reasons\": [..]}\n"
    "Check: obvious artifacts (hands/faces/objects), temporal coherence, overall usability."
)
t0 = time.time()
resp = client.models.generate_content(
    model=model,
    contents=[f, JUDGE_PROMPT],
)
ms = int((time.time() - t0) * 1000)
print("\n=== response ===")
print(resp.text)

um = resp.usage_metadata
in_tok = getattr(um, "prompt_token_count", 0) or 0
out_tok = getattr(um, "candidates_token_count", 0) or 0
# gemini-3-flash-preview pricing: $0.50 / $3.00 per Mtok
cost = in_tok / 1e6 * 0.50 + out_tok / 1e6 * 3.00
print(f"\n=== usage === in={in_tok} out={out_tok} latency_ms={ms} est_cost=${cost:.5f}")
print(json.dumps({"model": model, "in_tok": in_tok, "out_tok": out_tok,
                  "latency_ms": ms, "est_cost_usd": round(cost, 5),
                  "available_flash": available}, indent=2))
