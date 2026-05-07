"""All API endpoints."""
from __future__ import annotations

import asyncio
import json
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import yaml
from fastapi import APIRouter, BackgroundTasks, HTTPException, UploadFile

from ..config import load_settings, Settings
from ..memory import load_work_meta
from ..orchestrator.pipeline import run_chapter_pipeline
from ..teams.publisher import PublisherAgent
from ..providers import get_provider

router = APIRouter()

# 백그라운드 작업 추적
_background_tasks: dict[str, dict[str, Any]] = {}
_executor = ThreadPoolExecutor(max_workers=1)


# ── 헬퍼 ────────────────────────────────────────────────────────────────────


def _get_work_dir(work_id: str, settings: Settings) -> Path:
    """작품 디렉토리 확인."""
    work_dir = settings.novels_dir / work_id
    if not work_dir.exists():
        raise HTTPException(status_code=404, detail=f"Work not found: {work_id}")
    return work_dir


def _list_chapters(work_dir: Path) -> list[dict[str, Any]]:
    """챕터 목록 스캔."""
    chapters_dir = work_dir / "chapters"
    chapters: list[dict[str, Any]] = []

    if not chapters_dir.exists():
        return chapters

    for i in range(1, 1000):
        chapter_path = chapters_dir / f"ch{i:03d}.md"
        meta_path = chapters_dir / f"ch{i:03d}_meta.json"

        if chapter_path.exists():
            meta = {}
            if meta_path.exists():
                meta = json.loads(meta_path.read_text(encoding="utf-8"))

            chapters.append({
                "chapter_n": i,
                "title": meta.get("title", f"제목 없음"),
                "status": "published" if meta else "draft",
                "created_at": meta.get("published_at", ""),
                "tags": meta.get("tags", []),
            })

    return chapters


def _run_pipeline_background(task_id: str, work_id: str, chapter_n: int, settings: Settings):
    """백그라운드에서 파이프라인 실행."""
    try:
        _background_tasks[task_id] = {"status": "running", "started_at": datetime.now(timezone.utc).isoformat()}
        result = run_chapter_pipeline(work_id, chapter_n, settings=settings)
        _background_tasks[task_id] = {
            "status": "completed" if result.success else "failed",
            "started_at": _background_tasks[task_id]["started_at"],
            "finished_at": datetime.now(timezone.utc).isoformat(),
            "result": {
                "success": result.success,
                "failure_stage": result.failure_stage,
                "failure_reason": result.failure_reason,
                "chapter_path": str(result.chapter_path) if result.chapter_path else None,
            },
        }
    except Exception as e:
        _background_tasks[task_id] = {
            "status": "error",
            "started_at": _background_tasks[task_id]["started_at"],
            "finished_at": datetime.now(timezone.utc).isoformat(),
            "error": str(e),
        }


# ── 작품 목록 / 신규 ──────────────────────────────────────────────────────────


@router.get("/works")
def list_works():
    """전체 작품 목록."""
    settings = load_settings()
    novels_dir = settings.novels_dir
    if not novels_dir.exists():
        return []

    works = []
    for entry in novels_dir.iterdir():
        if not entry.is_dir():
            continue
        meta_path = entry / "meta.json"
        if not meta_path.exists():
            continue
        try:
            meta = json.loads(meta_path.read_text(encoding="utf-8"))
        except Exception:
            continue

        chapters_dir = entry / "chapters"
        total = 0
        if chapters_dir.exists():
            total = len([f for f in chapters_dir.iterdir() if f.name.endswith("_meta.json")])

        works.append({
            "work_id": entry.name,
            "title": meta.get("title", entry.name),
            "genre": meta.get("genre", ""),
            "total_chapters": total,
            "published_chapters": meta.get("published_chapters", 0),
        })
    # 발행 화수 많은 작품이 위로 (메인 작품 우선)
    works.sort(key=lambda w: (-w["published_chapters"], w["work_id"]))
    return {"works": works}


