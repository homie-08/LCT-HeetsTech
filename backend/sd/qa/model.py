"""Типы отчёта нормоконтроля."""

from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, Field

Severity = Literal["error", "warning", "info"]
DefectKind = Literal["overflow", "stray", "collision", "contrast", "empty_slot",
                     "font", "palette", "grid", "coverage", "diversity", "audit"]
Nature = Literal["deterministic", "contextual"]

# Какие из старых проверок нормоконтроля что чинят: пересборка слайда с
# ужатым бюджетом лечит только то, что произошло от объёма текста.
FIXABLE_KINDS = {"overflow": "пересборка слайда с ужатым бюджетом",
                 "stray": "пересборка слайда с ужатым бюджетом",
                 "collision": "пересборка слайда с ужатым бюджетом",
                 "coverage": "пересборка на макете с бо́льшим числом мест"}


# Группы чек-листа для проверок нормоконтроля, которые были до аудита.
KIND_GROUPS = {"overflow": "вёрстка", "stray": "вёрстка", "collision": "вёрстка",
               "grid": "вёрстка", "font": "шаблон", "palette": "шаблон",
               "contrast": "шаблон", "empty_slot": "целостность",
               "coverage": "целостность", "diversity": "плотность"}


class Defect(BaseModel):
    kind: DefectKind
    severity: Severity = "error"
    slide: int = 0
    message: str = ""
    bbox: list[float] | None = None
    detail: str = ""
    check: str = ""
    """Идентификатор проверки из каталога аудита (для старых проверок — kind)."""
    nature: Nature = "deterministic"
    fixable: bool = False
    fix: str = ""
    group: str = ""

    def model_post_init(self, __context) -> None:
        if not self.check:
            self.check = self.kind
        if not self.group:
            self.group = KIND_GROUPS.get(self.kind, "нормоконтроль")
        if self.kind in FIXABLE_KINDS and not self.fix:
            self.fixable, self.fix = True, FIXABLE_KINDS[self.kind]

    @property
    def id(self) -> str:
        """Устойчивый адрес находки — по нему пользователь выбирает, что чинить.

        Не `hash()`: он у строк случайный от запуска к запуску, а адрес должен
        совпадать между сборкой и запросом на ремонт после перезапуска.
        """
        import zlib

        return f"{self.slide}:{self.check}:{zlib.crc32(self.message.encode('utf-8')) % 100000}"

    def __str__(self) -> str:  # pragma: no cover
        where = f"слайд {self.slide}: " if self.slide else ""
        return f"{where}{self.message}"


class Metrics(BaseModel):
    """Числа из docs/01-task-analysis.md §5 — их считает `sd check`."""

    font_conformance: float = 1.0
    palette_conformance: float = 1.0
    grid_alignment: float = 1.0
    overflow_slides: int = 0
    collision_slides: int = 0
    contrast_pass: float = 1.0
    pattern_diversity: float = 0.0
    coverage: float = 0.0
    slides: int = 0

    def summary(self) -> str:
        return (f"шрифты {self.font_conformance:.0%} · палитра {self.palette_conformance:.0%} · "
                f"сетка {self.grid_alignment:.0%} · контраст {self.contrast_pass:.0%} · "
                f"переполнений {self.overflow_slides} · коллизий {self.collision_slides} · "
                f"разнообразие {self.pattern_diversity:.2f} · покрытие {self.coverage:.0%}")


class DeckReport(BaseModel):
    deck: str = ""
    template: str = ""
    metrics: Metrics = Field(default_factory=Metrics)
    defects: list[Defect] = Field(default_factory=list)
    notes: list[str] = Field(default_factory=list)
    skills: dict[str, int] = Field(default_factory=dict)
    """Версии промптов агентов, которыми собрана колода."""
    llm: str = ""
    checks: list[str] = Field(default_factory=list)
    """Какие проверки чек-листа выполнены."""
    skipped_checks: dict[str, str] = Field(default_factory=dict)
    """Какие пропущены и почему (обычно — контекстуальные без модели)."""

    @property
    def errors(self) -> list[Defect]:
        return [defect for defect in self.defects if defect.severity == "error"]

    @property
    def clean(self) -> bool:
        return not self.errors

    def slides_with_errors(self) -> set[int]:
        return {defect.slide for defect in self.errors if defect.slide}
