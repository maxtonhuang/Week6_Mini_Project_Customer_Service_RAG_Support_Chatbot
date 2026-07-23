"""Unit tests for ragguard.fullrun helpers (no GPU / pipeline needed)."""
import pytest

from ragguard import orchestrator
from ragguard.fullrun import _pick_elapsed
from ragguard.orchestrator import RunCancelled, _stop


def test_resume_preserves_honest_elapsed():
    # A completed run resumed in ~0.4s must NOT clobber the real 527.9s full-run time.
    assert _pick_elapsed(0.4, 527.9, fresh=False) == 527.9


def test_first_full_run_records_its_own_time():
    # No prior results.json -> record this run's time as-is.
    assert _pick_elapsed(527.9, None, fresh=False) == 527.9
    assert _pick_elapsed(527.9, "n/a", fresh=False) == 527.9   # non-numeric prior ignored


def test_fresh_run_always_retimes():
    # 'Start fresh' recomputes everything, so its own (smaller/larger) time wins.
    assert _pick_elapsed(300.0, 527.9, fresh=True) == 300.0


def test_longer_partial_recompute_wins():
    # A partial resume that recomputed several phases and took longer than the recorded
    # time should update it (max keeps the largest observed full-compute duration).
    assert _pick_elapsed(600.0, 527.9, fresh=False) == 600.0


# ---- Stop button / cooperative cancellation ----

def test_stop_helper_raises_only_when_asked():
    _stop(None)            # no callback -> no-op
    _stop(lambda: False)   # not stopping -> no-op
    with pytest.raises(RunCancelled):
        _stop(lambda: True)


def test_two_stage_search_aborts_before_any_work():
    # should_stop=True must raise at the first loop boundary, before touching the (None) pipeline.
    with pytest.raises(RunCancelled):
        orchestrator.two_stage_search(None, [], None, [object()], [],
                                      screen_n=1, screen_benign=1, confirm_top=1,
                                      should_stop=lambda: True)


def test_matrix_aborts_before_any_work():
    with pytest.raises(RunCancelled):
        orchestrator.attack_defense_matrix(None, [], None, [object()], n=1,
                                           should_stop=lambda: True)
