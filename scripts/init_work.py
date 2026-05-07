#!/usr/bin/env python3
"""신규 소설 메타 파이프라인 CLI 진입점.

컨셉 한 줄 → 엔딩 → 3막 100화 줄거리 자동 생성.

사용 예:
    .venv/bin/python scripts/init_work.py --logline "F급 짐꾼이 시스템 버그를 발견해 S급으로 각성" \\
        --genre 헌터물 --total 100 --protagonist 강이준 --auto

    .venv/bin/python scripts/init_work.py --input concept.yaml --auto

    .venv/bin/python scripts/init_work.py --logline "..." --dry-run
"""
from __future__ import annotations

import argparse
import re
import sys
import time
import traceback
from pathlib import Path

# backend를 import 경로에 추가
ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "backend"))

from app.config import load_settings  # noqa: E402
from app.orchestrator.meta_graph import invoke_meta_pipeline  # noqa: E402
from app.utils.alert import send_telegram  # noqa: E402


# ── 유틸 ─────────────────────────────────────────────────────────────────────


def _slugify(text: str) -> str:
    """logline → work_id 슬러그 (공백→_, 특수문자 제거, 최대 30자 소문자)."""
    text = re.sub(r"[^\w\s가-힣]", "", text)
    text = re.sub(r"\s+", "_", text.strip())
    return text[:30].lower() or "novel"


def _load_yaml_input(path: Path) -> dict:
    """yaml 파일을 읽어 concept_input dict로 반환."""
    import yaml

    content = path.read_text(encoding="utf-8")
    data = yaml.safe_load(content)
    if not isinstance(data, dict):
        raise ValueError(f"yaml 파일이 dict 형식이 아닙니다: {path}")
    return data


def _print_concept_preview(concept: dict | None) -> None:
    if not concept:
        print("  (컨셉 없음)")
        return
    print(f"  logline : {concept.get('logline', '')[:80]}")
    print(f"  genre   : {concept.get('genre', '')} / mood: {concept.get('mood', '')}")
    print(f"  summary : {concept.get('summary', '')[:120]}...")


def _print_ending_preview(ending: dict | None) -> None:
    if not ending:
        print("  (엔딩 없음)")
        return
    print(f"  엔딩    : {ending.get('summary', '')[:80]}")
    print(f"  3막클라 : {ending.get('act3_climax', '')[:80]}")
    for act in ending.get("acts", []):
        print(f"  {act.get('name','?')} : {act.get('summary','')[:60]}...")


def _print_skeleton_preview(skeleton: list[dict] | None, act_n: int) -> None:
    """해당 막 처음 3화 + 마지막 3화 미리보기."""
    if not skeleton:
        print("  (줄거리 없음)")
        return
    act_chapters = [ch for ch in skeleton if ch.get("act") == act_n]
    if not act_chapters:
        return
    head = act_chapters[:3]
    tail = act_chapters[-3:] if len(act_chapters) > 3 else []
    for ch in head:
        print(f"  ch{ch['chapter_n']:03d}: {ch.get('overall','')[:70]}...")
    if tail:
        print("  ...")
        for ch in tail:
            print(f"  ch{ch['chapter_n']:03d}: {ch.get('overall','')[:70]}...")


# ── 단계 검토 게이트 (M2 작업 예정) ───────────────────────────────────────────
# TODO(M2): --auto 아닐 때 각 메이저 단계 후 대화식 게이트 구현.
#   - [Enter] 다음 / [r] 재생성 / [e] 직접 편집 (EDITOR 환경변수) / [q] 중단
#   - 현재 M1에선 --auto 여부와 무관하게 전 자동 진행.
#   - 단계 게이트는 그래프 외부(CLI 루프)에서 처리할 예정.


# ── 메인 ─────────────────────────────────────────────────────────────────────


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="teamMakeBooks 신규 소설 메타 파이프라인 (컨셉 → 100화 줄거리)",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
예시:
  # 로그라인에서 전 자동
  python scripts/init_work.py --logline "F급 짐꾼이 시스템 버그를 발견해 S급으로 각성" --auto

  # yaml 입력
  python scripts/init_work.py --input concept.yaml --auto

  # dry-run (LLM 호출 없이 검증만)
  python scripts/init_work.py --logline "..." --dry-run
