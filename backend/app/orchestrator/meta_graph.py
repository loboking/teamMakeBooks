"""메타 파이프라인 — 컨셉 → 엔딩 → 100화 줄거리 LangGraph 오케스트레이터.

M1 범위: init_concept → ending_lock → ending_lock_review →
         plot_act1~3 (각 막 후 outline_consistency 루프) →
         ending_recheck → save_intermediate → END
"""
from __future__ import annotations

import json
import re
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Literal

import yaml
from langgraph.graph import END, StateGraph
from typing_extensions import TypedDict

from ..config import Settings
from ..providers import get_provider
from ..utils.alert import send_alert

# ── 의존 모듈 (다른 에이전트가 동시 작성 중 — M1_INTERFACES.md §2, §3 기준) ──────
# 아직 모듈이 생성되지 않았을 수 있음. 통합 테스트는 모든 에이전트 완료 후 진행.
from ..teams.meta_writer import MetaWriterAgent  # noqa: E402
from ..teams.reviewer.meta_reviewers import (  # noqa: E402
    EndingLockReviewer,
    OutlineConsistencyReviewer,
)
from ..teams.reviewer.agent import ReviewResult  # noqa: E402


# ── MetaState ─────────────────────────────────────────────────────────────────


class MetaState(TypedDict):
    settings: Any  # Settings 인스턴스 (직렬화 불필요 — 단일 프로세스)

    # 사용자 입력 (raw)
    concept_input: dict   # {"logline": str, "genre": str, "mood": str,
                          #  "total_chapters": int, "protagonist": str,
                          #  "keywords": [...], "forbidden": [...],
                          #  "reference_tone": str, "work_id": None|str}

    # 결정된 work_id (normalize_concept 후)
    work_id: str

    # 단계별 산출물
    concept: dict | None          # 정규화된 컨셉
    ending: dict | None           # {"summary": str, "act3_climax": str, "acts": [...]}
    plot_skeleton: list[dict] | None
                                  # [{"chapter_n": int, "act": int, "overall": str}, ...]

    # 검수
    review_history: list[dict]    # 각 스테이지 검수 결과 누적
    retry_counts: dict[str, int]  # {"ending_lock": N, "outline_consistency_act1": N, ...}

    # 진행
    current_stage: str            # "init_concept"|"ending_lock"|"plot_act1"|...|"__halt__"
    success: bool
    failure_stage: str | None
    failure_reason: str | None

    # 산출 경로 (M1: novels/{work_id}/_init/*.yaml)
    init_dir: Path | None         # novels/{work_id}/_init/

    started_at: str


# ── 유틸 ─────────────────────────────────────────────────────────────────────


def _slugify(text: str) -> str:
    """logline에서 URL-safe 슬러그 생성 (공백→_, 특수문자 제거, 최대 30자)."""
    text = re.sub(r"[^\w\s가-힣]", "", text)
    text = re.sub(r"\s+", "_", text.strip())
    return text[:30].lower() or "novel"


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def _agent_config(settings: Settings, team: str, role: str) -> dict:
    """settings.config에서 temperature·num_predict 추출. 없으면 기본값."""
    cfg = settings.config.get(team, {})
    return {
        "temperature": float(cfg.get(f"{role}_temperature", 0.5)),
        "num_predict": int(cfg.get(f"{role}_num_predict", 2000)),
    }


def _reviewer_config(settings: Settings, team: str) -> dict:
    cfg = settings.config.get(team, {})
    return {
        "temperature": float(cfg.get("temperature", 0.2)),
        "num_predict": int(cfg.get("num_predict", 800)),
    }


# ── 노드 함수 ─────────────────────────────────────────────────────────────────


def _init_concept(state: MetaState) -> dict:
    """사용자 입력 정규화 + work_id 생성 + 누락 옵션 보충."""
    settings: Settings = state["settings"]
    concept_input: dict = state["concept_input"]

    # work_id 결정: 이미 있으면 재사용, 없으면 logline 슬러그
    work_id = concept_input.get("work_id") or state.get("work_id") or ""
    if not work_id:
        logline = concept_input.get("logline", "")
        ts = datetime.now(timezone.utc).strftime("%y%m%d")
        genre_slug = concept_input.get("genre", "novel")[:10].replace(" ", "_")
        work_id = f"{genre_slug}_{_slugify(logline)}_{ts}"

    print(f"[meta:init_concept] work_id={work_id}")

    # MetaWriterAgent 생성
    model_key = settings.model_key("meta_writer", "concept")
    cfg = _agent_config(settings, "meta_writer", "concept")
    writer = MetaWriterAgent(
        get_provider(model_key, settings),
        temperature=cfg["temperature"],
        num_predict=cfg["num_predict"],
        logs_dir=settings.logs_dir,
    )

    concept = writer.normalize_concept(concept_input, work_id)
    print(f"[meta:init_concept] 컨셉 정규화 완료: {concept.get('logline', '')[:40]}...")

    return {
        "work_id": work_id,
        "concept": concept,
        "current_stage": "ending_lock",
    }


