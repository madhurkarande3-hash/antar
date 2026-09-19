"""HTTP + WebSocket API.

    uvicorn antar.api:app --reload          (from the backend/ folder)

Open http://127.0.0.1:8000           control-room console
     http://127.0.0.1:8000/docs      interactive API docs (try every endpoint)
     http://127.0.0.1:8000/demo/     the original simulator + pod explorer, served locally
"""
from __future__ import annotations

import logging
import os
from contextlib import asynccontextmanager
from pathlib import Path
from typing import Literal, Optional

from fastapi import Depends, FastAPI, Header, HTTPException, Query, WebSocket, WebSocketDisconnect
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse, RedirectResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, Field

from . import __version__
from .dispatch import Dispatcher, Recipient
from .runtime import SCENARIOS, Runtime, Segment, clock
from .store import Store

def _load_dotenv(path: Path) -> None:
    """Read backend/.env (KEY=value lines) so secrets never go in code. Real env vars win."""
    if not path.is_file():
        return
    for line in path.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, _, val = line.partition("=")
        os.environ.setdefault(key.strip(), val.strip().strip('"').strip("'"))


_load_dotenv(Path(__file__).resolve().parent.parent / ".env")

logging.basicConfig(level=os.getenv("ANTAR_LOG_LEVEL", "INFO"),
                    format="%(asctime)s %(levelname)-7s %(name)s: %(message)s")

HERE = Path(__file__).resolve().parent
REPO_ROOT = HERE.parent.parent
DB_PATH = os.getenv("ANTAR_DB", str(HERE.parent / "data" / "antar.db"))


@asynccontextmanager
async def lifespan(app: FastAPI):
    store = Store(DB_PATH)
    seed = os.getenv("ANTAR_SEED")
    runtime = Runtime(store, int(seed) if seed else None)
    app.state.store, app.state.runtime = store, runtime
    runtime.start()
    logging.getLogger("antar").info("ANTAR backend up. Console: http://127.0.0.1:8000  Docs: /docs")
    yield
    await runtime.stop()
    store.close()


app = FastAPI(
    title="ANTAR control-room API",
    version=__version__,
    description="Absence-based crash detection for unlit rural roads. "
                "The detector only ever sees pod pass events; everything else is inferred.",
    lifespan=lifespan,
)
app.add_middleware(CORSMiddleware, allow_origins=["*"], allow_methods=["*"], allow_headers=["*"])


PUBLIC_DEMO = os.getenv("ANTAR_PUBLIC_DEMO", "").lower() in ("1", "true", "yes")


def not_in_public_demo() -> None:
    """Endpoints that store personal data or reach real phones are closed on the public demo."""
    if os.getenv("ANTAR_PUBLIC_DEMO", "").lower() in ("1", "true", "yes"):
        raise HTTPException(403, "Disabled on the public demo. Run ANTAR locally to use this endpoint.")


def pod_key(x_pod_key: Optional[str] = Header(None)) -> None:
    """Field pods must present ANTAR_POD_KEY (if one is configured) in the X-Pod-Key header."""
    expected = os.getenv("ANTAR_POD_KEY")
    if expected and x_pod_key != expected:
        raise HTTPException(401, "Missing or wrong X-Pod-Key. Only registered pods may upload.")


def rt() -> Runtime:
    return app.state.runtime


def seg(segment_id: str) -> Segment:
    try:
        return rt().get(segment_id)
    except KeyError:
        raise HTTPException(404, f"Unknown segment '{segment_id}'. GET /api/segments lists them.")


# ------------------------------------------------------------------ models
class PassEvent(BaseModel):
    pod: Literal["POD A", "POD B", "POD C", "POD D"]
    speed_mps: float = Field(..., gt=0, lt=70, description="Measured speed, metres per second")
    length_m: float = Field(..., gt=0.5, lt=25, description="Measured vehicle length, metres")
    signature: list[float] = Field(..., min_length=4, max_length=4,
                                   description="4-D vehicle signature from the pod sensor (sensor-agnostic), each value 0..1")
    t: Optional[float] = Field(None, description="Unix time of passage; defaults to server time")


class Heartbeat(BaseModel):
    battery_pct: Optional[float] = Field(None, ge=0, le=100)
    rssi_dbm: Optional[float] = Field(None, ge=-130, le=0)
    power: Optional[Literal["pole", "solar", "battery"]] = None


class PodState(BaseModel):
    online: bool


