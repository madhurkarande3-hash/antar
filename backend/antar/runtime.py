"""Segment runtime: glues detector + pods + persistence + dispatch + live console.

Two kinds of segment run side by side:

* ``sim``   — driven by the ground-truth traffic model (antar.traffic). This is the
              live demo: press a scenario, watch the backend decide.
* ``field`` — driven by real pod uploads through the REST API. The detector is ticked
              on the server clock. This is where ESP32 firmware will post to.

The detector code is identical in both.
"""
from __future__ import annotations

import asyncio
import json
import logging
import random
import time
from typing import Any, Awaitable, Callable, Optional

from .config import DEFAULT
from .detector import Detector
from .dispatch import Dispatcher, Recipient, relay_path
from .store import Store
from .traffic import CRASH, EXIT, Traffic

log = logging.getLogger("antar.runtime")

Broadcast = Callable[[dict], Awaitable[None]]
STEP = 0.2                       # sim seconds per physics step (same as the browser sim)
TOWER = "TOWER-07"
HEARTBEAT_TIMEOUT_S = 90.0
SCENARIOS = {
    "A": ("nominal", "Scenario A, nominal: the next vehicle will pass POD B normally."),
    "B": ("crash", f"Scenario B, incident: the next vehicle will stop at K{CRASH / 1000:.3f}. ANTAR is not told."),
    "C": ("exit", f"Scenario C, legal exit: the next vehicle will turn off at K{EXIT / 1000:.3f}. ANTAR is not told."),
}


def clock(t: float) -> str:
    s = t % 86400
    return f"{int(s // 3600):02d}:{int(s % 3600 // 60):02d}:{s % 60:04.1f}"


def default_pods(virtual: bool) -> dict[str, dict]:
    spec = [("POD A", 0, 94, -68, "pole"), ("POD B", 700, 88, -79, "solar"),
            ("POD C", 1290, 81, -84, "solar"), ("POD D", 1610, 76, -91, "battery")]
    now = time.time()
    return {pid: {"id": pid, "chainage_m": m, "online": True, "battery_pct": bat, "rssi_dbm": rssi,
                  "power": pwr, "last_seen": now, "virtual": virtual, "face": f"{pid[-1]} ONLINE"}
            for pid, m, bat, rssi, pwr in spec}


