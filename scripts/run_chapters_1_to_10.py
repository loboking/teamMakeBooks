#!/usr/bin/env python3
"""1화~10화 순차 자동 생성 + 텔레그램 발행.

각 회차:
  1. run_chapter_pipeline 실행
  2. 성공 시 본문을 텔레그램으로 분할 전송
  3. 실패 시 텔레그램 경보
다음 회차로.
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

CHAPTERS = list(range(1, 11))
WORK_ID = "modern_fantasy_game_01"
MAX_TG_LEN = 3500  # 안전 여유, 텔레그램 4096 한계


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
        head = f"📖 <b>{n}화 ({i}/{total})</b>\n\n" if i == 1 else f"📖 <b>{n}화 (계속 {i}/{total})</b>\n\n"
        # HTML escaping: 본문 내 <, >, & 처리
        escaped = part.replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")
        ok = tg_send(settings.telegram_bot_token, settings.telegram_chat_id, head + escaped)
        if not ok:
            print(f"  [warn] 텔레그램 part {i}/{total} 전송 실패", flush=True)
        time.sleep(1)  # rate limit 보호


def main() -> int:
    settings = load_settings(ROOT)
    overall_t0 = time.time()
    summary: list[dict] = []

    tg_send(
        settings.telegram_bot_token, settings.telegram_chat_id,
        "🚀 <b>1화~10화 자동 생성 시작</b>\n각 화 발행 즉시 본문 푸시.\n예상 60-90분.",
    )

    for n in CHAPTERS:
        print(f"\n=== Chapter {n} 시작 ===", flush=True)
        t0 = time.time()
        try:
            r = run_chapter_pipeline(WORK_ID, n, settings=settings)
        except Exception as e:
            elapsed = time.time() - t0
            print(f"  💥 예외 ({elapsed:.1f}s): {e}", flush=True)
            traceback.print_exc()
            tg_send(
                settings.telegram_bot_token, settings.telegram_chat_id,
                f"💥 <b>{n}화 예외 발생</b>\n<code>{e}</code>\n<b>전체 작업 중단</b>",
            )
            summary.append({"n": n, "status": "exception", "elapsed": elapsed, "error": str(e)})
            break

        elapsed = time.time() - t0
        if r.success:
            print(f"  ✅ 발행 완료 ({elapsed:.1f}s) — {r.chapter_path}", flush=True)
            send_chapter(r.chapter_path, n, settings)
            summary.append({
                "n": n, "status": "ok", "elapsed": elapsed,
                "review_rounds": len(r.review_history),
                "path": str(r.chapter_path),
            })
        else:
            print(f"  ❌ 실패 ({elapsed:.1f}s) — {r.failure_stage}: {r.failure_reason}", flush=True)
            tg_send(
                settings.telegram_bot_token, settings.telegram_chat_id,
                f"❌ <b>{n}화 발행 실패</b>\n단계: {r.failure_stage}\n사유: {r.failure_reason}\n다음 회차로 계속.",
            )
            summary.append({
                "n": n, "status": "fail", "elapsed": elapsed,
                "stage": r.failure_stage, "reason": r.failure_reason,
            })
            # 실패 시 다음 화로 진행 (장기 흐름 끊지 않음)

    overall_elapsed = time.time() - overall_t0
    ok_count = sum(1 for s in summary if s["status"] == "ok")
    fail_count = sum(1 for s in summary if s["status"] == "fail")
    exc_count = sum(1 for s in summary if s["status"] == "exception")

    final_msg = (
        f"🏁 <b>1-10화 자동 발행 마무리</b>\n\n"
        f"✅ 성공: <b>{ok_count}</b>화\n"
        f"❌ 실패: <b>{fail_count}</b>화\n"
        f"💥 예외: <b>{exc_count}</b>화\n"
        f"⏱ 총 시간: {overall_elapsed/60:.1f}분\n"
    )
    tg_send(settings.telegram_bot_token, settings.telegram_chat_id, final_msg)
    print(f"\n{final_msg}")

    out_path = ROOT / "docs" / "poc_results" / "chapters_1_10_summary.json"
    out_path.write_text(
        json.dumps(summary, ensure_ascii=False, indent=2), encoding="utf-8"
    )
    return 0 if fail_count == 0 and exc_count == 0 else 1


if __name__ == "__main__":
    sys.exit(main())
