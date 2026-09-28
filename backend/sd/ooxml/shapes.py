"""Нормализованный обход дерева шейпов слайда, макета или мастера.

Дальше по пайплайну всем нужен один и тот же набор фактов о шейпе: где он лежит
в абсолютных координатах, какой у него плейсхолдер, чем залит и какой текст
внутри. Собираем это один раз здесь, чтобы палитра, сетка, декор и извлечение
паттернов смотрели на одну структуру.
"""

from __future__ import annotations

from dataclasses import dataclass, field

from lxml import etree

from .ns import NS, attr_int, local_name

# Типы плейсхолдеров, которые несут контент (остальное — служебное: дата, номер).
CONTENT_PH = {"title", "ctrTitle", "subTitle", "body", "obj", "pic", "chart",
              "tbl", "dgm", "media", "clipArt"}
CHROME_PH = {"dt", "ftr", "sldNum", "hdr"}


@dataclass
class Run:
    text: str
    rpr: etree._Element | None = None


@dataclass
class Paragraph:
    level: int = 0
    runs: list[Run] = field(default_factory=list)
    ppr: etree._Element | None = None
    is_field: bool = False        # номер слайда/дата — не контент

    @property
    def text(self) -> str:
        return "".join(run.text for run in self.runs)


@dataclass
class Shape:
    part: str
    shape_id: int
    name: str
    tag: str                              # sp | pic | graphicFrame | cxnSp | grpSp
    x: int = 0
    y: int = 0
    cx: int = 0
    cy: int = 0
    rot: int = 0
    flip_h: bool = False
    flip_v: bool = False
    ph_type: str | None = None
    ph_idx: int | None = None
    prst_geom: str | None = None
    graphic_kind: str | None = None       # chart | table | diagram | ole
    element: etree._Element | None = None
    tx_body: etree._Element | None = None
    paragraphs: list[Paragraph] = field(default_factory=list)
    group_path: tuple[str, ...] = ()
    geometry_inherited: bool = False

    # --- удобные признаки ---------------------------------------------------

    @property
    def is_placeholder(self) -> bool:
        return self.ph_type is not None or self.ph_idx is not None

    @property
    def is_content_placeholder(self) -> bool:
        if not self.is_placeholder:
            return False
        return (self.ph_type or "body") in CONTENT_PH

    @property
    def is_chrome(self) -> bool:
        return self.ph_type in CHROME_PH

    @property
    def text(self) -> str:
        return "\n".join(p.text for p in self.paragraphs if not p.is_field).strip()

    @property
    def area(self) -> int:
        return max(0, self.cx) * max(0, self.cy)

    def bbox_fraction(self, width: int, height: int) -> list[float]:
        return [round(self.x / width, 5), round(self.y / height, 5),
                round(self.cx / width, 5), round(self.cy / height, 5)]

    def sp_pr(self) -> etree._Element | None:
        if self.element is None:
            return None
        for tag in ("p:spPr", "p:grpSpPr"):
            node = self.element.find(tag, NS)
            if node is not None:
                return node
        return None

    def style(self) -> etree._Element | None:
        return self.element.find("p:style", NS) if self.element is not None else None


def _read_xfrm(node: etree._Element | None) -> tuple[int, int, int, int, int, bool, bool]:
    if node is None:
        return 0, 0, 0, 0, 0, False, False
    off = node.find("a:off", NS)
    ext = node.find("a:ext", NS)
    return (attr_int(off, "x", 0) or 0, attr_int(off, "y", 0) or 0,
            attr_int(ext, "cx", 0) or 0, attr_int(ext, "cy", 0) or 0,
            attr_int(node, "rot", 0) or 0,
            node.get("flipH") == "1", node.get("flipV") == "1")


def _parse_text(tx_body: etree._Element | None) -> list[Paragraph]:
    paragraphs: list[Paragraph] = []
    if tx_body is None:
        return paragraphs
    for p_el in tx_body.findall("a:p", NS):
        ppr = p_el.find("a:pPr", NS)
        para = Paragraph(level=attr_int(ppr, "lvl", 0) or 0, ppr=ppr)
        for child in p_el:
            if not isinstance(child.tag, str):
                continue
            name = local_name(child)
            if name == "r":
                text_el = child.find("a:t", NS)
                para.runs.append(Run(text_el.text or "" if text_el is not None else "",
                                     child.find("a:rPr", NS)))
            elif name == "fld":
                text_el = child.find("a:t", NS)
                para.runs.append(Run(text_el.text or "" if text_el is not None else "",
                                     child.find("a:rPr", NS)))
                para.is_field = True
            elif name == "br":
                para.runs.append(Run("\n"))
        paragraphs.append(para)
    return paragraphs


