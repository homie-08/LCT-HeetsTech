"""Раскладка тезиса по местам карточки.

Места в карточке неравноценны: у одного в шаблоне стоит номер «01», у другого —
заголовок, у третьего — пояснение. Ошибка здесь видна сразу: в счётчик уезжает
обрывок фразы, а сама фраза рвётся пополам.
"""

from __future__ import annotations

from pathlib import Path

import pytest
from lxml import html as lxml_html

from sd.htmldeck.build import _fill_card, _shrink_columns, _split
from sd.htmldeck.parse import Slot, parse_template

PACKAGE = Path(__file__).resolve().parents[2] / "templates" / "incoming" / "package"


def _slot(sample: str, font: float, role: str = "item", budget: int = 0) -> Slot:
    return Slot(path=f"p{font}", role=role, sample=sample, font_px=font,
                bold=False, group="g1", order=0, budget=budget or len(sample))


def _placed(card: list[Slot], text: str) -> dict[str, str]:
    """Прогоняет раскладку и возвращает, что куда легло."""
    result: dict[str, str] = {}

    def put(slot: Slot, value: str) -> bool:
        if value:
            result[slot.path] = value
        return True

    _fill_card(put, card, text)
    return result


def test_counter_keeps_template_numbering():
    """В слот с «01» тезис не попадает: это счётчик, а не место под текст."""
    counter, line = _slot("01", 28, role="body"), _slot("Проблема: знания в документах", 32)
    placed = _placed([counter, line], "Трение мешает движению и помогает сцеплению.")
    assert counter.path not in placed
    assert placed[line.path] == "Трение мешает движению и помогает сцеплению."


def test_short_phrase_goes_to_the_heading():
    """Короткая фраза — заголовок карточки, а не подпись под ним."""
    heading, body = _slot("Семантический поиск", 34), _slot(
        "Находит ответ по смыслу, а не по совпадению слов", 27, role="body")
    placed = _placed([heading, body], "Введение")
    assert placed == {heading.path: "Введение"}


def test_long_thesis_goes_to_the_roomy_slot():
    """Длинный тезис уходит в самое вместительное место, а не в шапку."""
    heading, body = _slot("Семантический поиск", 34), _slot(
        "Находит ответ по смыслу, а не по совпадению слов", 27, role="body")
    text = ("Скольжение саней происходит под действием скатывающей силы "
            "и зависит от состояния льда.")
    placed = _placed([heading, body], text)
    assert placed == {body.path: text}


def test_natural_split_fills_both_places():
    """Там, где мысль делится сама, карточка получает и шапку, и пояснение."""
    heading, body = _slot("Семантический поиск", 34), _slot(
        "Находит ответ по смыслу, а не по совпадению слов", 27, role="body")
    placed = _placed([heading, body],
                     "Керлинг — игра, где трение регулируют щётками.")
    assert placed[heading.path] == "Керлинг"
    assert placed[body.path] == "игра, где трение регулируют щётками."


def test_phrase_is_never_split_mid_thought():
    """Фразу без своей границы делить нечем — она идёт целиком."""
    text = "Скольжение саней происходит под действием скатывающей силы"
    assert _split(text) == (text, "")


def test_oversized_head_is_not_forced_into_the_heading():
    """Если шапка не влезает в своё место, целое лучше двух огрызков."""
    heading, body = _slot("Итог", 34), _slot(
        "Находит ответ по смыслу, а не по совпадению слов", 27, role="body")
    text = ("При движении саней возникает ещё одна сила — сила "
            "аэродинамического сопротивления.")
    placed = _placed([heading, body], text)
    assert placed == {body.path: text}


def test_grid_follows_the_number_of_cards():
    """Убрали карточки — сетка сужается, иначе оставшаяся жмётся в угол."""
    container = lxml_html.fromstring(
        '<div style="display:grid; grid-template-columns:repeat(3,1fr); gap:24px;">'
        "<div>карточка</div></div>")
    _shrink_columns(container, keep=1)
    assert "repeat(1,1fr)" in container.get("style")
    assert "gap:24px" in container.get("style")


def test_grid_untouched_when_nothing_dropped():
    container = lxml_html.fromstring(
        '<div style="grid-template-columns:repeat(2,minmax(0,1fr));">x</div>')
    _shrink_columns(container, keep=3)
    assert "repeat(2,minmax(0,1fr))" in container.get("style")


