"""Привязка данных к секторным диаграммам HTML-шаблонов.

Донаты и арки в шаблонах нарисованы одним генератором: кольцевой сектор со
скруглёнными углами (см. README пакета). У декоративной диаграммы углы
расставлены поровну и с цифрами контента никак не связаны — картинка красивая,
но врёт. Здесь сектора пересобираются заново: из путей шаблона вынимается
геометрия (центр, радиусы, скругление, зазоры), а углы раздаются
пропорционально значениям из контента.

Всё оформление остаётся родным: цвета секторов, толщина кольца, скругления и
иконки — из шаблона; от нас только доли.
"""

from __future__ import annotations

import math
import re
from dataclasses import dataclass

from lxml import etree

SVG_NS = "http://www.w3.org/2000/svg"

# Уже сектора не делаем: в острый клин не помещается скругление углов,
# и он читается как ошибка, а не как маленькая доля.
MIN_SPAN_DEG = 14.0
# Незамкнутый остаток меньше этого угла считаем зазором замкнутого доната.
CLOSED_GAP_DEG = 40.0


@dataclass
class Sector:
    a1: float                  # угол начала, градусы
    a2: float                  # угол конца
    fill: str

    @property
    def span(self) -> float:
        return self.a2 - self.a1

    @property
    def mid(self) -> float:
        return (self.a1 + self.a2) / 2


@dataclass
class Donut:
    cx: float
    cy: float
    outer: float               # Ro
    inner: float               # Ri
    corner: float              # c — радиус скругления угла
    sectors: list[Sector]
    closed: bool               # полное кольцо или арка
    gap: float                 # угловой зазор между секторами


# --- разбор путей шаблона -----------------------------------------------------

NUMBER = r"-?\d+(?:\.\d+)?"
FIRST_ARC_RE = re.compile(
    rf"M\s*({NUMBER})[ ,]({NUMBER})\s*A\s*({NUMBER})[ ,]\3\s+0\s+[01]\s+1\s+"
    rf"({NUMBER})[ ,]({NUMBER})")
ARC_RE = re.compile(rf"A\s*({NUMBER})[ ,]\1\s+0\s+([01])\s+([01])")


def _circumcenter(p1, p2, p3) -> tuple[float, float] | None:
    """Центр окружности по трём точкам."""
    ax, ay = p1
    bx, by = p2
    cx, cy = p3
    d = 2 * (ax * (by - cy) + bx * (cy - ay) + cx * (ay - by))
    if abs(d) < 1e-9:
        return None
    ux = ((ax * ax + ay * ay) * (by - cy) + (bx * bx + by * by) * (cy - ay)
          + (cx * cx + cy * cy) * (ay - by)) / d
    uy = ((ax * ax + ay * ay) * (cx - bx) + (bx * bx + by * by) * (ax - cx)
          + (cx * cx + cy * cy) * (bx - ax)) / d
    return ux, uy


def _angle(cx: float, cy: float, x: float, y: float) -> float:
    return math.degrees(math.atan2(y - cy, x - cx))


def parse_donut(svg: etree._Element) -> Donut | None:
    """Восстанавливает геометрию диаграммы из путей генератора."""
    raw: list[tuple[tuple[float, float], tuple[float, float], float, float, float, str]] = []
    for path in svg.iter(f"{{{SVG_NS}}}path", "path"):
        d = path.get("d") or ""
        fill = path.get("fill") or ""
        first = FIRST_ARC_RE.match(d.strip())
        if not (first and fill and fill != "none"):
            continue
        # Дуги в контуре генератора идут в известном порядке: первая — внешняя
        # (радиус Ro), вторая — скругление угла (радиус c), а внутренняя — та,
        # что рисуется против часовой (sweep 0) и радиусом не равна скруглению.
        # По флагам их различать нельзя: у сектора меньше 180° внешняя дуга
        # несёт те же «0 1», что и скругление.
        arcs = ARC_RE.findall(d)
        if len(arcs) < 3:
            continue
        corner = float(arcs[1][0])
        inner = next((float(radius) for radius, _, sweep in arcs
                      if sweep == "0" and float(radius) != corner), None)
        if inner is None:
            continue
        x1, y1, outer, x2, y2 = (float(first.group(i)) for i in range(1, 6))
        raw.append(((x1, y1), (x2, y2), outer, inner, corner, fill))

    if len(raw) < 2:
        return None

    outer = raw[0][2]
    points = [p for item in raw for p in (item[0], item[1])]
    centre = _circumcenter(points[0], points[1], points[-1])
    if centre is None:
        return None
    cx, cy = centre

    corner = raw[0][4]
    go = math.degrees(corner / outer)      # угловая поправка на скругление
    sectors = []
    for p1, p2, _, _, _, fill in raw:
        a1 = _angle(cx, cy, *p1) - go
        a2 = _angle(cx, cy, *p2) + go
        while a2 <= a1:                    # дуга через 180°: atan2 перескакивает
            a2 += 360.0
        sectors.append(Sector(a1, a2, fill))
    sectors.sort(key=lambda s: s.a1)

    gaps = [sectors[i + 1].a1 - sectors[i].a2 for i in range(len(sectors) - 1)]
    tail = sectors[0].a1 + 360.0 - sectors[-1].a2
    closed = tail <= CLOSED_GAP_DEG
    if closed:
        gaps.append(tail)
    gap = sum(gaps) / len(gaps) if gaps else 6.0

    return Donut(cx=cx, cy=cy, outer=outer, inner=raw[0][3], corner=corner,
                 sectors=sectors, closed=closed, gap=gap)


