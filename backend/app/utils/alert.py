"""경보 — 콘솔 + 파일 + 텔레그램(토큰 있을 때)."""
from __future__ import annotations

from datetime import datetime, timezone
from pathlib import Path

import requests


def send_alert(message: str, settings) -> None:
    print(f"[ALERT] {message}")

    settings.logs_dir.mkdir(parents=True, exist_ok=True)
    log_path = settings.logs_dir / "alerts.log"
    with log_path.open("a", encoding="utf-8") as f:
        f.write(f"{datetime.now(timezone.utc).isoformat()} {message}\n")

    if settings.telegram_bot_token and settings.telegram_chat_id:
        try:
            requests.post(
                f"https://api.telegram.org/bot{settings.telegram_bot_token}/sendMessage",
                json={
                    "chat_id": settings.telegram_chat_id,
                    "text": f"⚠️ teamMakeBooks 경보\n\n{message}",
                },
                timeout=10,
            )
        except Exception as e:
            with log_path.open("a", encoding="utf-8") as f:
                f.write(f"{datetime.now(timezone.utc).isoformat()} [ALERT] 텔레그램 전송 실패: {e}\n")


def send_telegram(message: str, settings, *, parse_mode: str = "HTML") -> bool:
    """완료/진행 알림용. 실패해도 조용히 False 반환."""
    if not (settings.telegram_bot_token and settings.telegram_chat_id):
        return False
    try:
        r = requests.post(
            f"https://api.telegram.org/bot{settings.telegram_bot_token}/sendMessage",
            json={
                "chat_id": settings.telegram_chat_id,
                "text": message,
                "parse_mode": parse_mode,
            },
            timeout=10,
        )
        return r.ok
    except Exception:
        return False
