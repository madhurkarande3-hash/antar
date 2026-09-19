"""ANTAR detector — a faithful port of the detector block in simulation/antar-sim.html.

Its ONLY inputs are pod events:

    pod_a(t, speed, length, signature)
    pod_b(t, speed, length, signature)
    tick(t)

It is never told which scenario is running, where a vehicle went, or that a crash
occurred. Everything it concludes, it concludes from those calls. It has no I/O and
no clock of its own, so it runs identically in tests (instantly), in the live
simulator, and against real pod uploads.

Outputs are emitted as plain dicts through `listener(event)` so that the runtime can
persist them and push them to the control-room console.
"""
from __future__ import annotations

import math
from collections import deque
from dataclasses import dataclass, field
from typing import Callable, Optional

from .config import DEFAULT, TIERS, DetectorConfig

Listener = Callable[[dict], None]


def clamp01(v: float) -> float:
    return 0.0 if v < 0 else 1.0 if v > 1 else v


def class_of(length_m: float) -> str:
    if length_m < 3.0:
        return "2W"
    if length_m < 5.5:
        return "CAR"
    if length_m < 7.0:
        return "3W"
    return "HV"


def sig_dist(a: list[float], b: list[float]) -> float:
    return math.sqrt(sum((x - y) ** 2 for x, y in zip(a, b)))


@dataclass
class Track:
    id: str
    t_a: float
    v_a: float
    length: float
    cls: str
    dist: float
    sig: list[float]
    t_exp: float
    t_early: float
    t_late: float
    state: str = "open"          # open | closed | missed
    t_b: Optional[float] = None
    v_b: Optional[float] = None
    d_sig: Optional[float] = None

    def public(self) -> dict:
        return {
            "id": self.id, "cls": self.cls, "state": self.state,
            "t_a": round(self.t_a, 2), "v_a_kmh": round(self.v_a * 3.6, 1),
            "t_exp": round(self.t_exp, 2), "t_early": round(self.t_early, 2),
            "t_late": round(self.t_late, 2),
            "t_b": None if self.t_b is None else round(self.t_b, 2),
            "delta_s": None if self.t_b is None else round(self.t_b - self.t_exp, 2),
            "d_sig": None if self.d_sig is None else round(self.d_sig, 3),
        }


@dataclass
class Suspicion:
    evt: str
    trk: Track
    t_open: float
    t_close: float
    extra: list[Track] = field(default_factory=list)
    conf: float = 0.18
    tier: int = 0
    parts: dict = field(default_factory=dict)
    flow: dict = field(default_factory=dict)
    speeds: dict = field(default_factory=dict)
    reason: str = ""
    settled: bool = False
    t_settle: float = 0.0
    verdict: Optional[str] = None      # dispatch | dismiss
    note: str = ""
    degraded: bool = False
    history: list[dict] = field(default_factory=list)
    _last_h: float = 0.0

    def public(self) -> dict:
        return {
            "evt": self.evt, "opened_by": self.trk.id,
            "t_open": round(self.t_open, 2), "t_close": round(self.t_close, 2),
            "extra_misses": [k.id for k in self.extra],
            "confidence": round(self.conf, 3), "tier": TIERS[self.tier],
            "parts": {k: round(v, 3) for k, v in self.parts.items()},
            "flow": self.flow, "speeds": self.speeds, "reason": self.reason,
            "settled": self.settled, "t_settle": round(self.t_settle, 2),
            "verdict": self.verdict, "note": self.note, "degraded": self.degraded,
            "history": self.history[-120:],
        }