def _ending_lock(state: MetaState) -> dict:
    """엔딩 1줄 + 3막 골격 생성."""
    settings: Settings = state["settings"]
    concept: dict = state["concept"]
    work_id: str = state["work_id"]

    model_key = settings.model_key("meta_writer", "ending")
    cfg = _agent_config(settings, "meta_writer", "ending")
    writer = MetaWriterAgent(
        get_provider(model_key, settings),
        temperature=cfg["temperature"],
        num_predict=cfg["num_predict"],
        logs_dir=settings.logs_dir,
    )

    print(f"[meta:ending_lock] 엔딩 생성 중...")
    ending = writer.generate_ending(concept, work_id)
    print(f"[meta:ending_lock] 엔딩 생성 완료: {ending.get('summary', '')[:50]}...")

    return {
        "ending": ending,
        "current_stage": "ending_lock_review",
    }


def _ending_lock_review(state: MetaState) -> dict:
    """엔딩 ↔ 컨셉 일관성 검수. 실패 시 revise → 재시도."""
    settings: Settings = state["settings"]
    concept: dict = state["concept"]
    ending: dict = state["ending"]
    work_id: str = state["work_id"]
    retry_counts = dict(state["retry_counts"])
    review_history = list(state["review_history"])

    attempt = retry_counts.get("ending_lock", 0) + 1
    retry_counts["ending_lock"] = attempt
    max_retries = settings.max_retries

    model_key = settings.model_key("meta_reviewer", "ending_lock")
    cfg = _reviewer_config(settings, "meta_reviewer")
    reviewer = EndingLockReviewer(
        get_provider(model_key, settings),
        temperature=cfg["temperature"],
        num_predict=cfg["num_predict"],
        logs_dir=settings.logs_dir,
    )

    print(f"[meta:ending_lock_review] 시도 {attempt}/{max_retries}")
    result: ReviewResult = reviewer.review_ending(concept, ending, attempt=attempt, work_id=work_id)

    review_history.append({
        "role": result.role,
        "attempt": result.attempt,
        "passed": result.passed,
        "score": result.score,
        "reason": result.reason,
        "feedback": result.feedback if not result.passed else "",
        "parse_error": result.parse_error,
        "timestamp": _now_iso(),
    })

    if result.passed:
        print(f"[meta:ending_lock_review] 통과 (점수 {result.score})")
        return {
            "retry_counts": retry_counts,
            "review_history": review_history,
            "current_stage": "plot_act1",
        }

    if attempt >= max_retries:
        print(f"[meta:ending_lock_review] {max_retries}회 소진 → __halt__")
        return {
            "retry_counts": retry_counts,
            "review_history": review_history,
            "failure_stage": "ending_lock_review",
            "failure_reason": result.feedback,
            "current_stage": "__halt__",
        }

    # revise — 엔딩 재생성
    print(f"[meta:ending_lock_review] 엔딩 수정 (사유: {result.reason})")
    model_key_w = settings.model_key("meta_writer", "ending")
    cfg_w = _agent_config(settings, "meta_writer", "ending")
    writer = MetaWriterAgent(
        get_provider(model_key_w, settings),
        temperature=cfg_w["temperature"],
        num_predict=cfg_w["num_predict"],
        logs_dir=settings.logs_dir,
    )
    new_ending = writer.revise_ending(ending, result.feedback, concept, work_id)

    return {
        "ending": new_ending,
        "retry_counts": retry_counts,
        "review_history": review_history,
        "current_stage": "ending_lock_review",  # 재검수
    }


