"""Разрешение цвета DrawingML в конкретный `#RRGGBB`.

Цвет в OOXML почти никогда не лежит готовым: это ссылка на тему (`schemeClr`)
плюс цепочка модификаторов (`lumMod`, `tint`, `shade`, …). «Акцент 1, светлее 40 %»
из интерфейса PowerPoint — это `schemeClr accent1` + `lumMod 60000` + `lumOff 40000`.
Без этих преобразований палитра шаблона извлекается неправильно.

Соглашения по формулам (ECMA-376 §20.1.2.3 и поведение PowerPoint):
* `lumMod`/`lumOff`, `satMod`/`satOff`, `hueMod`/`hueOff` — в пространстве HSL;
* `shade`/`tint` — в линейном RGB (гамма 2.2), как требует спецификация;
* `alpha` не влияет на итоговый RGB, но сохраняется отдельно.
"""

from __future__ import annotations

import colorsys
from dataclasses import dataclass

from lxml import etree

from .ns import NS, local_name

# Цвета `a:prstClr` — берём подмножество, которое реально встречается в шаблонах.
PRESET_COLORS = {
    "black": "000000", "white": "FFFFFF", "red": "FF0000", "green": "008000",
    "blue": "0000FF", "yellow": "FFFF00", "cyan": "00FFFF", "magenta": "FF00FF",
    "gray": "808080", "darkGray": "A9A9A9", "lightGray": "D3D3D3", "orange": "FFA500",
}

SYS_COLORS = {
    "windowText": "000000", "window": "FFFFFF", "btnFace": "F0F0F0",
    "btnText": "000000", "highlight": "0078D7", "highlightText": "FFFFFF",
    "grayText": "808080", "3dDkShadow": "696969", "3dLight": "E3E3E3",
}

# Имена в `a:clrScheme`; bg1/tx1/bg2/tx2 — псевдонимы, разворачиваются через clrMap.
SCHEME_SLOTS = ("dk1", "lt1", "dk2", "lt2", "accent1", "accent2", "accent3",
                "accent4", "accent5", "accent6", "hlink", "folHlink")

COLOR_ELEMENTS = ("srgbClr", "sysClr", "schemeClr", "prstClr", "hslClr", "scrgbClr")


@dataclass(frozen=True)
class ResolvedColor:
    """Итоговый цвет плюс след того, откуда он взялся."""

    hex: str                      # "#RRGGBB"
    alpha: float = 1.0            # 0..1
    scheme_slot: str | None = None  # accent1, dk2, … если цвет пришёл из темы
    mods: tuple[str, ...] = ()      # ("lumMod=60000", "lumOff=40000")

    @property
    def provenance(self) -> str:
        if self.scheme_slot:
            base = f"theme.{self.scheme_slot}"
            return f"{base}+{'+'.join(self.mods)}" if self.mods else base
        return "literal"

    def to_json(self) -> dict:
        out: dict = {"value": self.hex, "from": self.provenance}
        if self.alpha < 1.0:
            out["alpha"] = round(self.alpha, 3)
        return out


# --- преобразования пространств -------------------------------------------------

def hex_to_rgb(value: str) -> tuple[float, float, float]:
    value = value.lstrip("#")
    return tuple(int(value[i:i + 2], 16) / 255.0 for i in (0, 2, 4))  # type: ignore[return-value]


def rgb_to_hex(rgb: tuple[float, float, float]) -> str:
    return "#" + "".join(f"{max(0, min(255, round(c * 255))):02X}" for c in rgb)


def _srgb_to_linear(c: float) -> float:
    return c ** 2.2


def _linear_to_srgb(c: float) -> float:
    return max(0.0, min(1.0, c)) ** (1 / 2.2)


def relative_luminance(hex_color: str) -> float:
    """Относительная яркость по WCAG 2.1 — нужна для проверки контраста."""
    def channel(c: float) -> float:
        return c / 12.92 if c <= 0.04045 else ((c + 0.055) / 1.055) ** 2.4

    r, g, b = (channel(c) for c in hex_to_rgb(hex_color))
    return 0.2126 * r + 0.7152 * g + 0.0722 * b


def contrast_ratio(fg: str, bg: str) -> float:
    l1, l2 = relative_luminance(fg), relative_luminance(bg)
    lighter, darker = max(l1, l2), min(l1, l2)
    return (lighter + 0.05) / (darker + 0.05)


# --- применение модификаторов ---------------------------------------------------

