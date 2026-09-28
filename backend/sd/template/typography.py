"""Типографика шаблона: пары шрифтов, шкала кеглей, стили ролей текста.

Свойства текста в PowerPoint наследуются по цепочке
`txStyles мастера → плейсхолдер мастера → плейсхолдер макета → шейп слайда →
абзац → ран`, и каждое звено переопределяет только часть свойств. Поэтому
кегль заголовка почти никогда не написан там, где его ищут: без разворачивания
цепочки шаблон читается неправильно.
"""

from __future__ import annotations

from collections import Counter
from dataclasses import dataclass, field

from lxml import etree

from ..ooxml.fill import StyleContext, read_fill
from ..ooxml.ns import NS, attr_int, local_name
from ..ooxml.package import Package
from ..ooxml.shapes import Shape, match_placeholder
from .model import Bullet, Fonts, TextStyle, Typography
from .palette import build_context

# Какой раздел `p:txStyles` мастера отвечает за плейсхолдер данного типа.
PH_CATEGORY = {
    "title": "title", "ctrTitle": "title",
    "body": "body", "subTitle": "body", "obj": "body",
    "dt": "other", "ftr": "other", "sldNum": "other", "hdr": "other",
}

ALIGN_MAP = {"l": "l", "ctr": "ctr", "r": "r", "just": "just", "justLow": "just",
             "dist": "just", "thaiDist": "just"}


@dataclass
class RawStyle:
    """Промежуточное представление: None означает «не задано на этом уровне»."""

    font: str | None = None
    size_pt: float | None = None
    bold: bool | None = None
    italic: bool | None = None
    caps: str | None = None
    color: str | None = None
    color_slot: str | None = None
    align: str | None = None
    line_spacing: float | None = None
    space_before_pt: float | None = None
    space_after_pt: float | None = None
    margin_left: int | None = None
    indent: int | None = None
    bullet_kind: str | None = None
    bullet_char: str | None = None
    bullet_font: str | None = None
    bullet_color: str | None = None
    sources: list[str] = field(default_factory=list)

    def merge(self, other: "RawStyle") -> None:
        for key, value in vars(other).items():
            if key == "sources":
                self.sources.extend(value)
            elif value is not None:
                setattr(self, key, value)

    def to_text_style(self, fonts: Fonts) -> TextStyle:
        bullet = None
        if self.bullet_kind and self.bullet_kind != "none":
            bullet = Bullet(char=self.bullet_char, font=self.bullet_font,
                            color=self.bullet_color, kind=self.bullet_kind,
                            indent=float(self.margin_left or 0))
        font = self.font
        if font == "+mj-lt":
            font = fonts.major
        elif font == "+mn-lt":
            font = fonts.minor
        return TextStyle(
            font=font, size_pt=self.size_pt,
            bold=bool(self.bold), italic=bool(self.italic),
            caps=self.caps or "none", color=self.color, color_slot=self.color_slot,
            align=self.align or "l", line_spacing=self.line_spacing,
            space_before_pt=self.space_before_pt or 0.0,
            space_after_pt=self.space_after_pt or 0.0,
            bullet=bullet,
            provenance=" → ".join(self.sources),
        )


# --- чтение отдельных узлов ------------------------------------------------

def _read_rpr(rpr: etree._Element | None, ctx: StyleContext, origin: str) -> RawStyle:
    style = RawStyle()
    if rpr is None:
        return style
    style.sources.append(origin)

    if (size := attr_int(rpr, "sz", None)) is not None:
        style.size_pt = size / 100.0
    if (bold := rpr.get("b")) is not None:
        style.bold = bold in ("1", "true")
    if (italic := rpr.get("i")) is not None:
        style.italic = italic in ("1", "true")
    if (caps := rpr.get("cap")) is not None:
        style.caps = {"all": "all", "small": "small", "none": "none"}.get(caps, "none")

    latin = rpr.find("a:latin", NS)
    if latin is not None and latin.get("typeface"):
        style.font = latin.get("typeface")

    fill = read_fill(rpr, ctx)
    if fill.color is not None:
        style.color = fill.color.hex
        style.color_slot = fill.color.scheme_slot
    return style


