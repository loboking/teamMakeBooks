"""메타 파이프라인 검수자 — EndingLockReviewer / OutlineConsistencyReviewer.

기존 ReviewResult 데이터클래스를 그대로 재사용. 출력 JSON 형식도 prompts.py의
REVIEW_SCHEMA와 동일 ({"판정","점수","이유","수정가이드"}).
"""
from __future__ import annotations

import json
from pathlib import Path

from ...providers import LLMProvider
from ...utils.logger import log_call
from .agent import ReviewResult
from .meta_prompts import (
    build_ending_lock_prompt,
    build_ending_vs_skeleton_prompt,
    build_outline_consistency_prompt,
)
from .prompts import REVIEW_SCHEMA


def _parse_review(text: str, role: str, attempt: int) -> ReviewResult:
    """검수 출력 JSON 파싱 — 실패 시 보수적으로 반려 처리 (기존 ReviewerAgent와 동일)."""
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
        reason = "검수 출력 파싱 실패"
        feedback = "검수자 출력 형식이 깨짐. 본문 재생성 필요."

    return ReviewResult(
        role=role,
        attempt=attempt,
        passed=passed,
        score=score,
        reason=reason,
        feedback=feedback,
        raw=text,
        parse_error=parse_error,
    )


class EndingLockReviewer:
    """엔딩 ↔ 컨셉 / 엔딩 ↔ 100화 끝 정합 검수자."""

    def __init__(
        self,
        provider: LLMProvider,
        *,
        temperature: float = 0.2,
        num_predict: int = 800,
        logs_dir: Path | None = None,
    ):
        self.provider = provider
        self.temperature = temperature
        self.num_predict = num_predict
        self.logs_dir = logs_dir

    def review_ending(
        self,
        concept: dict,
        ending: dict,
        *,
        attempt: int,
        work_id: str,
    ) -> ReviewResult:
        """엔딩 생성 직후 — concept 대비 1줄 엔딩·3막 골격 정합 검수."""
        prompt = build_ending_lock_prompt(concept, ending)
        resp = self.provider.complete(
            prompt,
            max_tokens=self.num_predict,
            temperature=self.temperature,
            format_schema=REVIEW_SCHEMA,
        )
        text = resp.text.strip()

        if self.logs_dir:
            log_call(
                team="meta_reviewer",
                role=f"ending_lock_attempt{attempt}",
                work_id=work_id,
                chapter_n=0,
                prompt=prompt,
                response=resp,
                logs_dir=self.logs_dir,
            )

        return _parse_review(text, role="ending_lock", attempt=attempt)

    def review_against_skeleton(
        self,
        ending: dict,
        skeleton: list[dict],
        *,
        attempt: int,
        work_id: str,
    ) -> ReviewResult:
        """100화 골격 완성 후 — 막 경계 화·마지막 화가 엔딩과 일치하는지 검수."""
        prompt = build_ending_vs_skeleton_prompt(ending, skeleton)
        resp = self.provider.complete(
            prompt,
            max_tokens=self.num_predict,
            temperature=self.temperature,
            format_schema=REVIEW_SCHEMA,
        )
        text = resp.text.strip()

        if self.logs_dir:
            log_call(
                team="meta_reviewer",
                role=f"ending_recheck_attempt{attempt}",
                work_id=work_id,
                chapter_n=0,
                prompt=prompt,
                response=resp,
                logs_dir=self.logs_dir,
            )

        return _parse_review(text, role="ending_recheck", attempt=attempt)


class OutlineConsistencyReviewer:
    """concept ↔ ending ↔ plot_skeleton(해당 막) 모순 검수자."""

    def __init__(
        self,
        provider: LLMProvider,
        *,
        temperature: float = 0.2,
        num_predict: int = 800,
        logs_dir: Path | None = None,
    ):
        self.provider = provider
        self.temperature = temperature
        self.num_predict = num_predict
        self.logs_dir = logs_dir

    def review_act(
        self,
        concept: dict,
        ending: dict,
        skeleton_act: list[dict],
        *,
        act_idx: int,
        attempt: int,
        work_id: str,
    ) -> ReviewResult:
        """act_idx 막에 해당하는 화들만 받아 정합 검수."""
        prompt = build_outline_consistency_prompt(
            concept, ending, skeleton_act, act_idx=act_idx
        )
        resp = self.provider.complete(
            prompt,
            max_tokens=self.num_predict,
            temperature=self.temperature,
            format_schema=REVIEW_SCHEMA,
        )
        text = resp.text.strip()

        if self.logs_dir:
            log_call(
                team="meta_reviewer",
                role=f"outline_consistency_act{act_idx + 1}_attempt{attempt}",
                work_id=work_id,
                chapter_n=0,
                prompt=prompt,
                response=resp,
                logs_dir=self.logs_dir,
            )

        return _parse_review(
            text, role=f"outline_consistency_act{act_idx + 1}", attempt=attempt
        )
