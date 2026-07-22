"""Regression tests for the three gaps a reviewer flagged:
  1. Optuna threshold tuning exists and runs.
  2. The adaptive attacker (A7) is driven by the injected LLM, not hardcoded.
  3. The benign eval set is guaranteed disjoint from the KB.
"""
from __future__ import annotations

from ragguard import corpus
from ragguard.schemas import AttackCase, AttackGoal, JudgeVerdict, RagResponse


# ---------------- Gap 3: benign eval disjoint from the KB ----------------

def test_benign_eval_disjoint_from_kb():
    docs, benign = corpus.build_knowledge_base(seed=3)
    kb = {d.text for d in docs}
    assert benign, "benign eval is empty"
    leaks = [a for _, a in benign if a in kb]
    assert not leaks, f"{len(leaks)} benign gold answers are indexed KB docs (not disjoint)"


def test_build_benign_eval_excludes_responses():
    base = corpus.build_benign_eval(n=50, seed=1)
    assert base
    victim = base[0][1]
    filtered = corpus.build_benign_eval(n=50, seed=1, exclude_responses={victim})
    assert all(a != victim for _, a in filtered), "exclude_responses did not remove the answer"


# ---------------- Gap 2: A7 is LLM-driven ----------------

class _RecordingLLM:
    def __init__(self):
        self.calls = []
    def generate(self, messages, **kw):
        self.calls.append(messages)
        return f"MUTATED-PROMPT-{len(self.calls)}"
    def generate_batch(self, batch, **kw):
        return [self.generate(m) for m in batch]


class _AlwaysFailPipe:
    def answer(self, query, injected_docs=None, defenses=None):
        return RagResponse(query=query, answer="I can't help with that.", blocked=False)


class _NeverSucceedJudge:
    def verdict(self, case, resp):
        return JudgeVerdict(success=False, refused=True, reason="refused")


def test_adaptive_attacker_is_llm_driven():
    from ragguard.attacks.adaptive import AdaptiveAttacker
    llm = _RecordingLLM()
    seeds = [AttackCase(case_id="s1", attack_id="A1",
                        goal=AttackGoal.POLICY_VIOLATION, user_input="original prompt")]
    recs = AdaptiveAttacker(llm, rounds=3).run(seeds, _AlwaysFailPipe(), _NeverSucceedJudge())
    assert len(recs) == 3
    # every failed round asks the injected LLM to mutate -> proves it's LLM-driven
    assert len(llm.calls) == 3, f"attacker LLM called {len(llm.calls)} times (expected 3)"
    # the LLM actually saw the failed prompt + response (PAIR-style feedback)
    joined = " ".join(m.get("content", "") for m in llm.calls[0])
    assert "original prompt" in joined and "RESPONSE" in joined


# ---------------- Gap 1: Optuna threshold tuning ----------------

def test_tune_thresholds_runs_optuna():
    try:
        import optuna  # noqa: F401
    except Exception:
        print("SKIP test_tune_thresholds_runs_optuna: optuna not installed (offline sandbox)")
        return
    from ragguard import orchestrator

    class FakeAtk:
        id, name, lab_type = "A1", "fake", "LLM"
        def generate(self, n):
            return [AttackCase(case_id=f"c{i}", attack_id="A1",
                               goal=AttackGoal.POLICY_VIOLATION, user_input="x") for i in range(n)]

    class FakeDef:
        def __init__(self, thr): self.id, self.thr = "D5", thr

    class FakePipe:
        def _one(self, defenses):
            thr = getattr(defenses[0], "thr", 0.0) if defenses else 0.0
            blocked = thr >= 0.5
            return RagResponse(query="q", answer="blocked" if blocked else "ok", blocked=blocked)
        def answer(self, q, injected_docs=None, defenses=None):
            return self._one(defenses)
        def answer_many(self, qs, injected_docs_list=None, defenses=None):
            return [self._one(defenses) for _ in qs]

    class FakeJudge:
        def verdict(self, case, resp):
            return JudgeVerdict(success=(resp.answer == "ok"), refused=False)

    res = orchestrator.tune_thresholds(
        FakePipe(), [FakeAtk()], FakeJudge(),
        defense_factory=lambda p: [FakeDef(p["D5"])],
        benign_eval=[("q", "gold")] * 4,
        param_space={"D5": (0.0, 1.0)},
        n_trials=5, n=2, benign_k=2,
    )
    assert "best_params" in res and "D5" in res["best_params"]
    assert "tuned_metrics" in res and 0.0 <= res["tuned_metrics"]["asr"] <= 1.0
    assert res["n_trials"] == 5


# ---------------- VRAM auto-tuning ----------------

def test_autotune_tiers():
    from ragguard import autotune
    assert autotune.recommend(vram=32)["load_in_4bit"] is False   # 5090 -> bf16
    assert autotune.recommend(vram=24)["load_in_4bit"] is False   # L4  -> bf16
    p12 = autotune.recommend(vram=12)                              # 5070 -> 4-bit
    assert p12["load_in_4bit"] is True and "bitsandbytes" in p12["needs"]
    p8 = autotune.recommend(vram=8)                                # 8 GB -> smaller model
    assert p8["load_in_4bit"] is False and p8["model_id"] == autotune.SMALL_MODEL
    assert autotune.recommend(vram=4)["load_in_4bit"] is True
    assert autotune.recommend(vram=None)["device"] in ("cpu", "cuda")


def test_autotune_ensure_installed_skips_present():
    from ragguard import autotune
    assert autotune.ensure_installed(["json"], verbose=False) == []   # stdlib already present
