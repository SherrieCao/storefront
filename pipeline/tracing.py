"""Instrumentation: run directories, traced_tool, log writers, reasoning capture.

Every run is a self-contained, inspectable, replayable directory.
Every LLM and tool call is traced with full I/O and cost.
Agent reasoning is captured at three levels:
  - REASONING.md  : human-readable narrative of how the run was decided
  - structured     : `reasoning`/`why` fields inside each stage's JSON
  - trace.jsonl    : raw thinking blocks + full prompt/response (forensics)
When something goes wrong, the answer is one directory away.
"""
from __future__ import annotations

import functools
import json
import time
import traceback as tb
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Callable

from . import config


@dataclass
class Run:
    run_id:   str
    business: str
    dir:      Path
    costs:    dict[str, float] = field(default_factory=dict)
    models:   dict[str, str]   = field(default_factory=dict)
    _t0:      float            = field(default_factory=time.time)

    @property
    def trace_path(self)     -> Path: return self.dir / "trace.jsonl"
    @property
    def log_path(self)       -> Path: return self.dir / "run.log"
    @property
    def cost_path(self)      -> Path: return self.dir / "cost.json"
    @property
    def cost_md_path(self)   -> Path: return self.dir / "COST.md"
    @property
    def meta_path(self)      -> Path: return self.dir / "meta.json"
    @property
    def reasoning_path(self) -> Path: return self.dir / "REASONING.md"
    @property
    def prompt_path(self)    -> Path: return self.dir / "PROMPT.md"
    @property
    def lineage_path(self)   -> Path: return self.dir / "lineage.json"
    @property
    def flagged_shots_path(self) -> Path: return self.dir / "flagged_shots.json"

    def trace(self, event: dict[str, Any]) -> None:
        with self.trace_path.open("a") as f:
            f.write(json.dumps({"ts": _now(), **event}, default=str) + "\n")

    def log(self, line: str) -> None:
        stamped = f"[{_elapsed(self._t0)}] {line}"
        print(stamped, flush=True)
        with self.log_path.open("a") as f:
            f.write(stamped + "\n")

    def reason(self, stage: str, thinking: str | None, rationale: str) -> None:
        """Append a stage's reasoning to REASONING.md (human-readable narrative)."""
        with self.reasoning_path.open("a") as f:
            f.write(f"\n## {stage}\n\n")
            if thinking:
                f.write(f"**Thinking (model trace):**\n\n> "
                        + thinking.replace("\n", "\n> ") + "\n\n")
            f.write(f"**Rationale (stated):**\n\n{rationale}\n")
        if thinking:
            self.trace({"step": stage, "type": "thinking", "thinking": thinking})

    def add_cost(self, step: str, amount: float) -> None:
        self.costs[step] = round(self.costs.get(step, 0.0) + amount, 6)

    def cost_total(self) -> float:
        """Running total across all stages. The cost ceiling (budget.py) checks this before every
        paid call."""
        return round(sum(self.costs.values()), 6)

    def note_model(self, step: str, model_id: str) -> None:
        self.models[step] = model_id

    def write_flagged_shots(self, flagged: list[dict[str, Any]]) -> None:
        """Shots that failed MAX_SHOT_RETRIES — surfaced to the operator, never silently accepted."""
        self.flagged_shots_path.write_text(json.dumps(flagged, indent=2, default=str))

    @property
    def creative_flags_path(self) -> Path: return self.dir / "creative_flags.json"

    def write_creative_flags(self, flags: list[dict[str, Any]]) -> None:
        """Creative stages (concept/director/hook) whose reviewer wasn't satisfied after retries —
        accepted-best but surfaced to the operator (parallel to flagged_shots)."""
        self.creative_flags_path.write_text(json.dumps(flags, indent=2, default=str))

    def write_cost_md(self, status: str = "in progress") -> None:
        """Human-readable per-stage cost vs the $5 ceiling, so a $4.80 run is visible mid-flight."""
        total = self.cost_total()
        ceiling = config.COST_CEILING_USD
        lines = [f"# Cost — Run {self.run_id} ({self.business})", "",
                 f"**Status:** {status}  ·  **Ceiling:** ${ceiling:.2f}", "",
                 "| Stage | Cost |", "|---|---|"]
        for step, amt in self.costs.items():
            lines.append(f"| {step} | ${amt:.4f} |")
        bar = "OVER CEILING" if total > ceiling else (
            "near ceiling" if total >= ceiling * config.COST_WARN_FRACTION else "ok")
        lines += ["|---|---|", f"| **total** | **${total:.4f}** |", "",
                  f"_{bar} (${total:.4f} / ${ceiling:.2f})_", ""]
        self.cost_md_path.write_text("\n".join(lines))

    def _write_meta(self, status: str, extra: dict[str, Any] | None = None) -> float:
        total = self.cost_total()
        self.cost_path.write_text(json.dumps({**self.costs, "total": total}, indent=2))
        self.write_cost_md(status)
        self.meta_path.write_text(json.dumps({
            "run_id": self.run_id, "business": self.business,
            "models": self.models, "scaffold_versions": config.SCAFFOLD_VERSIONS,
            "total_cost": total, "status": status, "finished_at": _now(),
            **(extra or {}),
        }, indent=2))
        return total

    def finalize(self) -> None:
        total = self._write_meta("ok")
        self.log(f"Done. Total cost: ${total:.4f}")

    def fail(self, step: str, exc: BaseException, cls: dict[str, Any]) -> None:
        """Record a clean failure: trace entry + cost.json + meta.json(status=failed), so the
        run dir still explains what broke and what was already spent."""
        self.trace({"step": step, "type": "error", "error": str(exc), "classification": cls})
        total = self._write_meta("failed", {"failed_step": step, "error": cls})
        self.log(f"FAILED at '{step}': {cls.get('message', '')} (spent so far: ${total:.4f})")

    def pause(self, after_step: str) -> None:
        """Record a clean pause for operator approval: meta.json(status=awaiting_approval). The run
        dir holds the creative direction and is resumable from the next step once approved."""
        total = self._write_meta("awaiting_approval", {"paused_after": after_step})
        self.log(f"AWAITING APPROVAL after '{after_step}' (spent so far: ${total:.4f})")


