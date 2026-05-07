#!/usr/bin/env python3
"""작품별 schedule을 스캔해 due한 작품의 회차를 발행한다.

크론에 매분 등록:
  * * * * * cd /Volumes/SSD2T/teamMakeBooks && .venv/bin/python scripts/scheduler_tick.py >> logs/scheduler.log 2>&1

또는 매 5분:
  */5 * * * * ...
"""
from __future__ import annotations

import sys
import traceback
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "backend"))

from app.config import load_settings  # noqa: E402
from app.orchestrator import run_chapter_pipeline  # noqa: E402
from app.scheduler import (  # noqa: E402
    compute_next_run,
    get_next_chapter_n,
    is_due,
    load_schedule,
    save_schedule,
)


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def main() -> int:
    settings = load_settings(ROOT)
    novels_dir = settings.novels_dir
    if not novels_dir.exists():
        print(f"[tick] novels_dir 없음: {novels_dir}", file=sys.stderr)
        return 1

    works = [d for d in novels_dir.iterdir() if d.is_dir() and (d / "meta.json").exists()]
    print(f"[tick] {_now_iso()} | 작품 {len(works)}개 스캔")

    for work_dir in works:
        work_id = work_dir.name
        sch = load_schedule(work_id, novels_dir)
        if not sch.enabled or sch.paused or sch.frequency == "manual":
            continue
        if not is_due(sch):
            nxt = compute_next_run(sch)
            print(f"  {work_id}: 대기 (다음 실행 {nxt})" if nxt else f"  {work_id}: 비활성")
            continue

        # 발행 진입 — 마지막 실행 시각·상태 즉시 기록 (중복 진입 방지)
        sch.last_run_at = _now_iso()
        sch.last_status = "running"
        sch.last_error = ""
        save_schedule(work_id, novels_dir, sch)

        start_n = get_next_chapter_n(work_id, novels_dir)
        end_n = start_n + sch.batch_size - 1
        print(f"  {work_id}: 발행 시작 ch{start_n:03d}~ch{end_n:03d}")

        ok_count = 0
        last_err = ""
        try:
            for n in range(start_n, end_n + 1):
                result = run_chapter_pipeline(work_id=work_id, chapter_n=n, settings=settings)
                if result.success:
                    ok_count += 1
                    print(f"    ch{n:03d} OK")
                else:
                    last_err = f"ch{n:03d} 실패: {result.failure_stage} / {result.failure_reason}"
                    print(f"    {last_err}")
                    break  # 한 화 실패 시 중단 (다음 tick에서 재시도)
        except Exception as e:
            last_err = f"예외: {e}"
            traceback.print_exc()

        # 상태 업데이트
        sch = load_schedule(work_id, novels_dir)  # 다른 프로세스가 변경했을 수도
        sch.last_run_at = _now_iso()
        sch.last_status = "ok" if ok_count == sch.batch_size else "failed"
        sch.last_error = last_err
        sch.last_published_n = start_n + ok_count - 1 if ok_count > 0 else sch.last_published_n
        save_schedule(work_id, novels_dir, sch)
        print(f"  {work_id}: {ok_count}/{sch.batch_size}화 발행 (status={sch.last_status})")

    return 0


if __name__ == "__main__":
    sys.exit(main())
