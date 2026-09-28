"""Цикл «собрал → посмотрел → починил».

Измерение по метрикам шрифта бывает оптимистичнее реальной вёрстки: PowerPoint
переносит строки чуть иначе, а подстановка шрифта добавляет расхождение. Поэтому
последнее слово за рендером: слайды, где на картинке видно переполнение,
пересобираются с ужатым бюджетом ёмкости, и так до тех пор, пока дефекты не
исчезнут или не кончатся попытки.

Оставшиеся дефекты не прячутся: они попадают в отчёт с номером слайда и
координатами — иначе «без ручного редактирования» нечем подтвердить.
"""

from __future__ import annotations

from pathlib import Path

from ..compose import BuildResult, build_deck
from ..content.model import ContentIR
from ..fit import fill_deck
from ..template.model import DesignSystem
from .model import DeckReport, Defect
from .static import static_report
from .visual import VisualInspector

BUDGET_STEPS = [0.82, 0.68]     # насколько ужимаем слот после каждой неудачи


def check_deck(deck_path: str | Path, design: DesignSystem, ir: ContentIR,
               filled_slides, template: str | Path,
               inspector: VisualInspector | None = None, client=None,
               audit: bool = True) -> DeckReport:
    """Полный отчёт: разметка, аудит по чек-листу и, если есть рендерер, картинка."""
    from ..llm import prompts
    from .audit import audit_deck

    metrics, defects = static_report(deck_path, design, ir, filled_slides)
    report = DeckReport(deck=str(deck_path), template=str(template),
                        metrics=metrics, defects=list(defects),
                        skills=prompts.versions())

    if audit:
        # Чек-лист заказчика — детерминированная часть всегда, контекстуальная
        # (вопросы модели) — когда модель подключена.
        found = audit_deck(deck_path, design, ir, filled_slides, client=client)
        report.defects.extend(found.defects)
        report.checks = found.checked
        report.skipped_checks = found.skipped

    for slide in filled_slides:
        for defect_text in slide.defects:
            # Укладчик уже подписывает номер слайда — второй раз не дублируем.
            message = defect_text.removeprefix(f"слайд {slide.n}: ")
            if message.startswith("не размещено фрагментов") and slide.dropped:
                continue                      # каждый фрагмент уже назван покрытием
            report.defects.append(Defect(kind="overflow", severity="warning",
                                         slide=slide.n, message=message))

    if inspector is None:
        report.notes.append("рендерер недоступен — визуальные проверки пропущены")
        # Контраст меряется по картинке слайда: без рендерера честно «не проверено».
        if "contrast" in report.checks:
            report.checks.remove("contrast")
            report.skipped_checks["contrast"] = "рендерер недоступен"
        return report

    visual = inspector.inspect(deck_path, filled_slides)
    report.defects.extend(_fold_contrast(visual.defects))
    report.metrics.contrast_pass = round(visual.contrast_pass, 4)
    report.metrics.overflow_slides = len({defect.slide for defect in visual.defects
                                          if defect.kind == "overflow"})
    report.metrics.collision_slides = len({defect.slide for defect in visual.defects
                                           if defect.kind == "collision"})
    return report


def _fold_contrast(defects: list[Defect], threshold: int = 3) -> list[Defect]:
    """Одно и то же сочетание цветов шаблона на многих слайдах — одна находка.

    Синий заголовок на белом — решение дизайнера шаблона, и повторять его
    четырнадцать раз в списке значит заслонить им находки по существу.
    """
    groups: dict[str, list[Defect]] = {}
    for defect in defects:
        if defect.kind == "contrast":
            groups.setdefault(defect.message, []).append(defect)
    folded: list[Defect] = []
    seen: set[str] = set()
    for defect in defects:
        if defect.kind != "contrast" or len(groups[defect.message]) < threshold:
            folded.append(defect)
            continue
        if defect.message in seen:
            continue
        seen.add(defect.message)
        slides = sorted({item.slide for item in groups[defect.message]})
        folded.append(defect.model_copy(update={
            "slide": 0,
            "message": f"{defect.message}; слайды {', '.join(map(str, slides))}"}))
    return folded


