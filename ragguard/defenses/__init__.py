"""Defense implementations (D1-D9).

``build_all_defenses`` returns instances of every defense in canonical order. The
pipeline enforces the D6-before-D2 ordering rule at pre-retrieval time. The exhaustive
Pareto search runs over D1-D6 only (``SEARCH_DEFENSE_IDS``); D7-D9 are targeted/deployment
controls always-on in the full stack.
"""
from __future__ import annotations

from ..interfaces import Defense
from .impl import (
    D1SystemPromptSpotlight,
    D2InputGuardrail,
    D3RetrievalSanitiser,
    D4OutputFilter,
    D5Groundedness,
    D6Normalizer,
    D7VisibilityFilter,
    D8RateLimit,
    D9SemanticLeakFilter,
    D10InstructionHierarchy,
    D11DecodeScan,
    HARDENED_SYSTEM_PROMPT,
)

DEFENSE_ORDER = ["D1", "D2", "D3", "D4", "D5", "D6", "D7", "D8", "D9"]

# The exhaustive two-stage Pareto search runs over the original content filters D1-D6
# (2^6 = 64 stacks). D7-D9 are targeted/deployment controls for A8/A9/A10 and are always
# on in the full stack + toggleable in the labs, but excluded from the 64-stack search so it
# doesn't blow up to 512 stacks (and so D8's session control doesn't perturb the sweep).
SEARCH_DEFENSE_IDS = ["D1", "D2", "D3", "D4", "D5", "D6"]

# Sophistication-ladder defence levels: D0 (none) / D1 (content filters) / D2
# (defence-in-depth, incl. D10/D11). See build_defense_level below.
DEFENSE_LEVEL_LABELS = {
    0: "D0 · none",
    1: "D1 · content filters",
    2: "D2 · defence-in-depth",
}

__all__ = [
    "build_all_defenses", "DEFENSE_ORDER", "SEARCH_DEFENSE_IDS", "HARDENED_SYSTEM_PROMPT",
    "D1SystemPromptSpotlight", "D2InputGuardrail", "D3RetrievalSanitiser",
    "D4OutputFilter", "D5Groundedness", "D6Normalizer",
    "D7VisibilityFilter", "D8RateLimit", "D9SemanticLeakFilter",
    "D10InstructionHierarchy", "D11DecodeScan",
    "build_defense_level", "defense_level_stack_label", "DEFENSE_LEVEL_LABELS",
]


def build_all_defenses(
    system_prompt_secrets: list[str] | None = None,
    thresholds: dict | None = None,
) -> list[Defense]:
    """Instantiate all defenses in canonical (D1..D9) order.

    ``thresholds`` may carry keys: 'D2' (float), 'D3_floor' (float), 'D5' (float), 'D9' (float).
    ``system_prompt_secrets`` is wired into D4 and D9 for system-prompt-leak detection.
    """
    t = thresholds or {}
    return [
        D1SystemPromptSpotlight(),
        D2InputGuardrail(threshold=t.get("D2", 0.5)),
        D3RetrievalSanitiser(score_floor=t.get("D3_floor")),
        D4OutputFilter(system_prompt_secrets=system_prompt_secrets),
        D5Groundedness(threshold=t.get("D5", 0.15)),
        D6Normalizer(),
        D7VisibilityFilter(role="public"),
        D8RateLimit(),
        D9SemanticLeakFilter(system_prompt_secrets=system_prompt_secrets, threshold=t.get("D9", 0.35)),
    ]


def build_defense_level(k: int, *, system_prompt_secrets: list[str] | None = None) -> list[Defense]:
    """Build one of the three sophistication-ladder defence levels (D0/D1/D2), run against
    attack levels L0/L1/L2.

    * ``k == 0`` -> no defence at all.
    * ``k == 1`` -> content filters only: D1+D2+D4+D6 (spotlighting, input guardrail,
      output filter, input normalisation).
    * ``k == 2`` -> full defence-in-depth: D1-D7, D9, plus the two new controls D10
      (instruction hierarchy) and D11 (decode-then-scan output filter). D8 (session rate
      limit) is a deployment control, excluded here the same way it's excluded from
      ``SEARCH_DEFENSE_IDS``.
    """
    if k == 0:
        return []
    if k == 1:
        return [
            D1SystemPromptSpotlight(),
            D2InputGuardrail(),
            D4OutputFilter(system_prompt_secrets=system_prompt_secrets),
            D6Normalizer(),
        ]
    if k == 2:
        return [
            D1SystemPromptSpotlight(),
            D2InputGuardrail(),
            D3RetrievalSanitiser(),
            D4OutputFilter(system_prompt_secrets=system_prompt_secrets),
            D5Groundedness(),
            D6Normalizer(),
            D7VisibilityFilter(role="public"),
            D9SemanticLeakFilter(system_prompt_secrets=system_prompt_secrets),
            D10InstructionHierarchy(),
            D11DecodeScan(system_prompt_secrets=system_prompt_secrets),
        ]
    raise ValueError(f"invalid defense level: {k!r} (must be 0, 1, or 2)")


def defense_level_stack_label(k: int) -> str:
    """Human-readable '+'-joined id label for a defence level, e.g. 'D1+D2+D4+D6'."""
    ids = [d.id for d in build_defense_level(k)]
    return "+".join(ids) if ids else "none"
