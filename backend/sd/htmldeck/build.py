"""Сборка презентации в HTML-шаблоне.

Секция шаблона копируется целиком и в ней подменяется только текст найденных
слотов. Всё остальное — градиенты, донаты, орбиты, шевроны, иконки — остаётся
ровно таким, каким его нарисовал дизайнер. Лишние карточки в сетке удаляются:
три мысли в раскладке на четыре карточки оставили бы пустую.
"""

from __future__ import annotations

import copy
import re
from dataclasses import dataclass, field
from pathlib import Path

from lxml import etree, html as lxml_html

from ..content.model import Block, ContentIR
from ..plan.model import DeckPlan, SlidePlan
from .parse import HtmlTemplate, Pattern, Slot, _children, _node_at

# Насколько макет одного замысла годится под другой.
AFFINITY: dict[tuple[str, str], float] = {
    ("bullets", "two_column"): 0.6, ("bullets", "agenda"): 0.5, ("bullets", "metrics"): 0.4,
    ("bullets", "process"): 0.4, ("agenda", "bullets"): 0.7, ("metrics", "bullets"): 0.4,
    ("metrics", "process"): 0.4, ("comparison", "table"): 0.6, ("comparison", "two_column"): 0.6,
    ("process", "bullets"): 0.5, ("process", "metrics"): 0.4, ("table", "comparison"): 0.6,
    ("two_column", "bullets"): 0.6, ("quote", "section"): 0.4, ("contacts", "section"): 0.5,
    ("chart", "metrics"): 0.6, ("metrics", "chart"): 0.5, ("chart", "bullets"): 0.3,
    ("cover", "section"): 0.4, ("section", "cover"): 0.4, ("table", "bullets"): 0.3,
}


@dataclass
class SlideResult:
    n: int
    label: str
    archetype: str
    filled: int = 0
    dropped_cards: int = 0
    animated: int = 0
    notes: list[str] = field(default_factory=list)


@dataclass
class BuildResult:
    path: Path
    slides: list[SlideResult] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)
    rewritten: int = 0
    """Сколько обрезанных фрагментов модель переписала короче."""


def _affinity(intent: str, archetype: str) -> float:
    if intent == archetype:
        return 1.0
    return AFFINITY.get((intent, archetype), 0.12)


def _demand(slide: SlidePlan, ir: ContentIR) -> tuple[list[str], list[tuple[str, str]], str]:
    """Что просит слайд: тезисы, пары «цифра/подпись», связный текст."""
    items: list[str] = list(slide.items)
    metrics: list[tuple[str, str]] = []
    prose: list[str] = []

    # Тезисы плана заменяют пересказываемые ими абзацы: иначе на слайд поедет
    # и выжимка, и исходный текст.
    prose_replaced = bool(slide.items)

    for block_id in slide.blocks:
        block: Block | None = ir.block(block_id)
        if block is None:
            continue
        if block.type in ("list", "steps"):
            if not prose_replaced:
                items.extend(block.items)
        elif block.type == "metric":
            metrics.append((block.value, block.label))
        elif block.type == "contact":
            prose.append(block.text)
        elif block.type in ("paragraph", "quote"):
            if not prose_replaced:
                prose.append(block.text)

    if not metrics:
        # План часто ссылается на список, а не на извлечённые из него метрики.
        # Для слайда-диаграммы цифры нужны отдельно — подтягиваем метрики,
        # производные от блоков этого слайда: те же данные, но в форме
        # «значение / подпись», из которой строятся сектора.
        wanted = set(slide.blocks)
        metrics = [(block.value, block.label) for block in ir.blocks
                   if block.type == "metric" and block.derived_from in wanted]
    return items, metrics, " ".join(prose)


def _path_key(path: str) -> tuple[int, ...]:
    """Путь узла как числа: «1/10» идёт после «1/9», а не перед ним."""
    return tuple(int(part) for part in path.split("/") if part.isdigit())


def _main_group(pattern: Pattern, role: str) -> str:
    """Группа карточек, несущая содержание: самая многочисленная с нужной ролью."""
    counts: dict[str, int] = {}
    for slot in pattern.slots:
        if slot.group and slot.role == role:
            counts[slot.group] = max(counts.get(slot.group, 0), slot.order + 1)
    if not counts:
        return ""
    return max(counts, key=lambda key: counts[key])


def _figure_slot(pattern: Pattern) -> Slot | None:
    """Самый крупный слот под число вне карточек — «большая цифра» макета."""
    candidates = [slot for slot in pattern.slots if not slot.group and slot.is_number]
    return max(candidates, key=lambda slot: slot.font_px) if candidates else None


