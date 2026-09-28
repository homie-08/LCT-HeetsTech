"""Проверки по разметке готового файла — без рендера.

Считают ровно то, что обещано в постановке: шрифты и цвета взяты из шаблона,
шейпы стоят по сетке, контент не потерялся, макеты не повторяются подряд.

Отдельно про смысл этих проверок. Собранный файл по построению не должен
содержать чужих шрифтов и цветов — сборщик их нигде не задаёт. Проверка нужна
не чтобы ловить ошибку, а чтобы утверждение «стиль только из шаблона» было
измеримым: на защите это число, а не обещание.
"""

from __future__ import annotations

import re

from ..content.model import ContentIR
from ..ooxml.color import hex_to_rgb
from ..ooxml.fill import shape_fill
from ..ooxml.ns import NS, attr_int
from ..ooxml.package import Package
from ..template.model import DesignSystem
from ..template.palette import build_context
from .model import Defect, Metrics

GRID_TOLERANCE = 0.008     # доля стороны слайда
COLOR_TOLERANCE = 0.06     # евклидово расстояние в RGB 0..1


def _close_to_palette(color: str, palette: list[str]) -> bool:
    try:
        target = hex_to_rgb(color)
    except (ValueError, IndexError):
        return False
    for candidate in palette:
        reference = hex_to_rgb(candidate)
        distance = sum((a - b) ** 2 for a, b in zip(target, reference)) ** 0.5
        if distance <= COLOR_TOLERANCE:
            return True
    return False


def check_fonts_and_colors(deck: Package, design: DesignSystem
                           ) -> tuple[float, float, list[Defect]]:
    """Доля ранов со шрифтом шаблона и доля заливок из палитры шаблона."""
    fonts = {name.lower() for name in
             [design.typography.fonts.major, design.typography.fonts.minor,
              *design.typography.fonts.embedded, *design.typography.fonts.used] if name}
    # Палитра шаблона — это не только его тема. Цвет, которым нарисована фигура
    # самого шаблона, «своим» быть обязан: иначе у шаблонов с инлайновыми
    # цветами нормоконтроль ругается на них же.
    palette = (list(design.palette.theme.values())
               + list(design.palette.roles.values())
               + list(design.palette.observed))

    runs_total = runs_ok = 0
    fills_total = fills_ok = 0
    defects: list[Defect] = []

    for index, part in enumerate(deck.slides, start=1):
        ctx = build_context(deck, part)
        for shape in deck.shapes(part):
            for paragraph in shape.paragraphs:
                for run in paragraph.runs:
                    if not run.text.strip() or run.rpr is None:
                        continue
                    latin = run.rpr.find("a:latin", NS)
                    typeface = (latin.get("typeface") if latin is not None else None)
                    if typeface is None:
                        continue                       # шрифт унаследован из шаблона
                    runs_total += 1
                    if typeface.lower() in fonts or typeface.startswith("+"):
                        runs_ok += 1
                    else:
                        defects.append(Defect(kind="font", severity="error", slide=index,
                                              message=f"чужой шрифт «{typeface}»"))

            fill = shape_fill(shape.sp_pr(), shape.style(), ctx)
            if fill.hex is None:
                continue
            fills_total += 1
            if fill.color.scheme_slot or _close_to_palette(fill.hex, palette):
                fills_ok += 1
            else:
                defects.append(Defect(kind="palette", severity="warning", slide=index,
                                      message=f"цвет {fill.hex} вне палитры шаблона"))

    return (runs_ok / runs_total if runs_total else 1.0,
            fills_ok / fills_total if fills_total else 1.0,
            defects)


# Фигуры схемы процесса и пиктограммы: их ставит композитор внутри поля,
# выровненного по макету, а внутренняя сетка схемы — её собственная.
DIAGRAM_SHAPE_RE = re.compile(r"^(Шаг \d+:|Стрелка \d+|Пиктограмма:)")


