from fastapi.testclient import TestClient

from roro_yield.simulator import ScenarioParams
from server.config import GAME_PARAMS
from server.main import create_app


def test_health():
    assert TestClient(create_app()).get("/api/health").json() == {"status": "ok"}


def test_game_params_are_five_lanes_of_120():
    assert GAME_PARAMS.n_lanes == 5 and GAME_PARAMS.lane_length_m == 120.0
    assert ScenarioParams().n_lanes == 6  # the engine default stays
