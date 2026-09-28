"""Выбор рендерера: берём самый точный из доступных на машине."""

from __future__ import annotations

from pathlib import Path

from .base import RenderResult, Renderer
from .libreoffice import LibreOfficeRenderer
from .powerpoint import PowerPointRenderer

BACKENDS: list[Renderer] = [PowerPointRenderer(), LibreOfficeRenderer()]


def available_backends() -> list[Renderer]:
    return [backend for backend in BACKENDS if backend.available()]


def get_renderer(prefer: str | None = None) -> Renderer | None:
    backends = available_backends()
    if prefer:
        for backend in backends:
            if backend.name == prefer:
                return backend
        return None
    return max(backends, key=lambda backend: backend.fidelity, default=None)


def render_deck(deck: Path, out_dir: Path, width_px: int = 1280,
                prefer: str | None = None) -> RenderResult:
    renderer = get_renderer(prefer)
    if renderer is None:
        raise RuntimeError(
            "Нет ни PowerPoint, ни LibreOffice. Установите LibreOffice "
            "(winget install TheDocumentFoundation.LibreOffice) или запускайте на "
            "машине с Office.")
    return renderer.render(Path(deck), Path(out_dir), width_px)


__all__ = ["Renderer", "RenderResult", "get_renderer", "render_deck",
           "available_backends", "PowerPointRenderer", "LibreOfficeRenderer"]
