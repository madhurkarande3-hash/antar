# ANTAR

### The road notices when you don't arrive.

> **Try it now:** **[https://antar-ebon.vercel.app](https://antar-ebon.vercel.app)** · no install, no login, runs in your browser
> **Backup:** download this repository and double-click `index.html`. Everything works offline.
>
> **What is real and what is simulated:** [STATUS.md](STATUS.md). Short version: the
> detection logic runs for real on simulated traffic; no pod, firmware, sensor or
> emergency-service integration exists.

> **Which parts run where.** The demo — landing page, simulator and 3D pod explorer —
> runs in any modern browser on **any operating system**, with nothing to install.
> The **optional** control-room backend is a local Python service and is **preferred on
> Windows**: double-click `run.bat` and it sets itself up. It also runs on macOS and
> Linux with `bash run.sh` (Python 3.10 or newer), but Windows is the path we have
> tested most. The backend is **not needed** to judge the prototype.

## For judges: 3 minutes

1. Open the live link (or `index.html`). The intro plays each time; press **Skip** or Esc to jump past it. Add `?intro=off` to any page URL to turn it off.
2. Click **Open the simulator**.
3. Click **Scenario A**. A vehicle passes Pod A and arrives at Pod B on time. Nothing happens, which is correct.
4. Click **Scenario B**. The vehicle never arrives. ANTAR does **not** alert immediately. It watches the traffic behind for up to 90 seconds, sees it slow and bunch, and then shows **ALERT DISPATCHED**.
5. Click **Scenario C**. The vehicle again never arrives, and the first seconds look exactly like B. This time the traffic behind stays normal, so ANTAR shows **CLEARED · LEGAL EXIT** and sends nothing.
6. Optional: open the **Pod explorer** to inspect the physical pod concept in 3D.
7. **What the live link cannot show:** what happens when a pod dies. That lives in the
   control room, which runs locally. Screenshots and a five-minute setup are in
   **[docs/control-room.md](docs/control-room.md)**.

B and C are the pair that matter: *the missing vehicle creates the suspicion, the road behind it provides the corroboration.*

| What you are looking at | Status |
|---|---|
| Detection, corroboration and dispatch logic | Working, runs in the simulator |
| Traffic, crashes and turn-offs | Simulated |
| Physical pod concept (ESP32, radio, solar power) | Design prototype, not yet built or field-tested |
| Speed and signature sensor | Not yet selected. The 3D model shows an ultrasonic pair as one candidate; a magnetometer or radar are others. The detector only needs speed, length and a repeatable signature |
| Camera in the pod model | Expansion slot only, the detector does not use it |
| Control-room backend (`backend/`) | Optional extension, runs locally, not needed for the demo |

ANTAR is a proposed roadside detection system for unlit rural roads, built here as a
working simulation. The idea: work out that a crash has happened by noticing that a vehicle
which passed one pod never reached the next one, then check with the traffic behind it
whether the road is actually blocked. The detection logic runs for real in the simulator;
the pods, the sensors and the alerts to real services do not exist yet.

---

## The problem

India lost **1,72,890 people to road crashes in 2023** (MoRTH, *Road Accidents in India 2023* [1]).
Most fatal crashes happen away from national highways: 22.8% on state highways and 41.4% on
other roads, against 35.8% on national highways [1].
Some of those victims could survive if help reached them quickly. That is the gap ANTAR is aimed at.

Trauma medicine calls it the golden hour. Internal bleeding, a blocked airway, shock —
these are treatable if someone reaches you in time. The clock does not start when the
ambulance is called. It starts at impact. Every minute nobody knows is a minute spent.

Picture a district road at 2 a.m. A vehicle leaves the carriageway. There is no
streetlight, no camera, no toll gantry, no patrol. The next vehicle may be four minutes
behind, and may not see anything off the road in the dark. Nobody sees it. Nobody calls.
The golden hour is spent before anyone even knows there is a clock running.

The existing answer to this is smart highway infrastructure — gantry-mounted cameras,
incident detection, control rooms. It works. It is also planned and funded at corridor
scale: NHAI's Advanced Traffic Management System rollout pairs camera-equipped highway
stretches with command-and-control centres every 75–100 km [2], and a single city
programme such as Chennai's Intelligent Transport System is costed at roughly
₹530–650 crore [3]. At that scale it gets built on expressways and flagship national
highways first. The roads where people
actually die — state highways, district roads, the two-lane undivided routes between
towns — will not see that infrastructure in any realistic timeframe. Not because the
technology doesn't exist, but because nobody can justify the bill for a road with
seven vehicles a minute on it.

The gap is not detection technology. The gap is detection technology cheap enough to put
where the deaths are.

---

## The inversion

Almost every crash-response product on the market waits for the victim to report.

| Approach | What it needs |
|---|---|
| In-car crash detection | A recent car with the feature fitted |
| Phone crash detection | The phone intact, charged, in coverage, and the model right |
| SOS buttons and apps | A conscious person able to reach and press it |

Each of these asks something of the person the crash just happened to. That is precisely
the thing a serious crash takes away. The cases where help is needed most urgently are the
cases where the victim is least able to ask for it.

ANTAR asks nothing of the vehicle or the person in it. It does not need them to carry a
device, install an app, or stay conscious. It watches the road instead of the car, and
it looks for an **absence** rather than an impact.

Nothing arriving is a signal. It is just a signal nobody has been reading.

---

## How the detection works

> The pods described here are a proposed design. In this prototype their measurements are
> produced by the traffic simulation, and the detection logic runs on those measurements.

Two pods are designed to sit on existing roadside poles, a known distance apart — about
**700 m** in the current model. Each pod senses vehicles passing beneath it. It does not photograph them or
identify them. It records that something passed, how fast it was going, and roughly how
long it was.

When a vehicle passes **Pod A**, the pod does one piece of arithmetic. It knows the
distance to **Pod B**, and it just measured the vehicle's speed. From those two numbers it
computes when that vehicle should reach Pod B, and opens an **arrival window** around that
time. Pod B is told to expect it.

There are only three things that can then happen.

| Outcome | What it means |
|---|---|
| **Arrives inside the window** | Normal pass. Track closes. Nothing further happens. |
| **Arrives late but arrives** | Traffic, a slow truck ahead, a careful driver. Still fine — this is why the window has tolerance. |
| **Never arrives** | The vehicle left the segment somehow. This is the only case worth thinking about. |

The window needs tolerance, and getting that tolerance right matters more than it sounds.
A motorcycle measured at 75 km/h can end up crawling behind a tractor for the next half
kilometre. If the window is tight, that motorcycle looks like it vanished, and the system
cries wolf on ordinary traffic. So the late edge of the window is not set by the vehicle's
own speed alone — it is also floored by the slowest thing realistically sharing that road.
No vehicle can cross the segment slower than the slowest vehicle in front of it.

In the traffic model, this window is generous enough that ordinary behaviour — overtaking,
bunching, a bus pulling out, a bullock cart — stays inside it, while a vehicle that never
arrives falls outside. Whether the same tolerances hold on a real road is exactly what
field testing would have to establish.

Every vehicle in the segment carries its own window, all running at the same time. At the
seven vehicles a minute the model generates, that is six or seven windows open
concurrently.

Full detail: **[docs/how-it-works.md](docs/how-it-works.md)**

---

## The hard problem

Here is the part that makes this difficult, and it is the part worth judging.

**From Pod A, a crash and a legal turn-off are the same event.**

A vehicle passes Pod A. It never reaches Pod B. That is all the pod knows. The vehicle
might be in a ditch. It might equally have turned off onto a village road, stopped at a
tea stall, pulled onto the shoulder to take a call, or turned into a field track. All of
these produce an identical signal: a window that opened and never closed.

A system that alerts on every unmatched window would fire repeatedly on any road with a
turn-off on it, and a system that cries wolf gets switched off — rightly so, because a
false alarm sends an ambulance away from someone who needs it.

So an unmatched window is not treated as a crash. It is treated as a **candidate**, and
nothing is dispatched. Instead, the system stops looking at the vehicle that vanished and
starts looking at the vehicles behind it.

This is the whole idea:

> **A blockage changes the behaviour of the traffic behind it. A turn-off does not.**

That is the assumption the design rests on, and it is what the traffic model reproduces.
When a vehicle blocks a two-lane road in the model, the vehicles arriving next brake hard,
slow to a crawl, swerve across the centre line, and some stop entirely. A queue builds
upstream. Fewer vehicles reach Pod B than Pod A let through, and the ones that get through
arrive slower than they should.

When a vehicle simply turns off at a junction, none of that happens. Flow at Pod B
continues to match inflow at Pod A, speeds hold, and nothing else goes missing.

The assumption is drawn from ordinary road behaviour, but it has not been checked against
real crash data. A non-crash blockage — livestock, a breakdown, waterlogging — would
produce the same evidence, and a crash that leaves the carriageway clear would produce
none.

So ANTAR does not try to detect the crash. It asks the road to corroborate it. The
evidence for a crash is not on the vehicle that disappeared — it is on the vehicles behind
it.

### Two stages

1. **Candidate.** A window expires unmatched. Confidence starts low. Nothing is
   dispatched, and the console says so explicitly.
2. **Corroboration.** For the next **90 seconds**, the system watches downstream flow
   against upstream inflow, downstream speed against upstream speed, and whether any other
   windows are going unmatched too. Confidence moves continuously as evidence accumulates.
3. **Decision.** At the end of the window — or earlier if the evidence is overwhelming —
   the accumulated confidence either clears the dispatch threshold or it doesn't.

Confidence is a continuous range, not a switch. It is reported in tiers — low, medium,
high — with the numbers that produced it shown alongside.

**If the evidence is insufficient, no alert is sent.** Not a cautious guess, not a
low-priority ping. The candidate is closed, logged with its timestamp and its reasoning,
and the system goes quiet. The design keeps the cost of a false alarm inside the system
instead of passing it to a hospital.

---

## What happens when it does decide

> Proposed alert path. In the demo all three recipients are simulated: nothing is sent to a
> real hospital, police unit or volunteer, and no such integration exists.

An alert is designed to go to three recipients at once, not in sequence:

- **The nearest hospital** — the intent is that a bed and a trauma team know before the
  patient is moving.
- **The road police** — jurisdiction, traffic control, and the formal response.
- **Registered local responders** — people who have opted in, living within a couple of
  kilometres of that stretch.

The third tier is the one that is usually missing, and it is the one the design cares most
about. On a rural stretch an ambulance may be tens of minutes away while a neighbour is
minutes away. (Those are illustrative, not measured: we have no response-time data for any
particular road.) A neighbour cannot perform surgery, but can find the vehicle in the dark,
keep an airway clear, stop bleeding, and tell the ambulance exactly where to stop.

> **The ambulance is the right responder. The neighbour is the fast one.**

You need both, and you need them started at the same moment.

---

## Deployment (proposed design)

> Nothing in this section has been built or field-tested yet. It describes how the pod is
> designed to be installed and connected. The simulator models the relay; it does not prove it.

The economics are the point of the design, so the hardware is deliberately boring.

- **Clamp-on retrofit.** A pod is designed as a housing that clamps to a pole that already
  exists. No new civil works, no trenching, no foundations, no gantries. The aim is that
  one person with a ladder and a spanner can install it.
- **Layered power.** Pole supply where there is one, solar where there isn't, battery
  underneath both. Rural power is intermittent; the pod is designed to expect that rather
  than to fail on it.
- **Pod-to-pod relay.** Pods are designed to talk to their neighbours over short-range radio
  and hand the message along the chain until it reaches a pod that has cellular coverage.
  Only that pod talks to the tower, so most pods need no SIM, no data plan and no recurring
  connectivity cost. Real radio range between poles has not been measured yet.
- **Target cost: under ₹2,500 per pod.** This is a design target; a costed bill of materials has not been produced yet.

That last number is the entire argument. Existing incident detection is not too primitive
for these roads — it is too expensive for them. The design targets a few thousand rupees
per pole so that, if it is built and proven, it can be afforded on the roads where the
deaths actually happen.

> Pods carry it to the tower. The tower carries it to people.

---

## Resilience (proposed, modelled in software)

> Re-pairing is implemented and tested in the detector and the backend. No physical pod has
> ever gone dark on a real road, because no pod has been built.

Rural deployments lose nodes. Equipment is stolen, struck, flooded, or simply runs out of
battery in a bad monsoon week. A system that stops working when one pod dies is not a
system anyone should install.

When a pod goes offline, its two neighbours are designed to re-pair with each other across
the wider gap, so the stretch stays covered. In the simulation the consequences are honest
and visible:

- The segment being monitored is now longer.
- The arrival window is therefore wider and less precise.
- Confidence in any judgement about that segment **drops by one tier**, and the console
  says why.

**Seeing this for yourself:** the re-pairing is not visible on the live link, because it
belongs to the control room. **[docs/control-room.md](docs/control-room.md)** has
screenshots of a pod going dark and of an alert still getting out on the degraded segment,
plus the five-minute setup if you would rather run it.

In the 120-run replay (see *What is proven*), the re-paired configuration still separated
crashes from turn-offs, though the alert took far longer and the margin narrowed. The
design degrades rather than failing, and it does not quietly pretend it is as certain as
it was.

---

## Running the simulation

Open **[`simulation/antar-sim.html`](simulation/antar-sim.html)** in any modern browser.
Double-click it. That is the whole process.

There is also an interactive physical pod concept at **[`pod/index.html`](pod/index.html)**.
The repository root **[`index.html`](index.html)** is the demo hub that links to both. The same files are what the live link serves.

No dependencies. No build step. No package manager. No server. No internet connection.
Everything — the traffic model, the detection logic, the rendering — is in that one file.

This is worth a sentence of explanation, because "it's just an HTML file" can read as a
shortcut. It isn't one. It mirrors the proposed field architecture, in which the reasoning
would happen locally on the pod, with no cloud service in the loop and no dependency on
anything being reachable. A demo that needs a server to prove a system that must work
without one would be arguing against itself.

The top half of the screen is the road — **ground truth**, what actually happened.
The bottom half is the console — **only what ANTAR can actually perceive**. The
simulation never tells the detector that a crash occurred. The detector has access to
exactly two kinds of event: a vehicle passed Pod A, and a vehicle passed Pod B. Everything
else it concludes, it concludes from those.

That separation is deliberate, and it is the thing to check if you are sceptical. The
detection logic is not reading the scenario you picked.

---

## The three scenarios

One button each. Everything else — traffic generation, speeds, timing, pod communication —
runs on its own.

### Scenario A · Nominal
A vehicle passes Pod A and arrives at Pod B as predicted. The track closes. No candidate,
no alert, nothing sent.

*Demonstrates: the normal path, which is what happens to virtually every vehicle. A system
that is quiet almost all the time is a system that works.*

### Scenario B · Incident
The tracked vehicle stops on the carriageway between the pods. Its window expires
unmatched. The traffic behind it brakes hard, bunches into a queue, swerves around the
site, and one vehicle stops entirely. Downstream flow at Pod B falls well below inflow at
Pod A, arriving vehicles are much slower than upstream, and further windows start going
unmatched. Confidence climbs into the high tier and the alert dispatches.

*Demonstrates: corroboration working. The system did not see the crash — it inferred a
blockage from the behaviour of vehicles that were never involved in it.*

### Scenario C · Legal exit
The tracked vehicle turns off onto the village road. Its window expires unmatched, exactly
as in Scenario B — the candidate opens identically. But the traffic behind is completely
unaffected. Flow holds, speeds hold, nothing else goes missing. After the full 90 seconds,
confidence is still low. The candidate is dismissed and logged. No alert.

*Demonstrates: the discrimination the whole design depends on. B and C are
indistinguishable at the moment of absence and are separated only by evidence gathered
afterwards.*

Scenarios B and C are the pair to watch together. If a judge only has time for one thing,
it is running B and then C and noticing that the first thirty seconds are identical.

Detail on all three: **[docs/scenarios.md](docs/scenarios.md)**

---

## What is proven, and what is not

We would rather be trusted than impressive, so here is the honest boundary.

**Demonstrated in this repository, on simulated traffic**

- The detection loop end to end: measure, predict, open a window, match or fail to match.
- Concurrent tracking of every vehicle in the segment, not one at a time.
- The discrimination logic — crash versus legal exit — from corroborating evidence only.
- Continuous confidence with an explicit dispatch threshold, and refusal to alert when the
  evidence isn't there.
- A simulated relay and hand-off model from pod to pod to tower to simulated recipients.
- A decision console that shows its reasoning step by step, in plain language, with
  timestamps on every event including dismissed candidates.

**Measured, and reproducible**

Run `python tools/replay.py` inside `backend/`. It replays the detector against simulated
traffic it has never seen, 20 seeds for each of the three scenarios, once with all pods
healthy and once with a pod switched off:

| Run | Result |
|---|---|
| All 120 runs | **120/120** ended in the expected decision |
| Incident, healthy pods | dispatched every time, confidence 0.83–0.89 |
| Incident, one pod dark | dispatched every time, confidence 0.84–0.97 |
| Legal exit | dismissed every time; confidence peaked at 0.53 healthy, 0.63 re-paired, against a 0.66 threshold |
| Time from the vehicle stopping to the alert | **67 s median, 100 s worst** with healthy pods; **199 s median** when re-paired across the wider gap |

`--seeds 40` runs the larger 240-run sweep. Every number here comes from the traffic model,
not from a road. The margin in the legal-exit case is narrower when a pod is dark, which is
one reason confidence drops a tier in that state.

**Not yet done**

- **Field validation.** The traffic model is a model. Real rural traffic will be messier,
  and the tolerance and confidence parameters will need tuning against real road data.
- **Hardware.** The pod is specified and the firmware track is scoped, but no pod has been
  built and mounted on a pole.
- **Sensor selection.** The simulation assumes a sensor that can time a passage, estimate
  speed and length, and produce a repeatable signature. Choosing the actual sensor and
  characterising it in weather is real work that has not been done.
- **Weatherproofing, certification, road-authority approval.** None of this is started.
- **Emergency service integration.** Dispatching to a real hospital or control room needs
  agreements and interfaces that a hackathon cannot produce.
- **Adversarial cases.** Livestock, waterlogging, a stopped vehicle that is not a crash,
  festival traffic. Some of these will produce false positives and need work.

This is a hackathon prototype. Within the traffic model it shows that the hard part —
telling a crash apart from an ordinary turn-off — has a workable answer. It does not show a
product ready for a road, and nothing here has been tested outside the simulation.

---

## Optional: control-room extension

**Not needed to run or judge the prototype.** The simulator is the prototype. This folder
explores what the control room behind the tower could look like, and it needs Python on
your own machine.

**Windows:** double-click `run.bat`. **macOS / Linux:** `./run.sh`. **VS Code:** open the
folder and press `Ctrl+Shift+B` after running the first-time setup task. Needs Python 3.10
or newer; the first run installs FastAPI and uvicorn into a local virtual environment.

Then open **http://127.0.0.1:8000** for the live console and **/docs** for the API.

Once it is up, this is the sequence worth running — it is the part the live link cannot
show:

1. Press **Scenario B**, watch the alert dispatch, then **Acknowledge** and **Resolve**.
2. Press **Scenario C** and watch an identical absence get dismissed.
3. In the **PODS** panel, press **Take offline** on POD B. POD A re-pairs with POD C
   across 1290 m and the threshold rises from 0.66 to 0.82.
4. Press **Scenario B** again. The crash is still caught on the degraded segment; it just
   takes longer and needs more evidence.

Step-by-step with screenshots: **[docs/control-room.md](docs/control-room.md)**

The detector in `backend/antar/detector.py` is a direct port of the one in the simulator,
with the same numbers. Two separate things run against it: the 51-test suite, which covers
scenarios A, B and C across eight random seeds each along with the API behaviour, and
`tools/replay.py`, the larger sweep quoted above. Around it the backend adds
incident de-duplication, simultaneous three-tier alert fan-out, pod heartbeats with
automatic re-pairing, a responder registry, a field ingestion API for pod firmware, and a
database that by design never stores an individual vehicle pass.

Full detail: **[backend/README.md](backend/README.md)**

---

## Repository map

```
antar/
├── README.md                     you are here
├── LICENSE                       MIT
├── index.html                    demo hub (what the live link opens)
├── vercel.json                   static hosting config
├── run.bat / run.sh              optional: launch the local backend
├── .vscode/                      tasks, debugger and test config
├── backend/                      optional control-room extension
│   ├── antar/                    detector, traffic model, API, dispatch, store, console
│   ├── tests/                    51 tests incl. multi-seed scenario checks
│   ├── tools/replay.py           the 120-run replay behind the quoted figures
│   ├── render.yaml               optional cloud deploy for the backend
│   └── README.md                 how the backend works and how to run it
├── simulation/
│   └── antar-sim.html            road-safety simulator
├── pod/
│   └── index.html                interactive 3D pod explorer
├── STATUS.md                     built / simulated / not built, in one page
├── LINKS.txt                     live demo and repository links
├── docs/
│   ├── how-it-works.md           the detection algorithm in detail
│   ├── architecture.md           proposed system structure and privacy position
│   ├── scenarios.md              what each scenario shows
│   ├── control-room.md           running the backend and watching a pod fail over
│   ├── diagrams.md               text diagrams of the system and the decision flow
│   ├── pod-explorer.md           what the 3D model represents
│   └── SENSOR_SYSTEMS.md         sensor concepts and what is not selected yet
├── hardware/
│   └── README.md                 the physical pod specification (nothing built)
└── assets/                       intro animation, fonts, bundled Three.js
```

---

## Sources

1. Ministry of Road Transport and Highways, *Road Accidents in India 2023* (released August 2025). Figures as reported in: [DT Next / PTI](https://www.dtnext.in/news/national/172-lakh-people-died-in-480-lakh-road-accidents-in-2023-road-ministry-report-844831) and [Business Standard](https://www.business-standard.com/india-news/road-accidents-up-4-2-in-2023-172k-lives-lost-despite-safety-push-125082901336_1.html) (share of fatal accidents by road type); dataset: [OpenCity](https://data.opencity.in/dataset/road-accidents-in-india-2023).
2. Business Standard, *NHAI plans ATMS for highways* (June 2026), for the control centres every 75–100 km: [link](https://www.business-standard.com/economy/news/nhai-atms-national-highways-traffic-management-delhi-ncr-126062600294_1.html).
3. DT Next, *Centre approves Rs 530 cr for intelligent transport system in Chennai* (₹530 crore project cost; tender estimate about ₹645.59 crore): [link](https://www.dtnext.in/news/chennai/centre-approves-rs-530-cr-for-intelligent-transport-system-in-chennai).

All ANTAR performance figures (120/120, 67 s median to alert) come from the traffic
simulation, not from field data. They are reproducible with `backend/tools/replay.py`.
The ₹2,500 per pod figure is a design target, not a quoted price.

---

## Team

**Madhur Karande** (lead) · **Mrigaj Waikar** · **Arahant Kankal**

---

## Licence

MIT. See [LICENSE](LICENSE).

- [Sensor Systems & Working](docs/SENSOR_SYSTEMS.md) — detailed sensing, wiring, and component behaviour
