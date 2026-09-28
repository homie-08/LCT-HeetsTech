"""Работа с HTML-шаблонами презентаций (.dc.html)."""

from .parse import HtmlTemplate, Pattern, Slot, parse_template

__all__ = ["HtmlTemplate", "Pattern", "Slot", "parse_template"]
