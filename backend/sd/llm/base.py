"""Контракт LLM-провайдера.

Один интерфейс на всех: «сообщения + JSON-схема -> валидный объект». Схема тут
не пожелание, а требование — дальше по пайплайну ответ уходит в детерминированный
код, который не должен разбирать свободный текст.

Провайдеров три: OpenAI-совместимый endpoint (под API организаторов), Anthropic
через официальный SDK и офлайн-заглушка. Ключ и base_url приходят из `.env`,
так что смена провайдера — правка конфигурации, а не кода.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Protocol, runtime_checkable


class LLMError(RuntimeError):
    """Провайдер не смог отдать валидный ответ."""


class LLMUnavailable(LLMError):
    """Провайдер не настроен — пайплайн переходит на эвристики."""


@dataclass
class Message:
    role: str          # system | user | assistant
    content: str


@dataclass
class LLMResponse:
    data: dict[str, Any]
    raw_text: str = ""
    model: str = ""
    provider: str = ""
    from_cache: bool = False
    usage: dict[str, int] = field(default_factory=dict)
    notes: list[str] = field(default_factory=list)


@runtime_checkable
class LLMProvider(Protocol):
    name: str
    model: str

    def available(self) -> bool: ...

    def complete(self, messages: list[Message], schema: dict[str, Any],
                 schema_name: str = "result", max_tokens: int = 16000) -> LLMResponse: ...


def system(text: str) -> Message:
    return Message("system", text)


def user(text: str) -> Message:
    return Message("user", text)


def render_schema_hint(schema: dict[str, Any]) -> str:
    """Схема в текст — для endpoint'ов, которые не умеют structured outputs.

    Деградация, а не основной путь: сначала пробуем нативный режим провайдера.
    """
    import json

    return ("Ответь ТОЛЬКО валидным JSON по этой JSON Schema, без markdown-обёртки "
            "и без пояснений:\n" + json.dumps(schema, ensure_ascii=False, indent=2))
