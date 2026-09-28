"""Пространства имён OOXML и мелкие помощники поверх lxml."""

from __future__ import annotations

from typing import Iterable

from lxml import etree

NS = {
    "a": "http://schemas.openxmlformats.org/drawingml/2006/main",
    "p": "http://schemas.openxmlformats.org/presentationml/2006/main",
    "r": "http://schemas.openxmlformats.org/officeDocument/2006/relationships",
    "c": "http://schemas.openxmlformats.org/drawingml/2006/chart",
    "rel": "http://schemas.openxmlformats.org/package/2006/relationships",
    "ct": "http://schemas.openxmlformats.org/package/2006/content-types",
    "p14": "http://schemas.microsoft.com/office/powerpoint/2010/main",
    "a14": "http://schemas.microsoft.com/office/drawing/2010/main",
    "mc": "http://schemas.openxmlformats.org/markup-compatibility/2006",
}

EMU_PER_PT = 12700
EMU_PER_INCH = 914400


def qn(tag: str) -> str:
    """`a:srgbClr` -> `{http://…/main}srgbClr`."""
    prefix, _, local = tag.partition(":")
    if not local:
        return tag
    return f"{{{NS[prefix]}}}{local}"


def findall(elem: etree._Element | None, path: str) -> list[etree._Element]:
    if elem is None:
        return []
    return elem.findall(path, NS)


def find(elem: etree._Element | None, path: str) -> etree._Element | None:
    if elem is None:
        return None
    return elem.find(path, NS)


def attr_int(elem: etree._Element | None, name: str, default: int | None = None) -> int | None:
    if elem is None:
        return default
    raw = elem.get(name)
    if raw is None:
        return default
    try:
        return int(raw)
    except ValueError:
        return default


def local_name(elem: etree._Element) -> str:
    tag = elem.tag
    if isinstance(tag, str) and tag.startswith("{"):
        return tag.split("}", 1)[1]
    return str(tag)


def iter_local(elem: etree._Element | None, names: Iterable[str]):
    """Обход потомков по локальным именам, без оглядки на префикс."""
    if elem is None:
        return
    wanted = set(names)
    for node in elem.iter():
        if isinstance(node.tag, str) and local_name(node) in wanted:
            yield node