def _graphic_kind(node: etree._Element) -> str | None:
    data = node.find("a:graphic/a:graphicData", NS)
    uri = data.get("uri", "") if data is not None else ""
    if "chart" in uri:
        return "chart"
    if "table" in uri:
        return "table"
    if "diagram" in uri:
        return "diagram"
    if "ole" in uri:
        return "ole"
    return None


def _walk(container: etree._Element, part: str, offset: tuple[float, float],
          scale: tuple[float, float], path: tuple[str, ...],
          out: list[Shape]) -> None:
    for node in container:
        if not isinstance(node.tag, str):
            continue
        tag = local_name(node)
        if tag not in ("sp", "pic", "graphicFrame", "cxnSp", "grpSp"):
            continue

        nv = node.find(".//p:cNvPr", NS)
        shape_id = attr_int(nv, "id", 0) or 0
        name = (nv.get("name") if nv is not None else "") or ""

        if tag == "graphicFrame":
            xfrm = node.find("p:xfrm", NS)
        elif tag == "grpSp":
            xfrm = node.find("p:grpSpPr/a:xfrm", NS)
        else:
            xfrm = node.find("p:spPr/a:xfrm", NS)
        raw_x, raw_y, raw_cx, raw_cy, rot, flip_h, flip_v = _read_xfrm(xfrm)

        x = offset[0] + raw_x * scale[0]
        y = offset[1] + raw_y * scale[1]
        cx = raw_cx * scale[0]
        cy = raw_cy * scale[1]

        if tag == "grpSp":
            # У группы своя система координат: chOff/chExt отображаются в off/ext.
            grp_xfrm = node.find("p:grpSpPr/a:xfrm", NS)
            ch_off = grp_xfrm.find("a:chOff", NS) if grp_xfrm is not None else None
            ch_ext = grp_xfrm.find("a:chExt", NS) if grp_xfrm is not None else None
            ch_x = attr_int(ch_off, "x", 0) or 0
            ch_y = attr_int(ch_off, "y", 0) or 0
            ch_cx = attr_int(ch_ext, "cx", 0) or 0
            ch_cy = attr_int(ch_ext, "cy", 0) or 0
            sx = (cx / ch_cx) if ch_cx else scale[0]
            sy = (cy / ch_cy) if ch_cy else scale[1]
            _walk(node, part, (x - ch_x * sx, y - ch_y * sy), (sx, sy),
                  path + (name,), out)
            continue

        ph = node.find(".//p:nvSpPr/p:nvPr/p:ph", NS)
        if ph is None:
            ph = node.find(".//p:nvPr/p:ph", NS)

        tx_body = node.find("p:txBody", NS)
        prst = node.find(".//a:prstGeom", NS)

        out.append(Shape(
            part=part, shape_id=shape_id, name=name, tag=tag,
            x=int(x), y=int(y), cx=int(cx), cy=int(cy),
            rot=rot, flip_h=flip_h, flip_v=flip_v,
            ph_type=ph.get("type", "body") if ph is not None else None,
            ph_idx=attr_int(ph, "idx", None) if ph is not None else None,
            prst_geom=prst.get("prst") if prst is not None else None,
            graphic_kind=_graphic_kind(node) if tag == "graphicFrame" else None,
            element=node, tx_body=tx_body, paragraphs=_parse_text(tx_body),
            group_path=path,
        ))


def iter_shapes(root: etree._Element, part: str = "") -> list[Shape]:
    """Все шейпы части в порядке отрисовки, координаты — абсолютные EMU."""
    tree = root.find(".//p:cSld/p:spTree", NS)
    if tree is None:
        return []
    shapes: list[Shape] = []
    _walk(tree, part, (0.0, 0.0), (1.0, 1.0), (), shapes)
    return shapes


def match_placeholder(shapes: list[Shape], ph_type: str | None,
                      ph_idx: int | None) -> Shape | None:
    """Родительский плейсхолдер в макете или мастере.

    PowerPoint ищет пару так: заголовок — по типу, остальное — по `idx`, а если
    не нашлось, то по типу. От этого зависит и наследование стиля, и координат.
    """
    if ph_type in ("title", "ctrTitle"):
        for shape in shapes:
            if shape.ph_type in ("title", "ctrTitle"):
                return shape
    if ph_idx is not None:
        for shape in shapes:
            if shape.ph_idx == ph_idx:
                return shape
    for shape in shapes:
        if shape.ph_type == ph_type:
            return shape
    if ph_type in ("body", "obj", None):
        for shape in shapes:
            if shape.ph_type in ("body", "obj"):
                return shape
    return None


def background_element(root: etree._Element) -> etree._Element | None:
    """`p:bg` части — заливка фона слайда/макета/мастера."""
    return root.find("p:cSld/p:bg", NS)
