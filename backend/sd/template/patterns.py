"""Библиотека паттернов слайдов, снятая с шаблона.

Паттерн — это раскладка одного слайда: какие слоты есть, где они лежат, каким
стилем набраны и сколько туда влезает. Источников два, и оба нужны:

* **макеты** — то, как шаблон задуман; заполняются штатными плейсхолдерами;
* **слайды-примеры** — то, как шаблон реально применяют; там часто вся красота
  нарисована руками, и такие слайды мы потом клонируем целиком.

Архетип («метрики», «сравнение», «раздел») — это семантика контента, а не
внешний вид: он говорит, *что* показываем, а как это выглядит — целиком из
шаблона. Классификатор объясняет каждое решение списком признаков.
"""

from __future__ import annotations

import re
from collections import defaultdict
from statistics import pstdev

from ..fit.textmetrics import capacity_chars, metrics_for
from ..ooxml.ns import NS, attr_int
from ..ooxml.package import Package
from ..ooxml.shapes import Shape
from .model import Archetype, Capacity, Pattern, RepeatGroup, Slot, Typography
from .typography import resolve_style

DEFAULT_INSETS = (91440, 45720, 91440, 45720)

# Штатный тип макета в OOXML — самый надёжный сигнал о назначении слайда.
LAYOUT_TYPE_ARCHETYPE: dict[str, Archetype] = {
    "title": "cover", "secHead": "section", "obj": "bullets", "tx": "bullets",
    "titleOnly": "section", "blank": "blank", "twoObj": "two_column",
    "twoTxTwoObj": "two_column", "twoObjAndTx": "two_column",
    "twoObjOverTx": "two_column", "objAndTwoObj": "two_column",
    "tbl": "table", "chart": "chart", "txAndChart": "chart", "chartAndTx": "chart",
    "objAndTx": "image_text", "txAndObj": "image_text", "picTx": "image_text",
    "clipArtAndTx": "image_text", "txAndClipArt": "image_text",
    "objOverTx": "image_text", "txOverObj": "image_text",
    "vertTx": "bullets", "vertTitleAndTx": "bullets", "dgm": "process",
    "objTx": "image_text", "cust": "blank",
}

# Слова в имени макета. Только общеупотребимые — привязок к конкретному шаблону нет.
NAME_KEYWORDS: dict[Archetype, tuple[str, ...]] = {
    "cover": ("титул", "обложк", "title slide", "cover"),
    "section": ("раздел", "section", "divider", "разделител"),
    "agenda": ("повестк", "содержан", "оглавлен", "agenda", "contents", "outline"),
    "comparison": ("сравнен", "comparison", "compare", "versus"),
    "metrics": ("показател", "метрик", "цифр", "kpi", "metric", "stat", "numbers"),
    "process": ("процесс", "этап", "шаг", "timeline", "process", "roadmap", "step"),
    "table": ("таблиц", "table"),
    "chart": ("диаграм", "график", "chart", "graph"),
    "quote": ("цитат", "отзыв", "quote", "testimonial"),
    "image_full": ("изображен", "картинк", "фото", "picture", "photo", "image"),
    "team": ("команд", "сотрудник", "team", "people", "staff"),
    "contacts": ("контакт", "спасибо", "contact", "thank"),
    "two_column": ("два", "две", "two content", "two column"),
}

NAME_WEIGHT: dict[str, float] = {"cover": 3.5, "section": 3.5, "agenda": 3.5,
                                 "contacts": 3.0, "quote": 3.0, "team": 3.0}

ARCHETYPE_ACCEPTS: dict[Archetype, list[str]] = {
    "cover": ["heading", "paragraph"],
    "section": ["heading"],
    "agenda": ["list", "steps"],
    "bullets": ["list", "paragraph", "steps"],
    "two_column": ["list", "paragraph"],
    "comparison": ["list", "paragraph"],
    "metrics": ["metric"],
    "process": ["steps", "list"],
    "table": ["table"],
    "chart": ["series"],
    "quote": ["quote"],
    "image_full": ["image"],
    "image_text": ["image", "paragraph", "list"],
    "gallery": ["image"],
    "team": ["image", "paragraph"],
    "contacts": ["paragraph", "list"],
    "blank": ["paragraph"],
}

