"""Сборка готовой презентации из шаблона, паттернов и уложенного контента."""

from .deck import BuildResult, build_deck

__all__ = ["build_deck", "BuildResult"]
