"""Тезисы и заголовки эвристического планировщика; согласие матчера с укладчиком.

Слайд с одной строкой на весь экран — самая частая жалоба на результат. Здесь
закреплено, откуда планировщик берёт тезисы, когда их мало, и как он даёт
заголовок разделу без заголовка — а также что матчер считает место так же,
как укладчик его потом занимает.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from sd.content.model import Block
from sd.content.parse import parse_text
from sd.plan import build_plan
from sd.plan.match import UNFIT, _content_demand, score
from sd.plan.storyline import MAX_THESES, _lead_title, _theses

DATASET = Path(__file__).resolve().parents[2] / "ресурсы" / "Датасет"


def _paragraph(text: str, block_id: str = "b1") -> Block:
    return Block(id=block_id, type="paragraph", text=text)


def test_single_paragraph_section_yields_several_theses():
    """Абзац из четырёх фраз — четыре тезиса, а не один."""
    text = ("Проект занимает от восьми недель. Первые две недели уходят на обследование. "
            "Далее пилот на одном подразделении. Затем тираж на всю компанию.")
    assert len(_theses([_paragraph(text)])) == 4


def test_extra_sentences_are_taken_round_robin():
    """Второй абзац не забирает слайд себе: по одной фразе с каждого."""
    first = "Первая мысль первого абзаца. Вторая мысль первого абзаца. Третья мысль первого."
    second = "Первая мысль второго абзаца. Вторая мысль второго абзаца."
    theses = _theses([_paragraph(first), _paragraph(second, "b2")])
    assert theses[:2] == ["Первая мысль первого абзаца.", "Первая мысль второго абзаца."]
    assert theses[2] == "Вторая мысль первого абзаца."


def test_lead_in_sentences_are_not_theses():
    """«Из-за этого:» обещает список, которого на слайде нет."""
    text = "Обработка документов остаётся ручной. Из-за этого: теряются заявки и время."
    assert all(not thesis.endswith(":") for thesis in _theses([_paragraph(text)]))


def test_theses_are_capped():
    text = " ".join(f"Мысль номер {number} в этом абзаце." for number in range(1, 10))
    assert len(_theses([_paragraph(text)])) == MAX_THESES


def test_lead_title_splits_on_colon_and_dash():
    title, rest = _lead_title(["Единая среда для работы с документами: приём и контроль.", "Ещё"])
    assert title == "Единая среда для работы с документами"
    assert rest[0].startswith("Приём и контроль") and rest[1] == "Ещё"
    title, rest = _lead_title(["Ядро — сервис маршрутизации на своих правилах."])
    assert title == "Ядро" and rest == ["Сервис маршрутизации на своих правилах."]


def test_lead_title_keeps_a_short_sentence_whole():
    title, rest = _lead_title(["Обработка документов остаётся ручной.", "Второй тезис."])
    assert title == "Обработка документов остаётся ручной" and rest == ["Второй тезис."]


def test_lead_title_gives_up_on_a_long_sentence():
    long = "Очень длинное предложение " * 6 + "без зацепки."
    assert _lead_title([long]) == ("", [long])


def test_agenda_skips_document_title_and_contacts():
    text = ("# Платформа\n\n## Платформа\n\nВводный абзац о продукте.\n\n"
            "## Проблема\n\nТекст проблемы. Ещё текст.\n\n## Решение\n\nТекст решения. Ещё.\n\n"
            "## Эффект\n\nТекст эффекта. Ещё.\n\n## Внедрение\n\nПлан внедрения. Ещё.\n\n"
            "## Контакты\n\nЗвоните: +7 495 000-00-00, potok@example.com\n")
    plan = build_plan(parse_text(text), None)
    agenda = next((slide for slide in plan.slides if slide.intent == "agenda"), None)
    assert agenda is not None
    assert "Платформа" not in agenda.items and "Контакты" not in agenda.items
    assert len(agenda.items) <= MAX_THESES


def test_leftover_sentence_folds_into_the_metrics_slide():
    """Абзац на одну-две фразы после цифр не становится отдельным слайдом."""
    text = ("# Отчёт\n\n## Проблема\n\nОбработка входящих документов остаётся ручной. "
            "Оператор переносит данные из скана.\n\n"
            "- средний срок обработки заявки — 6 рабочих дней\n"
            "- 19 % заявок теряются\n- на ручной ввод уходит 34 % времени\n"
            "- аудит занимает до 2 недель\n")
    plan = build_plan(parse_text(text), None)
    metrics = [slide for slide in plan.slides if slide.intent == "metrics"]
    assert len(metrics) == 1
    assert metrics[0].key_message.startswith("Обработка входящих документов")
    assert not any(slide.intent == "bullets" and "Оператор" in " ".join(slide.items)
                   for slide in plan.slides if slide is not metrics[0])


# --- матчер -----------------------------------------------------------------

def test_demand_ignores_title_echo_and_replaced_prose():
    """Тезис, равный заголовку, и абзац, из которого выжаты тезисы, места не просят."""
    text = "# Тема\n\n## Раздел\n\nПервая фраза раздела. Вторая фраза раздела.\n"
    ir = parse_text(text)
    plan = build_plan(ir, None)
    slide = next(slide for slide in plan.slides if slide.intent == "bullets")
    slide.key_message = slide.items[0]
    blocks = [ir.block(block_id) for block_id in slide.blocks]
    _, body_chars, items = _content_demand(slide, blocks)
    assert items == len(slide.items) - 1
    assert body_chars == sum(len(item) for item in slide.items[1:])


@pytest.mark.skipif(not DATASET.exists(), reason="нет датасета организаторов")
def test_cover_only_at_the_edges_of_the_deck():
    from sd.template.analyze import analyze_template

    design = analyze_template(DATASET / "Шаблон презентации VK Education.pptx")
    ir = parse_text("# Тема\n\n## Раздел\n\nФраза. Ещё фраза. И ещё одна.\n")
    slide = build_plan(ir, None).slides[-1]
    cover = next(pattern for pattern in design.patterns if pattern.archetype == "cover")
    assert score(cover, slide, ir, position="middle").archetype == UNFIT
    assert score(cover, slide, ir, position="last").archetype > UNFIT


class _EmptyTitles:
    """Модель, которая при ограничении схемой оставляет key_message пустым."""

    name = "fake"
    model = "test"

    def available(self) -> bool:
        return True

    def complete(self, messages, schema, schema_name="result", max_tokens=16000):
        from sd.llm.client import LLMResponse
        return LLMResponse(data={"title": "", "slides": [
            {"intent": "cover", "key_message": "", "blocks": ["b1"], "items": []},
            {"intent": "bullets", "key_message": "", "blocks": ["b1"],
             "items": ["Срок обработки упал: с шести дней до полутора",
                       "Ручной ввод сократился втрое"]},
            {"intent": "contacts", "key_message": "", "blocks": [], "items": ["Спасибо"]},
        ]}, provider=self.name, model=self.model)


def test_llm_plan_without_titles_takes_them_from_the_first_thesis():
    """Пустой key_message — не пустой заголовок на слайде."""
    from sd.llm.client import LLMClient
    from sd.plan.storyline import plan_with_llm

    ir = parse_text("# Итоги квартала\n\nСрок обработки упал с шести дней до полутора. "
                    "Ручной ввод сократился втрое.")
    plan = plan_with_llm(ir, LLMClient(_EmptyTitles(), use_cache=False))
    cover, body, contacts = plan.slides
    assert cover.key_message == "Итоги квартала"
    assert body.key_message == "Срок обработки упал"
    assert body.items == ["С шести дней до полутора", "Ручной ввод сократился втрое"]
    assert contacts.key_message == "Спасибо" and contacts.items == []
    assert any("заголовок взят из первого тезиса" in note for note in plan.warnings)


def test_short_prompt_is_a_brief_and_a_content_pack_is_not():
    from sd.plan.storyline import is_brief

    assert is_brief(parse_text("Итоги квартала команды поддержки: время ответа и отток"))
    long = parse_text("# Отчёт\n\n" + " ".join(["Слово"] * 200))
    assert not is_brief(long)
    with_data = parse_text("# Отчёт\n\n| Показатель | Было | Стало |\n|---|---|---|\n| Срок | 6 | 1 |")
    assert not is_brief(with_data)


def test_authored_plan_loses_invented_numbers_contacts_and_duplicates():
    from sd.plan.model import SlidePlan
    from sd.plan.storyline import _tidy_authored

    brief = "Итоги квартала: отток 4 %, план на следующий квартал"
    slides = [
        SlidePlan(n=1, intent="cover", key_message="Итоги квартала"),
        SlidePlan(n=2, intent="metrics", key_message="Время ответа сократилось на 15 %",
                  items=["Среднее время ответа — 1,5 часа", "Отток остался на уровне 4 %",
                         "Нагрузка вырастет в 3 квартале", "Пилот с 100 клиентами в июле"]),
        SlidePlan(n=3, intent="section", key_message=""),
        SlidePlan(n=4, intent="bullets", key_message="Время ответа сократилось на 15 %",
                  items=["Шаблоны ответов внедрены: очередь короче", "Обучение проведено"]),
        SlidePlan(n=5, intent="agenda", key_message="Планы", items=["Обучение", "Автоматизация", "Мониторинг"]),
        SlidePlan(n=6, intent="contacts", key_message="Ирина Смирнова", items=["support@example.com"]),
    ]
    warnings: list[str] = []
    _tidy_authored(slides, brief, warnings)

    assert [slide.intent for slide in slides] == ["cover", "metrics", "section", "bullets", "bullets"]
    metrics = slides[1]
    assert metrics.key_message == "Время ответа сократилось"          # число не из брифа
    # Число в конце отрезано, число из брифа осталось, фразы с числом в
    # середине убраны целиком — их без числа не прочитать.
    assert metrics.items == ["Среднее время ответа", "Отток остался на уровне 4 %"]
    assert slides[2].key_message == "Шаблоны ответов внедрены"           # разделитель взял следующий
    assert slides[3].key_message == "Шаблоны ответов внедрены"           # повтор → первый тезис
    assert slides[3].items == ["Очередь короче", "Обучение проведено"]
    assert [slide.n for slide in slides] == [1, 2, 3, 4, 5]
    assert any("выдуманных чисел" in note for note in warnings)
    assert any("контактами убран" in note for note in warnings)


def test_authored_slides_do_not_repeat_the_cover_title():
    from sd.plan.model import SlidePlan
    from sd.plan.storyline import _tidy_authored

    slides = [
        SlidePlan(n=1, intent="cover", key_message="Чат-бот поддержки"),
        SlidePlan(n=2, intent="bullets", key_message="Чат-бот поддержки",
                  items=["Типовые вопросы отнимают время специалистов", "Очередь растёт"]),
        SlidePlan(n=3, intent="section", key_message="Чат-бот поддержки"),
        SlidePlan(n=4, intent="bullets", key_message="Бот отвечает на типовые вопросы сам",
                  items=["Статус заявки", "Оплата"]),
    ]
    _tidy_authored(slides, "Чат-бот поддержки", [])
    assert [slide.key_message for slide in slides] == [
        "Чат-бот поддержки", "Типовые вопросы отнимают время специалистов",
        "Бот отвечает на типовые вопросы сам", "Бот отвечает на типовые вопросы сам"]


def test_data_blocks_forgotten_by_the_model_get_their_own_slides():
    from sd.plan.model import SlidePlan
    from sd.plan.storyline import _adopt_orphan_data

    ir = parse_text("# Отчёт\n\nАбзац.\n\n## Динамика\n\n"
                    "| Квартал | Заявок |\n|---|---|\n| I | 12400 |\n| II | 15800 |\n\n"
                    "## Контакты\n\nпочта: potok@example.com")
    table = next(block for block in ir.blocks if block.type == "table")
    slides = [
        SlidePlan(n=1, intent="cover", key_message="Отчёт", blocks=["b1"]),
        SlidePlan(n=2, intent="bullets", key_message="Абзац о главном", blocks=["b2"], items=["а"]),
        SlidePlan(n=3, intent="contacts", key_message="Контакты", blocks=[]),
    ]
    warnings: list[str] = []
    _adopt_orphan_data(slides, ir, warnings)
    assert [slide.intent for slide in slides] == ["cover", "bullets", "table", "contacts"]
    assert slides[2].blocks == [table.id] and slides[2].key_message == "Динамика"
    assert [slide.n for slide in slides] == [1, 2, 3, 4]
    assert warnings and table.id in warnings[0]

    # Повторный вызов ничего не добавляет: блок уже в плане.
    _adopt_orphan_data(slides, ir, warnings)
    assert len(slides) == 4