def _make_plot_act_node(act_idx: int):
    """plot_act1 / plot_act2 / plot_act3 노드 팩토리."""
    stage_name = f"plot_act{act_idx + 1}"

    def _plot_act_node(state: MetaState) -> dict:
        settings: Settings = state["settings"]
        concept: dict = state["concept"]
        ending: dict = state["ending"]
        work_id: str = state["work_id"]
        existing_skeleton: list[dict] = state.get("plot_skeleton") or []

        model_key = settings.model_key("meta_writer", "plot_skeleton")
        cfg = _agent_config(settings, "meta_writer", "plot_skeleton")
        writer = MetaWriterAgent(
            get_provider(model_key, settings),
            temperature=cfg["temperature"],
            num_predict=cfg["num_predict"],
            logs_dir=settings.logs_dir,
        )

        print(f"[meta:{stage_name}] {act_idx + 1}막 줄거리 생성 중...")
        act_chapters = writer.generate_plot_skeleton(
            concept, ending, act_idx=act_idx, work_id=work_id,
        )
        print(f"[meta:{stage_name}] {len(act_chapters)}화 생성 완료")

        # 기존 skeleton에서 이 막 외 화는 보존, 이 막 결과로 교체
        act_n = act_idx + 1
        filtered = [ch for ch in existing_skeleton if ch.get("act") != act_n]
        new_skeleton = sorted(filtered + act_chapters, key=lambda c: c["chapter_n"])

        return {
            "plot_skeleton": new_skeleton,
            "current_stage": f"outline_consistency_act{act_idx + 1}",
        }

    _plot_act_node.__name__ = stage_name
    return _plot_act_node


def _make_outline_consistency_node(act_idx: int):
    """outline_consistency_act1 / act2 / act3 노드 팩토리. revise 루프 내장."""
    stage_name = f"outline_consistency_act{act_idx + 1}"
    retry_key = stage_name

    def _consistency_node(state: MetaState) -> dict:
        settings: Settings = state["settings"]
        concept: dict = state["concept"]
        ending: dict = state["ending"]
        plot_skeleton: list[dict] = state["plot_skeleton"]
        work_id: str = state["work_id"]
        retry_counts = dict(state["retry_counts"])
        review_history = list(state["review_history"])

        attempt = retry_counts.get(retry_key, 0) + 1
        retry_counts[retry_key] = attempt
        max_retries = settings.max_retries

        # 이 막 화만 추출
        act_n = act_idx + 1
        skeleton_act = [ch for ch in plot_skeleton if ch.get("act") == act_n]

        model_key = settings.model_key("meta_reviewer", "outline_consistency")
        cfg = _reviewer_config(settings, "meta_reviewer")
        reviewer = OutlineConsistencyReviewer(
            get_provider(model_key, settings),
            temperature=cfg["temperature"],
            num_predict=cfg["num_predict"],
            logs_dir=settings.logs_dir,
        )

        print(f"[meta:{stage_name}] 시도 {attempt}/{max_retries} ({len(skeleton_act)}화)")
        result: ReviewResult = reviewer.review_act(
            concept, ending, skeleton_act,
            act_idx=act_idx, attempt=attempt, work_id=work_id,
        )

        review_history.append({
            "role": result.role,
            "attempt": result.attempt,
            "passed": result.passed,
            "score": result.score,
            "reason": result.reason,
            "feedback": result.feedback if not result.passed else "",
            "parse_error": result.parse_error,
            "timestamp": _now_iso(),
        })

        # 다음 스테이지 결정
        next_stages = {0: "plot_act2", 1: "plot_act3", 2: "ending_recheck"}

        if result.passed:
            print(f"[meta:{stage_name}] 통과 (점수 {result.score})")
            return {
                "retry_counts": retry_counts,
                "review_history": review_history,
                "current_stage": next_stages[act_idx],
            }

        if attempt >= max_retries:
            print(f"[meta:{stage_name}] {max_retries}회 소진 → __halt__")
            return {
                "retry_counts": retry_counts,
                "review_history": review_history,
                "failure_stage": stage_name,
                "failure_reason": result.feedback,
                "current_stage": "__halt__",
            }

        # revise — 해당 막 재생성
        print(f"[meta:{stage_name}] {act_idx + 1}막 수정 (사유: {result.reason})")
        model_key_w = settings.model_key("meta_writer", "plot_skeleton")
        cfg_w = _agent_config(settings, "meta_writer", "plot_skeleton")
        writer = MetaWriterAgent(
            get_provider(model_key_w, settings),
            temperature=cfg_w["temperature"],
            num_predict=cfg_w["num_predict"],
            logs_dir=settings.logs_dir,
        )
        revised_act = writer.revise_plot_act(
            skeleton_act, result.feedback, concept, ending,
            act_idx=act_idx, work_id=work_id,
        )

        # skeleton 갱신
        other_acts = [ch for ch in plot_skeleton if ch.get("act") != act_n]
        new_skeleton = sorted(other_acts + revised_act, key=lambda c: c["chapter_n"])

        return {
            "plot_skeleton": new_skeleton,
            "retry_counts": retry_counts,
            "review_history": review_history,
            "current_stage": stage_name,  # 재검수
        }

    _consistency_node.__name__ = stage_name
    return _consistency_node


