#!/usr/bin/env python3
"""2화~10화 재생성 + 텔레그램 푸시 (새 호명 룰 적용)."""
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

CHAPTERS = list(range(2, 11))
WORK_ID = "modern_fantasy_game_01"
MAX_TG = 3500


def tg(token, chat_id, text, parse_mode="HTML"):
    body = json.dumps({"chat_id": chat_id, "text": text, "parse_mode": parse_mode,
                       "disable_web_page_preview": True}, ensure_ascii=False).encode()
    req = urllib.request.Request(f"https://api.telegram.org/bot{token}/sendMessage",
                                  data=body, headers={"Content-Type":"application/json; charset=utf-8"})
    try:
        with urllib.request.urlopen(req, timeout=15) as r: return json.load(r).get("ok")
    except Exception as e:
        print(f"  [tg fail] {e}", flush=True); return False


def split_text(text, max_len=MAX_TG):
    parts, rem = [], text
    while len(rem) > max_len:
        cut = rem.rfind('\n\n', 0, max_len)
        if cut == -1: cut = rem.rfind('\n', 0, max_len)
        if cut == -1 or cut < max_len // 2: cut = max_len
        parts.append(rem[:cut].rstrip()); rem = rem[cut:].lstrip()
    if rem: parts.append(rem)
    return parts


def push_chapter(path, n, settings, stats):
    body = path.read_text(encoding="utf-8")
    parts = split_text(body)
    total = len(parts)
    head_meta = (
        f"♻️ <b>{n}화 재생성 (새 호명 룰)</b>\n"
        f"⏱ {stats['elapsed']:.0f}초 / 검수 라운드 {stats['rounds']}회\n"
        f"📊 강이준 풀 {stats['kang']}회·이준 {stats['ijun']}회 / 박세린 풀 {stats['sereen']}회·세린 {stats['serin']}회\n\n"
    )
    for i, p in enumerate(parts, 1):
        head = head_meta + f"📖 <b>{n}화 ({i}/{total})</b>\n\n" if i == 1 else f"📖 <b>{n}화 (계속 {i}/{total})</b>\n\n"
        esc = p.replace("&","&amp;").replace("<","&lt;").replace(">","&gt;")
        tg(settings.telegram_bot_token, settings.telegram_chat_id, head + esc)
        time.sleep(1)


def chapter_stats(body):
    kang = body.count("강이준")
    sereen = body.count("박세린")
    ijun = body.count("이준") - kang
    serin = body.count("세린") - sereen
    return {"kang": kang, "sereen": sereen, "ijun": ijun, "serin": serin}


def main():
    settings = load_settings(ROOT)
    overall_t0 = time.time()
    summary = []

    tg(settings.telegram_bot_token, settings.telegram_chat_id,
       "♻️ <b>2-10화 재생성 시작 (새 호명 룰)</b>\n예상 30-40분.")

    for n in CHAPTERS:
        print(f"\n=== Chapter {n} 재생성 ===", flush=True)
        t0 = time.time()
        try:
            r = run_chapter_pipeline(WORK_ID, n, settings=settings)
        except Exception as e:
            elapsed = time.time() - t0
            print(f"  💥 예외 ({elapsed:.1f}s): {e}", flush=True)
            traceback.print_exc()
            tg(settings.telegram_bot_token, settings.telegram_chat_id,
               f"💥 <b>{n}화 예외</b>\n<code>{e}</code>")
            summary.append({"n": n, "status": "exception", "elapsed": elapsed})
            break

        elapsed = time.time() - t0
        if r.success:
            body = Path(r.chapter_path).read_text(encoding="utf-8")
            st = chapter_stats(body)
            stats = {"elapsed": elapsed, "rounds": len(r.review_history), **st}
            print(f"  ✅ ({elapsed:.0f}s) 강이준 {st['kang']}/이준 {st['ijun']} | 박세린 {st['sereen']}/세린 {st['serin']}", flush=True)
            push_chapter(Path(r.chapter_path), n, settings, stats)
            summary.append({"n": n, "status": "ok", "elapsed": elapsed,
                            "rounds": len(r.review_history), **st})
        else:
            print(f"  ❌ 실패 ({elapsed:.1f}s): {r.failure_stage} - {r.failure_reason}", flush=True)
            tg(settings.telegram_bot_token, settings.telegram_chat_id,
               f"❌ <b>{n}화 실패</b>\n단계: {r.failure_stage}\n사유: {r.failure_reason}\n다음 회차로 계속.")
            summary.append({"n": n, "status": "fail", "elapsed": elapsed,
                            "stage": r.failure_stage, "reason": r.failure_reason})

    total_elapsed = time.time() - overall_t0
    ok = sum(1 for s in summary if s["status"] == "ok")
    fail = sum(1 for s in summary if s["status"] == "fail")
    exc = sum(1 for s in summary if s["status"] == "exception")
    avg_kang = sum(s.get("kang", 0) for s in summary if s["status"] == "ok") / max(1, ok)
    avg_sereen = sum(s.get("sereen", 0) for s in summary if s["status"] == "ok") / max(1, ok)

    final = (
        f"🏁 <b>2-10화 재생성 마무리</b>\n\n"
        f"✅ 성공: {ok} | ❌ 실패: {fail} | 💥 예외: {exc}\n"
        f"⏱ 총: {total_elapsed/60:.1f}분\n"
        f"📊 평균 풀네임 — 강이준 {avg_kang:.1f}회 / 박세린 {avg_sereen:.1f}회 (목표 ≤5)"
    )
    tg(settings.telegram_bot_token, settings.telegram_chat_id, final)
    print(final)

    (ROOT / "docs" / "poc_results" / "chapters_2_10_regen_summary.json").write_text(
        json.dumps(summary, ensure_ascii=False, indent=2), encoding="utf-8"
    )
    return 0 if fail == 0 and exc == 0 else 1


if __name__ == "__main__":
    sys.exit(main())
