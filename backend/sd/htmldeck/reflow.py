"""Подгонка собранной колоды по месту — браузером, а не на глаз.

Сколько текста влезет в слот, по длине образца шаблона не узнать: одна и та же
подпись в узкой карточке займёт четыре строки, а в широкой — две. Оценка по
знакам поэтому всегда перестраховывается, и текст обрывается там, где место
ещё было.

Здесь то же самое решается измерением. Колода открывается в браузере, и для
каждого слайда проверяется одно: помещается ли содержимое в слайд. Если нет —
кегль уменьшается, как это сделал бы дизайнер, пока не поместится или пока не
упрётся в предел читаемости. И только то, что не влезло даже там, укорачивается
— ровно на столько, на сколько считает нужным сама вёрстка.

Возвращаются готовые числа: какому узлу какой кегль и до какой длины урезать.
Правки вносятся в разметку по адресам узлов — так же, как их находят слоты.
"""

from __future__ import annotations

import json
import re
import subprocess
from dataclasses import dataclass
from pathlib import Path

from lxml import etree

from .textmap import COLLECT_JS, variant

# Мельче этого текст на слайде не читается — тот же предел, что и при укладке.
MIN_FONT_PX = 24.0
# Шаг уменьшения. Мельче шаг — точнее подгонка и больше проходов вёрстки.
STEP = 0.94
# Больше этого числа проходов не бывает: 0.94^40 — это уже вчетверо мельче.
MAX_ROUNDS = 40

REFLOW_JS = COLLECT_JS + """
(() => {
  const report = {};
  const FLOOR = %(floor)s, STEP = %(step)s, ROUNDS = %(rounds)s;

  const fits = (section) => section.scrollHeight <= section.clientHeight + 1;

  const shrink = (items) => {
    // Уменьшаем всё разом и на одну долю: пропорции макета заданы дизайнером,
    // и правка одного кегля из трёх сломала бы их сильнее, чем общий сдвиг.
    let moved = false;
    items.forEach((item) => {
      const size = parseFloat(getComputedStyle(item.node).fontSize);
      if (size * STEP < FLOOR) return;
      item.node.style.fontSize = (size * STEP) + 'px';
      moved = true;
    });
    return moved;
  };

  const trim = (section, items) => {
    // Дошли до предела кегля, а слайд всё равно переполнен. Режем — но не
    // наугад: по одному слову с конца самой длинной подписи, пока не влезет.
    for (let guard = 0; guard < 400 && !fits(section); guard += 1) {
      const longest = items.reduce(
        (best, item) => (item.node.textContent.length >
                         (best ? best.node.textContent.length : 0) ? item : best), null);
      if (!longest) return;
      const words = longest.node.textContent.replace(/…$/, '').trim().split(/\\s+/);
      if (words.length < 3) return;
      words.pop();
      longest.node.textContent = words.join(' ') + '…';
    }
  };

  const settle = (section, index) => {
    const items = window.__sdItems(section);
    if (!items.length) return false;             // слайд ещё не свёрстан
    if (fits(section)) return true;

    for (let round = 0; round < ROUNDS && !fits(section); round += 1) {
      if (!shrink(items)) break;
    }
    trim(section, items);

    items.forEach((item) => {
      const path = window.__sdPath(item.node, section);
      if (path === null) return;
      const text = item.node.textContent.trim();
      report[index + ':' + path] = {
        size: parseFloat(getComputedStyle(item.node).fontSize),
        limit: text.endsWith('…') ? text.length : 0,
      };
    });
    return true;
  };

  // Сцена держит свёрстанным только показанный слайд: у остальных нулевая
  // геометрия, и переполнения по ним не видно. Поэтому колода листается её же
  // кнопкой «дальше», и каждый слайд правится, пока он на экране.
  const done = {};
  let sections = [], stage = null;

  const step = (left) => {
    sections.forEach((section, index) => {
      if (!done[index] && settle(section, index)) done[index] = true;
    });
    if (left && stage) {
      stage.next();
      setTimeout(() => step(left - 1), 300);
      return;
    }
    const holder = document.createElement('div');
    holder.id = 'sd-reflow';
    holder.textContent = JSON.stringify(report);
    document.body.appendChild(holder);
  };

  window.__sdReady(() => {
    // Появление слайда идёт с прозрачностью и сдвигом. Прозрачное наш отбор
    // пропускает, поэтому на время подгонки анимации выключаются: нам нужна
    // конечная вёрстка, а не её первый кадр.
    const style = document.createElement('style');
    style.textContent = '[data-anim]{animation:none!important;opacity:1!important;'
                      + 'transform:none!important;filter:none!important;}';
    document.head.appendChild(style);

    sections = window.__sdSections();
    stage = [...document.querySelectorAll('*')].find(
      (node) => typeof node.next === 'function' && typeof node.goTo === 'function');
    step(sections.length);
  });
})();
"""

DUMP_RE = re.compile(r'<div id="sd-reflow">(.*?)</div>', re.S)


@dataclass
class Fix:
    """Что вёрстка велела сделать с одной надписью."""

    slide: int
    path: str
    size: float
    limit: int                                   # 0 — резать не нужно


def measure(deck_path: str | Path, browser: str, width: int = 1920,
            height: int = 1080, timeout: int = 240) -> list[Fix]:
    """Прогоняет колоду через вёрстку и возвращает правки. Пусто — всё влезло."""
    from .export import serve

    deck_path = Path(deck_path).resolve()
    script = REFLOW_JS % {"floor": MIN_FONT_PX, "step": STEP, "rounds": MAX_ROUNDS}
    probe = variant(deck_path, script, "reflow")
    try:
        with serve(deck_path.parent) as base:
            completed = subprocess.run([
                browser, "--headless=new", "--disable-gpu", "--no-first-run",
                "--no-default-browser-check", "--hide-scrollbars",
                "--force-device-scale-factor=1",
                f"--window-size={width},{height}",
                "--virtual-time-budget=20000", "--dump-dom",
                f"{base}/{probe.name}?_snthumb=1",
            ], capture_output=True, timeout=timeout)
        html = completed.stdout.decode("utf-8", "replace")
    finally:
        probe.unlink(missing_ok=True)

    found = DUMP_RE.search(html)
    if not found:
        return []
    try:
        payload = json.loads(_unescape(found.group(1)))
    except json.JSONDecodeError:
        return []

    fixes: list[Fix] = []
    for key, value in payload.items():
        slide, _, path = key.partition(":")
        if not slide.isdigit():
            continue
        fixes.append(Fix(slide=int(slide), path=path,
                         size=float(value.get("size") or 0),
                         limit=int(value.get("limit") or 0)))
    return fixes


def apply(sections: list[etree._Element], fixes: list[Fix]) -> tuple[int, int]:
    """Вносит правки вёрстки в разметку. Возвращает «ужато, урезано»."""
    from .build import _cut, _set_font, _set_text
    from .parse import _node_at

    shrunk = trimmed = 0
    for fix in fixes:
        if not 0 <= fix.slide < len(sections):
            continue
        node = _node_at(sections[fix.slide], fix.path)
        if node is None:
            continue
        if fix.size:
            _set_font(node, round(fix.size, 1))
            shrunk += 1
        if fix.limit:
            text = (node.text or "").strip()
            if len(text) > fix.limit:
                _set_text(node, _cut(text, fix.limit))
                trimmed += 1
    return shrunk, trimmed


def _unescape(text: str) -> str:
    return (text.replace("&quot;", '"').replace("&lt;", "<")
            .replace("&gt;", ">").replace("&#39;", "'").replace("&amp;", "&"))
