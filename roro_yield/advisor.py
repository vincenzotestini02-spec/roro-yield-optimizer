"""Smart planner without foresight: one accept/reject verdict from sampled futures (spec §5.3).

The advisor sees only a `PolicyView`: the current request, every past request (accepted or
not), a copy of its own deck, "request k of n" and the demand distribution (`ScenarioParams`).
It never receives a `Scenario`, so it cannot read the bookings still to come. The boundary is
structural: the view's `params` carry a neutral seed (so `ScenarioParams` cannot rebuild this
sailing), and the advisor's own sampling seed is a hash of the game seed. The hash only keeps the
two seeds apart in code: game seeds are small, so it is separation, not secrecy.

For each of K sampled futures it solves two LP relaxations of the §5.2 model with the deck's
loads fixed: (a) the current unit loaded where the auto-placement rule puts it, (b) rejected.
gain_f = V_a − V_b; accept iff the mean gain is positive (and the unit can be loaded).
"""

from __future__ import annotations

import hashlib
from dataclasses import dataclass, replace
from typing import Callable

import numpy as np
import pulp

from .deck import DeckState
from .models import Booking, Plan, Scenario, Vessel
from .optimizer import build_model
from .simulator import ScenarioParams, sample_future

SMART_LABEL = "Smart planner (no foresight)"
ADVISOR_LABEL = SMART_LABEL
NEUTRAL_SEED = 0  # the seed the advisor's ScenarioParams carry: never the game's own


def advisor_rng_seed(game_seed: int) -> int:
    """A stable seed for the advisor's sampling, hashed from the game seed.

    Verdicts stay deterministic per game, and the advisor never handles the game seed itself.
    This is separation, not secrecy: the seed space is small enough to enumerate.
    """
    digest = hashlib.sha256(f"advisor:{game_seed}".encode()).digest()
    return int.from_bytes(digest[:8], "big")


@dataclass(frozen=True)
class PolicyView:
    params: ScenarioParams  # the demand distribution, with seed = NEUTRAL_SEED
    vessel: Vessel
    commitment_m: float
    penalty_per_m: float
    deck: DeckState  # a copy: the advisor may not change the caller's deck
    history: tuple[Booking, ...]  # every past request, accepted or not
    current: Booking
    index: int  # 0-based position of `current` among the n_total requests
    n_total: int
    rng_seed: int  # advisor_rng_seed(game seed): for sampling futures only


@dataclass(frozen=True)
class Verdict:
    booking_id: str
    accept: bool
    feasible: bool
    n_pays_off: int
    k: int
    expected_gain_eur: float
    reason: str | None = None

    @property
    def text(self) -> str:
        if not self.feasible:
            return f"Can't load: {self.reason}"
        sign = "+" if self.expected_gain_eur >= 0 else "−"
        gain = f"expected gain {sign}€{abs(self.expected_gain_eur):,.0f}"
        if self.accept:
            return f"Accept — pays off in {self.n_pays_off} of {self.k} futures, {gain}"
        return f"Reject — pays off in only {self.n_pays_off} of {self.k} futures, {gain}"


def _contract_m(bookings) -> float:
    return sum(b.length_m for b in bookings if b.segment == "contract")


def _solve_value(prob: pulp.LpProblem) -> float:
    prob.solve(pulp.HiGHS(msg=False))
    if pulp.LpStatus[prob.status] != "Optimal":
        raise RuntimeError(f"advisor LP not optimal: {pulp.LpStatus[prob.status]}")
    return float(pulp.value(prob.objective))


def advise(view: PolicyView, k: int = 20) -> Verdict:
    current, deck = view.current, view.deck.copy()  # defensive: never touch the caller's deck
    reason = deck.why_not(current)
    if reason is not None:
        return Verdict(current.id, False, False, 0, 0, 0.0, reason)

    slot = deck.best_slot(current)
    assert slot is not None, "why_not passed but best_slot found no slot"
    rng = np.random.default_rng([view.rng_seed, view.index])
    assert view.index < view.n_total, "request index beyond n_total"
    n_remaining = view.n_total - view.index - 1
    requested_m = _contract_m(view.history) + _contract_m([current])

    gains = []
    for _ in range(k):
        future = sample_future(view.params, current.arrival_frac, n_remaining, rng)
        floor_m = min(view.commitment_m, requested_m + _contract_m(future))
        model = build_model(view.vessel, future, floor_m, view.penalty_per_m,
                            relaxed=True, deck=deck, forced=(current, slot))
        values = []
        for loaded in (1, 0):  # (a) current placed at its auto slot, (b) current rejected
            model.forced.lowBound = model.forced.upBound = loaded
            values.append(_solve_value(model.prob))
        gains.append(values[0] - values[1])

    mean_gain = float(np.mean(gains)) if gains else 0.0
    n_pays_off = int(sum(g > 1e-9 for g in gains))
    return Verdict(current.id, mean_gain > 1e-9, True, n_pays_off, k, mean_gain, None)


def view_for(scenario: Scenario, params: ScenarioParams, deck: DeckState, index: int) -> PolicyView:
    """The advisor's view at request `index`: past requests, the current one, a copy of the deck."""
    return PolicyView(
        params=replace(params, seed=NEUTRAL_SEED),
        vessel=scenario.vessel,
        commitment_m=scenario.contract_commitment_m,
        penalty_per_m=scenario.shortfall_penalty_per_m,
        deck=deck.copy(),
        history=tuple(scenario.bookings[:index]),
        current=scenario.bookings[index],
        index=index,
        n_total=len(scenario.bookings),
        rng_seed=advisor_rng_seed(params.seed),
    )


def smart_plan(
    scenario: Scenario,
    params: ScenarioParams,
    k: int = 20,
    on_progress: Callable[[int, int], None] | None = None,
) -> tuple[Plan, list[Verdict]]:
    """Play every request in arrival order: accept per verdict, load at the auto slot."""
    deck = DeckState(scenario.vessel)
    n = len(scenario.bookings)
    rejected: list[str] = []
    verdicts: list[Verdict] = []
    for index, booking in enumerate(scenario.bookings):
        verdict = advise(view_for(scenario, params, deck, index), k=k)
        verdicts.append(verdict)
        if verdict.accept:
            deck.place(booking)
        else:
            rejected.append(booking.id)
        if on_progress is not None:
            on_progress(index + 1, n)
    return Plan(SMART_LABEL, deck.placements, rejected), verdicts
