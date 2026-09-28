"""Снятие геометрии и стиля надписей со слайдов HTML-колоды.

Экспорт в PowerPoint снимком отдаёт точную картинку, но текст в нём править
нельзя — а править приходится почти всегда. Чтобы слайд остался редактируемым,
надписи нужно перенести настоящими текстовыми полями поверх фона, и для этого
надо знать, где именно и каким начертанием они стоят.

Считает это сам браузер: он единственный, кто знает результат вёрстки. Один
запуск на всю колоду — скрытые слайды остаются в разметке и сохраняют
геометрию, поэтому измерить можно всё сразу.

Координаты снимаются долями от площади слайда, а не пикселями. Окно браузера,
масштаб сцены и размер снимка тогда перестают иметь значение: доля переносится
в любой размер кадра без пересчётов и накопленной погрешности.
"""

from __future__ import annotations

import json
import re
import subprocess
from dataclasses import dataclass
from pathlib import Path

# Скрипт исполняется в браузере. Одна и та же разметка обходится дважды: при
# измерении и при съёмке фона, поэтому логика отбора надписей общая — иначе
# спрячется не то, что перенесено.
COLLECT_JS = """
window.__sdSections = () => [...document.querySelectorAll('section')];

window.__sdItems = function (section) {
  const base = section.getBoundingClientRect();
  if (!base.width || !base.height) return [];
  // Сцена вписывает слайд в окно масштабированием. Положения берём от видимой
  // рамки — там масштаб сокращается сам. А кегль масштабом не затронут, и
  // мерить его надо от неотмасштабированной высоты слайда.
  const own_height = section.offsetHeight || base.height;

  // Берём только собственный текст узла: иначе абзац приедет и сам по себе,
  // и ещё раз внутри каждого родителя.
  const own = (node) => [...node.childNodes]
    .filter((child) => child.nodeType === 3)
    .map((child) => child.textContent).join('').replace(/\s+/g, ' ').trim();

  const alpha = (color) => {
    const parts = (color || '').match(/[\d.]+/g) || [];
    return parts.length > 3 ? parseFloat(parts[3]) : 1;
  };

  const items = [];
  section.querySelectorAll('*').forEach((node) => {
    const text = own(node);
    if (!text) return;
    // Подписи внутри SVG выключены намеренно: они держатся на своих системах
    // координат и text-anchor, и текстовым полем их не повторить. Пусть
    // остаются частью картинки — диаграммы важнее правок.
    if (node.ownerSVGElement || node.tagName === 'svg') return;

    const style = getComputedStyle(node);
    if (style.visibility === 'hidden' || style.display === 'none') return;
    if (parseFloat(style.opacity) < 0.1) return;
    // Прозрачный цвет — это текст, залитый градиентом через background-clip.
    // Перенести его нечем: в поле он стал бы невидимым.
    if (alpha(style.color) < 0.1) return;

    const rect = node.getBoundingClientRect();
    if (!rect.width || !rect.height) return;
    const line = parseFloat(style.lineHeight);

    items.push({
      text: text,
      x: (rect.left - base.left) / base.width,
      y: (rect.top - base.top) / base.height,
      w: rect.width / base.width,
      h: rect.height / base.height,
      size: parseFloat(style.fontSize) / own_height,
      line: isNaN(line) ? 0 : line / own_height,
      family: (style.fontFamily || '').split(',')[0].replace(/['\"]/g, '').trim(),
      weight: parseInt(style.fontWeight, 10) || 400,
      italic: style.fontStyle === 'italic',
      color: style.color,
      align: style.textAlign,
      upper: style.textTransform === 'uppercase',
      node: node,
    });
  });
  return items;
};

// Адрес узла внутри слайда — номерами детей, как в слотах шаблона. По нему
// измеренное возвращается обратно в разметку.
window.__sdPath = function (node, section) {
  const steps = [];
  while (node && node !== section) {
    const parent = node.parentNode;
    if (!parent || !parent.children) return null;
    steps.unshift([...parent.children].indexOf(node));
    node = parent;
  }
  return steps.join('/');
};

// Загрузка шрифтов меняет ширины и переносы: до неё мерить бессмысленно.
window.__sdReady = function (next) {
  const wait = document.fonts && document.fonts.ready
    ? document.fonts.ready : Promise.resolve();
  wait.then(() => setTimeout(next, 400));
};
"""