# --- генератор путей (порт из README шаблонов) --------------------------------

def _point(cx: float, cy: float, radius: float, angle: float) -> str:
    rad = math.radians(angle)
    return f"{cx + radius * math.cos(rad):.1f} {cy + radius * math.sin(rad):.1f}"


def sector_path(cx: float, cy: float, outer: float, inner: float,
                a1: float, a2: float, corner: float) -> str:
    """Кольцевой сектор со скруглёнными углами — тот же контур, что в шаблонах."""
    go = math.degrees(corner / outer)
    gi = math.degrees(corner / inner)
    span = a2 - a1
    lf = 1 if (span - 2 * go) > 180 else 0
    lfi = 1 if (span - 2 * gi) > 180 else 0
    point = lambda radius, angle: _point(cx, cy, radius, angle)  # noqa: E731
    return " ".join([
        "M" + point(outer, a1 + go),
        f"A{outer:g} {outer:g} 0 {lf} 1 " + point(outer, a2 - go),
        f"A{corner:g} {corner:g} 0 0 1 " + point(outer - corner, a2),
        "L" + point(inner + corner, a2),
        f"A{corner:g} {corner:g} 0 0 1 " + point(inner, a2 - gi),
        f"A{inner:g} {inner:g} 0 {lfi} 0 " + point(inner, a1 + gi),
        f"A{corner:g} {corner:g} 0 0 1 " + point(inner + corner, a1),
        "L" + point(outer - corner, a1),
        f"A{corner:g} {corner:g} 0 0 1 " + point(outer, a1 + go),
        "Z",
    ])


# --- раздача углов по значениям ----------------------------------------------

def _spans(values: list[float], available: float) -> list[float]:
    """Углы секторов пропорционально значениям, с полом на читаемость."""
    total = sum(values) or 1.0
    spans = [available * value / total for value in values]

    # Слишком узкие доли поднимаем до пола, остальные ужимаем пропорционально.
    floor = min(MIN_SPAN_DEG, available / len(values))
    for _ in range(len(values)):
        deficit = sum(floor - s for s in spans if s < floor)
        if deficit <= 0:
            break
        wide = [i for i, s in enumerate(spans) if s > floor]
        shrinkable = sum(spans[i] - floor for i in wide) or 1.0
        for i in range(len(spans)):
            if spans[i] < floor:
                spans[i] = floor
            elif i in wide:
                spans[i] -= deficit * (spans[i] - floor) / shrinkable
    return spans


def rebuild(donut: Donut, values: list[float]) -> list[Sector]:
    """Новый набор секторов под значения — в геометрии исходной диаграммы."""
    count = len(values)
    start = donut.sectors[0].a1
    if donut.closed:
        available = 360.0 - donut.gap * count
    else:
        end = donut.sectors[-1].a2
        available = (end - start) - donut.gap * (count - 1)

    spans = _spans(values, available)
    fills = [s.fill for s in donut.sectors]
    sectors: list[Sector] = []
    cursor = start
    for index, span in enumerate(spans):
        sectors.append(Sector(cursor, cursor + span, fills[index % len(fills)]))
        cursor += span + donut.gap
    return sectors


# --- применение к секции ------------------------------------------------------

TRANSLATE_RE = re.compile(rf"translate\(({NUMBER}),({NUMBER})\)")


