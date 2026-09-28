"""Выбор провайдера по конфигурации.

Правило кейса — «переключение на API организаторов должно быть правкой одной
строки в .env, не кода». Поэтому весь выбор сосредоточен здесь и опирается
только на переменные окружения.
"""

from __future__ import annotations

import os
from pathlib import Path

from .base import LLMProvider
from .client import LLMClient
from .providers.openai_compatible import OpenAICompatibleProvider
from .providers.stub import StubProvider

ENV_FILE = Path(__file__).resolve().parents[3] / ".env"


def load_env(path: Path = ENV_FILE) -> dict[str, str]:
    """Читает `.env`, не затирая уже заданные переменные окружения."""
    values: dict[str, str] = {}
    if path.exists():
        for line in path.read_text(encoding="utf-8").splitlines():
            line = line.strip()
            if not line or line.startswith("#") or "=" not in line:
                continue
            key, _, value = line.partition("=")
            values[key.strip()] = value.strip().strip('"').strip("'")
    for key, value in values.items():
        os.environ.setdefault(key, value)
    return values


def build_provider(prefer: str | None = None) -> LLMProvider:
    """Возвращает провайдера: явный выбор, иначе OpenAI-совместимый, иначе заглушка.

    Только открытые веса: по условиям кейса модели с закрытыми весами
    использовать нельзя, поэтому провайдер здесь один — OpenAI-совместимый
    endpoint, за которым стоит Ollama, vLLM или Inference API организаторов.
    """
    load_env()
    choice = (prefer or os.environ.get("SD_LLM_PROVIDER", "")).strip().lower()

    def openai_provider() -> OpenAICompatibleProvider:
        return OpenAICompatibleProvider(
            base_url=os.environ.get("SD_LLM_BASE_URL", ""),
            api_key=os.environ.get("SD_LLM_API_KEY", ""),
            model=os.environ.get("SD_LLM_MODEL", ""),
            timeout=float(os.environ.get("SD_LLM_TIMEOUT", "180")),
        )

    if choice == "stub":
        return StubProvider()
    if choice in ("openai", "openai_compatible"):
        return openai_provider()

    candidate = openai_provider()
    return candidate if candidate.available() else StubProvider()


# Сколько секунд одной сборки можно отдать модели. Остальное время нужно
# самой сборке, рендеру и проверкам, чтобы уложиться в пять минут по ТЗ.
DEFAULT_BUDGET_S = 150.0


def build_client(prefer: str | None = None, use_cache: bool = True,
                 budget_s: float | None = None) -> LLMClient:
    if budget_s is None:
        load_env()
        budget_s = float(os.environ.get("SD_LLM_BUDGET_S", DEFAULT_BUDGET_S))
    return LLMClient(build_provider(prefer), use_cache=use_cache, budget_s=budget_s or None)


def llm_status() -> str:
    provider = build_provider()
    if provider.name == "stub":
        return ("LLM не настроена — работаем на эвристиках. "
                "Пропишите SD_LLM_BASE_URL / SD_LLM_API_KEY / SD_LLM_MODEL в .env")
    return f"LLM: {provider.name} / {provider.model}"