def _estimate(pattern: Pattern, slide: SlidePlan, ir: ContentIR) -> tuple[int, int]:
    """Сколько слотов макета мы закроем, а сколько останется пустыми.

    Считается ровно по тем же правилам, по которым потом идёт подстановка:
    иначе выбор пообещает одно, а сборка сделает другое. Пустой слот — это
    дыра в готовом слайде, и она весит больше, чем удачно совпавший архетип.
    """
    items, metrics, prose = _demand(slide, ir)
    value_group = _main_group(pattern, "metric_value")
    item_group = _main_group(pattern, "item")

    # То же правило, что у подстановки: раскладке без слотов под цифры метрики
    # отдаются карточками. Оценка обязана это видеть, иначе донат с подписями
    # по бокам выглядит для неё пустым и всегда проигрывает сетке KPI.
    if metrics and not value_group:
        items = [f"{value} — {label}" for value, label in metrics] + items
        metrics = []

    kept: dict[str, int] = {}
    if value_group:
        places = pattern.groups.get(value_group, 0)
        kept[value_group] = min(places, len(metrics)) if metrics else places
    if item_group and item_group != value_group:
        places = pattern.groups.get(item_group, 0)
        kept[item_group] = min(places, len(items)) if items else places

    # Раскладка вокруг одной большой цифры без цифры не работает вовсе:
    # огромный слот займёт фраза, и слайд развалится.
    figure = _figure_slot(pattern)
    if figure is not None and not metrics:
        return 0, max(1, len(pattern.slots))

    filled = empty = 0
    used_prose = False
    for slot in pattern.slots:
        if DECORATION_RE.match(slot.sample):
            continue
        if figure is not None and slot.path == figure.path:
            filled += 1
            continue
        if slot.group and slot.group in kept and slot.order >= kept[slot.group]:
            continue                                   # карточку уберём целиком
        if slot.role == "title":
            filled += 1 if slide.key_message else 0
            empty += 0 if slide.key_message else 1
        elif slot.group == value_group and value_group and metrics:
            filled += 1 if slot.role in ("metric_value", "metric_label") else 0
            empty += 0 if slot.role in ("metric_value", "metric_label") else 1
        elif slot.group == item_group and item_group and items:
            filled += 1 if slot.role in ("item", "body", "metric_label") else 0
            empty += 0 if slot.role in ("item", "body", "metric_label") else 1
        elif not slot.group and prose and not used_prose and slot.role in ("body", "item"):
            filled, used_prose = filled + 1, True
        elif (pattern.archetype == "cover" and slide.intent == "cover"
              and slot.role != "title"):
            filled += 1                                # под пояснение на обложке
        else:
            empty += 1
    return filled, empty


# Оценка негодного макета. Не бесконечность: назначение решается венгерским
# алгоритмом, а он на бесконечной стоимости падает.
UNFIT = -1000.0


def _pressure(pattern: Pattern, slide: SlidePlan, ir: ContentIR) -> float:
    """Во сколько раз текст длиннее того, подо что размечен макет.

    Заполненность слотов ничего не говорит о том, влезет ли в них текст:
    макет с четырьмя строками по три слова и макет с четырьмя абзацами для
    неё одинаковы. Разница видна только зрителю — во втором случае текст
    ужимается до нечитаемого кегля и обрывается. Поэтому теснота считается
    отдельно и выбирает из подходящих макетов тот, где текст поместится.
    """
    items, metrics, prose = _demand(slide, ir)
    if metrics and not _main_group(pattern, "metric_value"):
        items = [f"{value} — {label}" for value, label in metrics] + items

    ratios: list[float] = []
    item_group = _main_group(pattern, "item")
    if item_group and items:
        places = pattern.groups.get(item_group, 0)
        for order, text in enumerate(items[:places]):
            card = [slot for slot in pattern.slots
                    if slot.group == item_group and slot.order == order
                    and slot.role in ("item", "body", "metric_label")]
            # Меряем каждый кусок по тому месту, куда он на самом деле ляжет:
            # сумма всех мест карточки обещала бы простор, которого нет.
            ratios.extend(len(value) / max(1, slot.measure)
                          for slot, value in _card_plan(card, text))
    if prose:
        free = [slot.measure for slot in pattern.slots
                if slot.role in ("body", "item") and not slot.group]
        if free:
            ratios.append(len(prose) / max(free))
    return sum(ratios) / len(ratios) if ratios else 1.0


def _occupancy(pattern: Pattern, slide: SlidePlan, ir: ContentIR) -> float:
    """Какая доля мест в повторяющейся группе достанется содержанию."""
    items, metrics, _ = _demand(slide, ir)
    value_group = _main_group(pattern, "metric_value")
    item_group = _main_group(pattern, "item")
    if metrics and not value_group:
        items = [f"{value} — {label}" for value, label in metrics] + items
        metrics = []

    places = filled = 0
    counted: set[str] = set()
    for group, supply in ((value_group, metrics), (item_group, items)):
        total = pattern.groups.get(group, 0) if group else 0
        if not total or group in counted:
            continue
        counted.add(group)
        places += total
        filled += min(total, len(supply))
    return filled / places if places else 1.0


