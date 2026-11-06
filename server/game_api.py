"""The game: the browser keeps seed and decisions, the server rebuilds the session from them."""

from __future__ import annotations

from dataclasses import replace
from functools import lru_cache

from fastapi import APIRouter, HTTPException

from roro_yield.advisor import advise
from roro_yield.game import GameSession
from roro_yield.simulator import ScenarioParams, expected_contract_m, generate_scenario
from server import jobs_api
from server.config import ADVISOR_K, GAME_PARAMS
from server.schemas import Decision, GameRequest
from server.serialize import booking_out, deck_out, parse_slot, verdict_out

router = APIRouter(prefix="/api/game")
EXPECTED_SAMPLES = 40  # for the contract-floor warning only


class InvalidDecision(Exception):
    """A decision that does not fit the game so far. The message is shown to the user."""


def game_params(seed: int) -> ScenarioParams:
    return replace(GAME_PARAMS, seed=seed)


def replay(seed: int, decisions: list[Decision]) -> GameSession:
    params = game_params(seed)
    session = GameSession(generate_scenario(params), params)
    for d in decisions:
        if session.is_finished:
            raise InvalidDecision("The game is finished: no more decisions.")
        if d.booking_id != session.current.id:
            raise InvalidDecision(f"{d.booking_id} is not the current request.")
        if d.action == "reject":
            session.reject(session.index)
            continue
        try:
            slot = None if d.slot is None else parse_slot(d.slot)
        except ValueError:
            raise InvalidDecision(f"{d.slot} is not a deck zone.") from None
        if slot is not None and slot not in session.deck.remaining_m:
            raise InvalidDecision(f"{d.slot} is not a deck zone.")
        reason = session.accept(session.index, slot)
        if reason is not None:
            raise InvalidDecision(reason)
    return session


@lru_cache(maxsize=4096)
def _expected_contract_m(seed: int, after_frac: float, remaining: int) -> float:
    return expected_contract_m(game_params(seed), after_frac, remaining, n_samples=EXPECTED_SAMPLES)


def state_out(seed: int, session: GameSession) -> dict:
    current = session.current
    if current is not None:  # the session keeps this per index; fill it to keep each click fast
        remaining = len(session.queue) - session.index - 1
        session._expected_cache[session.index] = _expected_contract_m(seed, current.arrival_frac, remaining)
    slots = [] if current is None else session.deck.feasible_slots(current)
    best = None if current is None else session.deck.best_slot(current)
    return {
        "seed": seed,
        "index": session.index,
        "n_total": len(session.queue),
        "finished": session.is_finished,
        "current": None if current is None else booking_out(current),
        "past": [booking_out(b) for b in session.queue[:session.index]],
        "deck": deck_out(session.deck),
        "feasible_slots": [str(s) for s in slots],
        "best_slot": None if best is None else str(best),
        "cannot_load_reason": None if current is None else session.deck.why_not(current),
        "floor_at_risk": session.contract_floor_at_risk(),
        "contract_floor_m": session.scenario.contract_floor_m,
        "shortfall_penalty_per_m": session.scenario.shortfall_penalty_per_m,
    }


@router.post("/state")
def game_state(req: GameRequest) -> dict:
    return state_out(req.seed, replay(req.seed, req.decisions))


def decisions_key(decisions: list[Decision]) -> tuple:
    return tuple((d.booking_id, d.action, d.slot) for d in decisions)


@router.post("/verdict")
def game_verdict(req: GameRequest) -> dict:
    session = replay(req.seed, req.decisions)
    if session.is_finished:
        raise HTTPException(409, "The game is finished: no request to judge.")
    key = ("verdict", req.seed, decisions_key(req.decisions))
    return {"job_id": jobs_api.submit(key, advise, session.view_at_current(), ADVISOR_K, output=verdict_out)}