QUOTE_MARKS = re.compile(r"[«»\"“”„]")
NUMERIC = re.compile(r"^[\s\d.,%+\-–×x/₽$€]*$")


# --- слоты -----------------------------------------------------------------

def _insets(shape: Shape) -> tuple[int, int, int, int]:
    body_pr = shape.tx_body.find("a:bodyPr", NS) if shape.tx_body is not None else None
    if body_pr is None:
        return DEFAULT_INSETS
    return (attr_int(body_pr, "lIns", DEFAULT_INSETS[0]) or 0,
            attr_int(body_pr, "tIns", DEFAULT_INSETS[1]) or 0,
            attr_int(body_pr, "rIns", DEFAULT_INSETS[2]) or 0,
            attr_int(body_pr, "bIns", DEFAULT_INSETS[3]) or 0)


def _is_vertical(shape: Shape) -> bool:
    """Текст в макете повёрнут на 90°.

    Такие раскладки шаблоны держат для акцента — вертикальная надпись сбоку.
    Абзац, положенный в неё, читается только с наклонённой головой.
    """
    body_pr = shape.tx_body.find("a:bodyPr", NS) if shape.tx_body is not None else None
    return body_pr is not None and (body_pr.get("vert") or "horz") not in ("horz", "")


def _autofit(shape: Shape) -> str:
    body_pr = shape.tx_body.find("a:bodyPr", NS) if shape.tx_body is not None else None
    if body_pr is None:
        return "none"
    if body_pr.find("a:normAutofit", NS) is not None:
        return "shrink"
    if body_pr.find("a:spAutoFit", NS) is not None:
        return "grow"
    return "none"


def _nearest_style_name(size_pt: float | None, typography: Typography,
                        default: str = "body_l1") -> str:
    """Имя стиля из дизайн-системы, ближайшего по кеглю."""
    if size_pt is None or not typography.styles:
        return default
    named = [(name, style.size_pt) for name, style in typography.styles.items()
             if style.size_pt]
    if not named:
        return default
    return min(named, key=lambda item: abs(item[1] - size_pt))[0]


def _role_and_style(shape: Shape, typography: Typography,
                    size_pt: float | None) -> tuple[str | None, str]:
    """Роль слота и имя стиля. Плейсхолдеры говорят прямо, свободные шейпы — через кегль."""
    match shape.ph_type:
        case "title" | "ctrTitle":
            return "title", "title"
        case "subTitle":
            return "subtitle", "subtitle" if "subtitle" in typography.styles else "body_l1"
        case "pic" | "clipArt" | "media":
            return "image", "body_l1"
        case "chart":
            return "chart", "body_l1"
        case "tbl":
            return "table", "body_l1"
        case "dt" | "ftr" | "sldNum" | "hdr":
            return None, "footer"
        case "body" | "obj" | "dgm" | None:
            pass

    if shape.tag == "pic":
        return "image", "body_l1"
    if shape.graphic_kind == "chart":
        return "chart", "body_l1"
    if shape.graphic_kind in ("table", "diagram"):
        return "table", "body_l1"
    if shape.tx_body is None:
        return None, "body_l1"

    if shape.is_placeholder:
        title_size = _style_size(typography, "title")
        if size_pt and title_size and size_pt >= title_size * 1.25:
            # Плейсхолдер с кеглем крупнее заголовочного — место под цифру
            # фактоида: абзацы в 88 pt не набирают.
            return "metric_value", _nearest_style_name(size_pt, typography)
        return "body", _nearest_style_name(size_pt, typography)

    # Свободная надпись слайда-примера: роль выводим из кегля и самого текста.
    text = shape.text
    title_size = _style_size(typography, "title")
    body_size = _style_size(typography, "body_l1")
    style_name = _nearest_style_name(size_pt, typography)

    if size_pt and title_size and size_pt >= title_size * 1.25 and len(text) <= 14:
        return "metric_value", style_name
    if QUOTE_MARKS.search(text) and len(text) > 40:
        return "quote", style_name
    if size_pt and title_size and size_pt >= title_size * 0.85:
        return "title", style_name
    if size_pt and body_size and size_pt <= body_size * 0.75:
        return "caption", style_name
    return "body", style_name


def _style_size(typography: Typography, name: str) -> float | None:
    style = typography.styles.get(name)
    return style.size_pt if style else None


