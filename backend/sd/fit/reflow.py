"""Переразметка слотов под фактический объём контента.

Дизайнер, у которого три тезиса вместо четырёх, не оставляет дыру — он
раздвигает три карточки на всю ширину. Автоматика по умолчанию так не умеет:
она заполняет первые слоты и удаляет остальные, из-за чего контент липнет к
краю, а слайд выглядит незаконченным.

Здесь это исправляется в границах, заданных самим шаблоном: колонки
распределяются по той же области и с тем же межколонником, что у исходной
группы, пропорции слотов сохраняются. Ничего нового не придумывается — меняется
только распределение внутри уже существующей раскладки.
"""

from __future__ import annotations

from ..template.model import Pattern, Slot

COLUMN_TOLERANCE = 0.02      # доля ширины слайда: слоты одной колонки


def _columns(slots: list[Slot]) -> list[list[Slot]]:
    """Группирует слоты в колонки по горизонтальному положению."""
    columns: list[list[Slot]] = []
    for slot in sorted(slots, key=lambda item: item.bbox[0]):
        for column in columns:
            if abs(column[0].bbox[0] - slot.bbox[0]) <= COLUMN_TOLERANCE:
                column.append(slot)
                break
        else:
            columns.append([slot])
    return columns


def _rows(slots: list[Slot]) -> list[list[Slot]]:
    rows: list[list[Slot]] = []
    for slot in sorted(slots, key=lambda item: item.bbox[1]):
        for row in rows:
            if abs(row[0].bbox[1] - slot.bbox[1]) <= COLUMN_TOLERANCE:
                row.append(slot)
                break
        else:
            rows.append([slot])
    return rows


def _spread(units: list[list[Slot]], start: float, end: float, gap: float,
            axis: int) -> None:
    """Раскладывает единицы равномерно по отрезку, сохраняя зазор."""
    count = len(units)
    if count == 0 or end <= start:
        return
    size = (end - start - gap * (count - 1)) / count
    if size <= 0:
        return
    for index, unit in enumerate(units):
        offset = start + index * (size + gap)
        # Внутри единицы слоты могут иметь разную ширину относительно колонки —
        # сохраняем их пропорции, а не выравниваем в один блок.
        base = min(slot.bbox[axis] for slot in unit)
        span = max(slot.bbox[axis] + slot.bbox[axis + 2] for slot in unit) - base
        if span <= 0:
            continue
        for slot in unit:
            relative_start = (slot.bbox[axis] - base) / span
            relative_size = slot.bbox[axis + 2] / span
            slot.bbox[axis] = round(offset + relative_start * size, 5)
            slot.bbox[axis + 2] = round(relative_size * size, 5)


def reflow_group(pattern: Pattern, used: set[int]) -> bool:
    """Раздвигает заполненные колонки повторяющейся группы на всю её область.

    `used` — идентификаторы слотов (`id(slot)`), в которые лёг контент.
    Возвращает True, если геометрия изменилась.
    """
    if pattern.repeat is None:
        return False

    members = [slot for slot in pattern.slots if slot.group == pattern.repeat.group]
    if len(members) < 2:
        return False

    horizontal = abs(pattern.repeat.step.get("dx", 0.0)) >= abs(
        pattern.repeat.step.get("dy", 0.0))
    axis = 0 if horizontal else 1

    units = _columns(members) if horizontal else _rows(members)
    filled_units = [unit for unit in units if any(id(slot) in used for slot in unit)]
    if not filled_units or len(filled_units) == len(units):
        return False

    start = min(slot.bbox[axis] for slot in members)
    end = max(slot.bbox[axis] + slot.bbox[axis + 2] for slot in members)
    gaps = []
    for previous, current in zip(units, units[1:]):
        previous_end = max(slot.bbox[axis] + slot.bbox[axis + 2] for slot in previous)
        gaps.append(min(slot.bbox[axis] for slot in current) - previous_end)
    gap = max(0.0, min(gaps)) if gaps else 0.02

    _spread(filled_units, start, end, gap, axis)
    return True


def reflow_slide(pattern: Pattern, used: set[int]) -> list[str]:
    """Все переразметки для слайда. Возвращает список выполненных действий."""
    actions: list[str] = []
    if reflow_group(pattern, used):
        actions.append("колонки группы раздвинуты на всю область")
    return actions