class Segment:
    def __init__(self, seg_id: str, name: str, mode: str, store: Store, broadcast: Broadcast,
                 seed: Optional[int] = None):
        self.id, self.name, self.mode = seg_id, name, mode
        self.store, self.broadcast = store, broadcast
        self.rng = random.Random(seed)
        self.dispatcher = Dispatcher(self.rng)
        self.pods = default_pods(virtual=(mode == "sim"))
        self.detector = Detector(seg_id, DEFAULT, listener=self._on_event)
        self.traffic: Optional[Traffic] = Traffic(self._on_pass, seed=seed) if mode == "sim" else None
        self.speed = 4.0 if mode == "sim" else 1.0
        self.paused = False
        self.scenario: Optional[str] = None
        self.recent: list[dict] = []           # rolling console log (includes passes)
        self._tasks: set[asyncio.Task] = set()
        self._truth_seen = 0
        self.store.seed_responders(seg_id)
        if self.traffic:
            self._warm_up(1400)

    # ------------------------------------------------------------- time
    def now(self) -> float:
        return self.traffic.t if self.traffic else time.time()

    def _warm_up(self, steps: int) -> None:
        self.detector.quiet = True
        for _ in range(steps):
            self.traffic.step(STEP)
            self.detector.tick(self.traffic.t)
        self.detector.quiet = False
        self._truth_seen = len(self.traffic.truth)

    def advance(self, real_dt: float) -> None:
        if self.paused:
            return
        if self.traffic:
            remaining = real_dt * self.speed
            while remaining > 1e-9:
                dt = min(STEP, remaining)
                self.traffic.step(dt)
                self.detector.tick(self.traffic.t)
                remaining -= dt
            while self._truth_seen < len(self.traffic.truth):
                tr = self.traffic.truth[self._truth_seen]
                self._truth_seen += 1
                self._push({"kind": "ground_truth", "level": "truth", "text": "[ground truth] " + tr["text"],
                            "t": tr["t"], "segment": self.id})
        else:
            self._watchdog()
            self.detector.tick(time.time())

    # ----------------------------------------------------- sensor boundary
    def _on_pass(self, pod: str, t: float, v: float, length: float, sig: list[float]) -> Optional[str]:
        """The only door between ground truth and the detector."""
        return self.ingest_pass("POD A" if pod == "A" else self.downstream_pod(), t, v, length, sig)

    def downstream_pod(self) -> str:
        for pid in ("POD B", "POD C", "POD D"):
            if self.pods[pid]["online"]:
                return pid
        return "POD B"

    def ingest_pass(self, pod_id: str, t: float, v: float, length: float, sig: list[float]) -> Optional[str]:
        if pod_id not in self.pods:
            raise KeyError(pod_id)
        pod = self.pods[pod_id]
        if not pod["online"] and pod["virtual"]:
            return None
        pod["last_seen"] = time.time()
        if pod_id == "POD A":
            k = self.detector.pod_a(t, v, length, sig)
            pod["face"] = f"A {k.cls} {v * 3.6:02.0f}"
            return k.id
        if pod_id == self.downstream_pod():
            m = self.detector.pod_b(t, v, length, sig)
            pod["face"] = f"{pod_id[-1]} FLW {self.detector.flow(t)['observed_vpm']:02.0f}"
            return m.id if m else None
        return None    # a relay pod beyond the active pair: counted for health only

    # ----------------------------------------------------------- events
    def _push(self, e: dict) -> None:
        self.recent.append(e)
        del self.recent[:-250]
        self._spawn(self.broadcast({"type": "event", "segment": self.id, "clock": clock(e["t"]), **e}))

    def _spawn(self, coro: Awaitable[Any]) -> None:
        try:
            task = asyncio.get_running_loop().create_task(coro)
        except RuntimeError:            # no loop (unit tests): run synchronously
            asyncio.run(coro)
            return
        self._tasks.add(task)
        task.add_done_callback(self._tasks.discard)

    def _on_event(self, e: dict) -> None:
        self.store.audit(e)
        self._push(e)
        if e["kind"] == "candidate_opened":
            self._face("POD A", "A WATCH"); self._face(self.downstream_pod(), "NO MATCH")
        if e["kind"] == "decision":
            self._spawn(self._decide(e["suspicion"]))

    def _face(self, pid: str, text: str) -> None:
        self.pods[pid]["face"] = text

    async def _decide(self, sus: dict) -> None:
        if sus["verdict"] != "dispatch":
            inc = self.store.create_incident(self.id, sus, "dismissed")
            self._face("POD A", "A CLEAR"); self._face(self.downstream_pod(), "LINK")
            await self.broadcast({"type": "incident", "segment": self.id, "incident": inc})
            return

        self._face("POD A", "A ALERT"); self._face(self.downstream_pod(), "! SLOW !")
        active = self.store.active_incident(self.id)
        if active:
            # Same blockage, noticed again. Strengthen the record; do NOT page the hospital twice.
            inc = self.store.reconfirm(active["id"], sus)
            e = {"kind": "incident_update", "level": "warn", "t": sus["t_settle"], "segment": self.id,
                 "text": f"{sus['evt']} re-confirms active incident #{inc['id']} "
                         f"(x{inc['reconfirmations']}). No duplicate alert sent."}
            self.store.audit(e); self._push(e)
            await self.broadcast({"type": "incident", "segment": self.id, "incident": inc})
            return

        inc = self.store.create_incident(self.id, sus, "dispatched")
        await self.broadcast({"type": "incident", "segment": self.id, "incident": inc})
        relay = relay_path(list(self.pods.values()), self.downstream_pod(), TOWER, self.rng)
        responders = self.store.responders(self.id, active_only=True)
        recipients = [
            Recipient("hospital", "Nearest hospital", "CHC Sirsa, 8.4 km"),
            Recipient("police", "Highway patrol", "Patrol unit 12, 5.1 km"),
            Recipient("responders", "Local responders",
                      f"{len(responders)} registered within 2 km: " +
                      ", ".join(r["name"] for r in responders[:3]) if responders else "none registered"),
        ]
        payload = {
            "incident_id": inc["id"], "segment": self.id, "segment_name": self.name,
            "summary": f"Probable blockage between POD A (K0.000) and {self.downstream_pod()}. "
                       f"Confidence {sus['confidence']:.2f} {sus['tier']}.",
            "confidence": sus["confidence"], "tier": sus["tier"], "evidence": sus["reason"],
            "sim_clock": clock(sus["t_settle"]),
        }
        path = " > ".join([relay[0]["from"]] + [h["to"] for h in relay]) if relay else TOWER
        e = {"kind": "dispatch", "level": "alert", "t": sus["t_settle"], "segment": self.id,
             "text": f"Relaying incident #{inc['id']}: {path}, then 3 recipients at once", "relay": relay}
        self.store.audit(e); self._push(e)

        results = await self.dispatcher.fan_out(recipients, payload, relay)
        for r in results:
            self.store.add_alert(inc["id"], r)
        worst = max(r["latency_ms"] for r in results)
        ok = sum(r["status"] == "delivered" for r in results)
        e = {"kind": "dispatch", "level": "alert", "t": self.now(), "segment": self.id,
             "text": f"Transmission complete: {ok}/3 recipients acknowledged, end-to-end {worst} ms"}
        self.store.audit(e); self._push(e)
        self._face("POD A", "A ACK")
        await self.broadcast({"type": "incident", "segment": self.id,
                              "incident": self.store.get_incident(inc["id"])})

    # -------------------------------------------------------- controls
    def start_scenario(self, sid: str) -> None:
        if not self.traffic:
            raise ValueError("scenarios only run on simulated segments")
        fate, note = SCENARIOS[sid]
        self.detector.reset()
        self.traffic.clear_road()
        self.recent.clear()
        active = self.store.active_incident(self.id)
        if active:      # a fresh demo road has no wreck on it, so the old incident is over
            self.store.set_status(active["id"], "resolved")
        for pid in self.pods:
            self._face(pid, f"{pid[-1]} ONLINE")
        self._warm_up(1100)
        self.traffic.arm(fate)
        self.scenario = sid
        t = self.now()
        e = {"kind": "scenario", "level": "info", "t": t, "segment": self.id,
             "text": f"{note} Armed, waiting for the next pass at POD A."}
        self.store.audit(e); self._push(e)

    def set_pod_online(self, pod_id: str, online: bool, reason: str = "operator") -> dict:
        pod = self.pods[pod_id]
        if pod["online"] == online:
            return pod
        before = self.downstream_pod()
        pod["online"] = online
        pod["face"] = f"{pod_id[-1]} {'ONLINE' if online else 'DARK'}"
        if online:
            pod["last_seen"] = time.time()
        after = self.downstream_pod()
        t = self.now()
        e = {"kind": "pod_status", "level": "warn" if not online else "info", "t": t, "segment": self.id,
             "text": f"{pod_id} {'back online' if online else 'went dark'} ({reason})."}
        if before != after:
            seg_m = self.pods[after]["chainage_m"] - self.pods["POD A"]["chainage_m"]
            degraded = after != "POD B"
            self.detector.void_open(t, f"pair re-formed POD A to {after}")
            self.detector.set_degraded(degraded, seg_m)
            if self.traffic:
                self.traffic.pb = self.pods[after]["chainage_m"]
                self._warm_up(700)      # re-establish flow baselines for the new pair
            e["text"] += (f" Pair re-formed: POD A to {after}, {seg_m:.0f} m. " +
                          ("Windows are wider and every confidence tier now needs more evidence."
                           if degraded else "Full precision restored."))
        self.store.audit(e); self._push(e)
        return pod

    def heartbeat(self, pod_id: str, battery_pct: Optional[float], rssi_dbm: Optional[float],
                  power: Optional[str]) -> dict:
        pod = self.pods[pod_id]
        pod["last_seen"] = time.time()
        if battery_pct is not None:
            pod["battery_pct"] = battery_pct
        if rssi_dbm is not None:
            pod["rssi_dbm"] = rssi_dbm
        if power:
            pod["power"] = power
        if not pod["online"]:
            self.set_pod_online(pod_id, True, "heartbeat resumed")
        return pod

    def _watchdog(self) -> None:
        now = time.time()
        for pid, pod in self.pods.items():
            if pod["online"] and now - pod["last_seen"] > HEARTBEAT_TIMEOUT_S:
                self.set_pod_online(pid, False, f"no heartbeat for {HEARTBEAT_TIMEOUT_S:.0f} s")

    # -------------------------------------------------------- snapshot
    def snapshot(self, include_vehicles: bool = True) -> dict:
        t = self.now()
        d = self.detector
        sus = d.sus.public() if d.sus else None
        if sus and d.sus and not d.sus.settled:
            sus["remaining_s"] = round(max(0.0, d.sus.t_close - t), 1)
        return {
            "type": "state", "segment": self.id, "name": self.name, "mode": self.mode,
            "t": round(t, 2), "clock": clock(t), "speed": self.speed, "paused": self.paused,
            "scenario": self.scenario, "degraded": d.degraded, "segment_m": d.segment_m,
            "downstream_pod": self.downstream_pod(), "open_windows": d.open_windows(),
            "flow": d.flow(t), "speeds": d.speeds(t), "suspicion": sus,
            "pods": list(self.pods.values()),
            "vehicles": self.traffic.snapshot() if (self.traffic and include_vehicles) else [],
            "focus_track": self.traffic.focus_track if self.traffic else None,
            "geometry": {"exit_m": EXIT, "crash_m": CRASH} if self.traffic else None,
        }


