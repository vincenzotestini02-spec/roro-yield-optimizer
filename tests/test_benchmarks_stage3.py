import json
from pathlib import Path

from benchmarks.decision_rule import choose, criteria
from roro_yield import advisor

RESULTS = Path(__file__).resolve().parent.parent / "benchmarks" / "results"


def level(pct):
    return {"smart_vs_fcfs_pct": pct}


def test_criteria_are_computed_from_the_levels():
    assert all(criteria({40: level(-0.4), 60: level(6.0), 90: level(14.0)}).values())
    assert not criteria({40: level(-0.6), 60: level(6.0), 90: level(14.0)})["loss_at_40_at_most_0_5pct"]


def test_choose_prefers_pairs_within_the_loss_limit():
    results = {(0.5, 0.8): {40: level(-1.0), 60: level(9.0), 90: level(15.0)},
               (0.6, 0.9): {40: level(-0.2), 60: level(6.0), 90: level(13.5)}}
    assert choose(results) == (0.6, 0.9)


def test_published_results_have_the_three_levels():
    data = json.loads((RESULTS / "decision_rule.json").read_text(encoding="utf-8"))
    assert [lv["n_requests"] for lv in data["levels"]] == [40, 60, 90]
    assert all(lv["n_sailings"] == 30 for lv in data["levels"])
    assert set(data["criteria"]) == {"loss_at_40_at_most_0_5pct", "gain_at_60_at_least_5pct", "gain_at_90_at_least_13pct"}


def test_advisor_uses_the_calibrated_thresholds():
    data = json.loads((RESULTS / "decision_calibration.json").read_text(encoding="utf-8"))
    assert [advisor.ACCEPT_SHARE, advisor.REJECT_SHARE] == data["chosen"]


def test_ev_experiment_is_published():
    data = json.loads((RESULTS / "ev_test.json").read_text(encoding="utf-8"))
    assert data["summary"]["sailings"] == 10 and 0 <= data["summary"]["agreement"] <= 1


def test_the_expected_value_rule_caps_each_future_booking():
    from dataclasses import replace

    from benchmarks.ev_test import ev_gain
    from roro_yield.advisor import advise, view_for
    from roro_yield.deck import DeckState
    from roro_yield.simulator import ScenarioParams, generate_scenario

    params = replace(ScenarioParams(), n_requests=60, seed=1)
    s = generate_scenario(params)
    deck = DeckState(s.vessel)
    agree = 0
    for index in range(6):
        sampled = advise(view_for(s, params, deck, index), k=10, suggest_moves=False)
        gain = ev_gain(view_for(s, params, deck, index), k=10)
        agree += int(sampled.accept == (gain is not None and gain > 1e-9))
        if sampled.accept:
            deck.place(s.bookings[index])
    assert agree >= 4  # a per-slot cap made the rule reject everything
