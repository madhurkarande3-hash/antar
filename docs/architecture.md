# Architecture

> **This document describes the proposed field architecture.** None of it is deployed. What
> exists today is the browser simulator, the 3D pod concept model, and an optional backend
> reference implementation. Where this document says a pod does something, read it as what
> the design intends a pod to do once one is built.

ANTAR is four blocks. Each one has a clear job, and the boundaries between them are where
the important design decisions live.

```
   PROPOSED FIELD ARCHITECTURE

   SENSE  ─────▶  DECIDE  ─────▶  SHARE  ─────▶  SHOW
   on pod         on pod          pod → pod      display face
                                  → tower        + recipients
                                  → recipients
```

---

## 1. Sense

Each pod watches the road beneath it and produces one record per passing vehicle:

- timestamp of passage
- speed
- length class (2W / car / 3W / heavy)
- vehicle signature (a short physical fingerprint; the field sensor is not yet selected)

That is the entire sensor output. No image, no plate, no identity.

The pod is mounted by clamping to a pole that already exists — a power pole, a sign post,
an existing streetlight column. This is a deliberate constraint rather than a convenience.
New roadside civil works require land, permissions, contractors and money, and are the
main reason incident detection never reaches secondary roads. A clamp and a spanner do
not.

Power is layered: pole supply where available, solar where not, battery beneath both.
Rural power is intermittent, so the pod is designed around the assumption that its supply
will disappear regularly rather than treating that as a fault condition.

## 2. Decide

**All reasoning is meant to happen on the pod.** This is the most consequential
architectural choice in the design, and it drives most of the others.

Paired pods would exchange arrival windows with each other and evaluate matches locally.
Confidence would be computed locally, and the dispatch decision made locally, with no
server in the loop, no cloud inference and no round trip to a data centre. In this
prototype the same detector runs in the browser, and the optional backend runs a port of it
server-side as a reference implementation and control room — not because the design needs a
server, but because there is no pod to run it on yet.

Three reasons:

**Reliability.** A rural road is exactly where connectivity is worst. A system whose
decision-making depends on reaching a server is a system that stops working in the
conditions it was built for. Local decisions are intended to keep working during an
outage; that behaviour has not been tested on hardware.

**Latency.** The entire product is an argument about minutes. Adding a network dependency
to the decision path to save a small amount of on-pod computation is the wrong trade.

**Privacy.** Covered below, but briefly: if identifying information never leaves the pod,
there is no honeypot to secure.

The computation involved is not demanding — arithmetic on timestamps and speeds, a
nearest-neighbour match over a handful of open windows, and a weighted sum. It should run
comfortably on a microcontroller, though this has not been measured on the target chip. The hard part of this system is the reasoning, not the
compute.

## 3. Share

Only when a decision has actually been made does anything leave the segment.

Pods talk to their immediate neighbours over short-range radio. A message hops pod to pod
along the chain until it reaches a pod that has cellular coverage, and **only that pod
talks to the tower**.

This is what makes the economics work. Giving every pod a SIM and a data plan would add a
recurring per-pod cost that scales with deployment size and never goes away — the kind of
cost that quietly kills rural infrastructure projects two years in. Instead, most pods
need only a cheap radio, and the network borrows cellular coverage from wherever it
already happens to exist.

> **Pods carry it to the tower. The tower carries it to people.**

From the tower, the alert goes to three recipients simultaneously:

| Recipient | Role |
|---|---|
| Nearest hospital | Prepare a bed and a trauma team before the patient is moving |
| Road police | Jurisdiction, traffic control, formal response |
| Registered local responders | Opt-in, within ~2 km — the people who can be there first |

Simultaneous, not sequential. Serialising this would waste the minutes the system exists
to save.

### Resilience

If a pod goes offline, its neighbours are designed to re-pair across the wider gap so the
road stays covered. Re-pairing is implemented and tested in software; the change is not
hidden: the segment is longer, so the arrival window is
wider and less precise, and confidence in judgements about that segment drops by one tier.
The console states that this has happened and why.

The design principle is that degradation should be visible. A monitoring system that
silently becomes less reliable is worse than one that stops, because people keep trusting
it at the old level.

## 4. Show

Two audiences, two surfaces.

**On the road** — each pod is designed to carry a small amber dot-matrix display face
angled toward oncoming traffic. In normal operation it would show the pod's status, and
when an incident is confirmed ahead it would warn approaching drivers before they reach it. A driver who slows
down before a blind blockage is both safer and less likely to become the second crash.

**In the control room** — the decision console. It shows the checklist of steps the system
went through, each with a timestamp, the actual numbers involved, and a plain-language
sentence explaining the reasoning. It shows dismissed candidates as prominently as
dispatched alerts.

That last point matters. An operator needs to see what the system decided *not* to do and
why, or they have no basis for trusting what it does do.

---

## Privacy

**Identifying information does not leave the pod. There is nothing identifying to leave.**

The system never captures a registration plate, a photograph, a face, or a phone
identifier. The signature is a physical measurement (for example a magnetic profile) — it can say
"the thing at Pod B is the thing that passed Pod A ninety seconds ago" and nothing else.
It cannot be matched to a person, a vehicle registry, or a previous journey. It is
discarded once the window it belongs to closes.

What is designed to leave a pod in normal operation: nothing.

What leaves when an incident is confirmed: a location, a timestamp, a confidence value,
and the evidence behind it. Not who was involved.

The optional backend has a field-ingestion endpoint that accepts individual pass events, so
that a future pod could be developed and tested against it. Those events are held in memory
for matching and are never written to the database — see `backend/README.md`. In the
proposed architecture a deployed pod would not send them at all.

This is a stronger position than "we anonymise the data", and it is stronger on purpose.
Anonymisation is a promise about handling that has to be trusted and audited. Not
collecting the data is a property of the design that cannot be quietly reversed by a
configuration change, a policy update, or a subsequent owner of the system.

A camera-based system on the same poles could do everything ANTAR does and more. It would
also be a surveillance network pointed at every rural road it was installed on, and it
would be worth building whether or not anyone crashed. That is a different product with
different consequences, and the choice not to build it is deliberate.

---

## Where the simulation sits

`simulation/antar-sim.html` implements the software model of the **sense**, **decide** and
**show** blocks — the decision logic is real, the sensing is simulated — and models
**share** visually — the hop-by-hop relay, the tower hand-off, and
the three recipients acknowledging in sequence.

The simulation maintains a strict internal boundary that mirrors the real one: the traffic
model knows the ground truth, and the detector is only ever handed pod events
(`podA(time, speed, length, signature)` and the same for `podB`). The detector is never
told which scenario is running or that a crash occurred. Everything shown in the console
is derived from those events.

That boundary is the reason the demo means anything. If you want to check it, the
detection code is one clearly-marked block in the file and it takes no arguments other
than pod events.
