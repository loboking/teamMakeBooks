"""LangGraph 기반 오케스트레이터 그래프 — writer → naming → reviewer×4 → publisher."""
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
from ..teams.reviewer.dedup import remove_duplicates
from ..teams.reviewer.naming_checker import run_naming_check
from ..teams.reviewer.pronoun_fixer import fix_gender_pronouns
from ..teams.reviewer.prompts import _count_repetition_patterns, _format_count_report
from ..teams.reviewer.subject_rotator import rotate_subjects
from ..teams.writer import WriterAgent
from ..utils.alert import send_alert
from ..utils.logger import log_call, log_review_event

REVIEWER_ROLES: list[str] = ["direction", "character", "quality", "repetition"]

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
        print(f"[ALERT] {work_id} ch{chapter_n:03d} naming 검수 {settings.max_retries}회 소진 — 경고 마킹 후 진행")
        review_history[-1]["passed"] = True
        review_history[-1]["reason"] += f" [경고: naming {settings.max_retries}회 소진]"
        return {
            "retry_counts": retry_counts,
            "review_history": review_history,
            "current_stage": "direction",
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
                f"{settings.max_retries}회 소진 — 경고 마킹 후 진행: {result.feedback}"
            )
            print(msg)
            review_history[-1]["passed"] = True
            review_history[-1]["reason"] += f" [경고: {role} {settings.max_retries}회 소진]"
            role_idx = REVIEWER_ROLES.index(role)
            next_stage = REVIEWER_ROLES[role_idx + 1] if role_idx + 1 < len(REVIEWER_ROLES) else "publisher"
            return {
                "retry_counts": retry_counts,
                "review_history": review_history,
                "current_stage": next_stage,
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


def _load_main_characters(work_meta: dict) -> tuple[list[dict], dict]:
    """meta.json에서 main_characters 로드 → (names, name_limits).

    형식: meta.json의 "main_characters" = [
        {"name":"허다연","short":"다연","limit_full":5,"limit_short":25},
        ...
    ]
    main_characters 누락 시 protagonist 단일 사용 (보수적 폴백).
    """
    raw = work_meta.get("main_characters") or []
    if not raw:
        # 폴백: protagonist 한 명. short 없음.
        proto = str(work_meta.get("protagonist", "") or work_meta.get("title", "주인공")).strip()
        raw = [{"name": proto, "short": "", "limit_full": 7, "limit_short": 25}]

    names: list[dict] = []
    name_limits: dict = {}
    for c in raw:
        full = str(c.get("name", "")).strip()
        if not full:
            continue
        names.append({"name": full, "short": str(c.get("short", "")).strip()})
        name_limits[full] = {
            "full": int(c.get("limit_full", 7)),
            "short": int(c.get("limit_short", 25)),
        }
    return names, name_limits


def _repetition_review_node(state: PipelineState) -> dict:
    """전용 반복 검수 노드 — regex pre-count + LLM 판정 + polish_repetition 수정."""
    settings: Settings = state["settings"]
    draft = state["draft"]
    work_id = state["work_id"]
    retry_counts = dict(state["retry_counts"])
    review_history = list(state["review_history"])

    attempt = retry_counts.get("repetition", 0) + 1
    retry_counts["repetition"] = attempt

    # 작품 메타에서 주조연 호명·임계 로드 (강이준 하드코딩 제거)
    work_meta = load_work_meta(work_id, settings.novels_dir)
    names, name_limits = _load_main_characters(work_meta)

    def _all_within_limits(c: dict) -> tuple[bool, str]:
        """검사 결과 + 실패 사유. 통과 시 (True, "")."""
        # 인물별 한계 — 가드레일이 처리하므로 반려 사유에서 제외
        # for full, cnt in c.get("names", {}).items():
        #     ...
        # 동작동사 ≤4 (조금 완화)
        for verb, c2 in c.get("동작동사", {}).items():
            if c2 > 4:
                return False, f"동사 '{verb}'={c2}>4"
        # 연속주어 ≤6
        if c.get("연속주어", 0) > 6:
            return False, f"연속주어={c['연속주어']}>6"
        # 등급직업은 헌터물 등에서만 의미 — 한계 ≤3
        for kw, c2 in c.get("등급직업", {}).items():
            if c2 > 3:
                return False, f"등급 '{kw}'={c2}>3"
        return True, ""

    # regex pre-count — 모두 한계 이내이면 LLM 없이 즉시 통과
    counts = _count_repetition_patterns(draft, names)
    pre_ok, _ = _all_within_limits(counts)
    if pre_ok:
        print(f"[reviewer:repetition] 시도 {attempt} — regex 전체 통과 (LLM 생략)")
        review_history.append({
            "role": "repetition", "attempt": attempt, "passed": True,
            "score": 9, "reason": "regex pre-count 모두 한계 이내",
            "feedback": "", "parse_error": None,
            "timestamp": datetime.now(timezone.utc).isoformat(),
        })
        return {
            "retry_counts": retry_counts,
            "review_history": review_history,
            "current_stage": "publisher",
        }

    # LLM 판정
    from ..teams.reviewer.prompts import build_reviewer_prompt

    rep_max = int(settings.config.get("reviewer", {}).get("repetition_max_retries", 5))
    print(f"[reviewer:repetition] 시도 {attempt}/{rep_max}")
    reviewer_model = settings.model_key("reviewer", "repetition")
    reviewer = ReviewerAgent(
        "repetition",
        get_provider(reviewer_model, settings),
        temperature=float(settings.config.get("reviewer", {}).get("temperature", 0.2)),
        num_predict=int(settings.config.get("reviewer", {}).get("num_predict", 600)),
        logs_dir=settings.logs_dir,
    )

    # 작품 메타 + main_characters를 가진 최소 컨텍스트 (repetition 프롬프트가 ctx에서 names 추출)
    _ch_n = state["chapter_n"]
    _names = list(names)
    _name_limits = dict(name_limits)
    class _FakeCtx:
        current_chapter_n = _ch_n
        theme = ""
        naming_table = ""
        characters = ""
        plot_outline = ""
        chapter_outline = type('CO', (), {'overall': property(lambda self: '')})()
        main_characters = _names
        name_limits = _name_limits
    result: ReviewResult = reviewer.review(draft, _FakeCtx(), attempt, work_id)

    review_history.append({
        "role": result.role, "attempt": result.attempt, "passed": result.passed,
        "score": result.score, "reason": result.reason,
        "feedback": result.feedback if not result.passed else "",
        "parse_error": result.parse_error,
        "timestamp": datetime.now(timezone.utc).isoformat(),
    })

    if result.passed:
        # LLM 통과 시에도 regex 최종 검증 — LLM이 관대하게 통과시키는 경우 방지
        final_counts = _count_repetition_patterns(draft, names)
        ok, reason = _all_within_limits(final_counts)
        still_bad = not ok
        if still_bad:
            offenders_str = reason or "(이름 외 패턴)"
            print(f"[reviewer:repetition] LLM 통과했으나 regex 재검증 실패 — {offenders_str}")
            # 5회 소진 시: halt 대신 경고 마킹 후 publisher로 통과 (사용자 정책: 본문 발행 우선)
            if attempt >= rep_max:
                msg = f"[ALERT] {work_id} ch{state['chapter_n']:03d} repetition 검수 {rep_max}회 소진 — 경고 마킹 후 발행: {offenders_str}"
                print(msg)
                review_history[-1]["passed"] = True
                review_history[-1]["reason"] += f" [경고: regex 최종검증 미달 — {offenders_str}]"
                return {
                    "retry_counts": retry_counts,
                    "review_history": review_history,
                    "current_stage": "publisher",
                }
            # polish 재시도 — feedback에 regex 카운트 주입
            counts_report = _format_count_report(final_counts, name_limits)
            polish_feedback = f"여전히 초과됨:\n{counts_report}\n더 적극적으로 제거하세요."
            _persona = state["persona"]
            _wm = _persona.model_override or settings.model_key("writer")
            _w = WriterAgent(
                get_provider(_wm, settings),
                beat_temperature=float(settings.config.get("writer", {}).get("beat_temperature", 0.85)),
                beat_num_predict=int(settings.config.get("writer", {}).get("beat_num_predict", 4000)),
                logs_dir=settings.logs_dir,
            )
            new_draft = _w.polish_repetition(draft, polish_feedback, work_id, ctx=_FakeCtx())
            review_history[-1]["passed"] = False
            review_history[-1]["reason"] += f" (regex 재검증: {offenders_str})"
            return {
                "draft": new_draft,
                "retry_counts": retry_counts,
                "review_history": review_history,
                "current_stage": "repetition",
            }
        print(f"[reviewer:repetition] 통과 (점수 {result.score}) — regex 최종 검증 OK")
        return {
            "retry_counts": retry_counts,
            "review_history": review_history,
            "current_stage": "publisher",
        }

    if attempt >= rep_max:
        msg = (
            f"[ALERT] {work_id} ch{state['chapter_n']:03d} repetition 검수 "
            f"{rep_max}회 소진 — 경고 마킹 후 발행: {result.feedback}"
        )
        print(msg)
        review_history[-1]["passed"] = True
        review_history[-1]["reason"] += f" [경고: {rep_max}회 소진 — {result.feedback}]"
        return {
            "retry_counts": retry_counts,
            "review_history": review_history,
            "current_stage": "publisher",
        }

    # 전용 반복 정제 (revise 대신 polish_repetition 사용)
    print(f"[writer] 반복 정제 (사유: {result.reason})")
    writer_model = state["persona"].model_override or settings.model_key("writer")
    writer = WriterAgent(
        get_provider(writer_model, settings),
        beat_temperature=float(settings.config.get("writer", {}).get("beat_temperature", 0.85)),
        beat_num_predict=int(settings.config.get("writer", {}).get("beat_num_predict", 4000)),
        logs_dir=settings.logs_dir,
    )
    new_draft = writer.polish_repetition(draft, result.feedback, work_id, ctx=_FakeCtx())
    return {
        "draft": new_draft,
        "retry_counts": retry_counts,
        "review_history": review_history,
        "current_stage": "repetition",
    }


def _pronoun_fix_node(state: PipelineState) -> dict:
    """결정론적 3단계 정제 — dedup → pronoun → subject rotation."""
    draft = state["draft"]
    work_id = state["work_id"]
    settings: Settings = state["settings"]

    work_meta = load_work_meta(work_id, settings.novels_dir)
    characters = work_meta.get("main_characters", [])
    current = draft

    # Step 1: 중복 문단·반복 구문 제거
    dedup_result = remove_duplicates(current)
    if dedup_result.removed_paragraphs > 0 or dedup_result.removed_phrases > 0 or dedup_result.removed_banned_words > 0:
        current = dedup_result.fixed
        parts = []
        if dedup_result.removed_paragraphs > 0:
            parts.append(f"문단 {dedup_result.removed_paragraphs}개")
        if dedup_result.removed_phrases > 0:
            parts.append(f"구문 {dedup_result.removed_phrases}개")
        if dedup_result.removed_banned_words > 0:
            parts.append(f"금지어 {dedup_result.removed_banned_words}개")
        print(f"[dedup] {' + '.join(parts)} 제거")
    else:
        print("[dedup] 중복/금지어 없음")

    # Step 2: 성별 대명사 치환
    if characters:
        pronoun_result = fix_gender_pronouns(current, characters)
        if pronoun_result.fix_count > 0:
            current = pronoun_result.fixed
            print(f"[pronoun_fix] {pronoun_result.fix_count}건 치환")
            for d in pronoun_result.details[:3]:
                print(f"  - {d}")
            if len(pronoun_result.details) > 3:
                print(f"  ... 외 {len(pronoun_result.details) - 3}건")
        else:
            print("[pronoun_fix] 치환 없음")

    # Step 3: 연속 주어 회전
    if characters:
        subject_result = rotate_subjects(current, characters)
        if subject_result.fix_count > 0:
            current = subject_result.fixed
            print(f"[subject_rotate] {subject_result.fix_count}건 회전")
            for d in subject_result.details[:3]:
                print(f"  - {d}")
            if len(subject_result.details) > 3:
                print(f"  ... 외 {len(subject_result.details) - 3}건")
        else:
            print("[subject_rotate] 회전 불필요")

    return {"draft": current, "current_stage": "polish_flow"}


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
    if 0.80 <= ratio <= 1.15 and len(polished) >= 2500:
        print(f"[writer] 정제 완료 ({len(draft)} → {len(polished)}자, 비율 {ratio:.2f})")
    else:
        print(f"[writer] 정제 분량 이상 ({len(draft)} → {len(polished)}자, 비율 {ratio:.2f}) — 원본 유지")
        polished = draft

    # polish_flow(LLM)이 주어 회전을 망칠 수 있으므로 subject_rotate 재실행
    work_meta = load_work_meta(work_id, settings.novels_dir)
    characters = work_meta.get("main_characters", [])
    if characters:
        post_result = rotate_subjects(polished, characters)
        if post_result.fix_count > 0:
            polished = post_result.fixed
            print(f"[subject_rotate:post] polish 후 재정제 {post_result.fix_count}건")
    return {"draft": polished, "current_stage": "publisher"}


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

    # 위키 자동 갱신 — 등장 인물·사건·타임라인
    try:
        from ..wiki import detect_characters_in_text, update_wiki_after_chapter
        wiki_root = settings.project_root / "wiki"
        if (wiki_root / work_id).exists():
            candidate_names = [c.get("name", "") for c in getattr(ctx, "main_characters", []) or []]
            chars_in = detect_characters_in_text(draft, candidate_names)
            chapter_title = ""
            try:
                import json as _json
                meta_path = settings.novels_dir / work_id / "chapters" / f"ch{chapter_n:03d}_meta.json"
                if meta_path.exists():
                    chapter_title = _json.loads(meta_path.read_text(encoding="utf-8")).get("title", "")
            except Exception:
                pass
            update_wiki_after_chapter(
                wiki_root, work_id,
                chapter_n=chapter_n, summary=summary,
                characters_in_chapter=chars_in, slug=chapter_title,
            )
            print(f"[wiki] 갱신 완료 — 인물 {len(chars_in)}명, ch{chapter_n:03d} event 기록")
    except Exception as e:
        print(f"[wiki] 갱신 실패 (무시): {e}")

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
    import json as _json

    settings: Settings = state["settings"]
    work_id = state["work_id"]
    chapter_n = state["chapter_n"]
    failure_stage = state.get("failure_stage") or "unknown"
    failure_reason = state.get("failure_reason") or ""
    started_at = state["started_at"]
    review_history = state["review_history"]
    draft = state.get("draft", "") or ""

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

    # 구조화된 실패 누적 (휴먼 개입 + 패턴 분석용)
    failures_dir = settings.logs_dir / "failures"
    failures_dir.mkdir(parents=True, exist_ok=True)
    ts = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%S")
    failure_record = {
        "work_id": work_id,
        "chapter_n": chapter_n,
        "failure_stage": failure_stage,
        "failure_reason": failure_reason,
        "started_at": started_at,
        "failed_at": datetime.now(timezone.utc).isoformat(),
        "max_retries": settings.max_retries,
        "review_history": review_history,
        "draft_chars": len(draft),
        "draft_snippet_head": draft[:500],
        "draft_snippet_tail": draft[-500:] if len(draft) > 500 else "",
    }
    failure_path = failures_dir / f"{ts}_ch{chapter_n:03d}_{failure_stage}.json"
    failure_path.write_text(
        _json.dumps(failure_record, ensure_ascii=False, indent=2), encoding="utf-8"
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


def _route_after_quality(state: PipelineState) -> Literal["reviewer_quality", "reviewer_repetition", "alert_and_halt"]:
    stage = state["current_stage"]
    if stage == "__halt__":
        return "alert_and_halt"
    if stage == "quality":
        return "reviewer_quality"
    return "reviewer_repetition"


def _route_after_repetition(state: PipelineState) -> Literal["reviewer_repetition", "publisher", "alert_and_halt"]:
    stage = state["current_stage"]
    if stage == "__halt__":
        return "alert_and_halt"
    if stage == "repetition":
        return "reviewer_repetition"
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
    g.add_node("reviewer_repetition", _repetition_review_node)
    g.add_node("pronoun_fix", _pronoun_fix_node)
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
        "reviewer_repetition": "reviewer_repetition",
        "alert_and_halt": "alert_and_halt",
    })
    g.add_conditional_edges("reviewer_repetition", _route_after_repetition, {
        "reviewer_repetition": "reviewer_repetition",
        "publisher": "pronoun_fix",
        "alert_and_halt": "alert_and_halt",
    })

    g.add_edge("pronoun_fix", "polish_flow")
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
