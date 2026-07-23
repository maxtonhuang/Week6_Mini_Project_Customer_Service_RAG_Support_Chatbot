import pytest

_LADDER = {
    "families": ["A1", "A9"], "attack_levels": [0, 1, 2], "defense_levels": [0, 1, 2], "n": 3,
    "asr": {"A1": {"0": {"0": 0.9, "1": 0.3, "2": 0.0}, "1": {"0": 0.95, "1": 0.4, "2": 0.05},
                    "2": {"0": 1.0, "1": 0.5, "2": 0.1}},
             "A9": {"0": {"0": 1.0, "1": 0.5, "2": 0.0}, "1": {"0": 1.0, "1": 0.6, "2": 0.0},
                    "2": {"0": 1.0, "1": 0.7, "2": 0.0}}},
    "asr_overall": {"0": {"0": 0.95, "1": 0.4, "2": 0.0}, "1": {"0": 0.97, "1": 0.5, "2": 0.02},
                     "2": {"0": 1.0, "1": 0.6, "2": 0.05}},
    "utility": {"0": 0.70, "1": 0.62, "2": 0.55}, "frr": {"0": 0.0, "1": 0.03, "2": 0.08},
    "defense_level_stacks": {"0": "none", "1": "D1+D2+D4+D6", "2": "D1+D2+D3+D4+D5+D6+D7+D9+D10+D11"},
}

def test_ladder_table_md_contains_levels():
    from ragguard.report import ladder_table_md
    md = ladder_table_md(_LADDER)
    for s in ["L0", "L1", "L2", "D0", "D1", "D2"]:
        assert s in md
    assert "0.70" in md or "0.7" in md          # a utility figure
    assert "A9" in md                            # per-family row

def test_ladder_heatmap_writes_png(tmp_path):
    pytest.importorskip("matplotlib")
    from ragguard.report import ladder_heatmap
    p = ladder_heatmap(_LADDER, tmp_path / "ladder.png")
    import os
    assert os.path.exists(p) and os.path.getsize(p) > 0
