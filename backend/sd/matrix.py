"""Один контент через все шаблоны сразу.

Это главная демонстрация кейса, сведённая к одной команде. План истории строится
**один раз** и переиспользуется: значит, различия между презентациями объясняются
только шаблоном, а не тем, что модель каждый раз придумала что-то своё.

Результат — страница со сводкой: чем отличаются извлечённые дизайн-системы, какие
макеты выбраны под один и тот же слайд плана и что показал нормоконтроль.
"""

from __future__ import annotations

import html
import shutil
from dataclasses import dataclass, field
from pathlib import Path

from .content import parse_content
from .content.model import ContentIR
from .plan import DeckPlan, build_plan, match_deck
from .qa import build_with_repair
from .qa.model import DeckReport
from .template.analyze import analyze_template
from .template.model import DesignSystem

TEMPLATE_SUFFIXES = {".pptx", ".potx"}


@dataclass
class MatrixEntry:
    template: Path
    design: DesignSystem
    report: DeckReport
    deck: Path
    patterns: list[str] = field(default_factory=list)
    images: list[Path] = field(default_factory=list)
    error: str = ""


def run_matrix(content: str | Path, templates: str | Path, out_dir: str | Path,
               client=None, slides: int | None = None, render: bool = True,
               progress=print) -> tuple[ContentIR, DeckPlan, list[MatrixEntry]]:
    out_dir = Path(out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)

    ir = parse_content(content)
    plan = build_plan(ir, client, target_slides=slides)
    progress(f"контент: {len(ir.blocks)} блоков → план из {len(plan.slides)} слайдов "
             f"({plan.source})")

    paths = sorted(path for path in Path(templates).iterdir()
                   if path.suffix.lower() in TEMPLATE_SUFFIXES) \
        if Path(templates).is_dir() else [Path(templates)]

    entries: list[MatrixEntry] = []
    for path in paths:
        progress(f"  {path.name} …")
        design = analyze_template(path)
        spec = match_deck(plan, design, ir)
        deck_path = out_dir / f"{path.stem}.pptx"
        try:
            _, report, filled = build_with_repair(
                design, spec, ir, path, deck_path, client=client, visual=render,
                work_dir=out_dir / "_qa" / path.stem)
        except Exception as error:                       # pragma: no cover
            entries.append(MatrixEntry(path, design, DeckReport(), deck_path,
                                       error=str(error)))
            continue

        images: list[Path] = []
        if render:
            try:
                from .render import render_deck

                rendered = render_deck(deck_path, out_dir / "img" / path.stem, 640)
                images = list(rendered.images)
            except Exception as error:
                progress(f"    рендер недоступен: {error}")

        entries.append(MatrixEntry(
            template=path, design=design, report=report, deck=deck_path,
            patterns=[(design.pattern(slide.pattern_id).archetype
                       if design.pattern(slide.pattern_id) else "?")
                      for slide in spec.slides],
            images=images))
        progress(f"    {report.metrics.summary()}")

    _write_report(ir, plan, entries, out_dir)
    return ir, plan, entries


STYLE = """
:root { color-scheme: light dark; --bg:#fff; --fg:#111; --muted:#666; --line:#e5e5e5;
        --card:#fafafa; }
@media (prefers-color-scheme: dark) {
  :root { --bg:#141416; --fg:#ededed; --muted:#9a9a9a; --line:#2a2a2e; --card:#1c1c20; } }
* { box-sizing: border-box; }
body { margin:0; padding:24px; background:var(--bg); color:var(--fg);
       font:14px/1.5 "Segoe UI", system-ui, sans-serif; }
h1 { font-size:22px; margin:0 0 4px; } h2 { font-size:16px; margin:28px 0 10px; }
.sub { color:var(--muted); margin-bottom:18px; }
table { border-collapse:collapse; width:100%; font-size:13px; }
th, td { border:1px solid var(--line); padding:6px 9px; text-align:left; }
th { background:var(--card); font-weight:600; }
td.num { text-align:right; font-variant-numeric:tabular-nums; }
.bad { color:#c2410c; font-weight:600; }
.row { display:flex; gap:6px; overflow-x:auto; padding:6px 0 10px; }
.row img { height:104px; border:1px solid var(--line); border-radius:4px; }
.swatch { display:inline-block; width:16px; height:16px; border-radius:3px;
          border:1px solid var(--line); vertical-align:-3px; margin-right:2px; }
code { font:12px/1.5 ui-monospace, monospace; }
"""


