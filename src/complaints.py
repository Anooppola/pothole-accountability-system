"""Complaint lifecycle management for the simulated BBMP portal."""
from __future__ import annotations

import sqlite3
from contextlib import contextmanager
from datetime import datetime

from . import config

SCHEMA = """
CREATE TABLE IF NOT EXISTS complaints (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    complaint_id TEXT UNIQUE NOT NULL,
    citizen_name TEXT NOT NULL,
    citizen_phone TEXT,
    latitude REAL,
    longitude REAL,
    location_label TEXT,
    severity TEXT,
    source_type TEXT,
    evidence_path TEXT,
    status TEXT NOT NULL DEFAULT 'Registered',
    duplicate_of TEXT,
    duplicate_count INTEGER NOT NULL DEFAULT 0,
    reopened_count INTEGER NOT NULL DEFAULT 0,
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL,
    resolved_at TEXT
);

CREATE TABLE IF NOT EXISTS complaint_evidence (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    complaint_id TEXT NOT NULL,
    evidence_type TEXT NOT NULL,
    file_path TEXT NOT NULL,
    uploaded_by TEXT NOT NULL DEFAULT 'citizen',
    uploaded_at TEXT NOT NULL,
    note TEXT,
    is_duplicate INTEGER NOT NULL DEFAULT 0,
    FOREIGN KEY(complaint_id) REFERENCES complaints(complaint_id)
);

CREATE TABLE IF NOT EXISTS complaint_status_history (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    complaint_id TEXT NOT NULL,
    old_status TEXT,
    new_status TEXT NOT NULL,
    changed_by TEXT NOT NULL,
    changed_at TEXT NOT NULL,
    notes TEXT,
    FOREIGN KEY(complaint_id) REFERENCES complaints(complaint_id)
);

CREATE TABLE IF NOT EXISTS complaint_repairs (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    complaint_id TEXT NOT NULL,
    staff_id TEXT NOT NULL,
    before_photo_path TEXT,
    after_photo_path TEXT,
    repair_description TEXT,
    repair_date TEXT NOT NULL,
    created_at TEXT NOT NULL,
    FOREIGN KEY(complaint_id) REFERENCES complaints(complaint_id)
);

CREATE TABLE IF NOT EXISTS complaint_feedback (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    complaint_id TEXT NOT NULL,
    citizen_name TEXT NOT NULL,
    choice TEXT NOT NULL,
    reason TEXT,
    new_evidence_path TEXT,
    created_at TEXT NOT NULL,
    FOREIGN KEY(complaint_id) REFERENCES complaints(complaint_id)
);
"""


@contextmanager
def connect():
    conn = sqlite3.connect(config.DB_PATH)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON")
    try:
        yield conn
        conn.commit()
    finally:
        conn.close()


def init_db():
    with connect() as conn:
        conn.executescript(SCHEMA)


def now() -> str:
    return datetime.now().isoformat(timespec="seconds")


def _generate_complaint_id(conn) -> str:
    year = datetime.now().year
    prefix = f"CMP-{year}-"
    row = conn.execute(
        "SELECT complaint_id FROM complaints WHERE complaint_id LIKE ? ORDER BY complaint_id DESC LIMIT 1",
        (prefix + "%",),
    ).fetchone()
    next_num = int(row["complaint_id"].rsplit("-", 1)[1]) + 1 if row else 1
    return f"{prefix}{next_num:04d}"


def _write_status_history(conn, complaint_id: str, old_status: str | None, new_status: str, changed_by: str, notes: str = "") -> None:
    conn.execute(
        "INSERT INTO complaint_status_history (complaint_id, old_status, new_status, changed_by, changed_at, notes) VALUES (?, ?, ?, ?, ?, ?)",
        (complaint_id, old_status, new_status, changed_by, now(), notes),
    )


def _add_evidence(conn, complaint_id: str, evidence_type: str, file_path: str, uploaded_by: str = "citizen", note: str = "", is_duplicate: int = 0):
    conn.execute(
        "INSERT INTO complaint_evidence (complaint_id, evidence_type, file_path, uploaded_by, uploaded_at, note, is_duplicate) VALUES (?, ?, ?, ?, ?, ?, ?)",
        (complaint_id, evidence_type, file_path, uploaded_by, now(), note, is_duplicate),
    )
    return conn.execute("SELECT last_insert_rowid() AS id").fetchone()["id"]


def add_evidence(complaint_id: str, evidence_type: str, file_path: str, uploaded_by: str = "citizen", note: str = "", is_duplicate: int = 0):
    with connect() as conn:
        return _add_evidence(conn, complaint_id, evidence_type, file_path, uploaded_by, note, is_duplicate)


