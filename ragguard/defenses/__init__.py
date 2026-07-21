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
    HARDENED_SYSTEM_PROMPT,
)

DEFENSE_ORDER = ["D1", "D2", "D3", "D4", "D5", "D6"]

__all__ = [
    "build_all_defenses", "DEFENSE_ORDER", "HARDENED_SYSTEM_PROMPT",
    "D1SystemPromptSpotlight", "D2InputGuardrail", "D3RetrievalSanitiser",
    "D4OutputFilter", "D5Groundedness", "D6Normalizer",
]


def build_all_defenses(
    system_prompt_secrets: list[str] | None = None,
    thresholds: dict | None = None,
) -> list[Defense]:
    """Instantiate all six defenses in canonical (D1..D6) order.

    ``thresholds`` may carry keys: 'D2' (float), 'D3_floor' (float), 'D5' (float).
    ``system_prompt_secrets`` is wired into D4 for system-prompt-leak detection.
    """
    t = thresholds or {}
    return [
        D1SystemPromptSpotlight(),
        D2InputGuardrail(threshold=t.get("D2", 0.5)),
        D3RetrievalSanitiser(score_floor=t.get("D3_floor")),
        D4OutputFilter(system_prompt_secrets=system_prompt_secrets),
        D5Groundedness(threshold=t.get("D5", 0.15)),
        D6Normalizer(),
    ]
