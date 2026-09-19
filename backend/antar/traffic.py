"""Ground-truth traffic model — a port of updateWorld() from simulation/antar-sim.html.

This module knows everything: where each vehicle is, which one crashed, which one
turned off. The detector knows none of it. The ONLY thing that crosses from here to
the detector is `on_pass(pod, t, speed, length, signature)`, carrying noisy sensor
readings — exactly what a real pod would upload.
"""
from __future__ import annotations

import random
from dataclasses import dataclass, field
from typing import Callable, Optional

LANE_M, LANE_O = -1.85, 1.85
PA, PB = 0.0, 700.0
EXIT, CRASH = 330.0, 480.0
PMIN, PMAX = -130.0, 1900.0


@dataclass(frozen=True)
class VType:
    key: str
    cls: str
    length: float
    vmin: float
    vmax: float
    weight: float


TYPES = [
    VType("moto", "2W", 1.95, 16.5, 22.5, 0.22),
    VType("auto", "3W", 2.65, 11.0, 14.0, 0.10),
    VType("car", "CAR", 4.20, 18.0, 25.5, 0.46),
    VType("truck", "HV", 8.40, 10.0, 13.5, 0.13),
    VType("bus", "HV", 10.5, 12.0, 15.5, 0.09),
]


def _clamp(v, a, b):
    return a if v < a else b if v > b else v


@dataclass
class Vehicle:
    id: int
    T: VType
    p: float
    spd: float
    des: float
    sig: list[float]
    voff: float = LANE_M
    state: str = "run"          # run | crash | exit
    fate: Optional[str] = None  # crash | exit
    ot: bool = False
    last_ot: float = -99.0
    halt: float = 0.0
    exit_s: float = 0.0
    track: Optional[str] = None
    brake: float = 0.0


PassFn = Callable[[str, float, float, float, list[float]], Optional[str]]