@router.post("/works")
def create_work(title: str = None, genre: str = "general"):
    """신규 작품 생성."""
    if not title:
        raise HTTPException(status_code=400, detail="title required")

    settings = load_settings()
    work_id = title.replace(" ", "_").lower()
    # 알파벳+숫자+언더스코어만
    import re
    work_id = re.sub(r"[^a-z0-9가-힣_]", "", work_id)
    if not work_id:
        raise HTTPException(status_code=400, detail="Invalid title")

    work_dir = settings.novels_dir / work_id
    if work_dir.exists():
        raise HTTPException(status_code=409, detail=f"Work already exists: {work_id}")

    # 디렉토리 구조 생성
    (work_dir / "chapters").mkdir(parents=True)
    (work_dir / "chapter_outlines").mkdir(parents=True)
    (work_dir / "memory").mkdir(parents=True)
    (work_dir / "authors").mkdir(parents=True)

    # meta.json
    meta = {
        "work_id": work_id,
        "title": title,
        "genre": genre,
        "author_id": "",
        "is_ai_persona": True,
        "copyright": f"© {datetime.now().year} teamMakeBooks",
        "published_chapters": 0,
    }
    (work_dir / "meta.json").write_text(json.dumps(meta, ensure_ascii=False, indent=2), encoding="utf-8")

    # 기본 파일 템플릿
    (work_dir / "world_bible.md").write_text(f"# {title} — 세계관\n\n여기에 세계관을 작성하세요.\n", encoding="utf-8")
    (work_dir / "characters.md").write_text(f"# {title} — 등장인물\n\n여기에 등장인물을 작성하세요.\n", encoding="utf-8")
    (work_dir / "plot_outline.md").write_text(f"# {title} — 플롯 개요\n\n여기에 전체 플롯을 작성하세요.\n", encoding="utf-8")
    (work_dir / "naming_table.md").write_text(f"# {title} — 호칭표\n\n여기에 인물 간 호칭을 정의하세요.\n", encoding="utf-8")
    (work_dir / "theme.md").write_text(f"# {title} — 테마/약속\n\n여기에 작품 테마와 지켜야 할 약속을 작성하세요.\n", encoding="utf-8")
    (work_dir / "memory" / "character_state.md").write_text("", encoding="utf-8")
    (work_dir / "memory" / "world_state.md").write_text("", encoding="utf-8")
    (work_dir / "memory" / "event_log.md").write_text("", encoding="utf-8")
    (work_dir / "memory" / "unresolved_threads.md").write_text("", encoding="utf-8")

    return {"status": "ok", "work_id": work_id, "title": title}


# ── 사전 준비 데이터 ──────────────────────────────────────────────────────────


@router.get("/works/{work_id}/prep/{doc_name}")
def get_prep_doc(work_id: str, doc_name: str):
    """사전 준비 문서 읽기 (world_bible, characters, plot_outline, naming_table, theme)."""
    valid_docs = ["world_bible", "characters", "plot_outline", "naming_table", "theme"]
    if doc_name not in valid_docs:
        raise HTTPException(status_code=400, detail=f"Invalid doc: {doc_name}. Valid: {valid_docs}")

    settings = load_settings()
    work_dir = _get_work_dir(work_id, settings)
    extensions = {"world_bible": "md", "characters": "md", "plot_outline": "md", "naming_table": "md", "theme": "md"}
    ext = extensions[doc_name]
    doc_path = work_dir / f"{doc_name}.{ext}"

    if not doc_path.exists():
        return {"doc_name": doc_name, "content": ""}

    return {"doc_name": doc_name, "content": doc_path.read_text(encoding="utf-8")}


@router.put("/works/{work_id}/prep/{doc_name}")
def update_prep_doc(work_id: str, doc_name: str, content: str = None):
    """사전 준비 문서 수정."""
    if content is None:
        raise HTTPException(status_code=400, detail="content required")

    valid_docs = ["world_bible", "characters", "plot_outline", "naming_table", "theme"]
    if doc_name not in valid_docs:
        raise HTTPException(status_code=400, detail=f"Invalid doc: {doc_name}")

    settings = load_settings()
    work_dir = _get_work_dir(work_id, settings)
    doc_path = work_dir / f"{doc_name}.md"
    doc_path.write_text(content, encoding="utf-8")
    return {"status": "ok"}


# ── 요약 / 검증 ─────────────────────────────────────────────────────────────────


