"""LangGraph 기반 오케스트레이터 그래프 — writer → naming → reviewer×3 → publisher."""
from __future__ import annotations

from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Literal

from langgraph.graph import END, StateGraph
from typing_extensions import TypedDict

from ..config import Settings
from ..memory import load_novel_context, load_persona, load_work_meta
from ..providers import get_provider
from ..teams.publisher import PublishResult, PublisherAgent
from ..teams.reviewer import ReviewerAgent, ReviewResult
from ..teams.reviewer.naming_checker import run_naming_check
from ..teams.writer import WriterAgent
from ..utils.alert import send_alert
from ..utils.logger import log_call, log_review_event

REVIEWER_ROLES: list[str] = ["direction", "character", "quality"]

# ── State ─────────────────────────────────────────────────────────────────────


class PipelineState(TypedDict):
    # 입력
    work_id: str
    chapter_n: int
    settings: Any  # Settings (직렬화 불필요 — 단일 프로세스)

    # 로드된 컨텍스트
    ctx: Any           # NovelContext
    persona: Any       # Persona

    # 작업 데이터
    draft: str
    review_history: list[dict]
    retry_counts: dict[str, int]   # {"naming": 0, "direction": 0, ...}

    # 현재 진행 단계
    current_stage: str  # "naming" | "direction" | "character" | "quality"

    # 결과
    success: bool
    failure_stage: str | None
    failure_reason: str | None
    chapter_path: Path | None
    meta_path: Path | None
    summary_path: Path | None

    # 로그
    started_at: str


# ── 노드 함수들 ──────────────────────────────────────────────────────────────


def _load_context(state: PipelineState) -> dict:
    settings: Settings = state["settings"]
    work_id = state["work_id"]
    chapter_n = state["chapter_n"]

    print(f"[orchestrator] 컨텍스트 로딩: {work_id} / ch{chapter_n:03d}")
    ctx = load_novel_context(
        work_id, chapter_n,
        novels_dir=settings.novels_dir,
        recent_n=settings.recent_summaries_n,
    )
    work_meta = load_work_meta(work_id, settings.novels_dir)
    persona = load_persona(work_meta["author_id"], settings.authors_dir)
    return {"ctx": ctx, "persona": persona}


def _writer_draft(state: PipelineState) -> dict:
    settings: Settings = state["settings"]
    ctx = state["ctx"]
    persona = state["persona"]
    work_id = state["work_id"]

    writer_model = persona.model_override or settings.model_key("writer")
    writer = WriterAgent(
        get_provider(writer_model, settings),
        beat_temperature=float(settings.config.get("writer", {}).get("beat_temperature", 0.85)),
        beat_num_predict=int(settings.config.get("writer", {}).get("beat_num_predict", 4000)),
        logs_dir=settings.logs_dir,
    )
    print(f"[writer] 초안 생성 시작 (비트 {len(ctx.chapter_outline.beats)}개)")
    draft = writer.draft(ctx, persona, work_id)
    print(f"[writer] 초안 완료: {len(draft)}자")
    return {"draft": draft, "current_stage": "naming"}


def _naming_check(state: PipelineState) -> dict:
    ctx = state["ctx"]
    draft = state["draft"]
    chapter_n = state["chapter_n"]
    work_id = state["work_id"]
    settings: Settings = state["settings"]
    retry_counts = dict(state["retry_counts"])
    review_history = list(state["review_history"])

    # naming_table이 없으면 검수 없이 바로 direction으로
    if not ctx.naming_table:
        return {
            "retry_counts": retry_counts,
            "review_history": review_history,
            "current_stage": "direction",
        }

    attempt = retry_counts.get("naming", 0) + 1
    retry_counts["naming"] = attempt

    print(f"[reviewer:naming] 시도 {attempt}/{settings.max_retries}")
    naming_result = run_naming_check(draft, ctx.naming_table, chapter_n)
    review_history.append({
        "role": "naming",
        "attempt": attempt,
        "passed": naming_result.passed,
        "score": naming_result.score,
        "reason": (f"호칭 위반 {len(naming_result.violations)}건"
                   if not naming_result.passed else "OK"),
        "feedback": naming_result.feedback,
        "parse_error": None,
        "timestamp": datetime.now(timezone.utc).isoformat(),
    })

    if naming_result.passed:
        print("[reviewer:naming] 통과")
        return {
            "retry_counts": retry_counts,
            "review_history": review_history,
            "current_stage": "direction",
        }

    if attempt >= settings.max_retries:
        return {
            "retry_counts": retry_counts,
            "review_history": review_history,
            "failure_stage": "naming",
            "failure_reason": naming_result.feedback,
            "current_stage": "__halt__",
        }

    # 수정
    print("[writer] 호칭 수정 시도")
    writer_model = state["persona"].model_override or settings.model_key("writer")
    writer = WriterAgent(
        get_provider(writer_model, settings),
        beat_temperature=float(settings.config.get("writer", {}).get("beat_temperature", 0.85)),
        beat_num_predict=int(settings.config.get("writer", {}).get("beat_num_predict", 4000)),
        logs_dir=settings.logs_dir,
    )
    new_draft = writer.revise(draft, naming_result.feedback, ctx, state["persona"], work_id)
    return {
        "draft": new_draft,
        "retry_counts": retry_counts,
        "review_history": review_history,
        "current_stage": "naming",  # 다시 naming으로
    }


