#!/usr/bin/env python3
"""기존 작품 자산을 wiki/ vault로 분해.

입력 (작품별):
  novels/{wid}/meta.json
  novels/{wid}/characters.md  (## {이름} 섹션 분해)
  novels/{wid}/naming_table.md
  novels/{wid}/world_bible.md
  novels/{wid}/plot_outline.md
  novels/{wid}/_init/ending.yaml (있으면)
  novels/{wid}/chapters/ch*_summary.md (있으면)

출력:
  wiki/{wid}/_작품인덱스.md
  wiki/{wid}/characters/{이름}.md  (frontmatter + 누적 상태)
  wiki/{wid}/events/ch{n:03d}.md   (회차 요약)
  wiki/{wid}/timeline.md
  wiki/{wid}/locations/ (스켈레톤)
  wiki/{wid}/threads/  (스켈레톤)

Usage:
  python scripts/init_wiki.py                     # 모든 작품
  python scripts/init_wiki.py --work-id <wid>     # 특정 작품
"""
from __future__ import annotations

import argparse
import json
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent


def parse_characters_md(text: str) -> list[dict]:
    """## {이름} (역할) 헤딩 단위로 분해. 각 섹션의 fields를 dict로."""
    sections = re.split(r"^## ", text, flags=re.MULTILINE)
    result: list[dict] = []
    for sec in sections[1:]:  # 첫 번째는 헤더 텍스트
        lines = sec.strip().split("\n")
        if not lines:
            continue
        # 첫 줄: "차하린 (주인공)" 또는 "강이준"
        heading = lines[0].strip()
        m = re.match(r"(?P<name>[^\(]+?)\s*(\((?P<role>[^)]+)\))?\s*$", heading)
        name = m.group("name").strip() if m else heading
        role = (m.group("role") or "").strip() if m else ""

        body = "\n".join(lines[1:])
        # 각 필드 추출 — "- **필드**: 값" 패턴
        fields: dict = {}
        for fm in re.finditer(r"^[\-\*]\s*\*\*(?P<k>[^:*]+)\*\*\s*[:：]\s*(?P<v>.+?)$", body, flags=re.MULTILINE):
            key = fm.group("k").strip().lower()
            val = fm.group("v").strip()
            fields[key] = val
        result.append({"name": name, "role": role, "raw": body.strip(), "fields": fields})
    return result


def parse_naming_table(text: str) -> dict[str, list[dict]]:
    """naming_table.md 내 호칭 매핑 추출 — speaker → [{listener, address, context}]."""
    pairs: dict[str, list[dict]] = {}
    for m in re.finditer(
        r"\[(?P<speaker>[^\]→]+?)\s*→\s*(?P<listener>[^\]]+?)\]\s*[:：]\s*[\"\'“](?P<addr>[^\"\'”]+)[\"\'”]\s*(?:\((?P<ctx>[^)]+)\))?",
        text,
    ):
        sp = m.group("speaker").strip()
        pairs.setdefault(sp, []).append({
            "listener": m.group("listener").strip(),
            "address": m.group("addr").strip(),
            "context": (m.group("ctx") or "").strip(),
        })
    return pairs


def summary_first_line(p: Path) -> str:
    if not p.exists():
        return ""
    txt = p.read_text(encoding="utf-8").strip()
    for line in txt.split("\n"):
        s = line.strip()
        if s and not s.startswith("#") and not s.startswith(">"):
            return s
    return txt[:100]


