"""Кеш ответов модели.

На хакатоне это не оптимизация, а страховка: демонстрация не должна зависеть от
доступности endpoint'а, а повторный прогон того же контента обязан давать тот же
результат. Ключ — хеш от провайдера, модели, сообщений и схемы.
"""

from __future__ import annotations

import hashlib
import json
from pathlib import Path
from typing import Any

from .base import LLMResponse, Message

CACHE_DIR = Path(__file__).resolve().parents[3] / ".cache" / "llm"


def cache_key(provider: str, model: str, messages: list[Message],
              schema: dict[str, Any]) -> str:
    payload = json.dumps({
        "provider": provider,
        "model": model,
        "messages": [(m.role, m.content) for m in messages],
        "schema": schema,
    }, ensure_ascii=False, sort_keys=True)
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()[:32]


def load(key: str) -> LLMResponse | None:
    path = CACHE_DIR / f"{key}.json"
    if not path.exists():
        return None
    try:
        stored = json.loads(path.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, OSError):
        return None
    return LLMResponse(
        data=stored["data"],
        raw_text=stored.get("raw_text", ""),
        model=stored.get("model", ""),
        provider=stored.get("provider", ""),
        from_cache=True,
        usage=stored.get("usage", {}),
        notes=stored.get("notes", []),
    )


def store(key: str, response: LLMResponse) -> None:
    CACHE_DIR.mkdir(parents=True, exist_ok=True)
    payload = {
        "data": response.data,
        "raw_text": response.raw_text,
        "model": response.model,
        "provider": response.provider,
        "usage": response.usage,
        "notes": response.notes,
    }
    (CACHE_DIR / f"{key}.json").write_text(
        json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
