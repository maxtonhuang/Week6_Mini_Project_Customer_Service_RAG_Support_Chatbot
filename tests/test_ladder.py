"""Tests for the sophistication-ladder harness: level_cases (Task 1) sanity + run_ladder
(Task 3), which fills the attack-level x defence-level matrix with ASR (+ utility/FRR)."""
from __future__ import annotations

import pytest


def test_level_cases_all_families_all_levels():
    from ragguard import corpus
    from ragguard.attacks import build_all_attacks
    from ragguard.attacks.levels import level_cases, LADDER_FAMILIES
    docs, _ = corpus.build_knowledge_base()
    canaries = [d for d in docs if d.is_canary()]
    prod = {a.id: a for a in build_all_attacks(canary_docs=canaries)}
    for fam in LADDER_FAMILIES:
        for lvl in (0, 1, 2):
            cases = level_cases(fam, lvl, 4, production=prod, canary_docs=canaries)
            assert len(cases) == 4 and all(c.attack_id == fam for c in cases)


def test_run_ladder_offline_shape():
    from ragguard import corpus, prompts, canary as cm
    from ragguard.testing import ScriptedLLM, KeywordRetriever
    from ragguard.rag import RagPipeline
    from ragguard.judge import RuleJudge
    from ragguard.attacks import build_all_attacks
    from ragguard.attacks.levels import LADDER_FAMILIES
    from ragguard.ladder import run_ladder
    docs, benign = corpus.build_knowledge_base()
    canaries = [d for d in docs if d.is_canary()]
    pipe = RagPipeline(KeywordRetriever(docs), ScriptedLLM())
    judge = RuleJudge(canary_tokens=cm.canary_tokens(canaries),
                      system_prompt_secrets=prompts.SYSTEM_PROMPT_SECRETS)
    prod = {a.id: a for a in build_all_attacks(canary_docs=canaries)}
    benign_eval = [(d.text, "") for d in docs[:4]]
    out = run_ladder(pipe, judge, production=prod, canary_docs=canaries,
                     benign_eval=benign_eval, n=3, system_prompt_secrets=prompts.SYSTEM_PROMPT_SECRETS)
    assert set(out["families"]) == set(LADDER_FAMILIES)
    for fam in LADDER_FAMILIES:
        for al in ("0", "1", "2"):
            assert set(out["asr"][fam][al]) == {"0", "1", "2"}
            for dl in ("0", "1", "2"):
                assert 0.0 <= out["asr"][fam][al][dl] <= 1.0
    assert set(out["asr_overall"]) == {"0", "1", "2"}
    assert set(out["utility"]) == {"0", "1", "2"} and set(out["frr"]) == {"0", "1", "2"}
    assert out["defense_level_stacks"]["0"] == "none"


def test_run_ladder_stops():
    from ragguard import corpus, prompts, canary as cm
    from ragguard.testing import ScriptedLLM, KeywordRetriever
    from ragguard.rag import RagPipeline
    from ragguard.judge import RuleJudge
    from ragguard.attacks import build_all_attacks
    from ragguard.ladder import run_ladder
    from ragguard.orchestrator import RunCancelled
    docs, benign = corpus.build_knowledge_base()
    canaries = [d for d in docs if d.is_canary()]
    pipe = RagPipeline(KeywordRetriever(docs), ScriptedLLM())
    judge = RuleJudge(canary_tokens=cm.canary_tokens(canaries),
                      system_prompt_secrets=prompts.SYSTEM_PROMPT_SECRETS)
    prod = {a.id: a for a in build_all_attacks(canary_docs=canaries)}
    benign_eval = [(d.text, "") for d in docs[:4]]
    with pytest.raises(RunCancelled):
        run_ladder(pipe, judge, production=prod, canary_docs=canaries,
                   benign_eval=benign_eval, n=3,
                   system_prompt_secrets=prompts.SYSTEM_PROMPT_SECRETS,
                   should_stop=lambda: True)
