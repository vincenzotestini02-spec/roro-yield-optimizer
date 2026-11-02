from pathlib import Path

from streamlit.testing.v1 import AppTest

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
