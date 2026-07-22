"""Offline tests for the hardening pass: new attacks A8/A9/A10, new defences D7/D8/D9,
and the Visibility access-control fix. stdlib-only via run_tests.py (no torch/network)."""
from __future__ import annotations

from ragguard import prompts
from ragguard.attacks import build_all_attacks
from ragguard.defenses import (
    build_all_defenses, DEFENSE_ORDER, SEARCH_DEFENSE_IDS,
    D7VisibilityFilter, D8RateLimit,
)
from ragguard.judge import RuleJudge
from ragguard.schemas import Doc, Visibility
from ragguard.testing import KeywordRetriever, ScriptedLLM, tiny_corpus
from ragguard import canary as cm
from ragguard import rag


def _setup():
    docs = tiny_corpus() + cm.generate_canaries(n=6)
    canaries = [d for d in docs if d.is_canary()]
    pipe = rag.RagPipeline(KeywordRetriever(docs), ScriptedLLM())
    judge = RuleJudge(canary_tokens=cm.canary_tokens(canaries),
                      system_prompt_secrets=prompts.SYSTEM_PROMPT_SECRETS)
    attacks = {a.id: a for a in build_all_attacks(canary_docs=canaries)}
    defs = {d.id: d for d in build_all_defenses(system_prompt_secrets=prompts.SYSTEM_PROMPT_SECRETS)}
    return pipe, judge, attacks, defs


def _asr(pipe, judge, attack, stack, n=5):
    hits = 0
    for c in attack.generate(n):
        r = pipe.answer(c.user_input, injected_docs=c.injected_docs, defenses=stack)
        hits += judge.verdict(c, r).success
    return hits / n


def test_new_attacks_and_defenses_registered():
    _, _, attacks, defs = _setup()
    assert set(attacks) == {"A1", "A2", "A3", "A4", "A5", "A6", "A8", "A9", "A10"}
    assert DEFENSE_ORDER == ["D1", "D2", "D3", "D4", "D5", "D6", "D7", "D8", "D9"]
    assert SEARCH_DEFENSE_IDS == ["D1", "D2", "D3", "D4", "D5", "D6"]  # search stays at 64 stacks


def test_d7_visibility_drops_internal_docs():
    docs = [Doc("p", "public text"), Doc("i", "internal", visibility=Visibility.INTERNAL)]
    out = D7VisibilityFilter(role="public").post_retrieval("q", docs)
    assert [d.doc_id for d in out] == ["p"]
    # an authenticated agent bypasses the filter
    assert len(D7VisibilityFilter(role="agent").post_retrieval("q", docs)) == 2


def test_a8_membership_defended_by_access_control():
    pipe, judge, attacks, defs = _setup()
    assert _asr(pipe, judge, attacks["A8"], None) > 0            # leaks undefended
    assert _asr(pipe, judge, attacks["A8"], [defs["D7"]]) == 0    # D7 removes the internal doc


def test_a9_fingerprint_defended_by_d9():
    pipe, judge, attacks, defs = _setup()
    assert _asr(pipe, judge, attacks["A9"], None) > 0
    assert _asr(pipe, judge, attacks["A9"], [defs["D9"]]) == 0


def test_a10_paraphrase_defended_by_d9():
    from ragguard.attacks import A10ParaphraseExtraction
    # Public-only corpus: A10 leaks the (paraphrased) system prompt, not a canary — so this
    # isolates the sysprompt-leak path from the ScriptedLLM's canary-echo vulnerability.
    docs = [Doc("p1", "To reset your password, open Settings > Forgot Password."),
            Doc("p2", "Our refund window is 30 days from delivery.")]
    pipe = rag.RagPipeline(KeywordRetriever(docs), ScriptedLLM())
    judge = RuleJudge(system_prompt_secrets=prompts.SYSTEM_PROMPT_SECRETS)
    a10 = A10ParaphraseExtraction()
    d9 = build_all_defenses(system_prompt_secrets=prompts.SYSTEM_PROMPT_SECRETS)[-1]
    assert _asr(pipe, judge, a10, None) > 0
    assert _asr(pipe, judge, a10, [d9]) == 0


def test_d8_rate_limit_session_vs_batch():
    docs = tiny_corpus()
    pipe = rag.RagPipeline(KeywordRetriever(docs), ScriptedLLM())
    # persistent session (ONE D8 instance) -> blocks after the budget
    d8 = D8RateLimit(budget=3)
    blocked = sum(pipe.answer("hi", defenses=[d8], reset_session=False).blocked for _ in range(6))
    assert blocked == 3
    # batched sweep resets per case -> transparent (no distortion of ASR/FRR)
    rs = pipe.answer_many(["hi"] * 6, defenses=[D8RateLimit(budget=3)])
    assert sum(r.blocked for r in rs) == 0
