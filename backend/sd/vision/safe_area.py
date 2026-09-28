"""Проверка безопасной зоны по рендеру пустых макетов.

XML честно говорит, где стоят плейсхолдеры, но молчит о том, что дизайнер
положил под них: фоновую фотографию, логотип в углу, плашку с именем раздела.
Рендер **пустого** макета показывает ровно оформление шаблона — по нему и
проверяем.

Важное различие: тонкая линейка-разделитель и логотип на картинке выглядят
одинаково «краской», но линейка — часть раскладки (контент лежит между
линейками), а логотип — препятствие. Разделяем их морфологическим открытием:
структуры тоньше ~1.5 % стороны слайда препятствиями не считаются.
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

import numpy as np
from scipy.ndimage import binary_fill_holes
from skimage.measure import label, regionprops
from skimage.morphology import binary_opening, disk

from ..template.model import DesignSystem
from .image import Bbox, ink_mask, largest_free_rect, load_rgb, region_luminance

# Обложки и разделители намеренно заняты декором — по ним сетку не выводят.
DECORATIVE = {"cover", "section", "image_full", "gallery", "blank"}

THIN_FRACTION = 0.015     # тоньше этой доли стороны — линейка, а не препятствие
MIN_OBSTACLE_AREA = 0.002  # доля площади слайда


@dataclass
class Obstacle:
    bbox: Bbox
    area: float
    source: str

    def corner(self) -> str:
        x, y, w, h = self.bbox
        cx, cy = x + w / 2, y + h / 2
        return ("верх" if cy < 0.33 else "низ" if cy > 0.66 else "центр") + " " + \
               ("слева" if cx < 0.33 else "справа" if cx > 0.66 else "по центру")


def obstacle_mask(rgb: np.ndarray) -> np.ndarray:
    """Краска без тонких структур: остаются логотипы, фотографии, крупные плашки.

    Порядок важен. Маска краски — это **границы** объектов, поэтому крупный
    логотип в ней выглядит как тонкий контур и открытие стёрло бы его наравне с
    линейкой. Сначала заливаем замкнутые контуры (объект становится телом), и
    только потом убираем то, что осталось тонким.
    """
    height = rgb.shape[0]
    radius = max(1, int(round(height * THIN_FRACTION)))
    filled = binary_fill_holes(ink_mask(rgb, grow=1))
    return binary_opening(filled, disk(radius))


def obstacles_in(rgb: np.ndarray, source: str = "") -> tuple[np.ndarray, list[Obstacle]]:
    """Препятствия на изображении: крупные и толстые по обеим осям."""
    mask = obstacle_mask(rgb)
    height, width = mask.shape
    slide_area = float(height * width)

    obstacles: list[Obstacle] = []
    for region in regionprops(label(mask)):
        min_row, min_col, max_row, max_col = region.bbox
        box_w = (max_col - min_col) / width
        box_h = (max_row - min_row) / height
        if box_w * box_h < MIN_OBSTACLE_AREA:
            continue
        # Полоса во всю ширину слайда — это разделитель раскладки, а не объект,
        # который нельзя перекрывать. Требуем толщину по обеим осям.
        if min(box_w, box_h) < THIN_FRACTION:
            continue
        obstacles.append(Obstacle(
            bbox=(round(min_col / width, 4), round(min_row / height, 4),
                  round(box_w, 4), round(box_h, 4)),
            area=round(box_w * box_h, 4),
            source=source,
        ))
    return mask, obstacles


def find_obstacles(image_path: str | Path) -> tuple[np.ndarray, list[Obstacle]]:
    return obstacles_in(load_rgb(image_path), str(image_path))


def intersect(first: Bbox, second: Bbox) -> Bbox:
    x = max(first[0], second[0])
    y = max(first[1], second[1])
    right = min(first[0] + first[2], second[0] + second[2])
    bottom = min(first[1] + first[3], second[1] + second[3])
    return (round(x, 4), round(y, 4),
            round(max(0.0, right - x), 4), round(max(0.0, bottom - y), 4))


def _area(box: Bbox) -> float:
    return box[2] * box[3]


def refine_safe_area(design: DesignSystem, layout_images: dict[str, Path]
                     ) -> tuple[Bbox, list[str], list[Obstacle]]:
    """Уточнённая зона, замечания и список препятствий, найденных глазами."""
    declared: Bbox = tuple(design.geometry.safe_area)          # type: ignore[assignment]
    notes: list[str] = []

    content_parts = {pattern.source_part for pattern in design.patterns
                     if pattern.source_kind == "layout" and pattern.archetype not in DECORATIVE}
    candidates = [path for part, path in layout_images.items() if part in content_parts]
    if not candidates:
        candidates = list(layout_images.values())
    if not candidates:
        return declared, ["рендер недоступен — зона только из XML"], []

    all_obstacles: list[Obstacle] = []
    free_boxes: list[Bbox] = []
    for path in candidates:
        mask, obstacles = find_obstacles(path)
        all_obstacles.extend(obstacles)
        free_boxes.append(largest_free_rect(mask))

    # Медиана по макетам: один макет с фоновой картинкой не должен схлопнуть зону.
    middle = len(free_boxes) // 2
    lefts = sorted(box[0] for box in free_boxes)
    tops = sorted(box[1] for box in free_boxes)
    rights = sorted(box[0] + box[2] for box in free_boxes)
    bottoms = sorted(box[1] + box[3] for box in free_boxes)
    visual: Bbox = (lefts[middle], tops[middle],
                    max(0.0, rights[middle] - lefts[middle]),
                    max(0.0, bottoms[middle] - tops[middle]))

    merged = intersect(declared, visual)
    persistent = _persistent_obstacles(all_obstacles, len(candidates))

    if _area(merged) < 0.6 * _area(declared):
        notes.append(
            f"Рендер даёт зону {_fmt(visual)} против {_fmt(declared)} из разметки — "
            "расхождение больше 40 %, оставляем разметку и помечаем препятствия.")
        result = declared
    else:
        result = merged

    for obstacle in persistent:
        if _area(intersect(obstacle.bbox, result)) > 0:
            notes.append(f"Препятствие {_fmt(obstacle.bbox)} ({obstacle.corner()}) "
                         f"попадает в зону контента — под ним нельзя размещать текст.")
    return result, notes, persistent


def _persistent_obstacles(obstacles: list[Obstacle], layouts: int) -> list[Obstacle]:
    """Препятствия, встречающиеся на большинстве макетов, — это оформление шаблона."""
    buckets: dict[tuple, list[Obstacle]] = {}
    for obstacle in obstacles:
        key = tuple(round(value, 1) for value in obstacle.bbox)
        buckets.setdefault(key, []).append(obstacle)

    threshold = max(2, layouts // 2)
    return [max(group, key=lambda item: item.area)
            for group in buckets.values() if len(group) >= threshold]


def background_under(image_path: str | Path, bbox: Bbox) -> float:
    """Яркость фона под слотом: светлее 0.5 — нужен тёмный текст, и наоборот."""
    return region_luminance(load_rgb(image_path), bbox)


def _fmt(box: Bbox) -> str:
    return "[" + ", ".join(f"{value:.3f}" for value in box) + "]"