@router.get("/works/{work_id}/summaries")
def get_all_summaries(work_id: str):
    """전체 챕터 요약 목록."""
    settings = load_settings()
    work_dir = _get_work_dir(work_id, settings)
    chapters_dir = work_dir / "chapters"
    if not chapters_dir.exists():
        return {"summaries": []}

    summaries = []
    for f in sorted(chapters_dir.iterdir()):
        if not f.name.endswith("_summary.md"):
            continue
        n = int(f.name.replace("_summary.md", "").replace("ch", ""))
        try:
            content = f.read_text(encoding="utf-8").strip()
            # 첫 줄만 반환 (전체 로딩 방지)
            first_line = content.split("\n")[0] if content else ""
            summaries.append({"chapter_n": n, "preview": first_line[:100]})
        except Exception:
            summaries.append({"chapter_n": n, "preview": "(읽기 실패)"})

    return {"summaries": summaries}


@router.get("/works/{work_id}/validate")
def validate_work(work_id: str):
    """전체 파이프라인 검증 — 연속성, 캐릭터 일관성, 설정 충돌."""
    settings = load_settings()
    work_dir = _get_work_dir(work_id, settings)
    chapters_dir = work_dir / "chapters"
    if not chapters_dir.exists():
        return {"work_id": work_id, "issues": [], "warnings": []}

    issues = []
    warnings = []

    # 1. 메타 파일 누락 확인
    for i in range(1, 1000):
        chapter_path = chapters_dir / f"ch{i:03d}.md"
        meta_path = chapters_dir / f"ch{i:03d}_meta.json"
        summary_path = chapters_dir / f"ch{i:03d}_summary.md"

        if not chapter_path.exists():
            break  # 마지막 챕터
        if not meta_path.exists():
            issues.append({"type": "missing_meta", "chapter": i, "msg": f"ch{i:03d} 메타 파일 없음"})
        if not summary_path.exists():
            warnings.append({"type": "missing_summary", "chapter": i, "msg": f"ch{i:03d} 요약 파일 없음"})

    # 2. 아웃라인 누락 확인
    outlines_dir = work_dir / "chapter_outlines"
    if outlines_dir.exists():
        for i in range(1, 1000):
            if not (chapters_dir / f"ch{i:03d}.md").exists():
                break
            if not (outlines_dir / f"ch{i:03d}.yaml").exists():
                issues.append({"type": "missing_outline", "chapter": i, "msg": f"ch{i:03d} 아웃라인 없음"})

    # 3. 사전 준비 문서 존재 확인
    prep_docs = ["world_bible.md", "characters.md", "plot_outline.md", "naming_table.md"]
    for doc in prep_docs:
        if not (work_dir / doc).exists():
            warnings.append({"type": "missing_prep", "msg": f"{doc} 없음"})
        elif (work_dir / doc).stat().st_size < 50:
            warnings.append({"type": "empty_prep", "msg": f"{doc} 내용 부족"})

    return {
        "work_id": work_id,
        "total_chapters": len([f for f in chapters_dir.iterdir() if f.name.endswith(".md") and not f.name.endswith("_summary.md")]),
        "issues": issues,
        "warnings": warnings,
        "passed": len(issues) == 0,
    }


# ── 작품/챕터 ────────────────────────────────────────────────────────────────


@router.get("/works/{work_id}")
def get_work(work_id: str):
    """작품 메타 + 챕터 통계."""
    settings = load_settings()
    work_dir = _get_work_dir(work_id, settings)
    meta = load_work_meta(work_id, settings.novels_dir)

    chapters = _list_chapters(work_dir)
    published_count = sum(1 for c in chapters if c["status"] == "published")

    return {
        "work_id": work_id,
        "meta": meta,
        "stats": {
            "total_chapters": len(chapters),
            "published_chapters": published_count,
            "draft_chapters": len(chapters) - published_count,
        },
    }


@router.get("/works/{work_id}/chapters")
def list_chapters(work_id: str):
    """챕터 목록."""
    settings = load_settings()
    work_dir = _get_work_dir(work_id, settings)
    chapters = _list_chapters(work_dir)
    return {"chapters": chapters}


