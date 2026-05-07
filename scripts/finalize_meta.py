#!/usr/bin/env python3
"""메타 산출물 → 회차 파이프라인 진입 가능 상태 변환.

입력: novels/{work_id}/_init/{concept,ending,plot_skeleton}.yaml
산출:
  - novels/{work_id}/world_bible.md
  - novels/{work_id}/characters.md
  - novels/{work_id}/naming_table.md
  - novels/{work_id}/theme.md  (간이)
  - novels/{work_id}/meta.json  (author_id 채움)
  - novels/{work_id}/chapter_outlines/ch_n.yaml  (overall + beats[3])
  - authors/{author_id}.yaml

Usage:
  python scripts/finalize_meta.py --work-id <wid> [--from N --to M] [--skip-assets]

옵션:
  --from N --to M : ch_n.yaml 변환 범위 (기본: 전 회차)
  --skip-assets   : 사전 자산 (world/char/naming/persona) 생성 건너뜀.
                    이미 만들어진 work_id에 대해 outline만 추가 변환할 때.
"""
from __future__ import annotations

import argparse
import json
import sys
import time
from pathlib import Path

import yaml

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "backend"))

from app.config import load_settings  # noqa: E402
from app.providers import LLMProviderError, get_provider  # noqa: E402
from app.teams.meta_writer import MetaWriterAgent  # noqa: E402


# ─────────────────────────────────────────────────────────────────────────────
# markdown 직렬화 헬퍼
# ─────────────────────────────────────────────────────────────────────────────


def _characters_to_md(characters: list[dict], title: str) -> str:
    out = [f"# 등장인물 정의 — {title}\n", "> **호칭은 `naming_table.md` 참조.** 본 문서는 인물 정의·Arc 중심.\n"]
    role_order = {"주인공": 0, "조력자": 1, "적대자": 2, "조연": 3}
    chars = sorted(characters, key=lambda c: role_order.get(c.get("role", ""), 9))
    for c in chars:
        out.append(f"\n## {c.get('name', '?')} ({c.get('role', '')})")
        if c.get("rank"):
            out.append(f"- **등급**: {c['rank']}")
        if c.get("job"):
            out.append(f"- **직업/소속**: {c['job']}")
        if c.get("personality"):
            out.append(f"- **성격**: {c['personality']}")
        if c.get("appearance"):
            out.append(f"- **외모**: {c['appearance']}")
        if c.get("background"):
            out.append(f"- **배경**: {c['background']}")
        if c.get("arc"):
            out.append(f"- **Arc**: {c['arc']}")
    return "\n".join(out) + "\n"


def _naming_to_md(pairs: list[dict], title: str) -> str:
    out = [
        f"# 호칭표 — {title}\n",
        "> **결정론적 호칭 검수기의 ground truth.** 본문 속 모든 인물 간 호칭은 여기 정의된 것만 사용.\n",
        "## 형식\n",
        "```\n[화자 → 청자]: \"호칭\" (어조/맥락)\n```\n",
    ]
    # speaker별 그룹
    by_speaker: dict[str, list[dict]] = {}
    for p in pairs:
        by_speaker.setdefault(p.get("speaker", "?"), []).append(p)
    for speaker, items in by_speaker.items():
        out.append(f"\n## {speaker}")
        for p in items:
            ctx = f" ({p['context']})" if p.get("context") else ""
            out.append(f"[{speaker} → {p.get('listener','?')}]: \"{p.get('address','?')}\"{ctx}")
    return "\n".join(out) + "\n"


def _theme_md(concept: dict) -> str:
    return (
        f"# 테마 — {concept.get('logline', '')[:60]}\n\n"
        f"## 장르 / 분위기\n- {concept.get('genre','')} / {concept.get('mood','')}\n\n"
        f"## 키워드\n- {', '.join(concept.get('keywords', []) or [])}\n\n"
        f"## 금지 요소\n- {', '.join(concept.get('forbidden', []) or []) or '없음'}\n\n"
        f"## 한 줄 요약\n{concept.get('summary', '')}\n"
    )


# ─────────────────────────────────────────────────────────────────────────────
# 메인
# ─────────────────────────────────────────────────────────────────────────────