def _unplaced(pattern: Pattern, slide: SlidePlan, ir: ContentIR) -> float:
    """Доля тезисов, которым в макете вовсе не нашлось места.

    Незанятое место — это некрасиво, а потерянный тезис — это уже неверно:
    зритель не увидит того, что было в исходнике. Поэтому пустоту и потерю
    приходится считать порознь.
    """
    items, metrics, _ = _demand(slide, ir)
    value_group = _main_group(pattern, "metric_value")
    item_group = _main_group(pattern, "item")
    if metrics and not value_group:
        items = [f"{value} — {label}" for value, label in metrics] + items
        metrics = []

    supply = len(items) + len(metrics)
    if not supply:
        return 0.0

    room = pattern.groups.get(value_group, 0) if value_group else 0
    if item_group and item_group != value_group:
        room += pattern.groups.get(item_group, 0)
    if not room:
        # Без карточек тезисы уходят в свободный слот связным текстом —
        # это одно место, но содержание там сохраняется.
        room = 1 if any(slot.role in ("body", "item") and not slot.group
                        for slot in pattern.slots) else 0
    return max(0.0, (supply - room) / supply)


def _score(pattern: Pattern, slide: SlidePlan, ir: ContentIR, used: int,
           index: int = 0, total: int = 0) -> float:
    # Обложка и финал — не про содержание, а про место в колоде. Обложка в
    # середине или «Спасибо за внимание» на седьмом слайде из пятнадцати — это
    # не «хуже подходит», это неверно, сколько бы слотов оно ни закрыло.
    if total:
        if pattern.archetype == "cover" and index != 0:
            return UNFIT
        if pattern.archetype == "contacts" and index != total - 1:
            return UNFIT

    filled, empty = _estimate(pattern, slide, ir)
    total = filled + empty
    coverage = filled / total if total else 0.0
    # Запас в шаблонах разный, и небольшое превышение образца — норма: кегль
    # для того и уменьшается. Штрафуем только настоящую тесноту.
    cramped = max(0.0, min(2.0, _pressure(pattern, slide, ir) - 1.4))
    # Снятая карточка не считается пустым слотом — иначе выбор бы её боялся.
    # Но сетка на три места с одной карточкой выглядит недоделанной, поэтому
    # доля занятых мест учитывается отдельно — и мягко: пара свободных мест в
    # ряду из шести не портит слайд так, как одинокая карточка из трёх.
    idle = max(0.0, 0.7 - _occupancy(pattern, slide, ir))

    # Доли в процентах просятся на диаграмму: раскладка с донатом покажет их
    # лучше, чем сетка карточек, — сектора пересоберутся под эти цифры.
    chart_bonus = 0.0
    if pattern.has_chart:
        from .charts import numeric

        _, metrics, _ = _demand(slide, ir)
        percents = [value for value, _ in metrics
                    if "%" in value and numeric(value)]
        has_series = any((block := ir.block(block_id)) is not None
                         and block.type == "series" and block.x and block.y
                         for block_id in slide.blocks)
        if len(percents) >= 2 or has_series or len(metrics) >= 3:
            chart_bonus = 1.1

    # Раскладка вокруг одной большой цифры без цифры не работает совсем: в слот
    # с кеглем под двести пунктов уезжает заголовок и обрывается на полуслове.
    # Это не «хуже других», а негодно, поэтому не штраф, а отказ.
    if _figure_slot(pattern) is not None and not _demand(slide, ir)[1]:
        return UNFIT

    return (2.0 * _affinity(slide.intent, pattern.archetype)
            + chart_bonus
            + 2.2 * coverage
            - 0.9 * min(1.0, empty / 6.0)
            - 1.6 * cramped
            - 1.2 * idle
            - 1.4 * _unplaced(pattern, slide, ir)
            # Повтор макета подряд читается как «дальше то же самое»: колода из
            # трёх одинаковых слайдов выглядит небрежно даже при полной заливке.
            - 0.95 * used)


def choose(template: HtmlTemplate, plan: DeckPlan, ir: ContentIR) -> list[Pattern]:
    """Подбирает макет каждому слайду — сразу по всей колоде.

    Жадный выбор разбирает удачные макеты первыми слайдами, и последним
    достаётся то, во что контент не влезает: в прошлой версии финальный слайд
    получал таблицу с двенадцатью пустыми ячейками. Назначение делается
    венгерским алгоритмом по матрице «слайд × макет», где каждый макет входит
    несколькими копиями с растущим штрафом за повтор — так он остаётся
    доступным для всех подходящих слайдов, но колода не вырождается в один
    макет на тринадцать слайдов.
    """
    import math

    from scipy.optimize import linear_sum_assignment

    patterns = template.patterns
    if not patterns or not plan.slides:
        return []

    copies = max(2, math.ceil(len(plan.slides) / 3) + 1)
    columns = [(pattern, repeat) for repeat in range(copies) for pattern in patterns]
    total = len(plan.slides)
    cost = [[-_score(pattern, slide, ir, repeat, index, total)
             for pattern, repeat in columns]
            for index, slide in enumerate(plan.slides)]

    rows, assigned = linear_sum_assignment(cost)
    chosen: dict[int, Pattern] = {}
    for row, column in zip(rows, assigned):
        chosen[int(row)] = columns[column][0]
    order = [chosen[index] for index in range(len(plan.slides)) if index in chosen]
    return _break_runs(order, plan, ir, patterns)


# Насколько худший макет согласны взять, лишь бы не повторять предыдущий.
RUN_TOLERANCE = 1.1


