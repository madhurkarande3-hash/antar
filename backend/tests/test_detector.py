"""Unit tests for the detector: the numbers in docs/how-it-works.md, checked directly."""
import pytest
from antar.detector import Detector, class_of

SIG = [0.2, 0.4, 0.6, 0.8]


def det():
    ev = []
    return Detector(listener=ev.append), ev


def test_arrival_window_matches_docs():
    d, _ = det()
    k = d.pod_a(0.0, 25.0, 4.2, SIG)              # fast car, 90 km/h
    assert k.t_exp == pytest.approx(28.0)
    assert k.t_early == pytest.approx(700 / (25 * 1.30))
    assert k.t_late == pytest.approx(max(1.35 * 28.0, 700 / 9.0))   # floor wins: ~77.8 s


def test_length_classes():
    assert [class_of(x) for x in (1.9, 4.2, 6.0, 10.5)] == ["2W", "CAR", "3W", "HV"]


def test_on_time_arrival_closes_window():
    d, ev = det()
    d.pod_a(0.0, 20.0, 4.2, SIG)
    m = d.pod_b(35.0, 20.0, 4.3, [0.21, 0.41, 0.59, 0.8])
    assert m and m.state == "closed"
    d.tick(200.0)
    assert d.sus is None


def test_class_and_signature_gates_reject_wrong_vehicle():
    d, _ = det()
    d.pod_a(0.0, 20.0, 4.2, SIG)
    assert d.pod_b(35.0, 20.0, 10.0, SIG) is None                 # bus != car
    assert d.pod_b(35.0, 20.0, 4.2, [0.9, 0.1, 0.1, 0.1]) is None  # different signature


def test_lone_absence_never_dispatches():
    """0.18 on its own can never reach the threshold, no matter how long you wait."""
    d, ev = det()
    d.pod_a(0.0, 20.0, 4.2, SIG)
    for t in range(0, 400):
        d.tick(float(t))
    decisions = [e for e in ev if e["kind"] == "decision"]
    assert len(decisions) == 1
    assert decisions[0]["suspicion"]["verdict"] == "dismiss"


def test_degraded_segment_raises_every_tier():
    d, _ = det()
    d.set_degraded(True, 1290.0)
    assert d._tier(0.70, degraded=True) == 1     # would be HIGH on a healthy pair
    assert d._tier(0.70, degraded=False) == 2
    k = d.pod_a(0.0, 20.0, 4.2, SIG)
    assert k.dist == 1290.0


def test_void_open_prevents_false_misses():
    d, ev = det()
    d.pod_a(0.0, 20.0, 4.2, SIG)
    d.void_open(1.0, "test")
    for t in range(0, 300):
        d.tick(float(t))
    assert d.sus is None
