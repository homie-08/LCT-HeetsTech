"""Разрешение цвета DrawingML — самый частый источник тихих ошибок."""

from __future__ import annotations

from lxml import etree

from sd.ooxml.color import (contrast_ratio, hex_to_rgb, read_scheme, relative_luminance,
                            resolve_color, rgb_to_hex)

SCHEME = {"dk1": "#000000", "lt1": "#FFFFFF", "dk2": "#1F497D", "accent1": "#4472C4"}
CLR_MAP = {"bg1": "lt1", "tx1": "dk1", "bg2": "lt2", "tx2": "dk2"}

A = "http://schemas.openxmlformats.org/drawingml/2006/main"


def parse(xml: str) -> etree._Element:
    return etree.fromstring(f'<root xmlns:a="{A}">{xml}</root>')[0]


def test_srgb_literal():
    color = resolve_color(parse('<a:srgbClr val="D16349"/>'), SCHEME)
    assert color.hex == "#D16349"
    assert color.provenance == "literal"


def test_scheme_reference_keeps_provenance():
    color = resolve_color(parse('<a:schemeClr val="accent1"/>'), SCHEME, CLR_MAP)
    assert color.hex == "#4472C4"
    assert color.provenance == "theme.accent1"


def test_clr_map_alias():
    """`bg1` — не слот темы, а псевдоним; без clrMap цвет разрешится в чёрный."""
    color = resolve_color(parse('<a:schemeClr val="bg1"/>'), SCHEME, CLR_MAP)
    assert color.hex == "#FFFFFF"


def test_lum_mod_off_lightens():
    """«Акцент 1, светлее 40 %» из интерфейса PowerPoint."""
    xml = '<a:schemeClr val="accent1"><a:lumMod val="60000"/><a:lumOff val="40000"/></a:schemeClr>'
    color = resolve_color(parse(xml), SCHEME, CLR_MAP)
    assert relative_luminance(color.hex) > relative_luminance("#4472C4")
    assert color.provenance == "theme.accent1+lumMod=60000+lumOff=40000"


def test_shade_darkens_and_tint_lightens():
    dark = resolve_color(parse('<a:srgbClr val="4472C4"><a:shade val="50000"/></a:srgbClr>'), SCHEME)
    light = resolve_color(parse('<a:srgbClr val="4472C4"><a:tint val="50000"/></a:srgbClr>'), SCHEME)
    base = relative_luminance("#4472C4")
    assert relative_luminance(dark.hex) < base < relative_luminance(light.hex)


def test_alpha_is_kept_separately():
    color = resolve_color(parse('<a:srgbClr val="000000"><a:alpha val="50000"/></a:srgbClr>'), SCHEME)
    assert color.hex == "#000000" and abs(color.alpha - 0.5) < 1e-6


def test_sys_color_uses_last_known_value():
    color = resolve_color(parse('<a:sysClr val="windowText" lastClr="222222"/>'), SCHEME)
    assert color.hex == "#222222"


def test_contrast_ratio_matches_wcag_reference():
    assert abs(contrast_ratio("#FFFFFF", "#000000") - 21.0) < 0.01
    assert abs(contrast_ratio("#777777", "#FFFFFF") - 4.48) < 0.05


def test_rgb_roundtrip():
    assert rgb_to_hex(hex_to_rgb("#8CADAE")) == "#8CADAE"


def test_read_scheme_full_slot_set():
    xml = f'''<a:theme xmlns:a="{A}"><a:themeElements><a:clrScheme name="X">
      <a:dk1><a:sysClr val="windowText" lastClr="000000"/></a:dk1>
      <a:lt1><a:sysClr val="window" lastClr="FFFFFF"/></a:lt1>
      <a:dk2><a:srgbClr val="1F497D"/></a:dk2><a:lt2><a:srgbClr val="EEECE1"/></a:lt2>
      <a:accent1><a:srgbClr val="4472C4"/></a:accent1><a:accent2><a:srgbClr val="ED7D31"/></a:accent2>
      <a:accent3><a:srgbClr val="A5A5A5"/></a:accent3><a:accent4><a:srgbClr val="FFC000"/></a:accent4>
      <a:accent5><a:srgbClr val="5B9BD5"/></a:accent5><a:accent6><a:srgbClr val="70AD47"/></a:accent6>
      <a:hlink><a:srgbClr val="0563C1"/></a:hlink><a:folHlink><a:srgbClr val="954F72"/></a:folHlink>
    </a:clrScheme></a:themeElements></a:theme>'''
    scheme = read_scheme(etree.fromstring(xml))
    assert len(scheme) == 12
    assert scheme["accent1"] == "#4472C4" and scheme["lt1"] == "#FFFFFF"
