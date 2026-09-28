"""Сетка шаблона: поля, направляющие, колонки, безопасная зона, ритм отступов.

В шаблоне нет объекта «сетка» — она существует только как совпадение координат
десятков шейпов по разным макетам. Поэтому ищем её статистически: собираем
границы всех шейпов, кластеризуем по одной оси и берём кластеры с поддержкой.
Совпадение трёх и более границ на одной линии — это не случайность, а
направляющая, которую держал дизайнер.
"""

from __future__ import annotations

from dataclasses import dataclass
from statistics import median

from ..ooxml.package import Package
from ..ooxml.shapes import Shape
from .model import Columns, Geometry

# Допуск склейки границ в долях стороны слайда: 0.5 % — это ~4 мм на слайде 4:3.
TOLERANCE = 0.005
MIN_SUPPORT = 3
# Шейп, занимающий почти весь слайд, — это фон, а не элемент сетки.
FULL_BLEED = 0.85


@dataclass
class Cluster:
    center: float
    support: int
    values: list[float]


def cluster_1d(values: list[float], tolerance: float = TOLERANCE) -> list[Cluster]:
    """Одномерная кластеризация по разрыву: соседние значения ближе допуска — одна линия."""
    if not values:
        return []
    ordered = sorted(values)
    clusters: list[list[float]] = [[ordered[0]]]
    for value in ordered[1:]:
        if value - clusters[-1][-1] <= tolerance:
            clusters[-1].append(value)
        else:
            clusters.append([value])
    return [Cluster(round(sum(group) / len(group), 5), len(group), group)
            for group in clusters]


def _content_shapes(pkg: Package, parts: list[str]) -> list[tuple[str, Shape]]:
    """Шейпы, которые формируют сетку: без служебных плейсхолдеров и подложек."""
    width, height = pkg.slide_size
    result: list[tuple[str, Shape]] = []
    for part in parts:
        for shape in pkg.shapes(part):
            if shape.is_chrome or shape.cx <= 0 or shape.cy <= 0:
                continue
            if shape.cx / width > FULL_BLEED and shape.cy / height > FULL_BLEED:
                continue
            result.append((part, shape))
    return result


def extract_geometry(pkg: Package) -> Geometry:
    width, height = pkg.slide_size
    shapes = _content_shapes(pkg, [*pkg.layouts, *pkg.slides])
    if not shapes:
        return Geometry()

    lefts, rights, tops, bottoms = [], [], [], []
    for _, shape in shapes:
        lefts.append(shape.x / width)
        rights.append((shape.x + shape.cx) / width)
        tops.append(shape.y / height)
        bottoms.append((shape.y + shape.cy) / height)

    guides_x = [c.center for c in cluster_1d(lefts + rights) if c.support >= MIN_SUPPORT]
    guides_y = [c.center for c in cluster_1d(tops + bottoms) if c.support >= MIN_SUPPORT]

    margins = _margins(pkg, width, height, shapes)
    gutter = _gutter(shapes, width, height)
    content_width = max(0.0, 1.0 - margins["l"] - margins["r"])
    columns = _column_count(pkg, shapes, width, content_width, gutter)

    safe_area, gaps = _safe_area(pkg, height, margins["l"], margins["r"], margins["b"])

    return Geometry(
        margins=margins,
        columns=Columns(count=columns, gutter=round(gutter, 4),
                        width=round((content_width - gutter * (columns - 1)) / columns, 4)
                        if columns else 0.0),
        guides_x=guides_x,
        guides_y=guides_y,
        safe_area=safe_area,
        gaps=gaps,
    )


def _layout_extents(pkg: Package, width: int, height: int,
                    fallback: list[tuple[str, Shape]]
                    ) -> list[tuple[float, float, float, float]]:
    """Габариты контента каждого макета отдельно: (л, п, в, н) в долях."""
    extents: list[tuple[float, float, float, float]] = []
    for part in pkg.layouts:
        shapes = [s for s in pkg.shapes(part)
                  if s.is_content_placeholder and s.cx > 0 and s.cy > 0
                  and s.cx / width < FULL_BLEED and s.cy / height < FULL_BLEED]
        if not shapes:
            continue
        extents.append((
            min(s.x for s in shapes) / width,
            max(s.x + s.cx for s in shapes) / width,
            min(s.y for s in shapes) / height,
            max(s.y + s.cy for s in shapes) / height,
        ))
    if extents:
        return extents
    # Шаблон без плейсхолдеров — считаем по всем содержательным шейпам.
    by_part: dict[str, list[Shape]] = {}
    for part, shape in fallback:
        by_part.setdefault(part, []).append(shape)
    return [(min(s.x for s in items) / width, max(s.x + s.cx for s in items) / width,
             min(s.y for s in items) / height, max(s.y + s.cy for s in items) / height)
            for items in by_part.values()]