class SimControl(BaseModel):
    speed: Optional[float] = Field(None, ge=0.25, le=16)
    paused: Optional[bool] = None


class ResponderIn(BaseModel):
    name: str = Field(..., min_length=2, max_length=80)
    phone: str = Field(..., min_length=6, max_length=24)
    distance_km: float = Field(..., ge=0, le=10)
    skills: str = Field("", max_length=120)


class StatusChange(BaseModel):
    status: Literal["acknowledged", "resolved"]


# ------------------------------------------------------------------ system
@app.get("/api/health", tags=["system"])
def health():
    return {"ok": True, "version": __version__, "segments": list(rt().segments),
            "websocket_clients": len(rt().clients),
            "public_demo": os.getenv("ANTAR_PUBLIC_DEMO", "").lower() in ("1", "true", "yes")}


@app.get("/api/stats", tags=["system"])
def stats():
    return app.state.store.stats()


@app.get("/api/audit", tags=["system"])
def audit(limit: int = Query(200, ge=1, le=1000), segment: Optional[str] = None):
    """Decision-grade log. Individual vehicle passes are deliberately never stored."""
    return app.state.store.audit_log(limit, segment)


# ----------------------------------------------------------------- segments
@app.get("/api/segments", tags=["segments"])
def segments():
    return [s.snapshot(include_vehicles=False) for s in rt().segments.values()]


@app.get("/api/segments/{segment_id}", tags=["segments"])
def segment(segment_id: str, vehicles: bool = False):
    return seg(segment_id).snapshot(include_vehicles=vehicles)


@app.get("/api/segments/{segment_id}/log", tags=["segments"])
def segment_log(segment_id: str, limit: int = Query(120, ge=1, le=250)):
    return seg(segment_id).recent[-limit:]


@app.post("/api/segments/{segment_id}/scenario/{scenario}", tags=["simulation"])
def run_scenario(segment_id: str, scenario: Literal["A", "B", "C"]):
    s = seg(segment_id)
    try:
        s.start_scenario(scenario)
    except ValueError as e:
        raise HTTPException(409, str(e))
    return {"armed": scenario, "description": SCENARIOS[scenario][1]}


@app.patch("/api/segments/{segment_id}/sim", tags=["simulation"])
def sim_control(segment_id: str, body: SimControl):
    s = seg(segment_id)
    if body.speed is not None:
        s.speed = body.speed
    if body.paused is not None:
        s.paused = body.paused
    return {"speed": s.speed, "paused": s.paused}


# --------------------------------------------------------------------- pods
@app.post("/api/segments/{segment_id}/pass", tags=["pods"], dependencies=[Depends(pod_key)])
def ingest_pass(segment_id: str, ev: PassEvent):
    """What real pod firmware posts on every vehicle passage."""
    s = seg(segment_id)
    if s.mode != "field":
        raise HTTPException(409, "This segment is driven by the simulator. Post to SEG-FIELD-01.")
    if not all(0 <= x <= 1 for x in ev.signature):
        raise HTTPException(422, "signature values must be between 0 and 1")
    track = s.ingest_pass(ev.pod, ev.t or s.now(), ev.speed_mps, ev.length_m, ev.signature)
    return {"accepted": True, "track": track, "open_windows": s.detector.open_windows()}


@app.post("/api/segments/{segment_id}/pods/{pod_id}/heartbeat", tags=["pods"], dependencies=[Depends(pod_key)])
def heartbeat(segment_id: str, pod_id: str, hb: Heartbeat):
    s = seg(segment_id)
    if pod_id not in s.pods:
        raise HTTPException(404, f"Unknown pod '{pod_id}'")
    return s.heartbeat(pod_id, hb.battery_pct, hb.rssi_dbm, hb.power)


@app.put("/api/segments/{segment_id}/pods/{pod_id}", tags=["pods"])
def set_pod(segment_id: str, pod_id: str, body: PodState):
    """Take a pod offline / online to exercise re-pairing and degraded confidence."""
    s = seg(segment_id)
    if pod_id not in s.pods:
        raise HTTPException(404, f"Unknown pod '{pod_id}'")
    if pod_id == "POD A" and not body.online:
        raise HTTPException(409, "POD A anchors the segment in this build; take POD B offline instead.")
    return s.set_pod_online(pod_id, body.online)


# ---------------------------------------------------------------- incidents
@app.get("/api/incidents", tags=["incidents"])
def incidents(status: Optional[str] = None, segment: Optional[str] = None,
              limit: int = Query(100, ge=1, le=500)):
    return app.state.store.incidents(status, segment, limit)


