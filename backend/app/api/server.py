"""FastAPI app factory — CORS, middleware, routers."""
from __future__ import annotations

from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from .routes import router
from ..config import load_settings


@asynccontextmanager
async def lifespan(app: FastAPI):
    """앱 시작/종료 시 설정 로드."""
    # 시작 시 설정 확인
    settings = load_settings()
    print(f"[api] novels_dir: {settings.novels_dir}")
    yield
    # 종료 시 정리


def create_app() -> FastAPI:
    """FastAPI 앱 생성."""
    app = FastAPI(
        title="Novel Generator Admin API",
        version="0.1.0",
        lifespan=lifespan,
    )

    # CORS
    app.add_middleware(
        CORSMiddleware,
        allow_origins=["http://localhost:3000", "http://localhost:3001", "http://localhost:8001"],
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )

    # 라우터 등록
    app.include_router(router, prefix="/api")

    @app.get("/")
    def root():
        return {"status": "ok", "service": "novel-generator-api"}

    return app


app = create_app()
