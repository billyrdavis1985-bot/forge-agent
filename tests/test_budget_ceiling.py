"""Budget ceiling test: a session can never push cumulative spend past the
daily cap (the reviewer's $1.90 + $0.50 -> $2.40 overshoot scenario)."""
import pytest

def effective_cap(session_cap, daily_cap, spent):
    return max(0.0, min(session_cap, daily_cap - spent))

def test_reviewer_overshoot_scenario():
    # spent 1.90, daily 2.00, session 0.50 -> effective must be ~0.10, not 0.50
    assert effective_cap(0.50, 2.00, 1.90) == pytest.approx(0.10)

def test_full_session_when_budget_ample():
    assert effective_cap(0.50, 2.00, 0.10) == pytest.approx(0.50)

def test_zero_when_over_daily():
    assert effective_cap(0.50, 2.00, 2.30) == 0.0

def test_never_exceeds_daily():
    for spent in (0.0, 0.5, 1.0, 1.75, 1.99, 2.0):
        assert spent + effective_cap(0.50, 2.00, spent) <= 2.00 + 1e-9