# Сцена держит свёрстанным только показанный слайд — у остальных нулевая
# геометрия, а `location.hash` она читает лишь при загрузке. Поэтому колода
# листается её же кнопкой «дальше», и на каждом шаге меряется тот слайд,
# который сейчас на экране.
MEASURE_JS = COLLECT_JS + """
(() => {
  const collected = {};
  // Список слайдов берётся только после готовности страницы: сцена собирает
  // свои разделы сама, а те, что лежали в разметке, к тому времени уже не в
  // документе — мерить по ним нечего.
  let sections = [];
  let stage = null;

  const sweep = () => {
    // Слайд считается свёрстанным, если у него есть площадь. Иногда сцена
    // держит развёрнутыми сразу несколько — тогда за проход снимутся все.
    sections.forEach((section, index) => {
      if (index in collected) return;
      const items = window.__sdItems(section).map(({ node, ...rest }) => rest);
      if (items.length) collected[index] = items;
    });
  };

  const finish = () => {
    const data = sections.map((_, index) => ({
      index: index, items: collected[index] || [],
    }));
    const holder = document.createElement('div');
    holder.id = 'sd-measurements';
    holder.textContent = JSON.stringify(data);
    document.body.appendChild(holder);
  };

  const step = (left) => {
    sweep();
    if (!left || !stage) { finish(); return; }
    stage.next();
    // Слайд меняется с анимацией: мерить надо по её окончании, иначе в
    // размеры попадёт промежуточный кадр.
    setTimeout(() => step(left - 1), 700);
  };
  window.__sdReady(() => {
    sections = window.__sdSections();
    stage = [...document.querySelectorAll('*')].find(
      (node) => typeof node.next === 'function' && typeof node.goTo === 'function');
    step(sections.length);
  });
})();
"""

# Прячем не элемент, а только глифы: фон, рамка и тень часто заданы на том же
# узле, что и текст, и `visibility:hidden` унёс бы их вместе с ним.
HIDE_JS = COLLECT_JS + """
(() => {
  const hide = () => {
    window.__sdSections().forEach((section) => {
      window.__sdItems(section).forEach((item) => {
        item.node.style.setProperty('color', 'transparent', 'important');
        item.node.style.setProperty('-webkit-text-fill-color', 'transparent', 'important');
        item.node.style.setProperty('text-shadow', 'none', 'important');
      });
    });
  };
  // Сцена доверстывает слайд по ходу анимации, поэтому прячем не один раз,
  // а пока идёт съёмка.
  window.__sdReady(() => { hide(); setInterval(hide, 150); });
})();
"""


DUMP_RE = re.compile(r'<div id="sd-measurements">(.*?)</div>', re.S)
FIELDS = ("text", "x", "y", "w", "h", "size", "line", "family", "weight",
          "italic", "color", "align", "upper")


@dataclass
class TextBox:
    """Надпись слайда. Все размеры — доли от ширины и высоты слайда."""

    text: str
    x: float
    y: float
    w: float
    h: float
    size: float
    line: float
    family: str
    weight: int
    italic: bool
    color: str
    align: str
    upper: bool


@dataclass
class SlideText:
    index: int
    items: list[TextBox]


def variant(deck_path: Path, script: str, suffix: str) -> Path:
    """Копия колоды с добавленным скриптом — рядом, чтобы движок нашёлся."""
    source = deck_path.read_text(encoding="utf-8")
    tag = f"<script>{script}</script>"
    injected = (source.replace("</body>", f"{tag}\n</body>")
                if "</body>" in source else source + tag)
    target = deck_path.with_name(f"{deck_path.stem}.{suffix}.html")
    target.write_text(injected, encoding="utf-8")
    return target


def measure(deck_path: str | Path, browser: str, width: int = 1920,
            height: int = 1080, timeout: int = 180) -> list[SlideText]:
    """Геометрия и стиль всех надписей колоды. Пустой список — если не вышло.

    Размер окна должен совпадать с размером снимка: вёрстка слайда зависит от
    ширины кадра, и измеренное в другом окне легло бы мимо фона.
    """
    from .export import serve

    deck_path = Path(deck_path).resolve()
    probe = variant(deck_path, MEASURE_JS, "measure")
    try:
        with serve(deck_path.parent) as base:
            completed = subprocess.run([
                browser, "--headless=new", "--disable-gpu", "--no-first-run",
                "--no-default-browser-check", "--hide-scrollbars",
                "--force-device-scale-factor=1",
                f"--window-size={width},{height}",
                "--virtual-time-budget=15000", "--dump-dom",
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

    slides: list[SlideText] = []
    for slide in payload:
        try:
            items = [TextBox(**{key: item[key] for key in FIELDS})
                     for item in slide.get("items", [])]
        except KeyError:
            return []
        slides.append(SlideText(index=slide["index"], items=items))
    return slides


def _unescape(text: str) -> str:
    """Обратно из HTML-экранирования, в котором браузер отдал JSON."""
    return (text.replace("&quot;", '"').replace("&lt;", "<")
            .replace("&gt;", ">").replace("&#39;", "'").replace("&amp;", "&"))


def parse_rgb(value: str) -> tuple[int, int, int]:
    numbers = [int(float(part)) for part in re.findall(r"[\d.]+", value or "")[:3]]
    while len(numbers) < 3:
        numbers.append(0)
    return tuple(min(255, max(0, number)) for number in numbers)  # type: ignore[return-value]
