"""Alert routing: pod -> pod relay -> tower -> three recipients, simultaneously.

Channels are pluggable. The default `ConsoleChannel` records delivery with a realistic
latency so the demo is honest about what it is. Set ANTAR_WEBHOOK_URL to also POST every
alert as JSON to a URL you control (e.g. an n8n / Slack / SMS gateway on your homelab).
Set ANTAR_TELEGRAM_BOT_TOKEN and ANTAR_TELEGRAM_CHAT_ID to push every alert to a real
phone through a Telegram bot: one message per tier, sent at the same moment.
"""
from __future__ import annotations

import asyncio
import json
import logging
import os
import random
import time
import urllib.request
from dataclasses import dataclass

log = logging.getLogger("antar.dispatch")


@dataclass
class Recipient:
    tier: str          # hospital | police | responders
    name: str
    detail: str


class ConsoleChannel:
    name = "console"

    def __init__(self, rng: random.Random | None = None):
        self.rng = rng or random.Random()

    async def send(self, recipient: Recipient, payload: dict, index: int) -> dict:
        ms = int(190 + self.rng.random() * 170 + index * 60)
        await asyncio.sleep(ms / 1000)
        log.info("ALERT -> %s (%s): %s", recipient.name, recipient.tier, payload["summary"])
        return {"status": "delivered", "latency_ms": ms}


class WebhookChannel:
    name = "webhook"

    def __init__(self, url: str, timeout: float = 4.0):
        self.url, self.timeout = url, timeout

    def _post(self, body: bytes) -> int:
        req = urllib.request.Request(self.url, data=body, method="POST",
                                     headers={"Content-Type": "application/json"})
        with urllib.request.urlopen(req, timeout=self.timeout) as r:
            return r.status

    async def send(self, recipient: Recipient, payload: dict, index: int) -> dict:
        t0 = time.perf_counter()
        body = json.dumps({"recipient": recipient.__dict__, **payload}).encode()
        try:
            code = await asyncio.to_thread(self._post, body)
            ok = 200 <= code < 300
        except Exception as exc:  # network failure must never crash dispatch
            log.warning("webhook failed for %s: %s", recipient.name, exc)
            ok = False
        return {"status": "delivered" if ok else "failed",
                "latency_ms": int((time.perf_counter() - t0) * 1000)}


class TelegramChannel:
    name = "telegram"
    ICON = {"hospital": "🏥 HOSPITAL", "police": "🚓 HIGHWAY PATROL", "responders": "🙋 LOCAL RESPONDERS"}

    def __init__(self, token: str, chat_id: str, timeout: float = 6.0):
        self.url = f"https://api.telegram.org/bot{token}/sendMessage"
        self.chat_id, self.timeout = chat_id, timeout

    def format(self, recipient: Recipient, payload: dict) -> str:
        return (f"🚨 ANTAR ALERT → {self.ICON.get(recipient.tier, recipient.tier.upper())}\n"
                f"{recipient.detail}\n\n"
                f"Incident #{payload.get('incident_id', '-')} · {payload.get('segment_name', payload.get('segment', ''))}\n"
                f"{payload.get('summary', '')}\n"
                f"Evidence: {payload.get('evidence', '-')}\n"
                f"Sim clock {payload.get('sim_clock', '-')}")

    def _post(self, body: bytes) -> int:
        req = urllib.request.Request(self.url, data=body, method="POST",
                                     headers={"Content-Type": "application/json"})
        with urllib.request.urlopen(req, timeout=self.timeout) as r:
            return r.status

    async def send(self, recipient: Recipient, payload: dict, index: int) -> dict:
        t0 = time.perf_counter()
        body = json.dumps({"chat_id": self.chat_id, "text": self.format(recipient, payload)}).encode()
        try:
            code = await asyncio.to_thread(self._post, body)
            ok = 200 <= code < 300
        except Exception as exc:  # a dead phone network must never crash dispatch
            log.warning("telegram failed for %s: %s", recipient.name, type(exc).__name__)
            ok = False
        return {"status": "delivered" if ok else "failed",
                "latency_ms": int((time.perf_counter() - t0) * 1000)}


def relay_path(pods: list[dict], origin: str, tower_id: str, rng: random.Random) -> list[dict]:
    """Hop along ONLINE pods from the origin towards the tower (increasing chainage).
    Offline pods are skipped, which is exactly how the chain survives a dead node."""
    chain = sorted((p for p in pods if p["online"]), key=lambda p: p["chainage_m"])
    start = next((i for i, p in enumerate(chain) if p["id"] == origin), 0)
    names = [p["id"] for p in chain[start:]] + [tower_id]
    hops, acc = [], 0
    for a, b in zip(names, names[1:]):
        ms = int(26 + rng.random() * 44)
        acc += ms
        hops.append({"from": a, "to": b, "ms": ms, "acc_ms": acc})
    return hops


class Dispatcher:
    def __init__(self, rng: random.Random | None = None):
        self.rng = rng or random.Random()
        self.channels = [ConsoleChannel(self.rng)]
        url = os.getenv("ANTAR_WEBHOOK_URL")
        if url:
            self.channels.append(WebhookChannel(url))
        token, chat = os.getenv("ANTAR_TELEGRAM_BOT_TOKEN"), os.getenv("ANTAR_TELEGRAM_CHAT_ID")
        public = os.getenv("ANTAR_PUBLIC_DEMO", "").lower() in ("1", "true", "yes")
        if public and os.getenv("ANTAR_PUBLIC_TELEGRAM", "").lower() not in ("1", "true", "yes"):
            token = None   # strangers running scenario B must not flood the owner's phone
        if token and chat:
            self.channels.append(TelegramChannel(token, chat))
            log.info("Telegram alerts enabled for chat %s", chat)

    async def fan_out(self, recipients: list[Recipient], payload: dict, relay: list[dict]) -> list[dict]:
        """All recipients at once — serialising this would spend the minutes the system exists to save."""
        base = relay[-1]["acc_ms"] if relay else 0

        async def one(i: int, r: Recipient) -> dict:
            results = await asyncio.gather(*(ch.send(r, payload, i) for ch in self.channels))
            primary = results[0]
            delivered = any(x["status"] == "delivered" for x in results)
            return {"tier": r.tier, "recipient": r.name, "detail": r.detail,
                    "channel": "+".join(ch.name for ch in self.channels),
                    "status": "delivered" if delivered else "failed",
                    "latency_ms": base + primary["latency_ms"], "relay": relay}

        return list(await asyncio.gather(*(one(i, r) for i, r in enumerate(recipients))))
