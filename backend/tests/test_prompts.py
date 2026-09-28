"""Промпты агентов — отдельными версионируемыми файлами, а не в коде.

Требование ТЗ: конфиги скиллов и агентов лежат в репозитории отдельными
файлами. Здесь закреплено, что код их только загружает, что у каждого есть
версия, что версии доезжают до отчёта — и что бюджет времени на модель
действительно останавливает запросы.
"""

from __future__ import annotations

import re
import time
from pathlib import Path

import pytest

from sd.llm import prompts
from sd.llm.base import LLMError, LLMResponse, system, user
from sd.llm.client import LLMClient

ROOT = Path(__file__).resolve().parents[1]
CODE = ROOT / "sd"


def test_every_prompt_has_an_id_version_and_body():
    found = prompts.catalogue()
    assert {prompt.id for prompt in found} >= {"planner", "shortener", "shortener-batch"}
    for prompt in found:
        assert prompt.version >= 1
        assert len(prompt.text) > 100, f"{prompt.id}: тело промпта пустое"
        assert prompt.schema, f"{prompt.id}: не указана схема ответа"


def test_prompts_are_not_embedded_in_code():
    """Ни одной многострочной константы с текстом промпта в модулях."""
    offenders = []
    for path in CODE.rglob("*.py"):
        source = path.read_text(encoding="utf-8")
        if re.search(r'^[A-Z_]*PROMPT[A-Z_]*\s*=\s*"""', source, re.M):
            offenders.append(path.relative_to(ROOT).as_posix())
    assert not offenders, offenders


def test_planner_and_shortener_read_their_prompts():
    from sd.fit import shorten
    from sd.plan import storyline

    assert prompts.load(storyline.PROMPT).id == "planner"
    assert prompts.load(shorten.PROMPT).id == "shortener"
    assert prompts.load(shorten.BATCH_PROMPT_ID).id == "shortener-batch"


def test_missing_prompt_is_an_error_not_a_silent_blank(tmp_path: Path):
    prompts.load.cache_clear()
    with pytest.raises(prompts.PromptError):
        prompts.load("нет-такого", tmp_path)


def test_frontmatter_is_validated(tmp_path: Path):
    (tmp_path / "broken.md").write_text("---\nid: other\nversion: 2\n---\nтекст\n", encoding="utf-8")
    prompts.load.cache_clear()
    with pytest.raises(prompts.PromptError):
        prompts.load("broken", tmp_path)
    (tmp_path / "bare.md").write_text("просто текст без шапки\n", encoding="utf-8")
    with pytest.raises(prompts.PromptError):
        prompts.load("bare", tmp_path)


def test_versions_reach_the_deck_report():
    from sd.qa.model import DeckReport

    report = DeckReport(skills=prompts.versions())
    assert report.skills.get("planner", 0) >= 4


# --- бюджет времени -----------------------------------------------------------

class _SlowProvider:
    name = "fake"
    model = "fake-1"

    def __init__(self) -> None:
        self.calls = 0

    def available(self) -> bool:
        return True

    def complete(self, messages, schema, schema_name="result", max_tokens=16000):
        self.calls += 1
        time.sleep(0.05)
        return LLMResponse(data={"ok": True})


def test_budget_stops_further_requests_and_is_reported():
    provider = _SlowProvider()
    client = LLMClient(provider, use_cache=False, budget_s=0.08)   # type: ignore[arg-type]
    request = [system("s"), user("u")]
    schema = {"type": "object"}
    client.complete(request, schema)                    # первый успевает
    time.sleep(0.05)
    with pytest.raises(LLMError):
        client.complete(request, schema)                # второй — уже за бюджетом
    assert client.exhausted and provider.calls == 1


def test_no_budget_means_no_deadline():
    client = LLMClient(_SlowProvider(), use_cache=False)  # type: ignore[arg-type]
    assert client.deadline is None and client.budget_left is None
