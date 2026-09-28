"""Укладка контента в слоты паттерна.

Матчер решил, какой макет взять; здесь решается, что положить в каждый слот и
что делать, если не влезает. Порядок исправлений — от дешёвого к дорогому:
уменьшить кегль в пределах, заданных шаблоном, срезать хвост списка, попросить
модель переписать короче. Всё, что не удалось починить, остаётся в отчёте с
координатами — иначе «без ручного редактирования» проверить нельзя.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from typing import Literal

from ..content.model import Block, ContentIR
from ..template.area import CONTENT_GAP, EDGE, content_area  # noqa: F401 — публичный API укладки
from ..template.model import DesignSystem, Pattern, Slot
from .reflow import reflow_slide
from .textmetrics import SAMPLE_EN, SAMPLE_RU, capacity_chars, metrics_for, wrap_lines

FillKind = Literal["text", "items", "image", "chart", "table", "diagram", "icon", "empty"]


@dataclass
class SlotFill:
    slot: Slot
    kind: FillKind = "empty"
    text: str = ""
    items: list[str] = field(default_factory=list)
    block_id: str | None = None
    size_pt: float | None = None      # после уменьшения кегля
    lead_size_pt: float | None = None
    """Кегль первой строки: крупная цифра метрики над подписью."""
    lines: int = 0
    notes: list[str] = field(default_factory=list)

    @property
    def is_empty(self) -> bool:
        return self.kind == "empty" or (not self.text and not self.items
                                        and self.kind not in ("chart", "table", "image"))


@dataclass
class FilledSlide:
    n: int
    pattern: Pattern
    fills: list[SlotFill] = field(default_factory=list)
    dropped: list[str] = field(default_factory=list)
    defects: list[str] = field(default_factory=list)
    notes: list[str] = field(default_factory=list)

    def by_role(self, role: str) -> list[SlotFill]:
        return [fill for fill in self.fills if fill.slot.role == role]

    @property
    def used_slots(self) -> int:
        return sum(1 for fill in self.fills if not fill.is_empty)


MINOR_RATIO = 0.45

# Минимальный размер поля, в которое имеет смысл класть таблицу или график,
# если своего слота у шаблона нет: в подпись под фотографией они не влезают.
MEDIA_MIN_W = 0.35
MEDIA_MIN_H = 0.22
# Графику нужно больше: оси и подписи в полоске высотой в пятую часть слайда
# не прочитать.
CHART_MIN_H = 0.3
MEDIA_MIN_COLUMN_W = 0.17           # доля ширины слайда на одну колонку таблицы
MEDIA_MAX_W = 0.7                   # шире поля в шаблонах практически не бывают           # доля от самого ёмкого слота, ниже которой слот — подпись


# Уже этой доли ширины слайда текст не читается: стикер, подпись к рисунку,
# метка на схеме. Абзац в таком поле переносится по слогам.
PROSE_MIN_W = 0.12
# Во сколько раз самое длинное слово должно быть уже строки — на подстановку
# шрифта и кернинг, которых расчёт не видит.
WORD_SLACK = 1.12


def _major_slots(slots: list[Slot]) -> list[Slot]:
    """Слоты, несущие содержание, в порядке чтения.

    Если все слоты примерно одного размера — это равноправные карточки, берём
    все. Если есть заметно более мелкие, они играют роль подписей: содержание
    туда не кладём. Узкие полоски не берём вовсе, сколько бы знаков в них ни
    влезало по площади.
    """
    slots = [slot for slot in slots if slot.bbox[2] >= PROSE_MIN_W]
    if len(slots) < 2:
        return list(slots)
    largest = max(slot.capacity.chars for slot in slots) or 1
    major = [slot for slot in slots if slot.capacity.chars >= largest * MINOR_RATIO]
    chosen = major or list(slots)
    return sorted(chosen, key=lambda slot: (round(slot.bbox[1], 2), slot.bbox[0]))


def _emphasis_size(design: DesignSystem) -> float | None:
    """Кегль для крупной цифры — из шкалы самого шаблона, а не выдуманный.

    Если у шаблона есть собственный стиль крупного числа, берём его; иначе —
    самый крупный кегль, который шаблон вообще использует.
    """
    style = design.typography.styles.get("metric_value")
    if style and style.size_pt:
        return style.size_pt
    return max(design.typography.scale_pt) if design.typography.scale_pt else None


def _sorted_slots(pattern: Pattern, role: str) -> list[Slot]:
    """Слоты роли в порядке чтения: сверху вниз, слева направо."""
    return sorted((slot for slot in pattern.slots if slot.role == role),
                  key=lambda slot: (round(slot.bbox[1], 2), slot.bbox[0]))


def _style_of(design: DesignSystem, slot: Slot):
    return design.typography.styles.get(slot.style)


def _measure(text: str, slot: Slot, design: DesignSystem, size_pt: float,
             sample: str, budget: float = 1.0) -> tuple[int, bool]:
    """Сколько строк займёт текст и влезает ли он в слот при данном кегле.

    `budget` — доля ёмкости, которой разрешено пользоваться. Цикл ремонта
    ужимает её для слайдов, где рендер показал переполнение: измерение по
    метрикам шрифта бывает оптимистичнее реальной вёрстки PowerPoint.
    """
    style = _style_of(design, slot)
    width, height = design.source.slide_size.w_emu, design.source.slide_size.h_emu
    # Начертание берём у самого слота: жирный текст на десятую шире, и мерить
    # его светлым — значит обещать строку, в которую слово не влезет.
    metrics = metrics_for(slot.font or (style.font if style else "") or "",
                          slot.bold or bool(style and style.bold),
                          bool(style and style.italic))
    box_w = int(slot.bbox[2] * width)
    box_h = int(slot.bbox[3] * height)

    capacity, max_lines = capacity_chars(box_w, box_h, metrics, size_pt,
                                         style.line_spacing if style else None,
                                         style.caps if style else "none", sample=sample)
    usable_pt = (box_w - 91440 * 2) / 12700
    needed = len(wrap_lines(text, usable_pt, metrics, size_pt,
                            style.caps if style else "none"))
    # Слово шире строки PowerPoint ломает посреди: «распознаван-/ие». Перенос
    # по словам этого не видит — строк-то хватает. Поэтому самое длинное слово
    # обязано влезать в строку целиком, иначе кегль надо уменьшать дальше.
    shown = text.upper() if style and style.caps == "all" else text
    widest = max((metrics.text_width(word, size_pt) for word in shown.split()),
                 default=0.0)
    # Запас на подстановку шрифта: если гарнитуры шаблона нет в системе, ширины
    # считаются по соседней, и жирное слово выходит шире расчёта.
    fits = (needed <= max(1, int(max_lines * budget))
            and len(text) <= max(capacity, 1) * 1.15 * budget
            and widest * WORD_SLACK <= usable_pt)
    return needed, fits


def _scale_below(design: DesignSystem, size: float) -> list[float]:
    """Ступени типографической шкалы шаблона ниже данного кегля, по убыванию."""
    steps = {round(step, 1) for step in design.typography.scale_pt}
    steps |= {round(style.size_pt, 1) for style in design.typography.styles.values()
              if style.size_pt}
    return sorted((step for step in steps if step < size - 0.5), reverse=True)


def _shrink_to_fit(fill: SlotFill, design: DesignSystem, pattern: Pattern,
                   sample: str, budget: float = 1.0) -> None:
    """Ступень 1: уменьшаем кегль, но не ниже порога, заданного шаблоном."""
    text = fill.text or "\n".join(fill.items)
    if not text:
        return

    # Замечания о подгонке пересчитываются заново: иначе вердикт от прошлой
    # попытки остаётся в списке и следующая ступень считает, что не помогла.
    fill.notes = [note for note in fill.notes
                  if "кегль" not in note and "не влезает" not in note]
    style = _style_of(design, fill.slot)
    size = fill.slot.size_pt or (style.size_pt if style else None) or 18.0
    minimum = float(pattern.fit.get("min_size_pt", 12))
    step = float(pattern.fit.get("shrink_step", 0.9))

    lines, fits = _measure(text, fill.slot, design, size, sample, budget)
    ladder = _scale_below(design, size)
    while not fits:
        # Спускаемся по шкале шаблона, чтобы кегль оставался «его»; если
        # ближайшая ступень слишком далеко (шкала редкая), шаг геометрический.
        geometric = size * step
        candidate = ladder.pop(0) if ladder and ladder[0] >= geometric * step else geometric
        if candidate < minimum:
            break
        size = candidate
        lines, fits = _measure(text, fill.slot, design, size, sample, budget)

    fill.size_pt = round(size, 1)
    fill.lines = lines
    if fill.size_pt < (fill.slot.size_pt or size):
        fill.notes.append(f"кегль уменьшен до {fill.size_pt}")
    if not fits:
        fill.notes.append("не влезает даже на минимальном кегле")


def _trim_items(fill: SlotFill, design: DesignSystem, pattern: Pattern,
                sample: str, budget: float = 1.0) -> list[str]:
    """Ступень 2: срезаем хвост списка — только то, что действительно не влезло."""
    dropped: list[str] = []
    while len(fill.items) > 1:
        _shrink_to_fit(fill, design, pattern, sample, budget)
        if "не влезает" not in " ".join(fill.notes):
            break
        dropped.append(fill.items.pop())
        fill.notes = [note for note in fill.notes if "не влезает" not in note]

    # Пометку о переполнении мы снимали перед каждым срезом, поэтому последнее
    # слово должно остаться за фактом, а не за отменённым вердиктом: один
    # оставшийся пункт может не влезать сам по себе, и следующие ступени об
    # этом узнают только отсюда.
    _shrink_to_fit(fill, design, pattern, sample, budget)
    return dropped


def _shorten_with_model(fill: SlotFill, design: DesignSystem, pattern: Pattern,
                        sample: str, budget: float, client, context: str) -> bool:
    """Ступень 3: просим модель переписать короче — до того, как резать по словам."""
    from .shorten import shorten

    limit = int(max(20, fill.slot.capacity.chars * budget))
    shortened = shorten(fill.text, limit, client, context)
    if not shortened:
        return False

    original, fill.text = fill.text, shortened
    _shrink_to_fit(fill, design, pattern, sample, budget)
    if any("не влезает" in note for note in fill.notes):
        fill.text = original
        _shrink_to_fit(fill, design, pattern, sample, budget)
        return False
    fill.notes.append(f"текст сокращён моделью до {len(shortened)} знаков")
    return True


def _truncate_to_fit(fill: SlotFill, design: DesignSystem, pattern: Pattern,
                     sample: str, budget: float = 1.0) -> None:
    """Ступень 3: режем текст по словам.

    Это делается только после уменьшения кегля и только когда сокращать нечего:
    обрыв фразы виден зрителю, поэтому ставим многоточие и помечаем дефект —
    здесь должна работать модель, переписывая короче.
    """
    words = (fill.text or "").split()
    if len(words) < 4:
        return
    while len(words) > 3:
        words.pop()
        fill.text = " ".join(words) + "…"
        _shrink_to_fit(fill, design, pattern, sample, budget)
        if not any("не влезает" in note for note in fill.notes):
            fill.notes.append("текст обрезан по словам")
            return


# --- распределение контента по слотам ---------------------------------------

def _fill_title(slide, pattern: Pattern, fills: dict[int, SlotFill]) -> None:
    for index, slot in enumerate(_sorted_slots(pattern, "title")):
        if index == 0 and slide.plan.key_message:
            fills[id(slot)] = SlotFill(slot, "text", text=slide.plan.key_message)


def _sentences(text: str) -> list[str]:
    return [part for part in re.split(r"(?<=[.!?…])\s+", text.strip()) if part]


def _spread_units(units: list[str], slots: list[Slot], design: DesignSystem,
                  sample: str) -> list[str]:
    """Раскладывает длинный текст по свободным колонкам — по предложениям.

    Абзац, который не влезает в одну колонку, обрезать нельзя, пока рядом
    пустуют другие: именно так дизайнер и пользуется раскладкой на три доли.
    Режем только по границам предложений — разрыв посреди фразы виден сразу,
    и только пока есть куда класть.
    """
    if not units or len(units) >= len(slots):
        return units

    units = list(units)
    while len(units) < len(slots):
        index = max(range(len(units)), key=lambda position: len(units[position]))
        slot = slots[min(index, len(slots) - 1)]
        size = slot.size_pt or (style.size_pt if (style := _style_of(design, slot)) else None) or 18.0
        _, fits = _measure(units[index], slot, design, size, sample)
        sentences = _sentences(units[index])
        if fits or len(sentences) < 2:
            break
        half = max(1, len(sentences) // 2)
        units[index:index + 1] = [" ".join(sentences[:half]), " ".join(sentences[half:])]
    return units


# Слова короче этого при сверке «сказано ли это тезисами» не считаются.
COVER_WORD = 4


def _covered_by(text: str, items: list[str]) -> bool:
    """Сказан ли текст тезисами: почти все его значимые слова есть в них."""
    words = {word.lower() for word in re.findall(r"[\w@.+-]+", text)
             if len(word) >= COVER_WORD}
    if not words:
        return False
    said = " ".join(items).lower()
    return sum(word in said for word in words) / len(words) >= 0.8


NUMBER_TOKEN_RE = re.compile(r"\d+(?:[  ]\d{3})*(?:[.,]\d+)?")


def _norm_number(token: str) -> str:
    return re.sub(r"[  ]", "", token).replace(",", ".")


def _numbers_on_media(taken: dict[int, SlotFill], ir: ContentIR) -> set[str]:
    """Числа из таблиц и рядов, которые уже размещены на слайде."""
    shown: set[str] = set()
    for fill in taken.values():
        if fill.kind not in ("table", "chart") or not fill.block_id:
            continue
        block = ir.block(fill.block_id)
        if block is None:
            continue
        cells = [*block.header, *(cell for row in block.rows for cell in row),
                 *[str(x) for x in block.x],
                 *[str(value) for values in block.y.values() for value in values]]
        for cell in cells:
            shown.update(_norm_number(token) for token in NUMBER_TOKEN_RE.findall(cell))
    return shown


def _drop_title_echo(units: list[str], title: str) -> list[str]:
    """Убирает из текста фразу, которая уже стала заголовком слайда.

    Заголовок часто выводится из первого предложения абзаца — и тогда слайд
    показывает одну и ту же мысль дважды: крупно сверху и мелко снизу. Читатель
    видит не структуру, а повтор. Если после снятия эха от абзаца остаётся
    содержательный остаток, показываем его; если весь абзац и был заголовком,
    выкидываем — заголовок его уже сказал.
    """
    head = title.strip().rstrip("…").rstrip(".").strip().lower()
    if len(head) < 12:
        return units

    result: list[str] = []
    for unit in units:
        lowered = unit.strip().lower()
        if not lowered.startswith(head):
            result.append(unit)
            continue
        rest = unit.strip()[len(head):].lstrip(" .,:;—–-")
        if len(rest) >= 40:
            result.append(rest[0].upper() + rest[1:] if rest else rest)
    return result


def _title_fallback(slide, pattern: Pattern, fills: dict[int, SlotFill]) -> None:
    """Кладёт заголовок в текстовый слот, если слота роли «title» в макете нет.

    У шаблонов, где дизайн нарисован прямо на слайдах, ролей часто нет вовсе:
    все надписи распознаются как «тело». Без этого запасного хода обложка
    выходит пустой — название презентации оказывается негде разместить.
    """
    if not slide.plan.key_message or any(fill.slot.role == "title"
                                         for fill in fills.values()):
        return

    free = [slot for slot in pattern.slots
            if slot.role in ("body", "item", "subtitle", "quote")
            and id(slot) not in fills]
    if not free:
        return

    # Верхний слот — там, где заголовку и место; при равенстве берём крупный.
    best = min(free, key=lambda slot: (round(slot.bbox[1], 2),
                                       -(slot.size_pt or 0), slot.bbox[0]))
    fills[id(best)] = SlotFill(best, "text", text=slide.plan.key_message)


def _content_area(pattern: Pattern, design: DesignSystem, taken: dict[int, SlotFill],
                  role: str, need_w: float, need_h: float = MEDIA_MIN_H) -> Slot | None:
    """Синтетический слот под медиа в свободном поле; накрытые слоты закрывает."""
    box = content_area(pattern, design, need_w, need_h)
    if box is None:
        return None
    area = Slot(role=role, bbox=box, style="body_l1")  # type: ignore[arg-type]
    # Накрытые текстовые слоты — уже не место под текст: две вещи в одном
    # месте хуже, чем одна.
    for slot in pattern.slots:
        if slot.role != "title" and id(slot) not in taken and _overlaps(slot.bbox, box):
            taken[id(slot)] = SlotFill(slot, "empty")
    return area


def _overlaps(a: list[float], b: list[float]) -> bool:
    return (a[0] < b[0] + b[2] and b[0] < a[0] + a[2]
            and a[1] < b[1] + b[3] and b[1] < a[1] + a[3])


# Насколько слот может вырасти вниз, в долях своей высоты. Больше — и текст
# выйдет из карточки, в которой он живёт.
GROW_LIMIT = 3.0
GROW_GAP = 0.015
# Роли, которым расти можно: заголовок и цифра метрики держат композицию.
GROWABLE = {"body", "item", "caption", "metric_label", "quote"}


# Ниже этой доли высоты слот не растёт: там колонтитул и логотип.
GROW_FLOOR = 0.86


def _grow_slot(slot: Slot, pattern: Pattern, taken: dict[int, SlotFill],
               design: DesignSystem | None = None) -> bool:
    """Растягивает слот вниз до соседа снизу или до предела. True — если вырос.

    Границу карточки макет не сообщает, поэтому ориентиры три: ближайший
    занятый слот ниже в том же столбце, декор шаблона под слотом (логотип,
    линия колонтитула) — и потолок роста от собственной высоты, чтобы
    последний ряд карточек не уехал текстом за свой низ.
    """
    if slot.role not in GROWABLE:
        return False
    left, top, width, height = slot.bbox
    bottom = top + height
    floor = min(GROW_FLOOR, top + height * (1 + GROW_LIMIT))
    for item in (design.decor.items if design else []):
        box = item.bbox
        if (box[1] >= bottom - 1e-6 and box[0] < left + width and left < box[0] + box[2]):
            floor = min(floor, box[1] - GROW_GAP)
    for other in pattern.slots:
        if other is slot or other.bbox[1] <= top:
            continue
        fill = taken.get(id(other))
        if fill is not None and fill.is_empty:
            continue                                   # пустой слот не мешает
        horizontally = other.bbox[0] < left + width and left < other.bbox[0] + other.bbox[2]
        if horizontally and other.bbox[1] >= bottom - 1e-6:
            floor = min(floor, other.bbox[1] - GROW_GAP)
    if floor - bottom < 0.02:
        return False
    slot.bbox = [left, top, width, floor - top]
    return True


# Карточка: шапка и описание под ней. Описание лежит не дальше этого зазора
# от низа шапки и перекрывает её по ширине хотя бы наполовину.
CARD_GAP = 0.06
CARD_OVERLAP = 0.02
# Разброс верхних краёв, при котором карточки ещё считаются одним рядом.
ROW_SPREAD = 0.3
CARD_MIN_W = PROSE_MIN_W
CARD_ROLES = {"body", "item", "caption", "metric_label", "metric_value"}


def _cards(pattern: Pattern, taken: dict[int, SlotFill]) -> list[tuple[Slot, Slot | None]]:
    """Карточки макета: пары «шапка — описание» в порядке чтения.

    Разметка не говорит, какие слоты образуют карточку, — это видно по
    геометрии: описание стоит сразу под шапкой и той же ширины. Одиночный слот
    без описания — тоже карточка, только без второго места.
    """
    # Узкая полоска шириной в несколько слов — подпись к рисунку, а не
    # карточка: текст в ней переносится по слогам.
    # Слот под цифру показателя текстом не занимают: «Эффект» кеглем в сто
    # пунктов на месте «в 4 раза» — это не карточка, это ошибка.
    free = [slot for slot in pattern.slots
            if slot.role in CARD_ROLES and slot.role != "metric_value"
            and id(slot) not in taken and slot.bbox[2] >= CARD_MIN_W]
    paired: set[int] = set()
    cards: list[tuple[Slot, Slot | None]] = []
    for head in _reading_order(free):
        if id(head) in paired:
            continue
        desc = _desc_below(head, [slot for slot in free if id(slot) not in paired])
        paired.add(id(head))
        if desc is not None:
            paired.add(id(desc))
        cards.append((head, desc))

    # Ступеньки: карточки одного ряда стоят на разной высоте, и порядок «сверху
    # вниз» их перепутал бы. Если у каждой карточки своя колонка и разброс по
    # высоте невелик — это один ряд, читаем его слева направо. Сетка в два
    # ряда сюда не попадёт: её колонки делят карточки разных рядов.
    if not cards:
        return cards
    by_x = sorted(cards, key=lambda card: card[0].bbox[0])
    own_column = all(_overlap_x(a[0].bbox, b[0].bbox) <= 0.0
                     for a, b in zip(by_x, by_x[1:]))
    tops = [card[0].bbox[1] for card in cards]
    if own_column and max(tops) - min(tops) <= ROW_SPREAD:
        return by_x
    return cards


# Слоты, чьи верхние края расходятся меньше чем на эту долю высоты слайда,
# стоят в одном ряду: в макетах из Google Slides карточки одного ряда
# отличаются по высоте на доли процента, и сортировка «сверху вниз» без
# допуска ставила первую карточку последней.
ROW_TOLERANCE = 0.03


def _reading_order(slots: list[Slot]) -> list[Slot]:
    """Слоты в порядке чтения: ряд за рядом, в ряду — слева направо."""
    rows: list[list[Slot]] = []
    for slot in sorted(slots, key=lambda item: item.bbox[1]):
        if rows and abs(slot.bbox[1] - rows[-1][0].bbox[1]) <= ROW_TOLERANCE:
            rows[-1].append(slot)
        else:
            rows.append([slot])
    return [slot for row in rows for slot in sorted(row, key=lambda item: item.bbox[0])]


def _desc_below(head: Slot, candidates: list[Slot]) -> Slot | None:
    """Слот сразу под шапкой и той же ширины — её описание.

    Лёгкое наложение допускается: в макетах, вывезенных из Google Slides,
    рамки соседних надписей заходят друг на друга на доли процента.
    """
    below = [slot for slot in candidates if slot is not head
             and -CARD_OVERLAP <= slot.bbox[1] - (head.bbox[1] + head.bbox[3]) <= CARD_GAP
             and _overlap_x(head.bbox, slot.bbox) >= 0.5 * min(head.bbox[2], slot.bbox[2])]
    return min(below, key=lambda slot: slot.bbox[1]) if below else None


def _overlap_x(a: list[float], b: list[float]) -> float:
    return max(0.0, min(a[0] + a[2], b[0] + b[2]) - max(a[0], b[0]))


def _overlap_y(a: list[float], b: list[float]) -> float:
    return max(0.0, min(a[1] + a[3], b[1] + b[3]) - max(a[1], b[1]))


def _fill_cards(cards: list[tuple[Slot, Slot | None]], units: list[str],
                metric_parts: dict[str, tuple[str, str]],
                taken: dict[int, SlotFill]) -> list[str]:
    """Раздаёт тезисы по карточкам. Возвращает то, что не поместилось.

    Место в карточке выбирается по тексту, а не по порядку: цифра метрики — в
    шапку, подпись — в описание; короткая фраза — в шапку; длинная — в
    описание, где ей хватит строк, а шапка остаётся свободной. Так тезис не
    режется до трёх слов в однострочной плашке, пока описание под ней пустует.
    """
    rest = list(units)
    for head, desc in cards:
        if not rest:
            break
        unit = rest.pop(0)
        if unit in metric_parts and desc is not None:
            value, label = metric_parts[unit]
            taken[id(head)] = SlotFill(head, "text", text=value)
            taken[id(desc)] = SlotFill(desc, "text", text=label)
            continue
        if desc is None:
            if unit in metric_parts and len(unit) > head.capacity.chars * 1.1:
                # Кружок на таймлайне держит «в 4 раза», но не «в 4 раза —
                # срок обработки сократился». Цифра без подписи читается,
                # подпись, обрезанная по слогам, — нет.
                unit = metric_parts[unit][0]
            taken[id(head)] = SlotFill(head, "text", text=unit)
            continue
        lead, tail = _split_thesis(unit)
        room = max(1, head.capacity.chars)
        if tail and len(lead) <= room * 1.1:
            taken[id(head)] = SlotFill(head, "text", text=lead)
            taken[id(desc)] = SlotFill(desc, "text", text=tail)
        elif len(unit) <= room * 1.1:
            taken[id(head)] = SlotFill(head, "text", text=unit)
        else:
            taken[id(desc)] = SlotFill(desc, "text", text=unit)
            # Шапку держим пустой: иначе в неё ляжет чужой остаток, и над
            # пояснением окажется цифра из другой карточки.
            taken[id(head)] = SlotFill(head, "empty")
    return rest


def _split_thesis(text: str) -> tuple[str, str]:
    """Делит тезис на шапку и пояснение там, где мысль делится сама."""
    parts = re.split(r"(?<=[.!?])\s+", text.strip(), maxsplit=1)
    if len(parts) == 2 and len(parts[0]) <= 60:
        return parts[0].rstrip("."), parts[1]
    if " — " in text:
        lead, tail = text.split(" — ", 1)
        if len(lead) <= 60:
            return lead, tail
    if ": " in text:
        lead, tail = text.split(": ", 1)
        if len(lead) <= 60:
            return lead, tail
    return text, ""


def _metric_pairs(blocks: list[Block]) -> list[tuple[str, str]]:
    return [(block.value, block.label) for block in blocks if block.type == "metric"]


def fill_slide(design: DesignSystem, pattern: Pattern, slide, ir: ContentIR,
               sample: str | None = None, budget: float = 1.0,
               client=None) -> FilledSlide:
    """Раскладывает блоки слайда по слотам паттерна."""
    sample = sample or (SAMPLE_RU if ir.meta.language == "ru" else SAMPLE_EN)
    blocks = [block for block_id in slide.plan.blocks if (block := ir.block(block_id))]
    # Копия: один паттерн может достаться нескольким слайдам, а переразметка
    # меняет геометрию слотов — общий объект испортил бы соседние слайды.
    pattern = pattern.model_copy(deep=True)
    result = FilledSlide(n=slide.n, pattern=pattern)
    taken: dict[int, SlotFill] = {}

    # 1. Заголовок.
    _fill_title(slide, pattern, taken)
    _title_fallback(slide, pattern, taken)

    # 2. Медиа: у графика, таблицы и картинки свои слоты, текстом их не заменить.
    for block in list(blocks):
        role = {"series": "chart", "table": "table", "image": "image"}.get(block.type)
        if role is None:
            continue
        slots = [slot for slot in _sorted_slots(pattern, role) if id(slot) not in taken]
        if slots and block.type == "table":
            # Свой слот под таблицу бывает узким — на три колонки, где
            # «6 дней» переносится по буквам. Если содержательная область
            # шире, таблице лучше там.
            columns = max(len(block.header), max((len(row) for row in block.rows), default=1))
            need_w = min(MEDIA_MAX_W, max(MEDIA_MIN_W, MEDIA_MIN_COLUMN_W * columns))
            if slots[0].bbox[2] < need_w:
                wider = _content_area(pattern, design, taken, role, need_w)
                if wider is not None and wider.bbox[2] > slots[0].bbox[2]:
                    pattern.slots.append(wider)
                    slots = [wider]
        if not slots:
            # У шаблона может не быть ни одного слота под таблицу или график.
            # Молча потерять их нельзя: слайд останется с одним заголовком.
            # Кладём в самое большое свободное текстовое поле — композитор
            # рисует по геометрии слота, а не по его роли. Но подпись под
            # фотографией таблицей не станет: в тесную плашку она не влезет и
            # вылезет за края, поэтому подложка должна быть настоящей.
            # Таблице нужна ширина под каждую колонку: в узком поле заголовки
            # переносятся посреди слова и строки лезут за край.
            columns = (max(len(block.header),
                           max((len(row) for row in block.rows), default=1))
                       if block.type == "table" else 1)
            # Потолок обязателен: у широкого поля редко больше 0.7 ширины
            # слайда, и без него таблица на пять колонок не поместится никуда,
            # хотя ячейки в ней короткие.
            need_w = min(MEDIA_MAX_W, max(MEDIA_MIN_W, MEDIA_MIN_COLUMN_W * columns))
            slots = sorted((slot for slot in pattern.slots
                            if slot.role in ("body", "item") and id(slot) not in taken
                            and slot.bbox[2] >= need_w and slot.bbox[3] >= MEDIA_MIN_H),
                           # Основное поле важнее площади: широкий «body» лучше
                           # держит таблицу, чем высокая колонка списка.
                           key=lambda slot: (slot.role != "body",
                                             -(slot.bbox[2] * slot.bbox[3])))[:1]
        if not slots:
            # В шаблоне может вовсе не быть раскладки под таблицу — у VK Tech
            # её нет. Выбрасывать данные из-за этого нельзя: дизайнер в такой
            # ситуации берёт макет «заголовок + содержимое» и ставит таблицу в
            # содержательную область. Делаем то же: место под медиа — всё
            # свободное поле под заголовком, а текстовые слоты, которые оно
            # накрывает, слайду больше не нужны.
            synthetic = _content_area(pattern, design, taken, role, need_w,
                                      CHART_MIN_H if role == "chart" else MEDIA_MIN_H)
            if synthetic is not None:
                pattern.slots.append(synthetic)
                slots = [synthetic]
                result.notes.append(
                    f"слайд {result.n}: под {block.type} отведена содержательная область")
        if not slots:
            result.defects.append(
                f"слайд {result.n}: в макете нет места под {block.type} — блок не размещён")
            result.dropped.append(f"[{block.type}]")
            blocks.remove(block)
            continue
        taken[id(slots[0])] = SlotFill(slots[0], role, block_id=block.id)  # type: ignore[arg-type]
        blocks.remove(block)

    # 3. Метрики: пары «крупная цифра + подпись».
    metrics = _metric_pairs(blocks)
    value_slots = [slot for slot in _sorted_slots(pattern, "metric_value")
                   if id(slot) not in taken]
    label_slots = [slot for slot in _sorted_slots(pattern, "metric_label")
                   if id(slot) not in taken]
    if metrics and value_slots:
        for (value, label), value_slot in zip(metrics, value_slots):
            taken[id(value_slot)] = SlotFill(value_slot, "text", text=value)
        if label_slots:
            for (_, label), label_slot in zip(metrics, label_slots):
                taken[id(label_slot)] = SlotFill(label_slot, "text", text=label)
        else:
            # Слота под подпись нет — значит, подпись стоит в поле прямо под
            # цифрой. Иначе туда ляжет чужой остаток, и под «в 4 раза»
            # окажется «7 месяцев».
            spare = [slot for slot in pattern.slots
                     if slot.role in ("body", "caption") and id(slot) not in taken]
            for (_, label), value_slot in zip(metrics, value_slots):
                desc = _desc_below(value_slot, spare)
                if desc is not None:
                    taken[id(desc)] = SlotFill(desc, "text", text=label)
                    spare.remove(desc)
        used = min(len(metrics), len(value_slots))
        blocks = [block for block in blocks
                  if block.type != "metric" or _metric_pairs([block])[0] not in metrics[:used]]

    # 4. Текст: списки и метрики без своих слотов уходят в повторяющиеся элементы.
    #    У метрики запоминается разбивка «цифра / подпись» — если ей достанется
    #    отдельный слот, она получит иерархию, а не строку через тире.
    units: list[str] = list(slide.plan.items)
    metric_parts: dict[str, tuple[str, str]] = {}

    # Тезисы плана — это уже выжимка из тех же абзацев. Добавлять к ним сами
    # абзацы значит вернуть на слайд страницу текста, ради ухода от которой
    # тезисы и делались. Цифры и контакты берутся всегда: они не пересказ.
    prose_replaced = bool(slide.plan.items)

    for block in blocks:
        if block.type in ("list", "steps"):
            if not prose_replaced:
                units.extend(block.items)
        elif block.type == "metric":
            unit = f"{block.value} — {block.label}"
            metric_parts[unit] = (block.value, block.label)
            units.append(unit)
        elif block.type == "contact":
            # Контакты берутся всегда — кроме случая, когда план уже разложил
            # их по тезисам: почта, телефон и сайт отдельными строками. Тогда
            # строка целиком — эхо, и «не размещена» она по праву.
            if not (prose_replaced and _covered_by(block.text, slide.plan.items)):
                units.append(block.text)
        elif block.type in ("paragraph", "quote"):
            if not prose_replaced:
                units.append(block.text)

    # Эхо снимаем только там, где заголовок действительно попал на слайд: у
    # раскладки под фотографию во весь кадр слота под него нет, и тогда
    # вычеркнутая фраза не сказана нигде.
    if any(fill.slot.role == "title" and fill.text.strip() for fill in taken.values()):
        units = _drop_title_echo(units, slide.plan.key_message)

    # На слайде с показателями цифры — главное, подводка к ним — второе: места
    # раздаются по порядку, и первую карточку должна занять цифра.
    if slide.plan.intent == "metrics":
        units = ([unit for unit in units if unit in metric_parts]
                 + [unit for unit in units if unit not in metric_parts])

    item_slots = [slot for slot in _sorted_slots(pattern, "item") if id(slot) not in taken]
    body_slots = [slot for slot in _sorted_slots(pattern, "body") if id(slot) not in taken]
    quote_slots = [slot for slot in _sorted_slots(pattern, "quote") if id(slot) not in taken]

    if quote_slots and any(block.type == "quote" for block in blocks):
        quote = next(block for block in blocks if block.type == "quote")
        taken[id(quote_slots[0])] = SlotFill(quote_slots[0], "text", text=quote.text,
                                             block_id=quote.id)
        units = [unit for unit in units if unit != quote.text]

    # Схема процесса: все шаги уходят в один слот, композитор рисует их
    # фигурами. Шаги здесь не режутся и не сокращаются — в карточке схемы
    # кегль подбирается по самому длинному шагу.
    diagram = next((slot for slot in pattern.slots
                    if slot.role == "diagram" and id(slot) not in taken), None)
    if diagram is not None and units:
        taken[id(diagram)] = SlotFill(diagram, "diagram", items=[unit for unit in units])
        units = []

    # Слоты одной карточки не равнозначны: узкая плашка сверху — это подпись к
    # блоку под ней, а не ещё одно место для тезиса. Залитый в неё абзац
    # выглядит именно так, как выглядит текст, попавший не в своё поле.
    # Поэтому содержание кладём в крупные слоты, мелкие оставляем подписям.
    cards = _cards(pattern, taken)
    if units and len(cards) >= 2:
        units = _fill_cards(cards, units, metric_parts, taken)

    candidates = item_slots + body_slots
    text_slots = [slot for slot in _major_slots(candidates) if id(slot) not in taken]
    units = _spread_units(units, text_slots, design, sample)
    if units and text_slots:
        if len(units) <= len(text_slots):
            for slot, unit in zip(text_slots, units):
                if unit in metric_parts:
                    # Цифра и подпись — двумя строками. Кегль здесь не
                    # увеличиваем: слот может быть плашкой в две строки, и
                    # крупная цифра из неё вылезет. Иерархию даёт разбивка.
                    value, label = metric_parts[unit]
                    taken[id(slot)] = SlotFill(slot, "items", items=[value, label])
                else:
                    taken[id(slot)] = SlotFill(slot, "text", text=unit)
        else:
            per_slot = -(-len(units) // len(text_slots))        # ceil
            for index, slot in enumerate(text_slots):
                chunk = units[index * per_slot:(index + 1) * per_slot]
                if chunk:
                    taken[id(slot)] = SlotFill(
                        slot, "items" if len(chunk) > 1 else "text",
                        items=chunk if len(chunk) > 1 else [],
                        text=chunk[0] if len(chunk) == 1 else "")
        units = []

    # 5. Подзаголовок — для обложки: короткое пояснение под названием.
    subtitle_slots = [slot for slot in _sorted_slots(pattern, "subtitle")
                      if id(slot) not in taken]
    if subtitle_slots and (units or ir.meta.subtitle):
        text = units.pop(0) if units else ir.meta.subtitle
        taken[id(subtitle_slots[0])] = SlotFill(subtitle_slots[0], "text", text=text)

    result.dropped.extend(units)

    # 6. Переразметка группы намеренно отключена: у части шаблонов слоты имеют
    #    собственную заливку, и растянутый слот превращается в цветной блок во
    #    весь столбец. Правильнее выбирать подходящий по размеру макет, чем
    #    растягивать неподходящий — этим занимается матчер.

    # 7. Подгонка каждого заполненного слота.
    for slot in pattern.slots:
        fill = taken.get(id(slot), SlotFill(slot, "empty"))
        if fill.kind in ("text", "items"):
            if fill.kind == "items" and len(fill.items) > 1:
                result.dropped.extend(_trim_items(fill, design, pattern, sample, budget))
            else:
                _shrink_to_fit(fill, design, pattern, sample, budget)

            # Список, срезанный до одного пункта, — это тот же абзац, и ступени
            # для него те же: сократить моделью, затем обрезать по словам.
            if fill.kind == "items" and len(fill.items) == 1:
                fill.kind, fill.text, fill.items = "text", fill.items[0], []

            if fill.kind == "text":
                # Прежде чем резать текст, даём слоту место: в карточных
                # раскладках поле под подпись — полоска в одну строку, а под
                # ней пустая карточка. Дизайнер бы просто растянул рамку.
                if any("не влезает" in note for note in fill.notes):
                    if _grow_slot(slot, pattern, taken, design):
                        _shrink_to_fit(fill, design, pattern, sample, budget)
                        fill.notes.append("поле растянуто вниз")
                if any("не влезает" in note for note in fill.notes) and client is not None:
                    _shorten_with_model(fill, design, pattern, sample, budget, client,
                                        slide.plan.key_message)
                if any("не влезает" in note for note in fill.notes):
                    _truncate_to_fit(fill, design, pattern, sample, budget)
            if any("не влезает" in note for note in fill.notes):
                # Последняя ступень: слот физически мал для этого текста.
                # Пустая подпись честнее текста, налезающего на фотографию, —
                # фрагмент уходит в «не размещено» и виден в отчёте.
                result.dropped.append(fill.text or " ".join(fill.items))
                result.defects.append(
                    f"слайд {result.n}: {slot.role} слишком мал для текста — слот оставлен пустым")
                fill.kind = "empty"
                fill.text, fill.items = "", []
        result.fills.append(fill)

    # Тезис, все числа которого уже стоят в таблице или на графике этого
    # слайда, — пересказ данных, а не потеря: таблица его сказала. Такие
    # уходят в заметки, а не в «не размещено», откуда бы их ни срезало.
    shown = _numbers_on_media(taken, ir)
    if shown:
        kept: list[str] = []
        for unit in result.dropped:
            numbers = NUMBER_TOKEN_RE.findall(unit)
            if numbers and all(_norm_number(token) in shown for token in numbers):
                result.notes.append(
                    f"слайд {result.n}: тезис повторяет данные и не нужен: «{unit[:50]}»")
            else:
                kept.append(unit)
        result.dropped = kept
    if result.dropped:
        result.defects.append(
            f"слайд {result.n}: не размещено фрагментов — {len(result.dropped)}")
    return result


def fill_deck(design: DesignSystem, spec, ir: ContentIR,
              budgets: dict[int, float] | None = None, client=None) -> list[FilledSlide]:
    """Укладка всей колоды. `budgets` задаёт послайдовое ужатие для цикла ремонта."""
    filled: list[FilledSlide] = []
    for slide in spec.slides:
        pattern = design.pattern(slide.pattern_id)
        if pattern is None:
            continue
        filled.append(fill_slide(design, pattern, slide, ir,
                                 budget=(budgets or {}).get(slide.n, 1.0),
                                 client=client))
    return filled