def _read_ppr(ppr: etree._Element | None, ctx: StyleContext, origin: str) -> RawStyle:
    style = RawStyle()
    if ppr is None:
        return style
    style.sources.append(origin)

    if (align := ppr.get("algn")) is not None:
        style.align = ALIGN_MAP.get(align, "l")
    if (mar := attr_int(ppr, "marL", None)) is not None:
        style.margin_left = mar
    if (ind := attr_int(ppr, "indent", None)) is not None:
        style.indent = ind

    if (ln_spc := ppr.find("a:lnSpc", NS)) is not None:
        if (pct := ln_spc.find("a:spcPct", NS)) is not None:
            style.line_spacing = (attr_int(pct, "val", 100000) or 100000) / 100000.0
        elif (pts := ln_spc.find("a:spcPts", NS)) is not None:
            style.line_spacing = -(attr_int(pts, "val", 0) or 0) / 100.0  # < 0 = точный кегль

    for tag, attribute in (("a:spcBef", "space_before_pt"), ("a:spcAft", "space_after_pt")):
        node = ppr.find(tag, NS)
        if node is None:
            continue
        if (pts := node.find("a:spcPts", NS)) is not None:
            setattr(style, attribute, (attr_int(pts, "val", 0) or 0) / 100.0)

    for tag, kind in (("a:buNone", "none"), ("a:buChar", "char"), ("a:buAutoNum", "auto_num"),
                      ("a:buBlip", "picture")):
        node = ppr.find(tag, NS)
        if node is not None:
            style.bullet_kind = kind
            if kind == "char":
                style.bullet_char = node.get("char")
    if (bu_font := ppr.find("a:buFont", NS)) is not None:
        style.bullet_font = bu_font.get("typeface")
    if (bu_clr := ppr.find("a:buClr", NS)) is not None:
        fill = read_fill(bu_clr, ctx)
        if fill.color is not None:
            style.bullet_color = fill.color.hex

    # Внутри pPr может лежать defRPr — свойства «по умолчанию» для ранов абзаца.
    style.merge(_read_rpr(ppr.find("a:defRPr", NS), ctx, origin + "/defRPr"))
    return style


def _level_pr(lst_style: etree._Element | None, level: int) -> etree._Element | None:
    if lst_style is None:
        return None
    return lst_style.find(f"a:lvl{min(level, 8) + 1}pPr", NS)


# --- цепочка наследования --------------------------------------------------

def _shape_lst_style(shape: Shape | None) -> etree._Element | None:
    if shape is None or shape.tx_body is None:
        return None
    return shape.tx_body.find("a:lstStyle", NS)


def resolve_style(pkg: Package, part: str, shape: Shape, level: int = 0,
                  paragraph_index: int | None = None) -> TextStyle:
    """Действующий стиль текста уровня `level` в данном шейпе."""
    ctx = build_context(pkg, part)
    fonts = theme_fonts(pkg)
    master_part = pkg.master_of(part)
    layout_part = pkg.layout_of(part)

    style = RawStyle()

    # 1. Умолчания презентации — для обычных надписей вне плейсхолдеров.
    if not shape.is_placeholder:
        default = pkg.presentation.find("p:defaultTextStyle", NS)
        style.merge(_read_ppr(_level_pr(default, level), ctx, "presentation.defaultTextStyle"))

    # 2. Раздел txStyles мастера, соответствующий типу плейсхолдера.
    if master_part and pkg.has(master_part):
        master_root = pkg.xml(master_part)
        category = PH_CATEGORY.get(shape.ph_type or "", "other" if not shape.is_placeholder else "body")
        tx_styles = master_root.find("p:txStyles", NS)
        if tx_styles is not None:
            node = tx_styles.find(f"p:{category}Style", NS)
            style.merge(_read_ppr(_level_pr(node, level), ctx, f"master.{category}Style"))

        # 3. Собственный lstStyle плейсхолдера мастера.
        master_ph = match_placeholder(pkg.shapes(master_part),
                                      shape.ph_type, shape.ph_idx)
        style.merge(_read_ppr(_level_pr(_shape_lst_style(master_ph), level), ctx,
                              "master.placeholder"))

    # 4. Плейсхолдер макета (когда разбираем слайд).
    if layout_part and pkg.has(layout_part):
        layout_ph = match_placeholder(pkg.shapes(layout_part),
                                      shape.ph_type, shape.ph_idx)
        style.merge(_read_ppr(_level_pr(_shape_lst_style(layout_ph), level), ctx,
                              "layout.placeholder"))

    # 5. Сам шейп, затем абзац и ран.
    style.merge(_read_ppr(_level_pr(_shape_lst_style(shape), level), ctx, "shape.lstStyle"))

    paragraphs = [p for p in shape.paragraphs if p.level == level]
    if paragraph_index is not None and paragraph_index < len(shape.paragraphs):
        paragraphs = [shape.paragraphs[paragraph_index]]
    if paragraphs:
        para = paragraphs[0]
        style.merge(_read_ppr(para.ppr, ctx, "paragraph"))
        for run in para.runs:
            if run.rpr is not None and run.text.strip():
                style.merge(_read_rpr(run.rpr, ctx, "run"))
                break

    return style.to_text_style(fonts)


# --- шрифты и шкала --------------------------------------------------------