def main() -> int:
    parser = argparse.ArgumentParser(description="메타 산출물 → 회차 파이프라인 진입용 자산/outlines 변환")
    parser.add_argument("--work-id", required=True)
    parser.add_argument("--from", dest="ch_from", type=int, default=1, help="ch_n.yaml 변환 시작 (기본 1)")
    parser.add_argument("--to", dest="ch_to", type=int, default=0, help="ch_n.yaml 변환 끝 (0이면 전체)")
    parser.add_argument("--skip-assets", action="store_true", help="사전 자산 생성 건너뜀")
    parser.add_argument("--skip-outlines", action="store_true", help="ch_n.yaml 변환 건너뜀")
    args = parser.parse_args()

    settings = load_settings(ROOT)
    work_dir = settings.novels_dir / args.work_id
    init_dir = work_dir / "_init"
    if not init_dir.exists():
        print(f"[finalize] init 디렉토리 없음: {init_dir}", file=sys.stderr)
        return 1

    concept = yaml.safe_load((init_dir / "concept.yaml").read_text(encoding="utf-8"))
    ending = yaml.safe_load((init_dir / "ending.yaml").read_text(encoding="utf-8"))
    skel = yaml.safe_load((init_dir / "plot_skeleton.yaml").read_text(encoding="utf-8"))
    chapters = skel.get("chapters", [])
    total = int(skel.get("total", len(chapters)))
    print(f"[finalize] {args.work_id} / {total}화 / chapters={len(chapters)}")

    # MetaWriterAgent (저렴하게 — concept temperature 사용)
    cfg = settings.config.get("meta_writer", {})
    writer = MetaWriterAgent(
        get_provider(settings.model_key("meta_writer", "concept"), settings),
        temperature=float(cfg.get("ending_temperature", 0.6)),
        num_predict=int(cfg.get("ending_num_predict", 1200)),
        logs_dir=settings.logs_dir,
    )

    # ── 사전 자산 ─────────────────────────────────────────────────────────
    if not args.skip_assets:
        title = concept.get("summary", "")[:30] or args.work_id
        author_id = f"{args.work_id}_writer_01"

        print("[finalize] world_bible 생성...")
        t0 = time.time()
        wb = writer.generate_world_bible(concept, ending, chapters, work_id=args.work_id)
        print(f"  {time.time()-t0:.1f}s, {len(wb)}자")

        print("[finalize] characters 생성...")
        t0 = time.time()
        chars = writer.generate_characters(concept, ending, chapters, work_id=args.work_id)
        print(f"  {time.time()-t0:.1f}s, {len(chars)}명")

        print("[finalize] naming_table 생성...")
        t0 = time.time()
        pairs = writer.generate_naming_table(chars, work_id=args.work_id)
        print(f"  {time.time()-t0:.1f}s, {len(pairs)}쌍")

        print("[finalize] persona 생성...")
        t0 = time.time()
        persona = writer.generate_persona(concept, work_id=args.work_id, author_id=author_id)
        print(f"  {time.time()-t0:.1f}s, name={persona['name']}")

        # 저장
        work_dir.mkdir(parents=True, exist_ok=True)
        (work_dir / "world_bible.md").write_text(wb, encoding="utf-8")
        (work_dir / "characters.md").write_text(_characters_to_md(chars, title), encoding="utf-8")
        (work_dir / "naming_table.md").write_text(_naming_to_md(pairs, title), encoding="utf-8")
        (work_dir / "theme.md").write_text(_theme_md(concept), encoding="utf-8")

        # meta.json 갱신
        meta_path = work_dir / "meta.json"
        meta = json.loads(meta_path.read_text(encoding="utf-8")) if meta_path.exists() else {}
        meta.update({
            "work_id": args.work_id,
            "title": title,
            "genre": concept.get("genre", ""),
            "author_id": author_id,
            "is_ai_persona": True,
            "copyright": meta.get("copyright", "© 2026 teamMakeBooks"),
            "published_chapters": meta.get("published_chapters", 0),
            "total_planned": total,
        })
        meta_path.write_text(json.dumps(meta, ensure_ascii=False, indent=2), encoding="utf-8")

        # 페르소나 저장
        settings.authors_dir.mkdir(parents=True, exist_ok=True)
        (settings.authors_dir / f"{author_id}.yaml").write_text(
            yaml.safe_dump(persona, allow_unicode=True, sort_keys=False),
            encoding="utf-8",
        )
        print(f"[finalize] 사전 자산 저장 완료 → {work_dir}/")

    # ── outline 변환 (ch_n.yaml) ───────────────────────────────────────────
    if not args.skip_outlines:
        outlines_dir = work_dir / "chapter_outlines"
        outlines_dir.mkdir(parents=True, exist_ok=True)

        ch_to = args.ch_to or total
        targets = [c for c in chapters if args.ch_from <= int(c.get("chapter_n", 0)) <= ch_to]
        print(f"[finalize] outline 변환: ch{args.ch_from:03d}~ch{ch_to:03d} ({len(targets)}화)")

        for i, ch in enumerate(targets, start=1):
            n = int(ch["chapter_n"])
            try:
                t0 = time.time()
                expanded = writer.expand_chapter_to_beats(concept, ending, ch, work_id=args.work_id)
                # yaml 저장 (기존 ch_n.yaml 포맷)
                yaml_data = {
                    "chapter_n": expanded["chapter_n"],
                    "overall": expanded["overall"],
                    "beats": expanded["beats"],
                }
                (outlines_dir / f"ch{n:03d}.yaml").write_text(
                    yaml.safe_dump(yaml_data, allow_unicode=True, sort_keys=False, default_flow_style=False),
                    encoding="utf-8",
                )
                print(f"  ch{n:03d} ({i}/{len(targets)}, {time.time()-t0:.1f}s)")
            except LLMProviderError as e:
                print(f"  ch{n:03d} 실패: {e}", file=sys.stderr)
                # 실패해도 계속 — 나중에 다시 돌릴 수 있게
                continue

    print(f"[finalize] 완료 → {work_dir}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
