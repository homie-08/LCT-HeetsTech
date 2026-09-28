"""Декор шаблона: логотипы, плашки, линии и общий характер фигур.

Декор — это всё, что нарисовано на мастере и макетах, но не является
плейсхолдером: он и создаёт узнаваемость шаблона. Нам он нужен дважды: чтобы
не заезжать на него контентом (участвует в безопасной зоне) и чтобы при
клонировании слайда-примера понимать, что трогать нельзя.
"""

from __future__ import annotations

from collections import Counter

from ..ooxml.fill import shape_fill
from ..ooxml.ns import NS, attr_int
from ..ooxml.package import Package
from ..ooxml.shapes import Shape
from .model import Decor, DecorItem
from .palette import build_context

LOGO_MAX_AREA = 0.05      # доля площади слайда
BAR_MAX_THICKNESS = 0.04  # доля стороны слайда
EDGE_ZONE = 0.2           # насколько близко к краю, чтобы считаться угловым


def _classify(shape: Shape, width: int, height: int) -> str:
    w = shape.cx / width
    h = shape.cy / height
    area = w * h

    if shape.tag == "pic":
        return "logo" if area <= LOGO_MAX_AREA else "picture"
    if shape.tag == "cxnSp":
        return "line"
    if (h <= BAR_MAX_THICKNESS and w >= 0.3) or (w <= BAR_MAX_THICKNESS and h >= 0.3):
        return "bar"
    return "shape"


def _corner(shape: Shape, width: int, height: int) -> str:
    cx = (shape.x + shape.cx / 2) / width
    cy = (shape.y + shape.cy / 2) / height
    vertical = "t" if cy < EDGE_ZONE else ("b" if cy > 1 - EDGE_ZONE else "c")
    horizontal = "l" if cx < EDGE_ZONE else ("r" if cx > 1 - EDGE_ZONE else "c")
    return vertical + horizontal


def extract_decor(pkg: Package) -> Decor:
    width, height = pkg.slide_size
    grouped: dict[tuple, DecorItem] = {}
    corner_radii: list[int] = []
    line_widths: list[float] = []
    shadows = 0
    total_shapes = 0

    parts = [(part, "master") for part in pkg.masters]
    parts += [(part, f"layout:{pkg.name_of(part)}") for part in pkg.layouts]

    for part, scope in parts:
        ctx = build_context(pkg, part)
        for shape in pkg.shapes(part):
            if shape.is_placeholder or shape.cx <= 0 or shape.cy <= 0:
                continue
            total_shapes += 1

            sp_pr, style = shape.sp_pr(), shape.style()
            fill = shape_fill(sp_pr, style, ctx)
            kind = _classify(shape, width, height)

            image = None
            if shape.tag == "pic" and shape.element is not None:
                blip = shape.element.find(".//a:blip", NS)
                rid = blip.get(f"{{{NS['r']}}}embed") if blip is not None else None
                image = pkg.target(part, rid) if rid else None

            bbox = shape.bbox_fraction(width, height)
            key = (kind, tuple(round(v, 3) for v in bbox), fill.hex, image)
            if key in grouped:
                grouped[key].scope.append(scope)
            else:
                grouped[key] = DecorItem(kind=kind, bbox=bbox, fill=fill.hex,
                                         image=image, scope=[scope],
                                         geom=shape.prst_geom)

            # Характер фигур шаблона: скругления, толщина обводки, тени.
            if shape.prst_geom == "roundRect" and shape.element is not None:
                adj = shape.element.find(".//a:prstGeom/a:avLst/a:gd", NS)
                corner_radii.append(attr_int(adj, "fmla", 0) if adj is not None else 16667)
            elif shape.prst_geom == "rect":
                corner_radii.append(0)

            if sp_pr is not None:
                ln = sp_pr.find("a:ln", NS)
                if (w := attr_int(ln, "w", None)) is not None:
                    line_widths.append(w / 12700)
                if sp_pr.find("a:effectLst/a:outerShdw", NS) is not None:
                    shadows += 1

    items = sorted(grouped.values(), key=lambda item: -len(item.scope))

    shape_style = {
        "corner_radius_pct": Counter(corner_radii).most_common(1)[0][0] if corner_radii else 0,
        "line_width_pt": round(Counter(line_widths).most_common(1)[0][0], 2)
        if line_widths else 1.0,
        "shadow": total_shapes > 0 and shadows / max(total_shapes, 1) > 0.3,
    }
    return Decor(items=items, shape_style=shape_style)


def logo_items(decor: Decor) -> list[DecorItem]:
    return [item for item in decor.items if item.kind == "logo"]
