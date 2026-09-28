"""Укладка в PPTX-ветке: карточки, рост слотов, место под медиа, перенос слов.

Всё, что здесь проверяется, найдено на трёх шаблонах VK из датасета
организаторов: тезис резался до трёх слов в однострочной шапке карточки, пока
описание под ней пустовало; подпись показателя уезжала под чужую цифру; слово
шире стикера ломалось по слогам; таблице не находилось места, и она пропадала.
"""

from __future__ import annotations

import pytest

from sd.fit.layout import (CARD_MIN_W, SlotFill, _cards, _desc_below, _fill_cards,
                           _grow_slot, _major_slots, _split_thesis, content_area)
from sd.template.model import (Capacity, DecorItem, DesignSystem, Geometry, Pattern,
                               SlideSize, Slot, Source)


def _slot(role: str, x: float, y: float, w: float, h: float, chars: int = 40,
          lines: int = 1, size: float = 16.0, shape_id: int | None = None) -> Slot:
    return Slot(role=role, bbox=[x, y, w, h], size_pt=size,  # type: ignore[arg-type]
                capacity=Capacity(chars=chars, lines=lines), shape_id=shape_id)


def _pattern(slots: list[Slot]) -> Pattern:
    return Pattern(id="p", archetype="bullets", source_kind="slide", source_name="s",
                   source_part="s", render_mode="clone_slide", slots=slots)


def _design(safe=None) -> DesignSystem:
    geometry = Geometry(safe_area=safe) if safe else Geometry()
    source = Source(file="t.pptx", sha256="0" * 64,
                    slide_size=SlideSize(w_emu=12192000, h_emu=6858000, ratio="16:9"))
    return DesignSystem(source=source, geometry=geometry)


# --- карточки ----------------------------------------------------------------

def test_card_pairs_heading_with_description_below():
    """Шапка и описание под ней той же ширины — одна карточка."""
    head = _slot("body", 0.05, 0.30, 0.33, 0.03, chars=41)
    desc = _slot("caption", 0.05, 0.35, 0.33, 0.17, chars=220, lines=4)
    other = _slot("body", 0.42, 0.30, 0.33, 0.03, chars=41)
    cards = _cards(_pattern([head, desc, other]), {})
    assert [(a.bbox[0], b is not None) for a, b in cards] == [(0.05, True), (0.42, False)]
    assert cards[0][1] is desc


def test_slight_overlap_still_pairs():
    """Рамки из Google Slides заходят друг на друга на доли процента."""
    head = _slot("item", 0.66, 0.312, 0.44, 0.157)
    desc = _slot("body", 0.66, 0.467, 0.37, 0.110)          # выше низа шапки на 0,002
    assert _desc_below(head, [desc]) is desc


def test_long_thesis_goes_to_description_and_heading_stays_empty():
    """Длинный тезис — в описание; шапка резервируется, чтобы не получить чужой остаток."""
    head = _slot("body", 0.05, 0.30, 0.33, 0.03, chars=41)
    desc = _slot("caption", 0.05, 0.35, 0.33, 0.17, chars=220, lines=4)
    taken: dict[int, SlotFill] = {}
    text = "Заменяет связку из четырёх систем и почты, в которой сегодня теряется каждая пятая заявка."
    rest = _fill_cards([(head, desc)], [text, "Остаток"], {}, taken)
    assert taken[id(desc)].text == text
    assert taken[id(head)].kind == "empty"
    assert rest == ["Остаток"]


def test_short_thesis_goes_to_heading():
    head = _slot("body", 0.05, 0.30, 0.33, 0.03, chars=41)
    desc = _slot("caption", 0.05, 0.35, 0.33, 0.17, chars=220, lines=4)
    taken: dict[int, SlotFill] = {}
    _fill_cards([(head, desc)], ["Ядро"], {}, taken)
    assert taken[id(head)].text == "Ядро" and id(desc) not in taken


