"""Подбор паттерна под слайд — детерминированный, с объяснением.

Здесь модель не участвует. Оценка складывается из четырёх измеримых вещей:
насколько архетип паттерна соответствует замыслу слайда, влезает ли контент по
ёмкости слотов, есть ли слоты под картинку/график/таблицу и не повторяется ли
макет подряд.

Назначение делается венгерским алгоритмом по всей колоде, а не жадно по одному
слайду: иначе первые слайды разбирают лучшие макеты, а последним достаётся, что
осталось. Чтобы паттерн можно было использовать несколько раз, каждый из них
входит в матрицу несколькими копиями с растущим штрафом за повтор.
"""

from __future__ import annotations

import math

from scipy.optimize import linear_sum_assignment

from ..content.model import Block, ContentIR
from ..template.model import DesignSystem, Pattern
from ..template.synthetic import MAX_STEPS, MIN_STEPS, STEP_CHARS
from . import variants as variant_set
from .model import DeckPlan, DeckSpec, ScoreBreakdown, SlidePlan, SlideSpec
from .variants import Variant

# Насколько паттерн одного архетипа годится под замысел другого.
# 1.0 — точное совпадение, дальше — по убыванию пригодности.
AFFINITY: dict[tuple[str, str], float] = {
    ("bullets", "two_column"): 0.6, ("bullets", "agenda"): 0.5,
    ("bullets", "image_text"): 0.4, ("bullets", "metrics"): 0.35,
    ("agenda", "bullets"): 0.7, ("agenda", "two_column"): 0.5,
    ("metrics", "two_column"): 0.5, ("metrics", "bullets"): 0.35,
    ("metrics", "gallery"): 0.3,
    ("comparison", "two_column"): 0.9, ("comparison", "table"): 0.5,
    ("two_column", "comparison"): 0.9, ("two_column", "bullets"): 0.5,
    ("process", "metrics"): 0.55, ("process", "bullets"): 0.5,
    ("process", "two_column"): 0.4,
    ("chart", "image_text"): 0.45, ("chart", "bullets"): 0.25,
    ("table", "bullets"): 0.3, ("table", "two_column"): 0.3,
    ("quote", "section"): 0.5, ("quote", "bullets"): 0.3,
    ("contacts", "section"): 0.6, ("contacts", "bullets"): 0.4,
    ("cover", "section"): 0.6, ("section", "cover"): 0.5,
    ("image_text", "gallery"): 0.6, ("image_text", "image_full"): 0.5,
    ("gallery", "image_text"): 0.6, ("team", "gallery"): 0.7,
}
FALLBACK_AFFINITY = 0.15
BLANK_AFFINITY = 0.05

TEXT_ROLES = {"body", "item", "quote", "caption", "metric_label", "subtitle"}
ITEM_ROLES = {"item", "body", "metric_value", "metric_label"}


def affinity(intent: str, archetype: str) -> float:
    if intent == archetype:
        return 1.0
    if archetype == "blank":
        return BLANK_AFFINITY
    return AFFINITY.get((intent, archetype), FALLBACK_AFFINITY)


def _slide_blocks(slide: SlidePlan, ir: ContentIR) -> list[Block]:
    return [block for block_id in slide.blocks if (block := ir.block(block_id))]


def _content_demand(slide: SlidePlan, blocks: list[Block]) -> tuple[int, int, int]:
    """Сколько нужно: знаков в заголовке, знаков в теле, отдельных элементов.

    Таблицы и ряды данных в объём текста не входят: они занимают свой слот
    целиком, и их «длина в знаках» ничего не говорит о том, влезут ли они.
    """
    title_chars = len(slide.key_message)
    # Тезис, совпадающий с заголовком, укладчик снимет как эхо — и матчер не
    # должен считать его за место: иначе под один тезис выбирается раскладка
    # на четыре карточки, три из которых останутся пустыми.
    theses = [item for item in slide.items
              if item.strip().rstrip(".").lower() != slide.key_message.strip().rstrip(".").lower()]
    body_chars = sum(len(item) for item in theses)
    items = len(theses)

    # То же правило, что у укладчика: тезисы плана заменяют абзацы и списки,
    # из которых они выжаты. Считать и то и другое — значит просить у макета
    # вдвое больше места, чем на слайд реально ляжет.
    prose_replaced = bool(theses)
    for block in blocks:
        if block.type in ("list", "steps"):
            if not prose_replaced:
                items += len(block.items)
                body_chars += sum(len(item) for item in block.items)
        elif block.type == "metric":
            items += 1
            body_chars += len(block.value) + len(block.label)
        elif block.type == "contact":
            items += 1
            body_chars += len(block.text)
        elif block.type in ("paragraph", "quote"):
            if not prose_replaced:
                items += 1
                body_chars += len(block.text)
    return title_chars, body_chars, items


