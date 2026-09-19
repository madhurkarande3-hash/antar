# ANTAR backend

Optional reference implementation of the control room that would sit **behind the tower**.

> Demo-grade software, not deployed infrastructure. Every pod, every vehicle and every
> alert recipient here is simulated. No hospital, police unit or volunteer is contacted,
> there is no operator authentication, and storage is ephemeral.

The simulator in `simulation/antar-sim.html` demonstrates the detection logic in a browser.
This backend puts a service around that same logic: live decisions over WebSockets, a
database of incidents, three-tier alert routing, pod health and re-pairing, a responder
registry, and an API that future pod firmware could post to.

The proposed field architecture keeps the decision on the pod. The detector in
`antar/detector.py` is a line-by-line port of the browser detector, with no I/O and no
clock, and is the reference a future ESP32 firmware would have to match. It runs
server-side here because there is no pod to run it on, and because that lets the whole
chain be exercised and tested end to end.

## Run it

**Windows:** double-click `run.bat` in the repository root.
**macOS / Linux:** `./run.sh`
**VS Code:** open the repository folder, then
1. `Ctrl+Shift+P` → *Tasks: Run Task* → **ANTAR: set up backend (first time)**
2. `Ctrl+Shift+B` → **ANTAR: run backend on localhost:8000**
   or press `F5` → **ANTAR backend (debug)** to run with breakpoints.

Then open:

| URL | What |
|---|---|
| http://127.0.0.1:8000 | Control-room console (press scenario B, then C) |
| http://127.0.0.1:8000/docs | Interactive API docs, every endpoint is clickable |
| http://127.0.0.1:8000/demo/ | The original simulator and pod explorer, served locally |

Needs Python 3.10 or newer. Nothing else: the database is SQLite from the standard library.

## Test it

```
cd backend
.venv\Scripts\python -m pytest -q        # Windows
.venv/bin/python -m pytest -q            # macOS / Linux
```

51 tests. The important ones are in `tests/test_scenarios.py`: the traffic model is run
across eight random seeds per scenario and the detector — which is never told the
scenario — must stay quiet for A, dispatch for B and dismiss C every time. The same pair
is repeated with POD B offline, to check that the discrimination survives a degraded
segment.

For a larger sweep, `python tools/replay.py` replays the detector across 20 seeds per
scenario, healthy and degraded (120 runs), and reports the decisions, the confidence range
and the simulated time from the vehicle stopping to the alert. It is the source of the
figures quoted in the top-level README.

## Layout

```
backend/
├── antar/
│   ├── config.py      every tunable number, matching docs/how-it-works.md
│   ├── detector.py    windows, matching, corroboration, confidence (pure logic)
│   ├── traffic.py     ground-truth traffic model, ported from the simulator
│   ├── runtime.py     segments: ticks detector, pods, re-pairing, incident handling
│   ├── dispatch.py    pod-to-pod relay path and simultaneous three-tier fan-out
│   ├── store.py       SQLite: incidents, alerts, responders, audit log
│   ├── api.py         FastAPI routes + WebSocket
│   └── static/        console.html, the control-room UI
├── tests/
├── requirements.txt
└── requirements-dev.txt
```

## What the backend adds beyond the simulator

**Incident de-duplication.** A blocked road keeps producing missed windows, so the
detector keeps re-confirming the same blockage. The backend folds every re-confirmation
into the active incident instead of raising a second alert. The incident records how
many times it was re-confirmed.

**Simultaneous alert fan-out.** The three simulated recipients — hospital, highway patrol
and local responders — are notified at the same moment with `asyncio.gather`, after the
message relays pod to pod to the tower in the model. Offline pods are skipped in the relay path. Every delivery is stored with its
latency.

**Pod health and re-pairing.** Simulated pods send heartbeats (a real pod would do the
same). A pod that misses 90 seconds of heartbeats (or is taken offline from the console) is marked dark, POD A re-pairs with the
next online pod, open windows are voided rather than allowed to expire as false misses,
the segment length grows, and every confidence tier needs more evidence: HIGH requires
0.82 instead of 0.66 and early dispatch is disabled.

