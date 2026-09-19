# ANTAR — Sensor Systems & Working

This document explains the sensing hardware represented in the ANTAR pod and how each sensor contributes to the road-safety detection chain.

> Important: the current simulator is a software model. The descriptions below distinguish the **intended sensor role** from the **simulated behaviour shown in the demo**.
>
> **Sensor choice is still open.** The 3D pod shows an ultrasonic pair as the concept sensor. The detector itself is sensor-agnostic: it needs a passage time, a speed, a length and a repeatable 4-number signature. An ultrasonic pair, a magnetometer / inductive loop (magnetic profile) and a radar unit are all candidates, and none has been characterised on a real road yet. See `hardware/README.md`.

---

## 1. Ultrasonic Speed Detection — TX + RX

### What it is

The pod concept uses two ultrasonic sensing channels to estimate vehicle movement and speed at a pod.

- **TX** — emits the ultrasonic pulse.
- **RX** — listens for the reflected/returned signal.

In the physical concept, the two channels work together to observe a vehicle crossing the sensing zone.

### How it works

1. TX sends a short ultrasonic burst.
2. The wave reaches the vehicle.
3. Part of the energy is reflected back.
4. RX receives the echo.
5. The controller measures the timing/difference between observations.
6. Repeated measurements give a speed estimate.

The important output for ANTAR is not just "a vehicle exists". It is:

**vehicle detected → measured movement → estimated speed → timestamp**

That timestamp becomes the beginning of the vehicle's expected arrival window at the next pod.

### What the simulator shows

The road simulator creates sensor pass events at Pod A and Pod B. Each event contains:

- timestamp
- measured speed
- vehicle length estimate
- a simulated vehicle signature

The detector then calculates the expected arrival time at Pod B from the measured Pod A speed.

### Why it matters

Speed is the first piece of the temporal fingerprint.

A vehicle measured at Pod A at time `tA` and speed `v` creates an expected travel time:

`travel time = distance / speed`

This creates a window instead of a single exact deadline, allowing for normal variation in traffic.

### Colour in the 3D pod

🟢 **Green** — sensor / GPIO signal  
🔴 **Red** — power  
⚫ **Black** — ground

---

## 2. Optical Camera

### What it is

The pod includes a forward-facing camera in the physical concept.

It is intended as a visual sensing channel for future/expanded versions of ANTAR.

### Intended role

The camera can provide context that a simple presence sensor cannot:

- road scene verification
- vehicle classification
- lane/context information
- visual confirmation of unusual traffic behaviour

### What it does NOT do in the current simulator

The current road simulator does **not** use image recognition or camera footage as an input to the decision engine.

That is deliberate.

The detector is isolated from ground truth and receives only the simulated pod events. The simulation therefore proves the core inference mechanism independently of computer vision.

### Why keep it in the pod concept?

It makes the physical design extensible.

The basic ANTAR idea can operate from low-cost sensing first, while a future hardware revision can add local vision where it provides enough value to justify the cost.

---

## 3. RF Signal Catcher / Radio Link

### What it is

The signal catcher is the pod's radio-side sensing/communication element.

The physical pod includes a compact RF structure/antenna connected to the ESP32/radio module.

### Two jobs

**A. Receive**

The node can listen for neighbouring pod traffic and maintain the local mesh/relay link.

**B. Transmit**

When ANTAR reaches an alert decision, the message travels through the pod-to-pod relay chain until it reaches existing network coverage.

The design intentionally avoids putting a cellular SIM in every roadside pod.

### How the simulator represents it

The simulation models the transmission chain as:

`Pod A → Pod B → relay nodes (when enabled) → cell tower → recipients`

The transmission UI shows:

- relay hops
- per-hop latency
- tower handoff
- recipient acknowledgement

### Why it matters

This is the communications layer that turns a local road observation into a response.

The core product claim is:

**the pod detects locally; the network carries the alert.**

### 3D visual

The purple path in the pod explorer represents:

🟣 **RF / antenna feed**

The animated wave/ripple around the antenna is a visualisation of transmission activity, not a literal measurement of radio-field strength.

---

## 4. ESP32 Control Core

### What it does

The ESP32 is the central embedded controller in the pod concept.

It is responsible for:

- collecting sensor readings
- timestamping events
- maintaining local state
- communicating with neighbouring nodes
- passing data into the detection pipeline
- driving status/display outputs

The 3D model exposes the ESP32 as a real PCB-style assembly rather than a generic black box.

---

## 5. Battery + Power Layer

### Layered power concept

ANTAR uses a resilient power model:

1. existing pole power where available
2. solar generation
3. battery buffer

The reason is simple:

**a safety device cannot fail because the night-time power source failed.**

The 3D model shows the battery, power bus, I/O board and protected wiring as separate physical systems.

---

# How the Sensors Become a Decision

The important part of ANTAR is that **no single sensor says "crash".**

Instead:

### Stage 1 — Detect

Pod A measures a vehicle.

### Stage 2 — Predict

The system opens an arrival window for Pod B using the measured speed and segment distance.

### Stage 3 — Observe

Pod B either receives the matching vehicle or does not.

### Stage 4 — Candidate anomaly

If the arrival window expires without a match:

**ANTAR does NOT immediately dispatch.**

It creates a low-confidence candidate.

### Stage 5 — Corroborate

The system watches downstream traffic:

- expected flow
- observed flow
- downstream speed
- additional missing arrivals

### Stage 6 — Decide

**Normal flow → candidate dismissed**

**Traffic degradation + repeated absence → confidence rises**

**Enough evidence → alert dispatched**

This is the central design principle of ANTAR:

> **The missing vehicle creates the suspicion. The road behind it provides the corroboration.**

---

# Sensor / Connection Colour Code

| Colour | Connection | Meaning |
|---|---|---|
| 🔴 Red | Power | +VBAT / supply |
| ⚫ Black | Ground | Electrical return |
| 🟢 Green | Sensor / GPIO | Measurement and control signals |
| 🔵 Blue | Display / Data | Display and digital data lines |
| 🟣 Purple | RF / Antenna | Radio transmission path |
| 🟡 Yellow | Control | Enable / control signal |

---

# Current Demo vs Future Hardware

## Demonstrated now

- Two-pod arrival-window logic
- speed-based timing
- vehicle matching
- missing-arrival detection
- downstream-flow corroboration
- confidence tiers
- dispatch decision
- pod relay transmission model

## Physical design represented

- ESP32 control core
- ultrasonic TX/RX channels
- camera
- RF signal catcher / antenna
- battery buffer
- sensor I/O board
- front status display
- solar/power architecture

## Not claimed as physically validated by this demo

- calibrated ultrasonic hardware
- real-world RF range
- production camera inference
- final sensor BOM
- final deployment calibration

This separation keeps the prototype honest while making the intended system architecture easy to understand.
