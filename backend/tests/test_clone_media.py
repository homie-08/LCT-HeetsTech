"""Перенос медиа при клонировании слайда-примера.

Векторный декор в шаблонах нарисован в EMF, WMF или SVG. python-pptx открывает
картинку через PIL, чтобы узнать её размеры, а PIL таких форматов не знает и
падает с «cannot identify image file». Раньше на этом умирала вся сборка.
"""

from __future__ import annotations

import io
import re
import zipfile

import pytest

from conftest import ALL_TEMPLATES

from sd.ooxml.clone import _content_type_of, copy_slide_shapes, drop_all_slides
from sd.ooxml.package import Package

pytestmark = pytest.mark.skipif(not ALL_TEMPLATES, reason="нет шаблонов")

VECTOR_SUFFIX = ".svg"
VECTOR_TYPE = "image/svg+xml"


def _template_with_pictures():
    """Шаблон, у которого картинка привязана именно к слайду-примеру.

    Картинки мастера и макетов переносить не надо — они приезжают вместе с
    макетом. Клонирование трогает только связи слайда, поэтому и подменять
    нужно ту картинку, на которую ссылается слайд.
    """
    from sd.ooxml.ns import NS

    for path in ALL_TEMPLATES:
        pkg = Package.open(path)
        for part in pkg.slides:
            tree = pkg.xml(part).find(".//p:cSld/p:spTree", NS)
            if tree is None:
                continue
            rels = pkg.rels(part)
            for blip in tree.iter(f"{{{NS['a']}}}blip"):
                rid = blip.get(f"{{{NS['r']}}}embed")
                relation = rels.get(rid or "")
                target = relation.target if relation else ""
                if target.lower().endswith((".png", ".jpeg", ".jpg")):
                    return path, target
    pytest.skip("нет шаблона с картинкой внутри шейпа на слайде-примере")


def _vector_blob() -> bytes:
    """Иконка в SVG — ровно то, чем современные шаблоны рисуют пиктограммы.

    PIL векторных форматов не знает и падает с «cannot identify image file»,
    а python-pptx открывает через него любую картинку, чтобы узнать размеры.
    """
    return (b'<svg xmlns="http://www.w3.org/2000/svg" width="16" height="16">'
            b'<rect width="16" height="16"/></svg>')


def _with_vector_media(path, media_name: str) -> bytes:
    """Тот же шаблон, но вместо растровой картинки — векторная иконка."""
    renamed = re.sub(r"\.[^.]+$", VECTOR_SUFFIX, media_name)
    source = zipfile.ZipFile(path)
    buffer = io.BytesIO()

    with zipfile.ZipFile(buffer, "w", zipfile.ZIP_DEFLATED) as out:
        for item in source.infolist():
            data = source.read(item.filename)
            name = item.filename
            if name == media_name:
                name, data = renamed, _vector_blob()
            elif name == "[Content_Types].xml":
                text = data.decode("utf-8")
                insert = (f'<Default Extension="{VECTOR_SUFFIX.lstrip(".")}" '
                          f'ContentType="{VECTOR_TYPE}"/>')
                text = text.replace("</Types>", f"{insert}</Types>")
                data = text.encode("utf-8")
            elif name.endswith(".rels"):
                short = media_name.rsplit("/", 1)[-1]
                data = data.replace(short.encode("utf-8"),
                                    renamed.rsplit("/", 1)[-1].encode("utf-8"))
            out.writestr(name, data)
    source.close()
    return buffer.getvalue()


def test_vector_media_survives_cloning():
    """Сборка не падает, и картинка доезжает до нового пакета."""
    from pptx import Presentation

    path, media_name = _template_with_pictures()
    pkg = Package(_with_vector_media(path, media_name), path.name)
    assert _content_type_of(pkg, media_name.rsplit(".", 1)[0] + VECTOR_SUFFIX) == VECTOR_TYPE

    presentation = Presentation(io.BytesIO(pkg.as_pptx_bytes()))
    drop_all_slides(presentation)

    carried = 0
    for part in pkg.slides:
        layout_part = pkg.layout_of(part)
        layout = next((item for item in presentation.slide_layouts
                       if item.part.partname == f"/{layout_part}"), None)
        if layout is None:
            continue
        slide = presentation.slides.add_slide(layout)
        copy_slide_shapes(pkg, part, slide)          # раньше здесь падал PIL
        carried += sum(1 for rel in slide.part.rels.values()
                       if not rel.is_external and str(rel.target_part.partname)
                       .lower().endswith(VECTOR_SUFFIX))

    assert carried > 0, "векторная картинка не перенесена ни на один слайд"

    # Файл должен остаться читаемым: битые связи PowerPoint не прощает.
    result = io.BytesIO()
    presentation.save(result)
    with zipfile.ZipFile(io.BytesIO(result.getvalue())) as archive:
        assert any(name.lower().endswith(VECTOR_SUFFIX) for name in archive.namelist())
