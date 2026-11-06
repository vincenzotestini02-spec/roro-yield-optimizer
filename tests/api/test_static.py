import pytest
from fastapi.testclient import TestClient

from server import main


@pytest.fixture
def client_with_dist(tmp_path, monkeypatch):
    (tmp_path / "assets").mkdir()
    (tmp_path / "assets" / "app.js").write_text("console.log(1)")
    (tmp_path / "index.html").write_text('<div id="root"></div>')
    monkeypatch.setattr(main, "WEB_DIST", tmp_path)
    return TestClient(main.create_app())


def test_spa_route_serves_index(client_with_dist):
    r = client_with_dist.get("/lab")
    assert r.status_code == 200 and '<div id="root">' in r.text


def test_assets_are_served(client_with_dist):
    assert client_with_dist.get("/assets/app.js").text == "console.log(1)"


def test_unknown_api_route_stays_json_404(client_with_dist):
    r = client_with_dist.get("/api/nope")
    assert r.status_code == 404 and "<div" not in r.text