def theme_fonts(pkg: Package) -> Fonts:
    master = pkg.masters[0] if pkg.masters else pkg.presentation_part
    theme_part = pkg.theme_of(master)
    major = minor = ""
    if theme_part:
        scheme = pkg.xml(theme_part).find(".//a:themeElements/a:fontScheme", NS)
        if scheme is not None:
            major_node = scheme.find("a:majorFont/a:latin", NS)
            minor_node = scheme.find("a:minorFont/a:latin", NS)
            major = (major_node.get("typeface") if major_node is not None else "") or ""
            minor = (minor_node.get("typeface") if minor_node is not None else "") or ""
    used: set[str] = set()
    for part in [*pkg.masters, *pkg.layouts, *pkg.slides]:
        for node in pkg.xml(part).iter(f"{{{NS['a']}}}latin"):
            typeface = node.get("typeface")
            if typeface and not typeface.startswith("+"):
                used.add(typeface)

    return Fonts(major=major, minor=minor, embedded=pkg.embedded_fonts,
                 used=sorted(used))


def _role_of(shape: Shape) -> str | None:
    """Роль текста по типу плейсхолдера. Не-плейсхолдеры сюда не попадают."""
    match shape.ph_type:
        case "title" | "ctrTitle":
            return "title"
        case "subTitle":
            return "subtitle"
        case "body" | "obj":
            return "body"
        case "ftr" | "sldNum" | "dt":
            return "footer"
        case _:
            return None


def extract_typography(pkg: Package) -> Typography:
    """Стили ролей — по моде значений среди всех макетов, а не по первому найденному."""
    fonts = theme_fonts(pkg)
    samples: dict[str, list[TextStyle]] = {}
    sizes: Counter = Counter()

    for part in [*pkg.layouts, *pkg.slides]:
        for shape in pkg.shapes(part):
            if shape.tx_body is None:
                continue
            role = _role_of(shape)
            levels = sorted({p.level for p in shape.paragraphs}) or [0]

            if role == "body":
                for level in levels[:3]:
                    style = resolve_style(pkg, part, shape, level)
                    samples.setdefault(f"body_l{level + 1}", []).append(style)
                    if style.size_pt:
                        sizes[style.size_pt] += 1
            elif role:
                style = resolve_style(pkg, part, shape, 0)
                samples.setdefault(role, []).append(style)
                if style.size_pt and role != "footer":
                    sizes[style.size_pt] += 1
            elif not shape.is_placeholder and shape.text:
                style = resolve_style(pkg, part, shape, 0)
                if style.size_pt:
                    sizes[style.size_pt] += 1
                samples.setdefault("_free", []).append(style)

    styles = {name: _modal_style(items) for name, items in samples.items()
              if name != "_free" and items}

    # Кикер и крупная цифра метрики — из свободных надписей шаблона.
    if free := samples.get("_free"):
        styles.update(_derive_free_roles(free, styles))

    scale = [size for size, count in sizes.items() if count >= 2]
    if not scale:
        scale = list(sizes)
    scale.sort(reverse=True)

    return Typography(fonts=fonts, scale_pt=scale, styles=styles)


def _modal_style(items: list[TextStyle]) -> TextStyle:
    """Самое частое значение по каждому свойству — устойчивее среднего и первого."""
    def mode(values: list) -> object:
        filtered = [v for v in values if v is not None]
        return Counter(filtered).most_common(1)[0][0] if filtered else None

    base = items[0].model_copy(deep=True)
    base.font = mode([item.font for item in items])
    base.size_pt = mode([item.size_pt for item in items])
    base.color = mode([item.color for item in items])
    base.color_slot = mode([item.color_slot for item in items])
    base.align = mode([item.align for item in items]) or "l"
    base.bold = bool(mode([item.bold for item in items]))
    base.caps = mode([item.caps for item in items]) or "none"
    base.line_spacing = mode([item.line_spacing for item in items])
    base.provenance = items[0].provenance
    return base


def _derive_free_roles(free: list[TextStyle], known: dict[str, TextStyle]) -> dict[str, TextStyle]:
    """Роли, которых нет в плейсхолдерах: подзаголовок-кикер и крупная цифра."""
    with_size = [style for style in free if style.size_pt]
    if not with_size:
        return {}
    title_size = (known.get("title").size_pt if known.get("title") else None) or 0
    body_size = (known.get("body_l1").size_pt if known.get("body_l1") else None) or 0

    result: dict[str, TextStyle] = {}
    largest = max(with_size, key=lambda style: style.size_pt or 0)
    if title_size and (largest.size_pt or 0) > title_size * 1.2:
        result["metric_value"] = largest

    if body_size:
        smaller = [style for style in with_size if (style.size_pt or 0) < body_size]
        if smaller:
            result["kicker"] = max(smaller, key=lambda style: style.size_pt or 0)
    return result
