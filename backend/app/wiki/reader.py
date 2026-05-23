"""위키 vault 읽기 — 회차 작성 전 LLM 컨텍스트에 발췌 주입."""
from __future__ import annotations

import re
from dataclasses import dataclass
from pathlib import Path


def _parse_frontmatter(text: str) -> tuple[dict, str]:
    """간이 yaml frontmatter 파서 (key: value만 지원)."""
    if not text.startswith("---\n"):
        return {}, text
    end = text.find("\n---\n", 4)
    if end < 0:
        return {}, text
    fm_raw = text[4:end]
    body = text[end + 5:]
    fm: dict = {}
    for line in fm_raw.split("\n"):
        m = re.match(r"^([a-zA-Z_][a-zA-Z0-9_]*)\s*:\s*(.+)$", line)
        if m:
            k, v = m.group(1), m.group(2).strip()
            fm[k] = v
    return fm, body


@dataclass
class WikiCharacter:
    name: str
    frontmatter: dict
    definition: str       # ## 정의 (불변) 섹션
    cumulative: str       # ## 누적 상태 섹션
    path: Path


class WikiReader:
    def __init__(self, wiki_root: Path, work_id: str):
        self.wiki_root = wiki_root
        self.work_id = work_id
        self.work_dir = wiki_root / work_id

    def has_wiki(self) -> bool:
        return self.work_dir.exists()

    def get_character(self, name: str) -> WikiCharacter | None:
        path = self.work_dir / "characters" / f"{name}.md"
        if not path.exists():
            return None
        text = path.read_text(encoding="utf-8")
        fm, body = _parse_frontmatter(text)
        # 섹션 분해
        defs = ""
        cum = ""
        m = re.search(r"^##\s*정의[^\n]*\n(.+?)(?=^##|\Z)", body, flags=re.MULTILINE | re.DOTALL)
        if m:
            defs = m.group(1).strip()
        m = re.search(r"^##\s*누적 상태[^\n]*\n(.+?)(?=^##|\Z)", body, flags=re.MULTILINE | re.DOTALL)
        if m:
            cum = m.group(1).strip()
        return WikiCharacter(name=name, frontmatter=fm, definition=defs, cumulative=cum, path=path)

    def list_characters(self) -> list[str]:
        d = self.work_dir / "characters"
        if not d.exists():
            return []
        return [p.stem for p in d.glob("*.md")]

    def list_open_threads(self) -> list[dict]:
        """열린 떡밥 (status: open)."""
        d = self.work_dir / "threads"
        if not d.exists():
            return []
        out = []
        for p in d.glob("*.md"):
            fm, body = _parse_frontmatter(p.read_text(encoding="utf-8"))
            if fm.get("status", "open").lower() == "open":
                out.append({
                    "name": p.stem,
                    "introduced_ch": fm.get("introduced_ch", ""),
                    "body": body[:400],
                })
        return out

    def recent_timeline(self, n: int = 5) -> list[str]:
        """timeline.md 마지막 n줄."""
        tl = self.work_dir / "timeline.md"
        if not tl.exists():
            return []
        lines = [l for l in tl.read_text(encoding="utf-8").split("\n") if l.startswith("- ch")]
        return lines[-n:]


def fetch_wiki_context(wiki_root: Path, work_id: str, *,
                       characters: list[str] | None = None,
                       recent_timeline_n: int = 5) -> str:
    """회차 작성 전 wiki 발췌 — writer 프롬프트에 주입할 텍스트 블록."""
    r = WikiReader(wiki_root, work_id)
    if not r.has_wiki():
        return ""

    char_names = characters or r.list_characters()
    blocks: list[str] = ["[위키 발췌 — 작품 누적 상태]"]

    # 인물별 누적 상태 (정의는 이미 ctx.characters에 있으므로 누적만)
    if char_names:
        blocks.append("\n## 등장 예정 인물 누적 상태")
        for n in char_names:
            c = r.get_character(n)
            if not c:
                continue
            cum_lines = c.cumulative.split("\n")
            cum_recent = "\n".join(cum_lines[-6:]) if len(cum_lines) > 1 else c.cumulative
            blocks.append(f"### {n}\n{cum_recent}")

    # 미해결 떡밥
    open_threads = r.list_open_threads()
    if open_threads:
        blocks.append("\n## 미해결 떡밥 (open threads)")
        for t in open_threads[:5]:
            blocks.append(f"- **{t['name']}** (도입 ch{t['introduced_ch']}): {t['body'][:120]}")

    # 최근 타임라인
    recent = r.recent_timeline(recent_timeline_n)
    if recent:
        blocks.append("\n## 직전 타임라인")
        blocks.extend(recent)

    return "\n".join(blocks)