def _break_runs(chosen: list[Pattern], plan: DeckPlan, ir: ContentIR,
                patterns: list[Pattern]) -> list[Pattern]:
    """Разводит одинаковые макеты, стоящие подряд.

    Матрица назначений считает каждый слайд по отдельности и о соседстве не
    знает, а два одинаковых слайда подряд читаются как «дальше то же самое».
    Меняем второй на лучший из остальных — но только если он не сильно хуже:
    подходящий макет важнее разнообразия.
    """
    for index in range(1, len(chosen)):
        if chosen[index].id != chosen[index - 1].id:
            continue
        slide = plan.slides[index]
        total = len(chosen)
        current = _score(chosen[index], slide, ir, 0, index, total)
        alternatives = [pattern for pattern in patterns
                        if pattern.id != chosen[index - 1].id]
        if not alternatives:
            continue
        best = max(alternatives,
                   key=lambda pattern: _score(pattern, slide, ir, 0, index, total))
        if current - _score(best, slide, ir, 0, index, total) <= RUN_TOLERANCE:
            chosen[index] = best
    return chosen


# --- подстановка текста ------------------------------------------------------

def _set_text(node: etree._Element, text: str) -> None:
    """Меняет текст узла, не трогая вложенную разметку без текста.

    Внутри бывают иконки и значки — их дети остаются на месте, подменяется
    только собственный текст узла.
    """
    node.text = text
    for child in node:
        child.tail = ""


# Правила шаблонов: мельче 24px текст не опускается ни при каких условиях.
MIN_FONT_PX = 24.0
# Ниже этой доли от исходного кегля макет перестаёт быть собой: заголовок
# перестаёт читаться заголовком, а карточка — карточкой.
SHRINK_FLOOR = 0.62
# У заголовка запас больше. Он на слайде один, места под него отведено с избытком,
# и вдвое мельче он всё равно остаётся заголовком — а вот оборванный на полуслове
# читается как сбой вёрстки.
TITLE_FLOOR = 0.42
# Небольшой перебор длины бокс держит и без правок — переносом строки.
SLACK = 1.15


@dataclass
class Fitted:
    """Результат подгонки: что показать, каким кеглем и сколько знаков влезло."""

    text: str
    font_px: float | None
    allowed: int
    cut: bool                                    # оборвано многоточием
    over: bool = False                           # не влезло по оценке


def _fit(text: str, slot: Slot, cut: bool = True) -> Fitted:
    """Подгоняет текст под слот. Возвращает текст и новый кегль, если он нужен.

    Резать по словам — крайняя мера: обрыв фразы виден зрителю. Сначала
    уменьшаем кегль, ровно как поступил бы дизайнер, и лишь когда упёрлись в
    нижнюю границу читаемости, обрезаем остаток.

    Площадь, которую занимает текст, растёт как квадрат кегля, поэтому чтобы
    вместить вдвое больше знаков, кегль достаточно уменьшить в √2 раз.

    Всё это — оценка по длине образца, и она заведомо груба: настоящие переносы
    знает только вёрстка. Поэтому `cut=False` оставляет фразу целой и лишь
    отмечает её длинной: обрезать будет измерение, которому видно, сколько
    места осталось на самом деле.
    """
    sample = max(1, slot.measure)
    ratio = len(text) / sample
    if ratio <= SLACK:
        return Fitted(text, None, sample, False)

    floor = TITLE_FLOOR if slot.role == "title" else SHRINK_FLOOR
    font = max(MIN_FONT_PX, slot.font_px * max(floor, ratio ** -0.5))
    allowed = max(12, int(sample * (slot.font_px / font) ** 2 * SLACK))
    if len(text) <= allowed:
        return Fitted(text, round(font, 1), allowed, False)

    if not cut:
        # Фраза остаётся целой, но помечена длинной: её увидит и модель, и
        # подгонка по вёрстке.
        return Fitted(text, round(font, 1), allowed, False, True)

    shortened = _cut(text, allowed)
    return Fitted(shortened, round(font, 1), allowed, shortened.endswith("…"), True)


def _cut(text: str, allowed: int) -> str:
    """Режет текст, стараясь закончить мысль.

    Целое предложение без многоточия читается как законченная подпись, а
    оборванное на полуслове — как ошибка вёрстки. Поэтому сначала ищем точку в
    пределах допустимого, и только если её нет — режем по слову.
    """
    sentences = re.split(r"(?<=[.!?])\s+", text.strip())
    kept: list[str] = []
    for sentence in sentences:
        candidate = " ".join([*kept, sentence])
        if kept and len(candidate) > allowed:
            break
        kept.append(sentence)
    joined = " ".join(kept)
    if kept and len(joined) <= allowed:
        return joined

    cut = text[:allowed].rsplit(" ", 1)[0].rstrip(" ,;:—–-")
    return f"{cut}…"


def _set_font(node: etree._Element, font_px: float) -> None:
    style = node.get("style") or ""
    if re.search(r"font-size\s*:", style):
        style = re.sub(r"font-size\s*:\s*[^;]+", f"font-size:{font_px:g}px", style)
    else:
        style = f"font-size:{font_px:g}px; {style}".strip()
    node.set("style", style)


