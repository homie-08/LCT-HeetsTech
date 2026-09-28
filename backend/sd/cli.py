"""CLI сервиса.

    python -m sd analyze <шаблон.pptx> [--out design_system.json] [--quiet] [-v]
    python -m sd analyze <папка> --out-dir out/            # пакетно по всем шаблонам
    python -m sd preview <шаблон.pptx> [--out-dir data/previews] [--width 1280]
    python -m sd plan <шаблон> <контент> [--brief …] [--no-llm] [-v]
    python -m sd build <шаблон> <контент> [--out deck.pptx] [--rounds 2]
    python -m sd check <deck.pptx> --template <шаблон> --content <контент>
    python -m sd matrix <контент> [--templates templates/deck]

Дальше здесь появятся `build`, `evaluate` и `matrix` — см. docs/02-architecture.md §11.
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

from .template.analyze import analyze_template
from .template.model import DesignSystem

TEMPLATE_SUFFIXES = {".pptx", ".potx"}


def _print_summary(design: DesignSystem, verbose: bool = False) -> None:
    source = design.source
    palette = design.palette
    typo = design.typography
    geo = design.geometry

    print(f"\n{source.file}  {source.slide_size.ratio} "
          f"({source.layouts} макетов, {source.example_slides} слайдов-примеров)")

    print("  палитра")
    for role, color in palette.roles.items():
        print(f"    {role:16} {color}   ← {palette.role_provenance.get(role, '')}")
    if palette.accent_seq:
        print(f"    {'accent_seq':16} {' '.join(palette.accent_seq)}")
    print(f"    {'основа':16} {'тёмная' if palette.is_dark else 'светлая'}")

    print(f"  шрифты: {typo.fonts.major} / {typo.fonts.minor}"
          + (f"  (вшиты: {', '.join(typo.fonts.embedded)})" if typo.fonts.embedded else ""))
    print(f"  шкала кеглей: {', '.join(str(size) for size in typo.scale_pt)}")
    for name, style in typo.styles.items():
        bullet = f"  маркер {style.bullet.char!r}" if style.bullet and style.bullet.char else ""
        print(f"    {name:13} {str(style.font):18} {style.size_pt}pt  {style.color}"
              f"  {style.align}{bullet}")

    margins = geo.margins
    print(f"  поля: л {margins.get('l')} п {margins.get('r')} "
          f"в {margins.get('t')} н {margins.get('b')}")
    print(f"  колонок {geo.columns.count}, межколонник {geo.columns.gutter}, "
          f"направляющих {len(geo.guides_x)}×{len(geo.guides_y)}")
    print(f"  безопасная зона: {geo.safe_area}")
    if geo.gaps:
        print(f"  отступы: {geo.gaps}")

    kinds: dict[str, int] = {}
    for item in design.decor.items:
        kinds[item.kind] = kinds.get(item.kind, 0) + 1
    print(f"  декор: {kinds or '—'}  стиль фигур: {design.decor.shape_style}")

    print(f"  паттернов: {len(design.patterns)}")
    for pattern in design.patterns:
        roles: dict[str, int] = {}
        for slot in pattern.slots:
            roles[slot.role] = roles.get(slot.role, 0) + 1
        composition = " ".join(f"{role}×{count}" if count > 1 else role
                               for role, count in roles.items())
        repeat = f"  ↻{pattern.repeat.max}" if pattern.repeat else ""
        title_slots = pattern.slots_by_role("title")
        capacity = f"  заголовок ≤{title_slots[0].capacity.chars} зн." if title_slots else ""
        print(f"    {pattern.archetype:11} {pattern.confidence:.2f}  "
              f"{pattern.source_name[:28]:28} {composition}{repeat}{capacity}")
        if verbose:
            print(f"      признаки: {'; '.join(pattern.evidence)}")

    for warning in design.warnings:
        print(f"  ⚠ {warning}")


def _templates_in(path: Path) -> list[Path]:
    if path.is_dir():
        return sorted(p for p in path.rglob("*") if p.suffix.lower() in TEMPLATE_SUFFIXES)
    return [path]


def cmd_analyze(args: argparse.Namespace) -> int:
    targets = _templates_in(Path(args.template))
    if not targets:
        print("Шаблоны не найдены", file=sys.stderr)
        return 1

    out_dir = Path(args.out_dir) if args.out_dir else None
    if out_dir:
        out_dir.mkdir(parents=True, exist_ok=True)

    for target in targets:
        design = analyze_template(target)
        payload = design.model_dump(mode="json", by_alias=True)

        if args.out and len(targets) == 1:
            destination = Path(args.out)
        elif out_dir:
            destination = out_dir / f"{target.stem}.design.json"
        else:
            destination = None

        if destination:
            destination.parent.mkdir(parents=True, exist_ok=True)
            destination.write_text(json.dumps(payload, ensure_ascii=False, indent=2),
                                   encoding="utf-8")
        if not args.quiet:
            _print_summary(design, verbose=args.verbose)
            if destination:
                print(f"  → {destination}")
        elif destination is None:
            print(json.dumps(payload, ensure_ascii=False, indent=2))
    return 0


def cmd_preview(args: argparse.Namespace) -> int:
    """Рендер шаблона, уточнение безопасной зоны по картинке и контрольный лист."""
    from .ooxml.package import Package
    from .render import available_backends
    from .render.contact_sheet import write_contact_sheet
    from .render.preview import render_layouts, render_patterns
    from .template.analyze import analyze_package
    from .vision.safe_area import refine_safe_area

    backends = available_backends()
    if not backends:
        print("Нет ни PowerPoint, ни LibreOffice — рендер невозможен.", file=sys.stderr)
        return 2
    print(f"рендерер: {max(backends, key=lambda b: b.fidelity).name}")

    for target in _templates_in(Path(args.template)):
        pkg = Package.open(target)
        design = analyze_package(pkg)
        out_dir = Path(args.out_dir) / target.stem

        previews = render_patterns(design, pkg, out_dir, args.width)
        layouts = render_layouts(pkg, out_dir, args.width)
        refined, notes, obstacles = refine_safe_area(design, layouts)

        print(f"\n{target.name}: {len(previews)} превью")
        print(f"  безопасная зона: XML {design.geometry.safe_area} → рендер {list(refined)}")
        if obstacles:
            print(f"  препятствий на макетах: {len(obstacles)}")
            for obstacle in obstacles[:5]:
                print(f"    {obstacle.corner():14} {obstacle.bbox}  "
                      f"{obstacle.area:.1%} площади")
        for note in notes:
            print(f"  ⚠ {note}")
        design.geometry.safe_area = list(refined)

        sheet = write_contact_sheet(design, previews, out_dir)
        (out_dir / "design.json").write_text(
            json.dumps(design.model_dump(mode="json", by_alias=True),
                       ensure_ascii=False, indent=2), encoding="utf-8")
        print(f"  → {sheet}")
    return 0


def cmd_plan(args: argparse.Namespace) -> int:
    """Контент -> план истории -> подбор паттернов шаблона."""
    from .content import parse_content
    from .llm import build_client, llm_status
    from .plan import build_plan, match_deck
    from .template.analyze import analyze_template

    print(llm_status())
    ir = parse_content(args.content)
    print(f"контент: {len(ir.blocks)} блоков, {ir.meta.words} слов, "
          f"язык {ir.meta.language}")

    client = None if args.no_llm else build_client()
    plan = build_plan(ir, client, brief=args.brief or "", target_slides=args.slides)
    print(f"план ({plan.source}): {len(plan.slides)} слайдов")

    design = analyze_template(args.template)
    spec = match_deck(plan, design, ir)

    print(f"\nшаблон: {design.source.file} ({len(design.patterns)} паттернов)\n")
    for slide in spec.slides:
        pattern = design.pattern(slide.pattern_id)
        blocks = ", ".join(slide.plan.blocks) or "—"
        print(f"  {slide.n:2}. {slide.plan.intent:11} → "
              f"{pattern.archetype if pattern else '?':11} "
              f"{(pattern.source_name if pattern else slide.pattern_id)[:30]:30} "
              f"{slide.score.total:6.2f}")
        print(f"      «{slide.plan.key_message[:70]}»  блоки: {blocks}")
        if args.verbose:
            print(f"      {slide.why}")
            if slide.alternatives:
                alternatives = ", ".join(f"{name} {value:.2f}"
                                         for name, value in slide.alternatives)
                print(f"      альтернативы: {alternatives}")

    for warning in spec.warnings:
        print(f"  ⚠ {warning}")

    if args.out:
        Path(args.out).write_text(
            json.dumps(spec.model_dump(mode="json"), ensure_ascii=False, indent=2),
            encoding="utf-8")
        print(f"\n→ {args.out}")
    return 0


def cmd_build(args: argparse.Namespace) -> int:
    """Шаблон + контент -> готовая презентация (или три варианта вёрстки)."""
    from .content import parse_content
    from .llm import build_client, llm_status, prompts
    from .pipeline import build_one, build_variants
    from .plan import variants as variant_set
    from .template.analyze import analyze_template

    print(llm_status())
    print("агенты: " + ", ".join(prompt.label for prompt in prompts.catalogue()))
    ir = parse_content(args.content)
    design = analyze_template(args.template)
    client = None if args.no_llm else build_client()
    rounds = 0 if args.no_repair else args.rounds
    visual = not args.no_check

    if args.variant.lower() == "all":
        out_dir = Path(args.out or f"data/out/{Path(args.template).stem}")
        if out_dir.suffix.lower() == ".pptx":
            out_dir = out_dir.with_suffix("")
        results = build_variants(design, ir, args.template, out_dir, client=client,
                                 brief=args.brief or "", target_slides=args.slides,
                                 rounds=rounds, visual=visual,
                                 progress=lambda variant: print(
                                     f"\n== {variant.label}: {variant.tagline}"))
        for built in results.values():
            _print_build(design, built.spec, built.filled, built.result, built.report, built.path)
        return 0

    out_path = Path(args.out or f"data/out/{Path(args.template).stem}.pptx")
    built = build_one(design, ir, args.template, out_path, variant_set.get(args.variant),
                      client=client, brief=args.brief or "", target_slides=args.slides,
                      rounds=rounds, visual=visual)
    _print_build(design, built.spec, built.filled, built.result, built.report, out_path)
    return 0


def _print_build(design, spec, filled, result, report, out_path: Path) -> None:
    print(f"\n{design.source.file} + план из {len(spec.slides)} слайдов → {result.slides} слайдов")
    print(f"  режимы сборки: {result.mode_counts}")
    for slide, fill in zip(spec.slides, filled):
        pattern = design.pattern(slide.pattern_id)
        print(f"  {slide.n:2}. {pattern.archetype if pattern else '?':11} "
              f"{(pattern.source_name if pattern else '')[:26]:26} "
              f"слотов занято {fill.used_slots}/{len(fill.fills)}")

    print(f"\nнормоконтроль: {report.metrics.summary()}")
    for defect in report.defects[:15]:
        mark = "⚠" if defect.severity == "error" else "·"
        print(f"  {mark} {defect}")
    for note in report.notes:
        print(f"  · {note}")
    verdict = "✔ дефектов нет" if report.clean else "⚠ дефекты остались"
    print(f"\n{verdict}  →  {out_path}")


def cmd_check(args: argparse.Namespace) -> int:
    """Нормоконтроль уже собранного файла."""
    from .content import parse_content
    from .fit import fill_deck
    from .plan import build_plan, match_deck
    from .qa import VisualInspector, check_deck
    from .template.analyze import analyze_template

    design = analyze_template(args.template)
    ir = parse_content(args.content)
    spec = match_deck(build_plan(ir, client=None), design, ir)
    filled = fill_deck(design, spec, ir)

    inspector = (VisualInspector(design, args.template, Path(args.deck).parent / "_qa")
                 if VisualInspector.available() else None)
    report = check_deck(args.deck, design, ir, filled, args.template, inspector)

    print(f"{Path(args.deck).name}: {report.metrics.summary()}")
    for defect in report.defects:
        mark = "⚠" if defect.severity == "error" else "·"
        print(f"  {mark} [{defect.kind}] {defect}")
    if args.out:
        Path(args.out).write_text(
            json.dumps(report.model_dump(mode="json"), ensure_ascii=False, indent=2),
            encoding="utf-8")
        print(f"→ {args.out}")
    return 0 if report.clean else 1


def cmd_matrix(args: argparse.Namespace) -> int:
    """Один контент через все шаблоны — главная демонстрация адаптивности."""
    from .llm import build_client, llm_status
    from .matrix import run_matrix

    print(llm_status())
    client = None if args.no_llm else build_client()
    _, plan, entries = run_matrix(args.content, args.templates, args.out,
                                  client=client, slides=args.slides,
                                  render=not args.no_render)

    print(f"\n{'шаблон':26} {'шрифты':>7} {'палитра':>8} {'перепол.':>9} "
          f"{'коллизии':>9} {'покрытие':>9}")
    for entry in entries:
        if entry.error:
            print(f"{entry.template.stem[:26]:26} ошибка: {entry.error[:60]}")
            continue
        metrics = entry.report.metrics
        print(f"{entry.template.stem[:26]:26} {metrics.font_conformance:>6.0%} "
              f"{metrics.palette_conformance:>7.0%} {metrics.overflow_slides:>9} "
              f"{metrics.collision_slides:>9} {metrics.coverage:>8.0%}")

    print(f"\nплан ({plan.source}) построен один раз и переиспользован — "
          f"различия объясняются шаблоном")
    print(f"→ {Path(args.out) / 'index.html'}")
    return 0


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="sd", description=__doc__,
                                     formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = parser.add_subparsers(dest="command", required=True)

    analyze = sub.add_parser("analyze", help="разобрать шаблон и показать дизайн-систему")
    analyze.add_argument("template", help="файл .pptx/.potx или папка с ними")
    analyze.add_argument("--out", help="куда положить design_system.json (для одного файла)")
    analyze.add_argument("--out-dir", help="куда складывать JSON при пакетном разборе")
    analyze.add_argument("--quiet", action="store_true", help="без человекочитаемой сводки")
    analyze.add_argument("--verbose", "-v", action="store_true",
                         help="показать признаки, по которым определён архетип")
    analyze.set_defaults(func=cmd_analyze)

    preview = sub.add_parser("preview",
                             help="отрендерить шаблон и собрать контрольный лист")
    preview.add_argument("template", help="файл .pptx/.potx или папка с ними")
    preview.add_argument("--out-dir", default="data/previews", help="куда складывать")
    preview.add_argument("--width", type=int, default=1280, help="ширина рендера, px")
    preview.set_defaults(func=cmd_preview)

    plan = sub.add_parser("plan", help="разобрать контент и подобрать паттерны шаблона")
    plan.add_argument("template", help="шаблон .pptx/.potx")
    plan.add_argument("content", help="файл или папка с контентом")
    plan.add_argument("--brief", help="аудитория, тон, акценты")
    plan.add_argument("--slides", type=int, help="ориентир по числу слайдов")
    plan.add_argument("--no-llm", action="store_true", help="только эвристики")
    plan.add_argument("--out", help="куда сохранить план в JSON")
    plan.add_argument("--verbose", "-v", action="store_true",
                      help="показать разложение оценки и альтернативы")
    plan.set_defaults(func=cmd_plan)

    build = sub.add_parser("build", help="собрать презентацию по шаблону и контенту")
    build.add_argument("template", help="шаблон .pptx/.potx")
    build.add_argument("content", help="файл или папка с контентом")
    build.add_argument("--brief", help="аудитория, тон, акценты")
    build.add_argument("--slides", type=int, help="ориентир по числу слайдов")
    build.add_argument("--no-llm", action="store_true", help="только эвристики")
    build.add_argument("--out", help="куда сохранить .pptx")
    build.add_argument("--variant", default="balanced",
                       help="вариант вёрстки: compact, balanced, spacious или all — все три")
    build.add_argument("--rounds", type=int, default=2, help="раундов ремонта")
    build.add_argument("--no-repair", action="store_true", help="собрать без ремонта")
    build.add_argument("--no-check", action="store_true",
                       help="без визуальных проверок (быстрее)")
    build.set_defaults(func=cmd_build)

    check = sub.add_parser("check", help="нормоконтроль собранной презентации")
    check.add_argument("deck", help="готовый .pptx")
    check.add_argument("--template", required=True, help="шаблон, по которому собрано")
    check.add_argument("--content", required=True, help="исходный контент")
    check.add_argument("--out", help="куда сохранить отчёт в JSON")
    check.set_defaults(func=cmd_check)

    matrix = sub.add_parser("matrix", help="один контент через все шаблоны")
    matrix.add_argument("content", help="файл или папка с контентом")
    matrix.add_argument("--templates", default="templates/deck", help="папка с шаблонами")
    matrix.add_argument("--out", default="data/out/matrix", help="куда сложить результат")
    matrix.add_argument("--slides", type=int, help="ориентир по числу слайдов")
    matrix.add_argument("--no-llm", action="store_true", help="только эвристики")
    matrix.add_argument("--no-render", action="store_true", help="без рендера и превью")
    matrix.set_defaults(func=cmd_matrix)
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    return args.func(args)


if __name__ == "__main__":
    raise SystemExit(main())
