"""Содержательная область макета — свободное поле под заголовком.

Сюда укладчик кладёт таблицу, график или схему, когда своего слота под них в
макете нет; матчер этой же функцией решает, есть ли место; из неё же
собирается синтетический паттерн схемы процесса. Одна мерка на всех — иначе
матчер выберет макет, в котором укладчик места не найдёт.
"""

from __future__ import annotations

from .model import DesignSystem, Pattern

# Зазор между заголовком и содержательной областью, доля высоты слайда.
CONTENT_GAP = 0.03
# Поле у края слайда, ближе которого содержательная область не подходит.
EDGE = 0.03


def content_area(pattern: Pattern, design: DesignSystem, need_w: float = 0.35,
                 need_h: float = 0.22) -> list[float] | None:
    """Свободное поле под заголовком, куда можно положить таблицу или график.

    Границы берутся у самого макета: по ширине — размах его слотов, по
    высоте — от низа заголовка до низа безопасной зоны. Безопасная зона из
    геометрии годится не всегда: на шаблонах с крупным декором она бывает
    вырожденной, тогда край берётся по умолчанию. Той же функцией пользуется
    матчер — иначе он выберет макет, в котором укладчик места не найдёт.
    """
    titles = [slot for slot in pattern.slots if slot.role == "title"]
    others = [slot for slot in pattern.slots if slot.role != "title"]
    top = max((slot.bbox[1] + slot.bbox[3] for slot in titles), default=0.12) + CONTENT_GAP

    safe = design.geometry.safe_area
    sane = 0.2 < safe[2] <= 1 and 0.3 < safe[3] <= 1
    bottom = (safe[1] + safe[3]) if sane else 0.9
    if others:
        left = min(slot.bbox[0] for slot in others)
        right = max(slot.bbox[0] + slot.bbox[2] for slot in others)
    elif sane:
        left, right = safe[0], safe[0] + safe[2]
    else:
        left, right = 0.06, 0.94
    if titles:
        left = min(left, min(slot.bbox[0] for slot in titles))
        right = max(right, max(slot.bbox[0] + slot.bbox[2] for slot in titles))
    # Слот под фото во весь кадр начинается за краем слайда — область под
    # медиа за ним не идёт: у слайда есть поля.
    left, right = max(left, EDGE), min(right, 1 - EDGE)
    top = max(top, EDGE)

    width, height = right - left, bottom - top
    if width < need_w or height < need_h:
        return None
    return [left, top, width, height]
