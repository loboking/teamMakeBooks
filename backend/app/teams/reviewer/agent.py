"""검수자 에이전트 — 역할별 단일 클래스."""
from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path

from ...providers import LLMProvider
from ...utils.logger import log_call
from .prompts import REVIEW_SCHEMA, build_reviewer_prompt


@dataclass
class ReviewResult:
    role: str
    attempt: int
    passed: bool
    score: int
    reason: str
    feedback: str  # 통과 시 빈 문자열
    raw: str
    parse_error: str | None


class ReviewerAgent:
    def __init__(
        self,
        role: str,
        provider: LLMProvider,
        *,
        temperature: float = 0.2,
        num_predict: int = 600,
        logs_dir: Path | None = None,
    ):
        self.role = role
        self.provider = provider
        self.temperature = temperature
        self.num_predict = num_predict
        self.logs_dir = logs_dir

    def review(self, draft: str, ctx, attempt: int, work_id: str) -> ReviewResult:
        prompt = build_reviewer_prompt(self.role, ctx, draft)
        resp = self.provider.complete(
            prompt,
            max_tokens=self.num_predict,
            temperature=self.temperature,
            format_schema=REVIEW_SCHEMA,
        )
        text = resp.text.strip()

        if self.logs_dir:
            log_call(
                team="reviewer",
                role=f"{self.role}_attempt{attempt}",
                work_id=work_id,
                chapter_n=ctx.current_chapter_n,
                prompt=prompt,
                response=resp,
                logs_dir=self.logs_dir,
            )

        # 파싱 — 실패 시 보수적으로 반려 처리
        parse_error: str | None = None
        try:
            data = json.loads(text)
            verdict = data.get("판정", "")
            score = int(data.get("점수", 0))
            reason = str(data.get("이유", ""))
            feedback = str(data.get("수정가이드", ""))
            passed = verdict == "통과"
        except Exception as e:
            parse_error = f"파싱 실패: {e}"
            passed = False
            score = 0
            reason = "검수 출력 파싱 실패 — 보수적 반려"
            feedback = "검수자 출력 형식이 깨짐. 본문 재생성 필요."

        return ReviewResult(
            role=self.role,
            attempt=attempt,
            passed=passed,
            score=score,
            reason=reason,
            feedback=feedback,
            raw=text,
            parse_error=parse_error,
        )
