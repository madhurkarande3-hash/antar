"""SQLite persistence (standard library only — no database server to install).

Privacy position, enforced here by schema: individual vehicle passes and vehicle
signatures are NEVER written to disk. They live in detector memory for the few
minutes a window is open, then they are gone. What is stored is what the architecture
says may leave the segment: decisions, their evidence, and the alerts they caused.
"""
from __future__ import annotations

import json
import sqlite3
import threading
import time
from pathlib import Path
from typing import Any, Optional

SCHEMA = """
CREATE TABLE IF NOT EXISTS incidents (
    id              INTEGER PRIMARY KEY AUTOINCREMENT,
    segment         TEXT NOT NULL,
    evt             TEXT NOT NULL,
    status          TEXT NOT NULL,          -- dispatched | acknowledged | resolved | dismissed
    confidence      REAL NOT NULL,
    tier            TEXT NOT NULL,
    reason          TEXT NOT NULL,
    note            TEXT NOT NULL,
    degraded        INTEGER NOT NULL DEFAULT 0,
    reconfirmations INTEGER NOT NULL DEFAULT 0,
    sim_time        REAL NOT NULL,
    evidence_json   TEXT NOT NULL,
    created_at      REAL NOT NULL,
    updated_at      REAL NOT NULL
);
CREATE INDEX IF NOT EXISTS ix_incidents_segment ON incidents(segment, status);

CREATE TABLE IF NOT EXISTS alerts (
    id           INTEGER PRIMARY KEY AUTOINCREMENT,
    incident_id  INTEGER NOT NULL REFERENCES incidents(id) ON DELETE CASCADE,
    tier         TEXT NOT NULL,             -- hospital | police | responders
    recipient    TEXT NOT NULL,
    detail       TEXT NOT NULL,
    channel      TEXT NOT NULL,
    status       TEXT NOT NULL,             -- delivered | failed
    latency_ms   INTEGER NOT NULL,
    relay_json   TEXT NOT NULL,
    created_at   REAL NOT NULL
);

CREATE TABLE IF NOT EXISTS responders (
    id          INTEGER PRIMARY KEY AUTOINCREMENT,
    segment     TEXT NOT NULL,
    name        TEXT NOT NULL,
    phone       TEXT NOT NULL,
    distance_km REAL NOT NULL,
    skills      TEXT NOT NULL DEFAULT '',
    active      INTEGER NOT NULL DEFAULT 1,
    created_at  REAL NOT NULL
);

CREATE TABLE IF NOT EXISTS audit_log (
    id         INTEGER PRIMARY KEY AUTOINCREMENT,
    segment    TEXT NOT NULL,
    kind       TEXT NOT NULL,
    level      TEXT NOT NULL,
    text       TEXT NOT NULL,
    sim_time   REAL NOT NULL,
    created_at REAL NOT NULL
);
CREATE INDEX IF NOT EXISTS ix_audit_created ON audit_log(created_at);
"""

# Only decision-grade events reach the persisted audit log. Per-vehicle passes and matches
# are streamed live to the console over the WebSocket but are never written to disk.
AUDITED_KINDS = {"candidate_opened", "miss_folded", "decision", "pod_status",
                 "dispatch", "incident_update", "scenario"}


def _row(r: sqlite3.Row) -> dict:
    d = dict(r)
    for k in ("evidence_json", "relay_json"):
        if k in d:
            d[k.removesuffix("_json")] = json.loads(d.pop(k))
    if "degraded" in d:
        d["degraded"] = bool(d["degraded"])
    if "active" in d:
        d["active"] = bool(d["active"])
    return d


