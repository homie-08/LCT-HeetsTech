"""Замена текста в `a:txBody` с сохранением оформления.

Наивная запись текста стирает всё форматирование абзаца и рана. Здесь первый
абзац и первый ран используются как образец: из них берутся `pPr` и `rPr`
(шрифт, кегль, цвет, маркер), а меняется только содержимое. Так текст,
поставленный в клонированный слайд, выглядит ровно так же, как исходный.
"""

from __future__ import annotations

import copy

from lxml import etree

from .ns import NS, qn


def _first(elements: list[etree._Element]) -> etree._Element | None:
    return elements[0] if elements else None


def _make_run(template: etree._Element | None, text: str,
              size_pt: float | None) -> etree._Element:
    if template is not None:
        run = copy.deepcopy(template)
        for child in run.findall(qn("a:t")):
            run.remove(child)
    else:
        run = etree.Element(qn("a:r"))

    rpr = run.find(qn("a:rPr"))
    if size_pt is not None:
        if rpr is None:
            rpr = etree.Element(qn("a:rPr"))
            run.insert(0, rpr)
        rpr.set("sz", str(int(round(size_pt * 100))))

    text_element = etree.SubElement(run, qn("a:t"))
    text_element.text = text
    return run


def set_text(tx_body: etree._Element, lines: list[str],
             size_pt: float | None = None,
             first_size_pt: float | None = None) -> None:
    """Заменяет содержимое текстового блока строками, сохраняя стиль образца.

    `first_size_pt` задаёт кегль только первой строки — так делается иерархия
    «крупная цифра, под ней подпись», без правки остального оформления.
    """
    paragraphs = tx_body.findall(qn("a:p"))
    template_paragraph = _first(paragraphs)
    template_run = None
    for paragraph in paragraphs:
        if (runs := paragraph.findall(qn("a:r"))):
            template_run = runs[0]
            break

    if template_paragraph is not None:
        blank = copy.deepcopy(template_paragraph)
        for child in list(blank):
            if child.tag in (qn("a:r"), qn("a:fld"), qn("a:br"), qn("a:endParaRPr")):
                blank.remove(child)
    else:
        blank = etree.Element(qn("a:p"))

    for paragraph in paragraphs:
        tx_body.remove(paragraph)

    for index, line in enumerate(lines or [""]):
        paragraph = copy.deepcopy(blank)
        size = first_size_pt if index == 0 and first_size_pt else size_pt
        paragraph.append(_make_run(template_run, line, size))
        tx_body.append(paragraph)


def read_text(tx_body: etree._Element | None) -> str:
    if tx_body is None:
        return ""
    return "\n".join(
        "".join(node.text or "" for node in paragraph.iter(qn("a:t")))
        for paragraph in tx_body.findall(qn("a:p")))


def clear_autofit_scale(tx_body: etree._Element) -> None:
    """Снимает `fontScale`, оставшийся от прежнего текста.

    PowerPoint хранит подобранный масштаб автофита в разметке. Если его не
    сбросить, новый текст рисуется с чужим коэффициентом и кегль «плавает»
    относительно того, что мы посчитали.
    """
    body_pr = tx_body.find(qn("a:bodyPr"))
    if body_pr is None:
        return
    for autofit in body_pr.findall(qn("a:normAutofit")):
        autofit.attrib.pop("fontScale", None)
        autofit.attrib.pop("lnSpcReduction", None)


def iter_text_bodies(element: etree._Element):
    yield from element.iter(qn("a:txBody"))


def shape_id(element: etree._Element) -> int | None:
    node = element.find(f".//{qn('p:cNvPr')}")
    if node is None:
        for candidate in element.iter():
            if candidate.tag == qn("p:cNvPr"):
                node = candidate
                break
    try:
        return int(node.get("id")) if node is not None else None
    except (TypeError, ValueError):
        return None


def find_blips(element: etree._Element) -> list[etree._Element]:
    return [node for node in element.iter(qn("a:blip"))
            if node.get(f"{{{NS['r']}}}embed")]
