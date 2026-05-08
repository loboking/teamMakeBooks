"""파일 기반 소설 컨텍스트 로더."""
from __future__ import annotations

import json
from dataclasses import dataclass, field
from pathlib import Path

import yaml


@dataclass
class BeatOutline:
    name: str
    instruction: str


@dataclass
class ChapterOutline:
    chapter_n: int
    overall: str
    beats: list[BeatOutline] = field(default_factory=list)


@dataclass
class NovelContext:
    work_id: str
    world_bible: str
    characters: str
    plot_outline: str
    theme: str
    naming_table: str
    recent_summaries: list[str]
    current_chapter_n: int
    chapter_outline: ChapterOutline
    unresolved_threads: str = ""
    continuity_log: str = ""
    event_log: str = ""
    character_state: str = ""
    world_state: str = ""
    # 작품 메타에서 로드된 주조연 호명·임계 (반복 검수용)
    main_characters: list[dict] = field(default_factory=list)
    name_limits: dict = field(default_factory=dict)


def load_work_meta(work_id: str, novels_dir: Path) -> dict:
    return json.loads((novels_dir / work_id / "meta.json").read_text(encoding="utf-8"))


def load_chapter_outline(work_id: str, chapter_n: int, novels_dir: Path) -> ChapterOutline:
    path = novels_dir / work_id / "chapter_outlines" / f"ch{chapter_n:03d}.yaml"
    data = yaml.safe_load(path.read_text(encoding="utf-8"))
    return ChapterOutline(
        chapter_n=int(data["chapter_n"]),
        overall=str(data["overall"]),
        beats=[BeatOutline(name=str(b["name"]), instruction=str(b["instruction"])) for b in data["beats"]],
    )


def load_novel_context(
    work_id: str,
    chapter_n: int,
    *,
    novels_dir: Path,
    recent_n: int = 3,
) -> NovelContext:
    base = novels_dir / work_id

    world_bible = (base / "world_bible.md").read_text(encoding="utf-8")
    characters = (base / "characters.md").read_text(encoding="utf-8")
    plot_outline = (base / "plot_outline.md").read_text(encoding="utf-8")
    chapter_outline = load_chapter_outline(work_id, chapter_n, novels_dir)

    summaries: list[str] = []
    for i in range(max(1, chapter_n - recent_n), chapter_n):
        sp = base / "chapters" / f"ch{i:03d}_summary.md"
        if sp.exists():
            summaries.append(sp.read_text(encoding="utf-8"))

    def opt(p: Path) -> str:
        return p.read_text(encoding="utf-8") if p.exists() else ""

    # 메타에서 main_characters 로드 (회차 검수자가 동적으로 사용)
    meta = load_work_meta(work_id, novels_dir)
    raw_chars = meta.get("main_characters") or []
    if not raw_chars:
        proto = str(meta.get("protagonist", "") or "").strip()
        raw_chars = [{"name": proto, "short": "", "limit_full": 7, "limit_short": 25}] if proto else []
    main_characters: list[dict] = []
    name_limits: dict = {}
    for c in raw_chars:
        full = str(c.get("name", "")).strip()
        if not full:
            continue
        main_characters.append({"name": full, "short": str(c.get("short", "")).strip()})
        name_limits[full] = {
            "full": int(c.get("limit_full", 7)),
            "short": int(c.get("limit_short", 25)),
        }

    return NovelContext(
        work_id=work_id,
        world_bible=world_bible,
        characters=characters,
        plot_outline=plot_outline,
        theme=opt(base / "theme.md"),
        naming_table=opt(base / "naming_table.md"),
        recent_summaries=summaries,
        current_chapter_n=chapter_n,
        chapter_outline=chapter_outline,
        unresolved_threads=opt(base / "memory" / "unresolved_threads.md"),
        continuity_log=opt(base / "memory" / "continuity_log.md"),
        event_log=opt(base / "memory" / "event_log.md"),
        character_state=opt(base / "memory" / "character_state.md"),
        world_state=opt(base / "memory" / "world_state.md"),
        main_characters=main_characters,
        name_limits=name_limits,
    )
