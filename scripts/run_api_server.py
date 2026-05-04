#!/usr/bin/env python3
"""FastAPI API 서버 실행."""
from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "backend"))

import uvicorn

if __name__ == "__main__":
    uvicorn.run(
        "app.api.server:app",
        host="0.0.0.0",
        port=8001,
        reload=True,
        log_level="info",
    )
