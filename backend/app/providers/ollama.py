"""Ollama provider — 직접 HTTP 호출.

langchain-ollama 1.1.0 호환성 이슈로 직접 requests 사용.
LangGraph 그래프 노드 내에서는 LLMProvider 인터페이스로 추상화되어 LangChain 종속성 없이도 정상 동작.
"""
from __future__ import annotations

import time
from typing import Any

import requests

from .base import LLMProvider, LLMProviderError, LLMResponse


class OllamaProvider(LLMProvider):
    def __init__(self, model_id: str, base_url: str, *, timeout: int = 1800):
        self._model_id = model_id
        self._base_url = base_url.rstrip("/")
        self._timeout = timeout

    @property
    def model_id(self) -> str:
        return self._model_id

    def complete(
        self,
        prompt: str,
        *,
        max_tokens: int = 4096,
        temperature: float = 0.8,
        format_schema: dict[str, Any] | None = None,
    ) -> LLMResponse:
        body: dict[str, Any] = {
            "model": self._model_id,
            "prompt": prompt,
            "stream": False,
            "options": {
                "temperature": temperature,
                "num_predict": max_tokens,
                # gemma4 계열은 128k 컨텍스트 지원. 기본 4096이라 long prompt에서 빈 응답 발생.
                # 32k로 충분 (4기둥 + 본문 + 학습 예시 합계 약 15k 토큰 이내).
                "num_ctx": 32768,
            },
        }
        if format_schema is not None:
            body["format"] = format_schema

        t0 = time.time()
        last_err: Exception | None = None
        for attempt in range(1, 4):  # 최대 3회 재시도 (transient connection reset 대비)
            try:
                resp = requests.post(
                    f"{self._base_url}/api/generate", json=body, timeout=self._timeout
                )
                resp.raise_for_status()
                data = resp.json()
                return LLMResponse(
                    text=data.get("response", ""),
                    input_tokens=int(data.get("prompt_eval_count", 0)),
                    output_tokens=int(data.get("eval_count", 0)),
                    duration_ms=int((time.time() - t0) * 1000),
                    model_id=self._model_id,
                )
            except requests.RequestException as e:
                last_err = e
                # ConnectionReset / 짧은 SocketError 같은 transient — 잠시 대기 후 재시도
                wait = 5 * attempt
                print(f"  [ollama] 호출 실패 (시도 {attempt}/3): {e} — {wait}초 대기 후 재시도", flush=True)
                time.sleep(wait)

        raise LLMProviderError(f"ollama 호출 3회 모두 실패: {last_err}")
