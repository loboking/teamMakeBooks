"""LLM Provider 추상 인터페이스."""
from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass
from typing import Any


class LLMProviderError(Exception):
    """LLM 호출 실패 (네트워크/API 오류)."""


@dataclass
class LLMResponse:
    text: str
    input_tokens: int
    output_tokens: int
    duration_ms: int
    model_id: str


class LLMProvider(ABC):
    @abstractmethod
    def complete(
        self,
        prompt: str,
        *,
        max_tokens: int = 4096,
        temperature: float = 0.8,
        format_schema: dict[str, Any] | None = None,
    ) -> LLMResponse:
        """단일 프롬프트 → 텍스트.

        format_schema: JSON Schema dict (Ollama 0.5+). None이면 일반 텍스트.
        """

    @property
    @abstractmethod
    def model_id(self) -> str: ...
