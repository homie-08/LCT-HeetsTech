"""Сборка презентации в HTML-шаблоне: разбор, укладка, сокращение моделью."""

from __future__ import annotations

import re
from dataclasses import dataclass
from pathlib import Path

import pytest

from sd.content import parse_content
from sd.fit.shorten import Request, shorten_many
from sd.htmldeck import parse_template
from sd.htmldeck.build import build_deck
from sd.llm.base import LLMResponse
from sd.plan import build_plan

PACKAGE = Path(__file__).resolve().parents[2] / "templates" / "incoming" / "package"
CONTENT = Path(__file__).resolve().parents[2] / "data" / "content" / "pitch"
DECK = PACKAGE / "11 Neon Lime.dc.html"

pytestmark = pytest.mark.skipif(
    not DECK.exists() or not CONTENT.exists(),
    reason="нет пакета HTML-шаблонов или демо-контента")

NUMBER_RE = re.compile(r"\d+(?:[.,]\d+)?")
# Без DOTALL: точка не должна перескакивать на следующую строку, иначе все
# фрагменты запроса схлопнутся в один жадный захват.
LINE_RE = re.compile(r"^\[([^\]]+)\] лимит (\d+): (.+)$", re.MULTILINE)


def _templates() -> list[Path]:
    return sorted(path for path in PACKAGE.glob("*.dc.html")
                  if not path.name.startswith(("00 ", "our-", "deck.")))


# --- подставная модель -------------------------------------------------------

@dataclass
class _Provider:
    name: str = "fake"
    model: str = "fake-1"

    def available(self) -> bool:
        return True


class _Client:
    """Ведёт себя как исполнительная модель: короче лимита и с теми же числами.

    Настоящую сюда не подключишь — ключа в тестовом окружении нет, а проверить
    надо именно поведение конвейера: что запрос уходит один на всю колоду, что
    ответ доезжает до разметки и что негодные варианты отсекаются.
    """

    def __init__(self, override: dict[str, str] | None = None,
                 provider_name: str = "fake"):
        self.override = override or {}
        self.provider = _Provider(name=provider_name)
        self.calls = 0
        self.asked: dict[str, tuple[int, str]] = {}

    def complete(self, messages, schema, schema_name="result", max_tokens=16000):
        self.calls += 1
        payload = "\n\n".join(message.content for message in messages)
        items = []
        for identifier, limit, text in LINE_RE.findall(payload):
            self.asked[identifier] = (int(limit), text)
            if identifier in self.override:
                items.append({"id": identifier, "text": self.override[identifier]})
                continue
            numbers = " ".join(NUMBER_RE.findall(text))
            short = (f"{numbers} кратко" if numbers else "кратко")[:int(limit)]
            items.append({"id": identifier, "text": short})
        return LLMResponse(data={"items": items})


# --- разбор шаблона ----------------------------------------------------------

@pytest.mark.parametrize("path", _templates(), ids=lambda path: path.stem)
def test_every_template_parses(path):
    """Каждая колода пакета разбирается на макеты со слотами."""
    template = parse_template(path)
    assert template.width == 1920 and template.height == 1080
    assert len(template.patterns) >= 8, "макетов подозрительно мало"
    assert any(pattern.slots for pattern in template.patterns)
    assert all(pattern.label for pattern in template.patterns)


def test_repeating_cards_are_found():
    """Сетка карточек узнаётся как повторяющаяся группа."""
    template = parse_template(DECK)
    kpi = next(pattern for pattern in template.patterns if pattern.label == "Показатели")
    assert len(kpi.by_role("metric_value")) == 4
    assert len(kpi.by_role("metric_label")) == 4
    assert max(kpi.groups.values()) == 4


# --- сборка ------------------------------------------------------------------

def _build(tmp_path, client=None, reflow=False):
    template = parse_template(DECK)
    ir = parse_content(CONTENT)
    tmp_path.mkdir(parents=True, exist_ok=True)
    # Подгонка по вёрстке требует браузера и секунд на слайд. Здесь проверяется
    # укладка, а не она, — иначе каждый прогон поднимал бы Chrome.
    return build_deck(template, build_plan(ir), ir, tmp_path / "deck.dc.html",
                      client=client, reflow=reflow)


def test_template_text_does_not_leak(tmp_path):
    """Чужой текст шаблона не должен попасть в готовую колоду."""
    produced = _build(tmp_path).path.read_text(encoding="utf-8")
    for phrase in ("пористых материал", "самовозгоран", "грантовый проект"):
        assert phrase not in produced, f"в колоде остался текст шаблона: {phrase}"


def test_drawings_and_animation_survive(tmp_path):
    """Векторные элементы переносятся, анимация размечена и не мешает печати."""
    produced = _build(tmp_path).path.read_text(encoding="utf-8")
    assert produced.count("<svg") >= 5
    assert 'data-anim="card"' in produced
    assert "@media print" in produced


def test_without_model_truncation_is_reported(tmp_path):
    """Без модели обрезка остаётся, но о ней честно сказано."""
    result = _build(tmp_path)
    assert result.rewritten == 0
    assert any("обрезан" in note for slide in result.slides for note in slide.notes)
    assert any("модель не подключена" in warning for warning in result.warnings)


def test_model_removes_truncation(tmp_path):
    """Модель переписывает обрезанное, и многоточия уходят из колоды."""
    before = _build(tmp_path / "before")
    cut_before = sum(1 for slide in before.slides for note in slide.notes
                     if "обрезан" in note)
    assert cut_before, "нечего сокращать — проверка бессмысленна"

    client = _Client()
    after = _build(tmp_path / "after", client=client)

    assert client.calls == 1, "запрос к модели должен быть один на всю колоду"
    assert after.rewritten >= cut_before
    assert not any("осталось обрезанных" in warning for warning in after.warnings)

    produced = after.path.read_text(encoding="utf-8")
    assert "…</" not in produced, "в колоде остались обрывы фраз"


def test_batch_checks_answers():
    """Ответы модели проверяются: длина, сокращение и сохранность чисел."""
    requests = [
        Request(id="a", text="Срок обработки заявки составляет 6 рабочих дней", limit=20),
        Request(id="b", text="Доля ручного ввода снижается до 8 процентов", limit=20),
        Request(id="c", text="Короткая строка", limit=200),
    ]
    client = _Client(override={"a": "Срок — 6 дней",
                               "b": "Меньше ручного ввода",     # число потеряно
                               "c": "не спрашивали"})
    assert shorten_many(requests, client) == {"a": "Срок — 6 дней"}


def test_stub_provider_is_refused():
    """Офлайн-заглушка отдаёт бессмыслицу — на слайд её пускать нельзя."""
    requests = [Request(id="a", text="Очень длинная строка про сроки 6 дней", limit=10)]
    client = _Client(override={"a": "мусор"}, provider_name="stub")
    assert shorten_many(requests, client) == {}
    assert client.calls == 0