# Ближе этого к краю слайда содержание не подходит: там поле.
SLIDE_EDGE = 0.03


def _clip(bbox: list[float]) -> list[float]:
    """Обрезает рамку по слайду, оставляя поле у края.

    Рамку, от которой после обрезки осталось меньше двух третей, не трогаем:
    так стоят повёрнутые надписи и декоративные полосы у края — их положение
    задумано, а не унаследовано от экспорта.
    """
    left, top, w, h = bbox
    right, bottom = min(left + w, 1 - SLIDE_EDGE), min(top + h, 1 - SLIDE_EDGE)
    left, top = max(left, SLIDE_EDGE if right > SLIDE_EDGE else left), max(top, 0.0)
    new_w, new_h = right - left, bottom - top
    if new_w < 0.01 or new_h < 0.005 or new_w < w * 0.66 or new_h < h * 0.66:
        return bbox
    return [round(left, 4), round(top, 4), round(new_w, 4), round(new_h, 4)]


def _slot_from_shape(pkg: Package, part: str, shape: Shape, typography: Typography,
                     width: int, height: int) -> Slot | None:
    if shape.cx <= 0 or shape.cy <= 0 or shape.is_chrome:
        return None

    resolved = resolve_style(pkg, part, shape, 0) if shape.tx_body is not None else None
    size_pt = resolved.size_pt if resolved else None
    role, style_name = _role_and_style(shape, typography, size_pt)
    if role is None:
        return None

    # Рамка надписи в шаблонах, вывезенных из Google Slides, бывает шире
    # слайда: короткий образец этого не показывал, а наш текст уедет за край.
    # Слот обрезается по слайду, и композитор выставит по нему саму фигуру.
    bbox = shape.bbox_fraction(width, height)
    if shape.tx_body is None or not _is_vertical(shape):
        # Повёрнутую надпись не трогаем: её рамка стоит у края по замыслу.
        bbox = _clip(bbox)
    box_w = int(bbox[2] * width)
    box_h = int(bbox[3] * height)

    capacity = Capacity()
    if role not in ("image", "chart", "table") and resolved and size_pt:
        metrics = metrics_for(resolved.font or typography.fonts.minor,
                              resolved.bold, resolved.italic)
        chars, lines = capacity_chars(box_w, box_h, metrics, size_pt,
                                      resolved.line_spacing, resolved.caps,
                                      insets=_insets(shape))
        capacity = Capacity(chars=chars, lines=lines)

    return Slot(
        role=role,                                    # type: ignore[arg-type]
        bbox=bbox,
        style=style_name,
        size_pt=size_pt,
        font=resolved.font if resolved else None,
        bold=bool(resolved.bold) if resolved else False,
        ph_type=shape.ph_type,
        ph_idx=shape.ph_idx,
        capacity=capacity,
        required=role in ("title", "image", "chart", "table"),
        shape_id=shape.shape_id,
    )


def _single_title(slots: list[Slot]) -> None:
    """У слайда один заголовок; остальные «заголовки» — крупные цифры или шапки.

    Роль назначается по кеглю, и четыре номера «01…04» на слайде с шагами
    получают роль заголовка — а под пять заголовков ни одна укладка не
    рассчитана. Заголовком остаётся самый широкий, остальные становятся тем,
    что они есть: узкое место на пару знаков — цифра показателя, прочее —
    шапка карточки.
    """
    titles = [slot for slot in slots if slot.role == "title"]
    if len(titles) < 2:
        return
    keep = max(titles, key=lambda slot: (slot.bbox[2], -slot.bbox[1]))
    for slot in titles:
        if slot is keep:
            continue
        slot.role = "metric_value" if slot.capacity.chars <= 6 else "item"  # type: ignore[assignment]


# --- повторяющиеся группы ---------------------------------------------------