class Detector:
    def __init__(self, segment_id: str = "SEG-01", cfg: DetectorConfig = DEFAULT,
                 listener: Optional[Listener] = None, seq_start: int = 41):
        self.segment_id = segment_id
        self.cfg = cfg
        self.listener = listener or (lambda e: None)
        self.seq = seq_start
        self.tracks: deque[Track] = deque()
        self.a_det: deque[tuple[float, float]] = deque()
        self.b_det: deque[tuple[float, float]] = deque()
        self.sus: Optional[Suspicion] = None
        self.segment_m = cfg.segment_m
        self.degraded = False
        self.quiet = False            # warm-up: compute but don't emit

    # ------------------------------------------------------------------ util
    def _emit(self, kind: str, level: str, text: str, t: float, **data) -> None:
        if self.quiet:
            return
        self.listener({"kind": kind, "level": level, "text": text, "t": round(t, 2),
                       "segment": self.segment_id, **data})

    def reset(self) -> None:
        self.tracks.clear(); self.a_det.clear(); self.b_det.clear()
        self.sus = None

    def void_open(self, t: float, why: str) -> int:
        """Topology changed under open windows: they were computed for a pod that no
        longer exists, so they are voided rather than allowed to expire as false misses."""
        n = 0
        for k in self.tracks:
            if k.state == "open":
                k.state = "void"
                n += 1
        self.a_det.clear(); self.b_det.clear()
        if n:
            self._emit("windows_voided", "info", f"{n} open windows voided: {why}", t)
        return n

    def set_degraded(self, degraded: bool, segment_m: float) -> None:
        """A neighbour pod went dark: the pair re-forms across the wider gap.
        Windows widen automatically (they are computed from segment_m) and every
        confidence tier moves up one step, so the same evidence reads one tier lower."""
        self.degraded = degraded
        self.segment_m = segment_m

    # ----------------------------------------------------------------- events
    def pod_a(self, t: float, v: float, length: float, sig: list[float]) -> Track:
        c = self.cfg
        d = self.segment_m
        v = max(v, 0.5)
        k = Track(
            id=f"TRK-{self.seq:04d}", t_a=t, v_a=v, length=length, cls=class_of(length),
            dist=d, sig=list(sig),
            t_exp=t + d / v,
            t_early=t + d / (v * c.early_speedup),
            t_late=t + max(c.late_stretch * (d / v), d / c.late_floor_mps),
        )
        self.seq += 1
        self.tracks.append(k)
        self.a_det.append((t, v))
        self._emit("pass_a", "info",
                   f"POD A pass {k.id}, {k.cls}, {v * 3.6:.0f} km/h, window open "
                   f"({k.t_late - t:.0f} s)", t, track=k.public())
        return k

    def pod_b(self, t: float, v: float, length: float, sig: list[float]) -> Optional[Track]:
        c = self.cfg
        self.b_det.append((t, v))
        cls = class_of(length)
        best, bs = None, 1e9
        for k in self.tracks:
            if k.state != "open":
                continue
            if t < k.t_early - c.match_grace_s or t > k.t_late + c.match_grace_s:
                continue
            if k.cls != cls:
                continue
            dd = sig_dist(sig, k.sig)
            if dd > c.sig_max_dist:
                continue
            if dd < bs:
                bs, best = dd, k
        if best:
            best.state, best.t_b, best.v_b, best.d_sig = "closed", t, v, bs
            self._emit("match", "ok",
                       f"POD B match {best.id}, {t - best.t_exp:+.1f} s vs predicted, "
                       f"signature {bs:.3f}, {v * 3.6:.0f} km/h", t, track=best.public())
        else:
            self._emit("unmatched_arrival", "info",
                       f"POD B arrival matched no open window, {cls}, {v * 3.6:.0f} km/h", t)
        return best

    # ------------------------------------------------------------ statistics
    def tau(self, t: float) -> float:
        vs = [v for (tt, v) in self.a_det if tt >= t - self.cfg.tau_lookback_s]
        mean = sum(vs) / len(vs) if vs else self.cfg.tau_default_mps
        return self.segment_m / mean

    def flow(self, t: float) -> dict:
        c = self.cfg
        w, tau = c.flow_window_s, self.tau(t)
        exp_n = sum(1 for (tt, _) in self.a_det if t - tau - w <= tt <= t - tau)
        act_n = sum(1 for (tt, _) in self.b_det if t - w <= tt <= t)
        exp, act = exp_n * 60 / w, act_n * 60 / w
        ratio = clamp01(act / exp) if exp_n >= c.flow_min_sample else None
        return {"expected_vpm": round(exp, 2), "observed_vpm": round(act, 2),
                "sample": exp_n, "shortfall_vpm": round(max(0.0, exp - act), 2),
                "ratio": None if ratio is None else round(ratio, 3),
                "tau_s": round(tau, 1)}

    def speeds(self, t: float) -> dict:
        c = self.cfg
        up = [v for (tt, v) in self.a_det if tt >= t - c.speed_up_lookback_s]
        dn = [v for (tt, v) in self.b_det if tt >= t - c.speed_dn_lookback_s]
        u = sum(up) / len(up) if up else 0.0
        d = sum(dn) / len(dn) if dn else 0.0
        drop = clamp01(1 - d / u) if (up and dn and u > 0) else None
        return {"up_kmh": round(u * 3.6, 1), "down_kmh": round(d * 3.6, 1),
                "down_sample": len(dn), "drop": None if drop is None else round(drop, 3)}

    def open_windows(self) -> int:
        return sum(1 for k in self.tracks if k.state == "open")

    # ----------------------------------------------------------------- clock
    def tick(self, t: float) -> None:
        for k in self.tracks:
            if k.state == "open" and t > k.t_late:
                k.state = "missed"
                self._on_miss(k, t)
        if self.sus:
            self._evaluate(t)
        m = self.cfg.max_history
        for dq in (self.tracks, self.a_det, self.b_det):
            while len(dq) > m:
                dq.popleft()

    def _on_miss(self, k: Track, t: float) -> None:
        s = self.sus
        if s and not s.settled:
            s.extra.append(k)
            self._emit("miss_folded", "warn",
                       f"Missed arrival {k.id} folded into active event {s.evt}", t,
                       track=k.public(), event=s.evt)
            return
        if s and s.settled and t - s.t_settle < self.cfg.fold_after_settle_s:
            s.extra.append(k)
            self._emit("miss_folded", "warn",
                       f"Missed arrival {k.id} recorded against already-decided {s.evt}", t,
                       track=k.public(), event=s.evt)
            return
        self.sus = Suspicion(evt="EVT-" + k.id[4:], trk=k, t_open=t,
                             t_close=t + self.cfg.corroboration_s, degraded=self.degraded)
        self._emit("candidate_opened", "warn",
                   f"Candidate {self.sus.evt} opened by {k.id}: window expired with no match. "
                   f"Confidence LOW, dispatch held.", t, suspicion=self.sus.public())

    def _tier(self, conf: float, degraded: bool) -> int:
        c = self.cfg
        hi, med = (c.early_dispatch, c.tier_high) if degraded else (c.tier_high, c.tier_medium)
        return 2 if conf >= hi else 1 if conf >= med else 0

    def _evaluate(self, t: float) -> None:
        s, c = self.sus, self.cfg
        if s is None or s.settled:
            return
        s.degraded = s.degraded or self.degraded
        f, sp = self.flow(t), self.speeds(t)
        s.flow, s.speeds = f, sp

        ev_abs = c.w_absence
        ev_flow = 0.0 if f["ratio"] is None else \
            clamp01((1 - f["ratio"] - c.flow_deadzone) / c.flow_span) * c.w_flow
        ev_speed = 0.0 if sp["drop"] is None else \
            clamp01((sp["drop"] - c.speed_deadzone) / c.speed_span) * c.w_speed
        ev_miss = clamp01(len(s.extra) / c.miss_span) * c.w_miss
        s.conf = clamp01(ev_abs + ev_flow + ev_speed + ev_miss)
        s.parts = {"absence": ev_abs, "flow": ev_flow, "speed": ev_speed, "knock_on": ev_miss}
        s.tier = self._tier(s.conf, s.degraded)

        if t - s._last_h >= 1.0:
            s._last_h = t
            s.history.append({"t": round(t, 1), "exp": f["expected_vpm"],
                              "act": f["observed_vpm"], "conf": round(s.conf, 3)})

        s.reason = self._reason(s)

        if not s.degraded and s.conf >= c.early_dispatch:
            self._settle(t, True, "Evidence sufficient, early dispatch")
            return
        if t >= s.t_close:
            self._settle(t, s.tier == 2, "Corroboration window closed")

    @staticmethod
    def _reason(s: Suspicion) -> str:
        f, sp = s.flow, s.speeds
        rp = "an insufficient sample" if f["ratio"] is None else f"{f['ratio'] * 100:.0f}% of expected"
        sp_txt = ("POD B has seen no arrival at all for 45 seconds" if sp["down_sample"] == 0
                  else f"vehicles that do get through are {(sp['drop'] or 0) * 100:.0f}% slower than upstream")
        deg = " The segment is running degraded (a pod is offline), so every tier needs more evidence." \
            if s.degraded else ""
        n = len(s.extra)
        if s.tier == 2:
            misses = f", and {n} further arrival{'s are' if n != 1 else ' is'} missing too" if n else ""
            return (f"The traffic behind is testifying: downstream flow is {rp}, {sp_txt}{misses}. "
                    f"A vehicle taking a turn-off does not slow down or swallow the cars behind it.{deg}")
        if s.tier == 1:
            return (f"Downstream is starting to look wrong: flow is {rp}, {sp_txt}, with {n} "
                    f"knock-on misses. Evidence is building but not yet worth waking a hospital.{deg}")
        extra = "" if sp["down_sample"] == 0 else \
            f", pass speed matches upstream ({(sp['drop'] or 0) * 100:.0f}% apart)"
        return (f"The traffic behind is unaffected: downstream flow is {rp}{extra}, and nothing "
                f"else went missing. The road is not corroborating a crash.{deg}")

    def _settle(self, t: float, dispatch: bool, note: str) -> None:
        s = self.sus
        s.settled, s.t_settle, s.note = True, t, note
        s.verdict = "dispatch" if dispatch else "dismiss"
        if dispatch:
            self._emit("decision", "alert",
                       f"ALERT DISPATCHED for {s.evt}: confidence {s.conf:.2f} {TIERS[s.tier]}. {note}.",
                       t, suspicion=s.public())
        else:
            self._emit("decision", "clear",
                       f"Candidate {s.evt} dismissed: confidence {s.conf:.2f} {TIERS[s.tier]}. "
                       f"No alert sent. {note}.", t, suspicion=s.public())
