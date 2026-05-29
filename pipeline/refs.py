"""Reference loader — injects the Motion / SMB playbook into the thinking-stage prompts.

The deep craft (ad formats + per-vertical "what converts" + hook data, all from Motion's $1.3B Meta
ad-spend analysis) lives in scaffolds/references/*.md. Scaffolds are thin entry files (CLAUDE.md);
this wires the references INTO the Director / Concept / Hook-Designer context so they reason WITH the
data instead of improvising. Vertical-agnostic by construction: the whole multi-vertical playbook is
injected and the model selects the row relevant to {{business}}/{{brief}} — no per-vertical slicing,
so any SMB (salon, bakery, daycare, barber, …) is covered equally.

NOT for: business-specific logic — this only loads shared reference text.
"""
from __future__ import annotations
from . import config

REF_DIR = config.SCAFFOLDS_DIR / "references"


def reference_block(names: list[str]) -> str:
    """Concatenate the named reference files into one labeled block to append to a system prompt."""
    parts: list[str] = []
    for n in names:
        p = REF_DIR / n
        if p.exists():
            parts.append(f"\n\n---\n# REFERENCE — {n} (Motion / SMB playbook; reason WITH this)\n\n"
                         + p.read_text().strip())
    return "".join(parts)