def _apply_mod(rgb: tuple[float, float, float], name: str, val: float
               ) -> tuple[float, float, float]:
    h, l, s = colorsys.rgb_to_hls(*rgb)

    if name == "lumMod":
        l = l * val
    elif name == "lumOff":
        l = l + val
    elif name == "satMod":
        s = s * val
    elif name == "satOff":
        s = s + val
    elif name == "hueMod":
        h = (h * val) % 1.0
    elif name == "hueOff":
        h = (h + val) % 1.0
    elif name == "shade":
        lin = [_srgb_to_linear(c) * val for c in rgb]
        return tuple(_linear_to_srgb(c) for c in lin)  # type: ignore[return-value]
    elif name == "tint":
        lin = [_srgb_to_linear(c) * val + (1.0 - val) for c in rgb]
        return tuple(_linear_to_srgb(c) for c in lin)  # type: ignore[return-value]
    elif name == "gray":
        y = 0.299 * rgb[0] + 0.587 * rgb[1] + 0.114 * rgb[2]
        return (y, y, y)
    elif name == "inv":
        return (1 - rgb[0], 1 - rgb[1], 1 - rgb[2])
    elif name == "comp":
        h = (h + 0.5) % 1.0
    elif name == "gamma":
        return tuple(_srgb_to_linear(c) for c in rgb)  # type: ignore[return-value]
    elif name == "invGamma":
        return tuple(_linear_to_srgb(c) for c in rgb)  # type: ignore[return-value]
    else:
        return rgb

    l = max(0.0, min(1.0, l))
    s = max(0.0, min(1.0, s))
    return colorsys.hls_to_rgb(h, l, s)


def _base_color(elem: etree._Element, scheme: dict[str, str], clr_map: dict[str, str],
                phclr: str | None) -> tuple[str, str | None]:
    """Возвращает (hex, slot темы или None) без учёта модификаторов."""
    tag = local_name(elem)
    val = elem.get("val", "")

    if tag == "srgbClr":
        return f"#{val.upper()}", None
    if tag == "sysClr":
        last = elem.get("lastClr")
        return f"#{(last or SYS_COLORS.get(val, '000000')).upper()}", None
    if tag == "prstClr":
        return f"#{PRESET_COLORS.get(val, '000000')}", None
    if tag == "hslClr":
        h = int(elem.get("hue", "0")) / 21600000.0
        s = int(elem.get("sat", "0").rstrip("%")) / 100000.0
        lum = int(elem.get("lum", "0").rstrip("%")) / 100000.0
        return rgb_to_hex(colorsys.hls_to_rgb(h, lum, s)), None
    if tag == "scrgbClr":
        parts = [int(elem.get(k, "0").rstrip("%")) / 100000.0 for k in ("r", "g", "b")]
        return rgb_to_hex((parts[0], parts[1], parts[2])), None
    if tag == "schemeClr":
        if val == "phClr":
            return (phclr or "#000000"), None
        slot = clr_map.get(val, val)      # bg1 -> lt1 и т.п.
        return scheme.get(slot, "#000000"), slot
    return "#000000", None


def resolve_color(elem: etree._Element | None, scheme: dict[str, str],
                  clr_map: dict[str, str] | None = None,
                  phclr: str | None = None) -> ResolvedColor | None:
    """Разрешает элемент цвета DrawingML (`a:srgbClr`, `a:schemeClr`, …)."""
    if elem is None:
        return None
    if local_name(elem) not in COLOR_ELEMENTS:
        elem = first_color_element(elem)
        if elem is None:
            return None

    base_hex, slot = _base_color(elem, scheme, clr_map or {}, phclr)
    rgb = hex_to_rgb(base_hex)
    alpha = 1.0
    mods: list[str] = []

    for child in elem:
        if not isinstance(child.tag, str):
            continue
        name = local_name(child)
        raw = child.get("val")
        if raw is None:
            if name in ("inv", "gray", "comp", "gamma", "invGamma"):
                rgb = _apply_mod(rgb, name, 0.0)
                mods.append(name)
            continue
        if name == "alpha":
            alpha = int(raw.rstrip("%")) / 100000.0
            continue
        if name in ("hueMod", "hueOff"):
            value = int(raw) / 21600000.0 if name == "hueOff" else int(raw) / 100000.0
        else:
            value = int(raw.rstrip("%")) / 100000.0
        rgb = _apply_mod(rgb, name, value)
        mods.append(f"{name}={raw}")

    return ResolvedColor(rgb_to_hex(rgb), alpha, slot, tuple(mods))


def first_color_element(parent: etree._Element | None) -> etree._Element | None:
    """Первый потомок-цвет: у `a:solidFill`, `a:ln`, `a:defRPr` цвет лежит внутри."""
    if parent is None:
        return None
    for node in parent.iter():
        if isinstance(node.tag, str) and local_name(node) in COLOR_ELEMENTS:
            return node
    return None


def read_scheme(theme_root: etree._Element) -> dict[str, str]:
    """`a:clrScheme` темы -> {'dk1': '#000000', 'accent1': '#D16349', …}."""
    scheme_el = theme_root.find(".//a:themeElements/a:clrScheme", NS)
    scheme: dict[str, str] = {}
    if scheme_el is None:
        return scheme
    for slot in SCHEME_SLOTS:
        node = scheme_el.find(f"a:{slot}", NS)
        if node is None:
            continue
        color = resolve_color(first_color_element(node), {}, {})
        if color is not None:
            scheme[slot] = color.hex
    return scheme
