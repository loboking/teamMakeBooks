"""작가 에이전트 — 비트 분할 생성 + 수정 + 요약."""
from __future__ import annotations

from pathlib import Path

from ...providers import LLMProvider
from ...utils.logger import log_call
from .prompts import (
    build_beat_prompt,
    build_polish_prompt,
    build_rep_polish_prompt,
    build_revise_prompt,
    build_summary_prompt,
)


class WriterAgent:
    def __init__(
        self,
        provider: LLMProvider,
        *,
        beat_temperature: float = 0.85,
        beat_num_predict: int = 4000,
        logs_dir: Path | None = None,
    ):
        self.provider = provider
        self.beat_temperature = beat_temperature
        self.beat_num_predict = beat_num_predict
        self.logs_dir = logs_dir

    def draft(self, ctx, persona, work_id: str) -> str:
        """1화 본문을 비트 N개로 나눠 순차 생성. 비트 간 tail 컨텍스트 주입."""
        beats = ctx.chapter_outline.beats
        if not beats:
            raise ValueError("chapter_outline.beats가 비어 있음")

        full_text_parts: list[str] = []
        prev_tail = ""

        for i, beat in enumerate(beats):
            prompt = build_beat_prompt(persona, ctx, beat, prev_tail, i, len(beats))
            resp = self.provider.complete(
                prompt,
                max_tokens=self.beat_num_predict,
                temperature=self.beat_temperature,
            )
            text = resp.text.strip()
            full_text_parts.append(text)
            prev_tail = text[-400:]

            if self.logs_dir:
                log_call(
                    team="writer",
                    role=f"draft_beat_{beat.name}",
                    work_id=work_id,
                    chapter_n=ctx.current_chapter_n,
                    prompt=prompt,
                    response=resp,
                    logs_dir=self.logs_dir,
                )

        return "\n\n".join(full_text_parts).strip()

    def revise(self, draft: str, feedback: str, ctx, persona, work_id: str) -> str:
        prompt = build_revise_prompt(persona, ctx, draft, feedback)
        resp = self.provider.complete(
            prompt,
            max_tokens=self.beat_num_predict * len(ctx.chapter_outline.beats),
            temperature=self.beat_temperature,
        )
        if self.logs_dir:
            log_call(
                team="writer",
                role="revise",
                work_id=work_id,
                chapter_n=ctx.current_chapter_n,
                prompt=prompt,
                response=resp,
                logs_dir=self.logs_dir,
            )
        return resp.text.strip()

    def polish_flow(self, draft: str, ctx, persona, work_id: str) -> str:
        """완성된 본문의 호흡만 정제. 단문 → 어미 연결. 의미 보존."""
        prompt = build_polish_prompt(persona, draft, ctx)
        resp = self.provider.complete(
            prompt,
            max_tokens=max(self.beat_num_predict * 4, 12000),
            temperature=0.3,
        )
        if self.logs_dir:
            log_call(
                team="writer",
                role="polish_flow",
                work_id=work_id,
                chapter_n=ctx.current_chapter_n,
                prompt=prompt,
                response=resp,
                logs_dir=self.logs_dir,
            )
        return resp.text.strip()

    def polish_repetition(self, draft: str, feedback: str, work_id: str, ctx=None) -> str:
        """반복 패턴만 집중 교체. 본문 전체 재작성 X."""
        prompt = build_rep_polish_prompt(draft, feedback, ctx)
        resp = self.provider.complete(
            prompt,
            max_tokens=max(self.beat_num_predict * 3, 8000),
            temperature=0.3,
        )
        if self.logs_dir:
            log_call(
                team="writer",
                role="polish_repetition",
                work_id=work_id,
                chapter_n=0,
                prompt=prompt,
                response=resp,
                logs_dir=self.logs_dir,
            )
        return resp.text.strip()

    def write_summary(self, ctx, persona, chapter_text: str, work_id: str) -> str:
        prompt = build_summary_prompt(persona, ctx, chapter_text)
        resp = self.provider.complete(prompt, max_tokens=2000, temperature=0.3)
        if self.logs_dir:
            log_call(
                team="writer",
                role="summary",
                work_id=work_id,
                chapter_n=ctx.current_chapter_n,
                prompt=prompt,
                response=resp,
                logs_dir=self.logs_dir,
            )
        return resp.text.strip()
