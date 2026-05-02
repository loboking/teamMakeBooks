#!/usr/bin/env python3
"""PoC 1편 자동 생성 진입점."""
from __future__ import annotations

import argparse
import sys
import time
import traceback
from pathlib import Path

# backend를 import 가능하게
ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "backend"))

from app.config import load_settings  # noqa: E402
from app.orchestrator import run_chapter_pipeline  # noqa: E402
from app.utils.alert import send_telegram  # noqa: E402


def main() -> int:
    parser = argparse.ArgumentParser(description="teamMakeBooks PoC 1편 자동 생성")
    parser.add_argument("--work-id", required=True)
    parser.add_argument("--chapter", type=int, required=True)
    parser.add_argument("--dry-run", action="store_true", help="LLM 호출 없이 파일/설정 검증")
    args = parser.parse_args()

    settings = load_settings(ROOT)
    print(f"[startup] project_root={settings.project_root}")
    print(f"[startup] ollama={settings.ollama_base_url}")
    print(f"[startup] writer.model={settings.model_key('writer')}")

    if args.dry_run:
        from app.memory import load_novel_context, load_persona, load_work_meta

        print("[dry-run] 컨텍스트 + 페르소나 로드 시도...")
        ctx = load_novel_context(
            args.work_id, args.chapter,
            novels_dir=settings.novels_dir,
            recent_n=settings.recent_summaries_n,
        )
        meta = load_work_meta(args.work_id, settings.novels_dir)
        persona = load_persona(meta["author_id"], settings.authors_dir)
        print(f"[dry-run] OK | beats={len(ctx.chapter_outline.beats)} persona={persona.name}")
        return 0

    t0 = time.time()
    try:
        result = run_chapter_pipeline(
            work_id=args.work_id, chapter_n=args.chapter, settings=settings,
        )
    except Exception as e:
        print(f"[fatal] {e}", file=sys.stderr)
        traceback.print_exc()
        send_telegram(f"💥 <b>PoC 실패 (예외)</b>\n<code>{e}</code>", settings)
        return 1

    elapsed = time.time() - t0
    if result.success:
        msg = (
            f"✅ <b>PoC 발행 완료</b>\n"
            f"work: <code>{result.work_id}</code>\n"
            f"chapter: <code>{result.chapter_n}</code>\n"
            f"⏱ {elapsed:.1f}s\n"
            f"검수 라운드: {len(result.review_history)}\n"
            f"파일: <code>{result.chapter_path}</code>"
        )
        print(f"\n[SUCCESS] {result.chapter_path} ({elapsed:.1f}s)")
    else:
        msg = (
            f"❌ <b>PoC 실패</b>\n"
            f"단계: {result.failure_stage}\n"
            f"⏱ {elapsed:.1f}s\n"
            f"사유: {result.failure_reason}"
        )
        print(f"\n[FAIL] {result.failure_stage}: {result.failure_reason} ({elapsed:.1f}s)")

    send_telegram(msg, settings)
    return 0 if result.success else 1


if __name__ == "__main__":
    sys.exit(main())