class Store:
    def __init__(self, path: str | Path = "antar.db"):
        self.path = str(path)
        if self.path != ":memory:":
            Path(self.path).parent.mkdir(parents=True, exist_ok=True)
        self._lock = threading.Lock()
        self.db = sqlite3.connect(self.path, check_same_thread=False)
        self.db.row_factory = sqlite3.Row
        self.db.execute("PRAGMA journal_mode=WAL" if self.path != ":memory:" else "PRAGMA foreign_keys=ON")
        self.db.execute("PRAGMA foreign_keys=ON")
        self.db.executescript(SCHEMA)
        self.db.commit()

    def _exec(self, sql: str, args: tuple = ()) -> sqlite3.Cursor:
        with self._lock:
            cur = self.db.execute(sql, args)
            self.db.commit()
            return cur

    def _all(self, sql: str, args: tuple = ()) -> list[dict]:
        with self._lock:
            return [_row(r) for r in self.db.execute(sql, args).fetchall()]

    # ------------------------------------------------------------- audit
    def audit(self, e: dict) -> None:
        if e.get("kind") not in AUDITED_KINDS:
            return
        self._exec("INSERT INTO audit_log(segment,kind,level,text,sim_time,created_at) VALUES(?,?,?,?,?,?)",
                   (e.get("segment", ""), e["kind"], e.get("level", "info"), e.get("text", ""),
                    float(e.get("t", 0)), time.time()))

    def audit_log(self, limit: int = 200, segment: Optional[str] = None) -> list[dict]:
        if segment:
            return self._all("SELECT * FROM audit_log WHERE segment=? ORDER BY id DESC LIMIT ?", (segment, limit))
        return self._all("SELECT * FROM audit_log ORDER BY id DESC LIMIT ?", (limit,))

    # --------------------------------------------------------- incidents
    def create_incident(self, segment: str, sus: dict, status: str) -> dict:
        now = time.time()
        cur = self._exec(
            """INSERT INTO incidents(segment,evt,status,confidence,tier,reason,note,degraded,
               sim_time,evidence_json,created_at,updated_at) VALUES(?,?,?,?,?,?,?,?,?,?,?,?)""",
            (segment, sus["evt"], status, sus["confidence"], sus["tier"], sus["reason"], sus["note"],
             int(sus["degraded"]), sus["t_settle"], json.dumps(sus), now, now))
        return self.get_incident(cur.lastrowid)

    def get_incident(self, incident_id: int) -> Optional[dict]:
        rows = self._all("SELECT * FROM incidents WHERE id=?", (incident_id,))
        if not rows:
            return None
        inc = rows[0]
        inc["alerts"] = self._all("SELECT * FROM alerts WHERE incident_id=? ORDER BY id", (incident_id,))
        return inc

    def active_incident(self, segment: str) -> Optional[dict]:
        rows = self._all("""SELECT id FROM incidents WHERE segment=? AND status IN ('dispatched','acknowledged')
                            ORDER BY id DESC LIMIT 1""", (segment,))
        return self.get_incident(rows[0]["id"]) if rows else None

    def reconfirm(self, incident_id: int, sus: dict) -> dict:
        self._exec("""UPDATE incidents SET reconfirmations=reconfirmations+1,
                      confidence=MAX(confidence,?), updated_at=? WHERE id=?""",
                   (sus["confidence"], time.time(), incident_id))
        return self.get_incident(incident_id)

    def set_status(self, incident_id: int, status: str) -> Optional[dict]:
        self._exec("UPDATE incidents SET status=?, updated_at=? WHERE id=?", (status, time.time(), incident_id))
        return self.get_incident(incident_id)

    def incidents(self, status: Optional[str] = None, segment: Optional[str] = None,
                  limit: int = 100) -> list[dict]:
        q, args = "SELECT * FROM incidents WHERE 1=1", []
        if status:
            q += " AND status=?"; args.append(status)
        if segment:
            q += " AND segment=?"; args.append(segment)
        q += " ORDER BY id DESC LIMIT ?"; args.append(limit)
        out = self._all(q, tuple(args))
        for inc in out:
            inc["alerts"] = self._all("SELECT * FROM alerts WHERE incident_id=? ORDER BY id", (inc["id"],))
        return out

    def stats(self) -> dict:
        with self._lock:
            rows = self.db.execute("SELECT status, COUNT(*) n FROM incidents GROUP BY status").fetchall()
            a = self.db.execute("SELECT COUNT(*), AVG(latency_ms) FROM alerts").fetchone()
        by = {r["status"]: r["n"] for r in rows}
        return {"incidents_by_status": by, "alerts_sent": a[0],
                "mean_alert_latency_ms": None if a[1] is None else round(a[1])}

    # ------------------------------------------------------------ alerts
    def add_alert(self, incident_id: int, a: dict) -> None:
        self._exec("""INSERT INTO alerts(incident_id,tier,recipient,detail,channel,status,latency_ms,
                      relay_json,created_at) VALUES(?,?,?,?,?,?,?,?,?)""",
                   (incident_id, a["tier"], a["recipient"], a["detail"], a["channel"], a["status"],
                    a["latency_ms"], json.dumps(a["relay"]), time.time()))

    # -------------------------------------------------------- responders
    def add_responder(self, segment: str, name: str, phone: str, distance_km: float, skills: str) -> dict:
        cur = self._exec("""INSERT INTO responders(segment,name,phone,distance_km,skills,created_at)
                            VALUES(?,?,?,?,?,?)""", (segment, name, phone, distance_km, skills, time.time()))
        return self._all("SELECT * FROM responders WHERE id=?", (cur.lastrowid,))[0]

    def responders(self, segment: Optional[str] = None, active_only: bool = False) -> list[dict]:
        q, args = "SELECT * FROM responders WHERE 1=1", []
        if segment:
            q += " AND segment=?"; args.append(segment)
        if active_only:
            q += " AND active=1"
        return self._all(q + " ORDER BY distance_km", tuple(args))

    def delete_responder(self, rid: int) -> bool:
        return self._exec("DELETE FROM responders WHERE id=?", (rid,)).rowcount > 0

    def seed_responders(self, segment: str) -> None:
        if self.responders(segment):
            return
        for name, phone, km, skills in [
            ("Ramesh Yadav", "+91 98xxxx1042", 0.8, "first aid"),
            ("Sunita Devi", "+91 97xxxx5530", 1.4, "nurse, first aid"),
            ("Harpreet Singh", "+91 99xxxx7781", 1.9, "tractor, towing"),
        ]:
            self.add_responder(segment, name, phone, km, skills)

    def close(self) -> None:
        self.db.close()
