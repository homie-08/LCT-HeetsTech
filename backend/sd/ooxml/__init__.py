"""Низкоуровневая работа с пакетом OOXML: части, связи, цвет, заливки, шейпы."""

from .color import ResolvedColor, contrast_ratio, relative_luminance, resolve_color
from .fill import Fill, StyleContext, background_fill, read_fill, shape_fill
from .ns import NS, EMU_PER_PT, qn
from .package import Package
from .shapes import Shape, iter_shapes

__all__ = [
    "NS", "EMU_PER_PT", "qn", "Package", "Shape", "iter_shapes",
    "ResolvedColor", "resolve_color", "contrast_ratio", "relative_luminance",
    "Fill", "StyleContext", "read_fill", "shape_fill", "background_fill",
]