def build_with_repair(design: DesignSystem, spec, ir: ContentIR,
                      template: str | Path, out_path: str | Path,
                      client=None, rounds: int = 2, visual: bool = True,
                      work_dir: Path | None = None
                      ) -> tuple[BuildResult, DeckReport, list]:
    """Собирает презентацию и чинит слайды, на которых рендер показал дефекты."""
    work_dir = Path(work_dir or Path(out_path).parent / "_qa")
    inspector = (VisualInspector(design, template, work_dir)
                 if visual and VisualInspector.available() else None)

    budgets: dict[int, float] = {}
    filled = fill_deck(design, spec, ir, budgets, client)
    result = build_deck(design, filled, ir, template, out_path)
    report = check_deck(out_path, design, ir, filled, template, inspector, client)

    for attempt in range(rounds):
        broken = {defect.slide for defect in report.defects
                  if defect.kind in ("overflow", "stray") and defect.severity == "error"}
        if not broken:
            break

        budget = BUDGET_STEPS[min(attempt, len(BUDGET_STEPS) - 1)]
        for number in broken:
            budgets[number] = budget
        report.notes.append(
            f"ремонт {attempt + 1}: ужимаем слайды {sorted(broken)} до {budget:.0%} ёмкости")

        filled = fill_deck(design, spec, ir, budgets, client)
        result = build_deck(design, filled, ir, template, out_path)
        report = check_deck(out_path, design, ir, filled, template, inspector, client)
        report.notes.append(f"выполнено раундов ремонта: {attempt + 1}")

    result.defects = [str(defect) for defect in report.errors]
    if client is not None:
        report.llm = getattr(client, "name", "")
        if getattr(client, "exhausted", False):
            report.notes.append("бюджет времени на модель исчерпан — остаток собран без неё")
    return result, report, filled


def repair_selected(design: DesignSystem, spec, ir: ContentIR, template: str | Path,
                    out_path: str | Path, slides: list[int], client=None,
                    budget: float = 0.82, visual: bool = True,
                    work_dir: Path | None = None) -> tuple[BuildResult, DeckReport, list]:
    """Пересобирает выбранные слайды с ужатым бюджетом — то, что выбрал пользователь.

    Аудит показывает находки, а решает человек: какие из них чинить. Ремонт
    один на все «объёмные» находки — текст не влез, наложился, вылез за край,
    пунктов слишком много: слайд собирается заново с меньшей долей ёмкости, и
    укладчик сам сокращает, что не помещается.
    """
    work_dir = Path(work_dir or Path(out_path).parent / "_qa")
    inspector = (VisualInspector(design, template, work_dir)
                 if visual and VisualInspector.available() else None)
    budgets = {number: budget for number in slides}
    filled = fill_deck(design, spec, ir, budgets, client)
    notes = [f"ремонт по выбору: слайды {sorted(slides)} собраны на {budget:.0%} ёмкости"]

    # Неразмещённый фрагмент ужатием не лечится — ему нужно место. Такому
    # слайду ищем макет с достаточным числом мест; если в шаблоне такого нет,
    # так и говорим, а фрагмент остаётся в находках.
    moved = False
    for slide in filled:
        if slide.n not in slides or not slide.dropped:
            continue
        needed = len([fill for fill in slide.fills if not fill.is_empty
                      and fill.slot.role in ("item", "body", "quote", "metric_value")]
                     ) + len(slide.dropped)
        spec_slide = next(item for item in spec.slides if item.n == slide.n)
        better = _roomier_pattern(design, spec_slide, ir, needed, spec)
        if better is None:
            notes.append(f"слайд {slide.n}: в шаблоне нет макета на {needed} мест — "
                         f"фрагмент остаётся неразмещённым")
            continue
        notes.append(f"слайд {slide.n}: макет заменён на «{better.id}» ради {needed} мест")
        spec_slide.pattern_id = better.id
        moved = True
    if moved:
        filled = fill_deck(design, spec, ir, budgets, client)

    result = build_deck(design, filled, ir, template, out_path)
    report = check_deck(out_path, design, ir, filled, template, inspector, client)
    report.notes.extend(notes)
    result.defects = [str(defect) for defect in report.errors]
    return result, report, filled


def _roomier_pattern(design: DesignSystem, spec_slide, ir: ContentIR, needed: int, spec):
    """Лучший по оценке макет, у которого мест не меньше `needed`, кроме текущего."""
    from ..plan import variants as variant_set
    from ..plan.match import _pattern_supply, score

    variant = variant_set.get(getattr(spec.plan, "variant", None))
    position = ("first" if spec_slide.n == 1
                else "last" if spec_slide.n == len(spec.slides) else "middle")
    best, best_total = None, None
    for pattern in design.patterns:
        if not pattern.slots or pattern.id == spec_slide.pattern_id:
            continue
        _, _, places, lines = _pattern_supply(pattern)
        if max(places, lines if places <= 1 else 0) < needed:
            continue
        total = score(pattern, spec_slide.plan, ir, 0, design, position, variant).total
        if total <= 0:
            continue
        if best_total is None or total > best_total:
            best, best_total = pattern, total
    return best
