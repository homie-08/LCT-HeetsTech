"""Рендер через LibreOffice headless — переносимый путь (Linux, CI, чужая машина).

`soffice --convert-to pdf` даёт PDF, из него PyMuPDF растрирует страницы.
Точность высокая, но не эталонная: LibreOffice иначе трактует автофит и
подставляет свои шрифты, поэтому расхождения записываем в отчёт, а не считаем
ошибкой вёрстки.
"""

from __future__ import annotations

import os
import shutil
import subprocess
import tempfile
from pathlib import Path

from .base import RenderResult, cached, store

CANDIDATES = [
    r"C:\Program Files\LibreOffice\program\soffice.exe",
    r"C:\Program Files (x86)\LibreOffice\program\soffice.exe",
    "/usr/bin/soffice",
    "/usr/local/bin/soffice",
    "/Applications/LibreOffice.app/Contents/MacOS/soffice",
]


def find_soffice() -> str | None:
    if (found := shutil.which("soffice")) is not None:
        return found
    for candidate in CANDIDATES:
        if Path(candidate).exists():
            return candidate
    return None


class LibreOfficeRenderer:
    name = "libreoffice"
    fidelity = 2

    def __init__(self, timeout: int = 180):
        self.timeout = timeout

    def available(self) -> bool:
        return find_soffice() is not None

    def render(self, deck: Path, out_dir: Path, width_px: int = 1280) -> RenderResult:
        deck = Path(deck).resolve()
        if (hit := cached(deck, width_px, self.name, Path(out_dir))) is not None:
            return RenderResult(hit, self.name, "из кеша")

        soffice = find_soffice()
        if soffice is None:
            raise RuntimeError("LibreOffice не найден")

        import fitz

        out_dir = Path(out_dir).resolve()
        out_dir.mkdir(parents=True, exist_ok=True)
        with tempfile.TemporaryDirectory() as work:
            # Свой профиль: иначе soffice откажется работать, если LibreOffice
            # уже запущен пользователем.
            profile = Path(work) / "profile"
            subprocess.run(
                [soffice, "--headless", "--norestore",
                 f"-env:UserInstallation=file:///{profile.as_posix()}",
                 "--convert-to", "pdf", "--outdir", work, str(deck)],
                check=True, timeout=self.timeout, capture_output=True,
                env={**os.environ, "SAL_USE_VCLPLUGIN": "svp"},
            )
            pdfs = list(Path(work).glob("*.pdf"))
            if not pdfs:
                raise RuntimeError("LibreOffice не отдал PDF")

            images: list[Path] = []
            with fitz.open(pdfs[0]) as document:
                for index, page in enumerate(document, start=1):
                    zoom = width_px / page.rect.width
                    pixmap = page.get_pixmap(matrix=fitz.Matrix(zoom, zoom))
                    target = out_dir / f"slide-{index:03d}.png"
                    pixmap.save(target)
                    images.append(target)
        return RenderResult(store(deck, width_px, self.name, images), self.name)
