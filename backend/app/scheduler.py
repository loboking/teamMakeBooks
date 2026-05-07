"""작품별 회차 자동 발행 스케줄러 — meta.json 영속 + cron 호출.

데이터 모델: novels/{work_id}/meta.json의 "schedule" 섹션.

```json
"schedule": {
  "enabled": true,
  "frequency": "daily",        // daily | hourly | weekly | manual
  "hour": 9, "minute": 0,      // 시작 시각 (KST)
  "batch_size": 1,              // 1회 실행 시 발행할 화 수
  "paused": false,
  "last_run_at": "2026-05-08T00:00:00+00:00",
  "last_published_n": 0,
  "last_status": "ok",          // ok | failed | running
  "last_error": ""
}
```

다음 실행 시각은 `next_run_at`을 메타에 저장하지 않고, 매번 `compute_next_run`으로 계산.
이렇게 하면 사용자가 시간 변경해도 즉시 반영.
"""
from __future__ import annotations

import json
from dataclasses import asdict, dataclass
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Literal
from zoneinfo import ZoneInfo


KST = ZoneInfo("Asia/Seoul")
Frequency = Literal["daily", "hourly", "weekly", "manual"]


@dataclass
class Schedule:
    enabled: bool = False
    frequency: Frequency = "daily"
    hour: int = 9          # 0~23 (KST)
    minute: int = 0        # 0~59
    batch_size: int = 1
    paused: bool = False
    last_run_at: str = ""
    last_published_n: int = 0
    last_status: str = "idle"  # idle | running | ok | failed
    last_error: str = ""

    @classmethod
    def from_dict(cls, data: dict | None) -> "Schedule":
        if not data:
            return cls()
        return cls(
            enabled=bool(data.get("enabled", False)),
            frequency=str(data.get("frequency", "daily")),  # type: ignore
            hour=int(data.get("hour", 9)),
            minute=int(data.get("minute", 0)),
            batch_size=int(data.get("batch_size", 1)),
            paused=bool(data.get("paused", False)),
            last_run_at=str(data.get("last_run_at", "")),
            last_published_n=int(data.get("last_published_n", 0)),
            last_status=str(data.get("last_status", "idle")),
            last_error=str(data.get("last_error", "")),
        )


def load_schedule(work_id: str, novels_dir: Path) -> Schedule:
    meta_path = novels_dir / work_id / "meta.json"
    if not meta_path.exists():
        return Schedule()
    meta = json.loads(meta_path.read_text(encoding="utf-8"))
    return Schedule.from_dict(meta.get("schedule"))


def save_schedule(work_id: str, novels_dir: Path, schedule: Schedule) -> None:
    meta_path = novels_dir / work_id / "meta.json"
    meta = json.loads(meta_path.read_text(encoding="utf-8")) if meta_path.exists() else {}
    meta["schedule"] = asdict(schedule)
    meta_path.write_text(json.dumps(meta, ensure_ascii=False, indent=2), encoding="utf-8")


def compute_next_run(schedule: Schedule, now: datetime | None = None) -> datetime | None:
    """현재 시점에서 다음 자동 실행 시각 (KST). 비활성/일시정지면 None."""
    if not schedule.enabled or schedule.paused or schedule.frequency == "manual":
        return None
    now = (now or datetime.now(timezone.utc)).astimezone(KST)

    if schedule.frequency == "hourly":
        nxt = now.replace(minute=schedule.minute, second=0, microsecond=0)
        if nxt <= now:
            nxt += timedelta(hours=1)
        return nxt

    if schedule.frequency == "daily":
        nxt = now.replace(hour=schedule.hour, minute=schedule.minute, second=0, microsecond=0)
        if nxt <= now:
            nxt += timedelta(days=1)
        return nxt

    if schedule.frequency == "weekly":
        # 매주 월요일 동일 시각
        nxt = now.replace(hour=schedule.hour, minute=schedule.minute, second=0, microsecond=0)
        days_ahead = (0 - now.weekday()) % 7  # 다음 월요일까지 (월=0)
        if days_ahead == 0 and nxt <= now:
            days_ahead = 7
        nxt += timedelta(days=days_ahead)
        return nxt

    return None


def is_due(schedule: Schedule, now: datetime | None = None, *, slack_minutes: int = 5) -> bool:
    """지금 발행 대상인가? (예약 시각 ±slack_minutes 안에 들어오면 발행)."""
    if not schedule.enabled or schedule.paused or schedule.frequency == "manual":
        return False
    now = (now or datetime.now(timezone.utc)).astimezone(KST)

    # 마지막 실행 이후 frequency 주기 경과 + 시각 도달
    last = _parse_iso(schedule.last_run_at)
    if last:
        last_kst = last.astimezone(KST)
        gap = now - last_kst
        if schedule.frequency == "hourly" and gap < timedelta(minutes=55):
            return False
        if schedule.frequency == "daily" and gap < timedelta(hours=23):
            return False
        if schedule.frequency == "weekly" and gap < timedelta(days=6, hours=23):
            return False

    # 예약 시각 도달
    target_today = now.replace(hour=schedule.hour, minute=schedule.minute, second=0, microsecond=0)
    if schedule.frequency == "hourly":
        target_today = now.replace(minute=schedule.minute, second=0, microsecond=0)
    delta = abs((now - target_today).total_seconds()) / 60
    return delta <= slack_minutes


def _parse_iso(s: str) -> datetime | None:
    if not s:
        return None
    try:
        return datetime.fromisoformat(s)
    except ValueError:
        return None


def get_next_chapter_n(work_id: str, novels_dir: Path) -> int:
    """다음 발행할 화 번호 (1-based). 빈 작품이면 1."""
    chapters_dir = novels_dir / work_id / "chapters"
    if not chapters_dir.exists():
        return 1
    existing = sorted(
        int(f.stem.replace("ch", "").rstrip("_meta").rstrip("_summary"))
        for f in chapters_dir.glob("ch*.md")
        if f.stem[2:].isdigit()
    )
    return (existing[-1] + 1) if existing else 1