# Run-directory contract (CLAUDE.md). Numbered artifacts are written by the stages themselves.
SUBDIRS = ["input_snapshot", "03_enhanced", "04_keyframes", "05_shots", "06_voice",
           "08_assembly", "09_output", "09_output/frames"]

def setup_run(run_id: str | None, business: str) -> Run:
    config.RUNS_DIR.mkdir(exist_ok=True)
    if run_id is None:
        run_id = _next_id()
    d = config.RUNS_DIR / run_id
    d.mkdir(parents=True, exist_ok=True)
    for sub in SUBDIRS:
        (d / sub).mkdir(parents=True, exist_ok=True)
    run = Run(run_id=run_id, business=business, dir=d)
    if run.reasoning_path.exists():
        with run.reasoning_path.open("a") as f:
            f.write(f"\n## — REPLAY ({_now()}) —\n")
    else:
        run.reasoning_path.write_text(
            f"# Reasoning — Run {run_id} ({business})\n\n"
            f"How this run was decided, stage by stage. "
            f"NOTE: a model's stated reasoning is its account, not guaranteed ground "
            f"truth — the output is the real verdict.\n"
        )
    run.log(f"Run {run_id} started  business={business}")
    return run

def _next_id() -> str:
    existing = [int(p.name) for p in config.RUNS_DIR.iterdir()
                if p.is_dir() and p.name.isdigit()]
    return f"{(max(existing) + 1) if existing else 1:04d}"


_ACTIVE_RUN: Run | None = None
def set_active_run(run: Run | None) -> None:
    global _ACTIVE_RUN; _ACTIVE_RUN = run
def get_active_run() -> Run | None:
    return _ACTIVE_RUN


def traced_tool(fn: Callable) -> Callable:
    @functools.wraps(fn)
    def wrapper(*args, **kwargs):
        run = _ACTIVE_RUN; t0 = time.time()
        if run:
            run.trace({"step": "tool", "type": "call",
                       "tool": fn.__name__, "args": _trim(args), "kwargs": _trim(kwargs)})
        try:
            result = fn(*args, **kwargs)
            if run:
                run.trace({"step": "tool", "type": "result",
                           "tool": fn.__name__, "output": _trim(result), "ms": _ms(t0)})
            return result
        except Exception as e:
            if run:
                run.trace({"step": "tool", "type": "error", "tool": fn.__name__,
                           "error": str(e), "tb": tb.format_exc(), "ms": _ms(t0)})
            raise
    return wrapper


def log_llm_call(run: Run, step: str, model_id: str, prompt: Any,
                 raw_response: str, in_tok: int, out_tok: int, ms: int,
                 thinking: str | None = None) -> float:
    cost = _llm_cost(model_id, in_tok, out_tok)
    run.note_model(step, model_id); run.add_cost(step, cost)
    run.trace({
        "step": step, "type": "llm_call", "model": model_id,
        "in_tok": in_tok, "out_tok": out_tok, "cost": cost, "ms": ms,
        "prompt": prompt, "raw_response": raw_response,
        "thinking": thinking,
    })
    return cost

def _llm_cost(model: str, i: int, o: int) -> float:
    r = config.COST_PER_MTOK.get(model)
    return round((i * r[0] + o * r[1]) / 1_000_000, 6) if r else 0.0


def _now() -> str: return datetime.now(timezone.utc).isoformat()
def _elapsed(t0): s = int(time.time()-t0); return f"{s//60:02d}:{s%60:02d}"
def _ms(t0): return int((time.time()-t0)*1000)
def _trim(obj, limit=2000):
    try: s = json.dumps(obj, default=str)
    except TypeError: s = str(obj)
    return s[:limit] + f"...<+{len(s)-limit}>" if len(s) > limit else obj
