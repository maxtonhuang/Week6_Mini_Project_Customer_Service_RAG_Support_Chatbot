"""Metrics + selection math. Pure stdlib (no numpy/pandas needed to compute).

Shared by the attacks work-stream and the orchestrator, so it lives in the foundation.
Optional ``to_dataframe`` lazily imports pandas for convenience only.
"""
from __future__ import annotations

import re
from statistics import mean
from typing import Iterable, Sequence

from .schemas import RunRecord

_WORD = re.compile(r"[a-z0-9]+")


# ----------------------------- attack success -----------------------------

def asr(records: Sequence[RunRecord]) -> float:
    """Attack success rate over records."""
    if not records:
        return 0.0
    return sum(1 for r in records if r.success) / len(records)


def group_asr(records: Sequence[RunRecord], key: str) -> dict[str, float]:
    """ASR grouped by a RunRecord attribute (e.g. 'attack_id', 'defense_stack')."""
    buckets: dict[str, list[RunRecord]] = {}
    for r in records:
        buckets.setdefault(str(getattr(r, key)), []).append(r)
    return {k: asr(v) for k, v in buckets.items()}


def refusal_rate(records: Sequence[RunRecord]) -> float:
    if not records:
        return 0.0
    return sum(1 for r in records if r.refused) / len(records)


# --------------------------------- utility --------------------------------

def text_similarity(a: str, b: str) -> float:
    """Token-F1 overlap in [0,1]. Default offline utility scorer (swap for
    embedding cosine on Colab if desired)."""
    ta, tb = set(_WORD.findall(a.lower())), set(_WORD.findall(b.lower()))
    if not ta or not tb:
        return 0.0
    inter = len(ta & tb)
    if inter == 0:
        return 0.0
    prec, rec = inter / len(ta), inter / len(tb)
    return 2 * prec * rec / (prec + rec)


def utility(answers: Sequence[str], golds: Sequence[str], scorer=text_similarity) -> float:
    """Mean similarity of answers to gold responses."""
    pairs = list(zip(answers, golds))
    if not pairs:
        return 0.0
    return mean(scorer(a, g) for a, g in pairs)


def false_refusal_rate(blocked_flags: Iterable[bool]) -> float:
    """Fraction of benign queries that were wrongly blocked/refused."""
    flags = list(blocked_flags)
    if not flags:
        return 0.0
    return sum(1 for b in flags if b) / len(flags)


# ------------------------------ Pareto / knee -----------------------------

def pareto_front(points: Sequence[tuple[float, float, str]]) -> list[tuple[float, float, str]]:
    """Non-dominated points maximising both coordinates.

    points: (utility, robustness, label) where robustness = 1 - ASR.
    Returns the front sorted by utility descending.
    """
    front: list[tuple[float, float, str]] = []
    for p in points:
        dominated = any(
            (q[0] >= p[0] and q[1] >= p[1]) and (q[0] > p[0] or q[1] > p[1])
            for q in points if q is not p
        )
        if not dominated:
            front.append(p)
    # de-duplicate identical coords, keep first label
    seen: set[tuple[float, float]] = set()
    uniq = []
    for u, r, lbl in sorted(front, key=lambda x: (-x[0], -x[1])):
        if (round(u, 6), round(r, 6)) in seen:
            continue
        seen.add((round(u, 6), round(r, 6)))
        uniq.append((u, r, lbl))
    return uniq


def knee_point(front: Sequence[tuple[float, float, str]]) -> tuple[float, float, str] | None:
    """Pick the knee: the front point closest to the ideal (max util, max robustness)
    after min-max normalising each axis."""
    if not front:
        return None
    if len(front) == 1:
        return front[0]
    us = [p[0] for p in front]
    rs = [p[1] for p in front]
    umin, umax = min(us), max(us)
    rmin, rmax = min(rs), max(rs)

    def norm(v, lo, hi):
        return 0.0 if hi == lo else (v - lo) / (hi - lo)

    best, best_d = None, 1e9
    for p in front:
        nu, nr = norm(p[0], umin, umax), norm(p[1], rmin, rmax)
        d = (1 - nu) ** 2 + (1 - nr) ** 2
        if d < best_d:
            best_d, best = d, p
    return best


# ------------------------------- convenience ------------------------------

def summarize(records: Sequence[RunRecord]) -> dict:
    return {
        "n": len(records),
        "asr_overall": asr(records),
        "asr_by_attack": group_asr(records, "attack_id"),
        "asr_by_stack": group_asr(records, "defense_stack"),
        "refusal_rate": refusal_rate(records),
    }


def to_dataframe(records: Sequence[RunRecord]):
    """Optional: build a pandas DataFrame (lazy import)."""
    import pandas as pd  # noqa: local heavy import
    return pd.DataFrame([r.__dict__ for r in records])
