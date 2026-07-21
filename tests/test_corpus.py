"""Tests for the knowledge base + canaries + benign eval (offline path)."""
from __future__ import annotations

from ragguard import config
from ragguard.canary import canary_tokens, generate_canaries
from ragguard.corpus import build_knowledge_base
from ragguard.schemas import Visibility


def test_kb_has_public_and_canaries():
    docs, benign = build_knowledge_base()
    canaries = [d for d in docs if d.is_canary()]
    assert len(canaries) == config.N_CANARIES
    assert len(docs) > config.N_CANARIES          # public docs present too
    for d in canaries:
        assert d.visibility == Visibility.INTERNAL
        assert d.source == "internal"
        assert config.CANARY_RE.fullmatch(d.canary), d.canary


def test_canary_tokens_are_unique():
    docs = generate_canaries()
    toks = canary_tokens(docs)
    assert len(toks) == config.N_CANARIES
    assert len(set(toks)) == len(toks)


def test_canary_generation_is_deterministic():
    a = canary_tokens(generate_canaries(seed=123))
    b = canary_tokens(generate_canaries(seed=123))
    assert a == b


def test_benign_eval_nonempty_and_disjoint():
    docs, benign = build_knowledge_base()
    assert benign
    kb_texts = {d.text for d in docs}
    questions = {q for q, _ in benign}
    assert not (questions & kb_texts)             # benign questions are not KB docs
