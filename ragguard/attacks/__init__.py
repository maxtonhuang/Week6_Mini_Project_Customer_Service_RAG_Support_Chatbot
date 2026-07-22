"""Attack suite A1-A7.

``build_all_attacks`` returns the static suite (A1-A6). The adaptive agent (A7)
lives in ``ragguard.attacks.adaptive`` and is constructed separately because it
needs the pipeline + judge at run time.
"""
from __future__ import annotations

from .. import config
from ..interfaces import Attack
from .adaptive import AdaptiveAttacker, HeuristicAttackerLLM, adaptive_asr_curve
from .static import (
    A1DirectInjection,
    A2Jailbreak,
    A3IndirectInjection,
    A4SystemPromptExtraction,
    A5CanaryExtraction,
    A6Obfuscation,
    A8MembershipInference,
    A9FingerprintProbe,
    A10ParaphraseExtraction,
)

__all__ = [
    "build_all_attacks",
    "A1DirectInjection", "A2Jailbreak", "A3IndirectInjection",
    "A4SystemPromptExtraction", "A5CanaryExtraction", "A6Obfuscation",
    "A8MembershipInference", "A9FingerprintProbe", "A10ParaphraseExtraction",
    "AdaptiveAttacker", "HeuristicAttackerLLM", "adaptive_asr_curve",
]


def build_all_attacks(
    canary_docs,
    injection_prompts: list[str] | None = None,
    jailbreak_prompts: list[str] | None = None,
    seed: int = config.SEED,
) -> list[Attack]:
    """Instantiate the static attack suite A1-A6.

    ``canary_docs`` (required) are the planted confidential documents A5 tries to
    exfiltrate. ``injection_prompts`` / ``jailbreak_prompts`` override the built-in
    banks (e.g. with prompts loaded from the deepset / jailbreak HF datasets).
    """
    return [
        A1DirectInjection(injection_prompts),
        A2Jailbreak(jailbreak_prompts),
        A3IndirectInjection(),
        A4SystemPromptExtraction(),
        A5CanaryExtraction(canary_docs),
        A6Obfuscation(injection_prompts, jailbreak_prompts),
        A8MembershipInference(canary_docs),
        A9FingerprintProbe(seed=seed),
        A10ParaphraseExtraction(),
    ]
