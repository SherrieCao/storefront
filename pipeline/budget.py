"""Cost-ceiling enforcement — the $5 hard ceiling (D6) as a SILENT safety net (D19).

Before every PAID call (Seedance gen, judge, keyframe, TTS), the caller estimates the call's cost
and asks check_ceiling() whether running total + estimate would exceed config.COST_CEILING_USD. If
so, it raises CostCeilingExceeded; the stage halts remaining paid work, the orchestrator finalizes a
clean partial run dir. The Director NEVER sees cost — this operates purely at the pipeline level.

NOT for: creative/planning decisions (the Director plans freely; cost never gates creativity).
"""
from __future__ import annotations
from . import config
from .tracing import Run


class CostCeilingExceeded(Exception):
    """Raised when a paid call would push the run over config.COST_CEILING_USD."""
    def __init__(self, run: Run, step: str, estimate: float):
        self.step, self.estimate = step, estimate
        self.spent, self.ceiling = run.cost_total(), config.COST_CEILING_USD
        super().__init__(
            f"cost ceiling ${self.ceiling:.2f} would be exceeded at '{step}': "
            f"spent ${self.spent:.4f} + est ${estimate:.4f} = ${self.spent + estimate:.4f}")


# --- per-call cost estimators (used BEFORE the call to gate it) -------------

def seedance_shot(duration_s: float, *, tier: str | None = None) -> float:
    tier = tier or config.SEEDANCE_TIER
    rate = config.SEEDANCE_RATE.get(tier, config.SEEDANCE_RATE["standard"])["image"]
    return round(duration_s * rate, 4)

def judge_call() -> float:
    # Flash judge is ~$0.0006/call (docs/judge_findings.md); a tiny fixed reserve.
    return 0.002

def keyframe_image(n: int = 1) -> float:
    return round(n * config.NANO_BANANA_COST_PER_IMAGE, 4)

def tts_call(char_count: int) -> float:
    return round(char_count / 1000 * config.TTS_COST_PER_1K_CHARS, 4)


# --- the gate ---------------------------------------------------------------

def check_ceiling(run: Run, estimate: float, step: str) -> None:
    """Raise CostCeilingExceeded if `estimate` on top of the running total would breach the ceiling.
    Call immediately BEFORE a paid call. Also emits a one-time near-ceiling warning."""
    spent = run.cost_total()
    if spent + estimate > config.COST_CEILING_USD:
        run.log(f"[COST CEILING] halt before '{step}': ${spent:.4f} + est ${estimate:.4f} "
                f"> ${config.COST_CEILING_USD:.2f}")
        raise CostCeilingExceeded(run, step, estimate)
    warn_if_near(run)


def warn_if_near(run: Run) -> None:
    spent = run.cost_total()
    if spent >= config.COST_CEILING_USD * config.COST_WARN_FRACTION:
        run.log(f"[COST WARNING] ${spent:.4f} of ${config.COST_CEILING_USD:.2f} ceiling spent "
                f"({spent / config.COST_CEILING_USD * 100:.0f}%).")
