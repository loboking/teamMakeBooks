#!/usr/bin/env python3
"""검수자 회귀 하네스 v3 — 20개 케이스 + 결정론적 호칭 검수기 통합."""
from __future__ import annotations

import json
import sys
import time
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "backend"))

from app.config import load_settings  # noqa: E402
from app.memory.loader import (  # noqa: E402
    BeatOutline,
    ChapterOutline,
    NovelContext,
)
from app.providers import get_provider  # noqa: E402
from app.teams.reviewer import ReviewerAgent  # noqa: E402
from app.teams.reviewer.naming_checker import run_naming_check  # noqa: E402


CASES: list[dict[str, Any]] = [
    # ── 통과 (3) ──
    {
        "name": "01_PASS_정상_1막",
        "path": "tests/cases/01_pass_normal.md",
        "chapter_n": 1,
        "expected": {"direction": "통과", "character": "통과", "quality": "통과", "naming": "통과"},
    },
    {
        "name": "02_PASS_정상_3막",
        "path": "tests/cases/08_pass_act3_normal.md",
        "chapter_n": 96,
        "expected": {"direction": "통과", "character": "통과", "quality": "통과", "naming": "통과"},
    },
    {
        "name": "03_PASS_정상_4막카타르시스",
        "path": "tests/cases/09_pass_act4_catharsis.md",
        "chapter_n": 190,
        "expected": {"direction": "통과", "character": "통과", "quality": "통과", "naming": "통과"},
    },
    # ── 방향성 반려 (4) ──
    {
        "name": "04_REJECT_방향성_빵집",
        "path": "tests/cases/02_reject_direction_bakery.md",
        "chapter_n": 1,
        "expected": {"direction": "반려"},
    },
    {
        "name": "05_REJECT_방향성_시스템파괴",
        "path": "tests/cases/10_reject_direction_system_destroy.md",
        "chapter_n": 225,
        "expected": {"direction": "반려"},
    },
    {
        "name": "06_REJECT_방향성_회장최종보스",
        "path": "tests/cases/11_reject_direction_chairman_final_boss.md",
        "chapter_n": 220,
        "expected": {"direction": "반려"},
    },
    {
        "name": "07_REJECT_방향성_1화회장등장",
        "path": "tests/cases/12_reject_direction_chairman_act1.md",
        "chapter_n": 1,
        "expected": {"direction": "반려"},
    },
    # ── 캐릭터 반려 (4 — character LLM) ──
    {
        "name": "08_REJECT_캐릭터_S급강이준",
        "path": "tests/cases/03_reject_character_s_rank.md",
        "chapter_n": 1,
        "expected": {"character": "반려"},
    },
    {
        "name": "09_REJECT_캐릭터_호칭모순",
        "path": "tests/cases/04_reject_character_naming.md",
        "chapter_n": 1,
        "expected": {"character": "반려", "naming": "반려"},
    },
    {
        "name": "10_REJECT_캐릭터_어머니살아있음",
        "path": "tests/cases/13_reject_character_mother_alive.md",
        "chapter_n": 1,
        "expected": {"character": "반려"},
    },
    {
        "name": "11_REJECT_캐릭터_세린활무기",
        "path": "tests/cases/14_reject_character_serin_bow.md",
        "chapter_n": 1,
        "expected": {"character": "반려"},
    },
    {
        "name": "12_REJECT_캐릭터_세린짝사랑",
        "path": "tests/cases/15_reject_character_serin_crush.md",
        "chapter_n": 50,
        "expected": {"character": "반려"},
    },
    # ── 완성도 반려 (5) ──
    {
        "name": "13_REJECT_완성도_부서진문장",
        "path": "tests/cases/05_reject_quality_broken.md",
        "chapter_n": 1,
        "expected": {"quality": "반려"},
    },
    {
        "name": "14_REJECT_완성도_묘사반복",
        "path": "tests/cases/06_reject_quality_repetition.md",
        "chapter_n": 1,
        "expected": {"quality": "반려"},
    },
    {
        "name": "15_REJECT_완성도_시간점프",
        "path": "tests/cases/07_reject_quality_time_jump.md",
        "chapter_n": 1,
        "expected": {"quality": "반려"},
    },
    {
        "name": "16_REJECT_완성도_신파과다",
        "path": "tests/cases/16_reject_quality_melodrama.md",
        "chapter_n": 1,
        "expected": {"quality": "반려"},
    },
    {
        "name": "17_REJECT_완성도_클리프행어없음",
        "path": "tests/cases/17_reject_quality_no_cliffhanger.md",
        "chapter_n": 1,
        "expected": {"quality": "반려"},
    },
    # ── 결정론적 호칭 반려 (3) ──
    {
        "name": "18_REJECT_호칭_세린이강이준호명",
        "path": "tests/cases/18_reject_naming_serin_kang.md",
        "chapter_n": 5,
        "expected": {"naming": "반려"},
    },
    {
        "name": "19_REJECT_호칭_이서가오빠외호명",
        "path": "tests/cases/19_reject_naming_iseo_no_oppa.md",
        "chapter_n": 5,
        "expected": {"naming": "반려"},
    },
    {
        "name": "20_REJECT_호칭_1막회장강이준님",
        "path": "tests/cases/20_reject_naming_chairman_act1_honorific.md",
        "chapter_n": 1,
        "expected": {"naming": "반려"},
    },
]

WORK_ID = "modern_fantasy_game_01"
CHAPTER_OUTLINE_OVERALL_DEFAULT = (
    "강이준이 만년 F급 짐꾼으로 D급 던전에 투입 → 천장 붕괴로 던전 심층부 추락 → "
    "동료들에게 죽었다 여겨짐 → 어둠 속 깨어나 진명 시스템 각성 → 첫 퀘스트 "
    "'이 던전에서 살아 나가라' → 던전 깊은 곳 무언가와 마주치는 클리프행어로 끝."
)


