"""Orchestrator tests using inline fakes for Pipeline/Attack/Judge/Defense — no
dependency on the real work-stream modules."""
from __future__ import annotations

import os
import tempfile

from ragguard import orchestrator as orch
from ragguard import report
from ragguard.interfaces import Defense
from ragguard.schemas import AttackCase, AttackGoal, JudgeVerdict, RagResponse


class FakeDefense(Defense):
    def __init__(self, id):
        self.id = id
        self.name = id


class FakePipeline:
    """Vulnerable unless a 'protective' defense id is in the active stack."""
    system_prompt = "sp"

    def __init__(self, protective=("D4",)):
        self.protective = set(protective)

    def answer(self, query, injected_docs=None, defenses=None):
        ids = {getattr(d, "id", "") for d in (defenses or [])}
        blocked = bool(self.protective & ids)
        answer = "[blocked by defense]" if blocked else f"LEAK PWNED for {query}"
        return RagResponse(query=query, answer=answer, retrieved=[], blocked=blocked,
                           block_reason="", fired_defenses=list(ids), latency_s=0.001)


class FakeAttack:
    id = "AX"
    name = "fake"
    goal = AttackGoal.INDIRECT_INJECTION
    lab_type = "LLM"

    def generate(self, n):
        return [AttackCase(case_id=f"AX-{i}", attack_id="AX", goal=self.goal,
                           user_input=f"q{i}", target_marker="PWNED") for i in range(n)]


class FakeJudge:
    def verdict(self, case, resp):
        success = (case.target_marker in resp.answer) and not resp.blocked
        return JudgeVerdict(success=success, refused=resp.blocked, reason="")


BENIGN = [("how do I reset my password", "open settings and reset your password"),
          ("track my order", "track it from the orders page"),
          ("refund window", "our refund window is 30 days")]


def test_run_suite_counts_and_success():
    recs = orch.run_suite(FakePipeline(), [FakeAttack()], FakeJudge(), defenses=None, n=5)
    assert len(recs) == 5
    assert all(r.attack_id == "AX" and r.defense_stack == "none" for r in recs)
    assert all(r.success for r in recs)  # undefended -> all succeed


def test_evaluate_stack_keys_and_values():
    m = orch.evaluate_stack(FakePipeline(), [FakeAttack()], FakeJudge(),
                            [FakeDefense("D4")], BENIGN, n=5)
    for k in ("stack", "asr", "robustness", "utility", "frr", "overhead"):
        assert k in m
    assert 0.0 <= m["asr"] <= 1.0 and 0.0 <= m["robustness"] <= 1.0
    assert m["asr"] == 0.0          # D4 blocks the attack
    assert m["frr"] > 0.0           # ...but also blocks benign queries (the trade-off)


def test_two_stage_search_enumerates_and_selects():
    defs = [FakeDefense("D1"), FakeDefense("D2"), FakeDefense("D4")]
    out = orch.two_stage_search(FakePipeline(), [FakeAttack()], FakeJudge(), defs, BENIGN,
                                screen_n=3, confirm_top=3)
    assert len(out["screened"]) == 2 ** len(defs)     # all 8 subsets
    assert out["best"] is not None
    assert "_defenses" not in out["best"]             # internal field stripped
    assert len(out["pareto"]) >= 1
    assert len(out["finalists"]) <= 3


def test_attack_defense_matrix():
    defs = [FakeDefense("D1"), FakeDefense("D4")]
    recs = orch.attack_defense_matrix(FakePipeline(), [FakeAttack()], FakeJudge(), defs, n=3)
    stacks = {r.defense_stack for r in recs}
    assert "none" in stacks
    assert any("D4" in s for s in stacks)


def test_report_pure_functions_import_stdlib_only():
    recs = orch.run_suite(FakePipeline(), [FakeAttack()], FakeJudge(), defenses=None, n=3)
    md = report.results_table(recs)
    assert "AX" in md and "ASR by attack" in md
    with tempfile.TemporaryDirectory() as d:
        p = os.path.join(d, "r.csv")
        report.records_to_csv(recs, p)
        assert os.path.exists(p)