class Runtime:
    def __init__(self, store: Store, seed: Optional[int] = None):
        self.store = store
        self.clients: set = set()
        self.segments: dict[str, Segment] = {}
        self._task: Optional[asyncio.Task] = None
        self.add(Segment("SEG-SIM-01", "District road, simulated (Sirsa stretch)", "sim", store,
                         self.broadcast, seed))
        self.add(Segment("SEG-FIELD-01", "Field segment, awaiting pod uploads", "field", store,
                         self.broadcast, seed))

    def add(self, seg: Segment) -> None:
        self.segments[seg.id] = seg

    def get(self, seg_id: str) -> Segment:
        return self.segments[seg_id]

    async def broadcast(self, msg: dict) -> None:
        if not self.clients:
            return
        data = json.dumps(msg, default=str)
        dead = []
        for ws in list(self.clients):
            try:
                await ws.send_text(data)
            except Exception:
                dead.append(ws)
        for ws in dead:
            self.clients.discard(ws)

    async def run(self, hz: float = 20.0) -> None:
        last, frame = time.perf_counter(), 0
        while True:
            await asyncio.sleep(1 / hz)
            now = time.perf_counter()
            dt, last = min(now - last, 0.25), now
            frame += 1
            for seg in self.segments.values():
                try:
                    seg.advance(dt)
                except Exception:
                    log.exception("segment %s tick failed", seg.id)
            if frame % 3 == 0:
                for seg in self.segments.values():
                    await self.broadcast(seg.snapshot())

    def start(self) -> None:
        self._task = asyncio.get_running_loop().create_task(self.run())

    async def stop(self) -> None:
        if self._task:
            self._task.cancel()
            try:
                await self._task
            except asyncio.CancelledError:
                pass
