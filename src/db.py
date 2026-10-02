"""SQLite storage for processed videos and detected potholes."""
import sqlite3
from contextlib import contextmanager
from datetime import datetime

from . import config

SCHEMA = """
CREATE TABLE IF NOT EXISTS videos (
    id               INTEGER PRIMARY KEY AUTOINCREMENT,
    filename         TEXT NOT NULL,
    stored_path      TEXT NOT NULL,
    uploaded_at      TEXT NOT NULL,
    status           TEXT NOT NULL DEFAULT 'processing',  -- processing | done | failed
    duration_s       REAL,
    frames_analysed  INTEGER DEFAULT 0,
    frames_blurry    INTEGER DEFAULT 0,
    raw_detections   INTEGER DEFAULT 0,
    pothole_count    INTEGER DEFAULT 0,
    processing_s     REAL,
    error            TEXT
);

CREATE TABLE IF NOT EXISTS potholes (
    id               TEXT PRIMARY KEY,          -- e.g. PH-2026-001
    video_id         INTEGER NOT NULL REFERENCES videos(id) ON DELETE CASCADE,
    first_seen_s     REAL,
    last_seen_s      REAL,
    best_time_s      REAL,
    frames_seen      INTEGER,
    confidence       REAL,
    area_ratio       REAL,
    corrected_area   REAL,
    dark_ratio       REAL,
    solidity         REAL,
    in_path          INTEGER,
    score            REAL,
    severity         TEXT,
    priority         TEXT,
    image_path       TEXT,
    crop_path        TEXT,
    telegram_status  TEXT DEFAULT 'pending',     -- pending | sent | failed | not_configured
    telegram_error   TEXT,
    review_status    TEXT DEFAULT 'Pending',     -- Pending | Approved | Rejected
    review_note      TEXT,
    reviewed_at      TEXT,
    created_at       TEXT NOT NULL
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


def create_video(filename: str, stored_path: str) -> int:
    with connect() as conn:
        cur = conn.execute(
            "INSERT INTO videos (filename, stored_path, uploaded_at) VALUES (?, ?, ?)",
            (filename, stored_path, now()),
        )
        return cur.lastrowid


def update_video(video_id: int, **fields):
    if not fields:
        return
    cols = ", ".join(f"{k} = ?" for k in fields)
    with connect() as conn:
        conn.execute(f"UPDATE videos SET {cols} WHERE id = ?", (*fields.values(), video_id))


def next_pothole_id(conn) -> str:
    year = datetime.now().year
    prefix = f"PH-{year}-"
    row = conn.execute(
        "SELECT id FROM potholes WHERE id LIKE ? ORDER BY id DESC LIMIT 1", (prefix + "%",)
    ).fetchone()
    n = int(row["id"].rsplit("-", 1)[1]) + 1 if row else 1
    return f"{prefix}{n:03d}"


def insert_pothole(record: dict) -> str:
    with connect() as conn:
        pid = next_pothole_id(conn)
        record = {**record, "id": pid, "created_at": now()}
        cols = ", ".join(record)
        marks = ", ".join("?" for _ in record)
        conn.execute(f"INSERT INTO potholes ({cols}) VALUES ({marks})", tuple(record.values()))
        return pid


def update_pothole(pid: str, **fields):
    if not fields:
        return
    cols = ", ".join(f"{k} = ?" for k in fields)
    with connect() as conn:
        conn.execute(f"UPDATE potholes SET {cols} WHERE id = ?", (*fields.values(), pid))


def get_video(video_id: int):
    with connect() as conn:
        return conn.execute("SELECT * FROM videos WHERE id = ?", (video_id,)).fetchone()


def list_videos():
    with connect() as conn:
        return conn.execute("SELECT * FROM videos ORDER BY id DESC").fetchall()


def list_potholes(video_id=None):
    sql = "SELECT * FROM potholes"
    args = ()
    if video_id is not None:
        sql += " WHERE video_id = ?"
        args = (video_id,)
    sql += " ORDER BY score DESC"
    with connect() as conn:
        return conn.execute(sql, args).fetchall()


def get_pothole(pid: str):
    with connect() as conn:
        return conn.execute("SELECT * FROM potholes WHERE id = ?", (pid,)).fetchone()
