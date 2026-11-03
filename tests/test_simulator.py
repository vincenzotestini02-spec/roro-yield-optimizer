from statistics import mean

from roro_yield.models import UNIT_TYPES
from roro_yield.simulator import ScenarioParams, generate_scenario


def test_same_seed_same_scenario():
    assert generate_scenario(ScenarioParams(seed=7)) == generate_scenario(ScenarioParams(seed=7))


def test_different_seed_differs():
    assert generate_scenario(ScenarioParams(seed=1)).bookings != generate_scenario(ScenarioParams(seed=2)).bookings


def test_counts_shares_and_ids():
    s = generate_scenario(ScenarioParams())
    assert len(s.bookings) == 60
    n_contract = sum(b.segment == "contract" for b in s.bookings)
    assert abs(n_contract - 0.45 * 60) <= 10
    assert [b.arrival for b in s.bookings] == list(range(60))
    assert s.bookings[0].id == "B001"
    assert [lane.id for lane in s.vessel.lanes] == [f"L{i}" for i in range(1, 7)]
    assert s.vessel.total_lane_m == 720


def test_values_within_pinned_ranges():
    for seed in range(5):
        for b in generate_scenario(ScenarioParams(seed=seed)).bookings:
            ut = UNIT_TYPES[b.unit_type]
            assert b.length_m == ut.length_m
            assert ut.weight_range_t[0] <= b.weight_t <= ut.weight_range_t[1]
            assert not b.is_reefer or ut.can_be_reefer
            if b.segment == "contract":
                assert 45 <= b.rate_per_m <= 60
                assert b.customer in {"Nordfreight", "Baltic Logistics", "Humber Forwarding", "Jutland Cargo"}
            else:
                assert 75 <= b.rate_per_m <= 110 * 1.15
                assert b.customer.startswith("Spot haulier #")
            assert b.handling_cost == 80 + 1.5 * b.weight_t


def test_contracts_arrive_earlier_on_average():
    s = generate_scenario(ScenarioParams())
    contract = [b.arrival for b in s.bookings if b.segment == "contract"]
    spot = [b.arrival for b in s.bookings if b.segment == "spot"]
    assert mean(contract) < mean(spot)


def test_contract_floor_is_share_of_capacity():
    s = generate_scenario(ScenarioParams())
    contract_m = sum(b.length_m for b in s.bookings if b.segment == "contract")
    assert s.contract_floor_m == min(0.35 * 720, contract_m)
    assert s.shortfall_penalty_per_m == 200


def test_no_contracts_means_zero_floor():
    s = generate_scenario(ScenarioParams(contract_share=0.0))
    assert all(b.segment == "spot" for b in s.bookings)
    assert s.contract_floor_m == 0


def test_demand_exceeds_capacity_by_default():
    s = generate_scenario(ScenarioParams())
    assert sum(b.effective_length(0.5) for b in s.bookings) > 720


def test_spot_rate_multiplier_scales_spot_rates():
    base = generate_scenario(ScenarioParams(seed=3))
    high = generate_scenario(ScenarioParams(seed=3, spot_rate_multiplier=1.5))
    for a, b in zip(base.bookings, high.bookings):
        if a.segment == "spot":
            assert b.rate_per_m == a.rate_per_m * 1.5


def test_arrival_frac_sorted_and_stability_from_params():
    s = generate_scenario(ScenarioParams(max_heel_deg=1.0, ballast_tank_cap_t=50.0, lane_length_m=100.0))
    fracs = [b.arrival_frac for b in s.bookings]
    assert fracs == sorted(fracs) and all(0 <= f <= 1 for f in fracs)
    st = s.vessel.stability
    assert (st.max_heel_deg, st.tank_cap_t, st.end_tank_arm_m) == (1.0, 50.0, 40.0)
