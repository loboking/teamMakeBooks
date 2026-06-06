"""발행팀 — 메타데이터 생성 + 본문에 AI 배지 + 파일 저장."""
from __future__ import annotations

import json
import re
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path

from ...providers import LLMProvider
from ...utils.logger import log_call
from .prompts import PUBLISH_SCHEMA, build_publisher_prompt

AI_BADGE = "> 🤖 AI 생성 콘텐츠"


@dataclass
class PublishResult:
    title: str
    tags: list[str]
    one_line_summary: str
    chapter_path: Path
    meta_path: Path
    published_at: str


class PublisherAgent:
    def __init__(
        self,
        provider: LLMProvider,
        *,
        temperature: float = 0.4,
        num_predict: int = 600,
        logs_dir: Path | None = None,
    ):
        self.provider = provider
        self.temperature = temperature
        self.num_predict = num_predict
        self.logs_dir = logs_dir

    def publish(self, draft: str, ctx, work_id: str, novels_dir: Path) -> PublishResult:
        prompt = build_publisher_prompt(ctx, draft)
        resp = self.provider.complete(
            prompt,
            max_tokens=self.num_predict,
            temperature=self.temperature,
            format_schema=PUBLISH_SCHEMA,
        )
        if self.logs_dir:
            log_call(
                team="publisher",
                role="metadata",
                work_id=work_id,
                chapter_n=ctx.current_chapter_n,
                prompt=prompt,
                response=resp,
                logs_dir=self.logs_dir,
            )

        # 파싱 (실패 시 fallback)
        try:
            meta = json.loads(resp.text.strip())
            title = str(meta["title"])
            tags = list(meta["tags"])
            one_line_summary = str(meta["one_line_summary"])
        except Exception:
            title = f"제목 미생성 — ch{ctx.current_chapter_n:03d}"
            tags = ["미분류"]
            one_line_summary = "(요약 생성 실패)"

        # 본문에 AI 배지 + 제목 삽입
        # LLM 초안에 임의 제목(# N화. xxx)이 포함될 수 있으므로 먼저 제거
        _title_re = re.compile(r'^#\s*\d+화\.\s*.+$', re.MULTILINE)
        lines = draft.strip().split("\n")
        cleaned_lines = [l for l in lines if not _title_re.match(l)]
        cleaned = "\n".join(cleaned_lines).strip()
        body = (
            f"{AI_BADGE}\n\n"
            f"# {ctx.current_chapter_n}화. {title}\n\n"
            f"{cleaned}\n"
        )

        chapters_dir = novels_dir / work_id / "chapters"
        chapters_dir.mkdir(parents=True, exist_ok=True)
        chapter_path = chapters_dir / f"ch{ctx.current_chapter_n:03d}.md"
        chapter_path.write_text(body, encoding="utf-8")

        published_at = datetime.now(timezone.utc).isoformat()
        meta_path = chapters_dir / f"ch{ctx.current_chapter_n:03d}_meta.json"
        meta_path.write_text(
            json.dumps(
                {
                    "chapter_n": ctx.current_chapter_n,
                    "title": title,
                    "tags": tags,
                    "one_line_summary": one_line_summary,
                    "published_at": published_at,
                    "ai_badge": True,
                },
                ensure_ascii=False,
                indent=2,
            ),
            encoding="utf-8",
        )

        # 작품 meta.json의 published_chapters 카운터 증가
        work_meta_path = novels_dir / work_id / "meta.json"
        work_meta = json.loads(work_meta_path.read_text(encoding="utf-8"))
        work_meta["published_chapters"] = max(
            int(work_meta.get("published_chapters", 0)),
            ctx.current_chapter_n,
        )
        work_meta_path.write_text(
            json.dumps(work_meta, ensure_ascii=False, indent=2), encoding="utf-8"
        )

        return PublishResult(
            title=title,
            tags=tags,
            one_line_summary=one_line_summary,
            chapter_path=chapter_path,
            meta_path=meta_path,
            published_at=published_at,
        )
