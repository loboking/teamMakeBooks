"""파이프라인 오케스트레이터 — LangGraph graph.py 래퍼.

기존 PipelineResult / run_chapter_pipeline() 시그니처를 100% 보존한다.
"""
from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

from ..config import Settings
from .graph import invoke_pipeline


@dataclass
class PipelineResult:
    work_id: str
    chapter_n: int
    success: bool
    failure_stage: str | None
    failure_reason: str | None
    chapter_path: Path | None
    meta_path: Path | None
    summary_path: Path | None
    review_history: list[dict]


def run_chapter_pipeline(
    work_id: str,
    chapter_n: int,
    *,
    settings: Settings,
) -> PipelineResult:
    state = invoke_pipeline(work_id, chapter_n, settings=settings)
    return PipelineResult(
        work_id=state["work_id"],
        chapter_n=state["chapter_n"],
        success=state["success"],
        failure_stage=state.get("failure_stage"),
        failure_reason=state.get("failure_reason"),
        chapter_path=state.get("chapter_path"),
        meta_path=state.get("meta_path"),
        summary_path=state.get("summary_path"),
        review_history=state.get("review_history", []),
    )
