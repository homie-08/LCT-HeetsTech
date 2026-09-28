"""Пиктограммы: библиотека контуров, подбор по смыслу и нативные фигуры для pptx."""

from .library import KEYWORDS, NEUTRAL, SHAPES, pick, rank
from .shape import add_icon, icon_paths

__all__ = ["KEYWORDS", "NEUTRAL", "SHAPES", "pick", "rank", "add_icon", "icon_paths"]