def _make_reviewer_node(role: str):
    """direction / character / quality 검수 노드 팩토리."""
    def _reviewer_node(state: PipelineState) -> dict:
        settings: Settings = state["settings"]
        ctx = state["ctx"]
        persona = state["persona"]
        draft = state["draft"]
        work_id = state["work_id"]
        retry_counts = dict(state["retry_counts"])
        review_history = list(state["review_history"])

        attempt = retry_counts.get(role, 0) + 1
        retry_counts[role] = attempt

        reviewer_model = settings.model_key("reviewer", role)
        reviewer = ReviewerAgent(
            role,
            get_provider(reviewer_model, settings),
            temperature=float(settings.config.get("reviewer", {}).get("temperature", 0.2)),
            num_predict=int(settings.config.get("reviewer", {}).get("num_predict", 600)),
            logs_dir=settings.logs_dir,
        )
        print(f"[reviewer:{role}] 시도 {attempt}/{settings.max_retries}")
        result: ReviewResult = reviewer.review(draft, ctx, attempt, work_id)
        review_history.append({
            "role": result.role,
            "attempt": result.attempt,
            "passed": result.passed,
            "score": result.score,
            "reason": result.reason,
            "feedback": result.feedback if not result.passed else "",
            "parse_error": result.parse_error,
            "timestamp": datetime.now(timezone.utc).isoformat(),
        })

        if result.passed:
            print(f"[reviewer:{role}] 통과 (점수 {result.score})")
            role_idx = REVIEWER_ROLES.index(role)
            next_stage = REVIEWER_ROLES[role_idx + 1] if role_idx + 1 < len(REVIEWER_ROLES) else "publisher"
            return {
                "retry_counts": retry_counts,
                "review_history": review_history,
                "current_stage": next_stage,
            }

        if attempt >= settings.max_retries:
            msg = (
                f"[ALERT] {work_id} ch{state['chapter_n']:03d} {role} 검수 "
                f"{settings.max_retries}회 소진.\n사유: {result.reason}\n가이드: {result.feedback}"
            )
            print(msg)
            return {
                "retry_counts": retry_counts,
                "review_history": review_history,
                "failure_stage": role,
                "failure_reason": result.feedback,
                "current_stage": "__halt__",
            }

        # 수정
        print(f"[writer] 수정 시도 (사유: {result.reason})")
        writer_model = persona.model_override or settings.model_key("writer")
        writer = WriterAgent(
            get_provider(writer_model, settings),
            beat_temperature=float(settings.config.get("writer", {}).get("beat_temperature", 0.85)),
            beat_num_predict=int(settings.config.get("writer", {}).get("beat_num_predict", 4000)),
            logs_dir=settings.logs_dir,
        )
        new_draft = writer.revise(draft, result.feedback, ctx, persona, work_id)
        return {
            "draft": new_draft,
            "retry_counts": retry_counts,
            "review_history": review_history,
            "current_stage": role,  # 같은 검수자로 재시도
        }

    _reviewer_node.__name__ = f"reviewer_{role}"
    return _reviewer_node


