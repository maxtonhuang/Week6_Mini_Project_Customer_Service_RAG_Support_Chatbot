"""Tests for the attack suite (A1-A7)."""
from __future__ import annotations

from ragguard.attacks import A1DirectInjection, A6Obfuscation, build_all_attacks
from ragguard.attacks.adaptive import AdaptiveAttacker, HeuristicAttackerLLM, adaptive_asr_curve
from ragguard.schemas import AttackCase, AttackGoal, Doc, LAB_EVASION, RagResponse, Visibility


def _canaries():
    return [Doc(f"int-{i}", f"internal note code CANARY-000{i}-TOPIC{i}",
                visibility=Visibility.INTERNAL, canary=f"CANARY-000{i}-TOPIC{i}") for i in range(3)]


def test_build_all_attacks_ids():
    atks = build_all_attacks(_canaries())
    assert [a.id for a in atks] == ["A1", "A2", "A3", "A4", "A5", "A6"]


def test_each_attack_generates_n_wellformed():
    for a in build_all_attacks(_canaries()):
        cases = a.generate(5)
        assert len(cases) == 5
        for c in cases:
            assert c.attack_id == a.id
            assert c.user_input and c.lab_type
            assert isinstance(c.goal, AttackGoal)


def test_a3_indirect_has_poison_and_marker():
    a3 = {a.id: a for a in build_all_attacks(_canaries())}["A3"]
    for c in a3.generate(3):
        assert c.injected_docs and c.target_marker == "PWNED-A3"
        assert "[[INJECT:PWNED-A3]]" in c.injected_docs[0].text
        assert c.benign_query == c.user_input


def test_a5_canary_targets_real_tokens():
    a5 = {a.id: a for a in build_all_attacks(_canaries())}["A5"]
    for c in a5.generate(3):
        assert c.injected_docs and c.target_marker.startswith("CANARY-")
        assert c.injected_docs[0].canary == c.target_marker


def test_a6_obfuscates_but_keeps_marker_and_tag():
    a6 = A6Obfuscation()
    base = A1DirectInjection().generate(1)[0].user_input
    c = a6.generate(2)[0]
    assert c.lab_type == LAB_EVASION
    assert c.user_input != base           # obfuscated
    assert c.target_marker                # preserved
    assert "[[INJECT:" in c.user_input    # functional tag kept intact


def test_a5_requires_canaries():
    try:
        from ragguard.attacks.static import A5CanaryExtraction
        A5CanaryExtraction([])
        assert False, "should raise"
    except ValueError:
        pass


class _FakePipeline:
    """Only 'succeeds' once enough mutation rounds have elapsed."""
    system_prompt = "sys"

    def __init__(self, win_round=3):
        self.win_round = win_round
        self.calls = 0

    def answer(self, query, injected_docs=None, defenses=None):
        self.calls += 1
        ans = "PWNED-A7" if self.calls >= self.win_round else "I'm sorry, but I cannot help with that."
        return RagResponse(query=query, answer=ans)


def test_adaptive_escalates_and_records_rounds():
    from ragguard.judge import RuleJudge
    seed = AttackCase("s0", "A1", AttackGoal.INDIRECT_INJECTION, "do the thing", target_marker="PWNED-A7")
    atk = AdaptiveAttacker(HeuristicAttackerLLM(), rounds=5)
    recs = atk.run([seed], _FakePipeline(win_round=3), RuleJudge())
    assert recs and all(r.attack_id == "A7" for r in recs)
    rounds = [r.round for r in recs]
    assert rounds == sorted(rounds)            # increasing within the seed
    assert any(r.success for r in recs)        # eventually succeeds
    curve = adaptive_asr_curve(recs)
    assert curve == sorted(curve)              # non-decreasing
    assert curve[-1] == 1.0
