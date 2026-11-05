from app.deck_chart import deck_figure
from app.stability_view import ship_figure
from roro_yield.fcfs import solve_fcfs
from roro_yield.models import ZONES, Plan, Slot
from roro_yield.stability import Ballast
from roro_yield.simulator import ScenarioParams, generate_scenario


def _shapes(fig, prefix):
    return [s for s in fig.layout.shapes if (s.name or "").startswith(prefix)]


def test_one_shape_per_lane_and_per_accepted_unit():
    s = generate_scenario(ScenarioParams(seed=4))
    plan = solve_fcfs(s)
    fig = deck_figure(s, plan, title="FCFS")
    assert len(_shapes(fig, "lane:")) == 6
    assert len(_shapes(fig, "unit:")) == len(plan.accepted_ids)
    assert fig.layout.title.text == "FCFS"


def test_units_sit_inside_their_lane_in_loading_order():
    s = generate_scenario(ScenarioParams(seed=4))
    plan = solve_fcfs(s)
    fig = deck_figure(s, plan)
    zl = s.vessel.lane("L1").zone_length_m
    for z in range(ZONES):
        units = sorted((sh for sh in _shapes(fig, "unit:") if sh.name.endswith(f"@L1-Z{z}")), key=lambda sh: sh.x0)
        if not units:
            continue
        assert units[0].x0 == z * zl  # stacked from the zone's stern edge
        assert all(a.x1 <= b.x0 for a, b in zip(units, units[1:]))
    l1 = [sh for sh in _shapes(fig, "unit:") if "@L1-" in sh.name]
    assert all(sh.x1 <= 120 + 1e-9 for sh in l1)


def test_hover_traces_have_one_point_per_unit_and_a_legend():
    s = generate_scenario(ScenarioParams(seed=4))
    plan = solve_fcfs(s)
    fig = deck_figure(s, plan)
    assert sum(len(t.x) for t in fig.data if t.hovertext is not None) == len(plan.accepted_ids)
    assert all(t.customdata is None for t in fig.data)
    assert {t.name for t in fig.data if t.showlegend is not False} == {"Contract", "Spot"}
    assert {t.name for t in fig.data} <= {"Contract", "Spot"}


def test_empty_plan_renders():
    s = generate_scenario(ScenarioParams(seed=4))
    fig = deck_figure(s, Plan("x", {}, []))
    assert len(_shapes(fig, "unit:")) == 0
    assert len(_shapes(fig, "lane:")) == 6


def test_zone_dividers_and_lane_labels():
    s = generate_scenario(ScenarioParams(seed=4))
    fig = deck_figure(s, Plan("x", {}, []))
    dividers = _shapes(fig, "zone:")
    assert len(dividers) == 6 * (ZONES - 1)
    assert all(d.line.dash == "dash" for d in dividers)
    labels = list(fig.layout.yaxis.ticktext)
    assert labels[0].startswith("L1") and labels[0].endswith("P")  # port on top
    assert labels[-1].startswith("L6") and labels[-1].endswith("S")
    assert [t for t in labels if t.endswith("P")] == labels[:3]
    # centreline lane (odd lane count) is labelled C
    s3 = generate_scenario(ScenarioParams(seed=4, n_lanes=3))
    labels3 = list(deck_figure(s3, Plan("x", {}, [])).layout.yaxis.ticktext)
    assert labels3 == ["L1 P", "L2 C", "L3 S"]


def test_highlight_markers_have_slot_customdata():
    s = generate_scenario(ScenarioParams(seed=4))
    hl = [Slot("L3", 2), Slot("L5", 0)]
    fig = deck_figure(s, Plan("x", {}, []), highlight=hl)
    traces = [t for t in fig.data if t.customdata is not None]
    assert len(traces) == 1
    assert list(traces[0].customdata) == ["L3-Z2", "L5-Z0"]
    assert len(traces[0].x) == 2
    assert len(_shapes(fig, "highlight:")) == 2
    assert all("45, 164, 78" in sh.fillcolor or "2da44e" in sh.fillcolor for sh in _shapes(fig, "highlight:"))
    assert traces[0].hoverinfo == "none"
    assert fig.data[-1] is traces[0]  # on top of the unit hover markers
    assert not [t for t in deck_figure(s, Plan("x", {}, [])).data if t.customdata is not None]


def _hull_x(fig, name):
    return list(next(t for t in fig.data if t.name == name).x)


def test_ship_figure_rotates_with_heel():
    flat = ship_figure(0.0, 0.0, Ballast())
    heeled = ship_figure(2.0, 0.0, Ballast())
    assert _hull_x(flat, "hull-astern") != _hull_x(heeled, "hull-astern")
    assert _hull_x(flat, "hull-side") == _hull_x(heeled, "hull-side")
    assert any("exaggerated ×4" in a.text for a in heeled.layout.annotations)


def test_ship_figure_tank_fill_proportional():
    half = ship_figure(0, 0, Ballast(port_t=150.0), tank_cap_t=300.0)
    full = ship_figure(0, 0, Ballast(port_t=300.0), tank_cap_t=300.0)
    def height(fig):
        ys = next(t for t in fig.data if t.name == "tank-port").y
        return max(ys) - min(ys)
    assert abs(height(half) * 2 - height(full)) < 1e-6