def _move_icons(svg: etree._Element, donut: Donut, sectors: list[Sector]) -> None:
    """Переставляет иконки в середины новых секторов.

    Иконка привязана к сектору по положению: она стоит на среднем радиусе под
    средним углом. Ищем такие группы, сопоставляем ближайшему старому сектору
    и передвигаем в середину нового. Лишние иконки убираем — сектора без
    иконки лучше, чем иконка, повисшая на границе двух долей.
    """
    mid_radius = (donut.outer + donut.inner) / 2
    movable: list[tuple[etree._Element, int]] = []
    for node in list(svg.iter(f"{{{SVG_NS}}}g", "g")):
        match = TRANSLATE_RE.search(node.get("transform") or "")
        if not match:
            continue
        x, y = float(match.group(1)), float(match.group(2))
        radius = math.hypot(x - donut.cx, y - donut.cy)
        if abs(radius - mid_radius) > donut.outer * 0.2:
            continue
        angle = _angle(donut.cx, donut.cy, x, y)
        nearest = min(range(len(donut.sectors)),
                      key=lambda i: abs((donut.sectors[i].mid - angle + 180) % 360 - 180))
        movable.append((node, nearest))

    movable.sort(key=lambda item: item[1])
    for order, (node, _) in enumerate(movable):
        if order >= len(sectors):
            parent = node.getparent()
            if parent is not None:
                parent.remove(node)
            continue
        mid = sectors[order].mid
        rad = math.radians(mid)
        x = donut.cx + mid_radius * math.cos(rad)
        y = donut.cy + mid_radius * math.sin(rad)
        node.set("transform", TRANSLATE_RE.sub(
            f"translate({x:.1f},{y:.1f})", node.get("transform") or "", count=1))
        # Номер доли: по нему иконка потом найдёт свой тезис. В разметке
        # значки лежат в произвольном порядке, а по кругу — в порядке данных.
        node.set("data-sector", str(order))


def bind_sector_chart(section: etree._Element, values: list[float]) -> bool:
    """Пересобирает секторную диаграмму секции под значения. True — если нашлась."""
    if len(values) < 2:
        return False
    values = [abs(value) for value in values if value]
    if len(values) < 2:
        return False

    for svg in section.iter(f"{{{SVG_NS}}}svg", "svg"):
        donut = parse_donut(svg)
        if donut is None:
            continue
        sectors = rebuild(donut, values[:6])

        paths = [node for node in svg.iter(f"{{{SVG_NS}}}path", "path")
                 if FIRST_ARC_RE.match((node.get("d") or "").strip())
                 and (node.get("fill") or "none") != "none"]
        parent = paths[0].getparent()
        anchor = paths[0]
        for node in paths[1:]:
            node.getparent().remove(node)

        anchor.set("d", sector_path(donut.cx, donut.cy, donut.outer, donut.inner,
                                    sectors[0].a1, sectors[0].a2, donut.corner))
        anchor.set("fill", sectors[0].fill)
        previous = anchor
        for sector in sectors[1:]:
            node = etree.SubElement(parent, anchor.tag)
            node.set("d", sector_path(donut.cx, donut.cy, donut.outer, donut.inner,
                                      sector.a1, sector.a2, donut.corner))
            node.set("fill", sector.fill)
            previous.addnext(node)
            previous = node

        _move_icons(svg, donut, sectors)
        return True
    return False


# --- столбиковые диаграммы ----------------------------------------------------
#
# «График» в шаблонах — это колонки-дивы: подпись значения сверху, столбик с
# высотой в пикселях, подпись категории снизу. Высота и есть данные, поэтому
# привязка — тот же приём, что с донатом: цвета, отступы и акцент на последнем
# столбце остаются дизайнерскими, пересчитываются только высоты и подписи.

HEIGHT_RE = re.compile(r"height:\s*(\d+(?:\.\d+)?)px")

# Разумные пределы: меньше двух столбцов — не график, больше двенадцати — забор.
MIN_BARS, MAX_BARS = 2, 12
# Совсем нулевой столбик выглядит дыркой в ряду — оставляем ножку.
MIN_BAR_RATIO = 0.04


@dataclass
class BarColumn:
    root: etree._Element
    bar: etree._Element
    value_node: etree._Element | None
    label_node: etree._Element | None
    height: float


@dataclass
class BarChart:
    container: etree._Element
    columns: list[BarColumn]

    @property
    def max_height(self) -> float:
        return max(column.height for column in self.columns)


def _own_text_of(node: etree._Element) -> str:
    parts = [node.text or ""] + [child.tail or "" for child in node]
    return "".join(parts).strip()


def _bar_of(column: etree._Element) -> etree._Element | None:
    """Столбик внутри колонки: безтекстовый элемент с высотой в px и заливкой."""
    bars = []
    for node in column.iter():
        if not isinstance(node.tag, str):
            continue
        style = node.get("style") or ""
        if HEIGHT_RE.search(style) and "background" in style and not _own_text_of(node):
            bars.append(node)
    return bars[0] if len(bars) == 1 else None


