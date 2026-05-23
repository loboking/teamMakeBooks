"""위키 vault 갱신 — 회차 발행 후 자동 호출."""
from __future__ import annotations

import re
from pathlib import Path


class WikiUpdater:
    def __init__(self, wiki_root: Path, work_id: str):
        self.wiki_root = wiki_root
        self.work_id = work_id
        self.work_dir = wiki_root / work_id

    def ensure_dirs(self) -> None:
        for sub in ("characters", "events", "threads", "locations"):
            (self.work_dir / sub).mkdir(parents=True, exist_ok=True)

    def append_character_state(self, name: str, chapter_n: int, one_line: str) -> bool:
        """characters/{name}.md 의 '## 누적 상태' 섹션에 한 줄 추가."""
        path = self.work_dir / "characters" / f"{name}.md"
        if not path.exists():
            return False
        text = path.read_text(encoding="utf-8")
        marker = "## 누적 상태"
        if marker not in text:
            return False
        new_line = f"- ch{chapter_n:03d}: {one_line.strip()}"
        # 이미 같은 ch 라인 있으면 교체, 아니면 추가
        pattern = rf"^- ch{chapter_n:03d}: .+$"
        if re.search(pattern, text, flags=re.MULTILINE):
            text = re.sub(pattern, new_line, text, count=1, flags=re.MULTILINE)
        else:
            # 마커 섹션 끝에 줄 추가 (다음 ## 헤더 직전 or 파일 끝)
            sec_re = re.compile(rf"({re.escape(marker)}.*?)(?=^## |\Z)", flags=re.MULTILINE | re.DOTALL)
            m = sec_re.search(text)
            if m:
                section = m.group(1).rstrip()
                # "(회차 발행 시 자동 추가)" placeholder 제거
                section = re.sub(r"\(회차 발행 시 자동 추가\)\s*", "", section).rstrip()
                section_new = section + "\n" + new_line + "\n\n"
                text = text[:m.start(1)] + section_new + text[m.end(1):]
            else:
                text = text.rstrip() + "\n\n" + new_line + "\n"
        path.write_text(text, encoding="utf-8")
        return True

    def write_event(self, chapter_n: int, summary: str, characters: list[str], slug: str = "") -> None:
        """events/ch{n:03d}.md 생성/덮어쓰기."""
        path = self.work_dir / "events" / f"ch{chapter_n:03d}.md"
        related = "[" + ", ".join(f'"[[{c}]]"' for c in characters) + "]"
        content = (
            f"---\n"
            f"type: event\n"
            f"work_id: {self.work_id}\n"
            f"chapter_n: {chapter_n}\n"
            f"characters: {related}\n"
            f"---\n\n"
            f"# ch{chapter_n:03d}{(' — ' + slug) if slug else ''}\n\n"
            f"## 사건 요약\n{summary.strip()}\n"
        )
        path.write_text(content, encoding="utf-8")

    def append_timeline(self, chapter_n: int, one_line: str) -> None:
        """timeline.md에 줄 추가/교체."""
        path = self.work_dir / "timeline.md"
        if not path.exists():
            path.write_text("# 타임라인\n\n", encoding="utf-8")
        text = path.read_text(encoding="utf-8")
        new_line = f"- ch{chapter_n:03d}: {one_line.strip()[:200]}"
        pattern = rf"^- ch{chapter_n:03d}: .+$"
        if re.search(pattern, text, flags=re.MULTILINE):
            text = re.sub(pattern, new_line, text, count=1, flags=re.MULTILINE)
        else:
            text = text.rstrip() + "\n" + new_line + "\n"
        path.write_text(text, encoding="utf-8")


def update_wiki_after_chapter(
    wiki_root: Path, work_id: str, *,
    chapter_n: int, summary: str, characters_in_chapter: list[str],
    slug: str = "",
) -> None:
    """회차 발행 후 wiki 자동 갱신 엔트리."""
    u = WikiUpdater(wiki_root, work_id)
    u.ensure_dirs()
    u.write_event(chapter_n, summary, characters_in_chapter, slug=slug)
    # 첫 의미 있는 줄 추출 — 헤더(`#`/`**[...]**`/번호목록 prefix) 제외
    def _is_meaningful(line: str) -> bool:
        s = line.strip()
        if not s:
            return False
        if s.startswith("#") or s.startswith(">"):
            return False
        if s.startswith("**") and s.endswith("**"):  # 헤더성 굵은 라벨
            return False
        if re.match(r"^[\-\*\d]+\.?\s+\*?\*?[가-힣A-Za-z\s]+:\*?\*?", s):
            # 번호목록 라벨 — 그 다음 본문 부분만 사용
            return True
        return True
    candidate = ""
    for line in summary.split("\n"):
        if _is_meaningful(line):
            candidate = line.strip()
            break
    # 번호목록 prefix 제거
    candidate = re.sub(r"^[\d]+\.\s*\*?\*?[가-힣A-Za-z\s]+:\*?\*?\s*", "", candidate)
    one_line = candidate or summary[:120]
    u.append_timeline(chapter_n, one_line)
    for name in characters_in_chapter:
        u.append_character_state(name, chapter_n, one_line[:140])


def detect_characters_in_text(text: str, candidate_names: list[str]) -> list[str]:
    """본문에서 등장한 인물 추출 — 단순 grep."""
    return [n for n in candidate_names if n and n in text]