def _pattern_supply(pattern: Pattern) -> tuple[int, int, int, int]:
    """Сколько вмещает: знаков в заголовке, знаков в теле, мест, строк.

    Места и строки — разные величины, и путать их нельзя. Один большой блок —
    это **одно** место в композиции, но держит он столько пунктов, сколько в
    него влезает строк. По местам оценивается соответствие раскладки контенту
    (одна мысль в раскладке на десять блоков оставит девять дыр), по строкам —
    риск переполнения.
    """
    from ..fit.layout import PROSE_MIN_W

    title_chars = max((slot.capacity.chars for slot in pattern.slots_by_role("title")),
                      default=0)
    # Узкие полоски укладчик под текст не берёт — и матчер их не считает,
    # иначе стикер шириной в три слова сойдёт за место под абзац.
    usable = [slot for slot in pattern.slots if slot.bbox[2] >= PROSE_MIN_W]
    body_chars = sum(slot.capacity.chars for slot in usable
                     if slot.role in TEXT_ROLES)

    places = sum(1 for slot in usable if slot.role in ITEM_ROLES or
                 slot.role == "quote")
    if pattern.repeat:
        places = pattern.repeat.max

    lines = 0
    for slot in usable:
        if slot.role in ("item", "metric_value", "metric_label"):
            lines += max(1, slot.capacity.lines)
        elif slot.role in ("body", "quote"):
            lines += max(1, slot.capacity.lines)
    return title_chars, body_chars, max(places, 1), max(lines, 1)


def _chars_fit(ratio: float, window: tuple[float, float] = (0.45, 0.95)) -> float:
    """Насколько плотно текст заполняет слоты.

    Хорошо — когда занято от 45 до 95 % ёмкости. Ниже начинается пустой слайд:
    одна фраза в раскладке на десять блоков выглядит незаконченной, и именно это
    сильнее всего портит впечатление от результата. Окно задаёт вариант
    вёрстки: сжатому нормально и под завязку, просторному — и вполовину.
    """
    low, high = window
    if ratio > high:
        return max(0.0, high / ratio)
    if ratio >= low:
        return 1.0
    return max(0.05, ratio / low)


def _units_fit(needed: int, available: int) -> float:
    """Совпадение числа смысловых единиц с числом мест под них.

    Три тезиса в раскладке на три карточки — ровно то, что задумал дизайнер;
    те же три в раскладке на десять оставят семь дыр.
    """
    if needed <= 0 or available <= 0:
        return 0.5
    return max(0.05, min(needed, available) / max(needed, available))


# Оценка макета, который на этом месте неуместен в принципе.
UNFIT = -1000.0
# Уступка схемы из фигур родному макету шаблона при прочих равных.
SYNTHETIC_HANDICAP = 0.25
# Сколько раз за колоду можно взять схему из фигур.
SYNTHETIC_COPIES = 2


