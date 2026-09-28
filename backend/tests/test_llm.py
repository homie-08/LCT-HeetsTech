"""LLM-слой: схемы, повторы, кеш, разбор ответа.

Сети здесь нет: провайдеры подменяются, проверяется поведение обёртки.
"""

from __future__ import annotations

from typing import Any

import pytest
from jsonschema import Draft202012Validator

from sd.llm import LLMClient, LLMError, Message, user
from sd.llm.base import LLMResponse
from sd.llm.providers.openai_compatible import extract_json
from sd.llm.providers.stub import StubProvider, skeleton

SCHEMA: dict[str, Any] = {
    "type": "object",
    "properties": {
        "title": {"type": "string"},
        "slides": {
            "type": "array", "minItems": 2,
            "items": {
                "type": "object",
                "properties": {
                    "intent": {"type": "string", "enum": ["cover", "bullets"]},
                    "n": {"type": "integer", "minimum": 1},
                },
                "required": ["intent", "n"],
                "additionalProperties": False,
            },
        },
    },
    "required": ["title", "slides"],
    "additionalProperties": False,
}


class FlakyProvider:
    """Сначала отдаёт мусор, потом валидный ответ — как реальный endpoint."""

    name = "flaky"
    model = "test"

    def __init__(self, failures: int):
        self.failures = failures
        self.calls = 0

    def available(self) -> bool:
        return True

    def complete(self, messages, schema, schema_name="result", max_tokens=16000):
        self.calls += 1
        if self.calls <= self.failures:
            return LLMResponse(data={"title": 42}, provider=self.name, model=self.model)
        return LLMResponse(data={"title": "ok", "slides": [{"intent": "cover", "n": 1},
                                                           {"intent": "bullets", "n": 2}]},
                           provider=self.name, model=self.model)


def test_stub_output_satisfies_schema():
    provider = StubProvider()
    response = provider.complete([user("hi")], SCHEMA, "deck_plan")
    Draft202012Validator(SCHEMA).validate(response.data)


def test_skeleton_respects_enum_and_minimums():
    assert skeleton({"type": "string", "enum": ["a", "b"]}) == "a"
    assert skeleton({"type": "integer", "minimum": 3}) == 3
    assert len(skeleton({"type": "array", "minItems": 2, "items": {"type": "string"}})) == 2


def test_client_retries_until_valid():
    provider = FlakyProvider(failures=2)
    client = LLMClient(provider, use_cache=False, retries=2)
    response = client.complete([user("x")], SCHEMA, "deck_plan")
    assert provider.calls == 3
    assert "повторов" in " ".join(response.notes)


def test_client_gives_up_after_retries():
    provider = FlakyProvider(failures=99)
    client = LLMClient(provider, use_cache=False, retries=1)
    with pytest.raises(LLMError):
        client.complete([user("x")], SCHEMA, "deck_plan")
    assert provider.calls == 2


def test_retry_tells_the_model_what_was_wrong():
    """Повтор без объяснения ошибки — это просто ещё одна попытка наугад."""
    seen: list[list[Message]] = []

    class Recorder(FlakyProvider):
        def complete(self, messages, schema, schema_name="result", max_tokens=16000):
            seen.append(list(messages))
            return super().complete(messages, schema, schema_name, max_tokens)

    LLMClient(Recorder(failures=1), use_cache=False).complete(
        [user("x")], SCHEMA, "deck_plan")
    assert len(seen) == 2
    assert len(seen[1]) > len(seen[0])
    assert "не подошёл" in seen[1][-1].content


def test_cache_round_trip(tmp_path, monkeypatch):
    from sd.llm import cache

    monkeypatch.setattr(cache, "CACHE_DIR", tmp_path)
    provider = FlakyProvider(failures=0)
    client = LLMClient(provider, use_cache=True)

    first = client.complete([user("одинаковый запрос")], SCHEMA, "deck_plan")
    second = client.complete([user("одинаковый запрос")], SCHEMA, "deck_plan")
    assert provider.calls == 1, "второй вызов обязан прийти из кеша"
    assert second.from_cache and second.data == first.data


def test_cache_key_depends_on_schema_and_messages():
    from sd.llm import cache

    base = cache.cache_key("p", "m", [user("a")], SCHEMA)
    assert base != cache.cache_key("p", "m", [user("b")], SCHEMA)
    assert base != cache.cache_key("p", "m", [user("a")], {"type": "object"})
    assert base != cache.cache_key("other", "m", [user("a")], SCHEMA)


@pytest.mark.parametrize("text", [
    '{"a": 1}',
    '```json\n{"a": 1}\n```',
    'Вот результат:\n```\n{"a": 1}\n```\nготово',
    'Держите: {"a": 1}',
])
def test_extract_json_survives_markdown(text):
    assert extract_json(text) == {"a": 1}


def test_extract_json_reports_garbage():
    with pytest.raises(LLMError):
        extract_json("никакого json тут нет")


def test_stub_never_rewrites_slide_text():
    """Регресс: заглушка возвращала осмысленный по схеме, но пустой по смыслу текст.

    В плане это терпимо, а подставленная в слайд «text-9f2a1c» — молча
    испорченное содержание.
    """
    from sd.fit.shorten import shorten

    client = LLMClient(StubProvider(), use_cache=False)
    assert shorten("Очень длинный текст, который надо сократить" * 3, 20, client) is None


def test_factory_falls_back_to_stub(monkeypatch):
    from sd.llm import factory

    for name in ("SD_LLM_PROVIDER", "SD_LLM_BASE_URL", "SD_LLM_MODEL",
                 "SD_LLM_API_KEY", "ANTHROPIC_API_KEY"):
        monkeypatch.delenv(name, raising=False)
    monkeypatch.setattr(factory, "load_env", lambda path=None: {})
    assert factory.build_provider().name == "stub"


def test_shortener_rejects_words_in_a_foreign_script():
    """Сокращение с подменой слова английским не принимается."""
    from sd.fit.shorten import Request, _acceptable

    item = Request(id="q", text="Впервые видно, где именно документы застревают и почему",
                   limit=60)
    assert _acceptable(item, "Видно, где документы застревают и почему")
    assert not _acceptable(item, "Видно, где documents застревают и почему")
    english = Request(id="e", text="Powered by the Potok API gateway", limit=40)
    assert _acceptable(english, "Potok API gateway")