def test_metric_splits_into_value_and_label():
    head = _slot("item", 0.05, 0.30, 0.2, 0.06, chars=12)
    desc = _slot("body", 0.05, 0.37, 0.2, 0.08, chars=60, lines=2)
    taken: dict[int, SlotFill] = {}
    unit = "45 млн ₽ — экономия на операционных издержках"
    _fill_cards([(head, desc)], [unit], {unit: ("45 млн ₽", "экономия на операционных издержках")}, taken)
    assert taken[id(head)].text == "45 млн ₽"
    assert taken[id(desc)].text == "экономия на операционных издержках"


def test_metric_in_a_tight_lone_slot_keeps_only_the_value():
    """Кружок на таймлайне держит «в 4 раза», но не подпись по слогам."""
    circle = _slot("item", 0.1, 0.4, 0.13, 0.13, chars=10)
    taken: dict[int, SlotFill] = {}
    unit = "в 4 раза — срок обработки сократился"
    _fill_cards([(circle, None)], [unit], {unit: ("в 4 раза", "срок обработки сократился")}, taken)
    assert taken[id(circle)].text == "в 4 раза"


def test_staircase_cards_read_left_to_right():
    """Ступеньки: карточки одного ряда на разной высоте читаются по x."""
    heads = [_slot("item", x, y, 0.2, 0.06) for x, y in ((0.05, 0.52), (0.28, 0.44), (0.51, 0.36))]
    cards = _cards(_pattern(heads), {})
    assert [card[0].bbox[0] for card in cards] == [0.05, 0.28, 0.51]


def test_narrow_strips_and_figure_slots_are_not_cards():
    sticker = _slot("body", 0.7, 0.1, CARD_MIN_W - 0.02, 0.3, chars=90)
    figure = _slot("metric_value", 0.1, 0.4, 0.4, 0.3, chars=8)
    wide = _slot("body", 0.1, 0.1, 0.4, 0.1)
    cards = _cards(_pattern([sticker, figure, wide]), {})
    assert [card[0] for card in cards] == [wide]


def test_major_slots_skip_narrow_strips():
    wide = _slot("body", 0.1, 0.1, 0.4, 0.2, chars=300)
    strip = _slot("body", 0.7, 0.1, 0.09, 0.05, chars=22)
    assert _major_slots([wide, strip]) == [wide]


def test_split_thesis_only_on_natural_boundaries():
    assert _split_thesis("Ядро — сервис маршрутизации") == ("Ядро", "сервис маршрутизации")
    assert _split_thesis("Единая среда: приём и контроль") == ("Единая среда", "приём и контроль")
    whole = "Скольжение саней происходит под действием силы"
    assert _split_thesis(whole) == (whole, "")


# --- рост слота ---------------------------------------------------------------

def test_slot_grows_down_to_the_next_occupied_slot():
    head = _slot("body", 0.05, 0.30, 0.33, 0.10)
    below = _slot("body", 0.05, 0.60, 0.33, 0.03)
    taken = {id(below): SlotFill(below, "text", text="занят")}
    assert _grow_slot(head, _pattern([head, below]), taken)
    assert head.bbox[1] + head.bbox[3] == pytest.approx(0.60 - 0.015)


def test_slot_growth_is_limited_by_its_own_height():
    """Тонкая полоска не растёт втрое дальше своей карточки."""
    head = _slot("body", 0.05, 0.30, 0.33, 0.03)
    assert _grow_slot(head, _pattern([head]), {})
    assert head.bbox[3] == pytest.approx(0.03 * 4)


def test_slot_growth_is_capped_and_stops_above_decor():
    head = _slot("body", 0.12, 0.66, 0.18, 0.12)
    design = _design()
    design.decor.items.append(DecorItem(kind="logo", bbox=[0.03, 0.88, 0.2, 0.06]))
    assert _grow_slot(head, _pattern([head]), {}, design)
    assert head.bbox[1] + head.bbox[3] <= 0.88 - 0.015 + 1e-9


def test_title_and_figure_do_not_grow():
    title = _slot("title", 0.05, 0.05, 0.6, 0.1)
    assert not _grow_slot(title, _pattern([title]), {})


