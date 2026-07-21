"""NIST AI RMF scorecard tests."""
from __future__ import annotations

from ragguard import governance as gov


def test_scorecards_structure_and_improvement():
    b = gov.baseline_scorecard()
    d = gov.defended_scorecard({"baseline_asr": 0.8, "defended_asr": 0.1,
                                "best_stack": "D1+D4", "frr": 0.05})
    for sc in (b, d):
        keys = {f.key for f in sc.functions}
        assert keys == {"MAP", "MEASURE", "MANAGE"}
        assert sc.max_total() > 0
        assert 0 <= sc.total() <= sc.max_total()
    assert d.total() > b.total()   # defending improves the governance posture


def test_render_markdown_and_rows():
    d = gov.defended_scorecard()
    md = gov.render_markdown(d)
    assert "Map" in md and "Measure" in md and "Manage" in md
    rows = gov.to_rows(d)
    assert len(rows) == 9
    assert all({"function", "id", "status", "score"} <= set(r) for r in rows)


def test_compare():
    b = gov.baseline_scorecard()
    d = gov.defended_scorecard({"baseline_asr": 0.8, "defended_asr": 0.1})
    cmp = gov.compare(b, d)
    assert "→" in cmp and "MEASURE-2.7" in cmp


def test_evidence_carries_numbers():
    d = gov.defended_scorecard({"baseline_asr": 0.8, "defended_asr": 0.1, "best_stack": "D1+D4"})
    md = gov.render_markdown(d)
    assert "80%" in md and "10%" in md   # ASR reduction evidence rendered
