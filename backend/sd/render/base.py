"""Общий интерфейс рендереров и кеш результатов.

Рендер нужен трижды: превью паттернов в интерфейсе, детект декора и
безопасной зоны по пустому макету, визуальный нормоконтроль готового слайда.
Бэкендов три, они взаимозаменяемы и отличаются точностью — решение не должно
падать, если на машине нет ни PowerPoint, ни LibreOffice.
"""

from __future__ import annotations

import hashlib
import shutil
from dataclasses import dataclass
from pathlib import Path
from typing import Protocol

CACHE_ROOT = Path(__file__).resolve().parents[3] / ".cache" / "render"


@dataclass
class RenderResult:
    images: list[Path]
    backend: str
    note: str = ""

    def __len__(self) -> int:
        return len(self.images)


class Renderer(Protocol):
    name: str
    fidelity: int          # 3 — эталон, 2 — высокая, 1 — приблизительная

    def available(self) -> bool: ...

    def render(self, deck: Path, out_dir: Path, width_px: int = 1280) -> RenderResult: ...


def cache_key(deck: Path, width_px: int, backend: str) -> Path:
    digest = hashlib.sha256(deck.read_bytes()).hexdigest()[:16]
    return CACHE_ROOT / f"{digest}-{backend}-{width_px}"


def cached(deck: Path, width_px: int, backend: str,
           out_dir: Path | None = None) -> list[Path] | None:
    directory = cache_key(deck, width_px, backend)
    if not directory.exists():
        return None
    images = sorted(directory.glob("slide-*.png"))
    if not images:
        return None
    # Попадание в кеш не должно оставлять каталог назначения со старыми
    # картинками: вызывающий смотрит именно туда и увидит прошлый прогон.
    return deliver(images, out_dir) if out_dir else images


def deliver(images: list[Path], out_dir: Path) -> list[Path]:
    out_dir.mkdir(parents=True, exist_ok=True)
    delivered: list[Path] = []
    for index, image in enumerate(images, start=1):
        destination = out_dir / f"slide-{index:03d}.png"
        if image.resolve() != destination.resolve():
            shutil.copyfile(image, destination)
        delivered.append(destination)
    return delivered


def store(deck: Path, width_px: int, backend: str, images: list[Path]) -> list[Path]:
    directory = cache_key(deck, width_px, backend)
    directory.mkdir(parents=True, exist_ok=True)
    stored: list[Path] = []
    for index, image in enumerate(images, start=1):
        destination = directory / f"slide-{index:03d}.png"
        if image.resolve() != destination.resolve():
            shutil.copyfile(image, destination)
        stored.append(destination)
    return stored
