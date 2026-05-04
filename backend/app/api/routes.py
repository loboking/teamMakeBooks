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


# ── 스케줄 (임시 구현) ───────────────────────────────────────────────────────────


@router.get("/works/{work_id}/schedule")
def get_schedule(work_id: str):
    """스케줄 상태 (TODO: 실제 스케줄러 구현 필요)."""
    return {"work_id": work_id, "enabled": False, "daily_count": 0, "paused": True}


@router.post("/works/{work_id}/schedule")
def set_schedule(work_id: str, daily_count: int, start_chapter: int):
    """스케줄 설정 (TODO: 실제 스케줄러 구현 필요)."""
    return {"status": "ok", "message": "Schedule not implemented yet"}


@router.post("/works/{work_id}/schedule/pause")
def pause_schedule(work_id: str):
    """일시정지 (TODO)."""
    return {"status": "ok"}


@router.post("/works/{work_id}/schedule/resume")
def resume_schedule(work_id: str):
    """재개 (TODO)."""
    return {"status": "ok"}


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
