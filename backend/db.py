import sqlite3
from contextlib import contextmanager
from datetime import datetime, timezone

from .config import settings
from .seed import SCENIC_QA


def now() -> str:
    return datetime.now(timezone.utc).astimezone().isoformat(timespec="seconds")


@contextmanager
def connect():
    conn = sqlite3.connect(settings.db_path)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys=ON")
    try:
        yield conn
        conn.commit()
    finally:
        conn.close()


def init_db() -> None:
    for folder in (settings.data_dir, settings.audio_dir, settings.video_dir, settings.material_dir):
        folder.mkdir(parents=True, exist_ok=True)
    with connect() as db:
        db.executescript("""
        CREATE TABLE IF NOT EXISTS scenic_spots (
          id INTEGER PRIMARY KEY, name TEXT NOT NULL UNIQUE
        );
        CREATE TABLE IF NOT EXISTS qa_items (
          id INTEGER PRIMARY KEY, scenic_spot_id INTEGER NOT NULL REFERENCES scenic_spots(id),
          question TEXT NOT NULL, answer TEXT NOT NULL, created_at TEXT NOT NULL,
          UNIQUE(scenic_spot_id, question)
        );
        CREATE TABLE IF NOT EXISTS audio_assets (
          id INTEGER PRIMARY KEY, qa_id INTEGER NOT NULL REFERENCES qa_items(id),
          filename TEXT NOT NULL, relative_path TEXT NOT NULL, speaker_id TEXT NOT NULL,
          resource_id TEXT NOT NULL, created_at TEXT NOT NULL, UNIQUE(relative_path)
        );
        CREATE TABLE IF NOT EXISTS source_assets (
          id INTEGER PRIMARY KEY, original_name TEXT NOT NULL, stored_name TEXT NOT NULL,
          relative_path TEXT NOT NULL, media_type TEXT NOT NULL, created_at TEXT NOT NULL,
          UNIQUE(relative_path)
        );
        CREATE TABLE IF NOT EXISTS video_assets (
          id INTEGER PRIMARY KEY, qa_id INTEGER NOT NULL REFERENCES qa_items(id),
          audio_id INTEGER NOT NULL REFERENCES audio_assets(id),
          source_id INTEGER NOT NULL REFERENCES source_assets(id), filename TEXT,
          relative_path TEXT, status TEXT NOT NULL, error_message TEXT,
          remote_response TEXT, created_at TEXT NOT NULL, completed_at TEXT
        );
        CREATE TABLE IF NOT EXISTS pipeline_jobs (
          id INTEGER PRIMARY KEY, voice_id TEXT NOT NULL, status TEXT NOT NULL,
          total_count INTEGER NOT NULL, completed_count INTEGER NOT NULL DEFAULT 0,
          success_count INTEGER NOT NULL DEFAULT 0, failed_count INTEGER NOT NULL DEFAULT 0,
          options_json TEXT NOT NULL, created_at TEXT NOT NULL, started_at TEXT,
          completed_at TEXT, error_message TEXT
        );
        CREATE TABLE IF NOT EXISTS pipeline_items (
          id INTEGER PRIMARY KEY, job_id INTEGER NOT NULL REFERENCES pipeline_jobs(id),
          qa_id INTEGER NOT NULL REFERENCES qa_items(id), status TEXT NOT NULL,
          stage TEXT NOT NULL, audio_id INTEGER REFERENCES audio_assets(id),
          video_id INTEGER REFERENCES video_assets(id), source_path TEXT,
          error_message TEXT, created_at TEXT NOT NULL, completed_at TEXT,
          UNIQUE(job_id, qa_id)
        );
        """)
        db.execute("""UPDATE pipeline_jobs SET status='interrupted', completed_at=?,
          error_message=COALESCE(error_message,'服务重启，任务已中断')
          WHERE status='running'""", (now(),))
        db.execute("""UPDATE pipeline_items SET status='failed', stage='interrupted',
          error_message=COALESCE(error_message,'服务重启，任务已中断'), completed_at=?
          WHERE status='running'""", (now(),))
        for spot, items in SCENIC_QA.items():
            db.execute("INSERT OR IGNORE INTO scenic_spots(name) VALUES (?)", (spot,))
            spot_id = db.execute("SELECT id FROM scenic_spots WHERE name=?", (spot,)).fetchone()["id"]
            db.executemany(
                "INSERT OR IGNORE INTO qa_items(scenic_spot_id,question,answer,created_at) VALUES (?,?,?,?)",
                [(spot_id, q, a, now()) for q, a in items],
            )


def rows(sql: str, params=()):
    with connect() as db:
        return [dict(r) for r in db.execute(sql, params).fetchall()]
