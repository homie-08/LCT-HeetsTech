"""Привязка данных к секторным диаграммам HTML-шаблонов."""

from __future__ import annotations

import copy
import math
from pathlib import Path

import pytest

from sd.htmldeck.charts import (FIRST_ARC_RE, bind_bar_chart, bind_sector_chart,
                                chart_values, detect_chart, numeric, parse_bar_chart,
                                parse_donut, rebuild)
from sd.htmldeck.parse import parse_template

PACKAGE = Path(__file__).resolve().parents[2] / "templates" / "incoming" / "package"

pytestmark = pytest.mark.skipif(not PACKAGE.exists(), reason="нет пакета шаблонов")


def _section(deck: str, label: str):
    template = parse_template(PACKAGE / deck)
    for pattern, section in zip(template.patterns, template.sections):
        if pattern.label == label:
            return section
    raise AssertionError(f"в {deck} нет секции {label}")


def test_geometry_recovered_from_template():
    """Из путей шаблона восстанавливаются радиусы, скругление и зазор."""
    donut = parse_donut(_section("11 Neon Lime.dc.html", "Донат").find(".//svg"))
    assert donut is not None
    assert donut.outer == 80 and donut.inner == 45 and donut.corner == 7
    assert donut.closed
    assert 3 <= donut.gap <= 9
    # Декоративный донат — четыре равные четверти.
    for sector in donut.sectors:
        assert sector.span == pytest.approx(84, abs=1.5)


def test_open_arc_stays_open():
    """Арка Sunset — полукольцо: концы не должны сомкнуться в полный круг."""
    donut = parse_donut(_section("13 Sunset.dc.html", "Арка").find(".//svg"))
    assert donut is not None and not donut.closed

    sectors = rebuild(donut, [60, 25, 15])
    assert sectors[0].a1 == pytest.approx(donut.sectors[0].a1, abs=0.1)
    assert sectors[-1].a2 == pytest.approx(donut.sectors[-1].a2, abs=0.1)


def test_rebuild_shares_are_proportional():
    donut = parse_donut(_section("11 Neon Lime.dc.html", "Донат").find(".//svg"))
    sectors = rebuild(donut, [50, 30, 20])

    total = sum(sector.span for sector in sectors)
    assert sectors[0].span / total == pytest.approx(0.5, abs=0.02)
    assert sectors[1].span / total == pytest.approx(0.3, abs=0.02)
    # Полный оборот: сектора плюс зазоры.
    assert total + donut.gap * 3 == pytest.approx(360, abs=0.5)


def test_tiny_share_keeps_readable_sector():
    """Доля в один процент не превращается в щель — у сектора есть пол."""
    donut = parse_donut(_section("11 Neon Lime.dc.html", "Донат").find(".//svg"))
    sectors = rebuild(donut, [98, 1, 1])
    assert min(sector.span for sector in sectors) >= 13.9


def test_bind_replaces_paths_and_keeps_template_colors():
    section = copy.deepcopy(_section("17 Fintech.dc.html", "Донат"))
    svg = section.find(".//svg")
    # Порядок цветов — угловой, как их расставил дизайнер, а не порядок в файле:
    # k-я доля получает цвет k-го сектора по кругу.
    original = parse_donut(svg)
    palette = [sector.fill for sector in original.sectors]

    assert bind_sector_chart(section, [40, 35, 25])

    paths = [node for node in svg.iter("path")
             if FIRST_ARC_RE.match((node.get("d") or "").strip())
             and node.get("fill") not in (None, "none")]
    assert len(paths) == 3
    assert [node.get("fill") for node in paths] == palette[:3]


def test_icons_follow_sectors():
    """Иконки переезжают в середины новых секторов, лишние убираются."""
    section = copy.deepcopy(_section("11 Neon Lime.dc.html", "Донат"))
    svg = section.find(".//svg")
    assert bind_sector_chart(section, [50, 50])

    donut = parse_donut(svg)
    icons = [node for node in svg.iter("g")
             if "translate" in (node.get("transform") or "")]
    assert len(icons) == 2                     # из четырёх осталось по числу долей
    mids = {round(sector.mid) for sector in donut.sectors}
    for node in icons:
        transform = node.get("transform")
        x, y = (float(value) for value in
                transform.split("translate(")[1].split(")")[0].split(","))
        angle = math.degrees(math.atan2(y - donut.cy, x - donut.cx))
        assert any(abs((angle - mid + 180) % 360 - 180) < 3 for mid in mids)


