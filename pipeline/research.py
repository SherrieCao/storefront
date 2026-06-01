"""Business research — pull REAL reviews from Google Maps (primary) + Yelp (secondary) and distill
RANKED concrete, true anchor details (anchor_candidates[]) the Concept can pick a fresh one from. Details
are distilled ONLY from fetched review text + Google's AI reviewSummary, so they can't be fabricated; if
the business can't be matched, returns {"found": false} and the Concept pass ideates without it.

Reviews are cached per-business in inputs/<business>/reviews_cache.json (TTL config.REVIEW_CACHE_TTL_DAYS)
so repeat runs don't re-pay the Google fetch; the owner can also paste their own reviews into the cache's
operator_supplied[] (never expire).

Wired as a registered agent tool (research_business) and called by the Concept stage. The pipeline runs
fine without the API keys — research just no-ops to found:false. Isolate all API surfaces here so a
provider/endpoint swap is one file.

NOT for: fabricating reviews/details (distill only from fetched text), or creative decisions.
"""
from __future__ import annotations
import json, time
from datetime import datetime, timezone
from pathlib import Path
from typing import Any
from . import config
from .agent.registry import tool

_DISTILL_SYSTEM = """You are given REAL customer reviews (and possibly an AI-written review summary) for
ONE specific local business. Surface 3+ CONCRETE, specific, TRUE anchor details an ad could build on — a
named feature, a repeated praise, a genuine differentiator, a quirk — RANKED most-specific first (a
named/verifiable detail beats a vague vibe). Output JSON only:
{"found": bool,
 "anchor_candidates": [{"detail": "<one specific true thing>", "evidence": "<short verbatim quote>",
                        "why_specific": "<one line: why this fights generic>"}, ...],
 "review_summary_themes": ["<short theme>", ...]}
Rules: use ONLY the provided review text/summary; quote evidence VERBATIM (keep quotes short). Give as
many distinct, specific candidates as the reviews genuinely support (aim for 3+). If the reviews are
sparse or support nothing specific, return {"found": false, "anchor_candidates": []}. NEVER invent a
detail or a quote."""


def _map_new_reviews(dj: dict, sort_source: str) -> list[dict]:
    return [{"author": (r.get("authorAttribution") or {}).get("displayName", ""),
             "rating": r.get("rating"), "text": (r.get("text") or {}).get("text", ""),
             "time": r.get("publishTime", ""), "source": "google", "sort_source": sort_source}
            for r in dj.get("reviews", []) if (r.get("text") or {}).get("text")]


def _dedupe_reviews(reviews: list[dict]) -> list[dict]:
    seen, out = set(), []
    for r in reviews:
        k = ((r.get("author") or "").strip().lower(), (r.get("text") or "")[:80].strip().lower())
        if k in seen:
            continue
        seen.add(k); out.append(r)
    return out


def _google_newest_legacy(place_id: str, key: str) -> list[dict]:
    """Best-effort: the Places API (New) details endpoint returns ~5 most-relevant reviews with NO sort
    control, so to widen coverage we try the LEGACY details endpoint with reviews_sort=newest. If the key
    doesn't have the legacy API enabled it just REQUEST_DENIEDs -> we silently return [] (no regression)."""
    try:
        import requests
        r = requests.get("https://maps.googleapis.com/maps/api/place/details/json",
                         params={"place_id": place_id, "reviews_sort": "newest",
                                 "fields": "review", "key": key}, timeout=15)
        rj = r.json() if r.ok else {}
        return [{"author": rv.get("author_name", ""), "rating": rv.get("rating"),
                 "text": rv.get("text", ""), "time": rv.get("time", ""),
                 "source": "google", "sort_source": "newest"}
                for rv in (rj.get("result", {}) or {}).get("reviews", []) if rv.get("text")]
    except Exception:
        return []