def _detect_repeat(slots: list[Slot]) -> RepeatGroup | None:
    """Ищем равные боксы с постоянным шагом — это колонки или карточки.

    Такая группа делает паттерн эластичным: тот же макет принимает и 2, и 4
    элемента, а лишние слоты просто не заполняются.
    """
    candidates = defaultdict(list)
    for slot in slots:
        if slot.role in ("body", "image", "metric_value", "item"):
            key = (slot.role, round(slot.bbox[2], 3), round(slot.bbox[3], 3))
            candidates[key].append(slot)

    best: list[Slot] = []
    for group in candidates.values():
        if len(group) > len(best):
            best = group
    if len(best) < 2:
        return None

    horizontal = sorted(best, key=lambda s: (round(s.bbox[1], 2), s.bbox[0]))
    dx = [b.bbox[0] - a.bbox[0] for a, b in zip(horizontal, horizontal[1:])]
    dy = [b.bbox[1] - a.bbox[1] for a, b in zip(horizontal, horizontal[1:])]

    step: dict[str, float] = {}
    if dx and pstdev(dx) < 0.01 and abs(sum(dx) / len(dx)) > 0.01:
        step = {"dx": round(sum(dx) / len(dx), 4), "dy": 0.0}
    elif dy and pstdev(dy) < 0.01 and abs(sum(dy) / len(dy)) > 0.01:
        step = {"dx": 0.0, "dy": round(sum(dy) / len(dy), 4)}
    if not step:
        return None

    name = "items" if best[0].role in ("body", "item") else f"{best[0].role}s"
    for index, slot in enumerate(horizontal):
        slot.group = name
        slot.index = index
        if slot.role == "body":
            slot.role = "item"                        # type: ignore[assignment]

    return RepeatGroup(group=name, min=1, max=len(best), step=step)


# --- классификация ----------------------------------------------------------

def _classify(name: str, layout_type: str | None, slots: list[Slot],
              repeat: RepeatGroup | None, typography: Typography,
              is_first_layout: bool) -> tuple[Archetype, float, list[str]]:
    scores: defaultdict[str, float] = defaultdict(float)
    evidence: list[str] = []

    if layout_type and layout_type in LAYOUT_TYPE_ARCHETYPE:
        scores[LAYOUT_TYPE_ARCHETYPE[layout_type]] += 3.0
        evidence.append(f"тип макета={layout_type}")

    lowered = name.lower()
    for archetype, keywords in NAME_KEYWORDS.items():
        if any(word in lowered for word in keywords):
            # Позиционные роли дизайнер называет однозначно («Титульный слайд»,
            # «Заголовок раздела»), поэтому им имя весит больше структуры.
            scores[archetype] += NAME_WEIGHT.get(archetype, 2.0)
            evidence.append(f"имя «{name}»")
            break

    roles = [slot.role for slot in slots]
    images = [slot for slot in slots if slot.role == "image"]
    texts = [slot for slot in slots if slot.role in ("body", "item", "title", "subtitle")]
    image_area = sum(slot.bbox[2] * slot.bbox[3] for slot in images)

    if "table" in roles:
        scores["table"] += 4.0
        evidence.append("есть таблица")
    if "chart" in roles:
        scores["chart"] += 4.0
        evidence.append("есть диаграмма")
    if "quote" in roles:
        scores["quote"] += 3.0
        evidence.append("текст в кавычках")

    if images:
        if len(images) == 1 and image_area > 0.55 and len(texts) <= 1:
            scores["image_full"] += 3.0
            evidence.append(f"картинка занимает {image_area:.0%} слайда")
        elif len(images) >= 3:
            target = "team" if any(word in lowered for word in NAME_KEYWORDS["team"]) else "gallery"
            scores[target] += 3.0
            evidence.append(f"{len(images)} картинок сеткой")
        else:
            scores["image_text"] += 2.5
            evidence.append("картинка рядом с текстом")

        # Слайд, у которого треть площади под изображениями, — не список тезисов,
        # даже если тип макета в шаблоне остался служебным «объект».
        if image_area > 0.35:
            scores["bullets"] -= 2.0
            scores["agenda"] -= 2.0
            scores["two_column"] -= 1.0
            evidence.append(f"изображения занимают {image_area:.0%} площади")

    if repeat:
        count = repeat.max
        item_slots = [slot for slot in slots if slot.group == repeat.group]
        # Метрика — это короткая подпись у крупной цифры. Пять вариантов ответа
        # по 60 знаков метриками не являются, поэтому порог жёсткий.
        small = [slot for slot in item_slots if 0 < slot.capacity.chars <= 30]
        metric_like = any(slot.role == "metric_value" for slot in item_slots)

        if metric_like or (2 <= count <= 6 and item_slots and len(small) == len(item_slots)):
            scores["metrics"] += 2.5
            evidence.append(f"{count} коротких блока с постоянным шагом")
        if count == 2:
            scores["two_column"] += 2.0
            scores["comparison"] += 1.0
            evidence.append("два равных блока")
        elif count >= 3:
            # Последовательность (процесс) отличается от набора (метрики) только
            # стрелками или нумерацией, а не числом блоков, — иначе любая
            # трёхколоночная раскладка объявлялась бы «этапами».
            scores["metrics"] += 1.0
            scores["two_column"] += 0.5
            evidence.append(f"{count} равных блоков")

    body_slots = [slot for slot in slots if slot.role in ("body", "item")]
    title_slots = [slot for slot in slots if slot.role == "title"]

    if not body_slots and title_slots:
        if is_first_layout or "subtitle" in roles:
            scores["cover"] += 2.0
            evidence.append("только заголовок и подзаголовок")
        else:
            scores["section"] += 2.0
            evidence.append("только заголовок")
    elif len(body_slots) == 1 and body_slots[0].capacity.chars > 150:
        scores["bullets"] += 2.0
        evidence.append("один ёмкий текстовый блок")
    elif len(body_slots) == 2 and not repeat:
        scores["two_column"] += 1.5
        evidence.append("две колонки текста")

    if not slots:
        scores["blank"] += 1.0

    positive = {name: score for name, score in scores.items() if score > 0}
    if not positive:
        return ("bullets" if body_slots else "blank"), 0.2, evidence or ["признаков не найдено"]

    archetype, score = max(positive.items(), key=lambda item: item[1])
    return archetype, round(min(1.0, score / 5.0), 2), evidence  # type: ignore[return-value]


