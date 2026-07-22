"""Defense implementations (D1-D6).

``build_all_defenses`` returns instances of every defense in canonical order. The
pipeline enforces the D6-before-D2 ordering rule at pre-retrieval time.
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
    HARDENED_SYSTEM_PROMPT,
)

DEFENSE_ORDER = ["D1", "D2", "D3", "D4", "D5", "D6", "D7", "D8", "D9"]

# The exhaustive two-stage Pareto search runs over the original content filters D1-D6
# (2^6 = 64 stacks). D7-D9 are targeted/deployment controls for A8/A9/A10 and are always
# on in the full stack + toggleable in the labs, but excluded from the 64-stack search so it
# doesn't blow up to 512 stacks (and so D8's session control doesn't perturb the sweep).
SEARCH_DEFENSE_IDS = ["D1", "D2", "D3", "D4", "D5", "D6"]

__all__ = [
    "build_all_defenses", "DEFENSE_ORDER", "SEARCH_DEFENSE_IDS", "HARDENED_SYSTEM_PROMPT",
    "D1SystemPromptSpotlight", "D2InputGuardrail", "D3RetrievalSanitiser",
    "D4OutputFilter", "D5Groundedness", "D6Normalizer",
    "D7VisibilityFilter", "D8RateLimit", "D9SemanticLeakFilter",
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
