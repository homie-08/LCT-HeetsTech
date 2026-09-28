"""Синтетические паттерны: то, чего в шаблоне нет, но что собирается по его правилам.

Схема процесса из фигур. Далеко не в каждом шаблоне есть макет под шаги
процесса — у трёх шаблонов организаторов его нет ни у одного. Дизайнер в
таком случае берёт макет «заголовок + свободное поле» и рисует схему сам:
ряд карточек с номерами, соединённых стрелками, в цветах темы. Здесь то же
самое оформлено как паттерн: слот заголовка от самого макета и один слот
роли `diagram` на содержательную область. Матчер оценивает его наравне с
остальными (с небольшой уступкой родным макетам), укладчик отдаёт ему шаги,
композитор рисует фигуры.
"""

from __future__ import annotations

import io

from .area import content_area
from .model import Capacity, DesignSystem, Pattern, Slot

# Сколько шагов держит схема: меньше трёх — не процесс, больше шести — не
# схема, а таблица.
MIN_STEPS = 3
MAX_STEPS = 6
# Знаков на шаг: номер, короткая шапка и пояснение.
STEP_CHARS = 90
# Поле под схему — не меньше этих долей слайда: иначе шаги не прочитать.
DIAGRAM_MIN_W = 0.55
DIAGRAM_MIN_H = 0.34

PROCESS_ID = "process-diagram"


def process_pattern(design: DesignSystem, pkg=None) -> Pattern | None:
    """Паттерн схемы процесса на самом спокойном просторном макете с заголовком."""
    best: tuple[float, Pattern, list[float], Slot] | None = None
    for pattern in design.patterns:
        if pattern.source_kind != "layout" or pattern.render_mode != "use_layout":
            continue
        titles = [slot for slot in pattern.slots if slot.role == "title"]
        if not titles:
            continue
        if any(slot.role in ("image", "chart", "table", "metric_value") for slot in pattern.slots):
            continue                                # макет под фото или цифры — не поле
        area = content_area(pattern, design, DIAGRAM_MIN_W, DIAGRAM_MIN_H)
        if area is None:
            continue
        # Чем больше свободного поля, чем меньше в макете чужих слотов и чем
        # спокойнее фон под полем, тем лучше ляжет схема: плейсхолдеры под ней
        # композитор уберёт, а декор фона останется и будет просвечивать.
        busy = _background_busyness(design, pattern, area, pkg)
        score = area[2] * area[3] * (1.0 - busy) - 0.02 * (len(pattern.slots) - 1)
        if best is None or score > best[0]:
            best = (score, pattern, area, titles[0])
    if best is None:
        return None

    _, base, area, title = best
    return Pattern(
        id=PROCESS_ID,
        archetype="process",
        source_kind="layout",
        source_name=base.source_name,
        source_part=base.source_part,
        render_mode="use_layout",
        layout_part=base.layout_part or base.source_part,
        slots=[
            title.model_copy(),
            Slot(role="diagram", bbox=[round(value, 4) for value in area], style="body_l1",
                 capacity=Capacity(chars=STEP_CHARS * MAX_STEPS, lines=MAX_STEPS)),
        ],
        accepts={"synthetic": "process", "steps": [MIN_STEPS, MAX_STEPS]},
        confidence=0.5,
        evidence=[f"схема процесса из фигур на макете «{base.source_name}»"],
    )


# Пиксель считается «занятым», если отличается от цвета фона сильнее этого.
BUSY_THRESHOLD = 0.12


def _background_busyness(design: DesignSystem, pattern: Pattern, area: list[float],
                         pkg) -> float:
    """Доля поля, занятая рисунком фона макета: 0 — чистый фон, 1 — сплошной декор.

    Фоновая картинка макета лежит в пакете, рендер для этого не нужен: берём
    её, вырезаем поле схемы и считаем пиксели, ушедшие от преобладающего цвета.
    """
    if pkg is None:
        return 0.0
    scope = f"layout:{pattern.source_name}"
    pictures = [item for item in design.decor.items
                if item.kind == "picture" and item.image and scope in item.scope
                and item.bbox[2] >= 0.9 and item.bbox[3] >= 0.9]
    if not pictures:
        return 0.0
    try:
        from PIL import Image

        with Image.open(io.BytesIO(pkg.blob(pictures[0].image))) as image:
            picture = image.convert("RGB")
            picture.thumbnail((256, 256))
            width, height = picture.size
            box = (int(area[0] * width), int(area[1] * height),
                   max(int((area[0] + area[2]) * width), int(area[0] * width) + 1),
                   max(int((area[1] + area[3]) * height), int(area[1] * height) + 1))
            crop = picture.crop(box)
            pixels = list(crop.getdata())
    except Exception:                                 # noqa: BLE001 — нет картинки, нет счёта
        return 0.0
    if not pixels:
        return 0.0
    # Преобладающий цвет — по огрублённой гистограмме, чтобы градиент не
    # рассыпался на тысячи оттенков.
    buckets: dict[tuple[int, int, int], int] = {}
    for r, g, b in pixels:
        key = (r // 32, g // 32, b // 32)
        buckets[key] = buckets.get(key, 0) + 1
    base = max(buckets, key=buckets.get)
    base_rgb = tuple(channel * 32 + 16 for channel in base)
    limit = BUSY_THRESHOLD * 255
    busy = sum(1 for r, g, b in pixels
               if max(abs(r - base_rgb[0]), abs(g - base_rgb[1]), abs(b - base_rgb[2])) > limit)
    return round(busy / len(pixels), 3)