def _ending_recheck(state: MetaState) -> dict:
    """100화 완성 후 마지막 화 ↔ 엔딩 일치 검수. 실패 시 3막 revise."""
    settings: Settings = state["settings"]
    concept: dict = state["concept"]
    ending: dict = state["ending"]
    plot_skeleton: list[dict] = state["plot_skeleton"]
    work_id: str = state["work_id"]
    retry_counts = dict(state["retry_counts"])
    review_history = list(state["review_history"])

    attempt = retry_counts.get("ending_recheck", 0) + 1
    retry_counts["ending_recheck"] = attempt
    max_retries = settings.max_retries

    model_key = settings.model_key("meta_reviewer", "ending_lock")
    cfg = _reviewer_config(settings, "meta_reviewer")
    reviewer = EndingLockReviewer(
        get_provider(model_key, settings),
        temperature=cfg["temperature"],
        num_predict=cfg["num_predict"],
        logs_dir=settings.logs_dir,
    )

    print(f"[meta:ending_recheck] 시도 {attempt}/{max_retries} (전체 {len(plot_skeleton)}화)")
    result: ReviewResult = reviewer.review_against_skeleton(
        ending, plot_skeleton, attempt=attempt, work_id=work_id,
    )

    review_history.append({
        "role": result.role,
        "attempt": result.attempt,
        "passed": result.passed,
        "score": result.score,
        "reason": result.reason,
        "feedback": result.feedback if not result.passed else "",
        "parse_error": result.parse_error,
        "timestamp": _now_iso(),
    })

    if result.passed:
        print(f"[meta:ending_recheck] 통과 (점수 {result.score})")
        return {
            "retry_counts": retry_counts,
            "review_history": review_history,
            "current_stage": "save",
        }

    if attempt >= max_retries:
        print(f"[meta:ending_recheck] {max_retries}회 소진 → __halt__")
        return {
            "retry_counts": retry_counts,
            "review_history": review_history,
            "failure_stage": "ending_recheck",
            "failure_reason": result.feedback,
            "current_stage": "__halt__",
        }

    # 3막(act_idx=2)만 재생성
    print(f"[meta:ending_recheck] 3막 재수정 (사유: {result.reason})")
    act3_skeleton = [ch for ch in plot_skeleton if ch.get("act") == 3]
    model_key_w = settings.model_key("meta_writer", "plot_skeleton")
    cfg_w = _agent_config(settings, "meta_writer", "plot_skeleton")
    writer = MetaWriterAgent(
        get_provider(model_key_w, settings),
        temperature=cfg_w["temperature"],
        num_predict=cfg_w["num_predict"],
        logs_dir=settings.logs_dir,
    )
    revised_act3 = writer.revise_plot_act(
        act3_skeleton, result.feedback, concept, ending,
        act_idx=2, work_id=work_id,
    )

    other_acts = [ch for ch in plot_skeleton if ch.get("act") != 3]
    new_skeleton = sorted(other_acts + revised_act3, key=lambda c: c["chapter_n"])

    return {
        "plot_skeleton": new_skeleton,
        "retry_counts": retry_counts,
        "review_history": review_history,
        "current_stage": "ending_recheck",  # 재검수
    }


