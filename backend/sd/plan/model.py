"""План презентации и результат подбора паттернов."""

from __future__ import annotations

from pydantic import BaseModel, Field

from ..template.model import Archetype


class SlidePlan(BaseModel):
    """Один слайд как замысел: что показываем и чем."""

    n: int
    intent: Archetype
    key_message: str = ""
    blocks: list[str] = Field(default_factory=list)   # id блоков Content IR
    items: list[str] = Field(default_factory=list)
    """Текст, которого нет во входном контенте: пункты повестки, связки."""

    notes: str = ""


class DeckPlan(BaseModel):
    title: str = ""
    subtitle: str = ""
    slides: list[SlidePlan] = Field(default_factory=list)
    source: str = "heuristic"                          # heuristic | llm
    authored: bool = False
    """Текст слайдов написан моделью по брифу, а не взят из контент-пакета."""
    warnings: list[str] = Field(default_factory=list)
    variant: str = "balanced"
    """Вариант вёрстки, под который приведён план: compact | balanced | spacious."""


class ScoreBreakdown(BaseModel):
    """Разложение оценки — оно же объяснение выбора макета на защите."""

    archetype: float = 0.0
    capacity: float = 0.0
    assets: float = 0.0
    repeat_penalty: float = 0.0
    overflow_risk: float = 0.0
    density: float = 0.0
    """Ось варианта вёрстки: плюс за многоместные сетки в сжатом, минус — в просторном."""
    handicap: float = 0.0
    """Уступка синтетического макета: схема из фигур уступает родному макету шаблона."""

    @property
    def total(self) -> float:
        # Повтор макета стоит дёшево: в настоящих презентациях один и тот же
        # макет под однотипные слайды — норма, а вот подходящий по объёму макет
        # решает, будет слайд выглядеть законченным или полупустым.
        return round(2.0 * self.archetype + 1.8 * self.capacity + 0.7 * self.assets
                     - 0.5 * self.repeat_penalty - 2.0 * self.overflow_risk
                     + 0.6 * self.density - self.handicap, 4)

    def explain(self) -> str:
        handicap = f" · уступка −{self.handicap:.2f}" if self.handicap else ""
        return (f"архетип {self.archetype:.2f} · ёмкость {self.capacity:.2f} · "
                f"медиа {self.assets:.2f} · повтор −{self.repeat_penalty:.2f} · "
                f"риск переполнения −{self.overflow_risk:.2f}{handicap} = {self.total:.2f}")


class SlideSpec(BaseModel):
    """Слайд, для которого уже выбран паттерн."""

    n: int
    plan: SlidePlan
    pattern_id: str
    score: ScoreBreakdown = Field(default_factory=ScoreBreakdown)
    alternatives: list[tuple[str, float]] = Field(default_factory=list)

    @property
    def why(self) -> str:
        return self.score.explain()


class DeckSpec(BaseModel):
    plan: DeckPlan
    slides: list[SlideSpec] = Field(default_factory=list)
    template: str = ""
    warnings: list[str] = Field(default_factory=list)
