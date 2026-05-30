"""Stage 0.5: Concept Pass (Gemini, multimodal — SEES the assets).

Ideation BEFORE the Director: diverge (5 concepts), name + reject the category clichés, hard-gate
on asset FEASIBILITY, and self-select the single boldest feasible concept. The Director then
EXECUTES the chosen concept instead of inventing from scratch — so it can't fall back to the cliché
that was already named and rejected here.

NOT for: choosing format/shots/script (that's the Director), or generation.
"""
from __future__ import annotations
import json, time
from typing import Any
from . import config
from .tracing import Run, log_llm_call, set_active_run
from .llm import call_gemini_multimodal, parse_json
from .translator import _usable_assets       # same @-token assignment the Director/Translator use
from .director import _asset_summary          # identical asset rows (ref + file + quality)
from .research import research_business       # real Google/Yelp reviews -> a true anchor detail
from . import reviewers                       # 4-lens creative critic (self-correct loop)

CONCEPT_FILE = "01_concept.json"
RESEARCH_FILE = "01_research.json"


def run_concept(run: Run, inventory: dict[str, Any], *, use_cache: bool = False,
                feedback: str | None = None) -> dict[str, Any]:
    cache = run.dir / CONCEPT_FILE
    if use_cache and cache.exists():
        run.log("Concept: loaded from cache"); return json.loads(cache.read_text())

    run.log("Concept: diverging + killing clichés + self-selecting the boldest feasible idea")
    scaffold = _load_scaffold(inventory)
    model = config.MODEL_ROUTER.get("concept", config.MODEL_ROUTER["creative_director"])

    research = _business_research(run, inventory)   # real reviews -> a true detail to anchor on (cached)

    # Same multimodal asset gathering as the Director (the concept MUST see the real assets).
    tokened = _usable_assets(inventory)
    image_paths = [p for tok, p in tokened if tok.startswith("@Image")]
    video_paths = [p for tok, p in tokened if tok.startswith("@Video")]
    if inventory.get("logo_path"): image_paths.insert(0, inventory["logo_path"])

    base_payload = {
        "business": inventory["business"], "brief": inventory["brief"],
        "has_before_after": inventory["has_before_after"],
        "has_logo": inventory["has_logo"], "palette": inventory["palette"],
        "business_research": research,        # {found, detail, evidence, source, ...} or {found:false}
        "asset_summary": _asset_summary(inventory),
    }
    ctx = {"business": inventory["business"], "brief": inventory["brief"]}

    def _produce(fb: str | None) -> tuple[dict[str, Any], str | None]:
        payload = dict(base_payload)
        if fb:
            payload["prior_attempt_failed_review"] = {"fix_these": fb}  # baked into the regen
        user_text = json.dumps(payload, indent=2)
        if not config.GEMINI_API_KEY:                   # own stub — do NOT reuse the director-stub
            return parse_json(_stub_concept(inventory)), "STUB thinking: no GEMINI_API_KEY set"
        t0 = time.time()
        raw, thinking, in_tok, out_tok = call_gemini_multimodal(
            model, scaffold, user_text, image_paths, video_paths)
        log_llm_call(run, "concept", model, scaffold[:400] + "...", raw, in_tok, out_tok,
                     int((time.time() - t0) * 1000), thinking)
        return parse_json(raw), thinking

    # self-correcting critic loop: produce -> review (4 lenses) -> regenerate with feedback
    fb, concept, thinking, verdict, attempts = feedback, {}, None, {}, []
    for attempt in range(1, config.MAX_CREATIVE_RETRIES + 1):
        concept, thinking = _produce(fb)
        verdict = reviewers.review(run, "concept", concept, ctx)
        attempts.append({"attempt": attempt, "passed": verdict["pass"], "scores": verdict["scores"],
                         "failed_lenses": verdict["failed_lenses"], "improvement": verdict["improvement"]})
        if verdict["pass"]:
            break
        fb = verdict["improvement"]
        run.log(f"Concept: review attempt {attempt} FAIL ({verdict['failed_lenses']}) — regenerating")

    concept["_review"] = {"passed": verdict.get("pass", True), "scores": verdict.get("scores", {}),
                          "failed_lenses": verdict.get("failed_lenses", []),
                          "improvement": verdict.get("improvement", ""), "attempts": attempts}
    cache.write_text(json.dumps(concept, indent=2))
    _render_md(run, concept)

    chosen = concept.get("chosen", {}) or {}
    rationale = (f"**Chosen:** {chosen.get('name','')} — {chosen.get('concept','')}\n\n"
                 f"**Why bold:** {chosen.get('why_bold','')}\n\n"
                 f"**Rejected clichés:**\n"
                 + "\n".join(f"- {r}" for r in concept.get("rejected", [])))
    if research.get("found"):
        rationale = (f"**Real detail (from {'/'.join(research.get('source', [])) or 'reviews'}):** "
                     f"{research.get('detail','')}\n\n") + rationale
    run.reason("Concept", thinking, rationale)
    run.log(f"Concept: chosen='{str(chosen.get('name',''))[:60]}' "
            f"(rejected {len(concept.get('rejected', []))} clichés)")
    return concept


