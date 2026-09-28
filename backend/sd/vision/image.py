"""Базовые операции компьютерного зрения над рендером слайда.

Ключевое различение: **краска** и **фон**. Ровная цветная плашка — это фон, на
неё можно и нужно класть текст; логотип, фотография, линия, чужой текст — это
краска, туда лезть нельзя. Разница видна не по цвету, а по градиенту, поэтому
маска строится по границам, а не по отличию от «цвета фона».
"""

from __future__ import annotations

from pathlib import Path

import numpy as np
from PIL import Image
from skimage.color import rgb2gray
from skimage.filters import sobel
from skimage.morphology import binary_dilation, disk

Bbox = tuple[float, float, float, float]


def load_rgb(path: str | Path, max_width: int = 640) -> np.ndarray:
    """Изображение как (H, W, 3) в диапазоне 0..1, уменьшенное для скорости."""
    image = Image.open(path).convert("RGB")
    if image.width > max_width:
        height = round(image.height * max_width / image.width)
        image = image.resize((max_width, height), Image.LANCZOS)
    return np.asarray(image, dtype=np.float32) / 255.0


def relative_luminance(rgb: np.ndarray) -> np.ndarray:
    """Яркость по WCAG 2.1 — та же формула, что и для проверки контраста."""
    channels = np.where(rgb <= 0.04045, rgb / 12.92, ((rgb + 0.055) / 1.055) ** 2.4)
    return channels @ np.array([0.2126, 0.7152, 0.0722], dtype=np.float32)


def ink_mask(rgb: np.ndarray, threshold: float = 0.08, grow: int = 2) -> np.ndarray:
    """Маска «занято»: границы объектов, а не однотонные заливки."""
    edges = sobel(rgb2gray(rgb))
    mask = edges > threshold
    return binary_dilation(mask, disk(grow)) if grow else mask


def largest_free_rect(mask: np.ndarray) -> Bbox:
    """Наибольший прямоугольник без краски — классическая задача о гистограмме."""
    height, width = mask.shape
    heights = np.zeros(width, dtype=np.int32)
    best_area = 0
    best: tuple[int, int, int, int] = (0, 0, width, height)

    for row in range(height):
        heights = np.where(mask[row], 0, heights + 1)
        stack: list[tuple[int, int]] = []
        for column in range(width + 1):
            current = int(heights[column]) if column < width else 0
            start = column
            while stack and stack[-1][1] > current:
                index, tall = stack.pop()
                area = tall * (column - index)
                if area > best_area:
                    best_area = area
                    best = (index, row - tall + 1, column - index, tall)
                start = index
            stack.append((start, current))

    x, y, w, h = best
    return (round(x / width, 4), round(y / height, 4),
            round(w / width, 4), round(h / height, 4))


def crop(rgb: np.ndarray, bbox: Bbox) -> np.ndarray:
    height, width = rgb.shape[:2]
    x, y, w, h = bbox
    x0 = max(0, min(width - 1, int(x * width)))
    y0 = max(0, min(height - 1, int(y * height)))
    x1 = max(x0 + 1, min(width, int((x + w) * width)))
    y1 = max(y0 + 1, min(height, int((y + h) * height)))
    return rgb[y0:y1, x0:x1]


def region_luminance(rgb: np.ndarray, bbox: Bbox) -> float:
    """Средняя яркость фона под боксом — по ней выбирается светлое или тёмное начертание."""
    return float(relative_luminance(crop(rgb, bbox)).mean())


def dominant_color(rgb: np.ndarray, bbox: Bbox, bins: int = 16) -> str:
    """Самый частый цвет области — фактический фон под слотом."""
    patch = crop(rgb, bbox).reshape(-1, 3)
    quantised = np.clip((patch * (bins - 1)).round().astype(np.int32), 0, bins - 1)
    keys = quantised[:, 0] * bins * bins + quantised[:, 1] * bins + quantised[:, 2]
    winner = np.bincount(keys).argmax()
    channels = [(winner // (bins * bins)) % bins, (winner // bins) % bins, winner % bins]
    return "#" + "".join(f"{round(value * 255 / (bins - 1)):02X}" for value in channels)


def text_color(rgb: np.ndarray, background: np.ndarray, bbox: Bbox,
               threshold: float = 0.12, min_pixels: int = 40) -> str | None:
    """Фактический цвет текста в области: цвет пикселей, которыми слайд
    отличается от своего пустого макета. Пустая область — None."""
    patch = crop(rgb, bbox)
    base = crop(background, bbox)
    if patch.shape != base.shape or patch.size == 0:
        return None
    distance = np.abs(patch - base).max(axis=2)
    changed = distance > threshold
    if int(changed.sum()) < min_pixels:
        return None
    # Края букв сглажены — это смесь текста с фоном. Тело буквы — пиксели,
    # ушедшие от фона дальше всех; по ним и цвет.
    core = distance >= float(distance[changed].max()) * 0.7
    ink = patch[core] if int(core.sum()) >= min_pixels // 2 else patch[changed]
    return dominant_color(ink.reshape(1, -1, 3), (0.0, 0.0, 1.0, 1.0))


def ink_ratio(mask: np.ndarray, bbox: Bbox) -> float:
    """Доля закрашенных пикселей внутри бокса — так ловим переполнение и коллизии."""
    patch = crop(mask[:, :, None].astype(np.float32), bbox)
    return float(patch.mean())