@router.get("/works/{work_id}/chapters/{n:int}")
def get_chapter(work_id: str, n: int):
    """챕터 상세 (본문, 메타, 검수 리포트)."""
    settings = load_settings()
    work_dir = _get_work_dir(work_id, settings)
    chapters_dir = work_dir / "chapters"

    chapter_path = chapters_dir / f"ch{n:03d}.md"
    meta_path = chapters_dir / f"ch{n:03d}_meta.json"
    summary_path = chapters_dir / f"ch{n:03d}_summary.md"

    if not chapter_path.exists():
        raise HTTPException(status_code=404, detail=f"Chapter {n} not found")

    content = chapter_path.read_text(encoding="utf-8")
    meta = json.loads(meta_path.read_text(encoding="utf-8")) if meta_path.exists() else {}
    summary = summary_path.read_text(encoding="utf-8") if summary_path.exists() else None

    # 검수 리포트는 로그 파일에서 찾기 (구현 생략)
    return {
        "chapter_n": n,
        "content": content,
        "meta": meta,
        "summary": summary,
        "review_report": None,
    }


@router.put("/works/{work_id}/chapters/{n:int}")
def update_chapter(work_id: str, n: int, content: str = None):
    """챕터 본문 수정."""
    if content is None:
        raise HTTPException(status_code=400, detail="content required")

    settings = load_settings()
    work_dir = _get_work_dir(work_id, settings)
    chapter_path = work_dir / "chapters" / f"ch{n:03d}.md"

    if not chapter_path.exists():
        raise HTTPException(status_code=404, detail=f"Chapter {n} not found")

    chapter_path.write_text(content, encoding="utf-8")
    return {"status": "ok"}


# ── 파이프라인 ─────────────────────────────────────────────────────────────────


@router.post("/works/{work_id}/chapters/{n:int}/generate")
def generate_chapter(work_id: str, n: int, background_tasks: BackgroundTasks):
    """단일 챕터 생성 (백그라운드)."""
    settings = load_settings()
    work_dir = _get_work_dir(work_id, settings)

    # 아웃라인 확인
    outline_path = work_dir / "chapter_outlines" / f"ch{n:03d}.yaml"
    if not outline_path.exists():
        raise HTTPException(status_code=400, detail=f"Chapter outline for {n} not found")

    task_id = f"{work_id}_ch{n:03d}_{int(datetime.now(timezone.utc).timestamp())}"
    background_tasks.add_task(_run_pipeline_background, task_id, work_id, n, settings)

    return {"task_id": task_id, "status": "queued"}


@router.post("/works/{work_id}/batch-generate")
def batch_generate(work_id: str, start: int, end: int, background_tasks: BackgroundTasks):
    """범위 생성 (백그라운드)."""
    if start > end or end - start > 50:
        raise HTTPException(status_code=400, detail="Invalid range (max 50 chapters)")

    settings = load_settings()
    work_dir = _get_work_dir(work_id, settings)

    # 아웃라인 확인
    missing = []
    for i in range(start, end + 1):
        if not (work_dir / "chapter_outlines" / f"ch{i:03d}.yaml").exists():
            missing.append(i)

    if missing:
        raise HTTPException(status_code=400, detail=f"Missing outlines: {missing}")

    task_id = f"{work_id}_batch_{start}-{end}_{int(datetime.now(timezone.utc).timestamp())}"

    def _run_batch():
        results = []
        for i in range(start, end + 1):
            _background_tasks[task_id] = {"status": "running", "current": i, "total": end - start + 1}
            result = run_chapter_pipeline(work_id, i, settings=settings)
            results.append({"chapter_n": i, "success": result.success})
        _background_tasks[task_id] = {"status": "completed", "results": results}

    background_tasks.add_task(_run_batch)
    return {"task_id": task_id, "status": "queued", "count": end - start + 1}


@router.get("/works/{work_id}/pipeline/status")
def get_pipeline_status(work_id: str):
    """현재 파이프라인 상태."""
    # 이 작품과 관련된 작업 필터
    tasks = {k: v for k, v in _background_tasks.items() if k.startswith(work_id)}
    return {"tasks": tasks}


# ── 스케줄 ───────────────────────────────────────────────────────────────────────


@router.get("/works/{work_id}/schedule")
def get_schedule(work_id: str):
    """현재 스케줄 + 다음 자동 실행 시각 (KST)."""
    from dataclasses import asdict

    from ..scheduler import compute_next_run, get_next_chapter_n, load_schedule

    settings = load_settings()
    work_dir = _get_work_dir(work_id, settings)  # 존재 검증
    sch = load_schedule(work_id, settings.novels_dir)
    next_run = compute_next_run(sch)
    next_n = get_next_chapter_n(work_id, settings.novels_dir)
    return {
        "work_id": work_id,
        "schedule": asdict(sch),
        "next_run_at": next_run.isoformat() if next_run else None,
        "next_chapter_n": next_n,
    }


