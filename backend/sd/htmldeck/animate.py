"""Анимация слайдов собранной колоды.

Правило движка шаблонов: базовым стилем остаётся **конечный** вид элемента, а
анимация проигрывается *из* скрытого состояния. Тогда печать в PDF и режим
`prefers-reduced-motion` показывают готовый слайд, а не пустой — анимация может
не проиграть, и это не должно стоить зрителю содержания.

Всё гейтится на `[data-deck-active]`: появление начинается, когда слайд
показан, а не при загрузке страницы. Классов шаблоны не используют, поэтому
роли размечаются атрибутами `data-anim`, а очередь — переменной `--i`.
"""

from __future__ import annotations

import re

from lxml import etree

from .parse import Pattern, _children, _node_at

# Очередь появления для одиночных слотов: шапка слайда раньше содержания.
ORDER = {"kicker": 0, "title": 1, "body": 2, "item": 2, "quote": 2,
         "metric_value": 2, "metric_label": 2}

ANIM_CSS = """
<style>
/* Анимация появления. Базовый стиль — конечный вид: если анимация не
   проиграет (печать, prefers-reduced-motion, старый браузер), слайд всё равно
   показан целиком. */
@media (prefers-reduced-motion: no-preference) {
  @keyframes dc-rise { from { opacity: 0; transform: translateY(28px); } }
  @keyframes dc-title { from { opacity: 0; transform: translateY(38px); filter: blur(9px); } }
  @keyframes dc-kicker { from { opacity: 0; letter-spacing: .28em; } }
  @keyframes dc-card { from { opacity: 0; transform: translateY(34px) scale(.965); } }
  @keyframes dc-draw { from { opacity: 0; transform: scale(.86) rotate(-7deg); } }
  @keyframes dc-wipe { from { opacity: 0; clip-path: inset(0 100% 0 0); } }

  [data-deck-active] [data-anim] { animation-fill-mode: both; }
  [data-deck-active] [data-anim="kicker"] {
    animation: dc-kicker .55s cubic-bezier(.2,.8,.2,1);
    animation-delay: calc(var(--i, 0) * 70ms);
  }
  [data-deck-active] [data-anim="title"] {
    animation: dc-title .72s cubic-bezier(.2,.8,.2,1);
    animation-delay: calc(80ms + var(--i, 0) * 70ms);
  }
  [data-deck-active] [data-anim="text"] {
    animation: dc-rise .6s cubic-bezier(.2,.8,.2,1);
    animation-delay: calc(180ms + var(--i, 0) * 70ms);
  }
  [data-deck-active] [data-anim="card"] {
    animation: dc-card .66s cubic-bezier(.2,.8,.2,1);
    animation-delay: calc(240ms + var(--i, 0) * 110ms);
    transform-origin: center top;
  }
  [data-deck-active] [data-anim="figure"] {
    animation: dc-draw .9s cubic-bezier(.2,.8,.2,1);
    animation-delay: calc(200ms + var(--i, 0) * 90ms);
    transform-origin: center;
    transform-box: fill-box;
  }
  [data-deck-active] [data-anim="rule"] {
    animation: dc-wipe .7s cubic-bezier(.2,.8,.2,1);
    animation-delay: calc(160ms + var(--i, 0) * 80ms);
  }
}

/* Печать не ждёт: браузер снимает страницу когда угодно и может поймать
   элемент в начальной фазе — то есть невидимым. В PDF анимации не нужны
   вовсе, поэтому здесь их просто нет. */
@media print {
  [data-anim] { animation: none !important; }
}
</style>
""".strip()

