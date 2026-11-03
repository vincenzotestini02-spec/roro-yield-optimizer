from dataclasses import replace

import pytest

from roro_yield.models import DEFAULT_STABILITY, Booking, Lane, Slot, Vessel
from roro_yield.simulator import ScenarioParams, generate_scenario
from roro_yield.stability import (
    Ballast,
    ballast_fits,
    moments,
    required_ballast,
    residual_heel_deg,
    residual_trim_m,
)

STAB = DEFAULT_STABILITY
H, T = STAB.heel_limit_tm, STAB.trim_limit_tm


def test_zone_centres():
    lane = Lane("L1", 120)
    assert lane.zone_x_m(0) == -45
    assert lane.zone_x_m(3) == 45
    assert lane.zone_length_m == 30


@pytest.mark.parametrize("n", [1, 5, 6])
def test_lane_offsets_symmetric(n):
    lanes = generate_scenario(ScenarioParams(n_lanes=n)).vessel.lanes
    assert sum(lane.y_m for lane in lanes) == pytest.approx(0)
    if n == 1:
        assert lanes[0].y_m == 0
    if n == 5:
        assert lanes[2].y_m == 0
    if n > 1:
        assert lanes[0].y_m == min(lane.y_m for lane in lanes) < 0


def test_no_ballast_within_limits():
    assert required_ballast(0.5 * H, -0.5 * T, STAB).total_t == 0


def test_ballast_closed_form():
    stab = replace(STAB, side_tank_arm_m=9.0, end_tank_arm_m=50.0)
    m_t = stab.heel_limit_tm + 900
    b = required_ballast(m_t, 0, stab)
    assert b.port_t == pytest.approx(100) and b.stbd_t == 0
    assert residual_heel_deg(m_t, b, stab) == pytest.approx(stab.max_heel_deg, abs=1e-9)
    m_l = -(stab.trim_limit_tm + 500)
    b = required_ballast(0, m_l, stab)
    assert b.fore_t == pytest.approx(10) and b.aft_t == 0
    assert residual_trim_m(m_l, b, stab) == pytest.approx(-stab.max_trim_m)


def test_ballast_fits_cap():
    assert ballast_fits(Ballast(port_t=STAB.tank_cap_t), STAB)
    assert not ballast_fits(Ballast(aft_t=STAB.tank_cap_t + 1), STAB)


def test_moments_signs():
    v = Vessel("V", "r", (Lane("L1", 120, -3.2), Lane("L2", 120, 3.2)), 1000, 4, 0.5)
    b = Booking("B1", 0, "spot", "h", "mafi", 12.2, 40.0, False, 90.0, 0.0, 0.0)
    m_t, m_l = moments([(b, Slot("L2", 3))], v)
    assert m_t == pytest.approx(40 * 3.2) and m_l == pytest.approx(40 * 45)


def test_default_scenario_unchanged_floor():
    for seed in range(1, 11):
        s = generate_scenario(ScenarioParams(seed=seed))
        contract_m = sum(b.length_m for b in s.bookings if b.segment == "contract")
        assert s.contract_floor_m == min(0.35 * 720, contract_m)


def test_ballast_starboard_and_aft_branches():
    stab = replace(STAB, side_tank_arm_m=9.0, end_tank_arm_m=50.0)
    m_t = -(stab.heel_limit_tm + 900)  # port-heavy -> starboard tank
    b = required_ballast(m_t, 0, stab)
    assert b.stbd_t == pytest.approx(100) and b.port_t == 0
    assert residual_heel_deg(m_t, b, stab) == pytest.approx(-stab.max_heel_deg, abs=1e-9)
    m_l = stab.trim_limit_tm + 500  # bow-heavy -> aft tank
    b = required_ballast(0, m_l, stab)
    assert b.aft_t == pytest.approx(10) and b.fore_t == 0
    assert residual_trim_m(m_l, b, stab) == pytest.approx(stab.max_trim_m)
