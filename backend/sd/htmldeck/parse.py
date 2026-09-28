"""Разбор HTML-шаблона презентации (.dc.html) на паттерны и дизайн-систему.

Формат простой и потому пригодный для машины: колода — это `<x-import>` с
набором `<section data-label="…">`, у каждой секции всё оформление записано в
атрибуте `style`, классов нет. Один `<section>` — один макет.

Слоты ищутся не по разметке, а по типографике: самый крупный текст в секции —
заголовок, повторяющиеся однотипные контейнеры — карточки, крупное число рядом
с мелкой подписью — показатель. Ёмкость слота берётся из самого шаблона: если
дизайнер написал в подписи сорок знаков, значит столько туда и влезает.

Главное свойство разбора: он ничего не выбрасывает. Круги, донаты, шевроны,
градиенты и иконки остаются в разметке нетронутыми — при сборке мы подменяем
только текст в найденных слотах.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field

from lxml import etree, html as lxml_html

# Текстовые узлы мельче этого кегля — подписи и служебные пометки.
KICKER_MAX_PX = 34.0
# Во сколько раз число крупнее своей подписи в карточке показателя.
METRIC_RATIO = 1.8


@dataclass
class Slot:
    """Место под текст: где оно в разметке, что там стояло и сколько влезает."""

    path: str                      # индексный путь от секции: "1/0/2"
    role: str
    sample: str                    # текст шаблона — он же образец объёма
    font_px: float
    bold: bool
    group: str = ""                # ключ повторяющейся группы, если слот в ней
    order: int = 0                 # номер внутри группы
    budget: int = 0                # эталонная длина образца для такого же места

    @property
    def measure(self) -> int:
        """Длина образца, по которой меряется объём текста."""
        return self.budget or len(self.sample)

    @property
    def capacity(self) -> int:
        """Сколько знаков сюда положить. Дизайнер уже отмерил — берём с запасом."""
        return max(12, int(self.measure * 1.35))

    @property
    def is_number(self) -> bool:
        """Слот под число: «87 %», «1,5 года», «×3».

        Раскладка «большая цифра» держит там кегль в двести пунктов. Фраза,
        попавшая в такой слот, занимает пол-экрана и обрывается многоточием —
        поэтому такие места нужно узнавать и отдавать им только числа.
        """
        body = self.sample.replace(" ", "").replace(" ", "")
        if not body or len(body) > 14:
            return False
        digits = sum(character.isdigit() for character in body)
        return digits > 0 and digits >= len(body) * 0.4


@dataclass
class Pattern:
    """Макет: секция шаблона со списком слотов."""

    label: str
    index: int
    archetype: str
    slots: list[Slot] = field(default_factory=list)
    groups: dict[str, int] = field(default_factory=dict)   # группа -> число карточек
    group_roots: dict[str, str] = field(default_factory=dict)
    """(группа, номер) -> путь карточки. Нужен, чтобы убрать лишние карточки."""
    has_chart: bool = False
    """В секции есть секторная диаграмма — сектора можно пересобрать под данные."""

    @property
    def id(self) -> str:
        return f"{self.archetype}-{self.index:02d}"

    def by_role(self, role: str) -> list[Slot]:
        return [slot for slot in self.slots if slot.role == role]


@dataclass
class HtmlTemplate:
    """Разобранная колода-шаблон."""

    name: str
    head: str                      # содержимое <helmet>: шрифты и базовые стили
    stage_open: str                # открывающий тег <x-import …> со всеми атрибутами
    sections: list[etree._Element]
    patterns: list[Pattern]
    width: int = 1920
    height: int = 1080

    def pattern(self, pattern_id: str) -> Pattern | None:
        return next((item for item in self.patterns if item.id == pattern_id), None)


# --- разбор документа --------------------------------------------------------

def _style_of(node: etree._Element) -> dict[str, str]:
    raw = node.get("style") or ""
    result: dict[str, str] = {}
    for chunk in raw.split(";"):
        if ":" in chunk:
            key, value = chunk.split(":", 1)
            result[key.strip().lower()] = value.strip()
    return result


def _font_px(node: etree._Element, inherited: float) -> float:
    value = _style_of(node).get("font-size", "")
    match = re.match(r"([\d.]+)px", value)
    if match:
        return float(match.group(1))
    # У заголовочных тегов свой кегль по умолчанию — но в этих шаблонах он
    # всегда задан явно, поэтому наследуем.
    return inherited


def _is_bold(node: etree._Element, inherited: bool) -> bool:
    weight = _style_of(node).get("font-weight", "")
    if weight.isdigit():
        return int(weight) >= 600
    if weight in ("bold", "bolder"):
        return True
    if node.tag in ("h1", "h2", "h3", "b", "strong"):
        return True
    return inherited


def _own_text(node: etree._Element) -> str:
    """Текст самого узла без вложенных — пробелы схлопнуты."""
    parts = [node.text or ""]
    parts += [child.tail or "" for child in node]
    return re.sub(r"\s+", " ", "".join(parts)).strip()


def _signature(node: etree._Element) -> str:
    """Отпечаток контейнера: тег плюс ключевые свойства оформления.

    По нему узнаются карточки одной сетки: у них разметка одинаковая, а
    отличаются только текст и, иногда, цвет акцента.
    """
    style = _style_of(node)
    keys = ("display", "border-radius", "padding", "flex-direction",
            "grid-template-columns", "border-top", "border-left", "gap", "background")
    marks = [f"{key}={_without_colors(style[key])}" for key in keys if key in style]
    return f"{node.tag}|" + ";".join(marks)


def _without_colors(value: str) -> str:
    """Убирает цвет из значения свойства.

    Карточки одной сетки часто отличаются только акцентом: первая и последняя
    с цветной полоской сверху, средние — с приглушённой. Структурно это одна и
    та же карточка, и разводить их по разным группам нельзя.
    """
    value = re.sub(r"#[0-9a-fA-F]{3,8}", "", value)
    value = re.sub(r"(rgb|rgba|hsl|hsla)\([^)]*\)", "", value)
    return re.sub(r"\s+", " ", value).strip()


def _children(node: etree._Element) -> list[etree._Element]:
    """Дети-элементы. Одна функция на весь разбор: пути должны совпадать везде.

    lxml создаёт новый объект-обёртку при каждом обращении к узлу, поэтому
    запоминать элементы по `id()` нельзя — вместо этого всё адресуется путём
    вида «1/0/2», и он обязан считаться одинаково во всех обходах.
    """
    return [child for child in node if isinstance(child.tag, str)]


def _text_nodes(section: etree._Element) -> list[tuple[str, etree._Element, float, bool]]:
    """Все узлы с собственным текстом: путь, узел, кегль, полужирность."""
    found: list[tuple[str, etree._Element, float, bool]] = []

    def walk(node: etree._Element, path: str, font: float, bold: bool) -> None:
        font = _font_px(node, font)
        bold = _is_bold(node, bold)
        if _own_text(node):
            found.append((path, node, font, bold))
        for index, child in enumerate(_children(node)):
            if child.tag in ("script", "style", "svg"):
                continue
            walk(child, f"{path}/{index}" if path else str(index), font, bold)

    walk(section, "", 32.0, False)
    return found


def _repeat_groups(section: etree._Element,
                   roots: dict[str, str] | None = None) -> dict[str, tuple[str, int]]:
    """Ищет ряды одинаковых контейнеров: путь узла -> (ключ группы, номер).

    Сетка карточек — это несколько соседей с одинаковым отпечатком. Именно они
    дают шаблону повторяемость: сколько карточек нарисовал дизайнер, столько
    мыслей туда и войдёт. Группа приписывается и самой карточке, и всему, что
    внутри неё, — текст лежит во вложенных узлах.
    """
    groups: dict[str, tuple[str, int]] = {}
    roots = {} if roots is None else roots

    # Кандидаты собираются по всей секции, а не только среди родных братьев:
    # четыре одинаковые карточки, разложенные по двум колонкам, — это одна
    # сетка из четырёх, а не две пары. Ключ корзины — глубина, отпечаток
    # родителя и собственный отпечаток: так «карточка в колонке» не смешается
    # со случайно похожим элементом из другой части слайда.
    entries: list[tuple[int, str, str, str, etree._Element]] = []

    def collect(parent: etree._Element, path: str, parent_sig: str) -> None:
        for index, child in enumerate(_children(parent)):
            child_path = f"{path}/{index}" if path else str(index)
            sig = _signature(child)
            entries.append((child_path.count("/"), parent_sig, sig, child_path, child))
            collect(child, child_path, sig)

    collect(section, "", "root")

    buckets: dict[tuple[int, str, str], list[tuple[str, etree._Element]]] = {}
    for depth, parent_sig, sig, path, node in entries:
        buckets.setdefault((depth, parent_sig, sig), []).append((path, node))

    def mark(node: etree._Element, path: str, key: str, order: int) -> None:
        groups.setdefault(path, (key, order))
        for index, child in enumerate(_children(node)):
            mark(child, f"{path}/{index}", key, order)

    def assign(members: list[tuple[str, etree._Element]], bucket_key) -> None:
        key = f"g{abs(hash(bucket_key)) % 10000}"
        for order, (path, node) in enumerate(members):
            roots.setdefault(f"{key}#{order}", path)
            mark(node, path, key, order)

    # Сначала контейнеры, и глубокие раньше мелких: карточка внутри колонки
    # должна забрать свои тексты прежде, чем колонка-обёртка заберёт всё.
    container_buckets = sorted(
        ((bucket_key, members) for bucket_key, members in buckets.items()
         if 2 <= len(members) <= 16 and any(_children(node) for _, node in members)),
        key=lambda item: -item[0][0])
    for bucket_key, members in container_buckets:
        assign(members, bucket_key)

    # Повторяющиеся текстовые строки без обёртки (пункты повестки) — группа
    # сами по себе, но только если их ещё не забрала карточка.
    for bucket_key, members in buckets.items():
        if not (2 <= len(members) <= 16):
            continue
        free = [(path, node) for path, node in members if path not in groups]
        if len(free) >= 2 and not any(_children(node) for _, node in free):
            assign(free, bucket_key)

    return groups


def _has_sector_chart(section: etree._Element) -> bool:
    """Есть ли в секции диаграмма — секторная или столбиковая."""
    from .charts import detect_chart

    return detect_chart(section) is not None


ARCHETYPE_BY_LABEL = {
    "обложка": "cover", "титул": "cover", "финал": "contacts", "контакты": "contacts",
    "содержание": "agenda", "оглавление": "agenda", "повестка": "agenda",
    "раздел": "section", "разделитель": "section",
    "таблица": "table", "цитата": "quote", "таймлайн": "process", "план": "process",
    "этапы": "process", "задел": "process", "сравнение": "comparison",
    "показатели": "metrics", "метрики": "metrics", "kpi": "metrics",
    "большая цифра": "metrics", "цифра": "metrics",
    "донат": "chart", "арка": "chart", "график": "chart", "диаграмма": "chart",
    "карточки": "bullets", "две колонки": "two_column", "колонки": "two_column",
    "команда": "team", "галерея": "gallery",
}


def _archetype(label: str, slots: list[Slot], groups: dict[str, int]) -> str:
    lowered = label.lower()
    for key, value in ARCHETYPE_BY_LABEL.items():
        if key in lowered:
            return value
    if any(slot.role == "metric_value" for slot in slots):
        return "metrics"
    if groups:
        return "bullets"
    return "bullets"


def _assign_roles(slots: list[tuple[str, etree._Element, float, bool]],
                  groups: dict[str, tuple[str, int]]) -> list[Slot]:
    """Роль слота — из типографики и места в повторяющейся группе."""
    if not slots:
        return []

    largest = max(font for _, _, font, _ in slots)
    result: list[Slot] = []
    title_taken = False

    for path, node, font, bold in slots:
        group, order = groups.get(path, ("", 0))
        text = _own_text(node)

        if group:
            # Внутри карточки крупное — это либо число, либо заголовок карточки.
            siblings = [item for item in slots
                        if groups.get(item[0], ("", -1)) == (group, order)]
            top = max(item[2] for item in siblings) if siblings else font
            if font >= top:
                digits = sum(character.isdigit() for character in text)
                role = ("metric_value" if digits and len(text) <= 12
                        and len(siblings) > 1 else "item")
            else:
                role = "metric_label" if any(
                    item[2] >= font * METRIC_RATIO for item in siblings) else "body"
        elif not title_taken and font >= largest * 0.85:
            role, title_taken = "title", True
        elif font <= KICKER_MAX_PX:
            role = "kicker"
        else:
            role = "body"

        result.append(Slot(path=path, role=role, sample=text, font_px=font,
                           bold=bold, group=group, order=order))
    _equalize(result)
    return result


def _equalize(slots: list[Slot]) -> None:
    """Уравнивает вместимость одинаковых мест в повторяющихся карточках.

    Карточки списка сделаны по одной мерке, а образцы в них разной длины: в
    одной строка на сорок знаков, в другой на двадцать. Мерить каждую по себе —
    значит обрезать текст там, где место есть: дизайнер отмерил карточку по
    самой длинной строке. Поэтому вместимость берётся общая на всю группу.
    """
    families: dict[tuple[str, str, int], list[Slot]] = {}
    seen: dict[tuple[str, int, str], int] = {}
    for slot in slots:
        if not slot.group:
            continue
        # Место внутри карточки: какая по счёту надпись этой роли.
        key = (slot.group, slot.order, slot.role)
        position = seen.get(key, 0)
        seen[key] = position + 1
        families.setdefault((slot.group, slot.role, position), []).append(slot)

    for family in families.values():
        budget = max(len(slot.sample) for slot in family)
        for slot in family:
            slot.budget = budget


def _node_at(section: etree._Element, path: str) -> etree._Element | None:
    node = section
    if path:
        for step in path.split("/"):
            children = [child for child in node if isinstance(child.tag, str)]
            index = int(step)
            if index >= len(children):
                return None
            node = children[index]
    return node


def parse_template(path) -> HtmlTemplate:
    """Читает .dc.html и возвращает шаблон с макетами."""
    from pathlib import Path

    source = Path(path).read_text(encoding="utf-8")
    document = lxml_html.fromstring(source)

    helmet = document.find(".//helmet")
    head = ("".join(lxml_html.tostring(child, encoding="unicode") for child in helmet)
            if helmet is not None else "")

    stage = document.find(".//x-import")
    stage_open = ""
    width, height = 1920, 1080
    if stage is not None:
        attributes = " ".join(f'{key}="{value}"' for key, value in stage.attrib.items())
        stage_open = f"<x-import {attributes}>"
        width = int(stage.get("width") or width)
        height = int(stage.get("height") or height)

    sections = document.findall(".//section")
    patterns: list[Pattern] = []
    for index, section in enumerate(sections):
        roots: dict[str, str] = {}
        groups = _repeat_groups(section, roots)
        slots = _assign_roles(_text_nodes(section), groups)
        counts: dict[str, int] = {}
        for key, order in groups.values():
            counts[key] = max(counts.get(key, 0), order + 1)
        label = section.get("data-label") or f"Макет {index + 1}"
        patterns.append(Pattern(label=label, index=index,
                                archetype=_archetype(label, slots, counts),
                                slots=slots, groups=counts, group_roots=roots,
                                has_chart=_has_sector_chart(section)))

    return HtmlTemplate(name=Path(path).stem, head=head, stage_open=stage_open,
                        sections=sections, patterns=patterns,
                        width=width, height=height)