# --- место под медиа ----------------------------------------------------------

def test_content_area_lies_below_the_title_and_spans_the_layout():
    title = _slot("title", 0.05, 0.05, 0.6, 0.1)
    body = _slot("body", 0.05, 0.3, 0.4, 0.2)
    box = content_area(_pattern([title, body]), _design(), 0.35, 0.22)
    assert box is not None
    left, top, width, height = box
    assert top == pytest.approx(0.15 + 0.03)
    # По ширине — размах всех слотов, включая заголовок: он задаёт колонку.
    assert left == pytest.approx(0.05) and width == pytest.approx(0.6)
    # Низ — по безопасной зоне шаблона (здесь стандартная: 0,05 + 0,9).
    assert top + height == pytest.approx(0.95)


def test_content_area_ignores_a_degenerate_safe_zone():
    """У WorkSpace безопасная зона нулевой высоты — край берётся по умолчанию."""
    title = _slot("title", 0.05, 0.05, 0.6, 0.1)
    box = content_area(_pattern([title]), _design(safe=[0.035, 0.23, 0.64, 0.0]), 0.35, 0.22)
    assert box is not None and box[1] + box[3] == pytest.approx(0.9)


def test_content_area_refuses_a_hero_layout():
    """Под заголовком в нижней трети слайда графику места нет."""
    title = _slot("title", 0.05, 0.36, 0.64, 0.27)
    assert content_area(_pattern([title]), _design(), 0.35, 0.3) is None


def test_contact_line_already_said_by_theses_is_not_a_dropped_fragment():
    """План разложил контакты по строкам — строка целиком не «не размещена»."""
    from sd.fit.layout import _covered_by

    line = "Команда платформы «Поток», potok@example.com, +7 495 000-00-00, potok.example.com"
    items = ["Команда платформы «Поток»", "potok@example.com", "+7 495 000-00-00",
             "potok.example.com"]
    assert _covered_by(line, items)
    assert not _covered_by(line, ["Спасибо за внимание"])
    assert not _covered_by("", items)


def test_cards_of_one_row_read_left_to_right_despite_tiny_height_differences():
    """Карточки одного ряда с разбросом верха в доли процента — один ряд."""
    from sd.fit.layout import _cards
    from sd.template.model import Capacity, Pattern, Slot

    def card(x: float, y: float, role: str = "item") -> Slot:
        return Slot(role=role, bbox=[x, y, 0.24, 0.18], capacity=Capacity(chars=116, lines=4))

    pattern = Pattern(id="p", archetype="two_column", source_kind="slide", source_name="s",
                      source_part="s", render_mode="clone_slide",
                      slots=[card(0.36, 0.549), card(0.67, 0.549, "body"), card(0.05, 0.551),
                             Slot(role="body", bbox=[0.05, 0.88, 0.53, 0.05],
                                  capacity=Capacity(chars=66, lines=1))])
    heads = [head.bbox[0] for head, _ in _cards(pattern, {})]
    assert heads == [0.05, 0.36, 0.67, 0.05]


def test_thesis_restating_the_table_is_a_note_not_a_dropped_fragment():
    """Таблица на слайде уже сказала «34 %» — тезис с той же цифрой не «потерян»."""
    from sd.content.parse import parse_text
    from sd.fit.layout import _numbers_on_media, SlotFill
    from sd.template.model import Capacity, Slot

    ir = parse_text("# Отчёт\n\n| Показатель | Было | Стало |\n|---|---|---|\n"
                    "| Ручной ввод | 34 % | 8 % |\n| Срок | 6 дней | 1,5 дня |")
    table = next(block for block in ir.blocks if block.type == "table")
    slot = Slot(role="table", bbox=[0.1, 0.3, 0.8, 0.5], capacity=Capacity(chars=0))
    shown = _numbers_on_media({id(slot): SlotFill(slot, "table", block_id=table.id)}, ir)
    assert {"34", "8", "6", "1.5"} <= shown
    assert _numbers_on_media({}, ir) == set()
