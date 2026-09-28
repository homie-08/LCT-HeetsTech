"""Обёртка над провайдером: кеш, проверка схемы, повторы.

Провайдеры намеренно простые — они только ходят в сеть. Всё, что должно вести
себя одинаково независимо от endpoint'а (валидация ответа, повтор с указанием
ошибки, кеширование), живёт здесь.
"""

from __future__ import annotations

import time
from typing import Any

from jsonschema import Draft202012Validator
from jsonschema import ValidationError as SchemaError

from . import cache
from .base import LLMError, LLMProvider, LLMResponse, Message


class LLMClient:
    def __init__(self, provider: LLMProvider, use_cache: bool = True, retries: int = 2,
                 budget_s: float | None = None):
        self.provider = provider
        self.use_cache = use_cache
        self.retries = retries
        # Бюджет времени на модель для одной сборки. ТЗ отводит на колоду пять
        # минут, а локальная модель на слабой машине отвечает по десять секунд:
        # без потолка десяток сокращений съедает всё. Исчерпанный бюджет — это
        # обычная ошибка модели: каждый вызывающий уже умеет жить без ответа.
        self.deadline = time.monotonic() + budget_s if budget_s else None
        self.exhausted = False

    @property
    def budget_left(self) -> float | None:
        return None if self.deadline is None else max(0.0, self.deadline - time.monotonic())

    @property
    def name(self) -> str:
        return f"{self.provider.name}/{self.provider.model}"

    def complete(self, messages: list[Message], schema: dict[str, Any],
                 schema_name: str = "result", max_tokens: int = 16000) -> LLMResponse:
        key = cache.cache_key(self.provider.name, self.provider.model, messages, schema)
        if self.use_cache and (hit := cache.load(key)) is not None:
            return hit
        if self.deadline is not None and time.monotonic() >= self.deadline:
            self.exhausted = True
            raise LLMError("бюджет времени на модель исчерпан")

        validator = Draft202012Validator(schema)
        attempt_messages = list(messages)
        last_error: Exception | None = None

        for attempt in range(self.retries + 1):
            try:
                response = self.provider.complete(attempt_messages, schema,
                                                  schema_name, max_tokens)
                validator.validate(response.data)
            except (LLMError, SchemaError) as error:
                last_error = error
                if attempt == self.retries:
                    break
                # Показываем модели её же ошибку: это заметно надёжнее, чем
                # повторять тот же запрос в надежде на другой результат.
                attempt_messages = list(messages) + [Message(
                    "user",
                    f"Предыдущий ответ не подошёл: {error}. "
                    "Верни только валидный JSON строго по схеме.")]
                continue

            if attempt:
                response.notes.append(f"понадобилось повторов: {attempt}")
            if self.use_cache:
                cache.store(key, response)
            return response

        raise LLMError(f"{self.name}: не удалось получить валидный ответ "
                       f"за {self.retries + 1} попыток ({last_error})")