def init_work_wiki(work_id: str, wiki_root: Path, novels_root: Path) -> None:
    work_dir = novels_root / work_id
    if not (work_dir / "meta.json").exists():
        print(f"[skip] {work_id} — meta.json 없음")
        return

    meta = json.loads((work_dir / "meta.json").read_text(encoding="utf-8"))
    main_chars = {c["name"]: c for c in meta.get("main_characters", [])}

    target = wiki_root / work_id
    (target / "characters").mkdir(parents=True, exist_ok=True)
    (target / "events").mkdir(parents=True, exist_ok=True)
    (target / "threads").mkdir(parents=True, exist_ok=True)
    (target / "locations").mkdir(parents=True, exist_ok=True)

    # 1. characters/{이름}.md
    chars_md = (work_dir / "characters.md")
    naming_md = (work_dir / "naming_table.md")
    characters_parsed = parse_characters_md(chars_md.read_text(encoding="utf-8")) if chars_md.exists() else []
    naming_pairs = parse_naming_table(naming_md.read_text(encoding="utf-8")) if naming_md.exists() else {}

    character_names: list[str] = []
    for ch in characters_parsed:
        name = ch["name"]
        if not name:
            continue
        character_names.append(name)
        # main_characters에서 한도 가져오기
        main = main_chars.get(name, {})
        short_name = main.get("short", "")
        # frontmatter
        fm_lines = [
            "---",
            f"type: character",
            f"work_id: {work_id}",
            f"role: {ch['role']}",
            "status: active",
            f"short_name: {short_name}",
        ]
        if main.get("limit_full") is not None:
            fm_lines.append(f"limit_full: {main['limit_full']}")
        if main.get("limit_short") is not None:
            fm_lines.append(f"limit_short: {main['limit_short']}")
        # 관계 — naming_table에서 화자→청자 추출
        related = sorted({p["listener"] for p in naming_pairs.get(name, [])})
        if related:
            fm_lines.append("related: [" + ", ".join(f'"[[{r}]]"' for r in related) + "]")
        fm_lines.append("---")
        # 본문
        body_lines = [
            "",
            f"# {name}",
            "",
            "## 정의 (불변)",
            ch["raw"] or "(정의 없음)",
            "",
        ]
        # 호칭표 발췌
        if name in naming_pairs:
            body_lines.append("## 호칭")
            for p in naming_pairs[name]:
                ctx = f" ({p['context']})" if p["context"] else ""
                body_lines.append(f'- → {p["listener"]}: "{p["address"]}"{ctx}')
            body_lines.append("")
        body_lines += [
            "## 누적 상태",
            "(회차 발행 시 자동 추가)",
            "",
        ]
        out = "\n".join(fm_lines + body_lines)
        (target / "characters" / f"{name}.md").write_text(out, encoding="utf-8")

    # 2. events/ + timeline.md — chapters/ch*_summary.md 파싱
    timeline_lines = ["# 타임라인", ""]
    chapters_dir = work_dir / "chapters"
    if chapters_dir.exists():
        summary_files = sorted(chapters_dir.glob("ch*_summary.md"))
        for sf in summary_files:
            m = re.match(r"ch(\d+)_summary\.md", sf.name)
            if not m:
                continue
            n = int(m.group(1))
            line = summary_first_line(sf)
            # events/ch{n:03d}.md
            event_md = (
                f"---\n"
                f"type: event\n"
                f"work_id: {work_id}\n"
                f"chapter_n: {n}\n"
                f"---\n\n"
                f"# ch{n:03d}\n\n"
                f"## 사건 요약\n"
                f"{line}\n\n"
                f"## 전체 요약 본문\n"
                f"{sf.read_text(encoding='utf-8').strip()}\n"
            )
            (target / "events" / f"ch{n:03d}.md").write_text(event_md, encoding="utf-8")
            timeline_lines.append(f"- ch{n:03d}: {line[:120]}")
    (target / "timeline.md").write_text("\n".join(timeline_lines) + "\n", encoding="utf-8")

    # 3. 작품 인덱스
    total_planned = meta.get("total_planned") or meta.get("total_chapters") or 0
    published = meta.get("published_chapters", 0)
    idx_lines = [
        "---",
        "type: work_index",
        f"work_id: {work_id}",
        "---",
        "",
        f"# {meta.get('title', work_id)}",
        "",
        f"- **work_id**: `{work_id}`",
        f"- **장르**: {meta.get('genre', '')}",
        f"- **발행**: {published}/{total_planned}화",
        f"- **작가 페르소나**: `{meta.get('author_id', '')}`",
        "",
        "## 주조연",
    ]
    for n in character_names:
        idx_lines.append(f"- [[{work_id}/characters/{n}|{n}]]")
    idx_lines += ["", "## 바로가기", f"- [[{work_id}/timeline|타임라인]]"]
    (target / "_작품인덱스.md").write_text("\n".join(idx_lines) + "\n", encoding="utf-8")

    print(f"[init_wiki] {work_id} — 인물 {len(character_names)}명, 회차 {len(list((target / 'events').glob('*.md')))}개")


def main() -> int:
    p = argparse.ArgumentParser()
    p.add_argument("--work-id", default=None, help="특정 작품만 (기본: 전체)")
    args = p.parse_args()

    wiki_root = ROOT / "wiki"
    novels_root = ROOT / "novels"
    wiki_root.mkdir(exist_ok=True)

    if args.work_id:
        init_work_wiki(args.work_id, wiki_root, novels_root)
    else:
        for d in sorted(novels_root.iterdir()):
            if d.is_dir() and (d / "meta.json").exists():
                init_work_wiki(d.name, wiki_root, novels_root)

    print(f"\n[init_wiki] 완료 → {wiki_root}/")
    return 0


if __name__ == "__main__":
    sys.exit(main())