def _business_research(run: Run, inventory: dict[str, Any]) -> dict[str, Any]:
    """Fetch + distill a true detail from real Google/Yelp reviews (cached in 01_research.json so a
    Director-only re-iteration doesn't re-pay). Always returns a dict; found:false when nothing reliable."""
    cache = run.dir / RESEARCH_FILE
    if cache.exists():
        return json.loads(cache.read_text())
    set_active_run(run)                              # so research_business's distill call is logged/costed
    res = research_business(business=inventory.get("business", ""), brief=inventory.get("brief", ""))
    set_active_run(None)
    cache.write_text(json.dumps(res, indent=2))
    if res.get("found"):
        run.log(f"Research: found via {'/'.join(res.get('source', [])) or '?'} "
                f"({res.get('matched_name','')}) → {str(res.get('detail',''))[:70]}")
    else:
        run.log(f"Research: no reliable match ({res.get('matched_name') or 'business not found'})")
    return res


def _render_md(run: Run, concept: dict[str, Any]) -> None:
    chosen = concept.get("chosen", {}) or {}
    md = [f"# Concept — Run {run.run_id} ({run.business})\n", "## Rejected clichés"]
    md += [f"- {r}" for r in concept.get("rejected", [])] or ["- (none stated)"]
    md += [f"\n## Chosen: {chosen.get('name', '(unnamed)')}\n",
           str(chosen.get("concept", "")),
           f"\n**Why bold:** {chosen.get('why_bold', '')}",
           f"**Assets used:** {', '.join(chosen.get('assets_used', [])) or '—'}",
           f"**Must generate:** {', '.join(chosen.get('must_generate', [])) or '—'}",
           f"**Load-bearing info:** {chosen.get('load_bearing_info', '')}\n",
           "## Considered"]
    for c in concept.get("considered", []):
        md.append(f"- {c.get('idea','')} — risky: {c.get('risky_because','')} "
                  f"[feasible={c.get('feasible')}]")
    (run.dir / "01_concept.md").write_text("\n".join(md) + "\n")


def _load_scaffold(inv: dict) -> str:
    # Ground ideation in the multi-vertical playbook + hook data (vertical-agnostic; model picks the row).
    from .refs import reference_block
    t = (config.SCAFFOLDS_DIR / "concept.md").read_text() \
        + reference_block(["smb_verticals.md", "ad_formats.md", "hooks.md", "script_craft.md"])
    return (t.replace("{{business}}", str(inv.get("business", "")))
             .replace("{{brief}}", str(inv.get("brief", "")))
             .replace("{{has_before_after}}", str(inv.get("has_before_after", False)))
             .replace("{{has_logo}}", str(inv.get("has_logo", False)))
             .replace("{{palette}}", ", ".join(inv.get("palette", [])) or "not detected"))


def _stub_concept(inv: dict[str, Any] | None = None) -> str:
    """Vertical-NEUTRAL canned concept so offline/no-key runs complete for ANY business."""
    biz = (inv or {}).get("business", "this local business")
    return json.dumps({
        "rejected": ["STUB: the generic category-montage cliché",
                     "STUB: 'cute close-up + warm VO' — could be any business in the category"],
        "considered": [{"idea": "STUB idea", "risky_because": "...", "assets_used": ["@Image1"],
                        "gaps": [], "feasible": True}],
        "chosen": {
            "name": "STUB concept",
            "concept": f"STUB: one authentic, specific idea built around {biz}'s real assets and brief.",
            "why_bold": "STUB: specific and real, not the category cliché.",
            "assets_used": ["@Image1"], "must_generate": [],
            "load_bearing_info": "price/hours/location/CTA still carried in the script.",
        },
        "_stub": True,
    })
