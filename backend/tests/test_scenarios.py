"""End-to-end: ground-truth traffic model -> pod events -> detector, across many seeds.

The detector is never told the scenario. These tests are the proof that it tells a
crash apart from a turn-off anyway.
"""
import pytest
from antar.detector import Detector
from antar.traffic import Traffic

SEEDS = range(8)


def run(fate: str, seed: int, horizon: float = 260.0):
    ev = []
    d = Detector(listener=ev.append)

    def on_pass(pod, t, v, length, sig):
        if pod == "A":
            return d.pod_a(t, v, length, sig).id
        d.pod_b(t, v, length, sig)

    tr = Traffic(on_pass, seed=seed)
    d.quiet = True
    for _ in range(1400):
        tr.step(0.2); d.tick(tr.t)
    d.quiet = False
    tr.arm(fate)
    t0 = tr.t
    while tr.t - t0 < horizon:
        tr.step(0.2); d.tick(tr.t)
    first = next((e["suspicion"] for e in ev if e["kind"] == "decision"), None)
    return first, tr.focus_track


@pytest.mark.parametrize("seed", SEEDS)
def test_scenario_a_nominal_is_quiet(seed):
    first, _ = run("nominal", seed)
    assert first is None or first["verdict"] == "dismiss"


@pytest.mark.parametrize("seed", SEEDS)
def test_scenario_b_incident_dispatches(seed):
    first, focus = run("crash", seed)
    assert first is not None and first["verdict"] == "dispatch"
    assert first["tier"] == "HIGH" and first["confidence"] >= 0.66


@pytest.mark.parametrize("seed", SEEDS)
def test_scenario_c_legal_exit_is_dismissed(seed):
    first, focus = run("exit", seed)
    assert first is not None and first["verdict"] == "dismiss"
    assert first["opened_by"] == focus
    assert first["confidence"] < 0.66


@pytest.mark.parametrize("seed", range(4))
def test_degraded_pair_still_separates_b_from_c(seed):
    """POD B dark: POD A pairs with POD C at 1290 m. Wider windows, stricter tiers,
    and the crash/turn-off discrimination must still hold."""
    def run_deg(fate):
        ev = []
        d = Detector(listener=ev.append)
        d.set_degraded(True, 1290.0)

        def on_pass(pod, t, v, length, sig):
            if pod == "A":
                return d.pod_a(t, v, length, sig).id
            d.pod_b(t, v, length, sig)

        tr = Traffic(on_pass, seed=seed, pb=1290.0)
        d.quiet = True
        for _ in range(1400):
            tr.step(0.2); d.tick(tr.t)
        d.quiet = False
        tr.arm(fate)
        t0 = tr.t
        while tr.t - t0 < 320:
            tr.step(0.2); d.tick(tr.t)
        return next((e["suspicion"] for e in ev if e["kind"] == "decision"), None)

    b, c = run_deg("crash"), run_deg("exit")
    assert b and b["verdict"] == "dispatch" and b["degraded"]
    assert c and c["verdict"] == "dismiss"
