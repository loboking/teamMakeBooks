#!/usr/bin/env python3
"""이세계 슬로우라이프 무역 소설 초기화 — 마일스톤 6화 + ch001/002 아웃라인 + 본문 생성.

사용:
    .venv/bin/python scripts/quick_init.py
"""
from __future__ import annotations

import json
import sys
import time
from pathlib import Path

import yaml

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "backend"))

from app.config import load_settings  # noqa: E402
from app.providers import get_provider  # noqa: E402
from app.teams.meta_writer.agent import MetaWriterAgent  # noqa: E402

# ── 기본 입력 ──────────────────────────────────────────────────────────────────

WORK_ID = "isekai_slowlife_trade_01"
LOGLINE = (
    "현대 고등학교와 이계가 연결되어, 18세 고3 차하린이 이계에서 슬로우 라이프를 보내며 "
    "이계와 현실의 물건을 양방향으로 거래하고 이계 먼치킨으로 각성하는 이야기"
)
CONCEPT_INPUT: dict = {
    "logline": LOGLINE,
    "genre": "이세계물",
    "mood": "슬로우라이프",
    "total_chapters": 225,
    "protagonist": "차하린",
    "keywords": ["이세계", "슬로우라이프", "양방향무역", "먼치킨", "각성"],
    "forbidden": ["성적 묘사", "실명 거론"],
    "reference_tone": "",
    "work_id": WORK_ID,
}

MILESTONES = [1, 50, 100, 150, 200, 225]


def _act_idx_for(chapter_n: int, acts: list[dict]) -> int:
    for i, act in enumerate(acts):
        rng = act.get("range", [1, 1])
        if int(rng[0]) <= chapter_n <= int(rng[1]):
            return i
    return 0


def _save_yaml(path: Path, data: object) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(yaml.dump(data, allow_unicode=True, sort_keys=False), encoding="utf-8")


