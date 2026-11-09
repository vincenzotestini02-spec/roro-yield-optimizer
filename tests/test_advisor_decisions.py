import numpy as np
import pytest

from roro_yield.advisor import ACCEPT_SHARE, REJECT_SHARE, Verdict, advise, decide, view_for
from roro_yield.deck import DeckState
from roro_yield.simulator import ScenarioParams, generate_scenario


def gains(positive: int, k: int = 20, size: float = 100.0) -> list[float]:
    return [size] * positive + [-size] * (k - positive)


def test_initial_thresholds():
    assert (ACCEPT_SHARE, REJECT_SHARE) == (0.6, 0.8)


def test_clear_majority_accepts():
    assert decide(gains(15)) == "accept"


def test_clear_majority_rejects():
    assert decide(gains(3)) == "reject"


def test_split_futures_are_your_call():
    assert decide([110.0] * 11 + [-100.0] * 9) == "your_call"  # mean > 0 but only 55% favourable


def test_negative_mean_without_clear_majority_is_your_call():
    assert decide(gains(6)) == "your_call"  # 70% unfavourable < 80%


def test_your_call_counts_as_accept():
    v = Verdict("B1", True, 11, 20, 20.0, decision="your_call")
    assert v.accept is True
    assert Verdict("B1", True, 3, 20, -80.0, decision="reject").accept is False


def test_range_is_10th_to_90th_percentile():
    s = generate_scenario(ScenarioParams(seed=3))
    v = advise(view_for(s, ScenarioParams(seed=3), DeckState(s.vessel), 10), k=10)
    assert v.gain_low <= v.expected_gain_eur <= v.gain_high


def test_text_names_the_decision_and_the_range():
    v = Verdict("B1", True, 11, 20, 20.0, decision="your_call", gain_low=-300.0, gain_high=380.0)
    assert v.text == "Your call — pays off in 11 of 20 futures, expected gain +€20 (range −€300 to +€380)"


def test_cannot_load_is_not_accept():
    v = Verdict("B1", False, 0, 0, 0.0, reason="no lane has enough space left", decision="reject")
    assert v.accept is False and v.text.startswith("Can't load")


def test_advise_fills_the_new_fields():
    s = generate_scenario(ScenarioParams(seed=4))
    v = advise(view_for(s, ScenarioParams(seed=4), DeckState(s.vessel), 5), k=10)
    assert v.decision in ("accept", "reject", "your_call")
    assert v.pays_off_share == pytest.approx(v.n_pays_off / v.k)
    assert np.isfinite(v.gain_low) and np.isfinite(v.gain_high)