def _save_intermediate(state: MetaState) -> dict:
    """novels/{work_id}/_init/ 에 concept / ending / plot_skeleton yaml 저장."""
    settings: Settings = state["settings"]
    work_id: str = state["work_id"]
    concept: dict = state["concept"]
    ending: dict = state["ending"]
    plot_skeleton: list[dict] = state["plot_skeleton"]

    init_dir: Path = settings.novels_dir / work_id / "_init"
    init_dir.mkdir(parents=True, exist_ok=True)

    dump_opts = {"allow_unicode": True, "sort_keys": False}

    concept_path = init_dir / "concept.yaml"
    concept_path.write_text(yaml.safe_dump(concept, **dump_opts), encoding="utf-8")

    ending_path = init_dir / "ending.yaml"
    ending_path.write_text(yaml.safe_dump(ending, **dump_opts), encoding="utf-8")

    total = concept.get("total_chapters", len(plot_skeleton))
    skeleton_doc = {"total": total, "chapters": plot_skeleton}
    skeleton_path = init_dir / "plot_skeleton.yaml"
    skeleton_path.write_text(yaml.safe_dump(skeleton_doc, **dump_opts), encoding="utf-8")

    print(f"[meta:save] 저장 완료 → {init_dir}")
    print(f"[meta:save]   concept.yaml ({len(concept)} keys)")
    print(f"[meta:save]   ending.yaml  ({len(ending.get('acts', []))}막)")
    print(f"[meta:save]   plot_skeleton.yaml ({len(plot_skeleton)}화)")

    return {
        "init_dir": init_dir,
        "success": True,
        "current_stage": "done",
    }


def _meta_alert_and_halt(state: MetaState) -> dict:
    """실패 기록 JSON 저장 + 텔레그램/콘솔 경보."""
    settings: Settings = state["settings"]
    work_id: str = state.get("work_id", "unknown")
    failure_stage: str = state.get("failure_stage") or "unknown"
    failure_reason: str = state.get("failure_reason") or ""
    started_at: str = state.get("started_at", "")
    review_history: list[dict] = state.get("review_history", [])

    failed_at = _now_iso()
    ts = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%S")

    # logs/failures/ 디렉토리 보장
    failures_dir = settings.logs_dir / "failures"
    failures_dir.mkdir(parents=True, exist_ok=True)

    failure_record = {
        "work_id": work_id,
        "failure_stage": failure_stage,
        "failure_reason": failure_reason,
        "review_history": review_history,
        "started_at": started_at,
        "failed_at": failed_at,
        "max_retries": settings.max_retries,
    }

    failure_path = failures_dir / f"meta_{work_id}_{failure_stage}_{ts}.json"
    failure_path.write_text(
        json.dumps(failure_record, ensure_ascii=False, indent=2), encoding="utf-8"
    )
    print(f"[meta:halt] 실패 기록 → {failure_path}")

    # 경보 (텔레그램 포함)
    msg = (
        f"[META PIPELINE 실패] work_id={work_id}\n"
        f"단계: {failure_stage}\n"
        f"사유: {failure_reason}"
    )
    send_alert(msg, settings)

    return {"success": False}


# ── 조건부 라우터 ─────────────────────────────────────────────────────────────


def _route(
    state: MetaState,
    *,
    self_node: str,
    next_node: str,
) -> str:
    """공통 라우터: current_stage == '__halt__' → alert, == self_node → self_node, else → next_node."""
    stage = state["current_stage"]
    if stage == "__halt__":
        return "meta_alert_and_halt"
    if stage == self_node:
        return self_node
    return next_node


def _route_after_ending_lock_review(
    state: MetaState,
) -> Literal["ending_lock_review", "plot_act1", "meta_alert_and_halt"]:
    return _route(state, self_node="ending_lock_review", next_node="plot_act1")  # type: ignore[return-value]


def _route_after_outline_consistency_act1(
    state: MetaState,
) -> Literal["outline_consistency_act1", "plot_act2", "meta_alert_and_halt"]:
    return _route(state, self_node="outline_consistency_act1", next_node="plot_act2")  # type: ignore[return-value]


def _route_after_outline_consistency_act2(
    state: MetaState,
) -> Literal["outline_consistency_act2", "plot_act3", "meta_alert_and_halt"]:
    return _route(state, self_node="outline_consistency_act2", next_node="plot_act3")  # type: ignore[return-value]


def _route_after_outline_consistency_act3(
    state: MetaState,
) -> Literal["outline_consistency_act3", "ending_recheck", "meta_alert_and_halt"]:
    return _route(state, self_node="outline_consistency_act3", next_node="ending_recheck")  # type: ignore[return-value]


def _route_after_ending_recheck(
    state: MetaState,
) -> Literal["ending_recheck", "save_intermediate", "meta_alert_and_halt"]:
    return _route(state, self_node="ending_recheck", next_node="save_intermediate")  # type: ignore[return-value]