ANIM_JS = """
<script>
/* Числа на показателях набегают от нуля. Значение в разметке — конечное:
   без скрипта и при печати виден готовый результат. */
(function () {
  var motion = window.matchMedia && window.matchMedia('(prefers-reduced-motion: reduce)');
  if (motion && motion.matches) return;

  function parse(text) {
    /* Пробел-разделитель разрядов забираем только между цифрами: иначе из
       «100 %» пропадёт пробел перед знаком процента. */
    var match = String(text).match(
      /^(\\D*?)(\\d+(?:[\\s\\u00a0]\\d{3})*(?:[.,]\\d+)?)(.*)$/s);
    if (!match) return null;
    var raw = match[2].replace(/[\\s\\u00a0]/g, '').replace(',', '.');
    var value = parseFloat(raw);
    if (!isFinite(value)) return null;
    var decimals = (raw.split('.')[1] || '').length;
    var grouped = /[\\s\\u00a0]/.test(match[2]);
    return { prefix: match[1], value: value, suffix: match[3],
             decimals: decimals, grouped: grouped };
  }

  function show(node, parsed, value) {
    var text = value.toFixed(parsed.decimals);
    if (parsed.grouped) text = text.replace(/\\B(?=(\\d{3})+(?!\\d))/g, '\\u00a0');
    if (parsed.decimals) text = text.replace('.', ',');
    node.textContent = parsed.prefix + text + parsed.suffix;
  }

  function run(node) {
    if (node.dataset.dcCounted) return;
    var parsed = parse(node.dataset.dcValue || node.textContent);
    if (!parsed) return;
    node.dataset.dcCounted = '1';
    node.dataset.dcValue = parsed.prefix + parsed.value + parsed.suffix;
    var start = null, duration = 900, delay = 260;
    function step(now) {
      if (start === null) start = now;
      var passed = now - start - delay;
      if (passed < 0) return requestAnimationFrame(step);
      var progress = Math.min(1, passed / duration);
      var eased = 1 - Math.pow(1 - progress, 3);
      show(node, parsed, parsed.value * eased);
      if (progress < 1) requestAnimationFrame(step);
      else show(node, parsed, parsed.value);
    }
    requestAnimationFrame(step);
  }

  function sweep() {
    var active = document.querySelectorAll('[data-deck-active] [data-anim-count]');
    for (var i = 0; i < active.length; i++) run(active[i]);
  }

  var observer = new MutationObserver(sweep);
  observer.observe(document.documentElement,
                   { attributes: true, subtree: true, attributeFilter: ['data-deck-active'] });
  document.addEventListener('DOMContentLoaded', sweep);
  sweep();
})();
</script>
""".strip()

# Числа, которые имеет смысл «накручивать» от нуля.
COUNTABLE_RE = re.compile(r"\d")


def decorate(section: etree._Element, pattern: Pattern) -> int:
    """Размечает элементы секции ролями анимации. Возвращает число помеченных.

    Разметка идёт по уже найденным слотам и корням карточек — то есть по той же
    структуре, по которой шла подстановка текста. Ничего нового в разметку не
    добавляется: только атрибуты.
    """
    marked = 0
    carded = set()

    for key, path in sorted(pattern.group_roots.items(), key=lambda item: item[0]):
        order = int(key.rsplit("#", 1)[-1])
        node = _node_at(section, path)
        if node is None:
            continue
        _mark(node, "card", order)
        carded.add(path)
        marked += 1

    for slot in pattern.slots:
        if slot.group:
            continue
        node = _node_at(section, slot.path)
        if node is None or node.get("data-anim"):
            continue
        role = ("title" if slot.role == "title"
                else "kicker" if slot.role == "kicker" else "text")
        _mark(node, role, ORDER.get(slot.role, 2))
        marked += 1

    for slot in pattern.slots:
        if slot.role != "metric_value":
            continue
        node = _node_at(section, slot.path)
        if node is not None and COUNTABLE_RE.search(node.text or ""):
            node.set("data-anim-count", "")

    for index, figure in enumerate(_figures(section)):
        if figure.get("data-anim"):
            continue
        _mark(figure, "figure", index)
        marked += 1

    _renumber(section)
    return marked


def _renumber(section: etree._Element) -> None:
    """Выстраивает очередь появления по порядку чтения.

    Номер приходил из номера карточки внутри её группы, а групп в макете
    бывает несколько — и тогда две разные карточки получали одинаковую
    задержку и появлялись одновременно. Порядок в разметке совпадает с
    порядком чтения, поэтому нумеруем по нему.
    """
    counters: dict = {}
    for node in section.iter():
        role = node.get("data-anim") if isinstance(node.tag, str) else None
        if role not in ("card", "figure"):
            continue
        index = counters.get(role, 0)
        counters[role] = index + 1
        style = re.sub(r"--i:\s*\d+;?\s*", "", node.get("style") or "")
        node.set("style", f"--i:{index}; {style}".strip())


def _figures(section: etree._Element) -> list[etree._Element]:
    """Векторные фигуры верхнего уровня — их анимируем целиком, а не по частям."""
    found: list = []

    def walk(node: etree._Element) -> None:
        for child in _children(node):
            tag = child.tag if isinstance(child.tag, str) else ""
            if tag.endswith("svg"):
                found.append(child)
                continue
            walk(child)

    walk(section)
    return found


def _mark(node: etree._Element, role: str, order: int) -> None:
    node.set("data-anim", role)
    style = node.get("style") or ""
    if "--i:" not in style:
        node.set("style", f"--i:{order}; {style}".strip())
