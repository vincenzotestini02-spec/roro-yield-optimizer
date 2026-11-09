import io

from pypdf import PdfReader


def pdf_text(content: bytes) -> str:
    return "\n".join(page.extract_text() or "" for page in PdfReader(io.BytesIO(content)).pages)


def test_lab_pdf_has_the_plan_and_the_disclaimers(client, lab_values, wait):
    wait(client, client.post("/api/lab/plans", json=lab_values).json()["job_id"])
    r = client.post("/api/export/pdf", json={"source": "lab", "params": lab_values, "plan_key": "optimal"})
    assert r.status_code == 200 and r.content.startswith(b"%PDF")
    text = pdf_text(r.content)
    assert "Planning estimate, not a loading computer." in text and "Synthetic data, not DFDS data." in text
    assert "MV Nordic Bridge" in text and "Score" in text
    assert "roro-plan-optimal.pdf" in r.headers["content-disposition"]


def test_game_pdf_for_your_plan(client, finished_game):
    r = client.post("/api/export/pdf", json={"source": "game", **finished_game, "plan_key": "you"})
    assert r.status_code == 200 and "You" in pdf_text(r.content)


def test_game_csv_lists_loaded_units(client, finished_game):
    r = client.post("/api/export/csv", json={"source": "game", **finished_game, "plan_key": "fcfs"})
    assert r.status_code == 200 and r.text.startswith("lane,zone,position") and r.text.count("\n") > 10


def test_export_of_a_missing_smart_plan_is_409(client, finished_game):
    r = client.post("/api/export/pdf", json={"source": "game", **finished_game, "plan_key": "smart"})
    assert r.status_code == 409 and "again" in r.json()["detail"]


def test_wrong_combination_is_422(client, finished_game):
    r = client.post("/api/export/csv", json={"source": "game", **finished_game, "plan_key": "optimal"})
    assert r.status_code == 422


def test_lab_export_without_params_is_422(client):
    assert client.post("/api/export/csv", json={"source": "lab", "plan_key": "fcfs"}).status_code == 422


def test_unfinished_game_export_is_409(client):
    r = client.post("/api/export/pdf", json={"source": "game", "seed": 3, "decisions": [], "plan_key": "you"})
    assert r.status_code == 409


def test_old_manifest_route_still_works(client, lab_values, wait):
    wait(client, client.post("/api/lab/plans", json=lab_values).json()["job_id"])
    r = client.post("/api/manifest.csv", json={"params": lab_values, "plan_key": "optimal"})
    assert r.status_code == 200 and r.text.startswith("lane,zone,position")


def test_pdf_of_a_big_vessel_fits_on_pages(client, lab_values, wait):
    from server.presets import PRESETS
    values = {**lab_values, **PRESETS["shortsea"]["values"]}
    wait(client, client.post("/api/lab/plans", json=values).json()["job_id"], timeout=180)
    r = client.post("/api/export/pdf", json={"source": "lab", "params": values, "plan_key": "fcfs"})
    assert r.status_code == 200 and len(PdfReader(io.BytesIO(r.content)).pages) >= 2


def test_lab_export_rebuilds_a_plan_the_server_forgot(client, lab_values):
    values = {**lab_values, "seed": 4321}  # never computed in this process
    r = client.post("/api/export/csv", json={"source": "lab", "params": values, "plan_key": "optimal"})
    assert r.status_code == 200 and r.text.startswith("lane,zone,position")


def test_game_best_export_rebuilds_when_the_job_is_gone(client, finished_game):
    r = client.post("/api/export/csv", json={"source": "game", **finished_game, "plan_key": "best"})
    assert r.status_code == 200


def test_a_gone_smart_plan_says_to_run_it_again(client, lab_values):
    values = {**lab_values, "seed": 4322}
    r = client.post("/api/export/pdf", json={"source": "lab", "params": values, "plan_key": "smart"})
    assert r.status_code == 409 and "run the smart planner again" in r.json()["detail"].lower()