""",
    )

    # 입력 소스 (상호배타 — --logline XOR --input)
    input_group = parser.add_mutually_exclusive_group()
    input_group.add_argument("--logline", metavar="TEXT", help="작품 로그라인 (필수, --input 없을 때)")
    input_group.add_argument("--input", metavar="PATH", type=Path, help="concept yaml 파일 경로")

    # 선택 옵션
    parser.add_argument("--genre", default="modern_fantasy", metavar="TEXT", help="장르 (기본: modern_fantasy)")
    parser.add_argument("--mood", default="", metavar="TEXT", help="분위기/톤")
    parser.add_argument("--total", type=int, default=100, metavar="INT", help="총 화수 (기본: 100)")
    parser.add_argument("--protagonist", default="", metavar="TEXT", help="주인공 이름")
    parser.add_argument("--keyword", dest="keywords", action="append", default=[], metavar="TEXT",
                        help="키워드 (반복 가능: --keyword 시스템물 --keyword 각성물)")
    parser.add_argument("--forbidden", dest="forbidden", action="append", default=[], metavar="TEXT",
                        help="금지 요소 (반복 가능)")
    parser.add_argument("--reference-tone", default="", metavar="TEXT", help="참고 톤 (기존 작품 work_id 등)")
    parser.add_argument("--work-id", default="", metavar="TEXT", help="work_id 직접 지정 (기본: 자동 생성)")

    # 실행 모드
    parser.add_argument("--auto", action="store_true",
                        help="단계 검토 건너뛰고 전 자동 진행 (M1 기본 동작)")
    parser.add_argument("--dry-run", action="store_true",
                        help="LLM 호출 없이 입력 검증 + 디렉토리 확인만")

    return parser


def _dry_run(concept_input: dict, work_id: str, settings) -> int:
    """LLM 없이: 입력 정규화 확인 + novels/{work_id}/_init/ 생성 가능 여부 체크."""
    from datetime import datetime, timezone

    print("[dry-run] 입력 검증 중...")
    logline = concept_input.get("logline", "")
    if not logline:
        print("[dry-run] 오류: logline이 비어있습니다.", file=sys.stderr)
        return 1

    # work_id 생성 로직 시뮬레이션
    if not work_id:
        ts = datetime.now(timezone.utc).strftime("%y%m%d")
        genre_slug = concept_input.get("genre", "novel")[:10].replace(" ", "_")
        work_id = f"{genre_slug}_{_slugify(logline)}_{ts}"

    init_dir: Path = settings.novels_dir / work_id / "_init"
    print(f"[dry-run] work_id  = {work_id}")
    print(f"[dry-run] init_dir = {init_dir}")
    print(f"[dry-run] novels_dir 존재: {settings.novels_dir.exists()}")

    # 디렉토리 생성 가능 여부 테스트 (실제로 만들지 않음)
    try:
        init_dir.mkdir(parents=True, exist_ok=True)
        print(f"[dry-run] init_dir 생성 가능 확인 (생성됨: {init_dir})")
    except OSError as e:
        print(f"[dry-run] 오류: init_dir 생성 불가 — {e}", file=sys.stderr)
        return 1

    print(f"[dry-run] concept_input 키: {list(concept_input.keys())}")
    print("[dry-run] 검증 완료. LLM 호출 없음.")
    return 0


def main() -> int:
    parser = build_parser()
    args = parser.parse_args()

    # --logline / --input 둘 다 없으면 오류
    if args.logline is None and args.input is None:
        parser.error("--logline 또는 --input 중 하나는 필수입니다.")

    settings = load_settings(ROOT)
    print(f"[startup] project_root = {settings.project_root}")
    print(f"[startup] novels_dir   = {settings.novels_dir}")

    # concept_input 조립
    if args.input:
        concept_input = _load_yaml_input(args.input)
        # CLI 옵션으로 yaml 값 덮어쓰기 (명시적으로 지정된 경우만)
        if args.genre != "modern_fantasy":
            concept_input["genre"] = args.genre
        if args.mood:
            concept_input["mood"] = args.mood
        if args.total != 100:
            concept_input["total_chapters"] = args.total
        if args.protagonist:
            concept_input["protagonist"] = args.protagonist
        if args.keywords:
            concept_input.setdefault("keywords", [])
            concept_input["keywords"].extend(args.keywords)
        if args.forbidden:
            concept_input.setdefault("forbidden", [])
            concept_input["forbidden"].extend(args.forbidden)
        if args.reference_tone:
            concept_input["reference_tone"] = args.reference_tone
    else:
        concept_input = {
            "logline": args.logline,
            "genre": args.genre,
            "mood": args.mood,
            "total_chapters": args.total,
            "protagonist": args.protagonist,
            "keywords": args.keywords,
            "forbidden": args.forbidden,
            "reference_tone": args.reference_tone,
            "work_id": args.work_id or None,
        }

    work_id = args.work_id or concept_input.get("work_id") or ""

    # dry-run 분기
    if args.dry_run:
        return _dry_run(concept_input, work_id, settings)

    # TODO(M2): --auto가 False일 때 단계 검토 게이트 구현.
    #   현재 M1에선 --auto 플래그 무관하게 전 자동 진행.
    if not args.auto:
        print("[info] 단계 검토 모드는 M2에서 구현 예정. 현재는 자동 모드로 진행합니다.")

    # 파이프라인 실행
    logline_preview = concept_input.get("logline", "")[:60]
    print(f"\n[meta pipeline] 시작: {logline_preview}...")
    print(f"[meta pipeline] genre={concept_input.get('genre')} / total={concept_input.get('total_chapters')}화")

    t0 = time.time()
    try:
        result = invoke_meta_pipeline(
            concept_input,
            settings=settings,
            work_id=work_id or None,
        )
    except Exception as e:
        print(f"[fatal] {e}", file=sys.stderr)
        traceback.print_exc()
        send_telegram(f"[META PIPELINE 예외] {e}", settings)
        return 1

    elapsed = time.time() - t0

    if result.get("success"):
        init_dir = result.get("init_dir")
        plot_skeleton = result.get("plot_skeleton") or []
        print(f"\n[SUCCESS] {elapsed:.1f}s")
        print(f"  work_id    : {result.get('work_id')}")
        print(f"  산출물     : {init_dir}")
        print(f"  총화수     : {len(plot_skeleton)}화")
        print(f"  검수 라운드: {len(result.get('review_history', []))}건")

        # 텔레그램 완료 알림
        msg = (
            f"[META 완료] work_id={result.get('work_id')}\n"
            f"{len(plot_skeleton)}화 줄거리 생성 완료 ({elapsed:.1f}s)\n"
            f"→ {init_dir}"
        )
        send_telegram(msg, settings)
        return 0
    else:
        print(f"\n[FAIL] {elapsed:.1f}s")
        print(f"  단계  : {result.get('failure_stage')}")
        print(f"  사유  : {result.get('failure_reason')}")
        return 1


if __name__ == "__main__":
    sys.exit(main())