def check_grid(deck: Package, design: DesignSystem) -> tuple[float, list[Defect]]:
    """Доля шейпов с содержанием, чьи границы попадают в направляющие шаблона.

    Направляющие — это и явные линии сетки, и края слотов в макетах шаблона:
    там, куда дизайнер сам поставил поле, стоять можно. Судятся только шейпы
    с нашим содержанием — текст, таблицы, диаграммы, картинки; декор макета
    (плашки, линии) остался там, где его оставил дизайнер, и не наш."""
    guides_x = set(design.geometry.guides_x)
    guides_y = set(design.geometry.guides_y)
    if not guides_x or not guides_y:
        return 1.0, []
    for pattern in design.patterns:
        for slot in pattern.slots:
            x, y, w, h = slot.bbox
            guides_x.update((round(x, 4), round(x + w, 4)))
            guides_y.update((round(y, 4), round(y + h, 4)))

    width, height = deck.slide_size
    aligned = total = 0
    defects: list[Defect] = []

    for index, part in enumerate(deck.slides, start=1):
        for shape in deck.shapes(part):
            if shape.cx <= 0 or shape.cy <= 0 or shape.is_chrome:
                continue
            if not (shape.text or shape.graphic_kind or shape.tag == "pic"):
                continue                                # декор шаблона
            if DIAGRAM_SHAPE_RE.match(shape.name or ""):
                continue                                # части схемы: своя сетка внутри поля
            total += 1
            left, top = shape.x / width, shape.y / height
            on_grid = (min((abs(left - guide) for guide in guides_x), default=1)
                       <= GRID_TOLERANCE
                       and min((abs(top - guide) for guide in guides_y), default=1)
                       <= GRID_TOLERANCE)
            if on_grid:
                aligned += 1
            elif shape.tag != "graphicFrame":
                defects.append(Defect(
                    kind="grid", severity="info", slide=index,
                    message=f"шейп «{shape.name[:24]}» не по направляющим",
                    bbox=shape.bbox_fraction(width, height)))
    return (aligned / total if total else 1.0), defects


def check_coverage(ir: ContentIR, filled_slides) -> tuple[float, list[Defect]]:
    """Какая доля значимого контента реально попала на слайды."""
    significant = [block for block in ir.blocks
                   if block.type not in ("heading", "image") and block.size > 0]
    if not significant:
        return 1.0, []

    placed: set[str] = set()
    dropped: list[Defect] = []
    for slide in filled_slides:
        for fill in slide.fills:
            if fill.block_id:
                placed.add(fill.block_id)
        for text in slide.dropped:
            dropped.append(Defect(kind="coverage", severity="warning", slide=slide.n,
                                  message=f"не размещён фрагмент «{text[:60].strip()}…»",
                                  detail=text[:90]))

    # Блок считается размещённым и тогда, когда его текст ушёл в слот через
    # общий поток: сверяем по вхождению текста в заполненные слоты.
    rendered = " \n".join(fill.text + " ".join(fill.items)
                          for slide in filled_slides for fill in slide.fills)
    for block in significant:
        if block.id in placed:
            continue
        probe = (block.text or (block.items[0] if block.items else block.label))[:40]
        if probe and probe in rendered:
            placed.add(block.id)
            continue
        # Список, замененный на слайде метриками, потерянным не считается:
        # его содержание представлено производными блоками.
        derived = [metric for metric in ir.blocks if metric.derived_from == block.id]
        if derived and any(metric.id in placed
                           or (metric.label and metric.label[:30] in rendered)
                           for metric in derived):
            placed.add(block.id)

    return len(placed & {block.id for block in significant}) / len(significant), dropped


def check_diversity(filled_slides) -> tuple[float, list[Defect]]:
    patterns = [slide.pattern.id for slide in filled_slides]
    if not patterns:
        return 0.0, []
    defects = [
        Defect(kind="diversity", severity="info", slide=index + 2,
               message="тот же макет, что и на предыдущем слайде")
        for index, (previous, current) in enumerate(zip(patterns, patterns[1:]))
        if previous == current
    ]
    return len(set(patterns)) / len(patterns), defects


def static_report(deck_path, design: DesignSystem, ir: ContentIR, filled_slides
                  ) -> tuple[Metrics, list[Defect]]:
    deck = Package.open(deck_path)
    font_score, palette_score, defects = check_fonts_and_colors(deck, design)
    grid_score, grid_defects = check_grid(deck, design)
    coverage, coverage_defects = check_coverage(ir, filled_slides)
    diversity, diversity_defects = check_diversity(filled_slides)

    metrics = Metrics(
        font_conformance=round(font_score, 4),
        palette_conformance=round(palette_score, 4),
        grid_alignment=round(grid_score, 4),
        pattern_diversity=round(diversity, 4),
        coverage=round(coverage, 4),
        slides=len(deck.slides),
    )
    return metrics, defects + grid_defects + coverage_defects + diversity_defects