def score(pattern: Pattern, slide: SlidePlan, ir: ContentIR,
          repeat_index: int = 0, design: DesignSystem | None = None,
          position: str = "middle", variant: Variant | None = None) -> ScoreBreakdown:
    variant = variant or variant_set.get(None)
    blocks = _slide_blocks(slide, ir)
    # Обложка и финальный слайд — про место в колоде, а не про содержание:
    # титульный макет в середине неверен, сколько бы слотов он ни закрыл.
    # Обложка в конце допустима — так часто оформляют «Спасибо».
    if pattern.archetype == "cover" and position == "middle":
        return ScoreBreakdown(archetype=UNFIT)
    if pattern.archetype == "contacts" and position != "last":
        return ScoreBreakdown(archetype=UNFIT)
    title_need, body_need, items_need = _content_demand(slide, blocks)
    title_cap, body_cap, places, line_capacity = _pattern_supply(pattern)

    breakdown = ScoreBreakdown(archetype=affinity(slide.intent, pattern.archetype))

    if pattern.accepts.get("synthetic") == "process":
        # Схема из фигур: шагов должно быть от трёх до шести, картинок и данных
        # на ней не бывает. Мест у неё ровно столько, сколько шагов, — она
        # эластична, — а родному макету шаблона она уступает малую долю.
        low, high = pattern.accepts.get("steps", (MIN_STEPS, MAX_STEPS))
        if slide.intent != "process" or not (low <= items_need <= high) or any(
                block.type in ("table", "series", "image", "metric") for block in blocks):
            return ScoreBreakdown(archetype=UNFIT)   # содержание со стрелками — не процесс
        places = line_capacity = items_need
        # Карточки схемы подстраивают кегль под текст, поэтому заполненность
        # всегда «в норме»; риск переполнения считается от знаков на шаг.
        diagram_cap = items_need * STEP_CHARS
        body_cap = max(1, int(body_need / (sum(variant.fill_window) / 2))) if body_need else 1
        breakdown.handicap = SYNTHETIC_HANDICAP

    # --- ёмкость: и переполнение, и полупустой слайд одинаково плохи ---------
    if title_need and not title_cap and not body_cap:
        # Раскладке без единого текстового слота нечего предложить слайду с
        # заголовком: обложка из трёх фоторамок выйдет пустой.
        breakdown.capacity = 0.05
    elif body_need == 0:
        # Обложке и разделителю нечего класть в тело — судим только по заголовку,
        # иначе титульный макет проигрывает как «полупустой». И судим плавно:
        # название на три знака длиннее строки ужмётся или перенесётся, а
        # ступенька «0,5» отдавала обложку разделителю из-за этих трёх знаков.
        if not title_cap or title_need <= title_cap:
            breakdown.capacity = 1.0
        else:
            breakdown.capacity = round(max(0.5, title_cap / title_need), 4)
    elif body_cap <= 0:
        breakdown.capacity = 0.0
    else:
        # Не среднее, а произведение: среднее прощало таймлайну на девять
        # подписей единственный тезис — знаков-то в него влезает. Пустые
        # восемь мест среднее не видит, произведение видит.
        breakdown.capacity = round(
            _chars_fit(body_need / body_cap, variant.fill_window)
            * _units_fit(items_need, places) ** 0.5, 4)

    overflow = max(0.0, body_need / body_cap - 1.0) if body_cap else (1.0 if body_need else 0.0)
    if pattern.accepts.get("synthetic") == "process":
        overflow = max(0.0, body_need / diagram_cap - 1.0)
    if items_need > line_capacity:
        overflow += 0.5 * (items_need / line_capacity - 1.0)
    if title_need and title_cap and title_need > title_cap:
        # Заголовок длиннее строки ужмётся или перенесётся — это риск, а не
        # приговор: раскладка с однострочной шапкой не должна проигрывать
        # из-за него раскладке с девятью пустыми местами.
        overflow += 0.2 * min(1.0, title_need / title_cap - 1.0)
    breakdown.overflow_risk = min(1.5, overflow)

    # --- медиа: график, таблица и картинка требуют своего слота -------------
    breakdown.assets = _asset_fit(pattern, blocks, breakdown, design)

    # Раскладка вокруг крупной цифры без цифры не работает: огромный слот
    # либо останется пустым, либо получит слово вместо числа.
    figures = sum(slot.bbox[2] * slot.bbox[3] for slot in pattern.slots
                  if slot.role == "metric_value")
    if figures and not any(block.type == "metric" for block in blocks):
        breakdown.overflow_risk = min(1.5, breakdown.overflow_risk
                                      + (0.9 if figures > 0.05 else 0.4))

    # Раскладка с повёрнутым текстом — приём оформления, а не место для абзаца:
    # шаблон держит её для вертикальной надписи сбоку. Берём такую только тогда,
    # когда других не осталось.
    if pattern.accepts.get("vertical_text") and body_need:
        breakdown.overflow_risk = min(1.5, breakdown.overflow_risk + 0.8)
    breakdown.repeat_penalty = 0.35 * repeat_index
    if pattern.accepts.get("synthetic"):
        breakdown.repeat_penalty = 0.9 * repeat_index   # вторая схема — только по нужде

    # Ось вариантов: сжатая вёрстка тянется к сеткам со многими местами,
    # просторная — к одному крупному полю. Для обложки и разделителя мест нет,
    # и предпочтение их не касается.
    if variant.places_bias and body_need:
        crowd = min(places, 6) / 6.0
        breakdown.density = round(variant.places_bias * (crowd - 0.5), 4)
    return breakdown


def _has_wide_field(pattern: Pattern, design: DesignSystem | None = None,
                    content_type: str = "table", columns: int = 1) -> bool:
    """Есть ли поле, в которое поместится таблица или график целиком.

    Решение о запасном месте принимает укладчик (`fit.layout`), и матчер
    смотрит той же функцией и с той же меркой — ширина под каждую колонку
    таблицы: иначе он выберет раскладку, в которой таблице не найдётся места.
    """
    from ..fit.layout import (CHART_MIN_H, MEDIA_MAX_W, MEDIA_MIN_COLUMN_W, MEDIA_MIN_H,
                              MEDIA_MIN_W, content_area)

    need_h = CHART_MIN_H if content_type == "series" else MEDIA_MIN_H
    need_w = (min(MEDIA_MAX_W, max(MEDIA_MIN_W, MEDIA_MIN_COLUMN_W * columns))
              if content_type == "table" else MEDIA_MIN_W)
    if any(slot.role in ("body", "item")
           and slot.bbox[2] >= max(0.5, need_w) and slot.bbox[3] >= need_h
           for slot in pattern.slots):
        return True
    return design is not None and content_area(pattern, design, need_w, need_h) is not None


