import time
from dataclasses import replace

import pytest

from roro_yield.advisor import PolicyView, Verdict, advise
from roro_yield.deck import DeckState
from roro_yield.models import Booking, Lane, Scenario, Vessel
from roro_yield.simulator import ScenarioParams, generate_scenario


def view_from(scenario: Scenario, params: ScenarioParams, deck: DeckState, index: int) -> PolicyView:
    """The advisor's view at request `index`: past requests, the current one, a copy of the deck."""
    return PolicyView(
        params=params,
        vessel=scenario.vessel,
        commitment_m=scenario.contract_commitment_m,
        penalty_per_m=scenario.shortfall_penalty_per_m,
        deck=deck.copy(),
        history=tuple(scenario.bookings[:index]),
        current=scenario.bookings[index],
        index=index,
        n_total=len(scenario.bookings),
        seed=params.seed,
    )


def _bk(bid, segment="spot", rate=80.0, weight=10.0, length=13.6, frac=0.5, reefer=False, handling=0.0):
    return Booking(bid, 0, segment, "C", "semi_trailer", length, weight, reefer, rate, 0.0, handling, frac)


def test_information_set():
    params = ScenarioParams(seed=11)
    s1 = generate_scenario(params)
    other = generate_scenario(replace(params, seed=99))
    s2 = Scenario(s1.vessel, s1.bookings[:10] + other.bookings[10:], s1.contract_commitment_m,
                  s1.shortfall_penalty_per_m)
    assert s1.bookings[10:] != s2.bookings[10:]
    deck = DeckState(s1.vessel)
    for index in range(10):
        v1 = advise(view_from(s1, params, deck, index), k=4)
        v2 = advise(view_from(s2, params, deck, index), k=4)
        assert v1 == v2
        if v1.accept:
            deck.place(s1.bookings[index])


def test_infeasible_verdict():
    vessel = Vessel("V", "A → B", (Lane("L1", 70.0),), 5.0, 0, 0.5)  # 5 t deadweight
    s = Scenario(vessel, (_bk("B001", weight=10.0),), 0.0, 200.0)
    v = advise(view_from(s, ScenarioParams(), DeckState(vessel), 0))
    assert v == Verdict("B001", False, False, 0, 0, 0.0, "would exceed max deadweight")
    assert v.text == "Can't load: would exceed max deadweight"


def test_last_request():
    vessel = Vessel("V", "A → B", (Lane("L1", 70.0),), 1000.0, 0, 0.5)
    good = _bk("B001", rate=50.0, handling=100.0)  # margin 580
    bad = _bk("B001", rate=5.0, handling=100.0)  # margin -32
    for current, accept in ((good, True), (bad, False)):
        s = Scenario(vessel, (current,), 0.0, 200.0)
        v = advise(view_from(s, ScenarioParams(), DeckState(vessel), 0), k=5)
        assert v.feasible and v.accept is accept
        assert v.k == 5 and v.n_pays_off == (5 if accept else 0)
        assert v.expected_gain_eur == pytest.approx(current.margin, abs=1e-6)


def test_rejects_cheap_contract_early_when_spot_rich():
    params = ScenarioParams(spot_rate_multiplier=1.5, contract_floor_share=0.3, seed=5)
    vessel = generate_scenario(params).vessel
    deck = DeckState(vessel)
    history = []
    for i in range(40):  # 40 light contract semi-trailers: far above the 216 m floor, deck nearly full
        b = _bk(f"B{i + 1:03d}", "contract", rate=50.0, weight=10.0, frac=0.3 * i / 40)
        deck.place(b)
        history.append(b)
    current = _bk("B041", "contract", rate=45.0, weight=10.0, frac=0.3, handling=95.0)
    assert deck.why_not(current) is None and current.margin > 0
    view = PolicyView(params, vessel, 0.3 * vessel.total_lane_m, params.shortfall_penalty_per_m,
                      deck.copy(), tuple(history), current, 40, 100, params.seed)
    v = advise(view)
    assert v.feasible and not v.accept
    assert v.expected_gain_eur < 0
    assert v.text.startswith("Reject — pays off in only ")


def test_deterministic():
    params = ScenarioParams(seed=3)
    s = generate_scenario(params)
    deck = DeckState(s.vessel)
    for b in s.bookings[:5]:
        deck.place(b)
    assert advise(view_from(s, params, deck, 5), k=6) == advise(view_from(s, params, deck, 5), k=6)


def test_verdict_text():
    assert Verdict("B1", True, True, 16, 20, 420.0, None).text == \
        "Accept — pays off in 16 of 20 futures, expected gain +€420"
    assert Verdict("B1", False, True, 4, 20, -310.0, None).text == \
        "Reject — pays off in only 4 of 20 futures, expected gain −€310"


@pytest.mark.slow
def test_verdict_time():
    params = ScenarioParams()
    s = generate_scenario(params)
    deck = DeckState(s.vessel)
    for b in s.bookings[:10]:
        if deck.why_not(b) is None:
            deck.place(b)
    view = view_from(s, params, deck, 10)
    start = time.perf_counter()
    v = advise(view, k=20)
    elapsed = time.perf_counter() - start
    print(f"verdict time {elapsed:.2f} s: {v.text}")
    assert v.k == 20
    assert elapsed < 3
