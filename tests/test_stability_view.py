from streamlit.testing.v1 import AppTest



def _script():
    from app.stability_view import stability_gauges
    from roro_yield.models import DEFAULT_STABILITY

    stability_gauges(-1.8, 0.4, 46.0, DEFAULT_STABILITY, 1100.0)
    stability_gauges(5.0, -2.0, 0.0, DEFAULT_STABILITY, 1100.0)  # beyond limits, clamps


def test_stability_gauges_render():
    at = AppTest.from_function(_script).run()
    assert not at.exception
    text = " ".join(m.value for m in at.markdown)
    assert "sellable deadweight" in text
    assert "port" in text and "stern" in text
