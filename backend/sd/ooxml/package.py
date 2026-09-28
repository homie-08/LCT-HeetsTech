"""Пакет OOXML как набор частей и связей.

python-pptx удобен для сборки, но для анализа шаблона нужен доступ ко всему,
что он прячет: мастера, темы, `txStyles`, стилевая матрица, слайды-примеры,
шрифты. Плюс `.potx` python-pptx открывать отказывается — здесь же это просто
другой content-type, который мы умеем подменять.
"""

from __future__ import annotations

import hashlib
import io
import posixpath
import re
import zipfile
from dataclasses import dataclass
from pathlib import Path

from lxml import etree

from .ns import NS, attr_int
from .shapes import Shape, iter_shapes, match_placeholder

PRESENTATION_CT = ("application/vnd.openxmlformats-officedocument"
                   ".presentationml.presentation.main+xml")
TEMPLATE_CT = ("application/vnd.openxmlformats-officedocument"
               ".presentationml.template.main+xml")

RT = "http://schemas.openxmlformats.org/officeDocument/2006/relationships/"
RT_SLIDE = RT + "slide"
RT_MASTER = RT + "slideMaster"
RT_LAYOUT = RT + "slideLayout"
RT_THEME = RT + "theme"
RT_IMAGE = RT + "image"
RT_CHART = RT + "chart"


@dataclass(frozen=True)
class Rel:
    rid: str
    type: str
    target: str          # уже приведён к абсолютному имени части
    external: bool = False