def _margins(pkg: Package, width: int, height: int,
             fallback: list[tuple[str, Shape]]) -> dict[str, float]:
    """Поля — медиана габаритов контента по макетам.

    Каждый макет голосует своими крайними плейсхолдерами, медиана гасит выбросы:
    один макет с полноэкранной картинкой не сдвигает поля всего шаблона, а
    декоративные шейпы в расчёт вообще не входят.
    """
    extents = _layout_extents(pkg, width, height, fallback)
    if not extents:
        return {"l": 0.05, "r": 0.05, "t": 0.05, "b": 0.05}
    return {
        "l": round(median(e[0] for e in extents), 4),
        "r": round(max(0.0, 1.0 - median(e[1] for e in extents)), 4),
        "t": round(median(e[2] for e in extents), 4),
        "b": round(max(0.0, 1.0 - median(e[3] for e in extents)), 4),
    }


def _gutter(shapes: list[tuple[str, Shape]], width: int, height: int) -> float:
    """Межколоночник — мода горизонтальных зазоров между соседями в одной строке."""
    gaps: list[float] = []
    by_part: dict[str, list[Shape]] = {}
    for part, shape in shapes:
        by_part.setdefault(part, []).append(shape)

    for items in by_part.values():
        ordered = sorted(items, key=lambda s: s.x)
        for first, second in zip(ordered, ordered[1:]):
            overlap = min(first.y + first.cy, second.y + second.cy) - max(first.y, second.y)
            if overlap <= 0.5 * min(first.cy, second.cy):
                continue                                  # шейпы не в одной строке
            gap = (second.x - (first.x + first.cx)) / width
            if 0.002 < gap < 0.12:
                gaps.append(gap)
    if not gaps:
        return 0.02
    modal = cluster_1d(gaps, TOLERANCE)
    return max(modal, key=lambda c: c.support).center


def _column_count(pkg: Package, shapes: list[tuple[str, Shape]], width: int,
                  content_width: float, gutter: float) -> int:
    """Число колонок — по самому узкому типовому блоку контента.

    Берём ширины плейсхолдеров (декор колонок не задаёт) и среди кластеров с
    поддержкой ≥ 2 выбираем самый узкий: он и есть ширина одной колонки.
    """
    widths = [shape.cx / width for _, shape in shapes
              if shape.is_content_placeholder and 0.04 < shape.cx / width <= content_width + 0.02]
    if not widths:
        widths = [shape.cx / width for _, shape in shapes
                  if 0.04 < shape.cx / width <= content_width + 0.02]
    if not widths or content_width <= 0:
        return 12

    clusters = cluster_1d(widths, TOLERANCE * 2)
    supported = [c for c in clusters if c.support >= 2] or clusters
    narrow = min(supported, key=lambda c: c.center).center
    if narrow <= 0:
        return 12
    return max(1, min(24, round((content_width + gutter) / (narrow + gutter))))


def _safe_area(pkg: Package, height: int, left: float, right: float,
               bottom: float) -> tuple[list[float], dict]:
    """Зона под контент: между низом заголовка и нижним полем."""
    title_bottoms: list[float] = []
    body_tops: list[float] = []
    item_gaps: list[float] = []
    title_to_body: list[float] = []

    for part in pkg.layouts:
        placeholders = [s for s in pkg.shapes(part) if s.is_content_placeholder]
        titles = [s for s in placeholders if s.ph_type in ("title", "ctrTitle")]
        bodies = sorted((s for s in placeholders if s.ph_type not in ("title", "ctrTitle")),
                        key=lambda s: s.y)
        if titles:
            title_bottoms.append((titles[0].y + titles[0].cy) / height)
        if bodies:
            body_tops.append(bodies[0].y / height)
        if titles and bodies:
            # Считаем зазор внутри макета: сравнивать медианы по разным макетам
            # бессмысленно — у полноширинной плашки заголовка низ ниже верха тела.
            gap = (bodies[0].y - (titles[0].y + titles[0].cy)) / height
            if 0.0 <= gap < 0.3:
                title_to_body.append(gap)
        for first, second in zip(bodies, bodies[1:]):
            gap = (second.y - (first.y + first.cy)) / height
            if 0.002 < gap < 0.2:
                item_gaps.append(gap)

    top = median(body_tops) if body_tops else (median(title_bottoms) if title_bottoms else 0.2)
    safe = [round(left, 4), round(top, 4),
            round(max(0.0, 1.0 - left - right), 4),
            round(max(0.0, 1.0 - top - bottom), 4)]

    gaps = {}
    if title_to_body:
        gaps["title_to_body"] = round(median(title_to_body), 4)
    if item_gaps:
        gaps["between_items"] = round(median(item_gaps), 4)
    return safe, gaps
