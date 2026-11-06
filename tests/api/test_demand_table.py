import pytest

from benchmarks.demand_table import summarize


def row(fcfs, smart, optimal, ratio=1.0):
    return {"seed": 1, "fcfs": fcfs, "smart": smart, "optimal": optimal, "demand_ratio": ratio}


def test_summary_is_computed_from_sailings():
    level = summarize("low", 35, [row(100, 90, 110), row(100, 120, 130)])
    assert level["lost_to_fcfs"] == 1 and level["smart_vs_fcfs_pct"] == pytest.approx(5.0)
    assert level["n_sailings"] == 2 and level["smart"] == 105 and level["optimal"] == 120


def test_published_table_has_the_three_levels(client):
    t = client.get("/api/demand-table").json()
    assert [(x["label"], x["n_requests"]) for x in t["levels"]] == [("low", 35), ("normal", 50), ("high", 60)]
    assert all(x["n_sailings"] == 30 for x in t["levels"])
