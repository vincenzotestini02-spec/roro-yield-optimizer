import os
import time
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


FOUR_LABELS = ("First come, first served", "You", "Smart planner (no foresight)", "Best possible (perfect foresight)")


def _rerun_until(at, done, cap_s=180):
    """Background jobs finish between runs: rerun the script until `done(at)` holds."""
    start = time.perf_counter()
    while not done(at):
        assert time.perf_counter() - start < cap_s, "background job never finished"
        time.sleep(0.5)
        at.run()
        assert not at.exception


def _metric_labels(at):
    return [m.label for m in at.metric]


def test_full_game_reveal_four_cards_advisor_table_then_lab():
    at = _fresh()
    game = at.session_state["game"]
    clicks = 0
    while at.session_state["stage"] == "game":
        at.button(key="accept" if clicks % 3 == 0 else "reject").click().run()
        assert not at.exception
        clicks += 1
        assert clicks < 200
    _rerun_until(at, lambda a: all(lbl in _metric_labels(a) for lbl in FOUR_LABELS))
    assert [lbl for lbl in _metric_labels(at) if lbl in FOUR_LABELS] == list(FOUR_LABELS)
    assert any("heel" in c.value and "trim" in c.value and "ballast" in c.value for c in at.caption)
    tables = [d.value for d in at.dataframe if "advisor" in d.value.columns]
    assert len(tables) == 1 and len(tables[0]) == len(game.queue)
    assert any("verdicts use K = 3" in c.value for c in at.caption)

    def verdicts_done(a):
        table = next(d.value for d in a.dataframe if "advisor" in d.value.columns)
        return not (table["advisor"] == "…").any()

    _rerun_until(at, verdicts_done)
    table = next(d.value for d in at.dataframe if "advisor" in d.value.columns)
    assert set(table["advisor"]) <= {"accept", "reject", "reject (doesn't fit)"}
    assert (table["✗"] == "✗").sum() == sum(
        y != adv.split()[0] for y, adv in zip(table["you"], table["advisor"]))
    at.button(key="to_lab").click().run()
    assert not at.exception
    assert at.session_state["stage"] == "lab"


def test_toggles_survive_reveal_and_new_game():
    at = _fresh()
    at.radio(key="placement_mode").set_value("manual").run()
    at.session_state["stage"] = "reveal"
    at.run()
    assert not at.exception
    at.run()  # a second run without the widgets: Streamlit drops their widget state
    at.button(key="play_again").click().run()
    assert not at.exception
    assert at.session_state["stage"] == "game"
    assert at.session_state["placement_mode"] == "manual"
    assert at.radio(key="placement_mode").value == "manual"


def test_advisor_failure_shows_note(monkeypatch):
    import app.state

    def boom(*args, **kwargs):
        raise RuntimeError("solver exploded")

    monkeypatch.setattr(app.state, "advise", boom)
    at = _fresh()
    at.toggle(key="advisor_on").set_value(True).run()
    assert not at.exception
    assert any("Advisor unavailable for this request" in m.value for m in [*at.markdown, *at.caption])


def test_manual_failed_confirm_says_pick_another_zone():
    at = _fresh()
    at.radio(key="placement_mode").set_value("manual").run()
    at.button(key="accept").click().run()
    at.session_state["game_msg"] = "that zone can't take this unit"
    at.run()
    assert not at.exception
    texts = [w.value for w in at.warning]
    assert any("pick another zone or cancel" in t.lower() for t in texts)
    assert not any("Reject it to continue" in t for t in texts)


def test_lab_stability_sliders_and_rows():
    at = _fresh()
    at.button(key="skip_to_lab").click().run()
    at.slider(key="lab_heel").set_value(1.0).run()
    assert not at.exception
    assert at.slider(key="lab_lane_len").min == 70
    for key in ("lab_trim", "lab_tank", "lab_ballast_cost"):
        assert at.slider(key=key) is not None
    table = at.dataframe[0].value
    assert {"Ballast, t", "Heel, °", "Trim, m"} <= set(table.index)


def test_lab_run_smart_adds_smart_column():
    at = _fresh()
    at.button(key="skip_to_lab").click().run()
    at.slider(key="lab_n_requests").set_value(30).run()
    assert "Smart planner (no foresight)" not in at.dataframe[0].value.columns
    at.button(key="lab_run_smart").click().run()
    assert not at.exception
    _rerun_until(at, lambda a: "Smart planner (no foresight)" in a.dataframe[0].value.columns)
