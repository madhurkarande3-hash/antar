import asyncio
import json

from antar.dispatch import Dispatcher, Recipient, TelegramChannel

PAYLOAD = {"incident_id": 7, "segment": "SEG-SIM-01", "segment_name": "Sirsa stretch",
           "summary": "Probable blockage between POD A and POD B.", "confidence": 0.86,
           "tier": "HIGH", "evidence": "flow -48%", "sim_clock": "02:14"}


def test_telegram_disabled_without_env(monkeypatch):
    monkeypatch.delenv("ANTAR_TELEGRAM_BOT_TOKEN", raising=False)
    monkeypatch.delenv("ANTAR_TELEGRAM_CHAT_ID", raising=False)
    assert [c.name for c in Dispatcher().channels] == ["console"]


def test_telegram_sends_one_message_per_tier_at_once(monkeypatch):
    monkeypatch.setenv("ANTAR_TELEGRAM_BOT_TOKEN", "123:abc")
    monkeypatch.setenv("ANTAR_TELEGRAM_CHAT_ID", "999")
    sent = []
    monkeypatch.setattr(TelegramChannel, "_post", lambda self, body: sent.append(json.loads(body)) or 200)
    d = Dispatcher()
    assert "telegram" in [c.name for c in d.channels]
    recips = [Recipient("hospital", "Nearest hospital", "CHC"), Recipient("police", "Patrol", "Unit 12"),
              Recipient("responders", "Local", "2 registered")]
    res = asyncio.run(d.fan_out(recips, PAYLOAD, []))
    assert len(sent) == 3 and all(m["chat_id"] == "999" for m in sent)
    assert any("HOSPITAL" in m["text"] for m in sent) and "Incident #7" in sent[0]["text"]
    assert all(r["status"] == "delivered" for r in res)


def test_telegram_failure_never_breaks_dispatch(monkeypatch):
    monkeypatch.setenv("ANTAR_TELEGRAM_BOT_TOKEN", "123:abc")
    monkeypatch.setenv("ANTAR_TELEGRAM_CHAT_ID", "999")
    def boom(self, body):
        raise OSError("no network")
    monkeypatch.setattr(TelegramChannel, "_post", boom)
    res = asyncio.run(Dispatcher().fan_out([Recipient("police", "Patrol", "x")], PAYLOAD, []))
    assert res[0]["status"] == "delivered"   # console still delivered


from tests.test_api import client  # noqa: E402,F401  (reuse fixture)


def test_alert_test_endpoint(client):
    r = client.post("/api/alerts/test")
    assert r.status_code == 200 and "console" in r.json()["channels"]
