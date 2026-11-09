"""Planner state builders shared by the planner API tests."""

from roro_yield.simulator import ScenarioParams, generate_scenario


def planner_state(n: int, seed: int = 7) -> dict:
    s = generate_scenario(ScenarioParams(n_lanes=5, n_requests=n, seed=seed))
    bookings = [{
        "booking_id": b.id, "customer": b.customer, "unit_type": b.unit_type, "length_m": b.length_m,
        "weight_t": b.weight_t, "discharge_port": "Immingham", "segment": b.segment, "is_reefer": b.is_reefer,
        "rate_per_m": round(b.rate_per_m, 2),
    } for b in s.bookings]
    return {"vessel": {"preset": "demo"}, "bookings": bookings, "placements": {}}