def find_duplicate(latitude: float | None, longitude: float | None, radius_m: float = 15.0):
    if latitude is None or longitude is None:
        return None
    with connect() as conn:
        # approx 1 degree latitude ~= 111,000m; longitude varies with latitude, so use a conservative threshold.
        lat_delta = radius_m / 111000.0
        lon_delta = radius_m / 110000.0
        rows = conn.execute(
            "SELECT * FROM complaints WHERE status NOT IN ('Resolved', 'Closed') AND ABS(latitude - ?) <= ? AND ABS(longitude - ?) <= ? ORDER BY created_at DESC LIMIT 1",
            (latitude, lat_delta, longitude, lon_delta),
        ).fetchall()
        return dict(rows[0]) if rows else None


def list_complaints():
    with connect() as conn:
        rows = conn.execute("SELECT * FROM complaints ORDER BY created_at DESC").fetchall()
        return [dict(r) for r in rows]


def list_status_history(complaint_id: str):
    with connect() as conn:
        rows = conn.execute(
            "SELECT * FROM complaint_status_history WHERE complaint_id = ? ORDER BY changed_at ASC",
            (complaint_id,),
        ).fetchall()
        return [dict(r) for r in rows]


def get_complaint(complaint_id: str):
    with connect() as conn:
        row = conn.execute("SELECT * FROM complaints WHERE complaint_id = ?", (complaint_id,)).fetchone()
        return dict(row) if row else None


def register_complaint(
    citizen_name: str,
    citizen_phone: str,
    latitude: float,
    longitude: float,
    severity: str,
    source_type: str,
    evidence_path: str,
    location_label: str | None = None,
):
    existing = find_duplicate(latitude, longitude)
    if existing:
        with connect() as conn:
            complaint_id = existing["complaint_id"]
            existing_status = existing["status"]
            notes = f"Duplicate complaint flagged against existing complaint {complaint_id}."
            conn.execute(
                "UPDATE complaints SET duplicate_count = duplicate_count + 1, updated_at = ? WHERE complaint_id = ?",
                (now(), complaint_id),
            )
            _write_status_history(conn, complaint_id, existing_status, existing_status, "system", notes)
            _add_evidence(conn, complaint_id, evidence_type=source_type, file_path=evidence_path, uploaded_by="citizen", note="Additional evidence for duplicate report", is_duplicate=1)
        return {
            "complaint_id": complaint_id,
            "status": "Duplicate",
            "duplicate_of": complaint_id,
            "is_duplicate": True,
        }

    with connect() as conn:
        complaint_id = _generate_complaint_id(conn)
        now_ts = now()
        conn.execute(
            "INSERT INTO complaints (complaint_id, citizen_name, citizen_phone, latitude, longitude, location_label, severity, source_type, evidence_path, status, created_at, updated_at) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, 'Registered', ?, ?)",
            (complaint_id, citizen_name, citizen_phone, latitude, longitude, location_label, severity, source_type, evidence_path, now_ts, now_ts),
        )
        _write_status_history(conn, complaint_id, None, "Registered", "citizen", "Complaint registered by citizen.")
        _add_evidence(conn, complaint_id, evidence_type=source_type, file_path=evidence_path, uploaded_by="citizen", note="Initial complaint evidence", is_duplicate=0)
        row = conn.execute("SELECT * FROM complaints WHERE complaint_id = ?", (complaint_id,)).fetchone()
        return dict(row)


def update_status(complaint_id: str, new_status: str, changed_by: str = "system", notes: str = ""):
    with connect() as conn:
        row = conn.execute("SELECT * FROM complaints WHERE complaint_id = ?", (complaint_id,)).fetchone()
        if row is None:
            raise ValueError(f"Complaint {complaint_id} not found")
        old_status = row["status"]
        resolved_value = now() if new_status == "Resolved" else None
        conn.execute(
            "UPDATE complaints SET status = ?, updated_at = ?, resolved_at = ? WHERE complaint_id = ?",
            (new_status, now(), resolved_value, complaint_id),
        )
        _write_status_history(conn, complaint_id, old_status, new_status, changed_by, notes)
        updated_row = conn.execute("SELECT * FROM complaints WHERE complaint_id = ?", (complaint_id,)).fetchone()
        return dict(updated_row)