# ── 그래프 빌드 ───────────────────────────────────────────────────────────────


def _build_meta_graph() -> StateGraph:
    g = StateGraph(MetaState)

    # 노드 등록
    g.add_node("init_concept", _init_concept)
    g.add_node("ending_lock", _ending_lock)
    g.add_node("ending_lock_review", _ending_lock_review)
    g.add_node("plot_act1", _make_plot_act_node(0))
    g.add_node("outline_consistency_act1", _make_outline_consistency_node(0))
    g.add_node("plot_act2", _make_plot_act_node(1))
    g.add_node("outline_consistency_act2", _make_outline_consistency_node(1))
    g.add_node("plot_act3", _make_plot_act_node(2))
    g.add_node("outline_consistency_act3", _make_outline_consistency_node(2))
    g.add_node("ending_recheck", _ending_recheck)
    g.add_node("save_intermediate", _save_intermediate)
    g.add_node("meta_alert_and_halt", _meta_alert_and_halt)

    # 진입점 및 직선 엣지
    g.set_entry_point("init_concept")
    g.add_edge("init_concept", "ending_lock")
    g.add_edge("ending_lock", "ending_lock_review")
    g.add_edge("plot_act1", "outline_consistency_act1")
    g.add_edge("plot_act2", "outline_consistency_act2")
    g.add_edge("plot_act3", "outline_consistency_act3")
    g.add_edge("save_intermediate", END)
    g.add_edge("meta_alert_and_halt", END)

    # 조건부 엣지 (검수 루프)
    g.add_conditional_edges(
        "ending_lock_review",
        _route_after_ending_lock_review,
        {
            "ending_lock_review": "ending_lock_review",
            "plot_act1": "plot_act1",
            "meta_alert_and_halt": "meta_alert_and_halt",
        },
    )
    g.add_conditional_edges(
        "outline_consistency_act1",
        _route_after_outline_consistency_act1,
        {
            "outline_consistency_act1": "outline_consistency_act1",
            "plot_act2": "plot_act2",
            "meta_alert_and_halt": "meta_alert_and_halt",
        },
    )
    g.add_conditional_edges(
        "outline_consistency_act2",
        _route_after_outline_consistency_act2,
        {
            "outline_consistency_act2": "outline_consistency_act2",
            "plot_act3": "plot_act3",
            "meta_alert_and_halt": "meta_alert_and_halt",
        },
    )
    g.add_conditional_edges(
        "outline_consistency_act3",
        _route_after_outline_consistency_act3,
        {
            "outline_consistency_act3": "outline_consistency_act3",
            "ending_recheck": "ending_recheck",
            "meta_alert_and_halt": "meta_alert_and_halt",
        },
    )
    g.add_conditional_edges(
        "ending_recheck",
        _route_after_ending_recheck,
        {
            "ending_recheck": "ending_recheck",
            "save_intermediate": "save_intermediate",
            "meta_alert_and_halt": "meta_alert_and_halt",
        },
    )

    return g


# 컴파일된 그래프 (모듈 로드 시 한 번만 생성)
_compiled_meta_graph = _build_meta_graph().compile()


# ── 진입 함수 ─────────────────────────────────────────────────────────────────


def invoke_meta_pipeline(
    concept_input: dict,
    *,
    settings: Settings,
    work_id: str | None = None,
) -> MetaState:
    """logline + 옵션 → 100화 plot_skeleton.yaml까지 자동 생성.

    Args:
        concept_input: {"logline": str, "genre": str, ...} (M1_INTERFACES.md §1 참고)
        settings: load_settings()로 만든 Settings 인스턴스
        work_id: None이면 logline에서 자동 슬러그 생성

    Returns:
        최종 MetaState (state["success"] == True이면 정상 완료)
    """
    initial: MetaState = {
        "settings": settings,
        "concept_input": concept_input,
        "work_id": work_id or "",
        "concept": None,
        "ending": None,
        "plot_skeleton": None,
        "review_history": [],
        "retry_counts": {},
        "current_stage": "init_concept",
        "success": False,
        "failure_stage": None,
        "failure_reason": None,
        "init_dir": None,
        "started_at": _now_iso(),
    }
    return _compiled_meta_graph.invoke(initial)


def render_meta_graph_mermaid() -> str:
    """메타 그래프 구조를 Mermaid 다이어그램 문자열로 반환."""
    return _compiled_meta_graph.get_graph().draw_mermaid()