**Privacy by schema.** Individual vehicle passes and vehicle signatures are never written
to disk. The database holds decisions, their evidence, and the alerts they caused. The
test suite checks this.

**Incident lifecycle.** dispatched → acknowledged → resolved, strictly in that order: no skipping, no going back.
Dismissed candidates are a closed record and cannot be edited.

**Responder registry.** Opt-in responders per segment, with the 2 km radius enforced by
the API.

**Field ingestion.** `SEG-FIELD-01` has no traffic model. It only knows what pods upload,
which is where firmware will post:

```
POST /api/segments/SEG-FIELD-01/pass
{"pod": "POD A", "speed_mps": 21.4, "length_m": 4.3, "signature": [0.12, 0.55, 0.81, 0.33]}

POST /api/segments/SEG-FIELD-01/pods/POD%20B/heartbeat
{"battery_pct": 71, "rssi_dbm": -80, "power": "solar"}
```

Nodes on the field segment start online and go dark after 90 seconds unless a client heartbeats.
That is intended: the console should never claim a pod is healthy when it has not heard
from it.

## Public demo mode

Set `ANTAR_PUBLIC_DEMO=1` when the backend is on the internet (the included `render.yaml` does).
Anyone can still run scenarios, take pods offline and watch re-pairing. Closed to the public:
adding or deleting responders (phone numbers), the test-alert endpoint, and Telegram alerts.
Set `ANTAR_POD_KEY` and any client using the field-ingestion API must send it in an
`X-Pod-Key` header to upload passes and heartbeats. No real pod exists to use it yet.

## Optional Telegram test notifications

This sends messages to **your own** Telegram chat so you can see the fan-out arrive on a
phone during a demo. It is not an emergency-service integration.

1. In Telegram, message **@BotFather** → `/newbot` → copy the token.
2. Send your new bot any message.
3. Open `https://api.telegram.org/bot<TOKEN>/getUpdates` and copy the number in `"chat":{"id": ...}`.
4. Copy `backend/.env.example` to `backend/.env` and paste both values.
5. Restart the backend, open `/docs`, run **POST /api/alerts/test**. Your phone should buzz.

Then scenario B sends three test messages at once, labelled hospital, patrol and local
responders. All three go to your chat; none of them reach a real service.

## Configuration

| Variable | Default | Effect |
|---|---|---|
| `ANTAR_DB` | `backend/data/antar.db` | SQLite file location |
| `ANTAR_SEED` | random | Fix the traffic model's random seed for reproducible demos |
| `ANTAR_WEBHOOK_URL` | unset | Also POST every alert as JSON to this URL (n8n, an SMS gateway) |
| `ANTAR_TELEGRAM_BOT_TOKEN` + `ANTAR_TELEGRAM_CHAT_ID` | unset | Push every alert to a phone via a Telegram bot, one message per tier |
| `ANTAR_LOG_LEVEL` | `INFO` | Python logging level |
| `ANTAR_HOST` | `127.0.0.1` | `run.sh` only. Set to `0.0.0.0` to reach it from other devices on your network |

## Honest limits

Alerts are delivered to a console channel with realistic latency, plus an optional
webhook. No real hospital or police system is connected; that needs agreements a
hackathon cannot produce. There is no operator authentication on the API: this is a demo-grade
reference implementation, not production-secure infrastructure. Public demo mode
(`ANTAR_PUBLIC_DEMO=1`) closes the responder and test-alert endpoints and the pod key
protects field uploads, but that is not a substitute for real access control. Keep it on
localhost or behind a reverse proxy with auth.

Storage is SQLite. The optional Render deployment writes it to `/tmp`, which is
ephemeral: incidents and alerts are lost whenever the service restarts or sleeps. The
public demo uses ephemeral demo storage; a production deployment would use persistent
storage.

The sample responders (for example "Ramesh Yadav") and hospital and patrol names are
fictional.
