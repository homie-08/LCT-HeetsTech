"""Реализации провайдеров.

Только открытые веса: OpenAI-совместимый endpoint (Ollama, vLLM, Inference API
организаторов) и офлайн-заглушка для тестов.
"""

from .openai_compatible import OpenAICompatibleProvider
from .stub import StubProvider

__all__ = ["OpenAICompatibleProvider", "StubProvider"]