def build_test_context(settings, chapter_n: int) -> NovelContext:
    base = settings.novels_dir / WORK_ID

    def opt(p: Path) -> str:
        return p.read_text(encoding="utf-8") if p.exists() else ""

    return NovelContext(
        work_id=WORK_ID,
        world_bible=(base / "world_bible.md").read_text(encoding="utf-8"),
        characters=(base / "characters.md").read_text(encoding="utf-8"),
        plot_outline=(base / "plot_outline.md").read_text(encoding="utf-8"),
        theme=opt(base / "theme.md"),
        naming_table=opt(base / "naming_table.md"),
        recent_summaries=[],
        current_chapter_n=chapter_n,
        chapter_outline=ChapterOutline(
            chapter_n=chapter_n,
            overall=CHAPTER_OUTLINE_OVERALL_DEFAULT,
            beats=[BeatOutline(name="harness", instruction="(harness용 컨텍스트)")],
        ),
        unresolved_threads=opt(base / "memory" / "unresolved_threads.md"),
        continuity_log=opt(base / "memory" / "continuity_log.md"),
        event_log=opt(base / "memory" / "event_log.md"),
        character_state=opt(base / "memory" / "character_state.md"),
        world_state=opt(base / "memory" / "world_state.md"),
    )


def run_llm_review(role: str, body: str, ctx, settings) -> dict[str, Any]:
    agent = ReviewerAgent(
        role,
        get_provider(settings.model_key("reviewer", role), settings),
    )
    t0 = time.time()
    r = agent.review(body, ctx, attempt=1, work_id="harness")
    return {
        "actual": "통과" if r.passed else "반려",
        "score": r.score,
        "reason": r.reason,
        "feedback": r.feedback,
        "elapsed_s": round(time.time() - t0, 1),
        "raw": r.raw,
        "parse_error": r.parse_error,
    }


def run_deterministic_naming(body: str, naming_table: str, chapter_n: int) -> dict[str, Any]:
    t0 = time.time()
    r = run_naming_check(body, naming_table, chapter_n)
    return {
        "actual": "통과" if r.passed else "반려",
        "score": r.score,
        "reason": (f"호칭 위반 {len(r.violations)}건" if not r.passed else "OK"),
        "feedback": r.feedback,
        "elapsed_s": round(time.time() - t0, 2),
        "raw": json.dumps([{
            "type": v.type, "detail": v.detail, "excerpt": v.excerpt,
        } for v in r.violations], ensure_ascii=False),
        "parse_error": None,
    }


def run() -> int:
    settings = load_settings(ROOT)
    print(f"[harness] ollama={settings.ollama_base_url}")
    print(f"[harness] cases={len(CASES)}")

    results: list[dict[str, Any]] = []
    t_start = time.time()

    for case in CASES:
        body = (ROOT / case["path"]).read_text(encoding="utf-8")
        chapter_n = case["chapter_n"]
        ctx = build_test_context(settings, chapter_n)

        case_result: dict[str, Any] = {
            "name": case["name"],
            "expected": case["expected"],
            "reviews": {},
        }
        for role, expected in case["expected"].items():
            if role == "naming":
                res = run_deterministic_naming(body, ctx.naming_table, chapter_n)
            else:
                res = run_llm_review(role, body, ctx, settings)
            res["expected"] = expected
            res["match"] = (res["actual"] == expected)
            case_result["reviews"][role] = res
            mark = "✅" if res["match"] else "❌"
            print(
                f"  {case['name']:<40} / {role:<10} : "
                f"expected={expected} actual={res['actual']} score={res['score']} {mark} ({res['elapsed_s']}s)",
                flush=True,
            )
        results.append(case_result)

    total = sum(len(r["reviews"]) for r in results)
    matches = sum(1 for r in results for v in r["reviews"].values() if v["match"])
    elapsed = time.time() - t_start

    out_dir = ROOT / "docs" / "poc_results"
    out_dir.mkdir(parents=True, exist_ok=True)
    json_path = out_dir / "reviewer_harness_v3.json"
    md_path = out_dir / "reviewer_harness_v3.md"

    json_path.write_text(json.dumps(results, ensure_ascii=False, indent=2), encoding="utf-8")

    with md_path.open("w", encoding="utf-8") as f:
        f.write(f"# Reviewer Harness v3 — {matches}/{total} 매치\n\n")
        f.write(f"- 총 시간: {elapsed:.1f}s\n")
        f.write(f"- 케이스: {len(CASES)}개 (통과 3 + 방향성 4 + 캐릭터 5 + 완성도 5 + 호칭 3)\n\n")
        for c in results:
            f.write(f"### {c['name']}\n\n")
            f.write("| Role | expected | actual | score | match | elapsed |\n")
            f.write("|------|----------|--------|-------|-------|---------|\n")
            for role, v in c["reviews"].items():
                m = "✅" if v["match"] else "❌"
                f.write(
                    f"| {role} | {v['expected']} | {v['actual']} | {v['score']} | {m} | {v['elapsed_s']}s |\n"
                )
            f.write("\n")
            for role, v in c["reviews"].items():
                if not v["match"]:
                    f.write(f"#### ❌ {role} 미매치 — 사유\n\n")
                    f.write(f"- reason: {v.get('reason', '')}\n")
                    f.write(f"- raw:\n```\n{v.get('raw', '')[:600]}\n```\n\n")

    print(f"\n=== {matches}/{total} 매치 ({elapsed:.1f}s) ===")
    print(f"저장: {md_path}")
    return 0 if matches == total else 1


if __name__ == "__main__":
    sys.exit(run())