# --- сборка паттернов -------------------------------------------------------

def _signature(slots: list[Slot]) -> tuple:
    return tuple(sorted((slot.role, round(slot.bbox[0], 2), round(slot.bbox[1], 2),
                         round(slot.bbox[2], 2), round(slot.bbox[3], 2))
                        for slot in slots))


def _on_slide(shape: Shape, width: int, height: int) -> bool:
    """Виден ли шейп на слайде.

    Дизайнеры паркуют заготовки за краем холста: такие шейпы есть в XML, но на
    слайде их нет, и слотами они быть не могут.
    """
    if shape.cx <= 0 or shape.cy <= 0:
        return False
    visible_w = max(0, min(shape.x + shape.cx, width) - max(shape.x, 0))
    visible_h = max(0, min(shape.y + shape.cy, height) - max(shape.y, 0))
    return visible_w * visible_h >= 0.5 * shape.area


def _pattern_shapes(pkg: Package, part: str, kind: str, width: int, height: int) -> list[Shape]:
    """Что на этой части считается контентом, а что — оформлением.

    В макете контент — это только плейсхолдеры: всё остальное нарисовано
    дизайнером и трогать его нельзя. На слайде-примере дизайн часто сделан
    обычными надписями, поэтому там контентом считаем и свободные шейпы —
    кроме мелких картинок, которые почти всегда логотипы.
    """
    shapes = [shape for shape in pkg.shapes(part) if _on_slide(shape, width, height)]
    if kind == "layout":
        return [shape for shape in shapes if shape.is_content_placeholder]

    slide_area = float(width * height) or 1.0
    result: list[Shape] = []
    for shape in shapes:
        if shape.is_chrome or shape.cx <= 0 or shape.cy <= 0:
            continue
        if shape.is_content_placeholder:
            result.append(shape)
            continue
        if shape.is_placeholder:
            continue
        if shape.tag == "pic" and shape.area / slide_area < 0.02:
            continue                                  # логотип, а не иллюстрация
        if shape.tx_body is not None and shape.text:
            result.append(shape)
        elif shape.tag in ("pic", "graphicFrame"):
            result.append(shape)
    return result