def test_explicit_track_list_shrinks_too():
    """Колонки пишут и списком — `1fr 1fr 1fr`. Пока разбирался только
    `repeat(...)`, одинокая карточка так и оставалась в трети слайда."""
    container = lxml_html.fromstring(
        '<div style="display:grid; grid-template-columns:1fr 1fr 1fr; gap:36px;">x</div>')
    _shrink_columns(container, keep=1)
    assert "grid-template-columns:1fr;" in container.get("style").replace(" ;", ";")
    assert "gap:36px" in container.get("style")


def test_track_list_with_functions_is_not_split_by_spaces():
    """`minmax(0, 1fr)` — одна дорожка, а не две: пробел внутри скобок не в счёт."""
    container = lxml_html.fromstring(
        '<div style="grid-template-columns:minmax(0, 1fr) minmax(0, 1fr) 2fr;">x</div>')
    _shrink_columns(container, keep=2)
    assert "minmax(0, 1fr) minmax(0, 1fr)" in container.get("style")
    assert "2fr" not in container.get("style")


def _balanced(style: str) -> str:
    from sd.htmldeck.build import SlideResult, _balance_column

    section = lxml_html.fromstring(f'<section style="{style}">x</section>')
    _balance_column(section, SlideResult(n=1, label="", archetype=""))
    return section.get("style")


def test_short_content_is_spread_over_the_slide_height():
    """Наш текст короче шаблонного, и колонка, прижатая к верху, оставляет
    пустую треть внизу."""
    style = _balanced("display:flex; flex-direction:column; padding:100px;")
    assert "justify-content:safe center" in style
    assert "padding:100px" in style


def test_overflowing_content_is_not_clipped_from_the_top():
    """`safe` оставляет не влезающее прижатым к верху: центрирование срезало бы
    у него начало."""
    assert "safe center" in _balanced("display:flex; flex-direction:column;")


def test_designer_decision_is_kept():
    """Где выключка по высоте задана шаблоном, лезть не во что."""
    style = _balanced("display:flex; flex-direction:column; justify-content:flex-end;")
    assert "safe center" not in style


def test_non_column_layouts_are_untouched():
    assert _balanced("display:grid; grid-template-columns:1fr 1fr;") == \
        "display:grid; grid-template-columns:1fr 1fr;"


@pytest.mark.skipif(not PACKAGE.exists(), reason="нет пакета шаблонов")
def test_cards_of_one_group_share_capacity():
    """Карточки одного ряда сделаны по одной мерке — и мерка у них общая.

    Иначе текст обрезается в той карточке, где у шаблона образец покороче,
    хотя места там ровно столько же.
    """
    template = parse_template(PACKAGE / "03 Dark Tech.dc.html")
    agenda = next(pattern for pattern in template.patterns
                  if pattern.label == "Содержание")
    lines = [slot for slot in agenda.slots if slot.group and slot.role == "item"]
    assert len({slot.budget for slot in lines}) == 1
    assert max(slot.budget for slot in lines) == max(len(slot.sample) for slot in lines)
    assert min(len(slot.sample) for slot in lines) < lines[0].budget


@pytest.mark.skipif(not PACKAGE.exists(), reason="нет пакета шаблонов")
def test_cover_and_closing_keep_their_place():
    """Обложка в середине и «Финал» на седьмом слайде из пятнадцати — не «хуже
    подходит», а неверно, сколько бы слотов они ни закрыли."""
    from sd.content.parse import parse_text
    from sd.htmldeck.build import UNFIT, _score
    from sd.plan.storyline import build_plan

    template = parse_template(PACKAGE / "03 Dark Tech.dc.html")
    ir = parse_text("# Тема\n\n## Раздел\n\nПервый тезис. Второй тезис. Третий тезис.\n")
    plan = build_plan(ir, None)
    slide = plan.slides[-1]
    cover = next(p for p in template.patterns if p.archetype == "cover")
    closing = next(p for p in template.patterns if p.archetype == "contacts")

    assert _score(cover, slide, ir, 0, index=3, total=9) == UNFIT
    assert _score(closing, slide, ir, 0, index=3, total=9) == UNFIT
    assert _score(cover, slide, ir, 0, index=0, total=9) > UNFIT
    assert _score(closing, slide, ir, 0, index=8, total=9) > UNFIT
