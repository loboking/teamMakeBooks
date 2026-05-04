#!/usr/bin/env python3
"""ch101~255 순차 자동 생성 + 텔레그램 발행.

각 회차:
  1. run_chapter_pipeline 실행
  2. 성공 시 본문을 텔레그램으로 분할 전송
  3. 실패 시 텔레그램 경보
다음 회차로.

Usage:
  python scripts/run_chapters_101_plus.py [start] [end]
  python scripts/run_chapters_101_plus.py          # 101~120
"""
from __future__ import annotations

import json
import sys
import time
import traceback
import urllib.request
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "backend"))

from app.config import load_settings  # noqa: E402
from app.orchestrator import run_chapter_pipeline  # noqa: E402

WORK_ID = "modern_fantasy_game_01"
MAX_TG_LEN = 3500


def tg_send(token: str, chat_id: str, text: str, parse_mode: str = "HTML") -> bool:
    body = json.dumps({
        "chat_id": chat_id, "text": text, "parse_mode": parse_mode,
        "disable_web_page_preview": True,
    }, ensure_ascii=False).encode("utf-8")
    req = urllib.request.Request(
        f"https://api.telegram.org/bot{token}/sendMessage",
        data=body, headers={"Content-Type": "application/json; charset=utf-8"},
    )
    try:
        with urllib.request.urlopen(req, timeout=15) as r:
            return json.load(r).get("ok", False)
    except Exception as e:
        print(f"  [tg fail] {e}", flush=True)
        return False


def split_text(text: str, max_len: int = MAX_TG_LEN) -> list[str]:
    parts: list[str] = []
    remaining = text
    while len(remaining) > max_len:
        cut = remaining.rfind("\n\n", 0, max_len)
        if cut == -1:
            cut = remaining.rfind("\n", 0, max_len)
        if cut == -1 or cut < max_len // 2:
            cut = max_len
        parts.append(remaining[:cut].rstrip())
        remaining = remaining[cut:].lstrip()
    if remaining:
        parts.append(remaining)
    return parts


def send_chapter(chapter_path: Path, n: int, settings) -> None:
    body = chapter_path.read_text(encoding="utf-8")
    parts = split_text(body)
    total = len(parts)
    for i, part in enumerate(parts, 1):
        head = f"\U0001f4d6 <b>{n}화 ({i}/{total})</b>\n\n" if i == 1 else f"\U0001f4d6 <b>{n}화 (계속 {i}/{total})</b>\n\n"
        escaped = part.replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")
        ok = tg_send(settings.telegram_bot_token, settings.telegram_chat_id, head + escaped)
        if not ok:
            print(f"  [warn] tg part {i}/{total} failed", flush=True)
        time.sleep(1)


def main() -> int:
    start = int(sys.argv[1]) if len(sys.argv) > 1 else 101
    end = int(sys.argv[2]) if len(sys.argv) > 2 else 120
    chapters = list(range(start, end + 1))

    settings = load_settings(ROOT)
    overall_t0 = time.time()
    summary: list[dict] = []

    tg_send(
        settings.telegram_bot_token, settings.telegram_chat_id,
        f"\U0001f680 <b>ch{start}~ch{end} 자동 생성 시작</b>\n"
        f"각 화 발행 지시 본문 푸시.",
    )

    for n in chapters:
        print(f"\n=== Chapter {n} 시작 ===", flush=True)
        t0 = time.time()
        try:
            r = run_chapter_pipeline(WORK_ID, n, settings=settings)
        except Exception as e:
            elapsed = time.time() - t0
            print(f"  \U0001f4a5 예외 ({elapsed:.1f}s): {e}", flush=True)
            traceback.print_exc()
            tg_send(
                settings.telegram_bot_token, settings.telegram_chat_id,
                f"\U0001f4a5 <b>{n}화 예외</b>\n<code>{e}</code>",
            )
            summary.append({"n": n, "status": "exception", "elapsed": elapsed, "error": str(e)})
            break

        elapsed = time.time() - t0
        if r.success:
            print(f"  ✅ 발행 완료 ({elapsed:.1f}s) - {r.chapter_path}", flush=True)
            send_chapter(r.chapter_path, n, settings)
            summary.append({
                "n": n, "status": "ok", "elapsed": elapsed,
                "review_rounds": len(r.review_history),
                "path": str(r.chapter_path),
            })
        else:
            print(f"  ❌ 실패 ({elapsed:.1f}s) - {r.failure_stage}: {r.failure_reason}", flush=True)
            tg_send(
                settings.telegram_bot_token, settings.telegram_chat_id,
                f"❌ <b>{n}화 발행 실패</b>\n{r.failure_stage}: {r.failure_reason}",
            )
            summary.append({
                "n": n, "status": "fail", "elapsed": elapsed,
                "stage": r.failure_stage, "reason": r.failure_reason,
            })

    overall_elapsed = time.time() - overall_t0
    ok_count = sum(1 for s in summary if s["status"] == "ok")
    fail_count = sum(1 for s in summary if s["status"] == "fail")

    final_msg = (
        f"\U0001f3c1 <b>ch{start}~ch{end} 발행 마무리</b>\n\n"
        f"✅ 성과: <b>{ok_count}</b>화\n"
        f"❌ 실패: <b>{fail_count}</b>화\n"
        f"⏱ 총 시간: {overall_elapsed/60:.1f}분\n"
    )
    tg_send(settings.telegram_bot_token, settings.telegram_chat_id, final_msg)
    print(f"\n{final_msg}")

    out_path = ROOT / "logs" / f"pipeline_{start}_{end}.json"
    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_text(json.dumps(summary, ensure_ascii=False, indent=2), encoding="utf-8")
    return 0 if fail_count == 0 else 1


if __name__ == "__main__":
    sys.exit(main())
