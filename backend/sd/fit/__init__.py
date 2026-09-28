"""Укладка текста: метрики шрифтов, перенос строк, ёмкость слотов."""

from .layout import FilledSlide, SlotFill, fill_deck, fill_slide
from .textmetrics import capacity_chars, fits, metrics_for, wrap_lines

__all__ = ["metrics_for", "capacity_chars", "fits", "wrap_lines",
           "fill_slide", "fill_deck", "FilledSlide", "SlotFill"]
