"""Подбор иконок под смысл тезиса."""

from __future__ import annotations

import copy
from pathlib import Path

import pytest
from lxml import etree

from sd.htmldeck.icons import SHAPES, apply_icons, pick
from sd.htmldeck.parse import parse_template

PACKAGE = Path(__file__).resolve().parents[2] / "templates" / "incoming" / "package"

pytestmark = pytest.mark.skipif(not PACKAGE.exists(), reason="нет пакета шаблонов")


def _section(deck: str, label: str):
    template = parse_template(PACKAGE / deck)
    for pattern, section in zip(template.patterns, template.sections):
        if pattern.label == label:
            return section
    raise AssertionError(f"в {deck} нет секции {label}")


@pytest.mark.parametrize("text, expected", [
    ("Срок обработки сократился до полутора дней", "clock"),
    ("Команда из пяти инженеров", "team"),
    ("Экономия бюджета на внедрении", "money"),
    ("Хранение данных в едином реестре", "database"),
    ("Дорожная карта на 2026 год", "calendar"),
])
def test_meaning_drives_the_icon(text, expected):
    assert pick(text) == expected


@pytest.mark.parametrize("text, expected", [
    ("Скольжение саней по склону", "motion"),
    ("Между лезвием конька и льдом плёнка воды", "snow"),
    ("Сила тяжести и равновесие тела", "balance"),
    ("Физика молекул и вещества", "atom"),
    ("Олимпийский вид спорта", "trophy"),
    ("Аэродинамическое сопротивление воздуха", "wave"),
])
def test_vocabulary_reaches_beyond_business(text, expected):
    """Сервис обещает любой контент, а не только питчи: школьный доклад про
    трение не знает ни про выручку, ни про внедрение."""
    assert pick(text) == expected


def test_unknown_text_has_no_icon():
    assert pick("Абракадабра квазиморфная") is None
    assert pick("") is None
    assert pick("42 %") is None


def test_every_keyword_points_to_a_drawn_icon():
    """Словарь и набор контуров не должны разъезжаться."""
    from sd.htmldeck.icons import KEYWORDS

    assert set(KEYWORDS) <= set(SHAPES)


def test_icons_are_valid_svg_and_centred():
    """Контуры обязаны разбираться и лежать в габарите шаблонных значков."""
    for name, markup in SHAPES.items():
        node = etree.fromstring(f'<g xmlns="http://www.w3.org/2000/svg">{markup}</g>')
        assert len(node), f"{name}: пустая иконка"
        numbers = [abs(float(value)) for value in
                   __import__("re").findall(r"-?\d+(?:\.\d+)?", markup)]
        assert max(numbers) <= 20, f"{name}: контур выходит за габарит значка"


def test_replacement_keeps_template_styling():
    """Меняется геометрия, а цвет и толщина обводки остаются шаблонными."""
    section = copy.deepcopy(_section("11 Neon Lime.dc.html", "Донат"))
    svg = section.find(".//svg")
    styled = [node for node in svg.iter("{http://www.w3.org/2000/svg}g", "g")
              if node.get("stroke")]
    before = [(node.get("stroke"), node.get("stroke-width")) for node in styled]

    matched, _ = apply_icons(section, ["Хранение данных", "Проверка качества",
                                       "Команда проекта"])
    assert matched >= 1

    after = [(node.get("stroke"), node.get("stroke-width")) for node in styled]
    assert before == after, "замена иконки затронула оформление"
    assert any(node.get("data-icon") for node in svg.iter())


def test_no_icons_no_crash():
    section = copy.deepcopy(_section("11 Neon Lime.dc.html", "Раздел 01"))
    assert apply_icons(section, ["Любой текст"]) == (0, 0)


def test_separate_svg_icons_are_replaced():
    """Значок бывает не группой в общем рисунке, а отдельным маленьким svg.

    Шаблон «Dark Tech» рисует их именно так, и по прежнему правилу — искать
    группы со сдвигом — они не находились вовсе: рядом с санным спортом
    оставался робот из исходного питча.
    """
    section = copy.deepcopy(_section("03 Dark Tech.dc.html", "Три карточки"))
    matched, neutral = apply_icons(section, ["Скольжение саней по льду",
                                             "Сопротивление воздуха",
                                             "Абракадабра квазиморфная"])
    assert (matched, neutral) == (2, 1)
    icons = [svg.get("data-icon") for svg in section.findall(".//svg")]
    assert icons == ["motion", "wave", "mark"]


def test_our_shapes_land_inside_the_template_viewbox():
    """Контуры набора лежат вокруг нуля, а значок шаблона — в своём вьюбоксе."""
    section = copy.deepcopy(_section("03 Dark Tech.dc.html", "Три карточки"))
    apply_icons(section, ["Скольжение саней"])
    svg = section.find(".//svg")
    group = svg.find("{http://www.w3.org/2000/svg}g")
    assert group is not None, "контуры вложены без переноса — значок уедет в угол"
    assert "translate(12 12)" in group.get("transform")


def test_one_icon_is_not_repeated_across_a_slide():
    """Три одинаковых значка в ряд читаются как недоделка."""
    section = copy.deepcopy(_section("03 Dark Tech.dc.html", "Три карточки"))
    apply_icons(section, ["Движение саней", "Движение и сила тяжести",
                          "Движение по льду"])
    icons = [svg.get("data-icon") for svg in section.findall(".//svg")]
    assert len(set(icons)) == 3, f"значки повторяются: {icons}"


def test_charts_are_not_mistaken_for_icons():
    """Диаграмму подменять нельзя: она несёт данные, а не смысл подписи."""
    section = copy.deepcopy(_section("11 Neon Lime.dc.html", "Донат"))
    donut = section.find(".//svg")
    before = etree.tostring(donut)
    apply_icons(section, [])
    assert etree.tostring(donut) == before
