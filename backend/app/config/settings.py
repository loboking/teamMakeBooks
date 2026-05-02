"""환경설정 통합 로더 — .env + config.yaml."""
from __future__ import annotations

import os
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

import yaml
from dotenv import load_dotenv


@dataclass
class Settings:
    project_root: Path
    ollama_base_url: str
    gemini_api_key: str
    telegram_bot_token: str
    telegram_chat_id: str

    novels_dir: Path
    authors_dir: Path
    logs_dir: Path

    config: dict[str, Any] = field(default_factory=dict)

    @property
    def max_retries(self) -> int:
        return int(self.config["pipeline"]["max_retries"])

    @property
    def recent_summaries_n(self) -> int:
        return int(self.config["pipeline"]["recent_summaries_n"])

    def model_key(self, *path: str) -> str:
        node: Any = self.config["teams"]
        for key in path:
            node = node[key]
        return str(node["model"])


def load_settings(project_root: Path | None = None) -> Settings:
    """프로젝트 루트의 .env / config.yaml을 읽어 Settings 반환."""
    root = project_root or _detect_root()
    load_dotenv(root / ".env", override=False)

    cfg_path = root / "config.yaml"
    config = yaml.safe_load(cfg_path.read_text(encoding="utf-8")) if cfg_path.exists() else {}

    return Settings(
        project_root=root,
        ollama_base_url=os.getenv("OLLAMA_BASE_URL", "http://localhost:11434"),
        gemini_api_key=os.getenv("GEMINI_API_KEY", ""),
        telegram_bot_token=os.getenv("TELEGRAM_BOT_TOKEN", ""),
        telegram_chat_id=os.getenv("TELEGRAM_CHAT_ID", ""),
        novels_dir=root / os.getenv("NOVELS_DIR", "novels"),
        authors_dir=root / os.getenv("AUTHORS_DIR", "authors"),
        logs_dir=root / os.getenv("LOGS_DIR", "logs"),
        config=config,
    )


def _detect_root() -> Path:
    p = Path(__file__).resolve()
    for ancestor in [p, *p.parents]:
        if (ancestor / "config.yaml").exists() and (ancestor / "backend").exists():
            return ancestor
    return Path.cwd()