def test_no_binding_without_enough_values():
    section = copy.deepcopy(_section("11 Neon Lime.dc.html", "Донат"))
    assert not bind_sector_chart(section, [42])
    assert not bind_sector_chart(copy.deepcopy(_section(
        "11 Neon Lime.dc.html", "Раздел 01")), [40, 60])   # секции без диаграммы


def test_chart_values_prefer_percents():
    metrics = [("6 дней", "срок"), ("34 %", "ручной ввод"), ("19 %", "потери")]
    assert chart_values(metrics) == [34, 19]
    assert numeric("1,5 дня") == 1.5
    assert numeric("—") is None


# --- столбиковые графики ------------------------------------------------------

BARS_RE = __import__("re").compile(r"height:\s*(\d+)px")


def _bars(section):
    chart = parse_bar_chart(section)
    assert chart is not None
    return chart


def test_bar_chart_recognised_with_labels_only():
    """Колонки Corporate: значение сверху, столбик, подпись оси снизу."""
    chart = _bars(_section("06 Corporate.dc.html", "График"))
    assert len(chart.columns) == 6
    assert chart.max_height == 375
    assert all(column.value_node is not None for column in chart.columns)


def test_decorative_bars_are_not_a_chart():
    """Полосы на обложке без подписей — декор, а не данные."""
    template = parse_template(PACKAGE / "05 Pastel.dc.html")
    for pattern, section in zip(template.patterns, template.sections):
        if pattern.label == "Обложка":
            assert parse_bar_chart(section) is None
            return
    raise AssertionError("нет обложки")


def test_bind_scales_heights_and_keeps_accent_tail():
    section = copy.deepcopy(_section("06 Corporate.dc.html", "График"))
    accent = _bars(section).columns[-1].bar.get("style")

    assert bind_bar_chart(section, ["A", "B", "C", "D"], [10, 20, 30, 40])

    chart = _bars(section)
    assert len(chart.columns) == 4
    heights = [column.height for column in chart.columns]
    # Линейно от нуля: максимум ряда получает высоту самого высокого столбика.
    assert heights[-1] == pytest.approx(375, abs=1)
    assert heights[0] == pytest.approx(375 * 10 / 40, abs=1)
    # Акцентный цвет дизайнера остался на последнем столбце.
    assert ("background:#2f6fbf" in (chart.columns[-1].bar.get("style") or "")
            or chart.columns[-1].bar.get("style") == accent.replace("height:375px",
                                                                    "height:375px"))
    labels = [column.label_node.text for column in chart.columns]
    assert labels == ["A", "B", "C", "D"]
    values = [column.value_node.text for column in chart.columns]
    assert values == ["10", "20", "30", "40"]


def test_bind_grows_with_muted_clones():
    section = copy.deepcopy(_section("06 Corporate.dc.html", "График"))
    assert bind_bar_chart(section, [f"M{i}" for i in range(8)],
                          [float(i + 1) for i in range(8)])
    chart = _bars(section)
    assert len(chart.columns) == 8
    # Клоны — приглушённые, как первая колонка дизайнера.
    assert "background:#c5d6ea" in (chart.columns[0].bar.get("style") or "")


def test_tiny_value_keeps_visible_bar():
    section = copy.deepcopy(_section("06 Corporate.dc.html", "График"))
    assert bind_bar_chart(section, ["A", "B", "C"], [0.5, 90, 100])
    chart = _bars(section)
    assert min(column.height for column in chart.columns) >= 375 * 0.04 - 1


def test_detect_chart_kinds():
    assert detect_chart(_section("11 Neon Lime.dc.html", "Донат")) == "sector"
    assert detect_chart(_section("06 Corporate.dc.html", "График")) == "bars"
    assert detect_chart(_section("11 Neon Lime.dc.html", "Раздел 01")) is None
