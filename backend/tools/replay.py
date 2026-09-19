"""Replay the ANTAR detector against simulated traffic and report what it decided.

This is the script behind the numbers quoted in the README and on the landing page.
Everything here is SIMULATED: the traffic, the crash, the turn-off and the timings.
No field data is involved, and no pod hardware exists.

    cd backend
    python tools/replay.py            # 20 seeds per scenario, healthy + degraded = 120 runs
    python tools/replay.py --seeds 40 # the larger 240-run sweep
    python tools/replay.py --mode healthy --seeds 5   # quick check

For each scenario it reports how many runs ended in the expected decision, the
confidence reached, and - for the incident scenario - the simulated time from the
moment the vehicle stops on the road to the moment the detector dispatches.
"""
import argparse
import statistics as st
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from antar.detector import Detector          # noqa: E402
from antar.traffic import Traffic            # noqa: E402

SCENARIOS = {"nominal": "dismiss-or-nothing", "crash": "dispatch", "exit": "dismiss"}


def run(fate: str, seed: int, degraded: bool = False):
    """One run. Returns (decision or None, seconds from the stop to the decision)."""
    events = []
    det = Detector(listener=events.append)
    pod_b = 700.0
    horizon = 260.0
    if degraded:                       # POD B dark: POD A re-pairs with POD C, 1290 m away
        det.set_degraded(True, 1290.0)
        pod_b, horizon = 1290.0, 320.0

    def on_pass(pod, t, speed, length, sig):
        if pod == "A":
            return det.pod_a(t, speed, length, sig).id
        det.pod_b(t, speed, length, sig)

    traffic = Traffic(on_pass, seed=seed, pb=pod_b)
    det.quiet = True
    for _ in range(1400):              # warm up: fill the road, establish the baseline
        traffic.step(0.2)
        det.tick(traffic.t)
    det.quiet = False

    traffic.arm(fate)
    start = traffic.t
    t_stop = None
    while traffic.t - start < horizon:
        traffic.step(0.2)
        det.tick(traffic.t)
        if t_stop is None and any(v.state in ("crash", "exit") for v in traffic.veh):
            t_stop = traffic.t         # ground truth: the vehicle has left the road

    decisions = [e["suspicion"] for e in events if e["kind"] == "decision"]
    first = decisions[0] if decisions else None
    delay = (first["t_settle"] - t_stop) if (first and t_stop) else None
    return first, delay


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--seeds", type=int, default=20, help="traffic seeds per scenario")
    ap.add_argument("--mode", choices=("both", "healthy", "degraded"), default="both")
    ap.add_argument("--first-seed", type=int, default=100)
    args = ap.parse_args()

    total = correct = 0
    modes = {"both": (False, True), "healthy": (False,), "degraded": (True,)}[args.mode]
    print(f"{args.seeds} seeds per scenario, {args.mode} "
          f"= {args.seeds * 3 * len(modes)} runs. All figures are simulated.\n")
    for degraded in modes:
        label = "one pod dark (re-paired)" if degraded else "all pods healthy"
        print(f"-- {label}")
        for fate, expected in SCENARIOS.items():
            ok, delays, confs = 0, [], []
            for seed in range(args.first_seed, args.first_seed + args.seeds):
                decision, delay = run(fate, seed, degraded)
                if fate == "nominal":
                    ok += decision is None or decision["verdict"] == "dismiss"
                elif fate == "crash":
                    if decision and decision["verdict"] == "dispatch":
                        ok += 1
                        if delay is not None:
                            delays.append(delay)
                else:
                    ok += bool(decision and decision["verdict"] == "dismiss")
                if decision:
                    confs.append(decision["confidence"])
            total += args.seeds
            correct += ok
            line = f"   {fate:<8} expected {expected:<18} {ok}/{args.seeds} correct"
            if confs:
                line += f" · confidence {min(confs):.2f}-{max(confs):.2f}"
            if delays:
                line += (f" · stop to alert {st.median(delays):.0f}s median, "
                         f"{max(delays):.0f}s worst")
            print(line)
    print(f"\nTOTAL {correct}/{total} correct decisions (simulated traffic).")
    return 0 if correct == total else 1


if __name__ == "__main__":
    raise SystemExit(main())
