from app.deck_chart import deck_figure
from roro_yield.fcfs import solve_fcfs
from roro_yield.models import Plan
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
    l1 = sorted((sh for sh in _shapes(fig, "unit:") if sh.name.endswith("@L1")), key=lambda sh: sh.x0)
    assert l1[0].x0 == 0
    assert all(sh.x1 <= 120 for sh in l1)
    assert all(a.x1 <= b.x0 for a, b in zip(l1, l1[1:]))


def test_hover_traces_have_one_point_per_unit_and_a_legend():
    s = generate_scenario(ScenarioParams(seed=4))
    plan = solve_fcfs(s)
    fig = deck_figure(s, plan)
    assert sum(len(t.x) for t in fig.data) == len(plan.accepted_ids)
    assert {t.name for t in fig.data} <= {"Contract", "Spot"}


def test_empty_plan_renders():
    s = generate_scenario(ScenarioParams(seed=4))
    fig = deck_figure(s, Plan("x", {}, []))
    assert len(_shapes(fig, "unit:")) == 0
    assert len(_shapes(fig, "lane:")) == 6