COLUMNS_RE = re.compile(r"grid-template-columns\s*:\s*([^;]+)")
REPEAT_RE = re.compile(r"^repeat\(\s*(\d+)\s*,(.+)\)$", re.S)
# Разбор списка дорожек: пробелы внутри minmax(0, 1fr) не разделяют колонки.
TRACK_RE = re.compile(r"[^\s(]+(?:\([^)]*\))?")


def _drop_cards(section: etree._Element, pattern: Pattern, group: str, keep: int) -> int:
    """Убирает лишние карточки группы, начиная с последней."""
    dropped = 0
    total = pattern.groups.get(group, 0)
    parent = None
    for order in range(total - 1, keep - 1, -1):
        path = pattern.group_roots.get(f"{group}#{order}")
        node = _node_at(section, path) if path else None
        if node is not None and node.getparent() is not None:
            parent = node.getparent()
            parent.remove(node)
            dropped += 1
    if dropped and parent is not None:
        _shrink_columns(parent, keep)
    return dropped


def _shrink_columns(container: etree._Element, keep: int) -> None:
    """Подгоняет сетку под оставшиеся карточки.

    Сетка размечена на столько колонок, сколько карточек было в шаблоне. Если
    их стало меньше, лишние колонки остаются пустыми, и единственная карточка
    жмётся в угол вместо того, чтобы занять ряд.

    Колонки в шаблонах пишут двояко — `repeat(3, 1fr)` и `1fr 1fr 1fr`. Второе
    встречается не реже, и пока разбиралось только первое, одинокая карточка
    так и оставалась в трети слайда.
    """
    style = container.get("style") or ""
    match = COLUMNS_RE.search(style)
    if not match or keep < 1:
        return

    value = match.group(1).strip()
    repeat = REPEAT_RE.match(value)
    if repeat is not None:
        if int(repeat.group(1)) <= keep:
            return
        replacement = f"repeat({keep},{repeat.group(2).strip()})"
    else:
        tracks = TRACK_RE.findall(value)
        if len(tracks) <= keep:
            return
        replacement = " ".join(tracks[:keep])
    container.set("style", style[:match.start()]
                  + f"grid-template-columns:{replacement}" + style[match.end():])


@dataclass
class Overlong:
    """Текст, который не влез и был обрезан, — кандидат на переписывание."""

    node: etree._Element
    slot: Slot
    text: str
    limit: int
    slide: int

    @property
    def id(self) -> str:
        return f"s{self.slide}-{self.slot.path.replace('/', '_') or 'root'}"


