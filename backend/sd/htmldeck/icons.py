"""Подбор иконок под смысл тезиса.

Шаблон рисует иконки сам, но они подобраны под его собственный текст: рядом с
«регистрацией РИД» стоит звёздочка, а после подстановки нашего контента она
оказывается ни к чему. Здесь иконка выбирается по смыслу поставленного текста
и подменяется прямо в разметке — геометрией, без стилей.

Оформление остаётся шаблонным: цвет, толщина обводки и скругления заданы на
родительской группе, и мы её не трогаем. Меняются только контуры внутри.

Набор нарисован в манере Lucide и в его системе координат: центр в нуле,
габарит примерно ±8. Своя отрисовка, а не копия чужого файла, — чтобы у
открытого проекта не было вопросов по лицензии.
"""

from __future__ import annotations

import re

from lxml import etree

SVG_NS = "http://www.w3.org/2000/svg"

from ..icons.library import KEYWORDS, NEUTRAL, SHAPES, WORD_RE, pick, rank  # noqa: F401 — публичный API ветки

SHAPE_TAGS = {"path", "circle", "rect", "line", "polyline", "polygon", "ellipse"}
# Больше этого значок не бывает: за границей начинаются иллюстрации и графики,
# которые подменять нельзя.
MAX_ICON_PX = 96.0
# Доля габарита значка, которую занимает контур. Меньше единицы — у иконок
# принято поле по краю.
ICON_FILL = 0.84


def _icon_hosts(section: etree._Element) -> list[tuple[etree._Element, str]]:
    """Где в разметке лежат значки и как в них ложатся наши контуры.

    Шаблоны рисуют иконки двояко: одни держат их группой, сдвинутой
    трансформом внутри общего рисунка, другие — отдельным маленьким `<svg>` на
    свой значок. В первом случае наши контуры встают как есть — они в той же
    системе координат; во втором их надо перенести в центр вьюбокса и
    подогнать по размеру.
    """
    hosts: list[tuple[etree._Element, str]] = []
    for node in section.iter():
        if not isinstance(node.tag, str):
            continue
        children = [child for child in node if isinstance(child.tag, str)]
        if not children:
            continue
        if {child.tag.split("}")[-1] for child in children} - SHAPE_TAGS:
            continue                             # внутри не голые контуры

        tag = node.tag.split("}")[-1]
        if tag == "g" and "translate" in (node.get("transform") or ""):
            hosts.append((node, ""))
        elif tag == "svg" and _is_icon_size(node):
            placement = _placement(node)
            if placement:
                hosts.append((node, placement))
    return hosts


def _is_icon_size(svg: etree._Element) -> bool:
    """Значок ли это по размеру. У диаграммы и иллюстрации габарит больше."""
    for name in ("width", "height"):
        raw = re.match(r"[\d.]+", (svg.get(name) or "").strip())
        if raw is None or float(raw.group()) > MAX_ICON_PX:
            return False
    return True


def _placement(svg: etree._Element) -> str:
    """Перенос наших контуров в центр вьюбокса значка."""
    # Разбор HTML приводит имена атрибутов к нижнему регистру, а в разметке
    # шаблона стоит камелькейс — смотрим оба написания.
    box = svg.get("viewBox") or svg.get("viewbox") or ""
    parts = re.findall(r"-?[\d.]+", box)
    if len(parts) != 4:
        return ""
    left, top, width, height = (float(value) for value in parts)
    if width <= 0 or height <= 0:
        return ""
    # Контуры набора уложены в габарит ±8 вокруг нуля.
    scale = min(width, height) * ICON_FILL / 16
    return f"translate({left + width / 2:g} {top + height / 2:g}) scale({scale:g})"


def apply_icons(section: etree._Element, texts: list[str]) -> tuple[int, int]:
    """Заменяет иконки шаблона на подходящие по смыслу.

    Возвращает пару «подобрано по смыслу, заменено нейтральной».

    Иконки и тексты сопоставляются по порядку: и те и другие идут в разметке в
    порядке чтения. Если смысл не распознан, ставится нейтральная метка: значок
    шаблона там оставлять нельзя — он подобран под его собственный текст, и
    робот рядом с санным спортом выглядит нелепее любой абстрактной фигуры.
    """
    # Голая цифра тезисом не является: «34 %» смысла иконке не даёт, а место в
    # соответствии занимает и сдвигает подписи относительно значков.
    texts = [text for text in texts if WORD_RE.search(text or "")]

    hosts = _icon_hosts(section)
    if not hosts or not texts:
        return 0, 0

    # Если значки привязаны к долям диаграммы, порядок берём оттуда: по кругу
    # они идут в порядке данных, а в разметке — как их расставил дизайнер.
    if all(host.get("data-sector") is not None for host, _ in hosts):
        hosts.sort(key=lambda item: int(item[0].get("data-sector")))

    matched = neutral = 0
    taken: set[str] = set()
    for (host, placement), text in zip(hosts, texts):
        # Один и тот же значок трижды в ряд читается как недоделка, даже когда
        # он верен для каждой карточки по отдельности. Берём лучший из ещё не
        # занятых на этом слайде: второй по счёту смысл в тезисе тоже есть.
        name = next((candidate for candidate in rank(text)
                     if candidate not in taken), None)
        shapes = SHAPES[name or NEUTRAL]
        markup = (f'<g xmlns="{SVG_NS}" transform="{placement}">{shapes}</g>'
                  if placement else f'<g xmlns="{SVG_NS}">{shapes}</g>')
        try:
            replacement = etree.fromstring(markup)
        except etree.XMLSyntaxError:
            continue

        for child in list(host):
            host.remove(child)
        if placement:
            host.append(replacement)             # перенос нужен — кладём группой
        else:
            # У группы шаблона свой сдвиг уже есть, второй сломал бы положение.
            for child in replacement:
                host.append(child)
        host.set("data-icon", name or NEUTRAL)
        if name is None:
            neutral += 1
        else:
            taken.add(name)
            matched += 1
    return matched, neutral