class Package:
    """Только чтение: разбираем шаблон, ничего в нём не меняем."""

    def __init__(self, data: bytes, name: str = "template.pptx"):
        self.raw = data
        self.name = name
        self.sha256 = hashlib.sha256(data).hexdigest()
        self._zip = zipfile.ZipFile(io.BytesIO(data))
        self._xml_cache: dict[str, etree._Element] = {}
        self._rels_cache: dict[str, dict[str, Rel]] = {}

    @classmethod
    def open(cls, path: str | Path) -> "Package":
        path = Path(path)
        return cls(path.read_bytes(), path.name)

    # --- части ---------------------------------------------------------------

    @property
    def part_names(self) -> list[str]:
        return self._zip.namelist()

    def blob(self, part: str) -> bytes:
        return self._zip.read(part.lstrip("/"))

    def has(self, part: str) -> bool:
        try:
            self._zip.getinfo(part.lstrip("/"))
            return True
        except KeyError:
            return False

    def xml(self, part: str) -> etree._Element:
        part = part.lstrip("/")
        if part not in self._xml_cache:
            self._xml_cache[part] = etree.fromstring(self._zip.read(part))
        return self._xml_cache[part]

    # --- связи ---------------------------------------------------------------

    def rels(self, part: str) -> dict[str, Rel]:
        """Связи части: {rId: Rel} с целями, приведёнными к абсолютным именам."""
        part = part.lstrip("/")
        if part in self._rels_cache:
            return self._rels_cache[part]

        directory, filename = posixpath.split(part)
        rels_part = posixpath.join(directory, "_rels", filename + ".rels")
        result: dict[str, Rel] = {}
        if self.has(rels_part):
            for node in self.xml(rels_part):
                rid = node.get("Id", "")
                target = node.get("Target", "")
                external = node.get("TargetMode") == "External"
                if not external:
                    target = posixpath.normpath(posixpath.join(directory, target))
                result[rid] = Rel(rid, node.get("Type", ""), target, external)
        self._rels_cache[part] = result
        return result

    def related(self, part: str, rel_type: str) -> list[str]:
        return [rel.target for rel in self.rels(part).values() if rel.type == rel_type]

    def target(self, part: str, rid: str) -> str | None:
        rel = self.rels(part).get(rid)
        return rel.target if rel else None

    # --- структура презентации ----------------------------------------------

    @property
    def presentation_part(self) -> str:
        return "ppt/presentation.xml"

    @property
    def presentation(self) -> etree._Element:
        return self.xml(self.presentation_part)

    @property
    def slide_size(self) -> tuple[int, int]:
        node = self.presentation.find("p:sldSz", NS)
        return (attr_int(node, "cx", 9144000) or 9144000,
                attr_int(node, "cy", 6858000) or 6858000)

    def _ordered(self, list_tag: str, id_tag: str) -> list[str]:
        """Части в порядке, заданном презентацией, а не в порядке zip-архива."""
        parts: list[str] = []
        container = self.presentation.find(f"p:{list_tag}", NS)
        for node in container if container is not None else []:
            rid = node.get(f"{{{NS['r']}}}id")
            if rid and (target := self.target(self.presentation_part, rid)):
                parts.append(target)
        return parts

    @property
    def masters(self) -> list[str]:
        return self._ordered("sldMasterIdLst", "sldMasterId")

    @property
    def slides(self) -> list[str]:
        return self._ordered("sldIdLst", "sldId")

    def layouts_of(self, master_part: str) -> list[str]:
        """Макеты мастера в порядке `p:sldLayoutIdLst`."""
        parts: list[str] = []
        container = self.xml(master_part).find("p:sldLayoutIdLst", NS)
        for node in container if container is not None else []:
            rid = node.get(f"{{{NS['r']}}}id")
            if rid and (target := self.target(master_part, rid)):
                parts.append(target)
        return parts

    @property
    def layouts(self) -> list[str]:
        out: list[str] = []
        for master in self.masters:
            out.extend(self.layouts_of(master))
        return out

    def master_of(self, part: str) -> str | None:
        """Мастер для макета, или мастер слайда через его макет."""
        if masters := self.related(part, RT_MASTER):
            return masters[0]
        if layouts := self.related(part, RT_LAYOUT):
            return self.master_of(layouts[0])
        return None

    def layout_of(self, slide_part: str) -> str | None:
        layouts = self.related(slide_part, RT_LAYOUT)
        return layouts[0] if layouts else None

    def theme_of(self, part: str) -> str | None:
        """Тема, действующая для части (ищем через мастер)."""
        if themes := self.related(part, RT_THEME):
            return themes[0]
        master = self.master_of(part)
        if master and (themes := self.related(master, RT_THEME)):
            return themes[0]
        return None

    def shapes(self, part: str) -> list[Shape]:
        """Шейпы части с кешем: их перебирают все анализаторы подряд."""
        cache: dict[str, list] = self.__dict__.setdefault("_shape_cache", {})
        if part not in cache:
            shapes = iter_shapes(self.xml(part), part)
            cache[part] = shapes           # до наследования, чтобы не зациклиться
            self._inherit_geometry(part, shapes)
        return cache[part]

    def _inherit_geometry(self, part: str, shapes: list[Shape]) -> None:
        """Плейсхолдер без своего `a:xfrm` берёт координаты у родителя.

        Так устроено большинство макетов: положение заголовка задано один раз на
        мастере. Если это не разворачивать, половина плейсхолдеров выглядит как
        шейпы нулевого размера и выпадает из анализа.
        """
        parent = self.layout_of(part) or self.master_of(part)
        if not parent or parent == part or not self.has(parent):
            return
        parent_shapes = self.shapes(parent)
        for shape in shapes:
            if not shape.is_placeholder or (shape.cx > 0 and shape.cy > 0):
                continue
            match = match_placeholder(parent_shapes, shape.ph_type, shape.ph_idx)
            if match is None or match.cx <= 0 or match.cy <= 0:
                continue
            shape.x, shape.y, shape.cx, shape.cy = match.x, match.y, match.cx, match.cy
            shape.geometry_inherited = True

    def name_of(self, part: str) -> str:
        """Имя макета/слайда из `p:cSld/@name`, иначе имя файла."""
        root = self.xml(part)
        node = root.find("p:cSld", NS)
        name = node.get("name") if node is not None else None
        return name or posixpath.basename(part)

    # --- медиа и шрифты ------------------------------------------------------

    def images(self, part: str) -> dict[str, str]:
        return {rel.rid: rel.target for rel in self.rels(part).values()
                if rel.type == RT_IMAGE}

    @property
    def embedded_fonts(self) -> list[str]:
        """Имена шрифтов, вшитых в пакет (`p:embeddedFontLst`)."""
        names = []
        for node in self.presentation.findall(".//p:embeddedFont/p:font", NS):
            if typeface := node.get("typeface"):
                names.append(typeface)
        return names

    # --- конвертация ---------------------------------------------------------

    def as_pptx_bytes(self) -> bytes:
        """Тот же пакет, но с content-type презентации.

        `.potx` отличается от `.pptx` ровно одной строкой в `[Content_Types].xml`;
        python-pptx проверяет её строго и на шаблоне падает. Пересобираем архив,
        подменив тип, — содержимое не трогаем.
        """
        content_types = self.blob("[Content_Types].xml").decode("utf-8")
        if TEMPLATE_CT not in content_types:
            return self.raw
        patched = content_types.replace(TEMPLATE_CT, PRESENTATION_CT)

        buffer = io.BytesIO()
        with zipfile.ZipFile(buffer, "w", zipfile.ZIP_DEFLATED) as out:
            for item in self._zip.infolist():
                data = self._zip.read(item.filename)
                if item.filename == "[Content_Types].xml":
                    data = patched.encode("utf-8")
                # Именно копия ZipInfo: `writestr` перезаписывает смещения прямо
                # в переданном объекте, а он принадлежит исходному архиву —
                # после такой записи оригинал перестаёт читаться.
                entry = zipfile.ZipInfo(item.filename, date_time=item.date_time)
                entry.compress_type = item.compress_type
                entry.external_attr = item.external_attr
                entry.internal_attr = item.internal_attr
                entry.create_system = item.create_system
                out.writestr(entry, data)
        return buffer.getvalue()

    def __repr__(self) -> str:  # pragma: no cover
        cx, cy = self.slide_size
        return (f"<Package {self.name} {cx}x{cy} "
                f"masters={len(self.masters)} layouts={len(self.layouts)} "
                f"slides={len(self.slides)}>")


def emu_to_fraction(value: int, total: int) -> float:
    return round(value / total, 5) if total else 0.0


SLIDE_NUMBER_RE = re.compile(r"slide(\d+)\.xml$")


def part_index(part: str) -> int:
    match = SLIDE_NUMBER_RE.search(part)
    return int(match.group(1)) if match else 0
