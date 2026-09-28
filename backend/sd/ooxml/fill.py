"""Заливки: прямые, через стилевую матрицу темы и фоновые.

В шаблонах цвет шейпа чаще задан не напрямую, а ссылкой в стилевую матрицу темы
(`p:style/a:fillRef idx="2"` + цвет, который подставляется вместо `phClr`).
Если это не разворачивать, половина палитры шаблона остаётся невидимой.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Literal

from lxml import etree

from .color import ResolvedColor, first_color_element, resolve_color
from .ns import NS, attr_int, local_name

FillKind = Literal["none", "solid", "gradient", "picture", "pattern", "inherit"]


@dataclass
class StyleContext:
    """Всё, что нужно, чтобы развернуть цвет в конкретной части пакета."""

    scheme: dict[str, str]
    clr_map: dict[str, str] = field(default_factory=dict)
    fmt_scheme: etree._Element | None = None

    def resolve(self, elem: etree._Element | None,
                phclr: str | None = None) -> ResolvedColor | None:
        return resolve_color(elem, self.scheme, self.clr_map, phclr)


@dataclass
class Fill:
    kind: FillKind = "inherit"
    color: ResolvedColor | None = None
    stops: list[ResolvedColor] = field(default_factory=list)
    image_rid: str | None = None
    via_style: bool = False

    @property
    def hex(self) -> str | None:
        return self.color.hex if self.color else None


FILL_TAGS = ("noFill", "solidFill", "gradFill", "blipFill", "pattFill", "grpFill")


def _fill_child(container: etree._Element | None) -> etree._Element | None:
    if container is None:
        return None
    for child in container:
        if isinstance(child.tag, str) and local_name(child) in FILL_TAGS:
            return child
    return None


def read_fill(container: etree._Element | None, ctx: StyleContext,
              phclr: str | None = None) -> Fill:
    """Заливка из `spPr` / `bgPr` / `rPr` — то, что задано явно."""
    node = _fill_child(container)
    if node is None:
        return Fill("inherit")

    kind = local_name(node)
    if kind == "noFill":
        return Fill("none")
    if kind == "solidFill":
        return Fill("solid", ctx.resolve(first_color_element(node), phclr))
    if kind == "gradFill":
        stops = []
        for gs in node.findall("a:gsLst/a:gs", NS):
            if color := ctx.resolve(first_color_element(gs), phclr):
                stops.append(color)
        return Fill("gradient", stops[0] if stops else None, stops)
    if kind == "blipFill":
        blip = node.find(".//a:blip", NS)
        rid = blip.get(f"{{{NS['r']}}}embed") if blip is not None else None
        return Fill("picture", image_rid=rid)
    if kind == "pattFill":
        fg = node.find("a:fgClr", NS)
        return Fill("pattern", ctx.resolve(first_color_element(fg), phclr))
    return Fill("inherit")


def _keep_slot(fill: Fill, phclr: ResolvedColor | None) -> Fill:
    """Если цвет пришёл из `phClr`, сохраняем слот темы — иначе теряется провенанс."""
    if phclr is not None and fill.color is not None and fill.color.scheme_slot is None \
            and fill.color.hex == phclr.hex:
        fill.color = phclr
    return fill


def _style_matrix_fill(idx: int, ctx: StyleContext, phclr: str | None) -> Fill:
    """Разворачивает `a:fillRef idx` по `fmtScheme` темы."""
    if ctx.fmt_scheme is None or idx <= 0:
        return Fill("solid", ctx.resolve(None, phclr) if phclr else None)

    if idx >= 1000:
        lst = ctx.fmt_scheme.find("a:bgFillStyleLst", NS)
        pos = idx - 1000
    else:
        lst = ctx.fmt_scheme.find("a:fillStyleLst", NS)
        pos = idx

    if lst is None or pos < 1 or pos > len(lst):
        return Fill("inherit")

    # Кладём копию узла в отдельный контейнер: read_fill ищет заливку среди детей.
    holder = etree.Element("holder")
    holder.append(etree.fromstring(etree.tostring(lst[pos - 1])))
    return read_fill(holder, ctx, phclr)


def shape_fill(sp_pr: etree._Element | None, style: etree._Element | None,
               ctx: StyleContext) -> Fill:
    """Итоговая заливка шейпа: явная важнее стилевой ссылки."""
    direct = read_fill(sp_pr, ctx)
    if direct.kind != "inherit":
        return direct

    if style is not None:
        fill_ref = style.find("a:fillRef", NS)
        if fill_ref is not None:
            phclr = ctx.resolve(first_color_element(fill_ref))
            fill = _style_matrix_fill(attr_int(fill_ref, "idx", 0) or 0, ctx,
                                      phclr.hex if phclr else None)
            if fill.kind in ("solid", "gradient", "pattern") and fill.color is None:
                fill = Fill(fill.kind, phclr, fill.stops)
            _keep_slot(fill, phclr)
            fill.via_style = True
            if fill.kind != "inherit":
                return fill
            if phclr:
                return Fill("solid", phclr, via_style=True)
    return Fill("inherit")


def line_color(sp_pr: etree._Element | None, style: etree._Element | None,
               ctx: StyleContext) -> ResolvedColor | None:
    line = sp_pr.find("a:ln", NS) if sp_pr is not None else None
    if line is not None:
        if line.find("a:noFill", NS) is not None:
            return None
        if (color := ctx.resolve(first_color_element(line))) is not None:
            return color
    if style is not None:
        ln_ref = style.find("a:lnRef", NS)
        if ln_ref is not None:
            return ctx.resolve(first_color_element(ln_ref))
    return None


def background_fill(bg: etree._Element | None, ctx: StyleContext) -> Fill:
    """Фон части: `p:bgPr` (явно) или `p:bgRef` (ссылка в стилевую матрицу)."""
    if bg is None:
        return Fill("inherit")

    bg_pr = bg.find("p:bgPr", NS)
    if bg_pr is not None:
        return read_fill(bg_pr, ctx)

    bg_ref = bg.find("p:bgRef", NS)
    if bg_ref is not None:
        phclr = ctx.resolve(first_color_element(bg_ref))
        fill = _style_matrix_fill(attr_int(bg_ref, "idx", 0) or 0, ctx,
                                  phclr.hex if phclr else None)
        if fill.kind == "inherit" and phclr:
            return Fill("solid", phclr, via_style=True)
        _keep_slot(fill, phclr)
        fill.via_style = True
        return fill
    return Fill("inherit")


def read_clr_map(master_root: etree._Element) -> dict[str, str]:
    """`p:clrMap` мастера: bg1->lt1, tx1->dk1, … Без этого `schemeClr bg1` не развернуть."""
    node = master_root.find("p:clrMap", NS)
    if node is None:
        return {"bg1": "lt1", "tx1": "dk1", "bg2": "lt2", "tx2": "dk2"}
    return {key: value for key, value in node.attrib.items()}