@router.put("/works/{work_id}/schedule")
def set_schedule(
    work_id: str,
    enabled: bool = True,
    frequency: str = "daily",
    hour: int = 9,
    minute: int = 0,
    batch_size: int = 1,
):
    """스케줄 변경. frequency: daily | hourly | weekly | manual."""
    from dataclasses import asdict

    from ..scheduler import Schedule, compute_next_run, load_schedule, save_schedule

    if frequency not in ("daily", "hourly", "weekly", "manual"):
        raise HTTPException(status_code=400, detail=f"Invalid frequency: {frequency}")
    if not (0 <= hour <= 23) or not (0 <= minute <= 59):
        raise HTTPException(status_code=400, detail="hour 0~23, minute 0~59")
    if not (1 <= batch_size <= 20):
        raise HTTPException(status_code=400, detail="batch_size 1~20")

    settings = load_settings()
    _ = _get_work_dir(work_id, settings)
    cur = load_schedule(work_id, settings.novels_dir)
    new_sch = Schedule(
        enabled=enabled,
        frequency=frequency,  # type: ignore
        hour=hour, minute=minute, batch_size=batch_size,
        paused=cur.paused,
        last_run_at=cur.last_run_at,
        last_published_n=cur.last_published_n,
        last_status=cur.last_status,
        last_error=cur.last_error,
    )
    save_schedule(work_id, settings.novels_dir, new_sch)
    next_run = compute_next_run(new_sch)
    return {
        "status": "ok",
        "schedule": asdict(new_sch),
        "next_run_at": next_run.isoformat() if next_run else None,
    }


@router.post("/works/{work_id}/schedule/pause")
def pause_schedule(work_id: str):
    from ..scheduler import load_schedule, save_schedule

    settings = load_settings()
    _ = _get_work_dir(work_id, settings)
    sch = load_schedule(work_id, settings.novels_dir)
    sch.paused = True
    save_schedule(work_id, settings.novels_dir, sch)
    return {"status": "ok", "paused": True}


@router.post("/works/{work_id}/schedule/resume")
def resume_schedule(work_id: str):
    from ..scheduler import load_schedule, save_schedule

    settings = load_settings()
    _ = _get_work_dir(work_id, settings)
    sch = load_schedule(work_id, settings.novels_dir)
    sch.paused = False
    save_schedule(work_id, settings.novels_dir, sch)
    return {"status": "ok", "paused": False}


@router.post("/works/{work_id}/schedule/run-now")
def run_schedule_now(work_id: str, background_tasks: BackgroundTasks, batch_size: int = 0):
    """즉시 실행 — 현재 batch_size(또는 인자) 만큼 회차 발행을 background로 트리거."""
    from ..scheduler import get_next_chapter_n, load_schedule

    settings = load_settings()
    _ = _get_work_dir(work_id, settings)
    sch = load_schedule(work_id, settings.novels_dir)
    n_chapters = batch_size if batch_size > 0 else sch.batch_size
    start_n = get_next_chapter_n(work_id, settings.novels_dir)

    task_id = f"{work_id}_schedule_run_{datetime.now(timezone.utc).strftime('%y%m%dT%H%M%S')}"
    _background_tasks[task_id] = {
        "work_id": work_id,
        "kind": "schedule_run",
        "started_at": datetime.now(timezone.utc).isoformat(),
        "status": "running",
        "from_chapter": start_n,
        "to_chapter": start_n + n_chapters - 1,
    }

    def _runner():
        try:
            from ..orchestrator import run_chapter_pipeline
            for n in range(start_n, start_n + n_chapters):
                run_chapter_pipeline(work_id=work_id, chapter_n=n, settings=settings)
            _background_tasks[task_id]["status"] = "ok"
        except Exception as e:
            _background_tasks[task_id]["status"] = "failed"
            _background_tasks[task_id]["error"] = str(e)

    background_tasks.add_task(_runner)
    return {"task_id": task_id, "from_chapter": start_n, "to_chapter": start_n + n_chapters - 1}


