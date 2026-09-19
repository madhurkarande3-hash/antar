"""API tests against a throwaway database."""
import os
import time

import pytest
from fastapi.testclient import TestClient


@pytest.fixture()
def client(tmp_path):
    os.environ["ANTAR_DB"] = str(tmp_path / "t.db")
    os.environ["ANTAR_SEED"] = "3"
    import importlib
    import antar.api as api
    importlib.reload(api)
    with TestClient(api.app) as c:
        yield c


def test_health_and_console(client):
    assert client.get("/api/health").json()["ok"]
    assert "ANTAR" in client.get("/").text
    assert client.get("/demo/").status_code == 200
    assert client.get("/demo/simulation/antar-sim.html").status_code == 200


def test_segments_listed(client):
    ids = [s["segment"] for s in client.get("/api/segments").json()]
    assert ids == ["SEG-SIM-01", "SEG-FIELD-01"]


def test_scenario_endpoint(client):
    r = client.post("/api/segments/SEG-SIM-01/scenario/B")
    assert r.status_code == 200 and r.json()["armed"] == "B"
    assert client.post("/api/segments/SEG-FIELD-01/scenario/B").status_code == 409


def test_field_ingest_and_validation(client):
    body = {"pod": "POD A", "speed_mps": 20, "length_m": 4.2, "signature": [0.1, 0.2, 0.3, 0.4]}
    r = client.post("/api/segments/SEG-FIELD-01/pass", json=body)
    assert r.status_code == 200 and r.json()["track"].startswith("TRK-")
    assert client.post("/api/segments/SEG-SIM-01/pass", json=body).status_code == 409
    bad = {**body, "speed_mps": -3}
    assert client.post("/api/segments/SEG-FIELD-01/pass", json=bad).status_code == 422


def test_pod_offline_repairs_segment(client):
    r = client.put("/api/segments/SEG-SIM-01/pods/POD B", json={"online": False})
    assert r.status_code == 200
    s = client.get("/api/segments/SEG-SIM-01").json()
    assert s["degraded"] and s["downstream_pod"] == "POD C" and s["segment_m"] == 1290
    client.put("/api/segments/SEG-SIM-01/pods/POD B", json={"online": True})
    assert not client.get("/api/segments/SEG-SIM-01").json()["degraded"]
    assert client.put("/api/segments/SEG-SIM-01/pods/POD A", json={"online": False}).status_code == 409


def test_heartbeat(client):
    r = client.post("/api/segments/SEG-FIELD-01/pods/POD B/heartbeat", json={"battery_pct": 61, "power": "solar"})
    assert r.json()["battery_pct"] == 61


def test_responders_crud_and_radius_rule(client):
    base = "/api/segments/SEG-SIM-01/responders"
    assert len(client.get(base).json()) == 3             # seeded
    assert client.post(base, json={"name": "Far Away", "phone": "+91000000", "distance_km": 5}).status_code == 422
    r = client.post(base, json={"name": "Asha K", "phone": "+91 90000 00000", "distance_km": 1.1})
    assert r.status_code == 201
    assert client.delete(f"/api/responders/{r.json()['id']}").status_code == 204


def test_incident_lifecycle_end_to_end(client):
    """Run scenario B at high speed and wait for a real dispatch with 3 alerts."""
    client.patch("/api/segments/SEG-SIM-01/sim", json={"speed": 16})
    client.post("/api/segments/SEG-SIM-01/scenario/B")
    inc = None
    deadline = time.time() + 40
    while time.time() < deadline:
        found = client.get("/api/incidents?status=dispatched").json()
        if found and len(found[0]["alerts"]) == 3:
            inc = found[0]; break
        time.sleep(0.5)
    assert inc, "scenario B did not dispatch in time"
    assert {a["tier"] for a in inc["alerts"]} == {"hospital", "police", "responders"}
    skip = client.patch(f"/api/incidents/{inc['id']}", json={"status": "resolved"})
    assert skip.status_code == 409, "must not jump from dispatched straight to resolved"
    assert client.patch(f"/api/incidents/{inc['id']}", json={"status": "acknowledged"}).status_code == 200
    assert client.patch(f"/api/incidents/{inc['id']}", json={"status": "acknowledged"}).status_code == 409
    assert client.patch(f"/api/incidents/{inc['id']}", json={"status": "resolved"}).json()["status"] == "resolved"
    kinds = {e["kind"] for e in client.get("/api/audit").json()}
    assert "pass_a" not in kinds and "decision" in kinds      # privacy: no per-vehicle records stored
