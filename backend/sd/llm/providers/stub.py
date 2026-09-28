"""Офлайн-провайдер: детерминированные ответы без сети.

Нужен для тестов и для демонстрации без ключа. Он **не** заменяет модель по
смыслу — осмысленный запасной вариант даёт эвристический планировщик в
`sd/plan`. Задача заглушки скромнее: вернуть объект, валидный по схеме, чтобы
конвейер прошёл целиком и упал не здесь.
"""

from __future__ import annotations

import hashlib
from typing import Any, Callable

from ..base import LLMResponse, Message

Handler = Callable[[list[Message], dict[str, Any]], dict[str, Any]]


def skeleton(schema: dict[str, Any], seed: str = "") -> Any:
    """Минимальный объект, удовлетворяющий схеме."""
    kind = schema.get("type")
    if "const" in schema:
        return schema["const"]
    if enum := schema.get("enum"):
        return enum[0]
    if "default" in schema:
        return schema["default"]

    if kind == "object":
        properties = schema.get("properties", {})
        required = schema.get("required", list(properties))
        return {name: skeleton(properties.get(name, {}), f"{seed}/{name}")
                for name in required}
    if kind == "array":
        count = max(1, int(schema.get("minItems", 1)))
        item_schema = schema.get("items", {})
        return [skeleton(item_schema, f"{seed}[{i}]") for i in range(count)]
    if kind == "integer":
        return int(schema.get("minimum", 1))
    if kind == "number":
        return float(schema.get("minimum", 1))
    if kind == "boolean":
        return False
    if kind == "null":
        return None
    # Строка: делаем стабильной, но различимой между полями.
    digest = hashlib.sha256(seed.encode("utf-8")).hexdigest()[:6]
    return f"{seed.rsplit('/', 1)[-1] or 'text'}-{digest}"


class StubProvider:
    name = "stub"

    def __init__(self, handlers: dict[str, Handler] | None = None,
                 model: str = "offline-stub"):
        self.handlers = handlers or {}
        self.model = model

    def available(self) -> bool:
        return True

    def complete(self, messages: list[Message], schema: dict[str, Any],
                 schema_name: str = "result", max_tokens: int = 16000) -> LLMResponse:
        handler = self.handlers.get(schema_name)
        data = handler(messages, schema) if handler else skeleton(schema, schema_name)
        return LLMResponse(data=data, model=self.model, provider=self.name,
                           notes=["офлайн-заглушка: смысловое качество не гарантируется"])