def _polish_node(state: PipelineState) -> dict:
    """단문을 어미 연결로 묶어 호흡 정제. 의미·이름·플롯 변경 금지."""
    settings: Settings = state["settings"]
    ctx = state["ctx"]
    persona = state["persona"]
    draft = state["draft"]
    work_id = state["work_id"]

    writer_model = persona.model_override or settings.model_key("writer")
    writer = WriterAgent(
        get_provider(writer_model, settings),
        beat_temperature=float(settings.config.get("writer", {}).get("beat_temperature", 0.85)),
        beat_num_predict=int(settings.config.get("writer", {}).get("beat_num_predict", 4000)),
        logs_dir=settings.logs_dir,
    )
    print("[writer] 호흡 정제 (단문 합치기)")
    polished = writer.polish_flow(draft, ctx, persona, work_id)

    # 분량 sanity — 너무 줄거나 늘면 원본 유지
    ratio = len(polished) / max(1, len(draft))
    if 0.80 <= ratio <= 1.15 and len(polished) >= 2000:
        print(f"[writer] 정제 완료 ({len(draft)} → {len(polished)}자, 비율 {ratio:.2f})")
        return {"draft": polished, "current_stage": "publisher"}
    print(f"[writer] 정제 분량 이상 ({len(draft)} → {len(polished)}자, 비율 {ratio:.2f}) — 원본 유지")
    return {"current_stage": "publisher"}


def _publisher_node(state: PipelineState) -> dict:
    settings: Settings = state["settings"]
    ctx = state["ctx"]
    persona = state["persona"]
    draft = state["draft"]
    work_id = state["work_id"]

    print("[publisher] 메타데이터 생성 + 발행")
    publisher = PublisherAgent(
        get_provider(settings.model_key("publisher"), settings),
        temperature=float(settings.config.get("publisher", {}).get("temperature", 0.4)),
        num_predict=int(settings.config.get("publisher", {}).get("num_predict", 600)),
        logs_dir=settings.logs_dir,
    )
    pub: PublishResult = publisher.publish(draft, ctx, work_id, settings.novels_dir)
    print(f"[publisher] 발행 완료: {pub.title}")
    return {
        "chapter_path": pub.chapter_path,
        "meta_path": pub.meta_path,
        "current_stage": "summary",
    }


def _writer_summary(state: PipelineState) -> dict:
    settings: Settings = state["settings"]
    ctx = state["ctx"]
    persona = state["persona"]
    draft = state["draft"]
    work_id = state["work_id"]
    chapter_n = state["chapter_n"]
    started_at = state["started_at"]
    review_history = state["review_history"]

    print("[writer] 회차 요약 생성")
    writer_model = persona.model_override or settings.model_key("writer")
    writer = WriterAgent(
        get_provider(writer_model, settings),
        beat_temperature=float(settings.config.get("writer", {}).get("beat_temperature", 0.85)),
        beat_num_predict=int(settings.config.get("writer", {}).get("beat_num_predict", 4000)),
        logs_dir=settings.logs_dir,
    )
    summary = writer.write_summary(ctx, persona, draft, work_id)
    summary_path = (
        settings.novels_dir / work_id / "chapters" / f"ch{chapter_n:03d}_summary.md"
    )
    summary_path.write_text(summary, encoding="utf-8")

    log_review_event(
        work_id=work_id,
        chapter_n=chapter_n,
        pipeline_started_at=started_at,
        pipeline_finished_at=datetime.now(timezone.utc).isoformat(),
        final_status="published",
        history=review_history,
        logs_dir=settings.logs_dir,
    )

    return {"summary_path": summary_path, "success": True, "current_stage": "done"}


def _alert_and_halt(state: PipelineState) -> dict:
    settings: Settings = state["settings"]
    work_id = state["work_id"]
    chapter_n = state["chapter_n"]
    failure_stage = state.get("failure_stage") or "unknown"
    failure_reason = state.get("failure_reason") or ""
    started_at = state["started_at"]
    review_history = state["review_history"]

    msg = (
        f"[ALERT] {work_id} ch{chapter_n:03d} {failure_stage} 검수 "
        f"{settings.max_retries}회 소진.\n{failure_reason}"
    )
    send_alert(msg, settings)

    log_review_event(
        work_id=work_id,
        chapter_n=chapter_n,
        pipeline_started_at=started_at,
        pipeline_finished_at=datetime.now(timezone.utc).isoformat(),
        final_status="failed",
        history=review_history,
        logs_dir=settings.logs_dir,
    )
    return {"success": False}


# ── 조건부 엣지 라우터 ────────────────────────────────────────────────────────