def parse_bar_chart(section: etree._Element) -> BarChart | None:
    """Ищет ряд колонок-столбиков. Декоративные полосы без подписей не в счёт."""
    for parent in section.iter():
        if not isinstance(parent.tag, str):
            continue
        children = [child for child in parent if isinstance(child.tag, str)]
        if len(children) < 3:
            continue

        columns: list[BarColumn] = []
        for child in children:
            bar = _bar_of(child)
            if bar is None:
                columns = []
                break
            # Тексты колонки: до столбика — значение, после — подпись оси.
            value_node = label_node = None
            seen_bar = False
            for node in child.iter():
                if not isinstance(node.tag, str):
                    continue
                if node is bar:
                    seen_bar = True
                    continue
                if _own_text_of(node):
                    if not seen_bar and value_node is None:
                        value_node = node
                    elif seen_bar and label_node is None:
                        label_node = node
            if value_node is None and label_node is None:
                columns = []
                break
            height = float(HEIGHT_RE.search(bar.get("style")).group(1))
            columns.append(BarColumn(child, bar, value_node, label_node, height))

        if len(columns) >= 3:
            return BarChart(parent, columns)
    return None


def _format_value(value: float) -> str:
    """Число как в шаблонах: целое без хвоста, дробное — с запятой."""
    if float(value).is_integer():
        return str(int(value))
    return f"{value:.1f}".replace(".", ",")


def bind_bar_chart(section: etree._Element, labels: list[str],
                   values: list[float]) -> bool:
    """Пересобирает столбиковый график под ряд данных. True — если нашёлся."""
    points = [(label, float(value)) for label, value in zip(labels, values)
              if value is not None][:MAX_BARS]
    if len(points) < MIN_BARS:
        return False

    chart = parse_bar_chart(section)
    if chart is None:
        return False

    columns = list(chart.columns)
    need = len(points)

    # Лишние колонки убираем слева: акцент дизайнер держит на последних
    # столбцах («сейчас»), и хвост ряда должен его сохранить.
    while len(columns) > need:
        column = columns.pop(0)
        parent = column.root.getparent()
        if parent is not None:
            parent.remove(column.root)

    # Недостающие — клоны первой (приглушённой) колонки перед остальными.
    import copy as _copy

    while len(columns) < need:
        clone_root = _copy.deepcopy(columns[0].root)
        columns[0].root.addprevious(clone_root)
        bar = _bar_of(clone_root)
        value_node = label_node = None
        seen_bar = False
        for node in clone_root.iter():
            if not isinstance(node.tag, str):
                continue
            if node is bar:
                seen_bar = True
                continue
            if _own_text_of(node):
                if not seen_bar and value_node is None:
                    value_node = node
                elif seen_bar and label_node is None:
                    label_node = node
        columns.insert(0, BarColumn(clone_root, bar, value_node, label_node,
                                    columns[0].height))

    # Высоты — линейно от нуля, как в самих шаблонах: столбец с максимумом
    # получает высоту самого высокого столбика дизайнера.
    top = max(value for _, value in points) or 1.0
    scale = chart.max_height / top
    for column, (label, value) in zip(columns, points):
        height = max(chart.max_height * MIN_BAR_RATIO, value * scale)
        style = HEIGHT_RE.sub(f"height:{height:.0f}px", column.bar.get("style") or "")
        column.bar.set("style", style)
        column.bar.set("data-chart-bound", "")
        if column.value_node is not None:
            column.value_node.text = _format_value(value)
            for child in column.value_node:
                child.tail = ""
            column.value_node.set("data-chart-bound", "")
        if column.label_node is not None:
            column.label_node.text = label
            for child in column.label_node:
                child.tail = ""
            column.label_node.set("data-chart-bound", "")
    return True


def detect_chart(section: etree._Element) -> str | None:
    """Какая диаграмма есть в секции: секторная, столбиковая или никакой."""
    count = 0
    for path in section.iter():
        if not isinstance(path.tag, str) or not path.tag.endswith("path"):
            continue
        d = (path.get("d") or "").strip()
        fill = path.get("fill") or ""
        if fill and fill != "none" and FIRST_ARC_RE.match(d):
            count += 1
    if count >= 2:
        return "sector"
    if parse_bar_chart(section) is not None:
        return "bars"
    return None


def numeric(value: str) -> float | None:
    """Число из значения метрики: «34 %» -> 34, «1,5 дня» -> 1.5."""
    match = re.search(r"-?\d+(?:[.,]\d+)?", value)
    if not match:
        return None
    return float(match.group(0).replace(",", "."))


def chart_values(metrics: list[tuple[str, str]]) -> list[float]:
    """Значения для диаграммы из метрик слайда.

    Проценты предпочтительнее абсолютных чисел: донат читается как доли, и
    смешивать «34 %» с «6 дней» нельзя — доли выйдут бессмысленными.
    """
    percents = [numeric(value) for value, _ in metrics if "%" in value]
    percents = [value for value in percents if value]
    if len(percents) >= 2:
        return percents
    numbers = [numeric(value) for value, _ in metrics]
    return [value for value in numbers if value]