def fill_section(template: HtmlTemplate, pattern: Pattern, slide: SlidePlan,
                 ir: ContentIR, number: int, subtitle: str = "",
                 overlong: list[Overlong] | None = None,
                 cut: bool = True) -> tuple[etree._Element, SlideResult]:
    overlong = [] if overlong is None else overlong
    section = copy.deepcopy(template.sections[pattern.index])
    result = SlideResult(n=number, label=pattern.label, archetype=pattern.archetype)
    items, metrics, prose = _demand(slide, ir)
    done: set[str] = set()

    placed_texts: dict[str, str] = {}

    def put(slot: Slot, text: str) -> bool:
        node = _node_at(section, slot.path)
        if node is None or not text:
            return False
        fitted = _fit(text, slot, cut=cut)
        _set_text(node, fitted.text)
        if fitted.font_px is not None and fitted.font_px < slot.font_px:
            _set_font(node, fitted.font_px)
            result.notes.append(
                f"«{slot.role}»: кегль {slot.font_px:g} → {fitted.font_px:g}px")
        # Многоточие могло прийти и сверху: планировщик режет длинный абзац,
        # когда выводит из него заголовок. Зрителю всё равно, кто оборвал
        # фразу, поэтому такие места тоже отдаём модели.
        if fitted.over or fitted.text.rstrip().endswith("…"):
            if fitted.cut:
                result.notes.append(f"«{slot.role}»: текст обрезан")
            overlong.append(Overlong(node=node, slot=slot, text=text,
                                     limit=fitted.allowed, slide=number))
        done.add(slot.path)
        # Для подбора иконок важен смысл, а не подпись: берём содержательные
        # слоты карточек, а не заголовок слайда и не служебные надписи.
        if slot.role in ("item", "body", "metric_label"):
            placed_texts[slot.path] = text
        result.filled += 1
        return True

    # Раскладка «большая цифра»: в слот с числовым образцом идёт только число.
    figure = _figure_slot(pattern)
    if figure is not None and metrics:
        value, label = metrics[0]
        put(figure, value)
        caption = next((slot for slot in pattern.slots
                        if slot.path not in done and not slot.group
                        and slot.role in ("body", "item", "metric_label", "title")), None)
        if caption is not None:
            put(caption, label)
        metrics = metrics[1:]

    # Заголовок.
    for slot in pattern.by_role("title"):
        if slide.key_message and slot.path not in done:
            put(slot, slide.key_message)
        break

    # Обложка: под названием идёт пояснение — самый крупный слот после заголовка.
    if pattern.archetype == "cover" and subtitle:
        rest = sorted((slot for slot in pattern.slots
                       if slot.role != "title" and slot.path not in done),
                      key=lambda slot: -slot.font_px)
        if rest:
            put(rest[0], subtitle)

    # Показатели: пары «цифра — подпись» ложатся в карточки по порядку.
    value_group = _main_group(pattern, "metric_value")
    if value_group and metrics:
        places = pattern.groups.get(value_group, 0)
        for slot in pattern.slots:
            if slot.group != value_group or slot.order >= len(metrics):
                continue
            value, label = metrics[slot.order]
            if slot.role == "metric_value":
                put(slot, value)
            elif slot.role == "metric_label":
                put(slot, label)
        if len(metrics) < places:
            result.dropped_cards += _drop_cards(section, pattern, value_group, len(metrics))

    # Диаграммы: сектора — под доли из метрик, столбики — под ряд данных.
    # Без цифр диаграмма остаётся как в шаблоне — декоративная, но не врущая
    # конкретными значениями.
    chart_bound = False
    if metrics:
        from .charts import bind_sector_chart, chart_values

        values = chart_values(metrics)
        if len(values) >= 2 and bind_sector_chart(section, values):
            result.notes.append(f"диаграмма пересобрана под {len(values[:6])} долей")
            chart_bound = True

    if not chart_bound:
        from .charts import bind_bar_chart, numeric as _numeric

        series = next((block for block_id in slide.blocks
                       if (block := ir.block(block_id)) and block.type == "series"
                       and block.x and block.y), None)
        if series is not None:
            # Ряд, совпадающий по длине с осью, — основной; иначе первый.
            ys = next((row for row in series.y.values()
                       if len(row) == len(series.x)),
                      next(iter(series.y.values())))
            chart_bound = bind_bar_chart(section, series.x, ys)
        elif len(metrics) >= 3:
            labels = [label for _, label in metrics]
            values = [_numeric(value) for value, _ in metrics]
            if all(value is not None for value in values):
                chart_bound = bind_bar_chart(section, labels, values)  # type: ignore[arg-type]
        if chart_bound:
            result.notes.append("столбиковый график пересобран под данные")

    if chart_bound:
        # Подписи, которые проставила привязка, — заполненные слоты: иначе
        # чистка «недозаполненного» сотрёт значения и категории с графика.
        for slot in pattern.slots:
            node = _node_at(section, slot.path)
            if node is not None and node.get("data-chart-bound") is not None:
                done.add(slot.path)
                result.filled += 1

    # Раскладка без слотов под цифры получает метрики карточками: значение
    # становится шапкой, подпись — пояснением. Так подписи секторов доната
    # оказываются рядом с диаграммой, а не пропадают.
    if metrics and not value_group:
        items = [f"{value} — {label}" for value, label in metrics] + items

    # Тезисы: заголовок карточки — первая строка, подпись — остаток.
    item_group = _main_group(pattern, "item")
    if item_group and items:
        places = pattern.groups.get(item_group, 0)
        for order in range(min(places, len(items))):
            card = [slot for slot in pattern.slots
                    if slot.group == item_group and slot.order == order
                    and slot.role in ("item", "body", "metric_label")]
            _fill_card(put, card, items[order])
        if len(items) < places:
            result.dropped_cards += _drop_cards(section, pattern, item_group, len(items))

    # Связный текст — в свободные body-слоты вне карточек.
    free_body = [slot for slot in pattern.slots
                 if slot.role in ("body", "item") and not slot.group
                 and slot.path not in done]
    if prose and free_body:
        put(free_body[0], prose)

    # Иконки шаблона подобраны под его собственный текст: после подстановки
    # нашего они теряют смысл. Меняем на подходящие — по порядку чтения.
    from .icons import apply_icons

    placed = [text for _, text in sorted(placed_texts.items(),
                                         key=lambda item: _path_key(item[0]))]
    if placed:
        matched, neutral = apply_icons(section, placed)
        if matched:
            result.notes.append(f"иконок подобрано по смыслу: {matched}")
        if neutral:
            result.notes.append(f"иконок заменено нейтральными: {neutral}")

    _clear_leftovers(section, pattern, done, result)
    _balance_column(section, result)
    if not result.filled:
        result.notes.append("текст не подставлен — макет взят как есть")
    return section, result


def _balance_column(section: etree._Element, result: SlideResult) -> None:
    """Разводит содержимое по высоте слайда, если его меньше, чем у шаблона.

    Слайд свёрстан колонкой и прижат к верху: у дизайнера карточка держала
    иконку, заголовок и два абзаца, и место расходилось. Наш текст короче —
    карточки садятся, и нижняя треть слайда пустует.

    Ставим `safe center`: содержимое повыше нормы просто центрируется, а то,
    что в слайд не влезло, остаётся прижатым к верху и не срезается сверху.
    Тому, что и так занимает всю высоту, это ничего не меняет.
    """
    style = section.get("style") or ""
    compact = style.replace(" ", "")
    if "display:flex" not in compact or "flex-direction:column" not in compact:
        return
    if "justify-content" in compact:
        return                                   # дизайнер уже решил, где что
    section.set("style", f"{style.rstrip().rstrip(';')}; justify-content:safe center;")
    result.notes.append("содержимое разведено по высоте")