def _save_md(path: Path, content: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(content, encoding="utf-8")


def _save_json(path: Path, data: object) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")


def main() -> int:
    settings = load_settings(ROOT)
    work_dir: Path = settings.novels_dir / WORK_ID
    init_dir: Path = work_dir / "_init"
    outline_dir: Path = work_dir / "chapter_outlines"

    print(f"[quick_init] work_id  = {WORK_ID}")
    print(f"[quick_init] work_dir = {work_dir}")
    work_dir.mkdir(parents=True, exist_ok=True)

    model_key = settings.model_key("meta_writer", "concept")
    provider = get_provider(model_key, settings)
    agent = MetaWriterAgent(provider, temperature=0.5, num_predict=2000, logs_dir=settings.logs_dir)

    # ── 1. 컨셉 정규화 ───────────────────────────────────────────────────────
    print("\n[1/8] 컨셉 정규화...")
    t0 = time.time()
    concept = agent.normalize_concept(CONCEPT_INPUT, WORK_ID)
    # total 225 강제 (LLM 덮어쓰기 방지)
    concept["total_chapters"] = 225
    print(f"  logline  : {concept['logline'][:60]}")
    print(f"  genre    : {concept['genre']} / mood: {concept['mood']}")
    print(f"  총화수   : {concept['total_chapters']}")
    print(f"  ({time.time()-t0:.1f}s)")

    # ── 2. 엔딩 + 3막 ────────────────────────────────────────────────────────
    print("\n[2/8] 엔딩 + 3막 생성...")
    t0 = time.time()
    ending = agent.generate_ending(concept, WORK_ID)
    for act in ending["acts"]:
        print(f"  {act['name']} {act['range']}: {act['summary'][:50]}...")
    print(f"  ({time.time()-t0:.1f}s)")

    # ── 3. 마일스톤 6화 줄거리 ────────────────────────────────────────────────
    print("\n[3/8] 마일스톤 6화 줄거리 생성...")
    milestones: list[dict] = []
    prev_chapters: list[dict] = []
    for ch_n in MILESTONES:
        act_idx = _act_idx_for(ch_n, ending["acts"])
        t0 = time.time()
        prompt_chapter = {"chapter_n": ch_n, "act": act_idx + 1}
        # build_plot_chapter_prompt 직접 사용
        from app.teams.meta_writer.prompts import (
            PLOT_CHAPTER_SCHEMA,
            build_plot_chapter_prompt,
        )
        from app.teams.meta_writer.agent import _parse_json_object
        from app.providers import LLMProviderError

        overall = ""
        for retry in range(3):
            try:
                prompt = build_plot_chapter_prompt(
                    concept, ending,
                    act_idx=act_idx,
                    chapter_n=ch_n,
                    prev_chapters=prev_chapters[-2:] if prev_chapters else None,
                    work_id=WORK_ID,
                )
                resp = provider.complete(
                    prompt,
                    max_tokens=800,
                    temperature=0.5,
                    format_schema=PLOT_CHAPTER_SCHEMA,
                )
                data = _parse_json_object(resp.text)
                overall = str(data.get("overall", "")).strip()
                if len(overall) >= 50:
                    break
            except LLMProviderError as e:
                print(f"  ch{ch_n:03d} 재시도 {retry+1}/3: {e}")
        chapter_dict = {"chapter_n": ch_n, "act": act_idx + 1, "overall": overall}
        milestones.append(chapter_dict)
        prev_chapters.append(chapter_dict)
        print(f"  ch{ch_n:03d}: {overall[:60]}... ({time.time()-t0:.1f}s)")

    # ── 4. 사전 자산 생성 ─────────────────────────────────────────────────────
    print("\n[4/8] world_bible 생성...")
    t0 = time.time()
    world_bible = agent.generate_world_bible(concept, ending, milestones, work_id=WORK_ID)
    print(f"  {len(world_bible)}자 ({time.time()-t0:.1f}s)")

    print("\n[5/8] characters 생성...")
    t0 = time.time()
    characters_list = agent.generate_characters(concept, ending, milestones, work_id=WORK_ID)
    print(f"  {len(characters_list)}명 ({time.time()-t0:.1f}s)")

    print("\n[6/8] naming_table 생성...")
    t0 = time.time()
    naming_pairs = agent.generate_naming_table(characters_list, work_id=WORK_ID)
    print(f"  {len(naming_pairs)}쌍 ({time.time()-t0:.1f}s)")

    print("\n[7/8] persona 생성...")
    t0 = time.time()
    author_id = f"{WORK_ID}_writer_01"
    persona = agent.generate_persona(concept, work_id=WORK_ID, author_id=author_id)
    print(f"  {persona['name']} ({time.time()-t0:.1f}s)")

    # ── 5. 파일 저장 ──────────────────────────────────────────────────────────
    print("\n[8/8] 파일 저장...")

    # world_bible.md
    _save_md(work_dir / "world_bible.md", world_bible)

    # characters.md
    chars_md_lines = [f"# {concept.get('logline','')[:30]} — 등장인물\n"]
    for c in characters_list:
        chars_md_lines.append(f"## {c['name']} ({c.get('role','')}/{c.get('job','')})")
        for k in ("rank", "personality", "appearance", "background", "arc"):
            if c.get(k):
                chars_md_lines.append(f"- {k}: {c[k]}")
        chars_md_lines.append("")
    _save_md(work_dir / "characters.md", "\n".join(chars_md_lines))

    # naming_table.md
    naming_lines = ["# 호칭표\n"]
    for p in naming_pairs:
        naming_lines.append(f"- {p['speaker']} → {p['listener']}: \"{p['address']}\" ({p.get('context','')})")
    _save_md(work_dir / "naming_table.md", "\n".join(naming_lines))

    # theme.md (플롯에서 키워드 기반 간략 생성)
    theme_lines = [
        f"# {concept.get('logline','')[:30]} — 테마/약속\n",
        f"## 핵심 테마",
        f"키워드: {', '.join(concept.get('keywords', []))}",
        f"분위기: {concept.get('mood','')}",
        "",
        "## 금지 요소",
    ] + [f"- {f}" for f in concept.get("forbidden", [])]
    _save_md(work_dir / "theme.md", "\n".join(theme_lines))

    # plot_outline.md — 마일스톤 화 기반
    plot_lines = [f"# {WORK_ID} — 플롯 개요 (마일스톤)\n"]
    for m in milestones:
        plot_lines.append(f"## {m['chapter_n']}화 (막{m['act']})")
        plot_lines.append(m['overall'])
        plot_lines.append("")
    _save_md(work_dir / "plot_outline.md", "\n".join(plot_lines))

    # memory 디렉토리
    for fname in ("character_state.md", "world_state.md", "event_log.md", "unresolved_threads.md", "continuity_log.md"):
        p = work_dir / "memory" / fname
        if not p.exists():
            _save_md(p, "")

    # chapters 디렉토리
    (work_dir / "chapters").mkdir(exist_ok=True)

    # authors/{author_id}.yaml
    author_path = settings.authors_dir / f"{author_id}.yaml"
    _save_yaml(author_path, persona)

    # main_characters 자동 구성 (주인공 차하린 기준)
    protagonist_name = concept.get("protagonist", "차하린")
    short_name = protagonist_name[-2:] if len(protagonist_name) >= 3 else protagonist_name
    main_characters = [
        {
            "name": protagonist_name,
            "short": short_name,
            "limit_full": 5,
            "limit_short": 20,
        }
    ]

    # meta.json
    meta = {
        "work_id": WORK_ID,
        "title": concept.get("logline", WORK_ID)[:30],
        "genre": concept.get("genre", "이세계물"),
        "mood": concept.get("mood", "슬로우라이프"),
        "author_id": author_id,
        "is_ai_persona": True,
        "total_chapters": 225,
        "published_chapters": 0,
        "protagonist": protagonist_name,
        "keywords": concept.get("keywords", []),
        "main_characters": main_characters,
        "copyright": "© 2026 teamMakeBooks",
    }
    _save_json(work_dir / "meta.json", meta)

    # _init/ 저장
    init_dir.mkdir(parents=True, exist_ok=True)
    _save_yaml(init_dir / "concept.yaml", concept)
    _save_yaml(init_dir / "ending.yaml", ending)
    _save_yaml(init_dir / "milestone.yaml", {"chapters": milestones})

    # ── 6. ch001 / ch002 비트 아웃라인 ──────────────────────────────────────
    print("\nch001 비트 아웃라인 생성...")
    t0 = time.time()
    ch001_chapter = milestones[0]  # chapter_n=1 마일스톤
    ch001_outline = agent.expand_chapter_to_beats(concept, ending, ch001_chapter, work_id=WORK_ID)
    _save_yaml(outline_dir / "ch001.yaml", ch001_outline)
    print(f"  ch001 beats={len(ch001_outline['beats'])} ({time.time()-t0:.1f}s)")

    print("ch002 비트 아웃라인 생성...")
    t0 = time.time()
    # ch002: ch001(마일스톤) → ch050(마일스톤) 사이 보간
    # ch001 overall을 prev로, ch050 방향으로 이어지는 ch002 overall 생성 후 확장
    from app.teams.meta_writer.prompts import build_plot_chapter_prompt, PLOT_CHAPTER_SCHEMA
    ch002_overall = ""
    for retry in range(3):
        try:
            prompt = build_plot_chapter_prompt(
                concept, ending,
                act_idx=_act_idx_for(2, ending["acts"]),
                chapter_n=2,
                prev_chapters=[ch001_chapter],
                work_id=WORK_ID,
            )
            resp = provider.complete(prompt, max_tokens=800, temperature=0.5, format_schema=PLOT_CHAPTER_SCHEMA)
            data = _parse_json_object(resp.text)
            ch002_overall = str(data.get("overall", "")).strip()
            if len(ch002_overall) >= 50:
                break
        except Exception as e:
            print(f"  ch002 overall 재시도 {retry+1}/3: {e}")

    ch002_chapter = {"chapter_n": 2, "act": 1, "overall": ch002_overall}
    ch002_outline = agent.expand_chapter_to_beats(concept, ending, ch002_chapter, work_id=WORK_ID)
    _save_yaml(outline_dir / "ch002.yaml", ch002_outline)
    print(f"  ch002 beats={len(ch002_outline['beats'])} ({time.time()-t0:.1f}s)")

    print(f"\n[SUCCESS] {WORK_ID} 초기화 완료.")
    print(f"  world_bible    : {work_dir/'world_bible.md'}")
    print(f"  characters     : {work_dir/'characters.md'}")
    print(f"  meta.json      : {work_dir/'meta.json'}")
    print(f"  plot_outline   : {work_dir/'plot_outline.md'}")
    print(f"  author yaml    : {author_path}")
    print(f"  ch001 outline  : {outline_dir/'ch001.yaml'}")
    print(f"  ch002 outline  : {outline_dir/'ch002.yaml'}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
