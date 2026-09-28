"""Проверка готовых слайдов по рендеру.

Приём тот же, что при разборе шаблона: сравниваем слайд с его же оформлением.
Рендер пустого макета — это фон, который шаблон рисует сам; всё, что появилось
поверх него, — наш контент. Если такой контент оказался вне слотов, значит текст
вылез за границы или лёг не туда, и это видно без разметки, по пикселям.

Для клонированных слайдов фоном служит ещё и рендер исходного слайда-примера:
скопированный декор иначе считался бы нашим контентом.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path

import numpy as np
from skimage.measure import label, regionprops
from skimage.morphology import binary_dilation, disk

from ..ooxml.color import contrast_ratio
from ..ooxml.package import Package
from ..render import available_backends, render_deck
from ..render.preview import render_layouts, render_slides
from ..template.model import DesignSystem, Slot
from ..vision.image import crop, dominant_color, ink_mask, load_rgb, text_color
from .model import Defect

STRAY_MIN_AREA = 0.0015     # доля площади слайда
SLOT_MARGIN = 0.012         # допуск вокруг слота: свисающие элементы букв
TEXT_ROLES = {"title", "subtitle", "body", "item", "quote", "caption",
              "metric_value", "metric_label", "author", "kicker"}


@dataclass
class VisualResult:
    defects: list[Defect] = field(default_factory=list)
    contrast_checked: int = 0
    contrast_passed: int = 0
    images: list[Path] = field(default_factory=list)

    @property
    def contrast_pass(self) -> float:
        return self.contrast_passed / self.contrast_checked if self.contrast_checked else 1.0


def _allowed_mask(shape: tuple[int, int], slots: list[Slot]) -> np.ndarray:
    height, width = shape
    allowed = np.zeros(shape, dtype=bool)
    for slot in slots:
        x, y, w, h = slot.bbox
        x0 = max(0, int((x - SLOT_MARGIN) * width))
        y0 = max(0, int((y - SLOT_MARGIN) * height))
        x1 = min(width, int((x + w + SLOT_MARGIN) * width))
        y1 = min(height, int((y + h + SLOT_MARGIN) * height))
        if x1 > x0 and y1 > y0:
            allowed[y0:y1, x0:x1] = True
    return allowed


def _resize_mask(mask: np.ndarray, shape: tuple[int, int]) -> np.ndarray:
    if mask.shape == shape:
        return mask
    rows = (np.linspace(0, mask.shape[0] - 1, shape[0])).astype(int)
    columns = (np.linspace(0, mask.shape[1] - 1, shape[1])).astype(int)
    return mask[np.ix_(rows, columns)]


def _classify_stray(box: tuple[float, float, float, float],
                    slots: list[Slot]) -> tuple[str, Slot | None]:
    """Пятно рядом со слотом — переполнение; вдали от всех — посторонний контент."""
    x, y, w, h = box
    for slot in slots:
        sx, sy, sw, sh = slot.bbox
        near_horizontally = sx - 0.05 <= x <= sx + sw + 0.05
        below = sy + sh - 0.02 <= y <= sy + sh + 0.12
        if near_horizontally and below:
            return "overflow", slot
    return "stray", None


def inspect_slide(image_path: Path, background: np.ndarray, slots: list[Slot],
                  slide_number: int) -> list[Defect]:
    rgb = load_rgb(image_path)
    ink = ink_mask(rgb, grow=1)
    background = _resize_mask(background, ink.shape)

    content = ink & ~binary_dilation(background, disk(3))
    stray = content & ~_allowed_mask(ink.shape, slots)

    height, width = ink.shape
    slide_area = float(height * width)
    defects: list[Defect] = []

    for region in regionprops(label(stray)):
        min_row, min_col, max_row, max_col = region.bbox
        area = (max_row - min_row) * (max_col - min_col) / slide_area
        if area < STRAY_MIN_AREA:
            continue
        box = (min_col / width, min_row / height,
               (max_col - min_col) / width, (max_row - min_row) / height)
        kind, slot = _classify_stray(box, slots)
        message = (f"текст вышел за границы слота «{slot.role}»" if slot
                   else "контент вне слотов макета")
        defects.append(Defect(kind=kind, severity="error", slide=slide_number,
                              message=message,
                              bbox=[round(value, 4) for value in box]))
    return defects


def check_contrast(layout_image: Path, design: DesignSystem, slots: list[Slot],
                   slide_number: int, slide_image: Path | None = None
                   ) -> tuple[list[Defect], int, int]:
    """Контраст текста к фактическому фону под слотом, а не к цвету страницы.

    Цвет текста — тоже фактический, с рендера слайда: макет может перекрасить
    заголовок в белый на синей подложке, а стиль роли по-прежнему говорит
    «синий». Стиль — запасной ответ, когда на рендере текста не видно."""
    rgb = load_rgb(layout_image)
    slide_rgb = load_rgb(slide_image) if slide_image is not None else None
    if slide_rgb is not None and slide_rgb.shape != rgb.shape:
        slide_rgb = None
    defects: list[Defect] = []
    checked = passed = 0

    for slot in slots:
        if slot.role not in TEXT_ROLES:
            continue
        style = design.typography.styles.get(slot.style)
        actual = text_color(slide_rgb, rgb, tuple(slot.bbox)) if slide_rgb is not None else None
        color = actual or (style.color if style is not None else None)
        if not color:
            continue
        background = dominant_color(rgb, tuple(slot.bbox))
        ratio = contrast_ratio(color, background)
        checked += 1
        if ratio >= 4.5:
            passed += 1
        else:
            # Цвета текста и фона мы не выбираем — оба пришли из шаблона.
            # Низкий контраст здесь означает решение дизайнера шаблона, а не
            # дефект сборки, поэтому это сведения, а не ошибка.
            defects.append(Defect(
                kind="contrast", severity="info", slide=slide_number,
                message=f"контраст {ratio:.1f}:1 у «{slot.role}» "
                        f"({color} на {background}) — сочетание из шаблона",
                bbox=slot.bbox))
    return defects, checked, passed


class VisualInspector:
    """Готовит фоны шаблона один раз и переиспользует их между прогонами ремонта."""

    def __init__(self, design: DesignSystem, template: str | Path,
                 work_dir: Path, width_px: int = 1100):
        self.design = design
        self.pkg = Package.open(template)
        self.work_dir = Path(work_dir)
        self.width_px = width_px
        self._layouts: dict[str, Path] = {}
        self._slides: dict[str, Path] = {}
        self._masks: dict[str, np.ndarray] = {}

    @staticmethod
    def available() -> bool:
        return bool(available_backends())

    def _prepare(self) -> None:
        if self._layouts:
            return
        self._layouts = render_layouts(self.pkg, self.work_dir / "bg", self.width_px)
        self._slides = render_slides(self.pkg, self.work_dir / "bg", self.width_px)

    def background_for(self, pattern) -> tuple[np.ndarray, Path | None]:
        self._prepare()
        layout_image = self._layouts.get(pattern.layout_part or "")
        key = f"{pattern.id}"
        if key not in self._masks:
            masks = []
            if layout_image:
                masks.append(ink_mask(load_rgb(layout_image), grow=1))
            if pattern.render_mode == "clone_slide":
                # Декор, скопированный со слайда-примера, — тоже фон.
                source_image = self._slides.get(pattern.source_part)
                if source_image:
                    masks.append(ink_mask(load_rgb(source_image), grow=1))
            if not masks:
                self._masks[key] = np.zeros((10, 10), dtype=bool)
            else:
                shape = masks[0].shape
                combined = np.zeros(shape, dtype=bool)
                for mask in masks:
                    combined |= _resize_mask(mask, shape)
                self._masks[key] = combined
        return self._masks[key], layout_image

    def inspect(self, deck_path: str | Path, filled_slides) -> VisualResult:
        result = VisualResult()
        rendered = render_deck(Path(deck_path), self.work_dir / "deck", self.width_px)
        result.images = list(rendered.images)

        for slide, image in zip(filled_slides, rendered.images):
            slots = [fill.slot for fill in slide.fills if not fill.is_empty]
            if not slots:
                continue
            background, layout_image = self.background_for(slide.pattern)
            result.defects.extend(inspect_slide(image, background, slots, slide.n))

            if layout_image is not None:
                contrast_defects, checked, passed = check_contrast(
                    layout_image, self.design, slots, slide.n, slide_image=image)
                result.defects.extend(contrast_defects)
                result.contrast_checked += checked
                result.contrast_passed += passed
        return result
