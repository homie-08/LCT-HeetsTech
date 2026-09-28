"""Контрольный лист шаблона: что именно система увидела.

Одна страница, на которой рядом лежат рендер каждого паттерна, разметка
найденных слотов поверх него и признаки, по которым выбран архетип. Это и
инструмент отладки, и материал для защиты: видно, что решение читает шаблон,
а не подставляет заготовку.
"""

from __future__ import annotations

import html
import shutil
from pathlib import Path

from ..template.model import DesignSystem

ROLE_COLORS = {
    "title": "#e5484d", "subtitle": "#e07b39", "kicker": "#e07b39",
    "body": "#3b82f6", "item": "#0ea5e9", "quote": "#8b5cf6",
    "metric_value": "#16a34a", "metric_label": "#65a30d",
    "image": "#a855f7", "chart": "#0891b2", "table": "#0d9488",
    "caption": "#64748b", "footer": "#94a3b8", "author": "#64748b",
    "number": "#f59e0b",
}

STYLE = """
:root { color-scheme: light dark; --bg:#fff; --fg:#111; --muted:#666; --line:#e5e5e5;
        --card:#fafafa; }
@media (prefers-color-scheme: dark) {
  :root { --bg:#141416; --fg:#ededed; --muted:#9a9a9a; --line:#2a2a2e; --card:#1c1c20; } }
* { box-sizing: border-box; }
body { margin:0; padding:24px; background:var(--bg); color:var(--fg);
       font:14px/1.5 "Segoe UI", system-ui, sans-serif; }
h1 { font-size:20px; margin:0 0 4px; }
.sub { color:var(--muted); margin-bottom:20px; }
.summary { display:flex; flex-wrap:wrap; gap:24px; padding:16px; background:var(--card);
           border:1px solid var(--line); border-radius:10px; margin-bottom:24px; }
.summary div { min-width:180px; }
.summary b { display:block; font-size:12px; text-transform:uppercase;
             letter-spacing:.04em; color:var(--muted); margin-bottom:6px; }
.swatches { display:flex; gap:6px; flex-wrap:wrap; }
.swatch { width:26px; height:26px; border-radius:5px; border:1px solid var(--line); }
.grid { display:grid; grid-template-columns:repeat(auto-fill, minmax(340px, 1fr)); gap:18px; }
.card { border:1px solid var(--line); border-radius:10px; overflow:hidden;
        background:var(--card); }
.head { display:flex; justify-content:space-between; align-items:baseline; gap:8px;
        padding:10px 12px; border-bottom:1px solid var(--line); }
.arch { font-weight:600; }
.conf { color:var(--muted); font-variant-numeric:tabular-nums; }
.stage { position:relative; line-height:0; background:#8884; }
.stage img { width:100%; height:auto; display:block; }
.slot { position:absolute; border:1.5px solid; border-radius:2px; }
.slot span { position:absolute; top:0; left:0; font:10px/1.4 ui-monospace, monospace;
             padding:0 3px; color:#fff; white-space:nowrap; }
.meta { padding:10px 12px; font-size:12px; color:var(--muted); }
.meta code { color:var(--fg); }
"""


def _slot_overlay(pattern) -> str:
    parts = []
    for slot in pattern.slots:
        x, y, w, h = slot.bbox
        color = ROLE_COLORS.get(slot.role, "#888")
        label = slot.role if slot.group is None else f"{slot.role}[{slot.index}]"
        parts.append(
            f'<div class="slot" style="left:{x * 100:.2f}%;top:{y * 100:.2f}%;'
            f'width:{w * 100:.2f}%;height:{h * 100:.2f}%;border-color:{color}">'
            f'<span style="background:{color}">{html.escape(label)}</span></div>')
    return "".join(parts)


def _summary(design: DesignSystem) -> str:
    palette = design.palette
    typo = design.typography
    geo = design.geometry
    swatches = "".join(
        f'<div class="swatch" style="background:{color}" title="{name}: {color}"></div>'
        for name, color in palette.theme.items())
    roles = "<br>".join(
        f'<code>{name}</code> {color} <span style="color:var(--muted)">← '
        f'{html.escape(palette.role_provenance.get(name, ""))}</span>'
        for name, color in palette.roles.items())
    styles = "<br>".join(
        f"<code>{name}</code> {style.font} {style.size_pt}pt"
        for name, style in list(typo.styles.items())[:8])
    return f"""
    <div class="summary">
      <div><b>Палитра темы</b><div class="swatches">{swatches}</div></div>
      <div><b>Роли цвета</b>{roles}</div>
      <div><b>Типографика</b>{styles}</div>
      <div><b>Сетка</b>поля {geo.margins}<br>колонок {geo.columns.count},
           межколонник {geo.columns.gutter}<br>зона {geo.safe_area}</div>
    </div>"""


def write_contact_sheet(design: DesignSystem, previews: dict[str, Path],
                        out_dir: Path) -> Path:
    out_dir = Path(out_dir)
    image_dir = out_dir / "img"
    image_dir.mkdir(parents=True, exist_ok=True)

    cards = []
    for pattern in design.patterns:
        source = previews.get(pattern.id)
        stage = '<div class="stage" style="aspect-ratio:16/9"></div>'
        if source is not None and Path(source).exists():
            local = image_dir / f"{pattern.id}.png"
            shutil.copyfile(source, local)
            stage = (f'<div class="stage"><img src="img/{local.name}" alt="">'
                     f'{_slot_overlay(pattern)}</div>')

        capacity = ", ".join(
            f"{slot.role} ≤{slot.capacity.chars}"
            for slot in pattern.slots if slot.capacity.chars)
        repeat = f" · группа ↻{pattern.repeat.max}" if pattern.repeat else ""
        cards.append(f"""
        <div class="card">
          <div class="head"><span class="arch">{pattern.archetype}</span>
            <span class="conf">{pattern.confidence:.2f}</span></div>
          {stage}
          <div class="meta"><code>{html.escape(pattern.source_name)}</code>
            · {pattern.render_mode}{repeat}<br>
            {html.escape('; '.join(pattern.evidence))}<br>
            <span style="color:var(--muted)">{html.escape(capacity)}</span></div>
        </div>""")

    source = design.source
    document = f"""<!doctype html><html lang="ru"><meta charset="utf-8">
<title>{html.escape(source.file)} — разбор шаблона</title><style>{STYLE}</style>
<h1>{html.escape(source.file)}</h1>
<div class="sub">{source.slide_size.ratio} · {source.layouts} макетов ·
  {source.example_slides} слайдов-примеров · {len(design.patterns)} паттернов</div>
{_summary(design)}
<div class="grid">{''.join(cards)}</div>
</html>"""

    target = out_dir / "index.html"
    target.write_text(document, encoding="utf-8")
    return target
