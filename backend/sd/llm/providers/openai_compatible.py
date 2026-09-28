"""Провайдер для OpenAI-совместимого endpoint'а — основной путь на защите.

Inference API организаторов почти наверняка совместим с OpenAI Chat Completions,
поэтому base_url и модель берём из `.env`. Со structured outputs у совместимых
серверов по-разному: кто-то знает `json_schema`, кто-то только `json_object`,
кто-то ничего. Поэтому здесь лестница деградации — от строгой схемы к схеме в
промпте, с проверкой результата в любом случае.
"""

from __future__ import annotations

import json
import re
from typing import Any

import httpx

from ..base import (LLMError, LLMResponse, Message, render_schema_hint)

FENCE = re.compile(r"```(?:json)?\s*(.*?)```", re.DOTALL)


def extract_json(text: str) -> dict[str, Any]:
    """Достаёт объект из ответа: модель любит обернуть JSON в markdown."""
    candidate = text.strip()
    if match := FENCE.search(candidate):
        candidate = match.group(1).strip()
    if not candidate.startswith("{"):
        start, end = candidate.find("{"), candidate.rfind("}")
        if start >= 0 and end > start:
            candidate = candidate[start:end + 1]
    try:
        parsed = json.loads(candidate)
    except json.JSONDecodeError as error:
        raise LLMError(f"ответ не разбирается как JSON: {error}") from error
    if not isinstance(parsed, dict):
        raise LLMError("ожидался объект JSON")
    return parsed


class OpenAICompatibleProvider:
    """Chat Completions по HTTP. Официального SDK здесь нет намеренно —
    endpoint чужой, а протокол простой."""

    name = "openai_compatible"

    def __init__(self, base_url: str, api_key: str, model: str,
                 timeout: float = 180.0, extra_headers: dict[str, str] | None = None):
        self.base_url = base_url.rstrip("/")
        self.api_key = api_key
        self.model = model
        self.timeout = timeout
        self.extra_headers = extra_headers or {}
        self._structured_mode: str | None = None   # что endpoint реально принял

    def available(self) -> bool:
        return bool(self.base_url and self.model)

    # --- запрос ---------------------------------------------------------

    def _payload(self, messages: list[Message], schema: dict[str, Any],
                 schema_name: str, max_tokens: int, mode: str) -> dict[str, Any]:
        body: dict[str, Any] = {
            "model": self.model,
            "messages": [{"role": m.role, "content": m.content} for m in messages],
            "max_tokens": max_tokens,
        }
        if mode == "json_schema":
            body["response_format"] = {
                "type": "json_schema",
                "json_schema": {"name": schema_name, "schema": schema, "strict": True},
            }
        elif mode == "json_object":
            body["response_format"] = {"type": "json_object"}
        return body

    def _post(self, body: dict[str, Any]) -> dict[str, Any]:
        headers = {"Content-Type": "application/json", **self.extra_headers}
        if self.api_key:
            headers["Authorization"] = f"Bearer {self.api_key}"
        with httpx.Client(timeout=self.timeout) as client:
            response = client.post(f"{self.base_url}/chat/completions",
                                   json=body, headers=headers)
        if response.status_code >= 400:
            raise LLMError(f"HTTP {response.status_code}: {response.text[:400]}")
        return response.json()

    def complete(self, messages: list[Message], schema: dict[str, Any],
                 schema_name: str = "result", max_tokens: int = 16000) -> LLMResponse:
        notes: list[str] = []
        # Лестница деградации: если сервер не знает строгий режим, спускаемся,
        # но схему всё равно проверим сами.
        modes = [self._structured_mode] if self._structured_mode else \
            ["json_schema", "json_object", "prompt"]

        last_error: Exception | None = None
        for mode in modes:
            payload_messages = list(messages)
            if mode == "prompt":
                payload_messages.append(Message("user", render_schema_hint(schema)))

            try:
                raw = self._post(self._payload(payload_messages, schema, schema_name,
                                               max_tokens, mode))
            except LLMError as error:
                last_error = error
                notes.append(f"режим {mode} отклонён endpoint'ом")
                continue

            text = raw["choices"][0]["message"]["content"] or ""
            data = extract_json(text)
            self._structured_mode = mode
            if mode != "json_schema":
                notes.append(f"endpoint не поддерживает json_schema, режим {mode}")

            usage = raw.get("usage") or {}
            return LLMResponse(
                data=data, raw_text=text, model=raw.get("model", self.model),
                provider=self.name,
                usage={k: v for k, v in usage.items() if isinstance(v, int)},
                notes=notes,
            )

        raise LLMError(f"endpoint не принял ни один режим: {last_error}")
