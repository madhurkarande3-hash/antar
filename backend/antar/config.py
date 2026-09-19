"""Every tunable number in one place. Values match docs/how-it-works.md exactly."""
from dataclasses import dataclass


@dataclass(frozen=True)
class DetectorConfig:
    # geometry
    segment_m: float = 700.0          # POD A -> POD B

    # arrival window
    early_speedup: float = 1.30       # tEarly = t + D / (v * 1.30)
    late_stretch: float = 1.35        # tLate  = t + max(1.35 * D/v, D / 9.0)
    late_floor_mps: float = 9.0
    match_grace_s: float = 2.0
    sig_max_dist: float = 0.16

    # corroboration
    corroboration_s: float = 90.0
    flow_window_s: float = 90.0
    flow_min_sample: int = 5
    tau_lookback_s: float = 180.0
    tau_default_mps: float = 18.0
    speed_up_lookback_s: float = 120.0
    speed_dn_lookback_s: float = 45.0
    fold_after_settle_s: float = 40.0

    # confidence
    w_absence: float = 0.18
    w_flow: float = 0.46
    w_speed: float = 0.22
    w_miss: float = 0.20
    flow_deadzone: float = 0.10
    flow_span: float = 0.55
    speed_deadzone: float = 0.08
    speed_span: float = 0.40
    miss_span: float = 3.0

    # tiers
    tier_medium: float = 0.35
    tier_high: float = 0.66           # dispatch threshold
    early_dispatch: float = 0.82

    # housekeeping
    max_history: int = 400


DEFAULT = DetectorConfig()
TIERS = ("LOW", "MEDIUM", "HIGH")
