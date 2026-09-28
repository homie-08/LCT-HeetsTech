"""Сборка презентации целиком: план → подбор макетов → укладка → файл → аудит.

Одна точка входа для CLI и API, чтобы они не расходились: три варианта
вёрстки, бюджет модели и отчёт собираются здесь одинаково. Вариант меняет
только план и предпочтения матчера; шаблон, контент и правила укладки у всех
трёх одни.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path

from .compose import BuildResult
from .content.model import ContentIR
from .plan import build_plan, match_deck
from .plan import variants as variant_set
from .plan.model import DeckPlan, DeckSpec
from .plan.variants import Variant
from .qa import build_with_repair
from .qa.model import DeckReport
from .template.model import DesignSystem


@dataclass
class VariantResult:
    variant: Variant
    plan: DeckPlan
    spec: DeckSpec
    result: BuildResult
    report: DeckReport
    filled: list
    path: Path
    images: list[Path] = field(default_factory=list)


def build_one(design: DesignSystem, ir: ContentIR, template: str | Path, out_path: Path,
              variant: Variant | str | None = None, client=None, brief: str = "",
              target_slides: int | None = None, rounds: int = 2, visual: bool = True,
              work_dir: Path | None = None) -> VariantResult:
    """Собирает один вариант презентации."""
    chosen = variant if isinstance(variant, Variant) else variant_set.get(variant)
    plan = build_plan(ir, client, brief=brief, target_slides=target_slides, variant=chosen)
    spec = match_deck(plan, design, ir, chosen)
    result, report, filled = build_with_repair(
        design, spec, ir, template, out_path, client=client, rounds=rounds,
        visual=visual, work_dir=work_dir)
    report.notes.insert(0, f"вариант вёрстки: {chosen.label} — {chosen.tagline}")
    report.notes[1:1] = [note for note in plan.warnings if note not in report.notes]
    return VariantResult(variant=chosen, plan=plan, spec=spec, result=result,
                         report=report, filled=filled, path=Path(out_path))


def build_variants(design: DesignSystem, ir: ContentIR, template: str | Path,
                   out_dir: Path, client=None, brief: str = "",
                   target_slides: int | None = None, rounds: int = 2,
                   visual: bool = True, names: list[str] | None = None,
                   progress=None) -> dict[str, VariantResult]:
    """Три варианта вёрстки одного контента на одном шаблоне.

    Файлы ложатся в `out_dir/<variant>/deck.pptx`. Модель, если она есть,
    спрашивают один раз — план кешируется по тексту запроса, и варианты
    расходятся уже после неё.
    """
    out_dir = Path(out_dir)
    results: dict[str, VariantResult] = {}
    for variant in (variant_set.all_variants() if names is None
                    else [variant_set.get(name) for name in names]):
        if progress is not None:
            progress(variant)
        folder = out_dir / variant.id
        folder.mkdir(parents=True, exist_ok=True)
        results[variant.id] = build_one(
            design, ir, template, folder / "deck.pptx", variant, client, brief,
            target_slides, rounds, visual, work_dir=folder / "qa")
    return results