def _route_after_naming(state: PipelineState) -> Literal["naming_check", "reviewer_direction", "alert_and_halt"]:
    stage = state["current_stage"]
    if stage == "__halt__":
        return "alert_and_halt"
    if stage == "naming":
        return "naming_check"
    return "reviewer_direction"


def _route_after_direction(state: PipelineState) -> Literal["reviewer_direction", "reviewer_character", "alert_and_halt"]:
    stage = state["current_stage"]
    if stage == "__halt__":
        return "alert_and_halt"
    if stage == "direction":
        return "reviewer_direction"
    return "reviewer_character"


def _route_after_character(state: PipelineState) -> Literal["reviewer_character", "reviewer_quality", "alert_and_halt"]:
    stage = state["current_stage"]
    if stage == "__halt__":
        return "alert_and_halt"
    if stage == "character":
        return "reviewer_character"
    return "reviewer_quality"


def _route_after_quality(state: PipelineState) -> Literal["reviewer_quality", "publisher", "alert_and_halt"]:
    stage = state["current_stage"]
    if stage == "__halt__":
        return "alert_and_halt"
    if stage == "quality":
        return "reviewer_quality"
    return "publisher"


# ── 그래프 빌드 ───────────────────────────────────────────────────────────────


def _build_graph() -> StateGraph:
    g = StateGraph(PipelineState)

    g.add_node("load_context", _load_context)
    g.add_node("writer_draft", _writer_draft)
    g.add_node("naming_check", _naming_check)
    g.add_node("reviewer_direction", _make_reviewer_node("direction"))
    g.add_node("reviewer_character", _make_reviewer_node("character"))
    g.add_node("reviewer_quality", _make_reviewer_node("quality"))
    g.add_node("polish_flow", _polish_node)
    g.add_node("publisher", _publisher_node)
    g.add_node("writer_summary", _writer_summary)
    g.add_node("alert_and_halt", _alert_and_halt)

    g.set_entry_point("load_context")
    g.add_edge("load_context", "writer_draft")

    # naming_check 건너뜀 조건: naming_table 없으면 바로 direction
    # (naming_check 노드 내부에서 ctx.naming_table 존재 여부를 판단하므로
    #  그래프 엣지는 항상 naming_check를 거침 — 내부에서 즉시 통과 처리)
    g.add_edge("writer_draft", "naming_check")

    g.add_conditional_edges("naming_check", _route_after_naming, {
        "naming_check": "naming_check",
        "reviewer_direction": "reviewer_direction",
        "alert_and_halt": "alert_and_halt",
    })
    g.add_conditional_edges("reviewer_direction", _route_after_direction, {
        "reviewer_direction": "reviewer_direction",
        "reviewer_character": "reviewer_character",
        "alert_and_halt": "alert_and_halt",
    })
    g.add_conditional_edges("reviewer_character", _route_after_character, {
        "reviewer_character": "reviewer_character",
        "reviewer_quality": "reviewer_quality",
        "alert_and_halt": "alert_and_halt",
    })
    g.add_conditional_edges("reviewer_quality", _route_after_quality, {
        "reviewer_quality": "reviewer_quality",
        "publisher": "polish_flow",
        "alert_and_halt": "alert_and_halt",
    })

    g.add_edge("polish_flow", "publisher")
    g.add_edge("publisher", "writer_summary")
    g.add_edge("writer_summary", END)
    g.add_edge("alert_and_halt", END)

    return g


# 컴파일된 그래프 (모듈 로드 시 한 번만 생성)
_compiled_graph = _build_graph().compile()


def invoke_pipeline(
    work_id: str,
    chapter_n: int,
    *,
    settings: Settings,
) -> PipelineState:
    """그래프를 실행하고 최종 State를 반환한다."""
    initial: PipelineState = {
        "work_id": work_id,
        "chapter_n": chapter_n,
        "settings": settings,
        "ctx": None,
        "persona": None,
        "draft": "",
        "review_history": [],
        "retry_counts": {},
        "current_stage": "naming",
        "success": False,
        "failure_stage": None,
        "failure_reason": None,
        "chapter_path": None,
        "meta_path": None,
        "summary_path": None,
        "started_at": datetime.now(timezone.utc).isoformat(),
    }
    return _compiled_graph.invoke(initial)


def render_graph_mermaid() -> str:
    """그래프 구조를 Mermaid 다이어그램 문자열로 반환한다."""
    return _compiled_graph.get_graph().draw_mermaid()
