"""Business research — pull REAL reviews from Google Maps (primary) + Yelp (secondary) and distill
ONE concrete, true detail to anchor the concept on. The detail is distilled ONLY from fetched review
text, so it can't be fabricated; if the business can't be matched, returns {"found": false} and the
Concept pass ideates without it.

Wired as a registered agent tool (research_business) and called by the Concept stage. The pipeline runs
fine without the API keys — research just no-ops to found:false. Isolate all API surfaces here so a
provider/endpoint swap is one file.

NOT for: fabricating reviews/details (distill only from fetched text), or creative decisions.
"""
from __future__ import annotations
import json, time
from typing import Any
from . import config
from .agent.registry import tool

_DISTILL_SYSTEM = """You are given REAL customer reviews for ONE specific local business. Distill 1-2
CONCRETE, specific, recurring details an ad could anchor on — a named feature, a repeated praise, a
genuine differentiator, a quirk. Output JSON only:
{"found": bool, "detail": "<one specific true thing>", "evidence": ["<short verbatim quote>", ...],
 "why_it_fights_generic": "<one line>"}
Rules: use ONLY the review text provided; quote evidence VERBATIM (keep quotes short). If the reviews
are sparse, generic, or don't support a specific detail, return {"found": false}. NEVER invent a detail
or a quote."""


def _google_reviews(query: str) -> dict[str, Any]:
    """Google Places (New): Text Search -> Place Details (reviews). {} on no key / no match / error."""
    if not config.GOOGLE_PLACES_API_KEY:
        return {}
    try:
        import requests
        key = config.GOOGLE_PLACES_API_KEY
        s = requests.post(
            "https://places.googleapis.com/v1/places:searchText",
            headers={"Content-Type": "application/json", "X-Goog-Api-Key": key,
                     "X-Goog-FieldMask": "places.id,places.displayName,places.formattedAddress,places.rating"},
            json={"textQuery": query}, timeout=15)
        places = s.json().get("places", []) if s.ok else []
        if not places:
            return {}
        p = places[0]
        d = requests.get(
            f"https://places.googleapis.com/v1/places/{p.get('id')}",
            headers={"X-Goog-Api-Key": key,
                     "X-Goog-FieldMask": "displayName,formattedAddress,rating,reviews"},
            timeout=15)
        dj = d.json() if d.ok else {}
        reviews = [{"text": (r.get("text") or {}).get("text", ""), "rating": r.get("rating"),
                    "source": "google"}
                   for r in dj.get("reviews", []) if (r.get("text") or {}).get("text")]
        return {"reviews": reviews,
                "name": (dj.get("displayName") or p.get("displayName") or {}).get("text", ""),
                "address": dj.get("formattedAddress") or p.get("formattedAddress", ""),
                "rating": dj.get("rating") or p.get("rating")}
    except Exception:
        return {}


def _yelp_reviews(business: str, location: str) -> dict[str, Any]:
    """Yelp Fusion: Business Search -> reviews (3 excerpts). {} on no key/location / no match / error."""
    if not config.YELP_API_KEY or not location:
        return {}
    try:
        import requests
        h = {"Authorization": f"Bearer {config.YELP_API_KEY}"}
        s = requests.get("https://api.yelp.com/v3/businesses/search", headers=h,
                         params={"term": business, "location": location, "limit": 1}, timeout=15)
        biz = s.json().get("businesses", []) if s.ok else []
        if not biz:
            return {}
        b = biz[0]
        r = requests.get(f"https://api.yelp.com/v3/businesses/{b.get('id')}/reviews", headers=h,
                         params={"limit": 3, "sort_by": "yelp_sort"}, timeout=15)
        rj = r.json() if r.ok else {}
        reviews = [{"text": rv.get("text", ""), "rating": rv.get("rating"), "source": "yelp"}
                   for rv in rj.get("reviews", []) if rv.get("text")]
        addr = ", ".join((b.get("location", {}) or {}).get("display_address", []) or [])
        return {"reviews": reviews, "name": b.get("name", ""), "address": addr, "rating": b.get("rating")}
    except Exception:
        return {}


@tool("research_business",
      "Look up the REAL business on Google Maps + Yelp and distill ONE concrete, true detail from actual "
      "customer reviews to anchor the concept (fights generic). Returns {found, detail, evidence, source, "
      "matched_name, matched_address, rating}; found:false if it can't be reliably matched.",
      {"type": "object",
       "properties": {"business": {"type": "string", "description": "the business name"},
                      "brief":    {"type": "string", "description": "operator brief (for the location)"}},
       "required": ["business"]},
      not_for="fabricating reviews or details — only distill from fetched review text")
def research_business(business: str = "", brief: str = "") -> dict[str, Any]:
    # Google first; reuse its matched address as the Yelp location (more reliable than parsing the brief).
    g = _google_reviews(f"{business} {brief}".strip()[:300])
    location = g.get("address") or brief
    y = _yelp_reviews(business, location[:120]) if location else {}

    reviews = (g.get("reviews") or []) + (y.get("reviews") or [])
    matched_name = g.get("name") or y.get("name") or business
    matched_address = g.get("address") or y.get("address") or ""
    sources = [name for name, d in (("google", g), ("yelp", y)) if d.get("reviews")]
    rating = g.get("rating") or y.get("rating")

    if not reviews:
        return {"found": False, "matched_name": matched_name, "matched_address": matched_address,
                "_note": "no reviews found on Google/Yelp"}
    if not config.GEMINI_API_KEY:
        return {"found": False, "_stub": True, "matched_name": matched_name}

    try:
        from google import genai
        from google.genai import types
        from .tracing import get_active_run, log_llm_call
        from .llm import parse_json
        model = config.MODEL_ROUTER.get("business_research", config.MODEL_ROUTER["creative_director"])
        client = genai.Client(api_key=config.GEMINI_API_KEY)
        payload = json.dumps({"business": matched_name, "reviews": [r["text"] for r in reviews]}, indent=2)
        t0 = time.time()
        resp = client.models.generate_content(
            model=model, contents=[payload],
            config=types.GenerateContentConfig(system_instruction=_DISTILL_SYSTEM,
                                               response_mime_type="application/json"))
        spec = parse_json(resp.text)
        run = get_active_run()
        if run is not None:
            u = resp.usage_metadata
            log_llm_call(run, "business_research", model, "[research_business]", resp.text or "",
                         (u.prompt_token_count or 0), (u.candidates_token_count or 0),
                         int((time.time() - t0) * 1000), None)
    except Exception as e:
        return {"found": False, "matched_name": matched_name, "_error": str(e)}

    if not isinstance(spec, dict):
        return {"found": False, "matched_name": matched_name}
    spec.setdefault("found", bool(spec.get("detail")))
    spec.update({"matched_name": matched_name, "matched_address": matched_address,
                 "rating": rating, "source": sources})
    return spec