@dataclass
class Traffic:
    on_pass: PassFn
    seed: Optional[int] = None
    t: float = 22 * 3600 + 51 * 60 + 40
    veh: list[Vehicle] = field(default_factory=list)
    onc: list[dict] = field(default_factory=list)
    nid: int = 1
    spawn_in: float = 0.0
    onc_in: float = 2.0
    armed: Optional[str] = None       # 'nominal' | 'crash' | 'exit'
    secondary: Optional[float] = None
    halter: Optional[float] = None
    focus_track: Optional[str] = None
    truth: list[dict] = field(default_factory=list)
    pb: float = PB                    # downstream pod chainage (moves if POD B goes dark)

    def __post_init__(self):
        self.rng = random.Random(self.seed)

    # --------------------------------------------------------- generation
    def _pick(self) -> VType:
        r, acc = self.rng.random(), 0.0
        for T in TYPES:
            acc += T.weight
            if r <= acc:
                return T
        return TYPES[2]

    def _spawn(self):
        T = self._pick()
        des = T.vmin + self.rng.random() * (T.vmax - T.vmin)
        self.veh.append(Vehicle(self.nid, T, PMIN, des, des, [self.rng.random() for _ in range(4)]))
        self.nid += 1
        self.spawn_in = 5.5 + self.rng.random() * 5.6   # ~7.2 veh/min

    def _spawn_onc(self):
        T = self._pick()
        self.onc.append({"p": PMAX, "spd": T.vmin + self.rng.random() * (T.vmax - T.vmin)})
        self.onc_in = 8.0 + self.rng.random() * 13.0

    def _truth(self, text: str):
        self.truth.append({"t": round(self.t, 2), "text": text})

    # -------------------------------------------------------------- helpers
    def _lead(self, v: Vehicle):
        best, bd = None, 1e9
        for o in self.veh:
            if o is v or o.state == "exit" or abs(o.voff - v.voff) > 2.2:
                continue
            d = o.p - v.p
            if 0 < d < bd:
                bd, best = d, o
        return best

    def _onc_clear(self, v: Vehicle, ahead: float) -> bool:
        return not any(v.p - 20 < o["p"] < v.p + ahead for o in self.onc)

    def _sense(self, pod: str, v: Vehicle):
        r = self.rng
        meas = v.spd * (1 + (r.random() - 0.5) * 0.022)
        length = v.T.length * (1 + (r.random() - 0.5) * 0.06)
        sig = [_clamp(s + (r.random() - 0.5) * 0.05, 0, 1) for s in v.sig]
        track = self.on_pass(pod, self.t, meas, length, sig)
        if pod == "A":
            v.track = track
            if self.armed:
                v.fate = None if self.armed == "nominal" else self.armed
                self.focus_track = track
                self._truth(f"Scenario applied to the next vehicle at POD A ({track})")
                self.armed = None

    # ------------------------------------------------------------------ step
    def step(self, dt: float):
        self.t += dt
        self.spawn_in -= dt
        if self.spawn_in <= 0:
            self._spawn()
        self.onc_in -= dt
        if self.onc_in <= 0:
            self._spawn_onc()

        wreck = next((x for x in self.veh if x.state == "crash"), None)
        if self.secondary and self.t >= self.secondary:
            self.secondary = None
            if wreck:
                cand = min((o for o in self.veh if o.state == "run" and wreck.p - o.p > 3),
                           key=lambda o: wreck.p - o.p, default=None)
                if cand:
                    cand.state, cand.spd = "crash", 0.0
                    cand.p = wreck.p - (wreck.T.length / 2 + cand.T.length / 2 + 0.8)
        if self.halter and self.t >= self.halter:
            self.halter = None
            if wreck:
                cand = min((o for o in self.veh if o.state == "run" and 30 < wreck.p - o.p < 190),
                           key=lambda o: wreck.p - o.p, default=None)
                if cand:
                    cand.halt = self.t + 14

        hazards = [v for v in self.veh if v.state == "crash"]

        for v in self.veh:
            prev = v.p
            if v.state == "crash":
                v.spd = 0.0
                continue
            if v.state == "exit":
                v.des = max(8.5, v.des - 6 * dt)
                v.spd += _clamp(v.des - v.spd, -5 * dt, 2 * dt)
                v.exit_s += v.spd * dt / 424.0
                continue

            tgt = v.des
            lead = self._lead(v)
            gap = 1e9
            if lead:
                gap = lead.p - v.p - (lead.T.length + v.T.length) / 2
                safe = max(12.0, v.spd * 1.7)
                if gap < safe:
                    tgt = min(tgt, max(0.0, lead.spd * (gap / safe)))
                if gap < 5:
                    tgt = 0.0

            dodging = False
            for h in hazards:
                d = h.p - v.p
                if 0 < d < 48:
                    tgt = min(tgt, 1.3)
                elif 0 < d < 130:
                    tgt = min(tgt, 3.4)
                elif 0 < d < 300:
                    tgt = min(tgt, 8.5)
                elif -260 < d <= 0:
                    tgt = min(tgt, 8.0)
                if -18 < d < 70:
                    dodging = True
            if v.halt > self.t:
                tgt = 0.0

            if dodging and self._onc_clear(v, 220):
                vt = LANE_O + 0.6
            elif v.ot:
                vt = LANE_O
            else:
                vt = LANE_M

            if not dodging:
                if v.ot:
                    if not lead or gap > 16 or not self._onc_clear(v, 160):
                        v.ot = False
                elif (lead and lead.spd < v.des * 0.85 and 6 < gap < 65
                      and self.t - v.last_ot > 8 and PMIN + 40 < v.p < PB + 220
                      and not hazards and self._onc_clear(v, 240)):
                    v.ot, v.last_ot = True, self.t
                if v.ot:
                    tgt = v.des

            prev_spd = v.spd
            v.spd = max(0.0, v.spd + _clamp(tgt - v.spd, -7.5 * dt, 2.2 * dt))
            v.brake = _clamp(max(v.brake - dt * 2.2, (prev_spd - v.spd) / max(dt, 1e-4) / 4.5), 0, 1)
            v.voff += _clamp(vt - v.voff, -3.4 * dt, 3.4 * dt)
            v.p += v.spd * dt

            if prev < PA <= v.p:
                self._sense("A", v)
            if prev < self.pb <= v.p:
                self._sense("B", v)

            if v.fate == "exit":
                if v.p > EXIT - 45:
                    v.des = min(v.des, 10.5)
                if v.p >= EXIT:
                    v.state, v.fate = "exit", None
                    self._truth("Tracked vehicle turned onto the village road (invisible to ANTAR)")
            if v.fate == "crash" and v.p >= CRASH:
                v.state, v.spd, v.fate = "crash", 0.0, None
                self.secondary, self.halter = self.t + 1.6, self.t + 7
                self._truth(f"Tracked vehicle stopped at K{CRASH / 1000:.3f} (invisible to ANTAR)")

        for o in self.onc:
            o["p"] -= o["spd"] * dt
        self.onc = [o for o in self.onc if o["p"] > PMIN - 60]
        self.veh = [v for v in self.veh if v.p < PMAX and v.exit_s < 1.9]

    def arm(self, fate: str):
        self.armed = fate

    def clear_road(self):
        self.veh.clear(); self.onc.clear()
        self.secondary = self.halter = self.focus_track = self.armed = None
        self.spawn_in, self.onc_in = 0.0, 2.0

    def snapshot(self) -> list[dict]:
        return [{"id": v.id, "p": round(v.p, 1), "cls": v.T.cls, "kind": v.T.key,
                 "kmh": round(v.spd * 3.6), "state": v.state, "track": v.track,
                 "len": v.T.length, "brake": round(v.brake, 2), "lane": round(v.voff, 2)}
                for v in self.veh if v.p > PMIN]
