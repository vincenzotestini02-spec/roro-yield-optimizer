"""Linear, simplified stability model: moments, closed-form minimum ballast, residual heel/trim.

Signs: M_T > 0 = starboard-heavy (ballast goes to the port tank);
M_L > 0 = bow-heavy (ballast goes to the aft tank).
"""

from __future__ import annotations

import math
from dataclasses import dataclass
from typing import Iterable

from .models import Booking, Slot, Stability, Vessel


@dataclass(frozen=True)
class Ballast:
    port_t: float = 0.0
    stbd_t: float = 0.0
    fore_t: float = 0.0
    aft_t: float = 0.0

    @property
    def total_t(self) -> float:
        return self.port_t + self.stbd_t + self.fore_t + self.aft_t


def moments(loads: Iterable[tuple[Booking, Slot]], vessel: Vessel) -> tuple[float, float]:
    """Return (M_T, M_L) in t.m: weight x transverse offset, weight x longitudinal position."""
    m_t = m_l = 0.0
    for booking, slot in loads:
        lane = vessel.lane(slot.lane_id)
        m_t += booking.weight_t * lane.y_m
        m_l += booking.weight_t * lane.zone_x_m(slot.zone)
    return m_t, m_l


def required_ballast(m_t: float, m_l: float, stab: Stability) -> Ballast:
    excess_t = max(0.0, abs(m_t) - stab.heel_limit_tm) / stab.side_tank_arm_m
    excess_l = max(0.0, abs(m_l) - stab.trim_limit_tm) / stab.end_tank_arm_m
    return Ballast(
        port_t=excess_t if m_t > 0 else 0.0,
        stbd_t=excess_t if m_t < 0 else 0.0,
        aft_t=excess_l if m_l > 0 else 0.0,
        fore_t=excess_l if m_l < 0 else 0.0,
    )


def ballast_fits(b: Ballast, stab: Stability) -> bool:
    return max(b.port_t, b.stbd_t, b.fore_t, b.aft_t) <= stab.tank_cap_t


def residual_heel_deg(m_t: float, b: Ballast, stab: Stability) -> float:
    net = m_t - (b.port_t - b.stbd_t) * stab.side_tank_arm_m
    return math.degrees(math.atan(net / (stab.displacement_t * stab.gm_m)))


def residual_trim_m(m_l: float, b: Ballast, stab: Stability) -> float:
    net = m_l - (b.aft_t - b.fore_t) * stab.end_tank_arm_m
    return net / (stab.mtc_tm_per_cm * 100)
