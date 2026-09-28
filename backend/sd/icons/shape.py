"""Пиктограмма как нативная фигура pptx: `custGeom` с обводкой цвета темы.

Не картинка: контур редактируется в PowerPoint, перекрашивается вместе с
темой и масштабируется без потери качества. Цвет обводки приходит из
дизайн-системы шаблона — слотом темы, если роль из него взята, иначе
значением; сама библиотека цвета не знает.
"""

from __future__ import annotations

from functools import lru_cache

from lxml import etree
from pptx.enum.shapes import MSO_SHAPE
from pptx.oxml.ns import qn
from pptx.util import Emu

from .library import SHAPES
from .svgpath import Command, parse_svg

# Система координат набора: центр в нуле, габарит ±8, запас под обводку.
ICON_EXTENT = 10.0
# Разрешение пространства контура: целые координаты, точности хватает с запасом.
PATH_SPACE = 10000
# Толщина обводки в единицах набора — как у Lucide при габарите 16.
STROKE_UNITS = 1.5

# Цвет для фигуры: ("scheme", "accent1") — слот темы, ("rgb", "0077FF") — значение.
IconColor = tuple[str, str]


@lru_cache(maxsize=None)
def icon_paths(name: str) -> tuple[tuple[Command, ...], ...]:
    """Контуры пиктограммы в координатах набора."""
    markup = SHAPES.get(name)
    if markup is None:
        raise KeyError(f"нет пиктограммы «{name}»")
    return tuple(tuple(path) for path in parse_svg(markup))


def _unit(value: float) -> int:
    scale = PATH_SPACE / (2 * ICON_EXTENT)
    return int(round((value + ICON_EXTENT) * scale))


def custom_geometry(name: str) -> etree._Element:
    """`a:custGeom` пиктограммы: контуры без заливки, только обводка."""
    geometry = etree.Element(qn("a:custGeom"))
    for tag in ("a:avLst", "a:gdLst", "a:ahLst", "a:cxnLst"):
        etree.SubElement(geometry, qn(tag))
    rect = etree.SubElement(geometry, qn("a:rect"))
    rect.set("l", "0"), rect.set("t", "0"), rect.set("r", "r"), rect.set("b", "b")
    path_list = etree.SubElement(geometry, qn("a:pathLst"))
    for path in icon_paths(name):
        node = etree.SubElement(path_list, qn("a:path"))
        node.set("w", str(PATH_SPACE))
        node.set("h", str(PATH_SPACE))
        node.set("fill", "none")
        for command in path:
            if command[0] == "M":
                _point(etree.SubElement(node, qn("a:moveTo")), command[1], command[2])
            elif command[0] == "L":
                _point(etree.SubElement(node, qn("a:lnTo")), command[1], command[2])
            elif command[0] == "C":
                curve = etree.SubElement(node, qn("a:cubicBezTo"))
                for index in range(1, 7, 2):
                    _point(curve, command[index], command[index + 1])
            elif command[0] == "Z":
                etree.SubElement(node, qn("a:close"))
    return geometry


def _point(parent: etree._Element, x: float, y: float) -> None:
    point = etree.SubElement(parent, qn("a:pt"))
    point.set("x", str(_unit(x)))
    point.set("y", str(_unit(y)))


def add_icon(slide, name: str, left: int, top: int, size: int, color: IconColor,
             label: str = ""):
    """Ставит пиктограмму `name` квадратом `size` EMU в точку (left, top)."""
    shape = slide.shapes.add_shape(MSO_SHAPE.RECTANGLE, Emu(left), Emu(top),
                                   Emu(size), Emu(size))
    shape.name = f"Пиктограмма: {label or name}"
    sp_pr = shape._element.spPr
    preset = sp_pr.find(qn("a:prstGeom"))
    geometry = custom_geometry(name)
    if preset is not None:
        preset.addprevious(geometry)
        sp_pr.remove(preset)
    else:
        sp_pr.append(geometry)

    shape.fill.background()
    line = shape.line
    line.width = Emu(int(size * STROKE_UNITS / (2 * ICON_EXTENT)))
    _apply_color(line.color, color)
    ln = sp_pr.find(qn("a:ln"))
    if ln is not None:
        ln.set("cap", "rnd")
        for tag in ("a:round", "a:bevel", "a:miter"):
            for old in ln.findall(qn(tag)):
                ln.remove(old)
        etree.SubElement(ln, qn("a:round"))
    # Фигура без текста: подсказка «Текст» на иконке не нужна.
    text_body = shape._element.find(qn("p:txBody"))
    if text_body is not None:
        shape._element.remove(text_body)
    strip_style(shape)
    return shape


def strip_style(shape) -> None:
    """Снимает ссылки на матрицу стилей темы: тень и заливка «по умолчанию»
    для фигур — не выбор дизайнера шаблона, а заготовка PowerPoint."""
    style = shape._element.find(qn("p:style"))
    if style is not None:
        shape._element.remove(style)


def _apply_color(color_format, color: IconColor) -> None:
    from pptx.dml.color import RGBColor
    from pptx.enum.dml import MSO_THEME_COLOR

    kind, value = color
    if kind == "scheme":
        color_format.theme_color = SCHEME_TO_THEME[value]
    else:
        color_format.rgb = RGBColor.from_string(value.lstrip("#"))


# Слоты темы в перечисление python-pptx.
SCHEME_TO_THEME = {
    "dk1": "TEXT_1", "lt1": "BACKGROUND_1", "dk2": "TEXT_2", "lt2": "BACKGROUND_2",
    "accent1": "ACCENT_1", "accent2": "ACCENT_2", "accent3": "ACCENT_3",
    "accent4": "ACCENT_4", "accent5": "ACCENT_5", "accent6": "ACCENT_6",
    "hlink": "HYPERLINK", "folHlink": "FOLLOWED_HYPERLINK",
}


def _resolve_theme_names() -> None:
    """Имена перечисления → члены: python-pptx хранит их как `MSO_THEME_COLOR.X`."""
    from pptx.enum.dml import MSO_THEME_COLOR

    for key, member in list(SCHEME_TO_THEME.items()):
        if isinstance(member, str):
            SCHEME_TO_THEME[key] = getattr(MSO_THEME_COLOR, member)


_resolve_theme_names()
