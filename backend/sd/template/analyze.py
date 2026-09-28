"""Сборка дизайн-системы шаблона из отдельных анализаторов."""

from __future__ import annotations

from math import gcd
from pathlib import Path

from ..ooxml.package import Package
from .decor import extract_decor
from .geometry import extract_geometry
from .model import DesignSystem, SlideSize, Source
from .palette import extract_palette
from .patterns import extract_patterns
from .typography import extract_typography


def _ratio(width: int, height: int) -> str:
    divisor = gcd(width, height) or 1
    w, h = width // divisor, height // divisor
    # Приводим к привычным именам: 12192000x6858000 -> 16:9, а не 1778:1000.
    for name, (rw, rh) in {"16:9": (16, 9), "4:3": (4, 3), "16:10": (16, 10),
                           "3:2": (3, 2), "1:1": (1, 1)}.items():
        if abs(width / height - rw / rh) < 0.02:
            return name
    return f"{w}:{h}"


def analyze_template(path: str | Path) -> DesignSystem:
    """Шаблон -> дизайн-система. Ничего не пишет на диск."""
    pkg = Package.open(path)
    return analyze_package(pkg)


def analyze_package(pkg: Package) -> DesignSystem:
    width, height = pkg.slide_size
    warnings: list[str] = []

    if len(pkg.masters) > 1:
        warnings.append(
            f"В шаблоне {len(pkg.masters)} мастеров — дизайн-система строится по первому, "
            "остальные учитываются только как источник паттернов.")
    if not pkg.slides:
        warnings.append(
            "В шаблоне нет слайдов-примеров: паттерны будут извлечены только из макетов.")

    source = Source(
        file=pkg.name,
        sha256=pkg.sha256,
        slide_size=SlideSize(w_emu=width, h_emu=height, ratio=_ratio(width, height)),
        masters=len(pkg.masters),
        layouts=len(pkg.layouts),
        example_slides=len(pkg.slides),
    )

    typography = extract_typography(pkg)
    design = DesignSystem(
        source=source,
        palette=extract_palette(pkg),
        typography=typography,
        geometry=extract_geometry(pkg),
        decor=extract_decor(pkg),
        patterns=extract_patterns(pkg, typography),
        warnings=warnings,
    )

    # Схема процесса из фигур: макета под шаги в шаблоне может не быть, а
    # свободное поле под заголовком есть почти всегда.
    from .synthetic import process_pattern

    synthetic = process_pattern(design, pkg)
    if synthetic is not None:
        design.patterns.append(synthetic)

    covered = {pattern.archetype for pattern in design.patterns}
    missing = {"cover", "section", "bullets"} - covered
    if missing:
        design.warnings.append(
            "В шаблоне не нашлось паттернов под архетипы: " + ", ".join(sorted(missing))
            + " — под них подберём ближайшие по структуре.")

    if not design.typography.fonts.major:
        design.warnings.append("В теме не задана пара шрифтов — используем шрифт плейсхолдеров.")
    if design.typography.fonts.major and not design.typography.fonts.embedded:
        design.warnings.append(
            f"Шрифт «{design.typography.fonts.major}» не вшит в файл: на чужой машине "
            "потребуется подстановка метрически совместимого.")
    return design