def _pattern_from_part(pkg: Package, part: str, kind: str, typography: Typography,
                       width: int, height: int, is_first: bool) -> Pattern | None:
    shapes = _pattern_shapes(pkg, part, kind, width, height)
    slots = [slot for slot in (_slot_from_shape(pkg, part, shape, typography, width, height)
                               for shape in shapes) if slot is not None]
    if not slots:
        return None
    _single_title(slots)

    repeat = _detect_repeat(slots)
    root = pkg.xml(part)
    layout_type = root.get("type") if kind == "layout" else None
    name = pkg.name_of(part)

    archetype, confidence, evidence = _classify(name, layout_type, slots, repeat,
                                                typography, is_first)

    # Нижний предел кегля — от того, как набран сам макет, а не от эталона
    # роли: у WorkSpace эталонный «body» 36pt, а подписи на слайдах — 16.
    # Считать от эталона значит запретить ужимать ниже 21pt текст, который
    # дизайнер сам набрал шестнадцатым.
    sizes = [slot.size_pt or (typography.styles[slot.style].size_pt
                              if slot.style in typography.styles else None)
             for slot in slots if slot.role not in ("image", "chart", "table")]
    sizes = [size for size in sizes if size]
    min_size = min(sizes) if sizes else 12.0

    text_shapes = [s for s in shapes if s.tx_body is not None]
    autofit = "shrink" if any(_autofit(s) == "shrink" for s in text_shapes) else "none"

    return Pattern(
        id=f"{archetype}-{part.rsplit('/', 1)[-1].removesuffix('.xml')}",
        archetype=archetype,
        source_kind=kind,                              # type: ignore[arg-type]
        source_name=name,
        source_part=part,
        render_mode="use_layout" if kind == "layout" else "clone_slide",
        layout_part=part if kind == "layout" else pkg.layout_of(part),
        slots=slots,
        repeat=repeat,
        accepts={
            "blocks": ARCHETYPE_ACCEPTS.get(archetype, ["paragraph"]),
            "min": 1,
            "max": repeat.max if repeat else max(1, len([s for s in slots
                                                         if s.role in ("body", "item")])),
            # Иллюстрация нужна, только если под неё отведено заметное место:
            # мелкий декоративный плейсхолдер на обложке требованием не является.
            # Считаем суммарную площадь: три колонки под фотографии по отдельности
            # невелики, но раскладка без снимков превращается в пустой лист.
            "needs_image": sum(slot.bbox[2] * slot.bbox[3] for slot in slots
                               if slot.role == "image") > 0.12,
            "vertical_text": any(_is_vertical(shape) for shape in text_shapes),
        },
        fit={"autofit": autofit,
             "min_size_pt": round(max(8.0, min_size * 0.6), 1),
             "shrink_step": 0.9},
        confidence=confidence,
        evidence=evidence,
    )


# Больше этого числа немых фигур на слайде — это не композиция, а справочный
# лист: библиотека иконок, палитра, набор пиктограмм.
REFERENCE_SHEET_SHAPES = 40


def extract_patterns(pkg: Package, typography: Typography) -> list[Pattern]:
    width, height = pkg.slide_size
    patterns: list[Pattern] = []
    seen: dict[tuple, Pattern] = {}

    for index, part in enumerate(pkg.layouts):
        pattern = _pattern_from_part(pkg, part, "layout", typography, width, height,
                                     is_first=index == 0)
        if pattern is None:
            continue
        signature = _signature(pattern.slots)
        if signature in seen:
            seen[signature].evidence.append(f"дублирует макет «{pattern.source_name}»")
            continue
        seen[signature] = pattern
        patterns.append(pattern)

    # Слайды-примеры дают паттерны только там, где дизайн нарисован поверх макета.
    for part in pkg.slides:
        shapes = pkg.shapes(part)
        free = [s for s in shapes if not s.is_placeholder and not s.is_chrome
                and (s.tx_body is not None or s.tag in ("pic", "graphicFrame"))]
        layout_part = pkg.layout_of(part)
        if not free:
            for pattern in patterns:
                if pattern.source_part == layout_part:
                    pattern.confidence = round(min(1.0, pattern.confidence + 0.1), 2)
                    pattern.evidence.append("применён на слайде-примере")
            continue
        # Страница с библиотекой иконок или набором фигур — справочник для
        # дизайнера, а не раскладка: заголовок и текст там есть, но сотня
        # значков останется на слайде вместе с нашим контентом.
        silent = sum(1 for s in shapes if s.tx_body is None and not s.is_placeholder)
        if silent > REFERENCE_SHEET_SHAPES:
            continue

        pattern = _pattern_from_part(pkg, part, "slide", typography, width, height,
                                     is_first=False)
        if pattern is None:
            continue
        signature = _signature(pattern.slots)
        if signature in seen:
            continue
        seen[signature] = pattern
        patterns.append(pattern)

    return patterns
