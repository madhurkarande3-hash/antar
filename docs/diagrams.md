# Diagrams

Text diagrams of how ANTAR is put together. Two different things are drawn here, and it
matters which is which:

- **Proposed field system** — what would exist on a road. Not built.
- **What exists today** — the prototype in this repository.

---

## 1. The proposed field system

```
        traffic
           │
  ─────────┼──────────────── road ──────────────────────────────
           ▼                        ▼
      ┌─────────┐   700 m      ┌─────────┐        ┌─────────┐
      │  POD A  │◀────────────▶│  POD B  │◀──────▶│  POD C  │ ...
      └────┬────┘   radio      └────┬────┘ radio  └────┬────┘
           │                        │                  │
   senses a passage          expects the vehicle   relays onward
   opens a window            matches or doesn't    until one pod
   decides locally           decides locally       has cell signal
                                                        │
                                                        ▼
                                                  ┌───────────┐
                                                  │   TOWER   │
                                                  └─────┬─────┘
                                     ┌──────────────────┼──────────────────┐
                                     ▼                  ▼                  ▼
                                 hospital        highway patrol     neighbours
                                                                    within ~2 km

  All three at the same moment, never in sequence.
  NOT BUILT: no pod, no firmware, no radio, no real recipient.
```

Why decisions sit on the pod: the roads this is for have the worst connectivity, so a
system that must reach a server to think is a system that stops thinking exactly where it
is needed.

---

## 2. What exists today

```
   ┌──────────────────────────────────────────────────────────────┐
   │  BROWSER — simulation/antar-sim.html    (the prototype)      │
   │                                                              │
   │   traffic model  ──pod events──▶  detector  ──▶  console     │
   │   (ground truth)                  (decides)      (explains)  │
   │        │                                                     │
   │        └── the detector is never handed the ground truth     │
   └──────────────────────────────────────────────────────────────┘

   ┌──────────────────────────────────────────────────────────────┐
   │  BROWSER — pod/index.html        3D concept model of the pod │
   └──────────────────────────────────────────────────────────────┘

   ┌──────────────────────────────────────────────────────────────┐
   │  OPTIONAL — backend/   (not needed for the demo)             │
   │                                                              │
   │   traffic model ─▶ detector (port) ─▶ incidents ─▶ dispatch  │
   │                          │                 │          │      │
   │                          ▼                 ▼          ▼      │
   │                     WebSocket          SQLite    simulated   │
   │                     → console          (ephemeral) recipients│
   │                                                              │
   │   field-ingestion API: accepts pass events from a future pod │
   └──────────────────────────────────────────────────────────────┘
```

---

## 3. The decision flow

This is the part that actually runs. Everything below happens inside the detector.

```
   vehicle passes POD A
           │
           ├── measure: time, speed, length, signature
           ▼
   open an ARRIVAL WINDOW at POD B
   (0.55× to 1.30× of the predicted time, with a slow-vehicle floor)
           │
           ▼
   ┌───────────────┐   matched    ┌──────────────────────────┐
   │ POD B watches │─────────────▶│ track closed. Nothing     │
   │ for a match   │              │ happens. Correct.         │
   └───────┬───────┘              └──────────────────────────┘
           │ window expired, no match
           ▼
   CANDIDATE opened  ── absence alone is worth only 0.18 confidence,
           │             which can never reach the threshold by itself
           ▼
   CORROBORATION WINDOW · up to 90 s
   stop watching the missing vehicle, watch the traffic behind it
           │
           ├── downstream flow at POD B vs upstream inflow at POD A   (weight 0.46)
           ├── downstream speed vs upstream speed                     (weight 0.22)
           ├── other windows expiring unmatched in the same stretch   (weight 0.20)
           └── the original absence                                   (weight 0.18)
           │
           ▼
      CONFIDENCE  ──────────────────────────────────────────────┐
           │                                                     │
   ≥ 0.82 at any moment            ≥ 0.66 when the window closes │
           │                                │                    │
           ▼                                ▼                    ▼
     DISPATCH NOW                      DISPATCH             below 0.66
                                                                 │
                                                                 ▼
                                                     DISMISSED, logged with
                                                     its reasoning. No alert.
```

The same absence starts Scenario B and Scenario C. Only the evidence gathered afterwards
separates them.

---

## 4. Degraded mode

```
   normal:     POD A ◀──── 700 m ────▶ POD B          confidence as usual
                                        ✗ dark
   re-paired:  POD A ◀──────── 1290 m ────────▶ POD C
                     wider segment
                     → window wider and less precise
                     → dispatch needs 0.82 instead of 0.66
                     → early dispatch disabled
                     → the console says why
```

Degradation is meant to be visible. A monitoring system that quietly becomes less reliable
is worse than one that stops, because people keep trusting it at the old level.
