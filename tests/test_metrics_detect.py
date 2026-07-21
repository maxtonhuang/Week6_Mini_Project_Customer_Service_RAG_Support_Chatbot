"""Tests for the foundation metrics + detection primitives."""
from __future__ import annotations

from ragguard import detect, metrics
from ragguard.schemas import RunRecord


def _rec(attack_id, stack, success, refused=False):
    return RunRecord(
        case_id=f"{attack_id}-{success}", attack_id=attack_id, goal="g",
        defense_stack=stack, success=success, refused=refused, blocked=False, latency_s=0.0,
    )


def test_asr_and_grouping():
    recs = [_rec("A1", "none", True), _rec("A1", "none", False),
            _rec("A2", "none", True), _rec("A2", "none", True)]
    assert metrics.asr(recs) == 0.75
    by = metrics.group_asr(recs, "attack_id")
    assert by["A1"] == 0.5 and by["A2"] == 1.0


def test_utility_text_similarity():
    assert metrics.text_similarity("reset your password", "reset your password") == 1.0
    assert metrics.text_similarity("abc", "xyz") == 0.0


def test_false_refusal_rate():
    assert metrics.false_refusal_rate([True, False, False, False]) == 0.25


def test_pareto_and_knee():
    pts = [
        (0.9, 0.2, "weak"),     # high utility, low robustness
        (0.5, 0.9, "strong"),   # low utility, high robustness
        (0.7, 0.7, "balanced"),
        (0.4, 0.4, "dominated"),  # dominated by balanced
    ]
    front = metrics.pareto_front(pts)
    labels = {p[2] for p in front}
    assert "dominated" not in labels
    assert {"weak", "strong", "balanced"} <= labels
    knee = metrics.knee_point(front)
    assert knee is not None and knee[2] == "balanced"


def test_refusal_detection():
    assert detect.is_refusal("I'm sorry, but I cannot share that information.")
    assert not detect.is_refusal("Sure! Here is how to reset your password.")


def test_pii_detection():
    hits = detect.find_pii("contact jane@example.com or call +1 415 555 1234")
    kinds = {k for k, _ in hits}
    assert "email" in kinds and "phone" in kinds


def test_canary_regex_shared():
    assert detect.CANARY_RE.search("code CANARY-7F3A-REFUND-OVERRIDE here")