# ── 모델 ───────────────────────────────────────────────────────────────────────


@router.get("/models")
def list_models():
    """ollama 모델 목록 + 현재 모델."""
    settings = load_settings()

    # ollama API 호출
    try:
        import requests
        resp = requests.get(f"{settings.ollama_base_url}/api/tags", timeout=5)
        resp.raise_for_status()
        data = resp.json()
        models = [m["name"] for m in data.get("models", [])]
    except Exception:
        models = []

    return {
        "available": models,
        "current": {
            "writer": settings.model_key("writer"),
            "direction": settings.model_key("reviewer", "direction"),
            "character": settings.model_key("reviewer", "character"),
            "quality": settings.model_key("reviewer", "quality"),
            "publisher": settings.model_key("publisher"),
        },
    }


@router.put("/models")
def update_model(role: str, model: str):
    """모델 변경 (config.yaml 수정)."""
    valid_roles = ["writer", "direction", "character", "quality", "publisher"]
    if role not in valid_roles:
        raise HTTPException(status_code=400, detail=f"Invalid role: {role}")

    settings = load_settings()
    config_path = settings.project_root / "config.yaml"
    config = yaml.safe_load(config_path.read_text(encoding="utf-8"))

    # 역할에 따라 경로 다름
    if role == "writer":
        config["teams"]["writer"]["model"] = model
    else:
        config["teams"]["reviewer"][role]["model"] = model

    config_path.write_text(yaml.dump(config, allow_unicode=True), encoding="utf-8")
    return {"status": "ok"}


@router.post("/models/test")
def test_model(work_id: str, chapter_n: int, model: str, background_tasks: BackgroundTasks):
    """테스트 생성 (파이프라인 1회 실행 후 결과 반환)."""
    settings = load_settings()
    work_dir = _get_work_dir(work_id, settings)

    # 임시로 모델 오버라이드
    task_id = f"test_{work_id}_ch{chapter_n:03d}_{int(datetime.now(timezone.utc).timestamp())}"

    def _run_test():
        # TODO: 모델 오버라이드 로직 필요
        result = run_chapter_pipeline(work_id, chapter_n, settings=settings)
        _background_tasks[task_id] = {
            "status": "completed",
            "result": {
                "success": result.success,
                "chapter_path": str(result.chapter_path) if result.chapter_path else None,
            },
        }

    background_tasks.add_task(_run_test)
    return {"task_id": task_id, "status": "queued"}


# ── 설정 ───────────────────────────────────────────────────────────────────────


@router.get("/config")
def get_config():
    """config.yaml 반환."""
    settings = load_settings()
    return settings.config


@router.put("/config")
def update_config(config: dict = None):
    """config.yaml 수정."""
    if config is None:
        raise HTTPException(status_code=400, detail="config required")

    settings = load_settings()
    config_path = settings.project_root / "config.yaml"
    config_path.write_text(yaml.dump(config, allow_unicode=True), encoding="utf-8")
    return {"status": "ok"}


# ── 검수/발행 ───────────────────────────────────────────────────────────────────


@router.get("/works/{work_id}/reviews/{n:int}")
def get_review(work_id: str, n: int):
    """검수 리포트."""
    settings = load_settings()
    work_dir = _get_work_dir(work_id, settings)
    meta_path = work_dir / "chapters" / f"ch{n:03d}_meta.json"

    if not meta_path.exists():
        raise HTTPException(status_code=404, detail=f"Chapter {n} not found")

    meta = json.loads(meta_path.read_text(encoding="utf-8"))
    # TODO: 실제 검수 리포트 파일에서 읽기
    return {"chapter_n": n, "review_history": meta.get("review_history", [])}


@router.post("/works/{work_id}/publish/{n:int}")
def publish_chapter(work_id: str, n: int):
    """텔레그램 수동 발행."""
    settings = load_settings()
    work_dir = _get_work_dir(work_id, settings)

    chapter_path = work_dir / "chapters" / f"ch{n:03d}.md"
    if not chapter_path.exists():
        raise HTTPException(status_code=404, detail=f"Chapter {n} not found")

    # TODO: telegram 발행 로직 연동
    return {"status": "ok", "message": "Telegram publish not implemented yet"}
