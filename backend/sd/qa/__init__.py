"""Нормоконтроль готовой презентации: метрики, дефекты, цикл ремонта."""

from .model import DeckReport, Defect, Metrics
from .repair import build_with_repair, check_deck, repair_selected
from .static import static_report
from .visual import VisualInspector

__all__ = ["DeckReport", "Defect", "Metrics", "static_report", "VisualInspector",
           "check_deck", "build_with_repair", "repair_selected"]
