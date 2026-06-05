"""모델 키 → Provider 인스턴스."""
from __future__ import annotations

from .base import LLMProvider
from .ollama import OllamaProvider


def get_provider(model_key: str, settings) -> LLMProvider:
    """
    model_key: "ollama:<name>" / "gemini:<name>"
    예: "ollama:gemma4:e2b", "gemini:gemini-2.5-pro"
    """
    if not model_key or ":" not in model_key:
        raise ValueError(f"잘못된 model_key: {model_key!r}")

    provider_name, model_name = model_key.split(":", maxsplit=1)
    if provider_name == "ollama":
        ollama_cfg = settings.config.get("ollama", {})
        return OllamaProvider(
            model_name,
            settings.ollama_base_url,
            repetition_penalty=float(ollama_cfg.get("repetition_penalty", 1.15)),
            top_p=float(ollama_cfg.get("top_p", 0.85)),
        )
    if provider_name == "gemini":
        # PoC에선 미사용. 키 들어오면 아래 분기 켜기.
        raise NotImplementedError("Gemini provider는 v0.2에서 활성화 (키 확보 후)")
    raise ValueError(f"알 수 없는 provider: {provider_name}")