# Чисто оформительские надписи: «// 01», «→», «—». Букв в них нет, смысла тоже,
# и они часть рисунка — их шаблон вправе оставить себе.
DECORATION_RE = re.compile(r"^[^\w]*[\d\W]{0,6}$", re.UNICODE)


def _clear_leftovers(section: etree._Element, pattern: Pattern, done: set[str],
                     result: SlideResult) -> None:
    """Стирает текст шаблона из слотов, которые мы не заполнили.

    Иначе в готовой презентации остаются чужие фразы — про пористые материалы
    и грантовый проект. Пустой слот честнее: он виден и его нечем спутать с
    нашим содержанием.
    """
    cleared: list[str] = []
    for slot in pattern.slots:
        if slot.path in done or DECORATION_RE.match(slot.sample):
            continue
        node = _node_at(section, slot.path)
        if node is not None:
            _set_text(node, "")
            cleared.append(slot.path)
            result.notes.append(f"слот «{slot.role}» оставлен пустым")
    _drop_empty(section, cleared, result)


def _drop_empty(section: etree._Element, cleared: list[str],
                result: SlideResult) -> None:
    """Убирает опустевшие рамки и повисшие после них стрелки.

    Пустой слот честнее чужого текста, но рамка вокруг пустоты — уже брак: на
    слайде остаётся обведённый прямоугольник ни с чем. Убираем сам узел, если
    в нём не осталось ни текста, ни рисунка.
    """
    # С конца: пути слотов заданы номерами детей, и удаление раннего узла
    # сдвинуло бы все следующие.
    for path in sorted(cleared, key=_path_key, reverse=True):
        node = _node_at(section, path)
        if node is None or len(node) or (node.text or "").strip():
            continue                              # внутри иконка или текст
        parent = node.getparent()
        if parent is None:
            continue
        children = _children(parent)
        last = children and children[-1] is node
        parent.remove(node)
        result.notes.append("пустая рамка убрана")
        if last:
            _trim_trailing(parent, result)


def _trim_trailing(parent: etree._Element, result: SlideResult) -> None:
    """Снимает украшения, оставшиеся в хвосте ни к чему.

    Стрелка «↓» между блоками имеет смысл, пока после неё что-то есть. Когда
    последний блок убран, она показывает в пустоту.
    """
    while (children := _children(parent)):
        tail = children[-1]
        text = (tail.text or "").strip()
        if len(tail) or not text or not DECORATION_RE.match(text):
            return
        parent.remove(tail)
        result.notes.append("повисшее украшение убрано")


# Насколько фраза может превысить образец шапки и всё ещё считаться шапкой.
CARD_SLACK = 1.4


def _card_plan(card: list[Slot], text: str) -> list[tuple[Slot, str]]:
    """Кто из мест карточки что получит.

    Места в карточке неравноценны, и различает их не кегль, а образец: слот с
    номером «01» — счётчик, слот с длинной фразой — пояснение. Поэтому текст
    раздаётся по вместимости образца, а нумерация и стрелки шаблона остаются
    его собственными: подставить туда кусок фразы значит сломать и смысл, и
    вид карточки.

    Тем же расчётом пользуется оценка макета: если считать её отдельно, она
    рано или поздно разойдётся с подстановкой и начнёт обещать место, которого
    на слайде нет.
    """
    content = [slot for slot in card if not DECORATION_RE.match(slot.sample)]
    if not content:
        return []
    lead = max(content, key=lambda slot: slot.font_px)      # ведущее место
    roomy = max(content, key=lambda slot: slot.measure)     # самое вместительное

    head, tail = _split(text)
    if tail and lead is not roomy and len(head) <= lead.measure * CARD_SLACK:
        # Делим, только если шапка и правда шапка. Иначе от неё останется
        # огрызок с многоточием, а пояснение потеряет начало мысли.
        return [(lead, head), (roomy, tail)]
    if len(text) <= lead.measure * CARD_SLACK:
        # Короткая фраза — это заголовок карточки, а не подпись под ним:
        # в мелкий слот она встанет по размеру, но прочтётся как сноска.
        return [(lead, text)]
    return [(roomy, text)]


def _fill_card(put, card: list[Slot], text: str) -> None:
    """Раскладывает тезис по местам одной карточки."""
    for slot, value in _card_plan(card, text):
        put(slot, value)


def _split(text: str) -> tuple[str, str]:
    """Делит тезис на короткую «шапку» и пояснение — как в карточках шаблона.

    Делим только там, где мысль сама делится: по концу первого предложения или
    по тире. Резать фразу на полуслове нельзя — обе половины становятся
    бессмыслицей, и в карточке это видно сразу.
    """
    parts = re.split(r"(?<=[.!?])\s+", text.strip(), maxsplit=1)
    if len(parts) == 2 and len(parts[0]) <= 60:
        return parts[0].rstrip("."), parts[1]
    if " — " in text:
        head, tail = text.split(" — ", 1)
        return head, tail
    return text, ""