def _asset_fit(pattern: Pattern, blocks: list[Block], breakdown: ScoreBreakdown,
               design: DesignSystem | None = None) -> float:
    roles = [slot.role for slot in pattern.slots]
    needs = {block.type for block in blocks}
    score_value = 0.5

    columns = max((max(len(block.header), max((len(row) for row in block.rows), default=1))
                   for block in blocks if block.type == "table"), default=1)
    for content_type, role in (("series", "chart"), ("table", "table"), ("image", "image")):
        if content_type in needs:
            if role in roles:
                score_value = 1.0
            elif _has_wide_field(pattern, design, content_type, columns):
                # Своего слота нет, но есть широкое текстовое поле: укладчик
                # рисует таблицу и график по его геометрии. Это хуже готового
                # слота, но работает — и куда лучше узкой колонки.
                score_value = max(score_value, 0.5)
            else:
                # Ряд данных без слота под график придётся показывать текстом —
                # это не запрет, но заметный минус.
                breakdown.overflow_risk = min(1.5, breakdown.overflow_risk + 0.5)
                score_value = min(score_value, 0.1)

    if pattern.accepts.get("needs_image") and "image" not in needs:
        # Раскладка, построенная вокруг снимков, без снимков не работает: место
        # под них остаётся белым, а текст жмётся к подписям. Это не «чуть хуже»,
        # а тот самый полупустой слайд, поэтому считаем это риском, а не скидкой.
        score_value = min(score_value, 0.2)
        breakdown.overflow_risk = min(1.5, breakdown.overflow_risk + 0.3)
    return score_value


def match_deck(plan: DeckPlan, design: DesignSystem, ir: ContentIR,
               variant: Variant | str | None = None) -> DeckSpec:
    chosen = (variant if isinstance(variant, Variant)
              else variant_set.get(variant or plan.variant))
    patterns = [pattern for pattern in design.patterns if pattern.slots]
    if not patterns or not plan.slides:
        return DeckSpec(plan=plan, slides=[], template=design.source.file,
                        warnings=["нет паттернов или пустой план"])

    # Копий должно хватать, чтобы удачная раскладка досталась всем подходящим
    # слайдам, а не первым трём по счёту: у шаблона с двумя приличными
    # текстовыми макетами лимит в три копии оставлял последние слайды с тем,
    # во что контент не влезает вовсе. Но и снимать лимит совсем нельзя —
    # тогда вся колода собирается на одном макете.
    copies = max(3, math.ceil(len(plan.slides) / 3) + 2)
    # Схема из фигур — приём, а не макет: две на колоду, иначе презентация
    # превращается в один сплошной чертёж.
    columns: list[tuple[Pattern, int]] = [
        (pattern, copy) for copy in range(copies) for pattern in patterns
        if copy < (SYNTHETIC_COPIES if pattern.accepts.get("synthetic") else copies)]

    def place(index: int) -> str:
        if index == 0:
            return "first"
        return "last" if index == len(plan.slides) - 1 else "middle"

    breakdowns: list[list[ScoreBreakdown]] = [
        [score(pattern, slide, ir, repeat, design, place(index), chosen)
         for pattern, repeat in columns]
        for index, slide in enumerate(plan.slides)
    ]
    cost = [[-item.total for item in row] for row in breakdowns]
    rows, assigned = linear_sum_assignment(cost)

    slides: list[SlideSpec] = []
    for row, column in zip(rows, assigned):
        slide = plan.slides[row]
        pattern, _ = columns[column]
        ranked = sorted(
            ((patterns[index].id, breakdowns[row][index].total)
             for index in range(len(patterns))),
            key=lambda item: -item[1])[:3]
        slides.append(SlideSpec(n=slide.n, plan=slide, pattern_id=pattern.id,
                                score=breakdowns[row][column],
                                alternatives=[item for item in ranked
                                              if item[0] != pattern.id]))

    warnings = list(plan.warnings)
    weak = [spec for spec in slides if spec.score.overflow_risk > 0.4]
    if weak:
        warnings.append(
            f"риск переполнения на слайдах: {', '.join(str(s.n) for s in weak)} — "
            "укладчик сократит текст или сменит паттерн")

    return DeckSpec(plan=plan, slides=sorted(slides, key=lambda spec: spec.n),
                    template=design.source.file, warnings=warnings)
