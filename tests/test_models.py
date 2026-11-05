import pytest

from roro_yield.models import UNIT_TYPES, Booking, Lane, Plan, Scenario, Slot, Vessel


def make_vessel():
    return Vessel("V", "A → B", tuple(Lane(f"L{i}", 120) for i in range(1, 7)), 1100, 12, 0.5)


def test_booking_revenue_and_margin():
    b = Booking("B1", 0, "spot", "Haulier A", "semi_trailer", 13.6, 20.0, True, 100.0, 150.0, 110.0)
    assert b.revenue == pytest.approx(13.6 * 100 + 150)
    assert b.margin == pytest.approx(1360 + 150 - 110)
    assert b.effective_length(0.5) == pytest.approx(14.1)


def test_non_reefer_gets_no_fee():
    b = Booking("B2", 0, "contract", "KA", "mafi", 12.2, 40.0, False, 50.0, 80.0, 140.0)
    assert b.revenue == pytest.approx(610.0)


def test_vessel_total_lane_m():
    assert make_vessel().total_lane_m == 720


def test_unit_types_match_spec_lengths():
    assert UNIT_TYPES["semi_trailer"].length_m == 13.6
    assert UNIT_TYPES["accompanied_truck"].length_m == 16.5
    assert UNIT_TYPES["mafi"].length_m == 12.2
    assert not UNIT_TYPES["van"].can_be_reefer


def test_scenario_lookup_and_plan_accepted_ids():
    b = Booking("B1", 0, "spot", "H", "van", 6.5, 3.0, False, 90.0, 0.0, 84.5)
    s = Scenario(make_vessel(), (b,), 0.0, 200.0)
    assert s.booking("B1") is b
    plan = Plan("You", {"B1": Slot("L1", 0)}, [])
    assert plan.accepted_ids == ["B1"]


def test_slot_str_and_vessel_slots():
    assert str(Slot("L3", 2)) == "L3-Z2"
    v = make_vessel()
    assert len(v.slots) == 24
    assert v.lane("L2").id == "L2"


def test_scenario_floor_capped_by_requested_contract_metres():
    b = Booking("B1", 0, "contract", "KA", "van", 6.5, 3.0, False, 50.0, 0.0, 84.5)
    s = Scenario(make_vessel(), (b,), 252.0, 200.0)
    assert s.contract_floor_m == 6.5