def add_repair(complaint_id: str, staff_id: str, before_photo_path: str, after_photo_path: str, repair_description: str):
    with connect() as conn:
        row = conn.execute("SELECT complaint_id FROM complaints WHERE complaint_id = ?", (complaint_id,)).fetchone()
        if row is None:
            raise ValueError(f"Complaint {complaint_id} not found")
        conn.execute(
            "INSERT INTO complaint_repairs (complaint_id, staff_id, before_photo_path, after_photo_path, repair_description, repair_date, created_at) VALUES (?, ?, ?, ?, ?, ?, ?)",
            (complaint_id, staff_id, before_photo_path, after_photo_path, repair_description, now(), now()),
        )
        conn.execute(
            "UPDATE complaints SET status = 'In Repair', updated_at = ? WHERE complaint_id = ?",
            (now(), complaint_id),
        )
        _write_status_history(conn, complaint_id, "Registered", "In Repair", staff_id, "Repair work started.")
        return conn.execute("SELECT last_insert_rowid() AS id").fetchone()["id"]


def mark_resolved(complaint_id: str, changed_by: str = "staff"):
    with connect() as conn:
        row = conn.execute("SELECT * FROM complaints WHERE complaint_id = ?", (complaint_id,)).fetchone()
        if row is None:
            raise ValueError(f"Complaint {complaint_id} not found")
        conn.execute(
            "UPDATE complaints SET status = 'Resolved', resolved_at = ?, updated_at = ? WHERE complaint_id = ?",
            (now(), now(), complaint_id),
        )
        _write_status_history(conn, complaint_id, row["status"], "Resolved", changed_by, "Complaint marked as resolved by BBMP staff.")
        updated_row = conn.execute("SELECT * FROM complaints WHERE complaint_id = ?", (complaint_id,)).fetchone()
        return dict(updated_row)


def submit_feedback(complaint_id: str, citizen_name: str, choice: str, reason: str = "", new_evidence_path: str | None = None):
    with connect() as conn:
        row = conn.execute("SELECT * FROM complaints WHERE complaint_id = ?", (complaint_id,)).fetchone()
        if row is None:
            raise ValueError(f"Complaint {complaint_id} not found")

        if choice.lower() == "problem not solved":
            reopened_count = int(row["reopened_count"]) + 1
            conn.execute(
                "UPDATE complaints SET status = 'Reopened', reopened_count = ?, updated_at = ? WHERE complaint_id = ?",
                (reopened_count, now(), complaint_id),
            )
            _write_status_history(conn, complaint_id, row["status"], "Reopened", citizen_name, "Citizen reported issue still unresolved.")
            if new_evidence_path:
                _add_evidence(conn, complaint_id, evidence_type="photo", file_path=new_evidence_path, uploaded_by="citizen", note=reason, is_duplicate=0)
            conn.execute(
                "INSERT INTO complaint_feedback (complaint_id, citizen_name, choice, reason, new_evidence_path, created_at) VALUES (?, ?, ?, ?, ?, ?)",
                (complaint_id, citizen_name, choice, reason, new_evidence_path, now()),
            )
            updated_row = conn.execute("SELECT * FROM complaints WHERE complaint_id = ?", (complaint_id,)).fetchone()
            return dict(updated_row)

        conn.execute(
            "INSERT INTO complaint_feedback (complaint_id, citizen_name, choice, reason, new_evidence_path, created_at) VALUES (?, ?, ?, ?, ?, ?)",
            (complaint_id, citizen_name, choice, reason, new_evidence_path, now()),
        )
        updated_row = conn.execute("SELECT * FROM complaints WHERE complaint_id = ?", (complaint_id,)).fetchone()
        return dict(updated_row)


def get_evidence(complaint_id: str):
    with connect() as conn:
        rows = conn.execute(
            "SELECT * FROM complaint_evidence WHERE complaint_id = ? ORDER BY uploaded_at ASC",
            (complaint_id,),
        ).fetchall()
        return [dict(r) for r in rows]


def get_repairs(complaint_id: str):
    with connect() as conn:
        rows = conn.execute(
            "SELECT * FROM complaint_repairs WHERE complaint_id = ? ORDER BY repair_date ASC",
            (complaint_id,),
        ).fetchall()
        return [dict(r) for r in rows]


def get_feedback(complaint_id: str):
    with connect() as conn:
        rows = conn.execute(
            "SELECT * FROM complaint_feedback WHERE complaint_id = ? ORDER BY created_at ASC",
            (complaint_id,),
        ).fetchall()
        return [dict(r) for r in rows]


__all__ = [
    "init_db",
    "register_complaint",
    "update_status",
    "add_repair",
    "mark_resolved",
    "submit_feedback",
    "find_duplicate",
    "get_complaint",
    "list_complaints",
    "list_status_history",
    "get_evidence",
    "get_repairs",
    "get_feedback",
]