def _write_report(ir: ContentIR, plan: DeckPlan, entries: list[MatrixEntry],
                  out_dir: Path) -> Path:
    ok = [entry for entry in entries if not entry.error]

    design_rows = "".join(
        f"<tr><td>{html.escape(entry.template.name)}</td>"
        f"<td>{entry.design.source.slide_size.ratio}</td>"
        f"<td>{html.escape(entry.design.typography.fonts.major)}</td>"
        f"<td>{''.join(f'<span class=swatch style=background:{color}></span>' for color in entry.design.palette.accent_seq[:6])}</td>"
        f"<td><code>{entry.design.palette.roles.get('page_bg', '')}</code></td>"
        f"<td class=num>{entry.design.geometry.columns.count}</td>"
        f"<td class=num>{len(entry.design.patterns)}</td></tr>"
        for entry in ok)

    metric_rows = "".join(
        f"<tr><td>{html.escape(entry.template.name)}</td>"
        f"<td class=num>{entry.report.metrics.font_conformance:.0%}</td>"
        f"<td class=num>{entry.report.metrics.palette_conformance:.0%}</td>"
        f"<td class=num>{entry.report.metrics.grid_alignment:.0%}</td>"
        f"<td class='num {'bad' if entry.report.metrics.overflow_slides else ''}'>"
        f"{entry.report.metrics.overflow_slides}</td>"
        f"<td class='num {'bad' if entry.report.metrics.collision_slides else ''}'>"
        f"{entry.report.metrics.collision_slides}</td>"
        f"<td class=num>{entry.report.metrics.pattern_diversity:.2f}</td>"
        f"<td class=num>{entry.report.metrics.coverage:.0%}</td></tr>"
        for entry in ok)

    header = "".join(f"<th>{html.escape(entry.template.stem[:18])}</th>" for entry in ok)
    choice_rows = "".join(
        f"<tr><td>{slide.n}. <b>{slide.intent}</b><br>"
        f"<span style='color:var(--muted)'>{html.escape(slide.key_message[:48])}</span></td>"
        + "".join(f"<td>{entry.patterns[index] if index < len(entry.patterns) else '—'}</td>"
                  for entry in ok)
        + "</tr>"
        for index, slide in enumerate(plan.slides))

    galleries = "".join(
        f"<h2>{html.escape(entry.template.name)}</h2><div class=row>"
        + "".join(f'<img src="img/{entry.template.stem}/{image.name}" alt="">'
                  for image in entry.images)
        + "</div>"
        for entry in ok if entry.images)

    for entry in ok:
        for image in entry.images:
            target = out_dir / "img" / entry.template.stem / image.name
            target.parent.mkdir(parents=True, exist_ok=True)
            if Path(image).resolve() != target.resolve():
                shutil.copyfile(image, target)

    failures = "".join(
        f"<li>{html.escape(entry.template.name)}: {html.escape(entry.error)}</li>"
        for entry in entries if entry.error)

    document = f"""<!doctype html><html lang="ru"><meta charset="utf-8">
<title>Один контент × {len(ok)} шаблонов</title><style>{STYLE}</style>
<h1>Один контент × {len(ok)} шаблонов</h1>
<div class="sub">{len(ir.blocks)} блоков контента · план из {len(plan.slides)} слайдов
  ({plan.source}) построен один раз и переиспользован для всех шаблонов —
  различия ниже объясняются только шаблоном.</div>

<h2>Что извлечено из шаблонов</h2>
<table><tr><th>Шаблон</th><th>Формат</th><th>Шрифт</th><th>Акценты</th>
<th>Фон</th><th>Колонок</th><th>Паттернов</th></tr>{design_rows}</table>

<h2>Какой макет выбран под один и тот же слайд</h2>
<table><tr><th>Слайд плана</th>{header}</tr>{choice_rows}</table>

<h2>Нормоконтроль</h2>
<table><tr><th>Шаблон</th><th>Шрифты</th><th>Палитра</th><th>Сетка</th>
<th>Переполнений</th><th>Коллизий</th><th>Разнообразие</th><th>Покрытие</th></tr>
{metric_rows}</table>
{f'<h2>Не собралось</h2><ul>{failures}</ul>' if failures else ''}
{galleries}
</html>"""

    target = out_dir / "index.html"
    target.write_text(document, encoding="utf-8")
    return target
