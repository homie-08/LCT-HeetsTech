"""Компьютерное зрение: маска краски, свободная область, яркость фона.

Тесты на синтетических изображениях — им не нужен ни PowerPoint, ни шаблоны,
поэтому они работают везде, включая CI.
"""

from __future__ import annotations

import numpy as np

from sd.vision.image import (dominant_color, ink_mask, largest_free_rect, region_luminance,
                             relative_luminance)
from sd.vision.safe_area import intersect, obstacles_in


def canvas(color: float = 1.0, size: tuple[int, int] = (360, 640)) -> np.ndarray:
    return np.full((*size, 3), color, dtype=np.float32)


def test_flat_fill_is_not_ink():
    """Ровная плашка — это фон: на неё можно класть текст."""
    assert ink_mask(canvas(0.55)).sum() == 0


def test_object_is_ink():
    image = canvas()
    image[40:120, 40:200] = 0.0
    assert ink_mask(image).sum() > 0


def test_largest_free_rect_avoids_the_object():
    image = canvas()
    image[0:120, :] = 0.0                       # плашка с краской сверху
    box = largest_free_rect(ink_mask(image))
    assert box[1] > 0.3, "свободная область должна начинаться ниже объекта"
    assert box[3] > 0.5


def test_thin_rule_is_not_an_obstacle():
    """Линейка-разделитель — часть раскладки, контент лежит между линейками."""
    image = canvas()
    image[180:183, 40:600] = 0.2
    assert ink_mask(image).sum() > 0
    _, obstacles = obstacles_in(image)
    assert obstacles == []


def test_logo_sized_blob_is_an_obstacle():
    """Логотип в маске краски — только контур; без заливки контуров он терялся."""
    image = canvas()
    image[280:340, 540:620] = 0.1
    _, obstacles = obstacles_in(image)
    assert len(obstacles) == 1
    x, y, w, h = obstacles[0].bbox
    assert x > 0.75 and y > 0.7 and 0.05 < w < 0.25 and 0.05 < h < 0.3


def test_luminance_matches_wcag_anchors():
    assert relative_luminance(np.array([[[1.0, 1.0, 1.0]]], dtype=np.float32))[0, 0] == 1.0
    assert relative_luminance(np.array([[[0.0, 0.0, 0.0]]], dtype=np.float32))[0, 0] == 0.0


def test_region_luminance_reads_the_right_area():
    image = canvas(1.0)
    image[:, :320] = 0.0
    assert region_luminance(image, (0.0, 0.0, 0.4, 1.0)) < 0.1
    assert region_luminance(image, (0.6, 0.0, 0.4, 1.0)) > 0.9


def test_dominant_color_of_a_patch():
    image = canvas(1.0)
    image[:, :] = np.array([0.2, 0.4, 0.8], dtype=np.float32)
    color = dominant_color(image, (0.1, 0.1, 0.5, 0.5))
    assert color.startswith("#") and len(color) == 7
    red, green, blue = (int(color[i:i + 2], 16) for i in (1, 3, 5))
    assert red < green < blue


def test_intersect_is_empty_for_disjoint_boxes():
    assert intersect((0.0, 0.0, 0.2, 0.2), (0.5, 0.5, 0.2, 0.2))[2:] == (0.0, 0.0)


def test_text_color_is_taken_from_the_render_not_the_style():
    """Белый заголовок на синей подложке — белый, что бы ни говорил стиль роли."""
    import numpy as np
    from sd.vision.image import text_color

    background = np.zeros((60, 100, 3), dtype=np.float32)
    background[:] = (0.0, 0.47, 1.0)                        # синяя подложка
    slide = background.copy()
    slide[20:30, 10:60] = 1.0                               # белая надпись
    assert text_color(slide, background, (0.0, 0.0, 1.0, 1.0)) == "#FFFFFF"
    assert text_color(background, background, (0.0, 0.0, 1.0, 1.0)) is None
