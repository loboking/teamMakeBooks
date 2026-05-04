#!/usr/bin/env python3
"""ch055~100 LLM 검토 전용 스크립트 — direction/character/quality 3단계."""
from __future__ import annotations

import json
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "backend"))

from app.config import load_settings  # noqa: E402
from app.teams.reviewer.agent import ReviewerAgent  # noqa: E402
from app.teams.reviewer.prompts import REVIEW_SCHEMA, build_reviewer_prompt  # noqa: E402
from app.memory.loader import load_novel_context  # noqa: E402


def review_chapters(start: int, end: int, roles: list[str] | None = None) -> None:
    if roles is None:
        roles = ["direction", "character", "quality"]

    settings = load_settings(ROOT)
    work_id = "modern_fantasy_game_01"

    from app.providers.factory import get_provider
    model_key = settings.config["teams"]["reviewer"]["direction"]["model"]
    provider = get_provider(model_key, settings)

    results: list[dict] = []

    for ch in range(start, end + 1):
        ch_path = settings.novels_dir / work_id / "chapters" / f"ch{ch:03d}.md"
        if not ch_path.exists():
            print(f"ch{ch:03d}: 파일 없음, 건너뜀")
            continue

        body = ch_path.read_text("utf-8")

        try:
            ctx = load_novel_context(
                work_id, ch,
                novels_dir=settings.novels_dir,
                recent_n=settings.recent_summaries_n,
            )
        except Exception as e:
            print(f"ch{ch:03d}: 컨텍스트 로드 실패 ({e}), 건너뜀")
            continue

        chapter_results = []
        for role in roles:
            reviewer = ReviewerAgent(
                role,
                provider,
                temperature=float(settings.config.get("reviewer", {}).get("temperature", 0.2)),
                num_predict=int(settings.config.get("reviewer", {}).get("num_predict", 600)),
            )
            result = reviewer.review(body, ctx, 1, work_id)
            status = "✅" if result.passed else "❌"
            print(f"ch{ch:03d} [{role}]: {status} 점수={result.score} | {result.reason[:80]}")
            if not result.passed:
                print(f"  수정가이드: {result.feedback[:200]}")
            chapter_results.append({
                "chapter": ch,
                "role": role,
                "passed": result.passed,
                "score": result.score,
                "reason": result.reason,
                "feedback": result.feedback,
            })

        results.append({"ch": ch, "results": chapter_results})
        time.sleep(0.5)  # rate limit

    # 요약
    print("\n" + "=" * 60)
    total = len(results)
    for role in roles:
        passed = sum(1 for r in results for cr in r["results"] if cr["role"] == role and cr["passed"])
        failed = sum(1 for r in results for cr in r["results"] if cr["role"] == role and not cr["passed"])
        print(f"{role}: ✅{passed} ❌{failed} ({total}화)")

    # 실패 목록
    failures = [
        r for r in results for cr in r["results"] if not cr["passed"]
    ]
    if failures:
        print(f"\n❌ 수정 필요 챕터 ({len(failures)}건):")
        for f in failures:
            for cr in f["results"]:
                if not cr["passed"]:
                    print(f"  ch{f['ch']:03d} [{cr['role']}] 점수={cr['score']}: {cr['reason'][:80]}")

    # JSON 저장
    out_path = settings.logs_dir / f"review_{start}_{end}.json"
    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_text(json.dumps(results, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"\n결과 저장: {out_path}")


if __name__ == "__main__":
    start = int(sys.argv[1]) if len(sys.argv) > 1 else 55
    end = int(sys.argv[2]) if len(sys.argv) > 2 else 100
    roles = sys.argv[3].split(",") if len(sys.argv) > 3 else None
    print(f"[review] ch{start:03d}~ch{end:03d} | roles={roles or 'all'}")
    review_chapters(start, end, roles)
