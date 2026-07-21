"""Tests for the Gradio app's logic layer (DemoController). No gradio needed —
the UI wiring is separate and imports gradio lazily."""
from __future__ import annotations

from ragguard.app import DemoController


def _ctrl():
    return DemoController.offline(seed=7)


def test_controller_builds_offline():
    c = _ctrl()
    assert c.attacks and c.all_defenses and c.canaries
    assert set(c.defenses_by_id) == {"D1", "D2", "D3", "D4", "D5", "D6"}


def test_benign_query_is_answered():
    c = _ctrl()
    r = c.run_query("how do I reset my password?", "None", [])
    assert r.goal is None and r.answer and not r.blocked
    assert "Benign" in DemoController.verdict_html(r)


def test_attack_succeeds_then_defense_blocks():
    c = _ctrl()
    hot = c.run_query("", "A5", [])                 # canary extraction, undefended
    assert hot.attack_success is True
    cold = c.run_query("", "A5", ["D2", "D3", "D4"])  # with the best stack
    assert cold.attack_success is False
    # verdict rendering reflects the two states
    assert "SUCCEEDED" in DemoController.verdict_html(hot)
    assert "BLOCKED" in DemoController.verdict_html(cold) or "failed" in DemoController.verdict_html(cold)


def test_attack_table_shape():
    c = _ctrl()
    rows, asr = c.attack_table(4)
    assert len(rows) == 6 and all(len(row) == 4 for row in rows)
    assert 0.0 <= asr <= 1.0


def test_retrieved_markdown_flags_canaries():
    c = _ctrl()
    r = c.run_query("", "A5", [])
    md = DemoController.retrieved_markdown(r.retrieved)
    assert "INTERNAL" in md or "INJECTED" in md or "public" in md


def test_governance_markdown_has_both_scorecards():
    c = _ctrl()
    md = c.governance_markdown({"baseline_asr": 0.8, "defended_asr": 0.1, "best_stack": "D2+D3+D4"})
    assert md.count("NIST AI RMF") >= 2


def test_demo_script_has_four_beats():
    c = _ctrl()
    s = c.demo_script()
    for beat in ("1. It works", "2. It breaks", "3. We fix it", "4. It still works"):
        assert beat in s


def test_evaluate_stack_quick_returns_metrics():
    c = _ctrl()
    md = c.evaluate_stack_quick(["D2", "D3"], n=2, benign_k=4)
    assert "ASR" in md and "robustness" in md and "D2+D3" in md


def test_cached_helpers_no_results():
    c = _ctrl()   # offline controller has no saved results.json
    rows = c.cached_attack_rows()          # catalog shown even without a run
    assert len(rows) == 6
    assert rows[0][0] == "A1" and rows[0][1] and rows[0][2]   # id, name, type present
    assert rows[0][3] == "–"               # no ASR data yet
    assert "run" in c.best_summary_md().lower()


def test_header_stats_html():
    c = _ctrl()
    h = c.header_stats_html()
    assert "rg-stats" in h and "Model" in h and "Best stack" in h
