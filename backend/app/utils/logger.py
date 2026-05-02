"""구조화 로그 기록기."""
from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path


def log_call(
    *,
    team: str,
    role: str,
    work_id: str,
    chapter_n: int,
    prompt: str,
    response,
    logs_dir: Path,
) -> None:
    calls_dir = logs_dir / "calls"
    calls_dir.mkdir(parents=True, exist_ok=True)
    ts = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%S%f")
    fp = calls_dir / f"{ts}_{team}_{role}.json"
    fp.write_text(
        json.dumps(
            {
                "timestamp": datetime.now(timezone.utc).isoformat(),
                "team": team,
                "role": role,
                "work_id": work_id,
                "chapter_n": chapter_n,
                "model_id": getattr(response, "model_id", "?"),
                "prompt_preview": prompt[:200],
                "output_preview": (response.text or "")[:200],
                "input_tokens": getattr(response, "input_tokens", 0),
                "output_tokens": getattr(response, "output_tokens", 0),
                "duration_ms": getattr(response, "duration_ms", 0),
            },
            ensure_ascii=False,
            indent=2,
        ),
        encoding="utf-8",
    )


def log_review_event(
    *,
    work_id: str,
    chapter_n: int,
    pipeline_started_at: str,
    pipeline_finished_at: str,
    final_status: str,
    history: list[dict],
    logs_dir: Path,
) -> None:
    reviews_dir = logs_dir / "reviews"
    reviews_dir.mkdir(parents=True, exist_ok=True)
    fp = reviews_dir / f"{work_id}_ch{chapter_n:03d}.json"
    fp.write_text(
        json.dumps(
            {
                "work_id": work_id,
                "chapter_n": chapter_n,
                "pipeline_started_at": pipeline_started_at,
                "pipeline_finished_at": pipeline_finished_at,
                "final_status": final_status,
                "reviews": history,
            },
            ensure_ascii=False,
            indent=2,
        ),
        encoding="utf-8",
    )