@app.get("/api/incidents/{incident_id}", tags=["incidents"])
def incident(incident_id: int):
    inc = app.state.store.get_incident(incident_id)
    if not inc:
        raise HTTPException(404, "No such incident")
    return inc


@app.patch("/api/incidents/{incident_id}", tags=["incidents"])
async def update_incident(incident_id: int, body: StatusChange):
    store = app.state.store
    inc = store.get_incident(incident_id)
    if not inc:
        raise HTTPException(404, "No such incident")
    if inc["status"] == "dismissed":
        raise HTTPException(409, "Dismissed candidates are a closed record and cannot change status.")
    order = {"dispatched": 0, "acknowledged": 1, "resolved": 2}
    if order[body.status] <= order[inc["status"]]:
        raise HTTPException(409, f"Incident is already {inc['status']}.")
    if order[body.status] != order[inc["status"]] + 1:
        raise HTTPException(409, f"Incident is {inc['status']}; it must be acknowledged before it can be resolved.")
    inc = store.set_status(incident_id, body.status)
    await rt().broadcast({"type": "incident", "segment": inc["segment"], "incident": inc})
    return inc


@app.post("/api/alerts/test", tags=["incidents"], dependencies=[Depends(not_in_public_demo)])
async def test_alert():
    """Send one test alert through every configured channel (console, webhook, Telegram).
    Use it to check your phone buzzes before a demo, without running a scenario."""
    d = Dispatcher()
    payload = {"incident_id": "TEST", "segment": "SEG-SIM-01", "segment_name": "Test alert",
               "summary": "This is a test. If you can read this on your phone, ANTAR alerts work.",
               "confidence": 1.0, "tier": "HIGH", "evidence": "manual test", "sim_clock": "--:--"}
    results = await d.fan_out([Recipient("responders", "Test recipient", "ANTAR control room")], payload, [])
    return {"channels": [ch.name for ch in d.channels], "result": results[0]}


# --------------------------------------------------------------- responders
@app.get("/api/segments/{segment_id}/responders", tags=["responders"])
def list_responders(segment_id: str):
    seg(segment_id)
    return app.state.store.responders(segment_id)


@app.post("/api/segments/{segment_id}/responders", tags=["responders"], status_code=201,
          dependencies=[Depends(not_in_public_demo)])
def add_responder(segment_id: str, r: ResponderIn):
    seg(segment_id)
    if r.distance_km > 2:
        raise HTTPException(422, "Local responders must live within 2 km of the segment.")
    return app.state.store.add_responder(segment_id, r.name, r.phone, r.distance_km, r.skills)


@app.delete("/api/responders/{responder_id}", tags=["responders"], status_code=204,
            dependencies=[Depends(not_in_public_demo)])
def delete_responder(responder_id: int):
    if not app.state.store.delete_responder(responder_id):
        raise HTTPException(404, "No such responder")


# ---------------------------------------------------------------- websocket
@app.websocket("/ws")
async def ws(websocket: WebSocket):
    await websocket.accept()
    r = rt()
    r.clients.add(websocket)
    try:
        for s in r.segments.values():
            await websocket.send_json(s.snapshot())
            for e in s.recent[-80:]:
                await websocket.send_json({"type": "event", "clock": clock(e["t"]), **e})
        await websocket.send_json({"type": "incidents", "incidents": app.state.store.incidents(limit=30)})
        while True:
            await websocket.receive_text()     # keep-alive; console sends pings
    except WebSocketDisconnect:
        pass
    finally:
        r.clients.discard(websocket)


# ------------------------------------------------------------------- static
app.mount("/static", StaticFiles(directory=HERE / "static"), name="static")
# Only the public demo folders are exposed — never the backend or its database.
for _sub in ("simulation", "pod", "docs", "assets"):
    if (REPO_ROOT / _sub).is_dir():
        app.mount(f"/demo/{_sub}", StaticFiles(directory=REPO_ROOT / _sub, html=True), name=f"demo-{_sub}")


@app.get("/demo", include_in_schema=False)
def demo_redirect():
    return RedirectResponse("/demo/")


@app.get("/demo/", include_in_schema=False)
def demo_hub():
    return FileResponse(REPO_ROOT / "index.html")


@app.get("/", include_in_schema=False)
def console():
    return FileResponse(HERE / "static" / "console.html")


@app.get("/favicon.ico", include_in_schema=False)
def favicon():
    return RedirectResponse("/static/favicon.svg")
