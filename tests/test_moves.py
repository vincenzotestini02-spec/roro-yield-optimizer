import pytest

from roro_yield.deck import DeckState
from roro_yield.fcfs import solve_fcfs
from roro_yield.game import GameSession
from roro_yield.kpis import MOVE_COST_EUR, evaluate, objective
from roro_yield.models import Plan, Slot
from roro_yield.simulator import ScenarioParams, generate_scenario

FCFS_V2 = {1: 43657.950999999994, 2: 36704.60857438943, 3: 37236.992}


def game(seed=3):
    params = ScenarioParams(seed=seed)
    return GameSession(generate_scenario(params), params)


def test_remove_restores_the_deck():
    s = generate_scenario(ScenarioParams(seed=3))
    deck = DeckState(s.vessel)
    before = (dict(deck.remaining_m), deck.weight_t, deck.plugs_used, deck.moments)
    b = s.bookings[0]
    deck.place(b)
    removed, _ = deck.remove(b.id)
    assert removed == b and b.id not in deck.loads
    assert deck.remaining_m == pytest.approx(before[0]) and deck.weight_t == pytest.approx(before[1])
    assert deck.plugs_used == before[2] and deck.moments == pytest.approx(before[3])


def test_move_changes_the_slot_and_counts():
    g = game()
    g.accept(0)
    bid, slot = next(iter(g.deck.placements.items()))
    target = next(s for s in g.deck.feasible_slots(g.scenario.booking(bid)) if s != slot)
    assert g.move(bid, target) is None
    assert g.deck.placements[bid] == target and g.moves == 1 and g.to_plan().moves == 1


def test_failed_move_leaves_the_game_unchanged():
    g = game()
    g.accept(0)
    bid, slot = next(iter(g.deck.placements.items()))
    before = dict(g.deck.remaining_m)
    reason = g.move(bid, Slot("L9", 0))
    assert reason and g.deck.placements[bid] == slot and g.moves == 0
    assert g.deck.remaining_m == before


def test_move_of_a_unit_not_on_deck_is_refused():
    assert game().move("B001", Slot("L1", 0))


def test_moves_cost_80_each_in_the_objective():
    s = generate_scenario(ScenarioParams(seed=3))
    plan = solve_fcfs(s)
    moved = Plan(plan.method, plan.placements, plan.rejected, moves=2)
    assert MOVE_COST_EUR == 80.0
    assert objective(s, moved) == pytest.approx(objective(s, plan) - 160)
    assert evaluate(s, moved).moves == 2 and evaluate(s, moved).move_cost == 160


def test_no_moves_keeps_previous_scores():
    for seed, value in FCFS_V2.items():
        s = generate_scenario(ScenarioParams(seed=seed))
        assert objective(s, solve_fcfs(s)) == pytest.approx(value)