def _rewrite(overlong: list[Overlong], plan: DeckPlan, client,
             result: BuildResult) -> int:
    """Просит модель переписать обрезанное короче и вставляет то, что прошло."""
    if not overlong:
        return 0
    if client is None:
        result.warnings.append(
            f"обрезано фрагментов: {len(overlong)} — модель не подключена, "
            "переписать короче нечем")
        return 0

    from ..fit.shorten import Request, shorten_many

    # Фрагмент с многоточием от планировщика бывает и короче лимита — тогда
    # просить «уложись в лимит» бессмысленно, он и так уложился. Просим короче
    # исходного: только так фраза станет законченной, а не обрезанной.
    requests = [Request(id=item.id, text=item.text,
                        limit=min(item.limit, len(item.text) - 1),
                        context=plan.title) for item in overlong]
    shortened = shorten_many(requests, client)

    applied = 0
    for item in overlong:
        text = shortened.get(item.id)
        if not text:
            continue
        fitted = _fit(text, item.slot)
        if fitted.over:
            continue                       # короче не стало — оставляем обрезку
        _set_text(item.node, fitted.text)
        if fitted.font_px is not None and fitted.font_px < item.slot.font_px:
            _set_font(item.node, fitted.font_px)
        applied += 1

    stubborn = len(overlong) - applied
    if stubborn:
        result.warnings.append(f"осталось обрезанных фрагментов: {stubborn}")
    return applied


def build_deck(template: HtmlTemplate, plan: DeckPlan, ir: ContentIR,
               out_path: str | Path, animate: bool = True,
               client=None, reflow: bool = True,
               browser: str | None = None) -> BuildResult:
    """Собирает колоду и пишет .dc.html рядом с движком шаблона.

    Когда есть браузер, последнее слово о размерах остаётся за вёрсткой:
    оценка по знакам всегда перестраховывается, а она видит настоящие переносы.
    Поэтому при укладке текст не режется — обрезку доверяем измерению.
    """
    from .animate import ANIM_CSS, ANIM_JS, decorate
    from .export import find_browser

    out_path = Path(out_path)
    patterns = choose(template, plan, ir)
    checker = (browser or find_browser()) if reflow else None

    result = BuildResult(path=out_path)
    subtitle = plan.subtitle or ir.meta.subtitle
    overlong: list[Overlong] = []
    built: list[etree._Element] = []

    for number, (pattern, slide) in enumerate(zip(patterns, plan.slides), start=1):
        section, info = fill_section(template, pattern, slide, ir, number, subtitle,
                                     overlong, cut=checker is None)
        built.append(section)
        result.slides.append(info)

    # Переписывание моделью идёт одним запросом на всю колоду и только после
    # укладки: до неё неизвестно, что именно не влезло и в какой лимит.
    result.rewritten = _rewrite(overlong, plan, client, result)

    sections: list[str] = []
    for section, pattern, info in zip(built, patterns, result.slides):
        if animate:
            info.animated = decorate(section, pattern)
        sections.append(lxml_html.tostring(section, encoding="unicode"))

    _write_deck(out_path, template, sections, animate)

    if checker is not None:
        _reflow(out_path, built, template, checker, animate, result)
    return result


def _write_deck(out_path: Path, template: HtmlTemplate, sections: list[str],
                animate: bool) -> None:
    from .animate import ANIM_CSS, ANIM_JS

    head = template.head + (f"\n{ANIM_CSS}" if animate else "")
    tail = f"\n{ANIM_JS}" if animate else ""
    body = "\n".join(sections)
    out_path.write_text(
        "<!DOCTYPE html>\n<html>\n<head>\n<meta charset=\"utf-8\">\n"
        "<meta name=\"viewport\" content=\"width=device-width, initial-scale=1\">\n"
        "<script src=\"./support.js\"></script>\n</head>\n<body>\n<x-dc>\n"
        f"<helmet>\n{head}\n</helmet>\n"
        f"{template.stage_open}\n{body}\n</x-import>{tail}\n</x-dc>\n</body>\n</html>\n",
        encoding="utf-8")


def _reflow(out_path: Path, built: list[etree._Element], template: HtmlTemplate,
            browser: str, animate: bool, result: BuildResult) -> None:
    """Правит колоду по тому, что показала вёрстка, и переписывает файл."""
    from . import reflow

    try:
        fixes = reflow.measure(out_path, browser)
    except Exception as error:                   # подгонка — уточнение, не основа
        result.warnings.append(f"подгонка по вёрстке не удалась: {error}")
        return
    if not fixes:
        return

    shrunk, trimmed = reflow.apply(built, fixes)
    if not shrunk and not trimmed:
        return
    _write_deck(out_path, template,
                [lxml_html.tostring(section, encoding="unicode") for section in built],
                animate)
    if shrunk:
        result.warnings.append(f"кегль подогнан по вёрстке: {shrunk} надписей")
    if trimmed:
        result.warnings.append(f"не поместилось даже мельчайшим кеглем: {trimmed}")
