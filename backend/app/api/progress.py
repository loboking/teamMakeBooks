"""읽기 진행률 API."""
from __future__ import annotations

from datetime import datetime, timezone

import aiosqlite
from fastapi import APIRouter, Depends
from pydantic import BaseModel

from ..db import get_db_path
from .auth import get_current_user

router = APIRouter(prefix="/progress", tags=["progress"])


class ProgressBody(BaseModel):
    scroll_pct: float = 0.0
    completed: bool = False


@router.get("/{work_id}")
async def get_work_progress(work_id: str, user: dict = Depends(get_current_user)):
    """작품의 모든 화 진행률 목록."""
    async with aiosqlite.connect(get_db_path()) as db:
        db.row_factory = aiosqlite.Row
        async with db.execute(
            "SELECT chapter_n, scroll_pct, completed_at, updated_at FROM reading_progress "
            "WHERE user_id=? AND work_id=? ORDER BY chapter_n",
            (user["id"], work_id),
        ) as cur:
            rows = await cur.fetchall()
    return {"work_id": work_id, "progress": [dict(r) for r in rows]}


@router.put("/{work_id}/{chapter_n}")
async def upsert_progress(
    work_id: str,
    chapter_n: int,
    body: ProgressBody,
    user: dict = Depends(get_current_user),
):
    """스크롤 위치 저장 (upsert)."""
    now = datetime.now(timezone.utc).isoformat()
    completed_at = now if body.completed else None
    async with aiosqlite.connect(get_db_path()) as db:
        await db.execute(
            """
            INSERT INTO reading_progress (user_id, work_id, chapter_n, scroll_pct, completed_at, updated_at)
            VALUES (?, ?, ?, ?, ?, ?)
            ON CONFLICT(user_id, work_id, chapter_n) DO UPDATE SET
                scroll_pct=excluded.scroll_pct,
                completed_at=COALESCE(excluded.completed_at, reading_progress.completed_at),
                updated_at=excluded.updated_at
            """,
            (user["id"], work_id, chapter_n, body.scroll_pct, completed_at, now),
        )
        await db.commit()
    return {"ok": True}


@router.get("/continue/last")
async def get_last_read(user: dict = Depends(get_current_user)):
    """마지막으로 읽은 위치 반환."""
    async with aiosqlite.connect(get_db_path()) as db:
        db.row_factory = aiosqlite.Row
        async with db.execute(
            "SELECT work_id, chapter_n, scroll_pct FROM reading_progress "
            "WHERE user_id=? ORDER BY updated_at DESC LIMIT 1",
            (user["id"],),
        ) as cur:
            row = await cur.fetchone()
    if not row:
        return {"last": None}
    return {"last": dict(row)}