def _google_reviews(query: str) -> dict[str, Any]:
    """Google Places (New): Text Search -> Place Details (reviews + AI reviewSummary). Best-effort widens
    to legacy newest-sorted reviews. {} on no key / no match / error."""
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
        place_id = p.get("id")
        d = requests.get(
            f"https://places.googleapis.com/v1/places/{place_id}",
            headers={"X-Goog-Api-Key": key,
                     # reviewSummary = AI synthesis across ALL reviews (themes the 5-review cap misses).
                     "X-Goog-FieldMask": "displayName,formattedAddress,rating,reviews,reviewSummary"},
            timeout=15)
        dj = d.json() if d.ok else {}
        reviews = _map_new_reviews(dj, "most_relevant")
        reviews = _dedupe_reviews(reviews + _google_newest_legacy(place_id, key))   # best-effort widen
        review_summary = ((dj.get("reviewSummary") or {}).get("text") or {}).get("text", "")
        return {"reviews": reviews, "review_summary": review_summary, "place_id": place_id,
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


# --- per-business review cache (inputs/<business>/reviews_cache.json) ------------------------------
# Persists fetched reviews ACROSS runs so we don't re-pay the Google fetch every run; TTL'd because
# reviews change slowly. operator_supplied entries (manually pasted by the owner) never expire.

def _active_run():
    try:
        from .tracing import get_active_run
        return get_active_run()
    except Exception:
        return None


def _log(run, msg: str) -> None:
    if run is not None:
        try:
            run.log(msg)
        except Exception:
            pass


def _slugify(s: str) -> str:
    return "".join(c if c.isalnum() else "_" for c in (s or "").lower()).strip("_") or "business"


def _review_cache_path(slug: str) -> Path:
    return config.INPUTS_DIR / slug / "reviews_cache.json"


def _load_review_cache(slug: str) -> dict[str, Any] | None:
    """Cached payload if present AND the fetched block is younger than the TTL. If stale but the owner
    added operator_supplied reviews, return just those (never expire); otherwise None -> re-fetch."""
    p = _review_cache_path(slug)
    if not slug or not p.exists():
        return None
    try:
        c = json.loads(p.read_text())
    except Exception:
        return None
    age_days = (time.time() - float(c.get("fetched_at_epoch", 0) or 0)) / 86400.0
    if age_days < config.REVIEW_CACHE_TTL_DAYS:
        return c
    if c.get("operator_supplied"):
        return {**c, "reviews": [], "_stale_fetched": True}
    return None


def _save_review_cache(slug: str, g: dict[str, Any]) -> None:
    if not slug or not g.get("reviews"):
        return
    p = _review_cache_path(slug)
    try:
        prior = json.loads(p.read_text()) if p.exists() else {}
    except Exception:
        prior = {}
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(json.dumps({
        "business": slug, "place_id": g.get("place_id"),
        "fetched_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "fetched_at_epoch": time.time(),
        "review_summary": g.get("review_summary", ""),
        "matched_name": g.get("name", ""), "matched_address": g.get("address", ""),
        "rating": g.get("rating"), "reviews": g.get("reviews", []),
        "operator_supplied": prior.get("operator_supplied", []),   # preserved across re-fetches; never expire
    }, indent=2))


@tool("research_business",
      "Look up the REAL business on Google Maps + Yelp and distill RANKED concrete, true anchor details "
      "from actual customer reviews (fights generic). Returns {found, anchor_candidates[], "
      "review_summary_themes, detail (=top candidate, back-compat), source, matched_name, "
      "matched_address, rating}; found:false if it can't be reliably matched.",
      {"type": "object",
       "properties": {"business": {"type": "string", "description": "the business NAME"},
                      "location": {"type": "string", "description": "city/area (disambiguates the lookup)"},
                      "brief":    {"type": "string", "description": "operator brief (unused for the query)"}},
       "required": ["business"]},
      not_for="fabricating reviews or details — only distill from fetched review text")
def research_business(business: str = "", location: str = "", brief: str = "",
                      cache_key: str = "") -> dict[str, Any]:
    # Query Google with the NAME (+ location to disambiguate) — NOT the free-text brief, which is
    # marketing copy a geocoder chokes on. De-underscore in case the name came from a --business slug.
    name = (business or "").replace("_", " ").strip()
    # The review cache lives in the business's INPUT dir, which is the run's slug (e.g. "nail_salon"),
    # not the display name ("Conway Nail Bar"). The Concept caller passes cache_key=run.business; when
    # called bare (e.g. from the Director agent loop) we slugify the name so it's still stable.
    slug = (cache_key or "").strip() or _slugify(name)
    run = _active_run()

    cached = _load_review_cache(slug)
    if cached is not None and (cached.get("reviews") or cached.get("operator_supplied")):
        g = {"reviews": list(cached.get("reviews") or []), "review_summary": cached.get("review_summary", ""),
             "name": cached.get("matched_name") or name, "address": cached.get("matched_address", ""),
             "rating": cached.get("rating"), "place_id": cached.get("place_id")}
        _log(run, f"Reviews: cache hit ({slug}) — {len(g['reviews'])} reviews, skipping Google fetch")
    else:
        query = f"{name} {location}".strip() if location else name
        g = _google_reviews(query) if name else {}
        if g.get("reviews"):
            _save_review_cache(slug, g)
            _log(run, f"Reviews: fetched {len(g['reviews'])} from Google ({g.get('name','')}) + cached")

    op = list((cached or {}).get("operator_supplied") or [])   # owner-pasted reviews always join the pool
    loc = g.get("address") or location or brief
    y = _yelp_reviews(name, loc[:120]) if loc else {}

    reviews = (g.get("reviews") or []) + op + (y.get("reviews") or [])
    review_summary = g.get("review_summary", "")
    matched_name = g.get("name") or y.get("name") or name
    matched_address = g.get("address") or y.get("address") or ""
    sources = [s for s, d in (("google", g), ("yelp", y)) if d.get("reviews")]
    if op:
        sources.append("operator")
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
        payload = json.dumps({"business": matched_name, "reviews": [r["text"] for r in reviews],
                              "review_summary": review_summary}, indent=2)
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
    cands = [c for c in (spec.get("anchor_candidates") or []) if isinstance(c, dict) and c.get("detail")]
    spec["anchor_candidates"] = cands
    if cands:   # back-compat: downstream readers that expect a single `detail`/`evidence` keep working
        spec.setdefault("detail", cands[0].get("detail", ""))
        spec.setdefault("evidence", [c.get("evidence") for c in cands if c.get("evidence")])
        spec.setdefault("why_it_fights_generic", cands[0].get("why_specific", ""))
    spec.setdefault("found", bool(cands))
    spec.update({"matched_name": matched_name, "matched_address": matched_address,
                 "rating": rating, "source": sources, "review_summary": review_summary})
    return spec
