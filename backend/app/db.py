"""SQLite DB 초기화 — users + reading_progress 테이블."""
from __future__ import annotations

import os
from pathlib import Path

import aiosqlite

_DB_PATH: Path | None = None


def get_db_path() -> Path:
    global _DB_PATH
    if _DB_PATH is None:
        _DB_PATH = Path(os.getenv("DB_PATH", "teamMakeBooks.db"))
    return _DB_PATH


async def init_db() -> None:
    """테이블 없으면 생성."""
    async with aiosqlite.connect(get_db_path()) as db:
        await db.execute("""
            CREATE TABLE IF NOT EXISTS users (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                email TEXT UNIQUE NOT NULL,
                password_hash TEXT NOT NULL,
                created_at TEXT NOT NULL DEFAULT (datetime('now'))
            )
        """)
        await db.execute("""
            CREATE TABLE IF NOT EXISTS reading_progress (
                user_id INTEGER NOT NULL,
                work_id TEXT NOT NULL,
                chapter_n INTEGER NOT NULL,
                scroll_pct REAL NOT NULL DEFAULT 0,
                completed_at TEXT,
                updated_at TEXT NOT NULL DEFAULT (datetime('now')),
                PRIMARY KEY (user_id, work_id, chapter_n),
                FOREIGN KEY (user_id) REFERENCES users(id)
            )
        """)
        await db.commit()
