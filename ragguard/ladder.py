"""Sophistication-ladder harness: sweep attack-levels L0/L1/L2 x defence-levels D0/D1/D2
and fill the ASR (+ utility/FRR) matrix.

Builds entirely on the foundation + Task 1 (attack levels) + Task 2 (defence levels) APIs:
this module imports no concrete work-stream internals of its own — it only calls
``level_cases``, ``build_defense_level``, ``_answer_all`` and ``metrics.*``, exactly like
``orchestrator.evaluate_stack`` does for the single-stack case.
"""
from __future__ import annotations

from statistics import mean

from . import metrics
from .attacks.levels import LADDER_FAMILIES, level_cases
from .defenses import build_defense_level, defense_level_stack_label
from .orchestrator import _answer_all, _stop


def run_ladder(
    pipe,
    judge,
    *,
    production,
    canary_docs,
    benign_eval,
    families=None,
    n=8,
    attack_levels=(0, 1, 2),
    defense_levels=(0, 1, 2),
    system_prompt_secrets=None,
    should_stop=None,
) -> dict:
    """Run every family in ``families`` (default ``LADDER_FAMILIES``) at each attack level
    against each defence level, recording ASR per (family, attack level, defence level) plus
    per-defence-level utility/FRR on ``benign_eval``. All inner dict keys are strings so the
    result round-trips through JSON.
    """
    families = list(LADDER_FAMILIES) if families is None else list(families)

    # Precompute each defence level's stack, and its utility + FRR on the benign set once
    # (exactly the evaluate_stack idiom: answer the benign questions once per stack).
    defs_by_level: dict[int, list] = {}
    utility: dict[str, float] = {}
    frr: dict[str, float] = {}
    defense_level_stacks: dict[str, str] = {}
    questions = [q for q, _ in benign_eval]
    golds = [g for _, g in benign_eval]
    for dl in defense_levels:
        defs = build_defense_level(dl, system_prompt_secrets=system_prompt_secrets)
        defs_by_level[dl] = defs
        defense_level_stacks[str(dl)] = defense_level_stack_label(dl)
        bresps = _answer_all(pipe, questions, [None] * len(questions), defs)
        answers = [r.answer for r in bresps]
        blocked_flags = [bool(r.blocked) for r in bresps]
        utility[str(dl)] = metrics.utility(answers, golds)
        frr[str(dl)] = metrics.false_refusal_rate(blocked_flags)

    asr: dict[str, dict[str, dict[str, float]]] = {}
    for family in families:
        _stop(should_stop)   # let the UI Stop button abort between families
        asr[family] = {}
        for al in attack_levels:
            cases = level_cases(family, al, n, production=production, canary_docs=canary_docs)
            asr[family][str(al)] = {}
            for dl in defense_levels:
                resps = _answer_all(
                    pipe,
                    [c.user_input for c in cases],
                    [getattr(c, "injected_docs", None) for c in cases],
                    defs_by_level[dl],
                )
                asr[family][str(al)][str(dl)] = mean(
                    judge.verdict(c, r).success for c, r in zip(cases, resps)
                )

    asr_overall: dict[str, dict[str, float]] = {}
    for al in attack_levels:
        asr_overall[str(al)] = {
            str(dl): mean(asr[fam][str(al)][str(dl)] for fam in families)
            for dl in defense_levels
        }

    return {
        "families": list(families),
        "attack_levels": list(attack_levels),
        "defense_levels": list(defense_levels),
        "n": n,
        "asr": asr,
        "asr_overall": asr_overall,
        "utility": utility,
        "frr": frr,
        "defense_level_stacks": defense_level_stacks,
    }
