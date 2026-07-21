"""Orchestration: run attack suites, sweep the attack x defense matrix, and run the
two-stage defense-stack search that picks the best stack.

Everything arrives via the foundation protocols (Pipeline/Attack/Judge/Defense) as
arguments — this module imports NO concrete work-stream module, so it is testable
with tiny fakes.
"""
from __future__ import annotations

import itertools
from statistics import mean
from typing import Callable, Sequence

from . import config, metrics
from .schemas import RunRecord


# ------------------------------ helpers ------------------------------

def _defense_ids(defenses) -> list[str]:
    return [getattr(d, "id", "?") for d in (defenses or [])]


def _stack_label(defenses) -> str:
    ids = _defense_ids(defenses)
    return RunRecord.stack_label(ids)


def _goal_str(goal) -> str:
    return getattr(goal, "value", str(goal))


def _answer_all(pipeline, queries, injected, defenses):
    """Batched answers when the pipeline supports ``answer_many`` (the real
    RagPipeline); otherwise a plain loop so test fakes still work."""
    if hasattr(pipeline, "answer_many"):
        return pipeline.answer_many(queries, injected, defenses=defenses)
    return [pipeline.answer(q, injected_docs=injected[i], defenses=defenses)
            for i, q in enumerate(queries)]


# ------------------------------ running attacks ------------------------------

def run_suite(pipeline, attacks, judge, defenses=None, n=None, stack_label=None) -> list[RunRecord]:
    """Run every attack (n cases each) through the pipeline under the given defenses,
    scoring each with the judge. Returns a flat list of RunRecords."""
    n = config.N_PER_ATTACK if n is None else n
    if stack_label is None:
        stack_label = _stack_label(defenses)
    cases = []
    for attack in attacks:
        cases.extend(attack.generate(n))
    resps = _answer_all(
        pipeline,
        [c.user_input for c in cases],
        [getattr(c, "injected_docs", None) for c in cases],
        defenses,
    )
    records: list[RunRecord] = []
    for case, resp in zip(cases, resps):
        v = judge.verdict(case, resp)
        records.append(RunRecord(
            case_id=case.case_id,
            attack_id=case.attack_id,
            goal=_goal_str(case.goal),
            defense_stack=stack_label,
            success=bool(v.success),
            refused=bool(v.refused),
            blocked=bool(resp.blocked),
            latency_s=float(resp.latency_s),
            reason=v.reason,
        ))
    return records


# ------------------------------ evaluating a stack ------------------------------

def evaluate_stack(pipeline, attacks, judge, defenses, benign_eval, n=None) -> dict:
    """Score a single defense stack on the four axes the project cares about:
    ASR (robustness), utility, false-refusal rate, and latency overhead."""
    n = config.N_PER_ATTACK if n is None else n
    label = _stack_label(defenses)

    recs = run_suite(pipeline, attacks, judge, defenses=defenses, n=n, stack_label=label)
    stack_asr = metrics.asr(recs)

    questions = [q for q, _ in benign_eval]
    golds = [g for _, g in benign_eval]
    bresps = _answer_all(pipeline, questions, [None] * len(questions), defenses)
    answers = [r.answer for r in bresps]
    blocked_flags = [bool(r.blocked) for r in bresps]   # FRR = benign wrongly blocked
    latencies = [float(r.latency_s) for r in bresps]

    return {
        "stack": label,
        "n_defenses": len(_defense_ids(defenses)),
        "asr": stack_asr,
        "robustness": 1.0 - stack_asr,
        "utility": metrics.utility(answers, golds),
        "frr": metrics.false_refusal_rate(blocked_flags),
        "overhead": mean(latencies) if latencies else 0.0,
        "_defenses": list(defenses or []),   # internal: kept so the search can re-run it
    }


# ------------------------------ two-stage stack search ------------------------------

def _default_objective(m: dict) -> float:
    """Reward robustness, penalise false refusals; utility breaks ties (see sort)."""
    return m["robustness"] - 0.5 * m["frr"]


def two_stage_search(
    pipeline, attacks, judge, all_defenses, benign_eval,
    screen_n=None, confirm_top=None, screen_benign=None,
    objective: Callable[[dict], float] | None = None,
) -> dict:
    """Screen ALL 2^k defense-stack subsets cheaply (small attack + benign samples),
    then re-evaluate the top few at full sample size and the FULL benign set. Returns
    screened + confirmed results, the Pareto frontier of (utility vs robustness), its
    knee, and the selected best stack."""
    screen_n = config.SCREEN_N if screen_n is None else screen_n
    confirm_top = config.CONFIRM_TOP if confirm_top is None else confirm_top
    screen_benign = config.SCREEN_BENIGN if screen_benign is None else screen_benign
    objective = objective or _default_objective

    defs = list(all_defenses)
    subsets: list[list] = []
    for r in range(len(defs) + 1):
        for combo in itertools.combinations(defs, r):
            subsets.append(list(combo))

    # Stage 1 — screen every subset at small n.
    screened: list[dict] = []
    screen_benign_set = benign_eval[:screen_benign]
    for subset in subsets:
        m = evaluate_stack(pipeline, attacks, judge, subset or None, screen_benign_set, n=screen_n)
        m["score"] = objective(m)
        screened.append(m)
    screened.sort(key=lambda d: (d["score"], d["utility"]), reverse=True)

    # Stage 2 — confirm the top finalists at full n.
    finalists: list[dict] = []
    for m in screened[:confirm_top]:
        full = evaluate_stack(pipeline, attacks, judge, m["_defenses"] or None, benign_eval,
                              n=config.N_PER_ATTACK)
        full["score"] = objective(full)
        finalists.append(full)
    finalists.sort(key=lambda d: (d["score"], d["utility"]), reverse=True)

    # Pareto frontier over the full screened set (fuller picture for the plot).
    points = [(m["utility"], m["robustness"], m["stack"]) for m in screened]
    front = metrics.pareto_front(points)
    knee = metrics.knee_point(front)

    best = finalists[0] if finalists else None
    return {
        "screened": [_clean(m) for m in screened],
        "finalists": [_clean(m) for m in finalists],
        "best": _clean(best) if best else None,
        "pareto": front,
        "knee": knee,
    }


def _clean(m: dict) -> dict:
    """Drop the internal defense-object list so results are serialisable."""
    return {k: v for k, v in m.items() if k != "_defenses"}


# ------------------------------ attack x defense matrix ------------------------------

def attack_defense_matrix(pipeline, attacks, judge, defenses_list, n=None) -> list[RunRecord]:
    """Records for: no defense, each single defense, and the full stack — for the
    attack x defense heatmap."""
    n = config.N_PER_ATTACK if n is None else n
    records: list[RunRecord] = []
    records += run_suite(pipeline, attacks, judge, defenses=None, n=n, stack_label="none")
    for d in defenses_list:
        records += run_suite(pipeline, attacks, judge, defenses=[d], n=n,
                             stack_label=RunRecord.stack_label([getattr(d, "id", "?")]))
    if len(defenses_list) > 1:
        records += run_suite(pipeline, attacks, judge, defenses=list(defenses_list), n=n,
                             stack_label=RunRecord.stack_label(_defense_ids(defenses_list)))
    return records
