import os
from pathlib import Path

os.environ["RORO_ADVISOR_K"] = "3"  # before the app (and app.state) is first imported

from streamlit.testing.v1 import AppTest  # noqa: E402

from roro_yield.models import Slot  # noqa: E402

APP = str(Path(__file__).resolve().parents[1] / "streamlit_app.py")


def _fresh():
    at = AppTest.from_file(APP, default_timeout=60)
    at.run()
    assert not at.exception
    return at


def test_landing_renders_game_with_disclaimer():
    at = _fresh()
    assert at.session_state["stage"] == "game"
    assert any("not DFDS data" in m.value for m in [*at.markdown, *at.caption])


def test_full_game_reaches_reveal_then_lab():
    at = _fresh()
    clicks = 0
    while at.session_state["stage"] == "game":
        key = "accept" if clicks % 2 == 0 else "reject"
        at.button(key=key).click().run()
        assert not at.exception
        clicks += 1
        assert clicks < 200, "game never finished"
    assert at.session_state["stage"] == "reveal"
    assert any("Best possible (perfect foresight)" in m.label for m in at.metric)
    at.button(key="to_lab").click().run()
    assert not at.exception
    assert at.session_state["stage"] == "lab"


def test_skip_to_lab_and_change_a_slider():
    at = _fresh()
    at.button(key="skip_to_lab").click().run()
    assert not at.exception
    assert at.session_state["stage"] == "lab"
    at.slider(key="lab_n_lanes").set_value(4).run()
    assert not at.exception


def test_game_starts_the_smart_job():
    at = _fresh()
    import app.state

    assert app.state.ADVISOR_K == 3
    jobs = at.session_state["jobs"]
    assert jobs.has(("smart", at.session_state["seed"]))


def test_manual_game_places_in_chosen_zone():
    at = _fresh()
    at.radio(key="placement_mode").set_value("manual").run()
    assert not at.exception
    game = at.session_state["game"]
    booking = game.current
    at.button(key="accept").click().run()
    assert not at.exception
    assert game.pending_index == 0
    feasible = game.deck.feasible_slots(booking)
    slot_keys = [b.key for b in at.button if b.key and b.key.startswith("slot_")]
    assert sorted(slot_keys) == sorted(f"slot_{s.lane_id}_{s.zone}" for s in feasible)
    chosen = feasible[-1]  # deliberately not the auto (least-ballast) slot
    at.button(key=f"slot_{chosen.lane_id}_{chosen.zone}").click().run()
    assert not at.exception
    assert game.deck.placements[booking.id] == Slot(chosen.lane_id, chosen.zone)
    assert game.index == 1 and game.pending_index is None


def test_manual_cancel_and_mode_switch_clear_pending():
    at = _fresh()
    at.radio(key="placement_mode").set_value("manual").run()
    game = at.session_state["game"]
    at.button(key="accept").click().run()
    assert game.pending_index == 0
    at.button(key="cancel_pending").click().run()
    assert not at.exception
    assert game.pending_index is None and game.index == 0
    at.button(key="accept").click().run()
    assert game.pending_index == 0
    at.radio(key="placement_mode").set_value("auto").run()
    assert not at.exception
    assert game.pending_index is None and not game.deck.placements


def test_advisor_toggle_shows_verdict():
    at = _fresh()
    at.toggle(key="advisor_on").set_value(True).run()
    assert not at.exception
    assert any("futures" in m.value for m in at.markdown)
    seed = at.session_state["seed"]
    jobs = at.session_state["jobs"]
    assert jobs.result(("verdict", seed, 0)) is not None
    at.button(key="reject").click().run()
    assert not at.exception
    assert jobs.result(("verdict", seed, 1)) is not None  # next request's verdict shown too
