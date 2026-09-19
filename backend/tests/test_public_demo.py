import importlib
import os

import pytest
from fastapi.testclient import TestClient

PASS = {"pod": "POD A", "speed_mps": 20, "length_m": 4.2, "signature": [0.1, 0.5, 0.8, 0.3]}


@pytest.fixture()
def public(tmp_path, monkeypatch):
    monkeypatch.setenv("ANTAR_DB", str(tmp_path / "p.db"))
    monkeypatch.setenv("ANTAR_PUBLIC_DEMO", "1")
    monkeypatch.setenv("ANTAR_POD_KEY", "secret-pod")
    import antar.api as api
    importlib.reload(api)
    with TestClient(api.app) as c:
        yield c
    os.environ.pop("ANTAR_PUBLIC_DEMO", None)


def test_public_demo_keeps_the_demo_open(public):
    assert public.get("/api/health").status_code == 200
    assert public.post("/api/segments/SEG-SIM-01/scenario/B").status_code == 200
    assert public.put("/api/segments/SEG-SIM-01/pods/POD B", json={"online": False}).status_code == 200


def test_public_demo_closes_personal_data_and_phones(public):
    assert public.post("/api/alerts/test").status_code == 403
    r = public.post("/api/segments/SEG-SIM-01/responders", json={"name": "x", "phone": "9", "distance_km": 1})
    assert r.status_code == 403
    assert public.delete("/api/responders/1").status_code == 403


def test_pods_need_the_key(public):
    url = "/api/segments/SEG-FIELD-01/pass"
    assert public.post(url, json=PASS).status_code == 401
    assert public.post(url, json=PASS, headers={"X-Pod-Key": "wrong"}).status_code == 401
    assert public.post(url, json=PASS, headers={"X-Pod-Key": "secret-pod"}).status_code == 200


def test_telegram_muted_on_public_demo(monkeypatch):
    from antar.dispatch import Dispatcher
    monkeypatch.setenv("ANTAR_PUBLIC_DEMO", "1")
    monkeypatch.setenv("ANTAR_TELEGRAM_BOT_TOKEN", "1:a")
    monkeypatch.setenv("ANTAR_TELEGRAM_CHAT_ID", "2")
    assert [c.name for c in Dispatcher().channels] == ["console"]
