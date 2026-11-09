"""Vessel presets for the Lab: typical rounded figures we chose, never a named ship."""

from __future__ import annotations

from server.config import GAME_PARAMS

PRESET_NOTE = "Typical rounded figures, not a named ship."

PRESETS: dict[str, dict] = {
    "demo": {
        "label": "Demo ferry, 600 lane-m",
        "values": {
            "n_lanes": GAME_PARAMS.n_lanes, "lane_length_m": GAME_PARAMS.lane_length_m,
            "n_requests": GAME_PARAMS.n_requests, "max_dwt_t": GAME_PARAMS.max_dwt_t,
            "reefer_plugs": GAME_PARAMS.reefer_plugs, "displacement_t": GAME_PARAMS.displacement_t,
            "gm_m": GAME_PARAMS.gm_m, "mtc_tm_per_cm": GAME_PARAMS.mtc_tm_per_cm,
            "ballast_tank_cap_t": GAME_PARAMS.ballast_tank_cap_t,
        },
    },
    "ropax": {
        "label": "RoPax freight deck, about 1,800 lane-m",
        "values": {
            "n_lanes": 12, "lane_length_m": 150.0, "n_requests": 140, "max_dwt_t": 3500.0,
            "reefer_plugs": 30, "displacement_t": 20000.0, "gm_m": 2.0, "mtc_tm_per_cm": 250.0,
            "ballast_tank_cap_t": 600.0,
        },
    },
    "shortsea": {
        "label": "Short-sea RoRo, about 2,500 lane-m",
        "values": {
            "n_lanes": 16, "lane_length_m": 156.0, "n_requests": 190, "max_dwt_t": 5000.0,
            "reefer_plugs": 40, "displacement_t": 26000.0, "gm_m": 2.0, "mtc_tm_per_cm": 320.0,
            "ballast_tank_cap_t": 600.0,
        },
    },
}
