"""Сокращение текста под ёмкость слота.

Обрезка по словам — честный, но плохой запасной вариант: фраза обрывается.
Модель переписывает то же самое короче, сохраняя цифры и смысл. Лимит считается
по реальным метрикам шрифта, поэтому в промпт уходит конкретное число знаков,
а не пожелание «покороче», и результат всё равно перепроверяется измерением.
"""

from __future__ import annotations

import re
from dataclasses import dataclass

from ..llm import LLMClient, LLMError, prompts, system, user

SHORTEN_SCHEMA = {
    "type": "object",
    "properties": {"text": {"type": "string"}},
    "required": ["text"],
    "additionalProperties": False,
}

# Промпты — в prompts/shortener.md и prompts/shortener-batch.md.
PROMPT = "shortener"


def shorten(text: str, limit: int, client: LLMClient, context: str = "") -> str | None:
    """Возвращает сокращённый текст либо None, если модель не помогла."""
    if not text or limit <= 0 or len(text) <= limit:
        return None
    # Офлайн-заглушка возвращает строку, валидную по схеме, но бессмысленную.
    # Для планирования это приемлемо, для текста на слайде — нет: подстановка
    # молча испортила бы содержание.
    if getattr(client.provider, "name", "") == "stub":
        return None

    request = [system(prompts.load(PROMPT).text)]
    if context:
        request.append(user(f"Контекст слайда: {context}"))
    request.append(user(f"Лимит: {limit} символов.\n\nТекст:\n{text}"))

    try:
        response = client.complete(request, SHORTEN_SCHEMA, schema_name="shorten",
                                   max_tokens=2000)
    except LLMError:
        return None

    shortened = (response.data.get("text") or "").strip()
    if not shortened or len(shortened) >= len(text):
        return None
    return shortened


# --- пакетное сокращение -----------------------------------------------------

BATCH_SCHEMA = {
    "type": "object",
    "properties": {
        "items": {
            "type": "array",
            "items": {
                "type": "object",
                "properties": {"id": {"type": "string"}, "text": {"type": "string"}},
                "required": ["id", "text"],
                "additionalProperties": False,
            },
        },
    },
    "required": ["items"],
    "additionalProperties": False,
}

BATCH_PROMPT_ID = "shortener-batch"

NUMBER_RE = re.compile(r"\d+(?:[.,]\d+)?")


@dataclass
class Request:
    """Один фрагмент на сокращение."""

    id: str
    text: str
    limit: int
    context: str = ""


def _keeps_numbers(original: str, shortened: str) -> bool:
    """Все числа исходника должны остаться: подпись без цифры теряет смысл."""
    wanted = NUMBER_RE.findall(original)
    got = NUMBER_RE.findall(shortened)
    return all(number in got for number in wanted)


def shorten_many(requests: list[Request], client: LLMClient) -> dict[str, str]:
    """Сокращает пачку фрагментов одним запросом. Возвращает только годные.

    Один запрос вместо двадцати — не только скорость: модель видит все подписи
    слайда разом и держит их в одном регистре, а не переписывает каждую по
    отдельности. Результат проверяется по каждому фрагменту: не длиннее лимита,
    короче исходника и с сохранёнными числами. Не прошедшие проверку просто не
    возвращаются — сработает обрезка, и это будет видно в отчёте.
    """
    pending = [item for item in requests if item.text and len(item.text) > item.limit > 0]
    if not pending:
        return {}
    if getattr(client.provider, "name", "") == "stub":
        # Заглушка отдаёт валидную по схеме бессмыслицу. Для плана это годится,
        # для текста на слайде — нет.
        return {}

    lines = [f"[{item.id}] лимит {item.limit}: {item.text}" for item in pending]
    contexts = {item.context for item in pending if item.context}
    request = [system(prompts.load(BATCH_PROMPT_ID).text)]
    if contexts:
        request.append(user("Тема презентации: " + "; ".join(sorted(contexts))))
    request.append(user("\n\n".join(lines)))

    by_id = {item.id: item for item in pending}
    result: dict[str, str] = {}
    try:
        response = client.complete(request, BATCH_SCHEMA, schema_name="shorten_many",
                                   max_tokens=4000)
    except LLMError:
        response = None

    for entry in (response.data.get("items", []) if response else []):
        item = by_id.get(str(entry.get("id", "")))
        text = (entry.get("text") or "").strip()
        if item is not None and _acceptable(item, text):
            result[item.id] = text

    # Небольшие модели теряют пакет целиком: возвращают пустой список или
    # половину номеров. Оставшееся до просим поштучно — задача на один фрагмент
    # им по силам, а лишние запросы уходят только туда, где пакет не справился.
    for item in pending:
        if item.id in result:
            continue
        text = shorten(item.text, item.limit, client, item.context)
        if text and _acceptable(item, text):
            result[item.id] = text
    return result


def _acceptable(item: Request, text: str) -> bool:
    """Годен ли сокращённый вариант: короче, в лимите, с теми же числами и без
    слов на чужом алфавите — маленькая модель, сокращая русский текст, порой
    подменяет слово английским («где documents застревают»)."""
    if not text or len(text) >= len(item.text) or len(text) > item.limit:
        return False
    return _keeps_numbers(item.text, text) and _keeps_script(item.text, text)


LATIN_WORD_RE = re.compile(r"[A-Za-z]{3,}")


def _keeps_script(source: str, text: str) -> bool:
    """Латинские слова в ответе допустимы, только если были в исходнике."""
    known = {word.lower() for word in LATIN_WORD_RE.findall(source)}
    return all(word.lower() in known for word in LATIN_WORD_RE.findall(text))
