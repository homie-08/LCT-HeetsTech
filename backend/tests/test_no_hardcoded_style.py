"""Линтер «стиль не зашит» — главное обещание кейса, выраженное проверкой.

Сервис обязан брать оформление из шаблона, а не из своего кода. Проверить это
рассуждением нельзя, поэтому здесь обход AST по модулям, которые принимают
решения о внешнем виде: подбор макета, укладка текста, сборка файла. Находка
HEX-цвета, названия шрифта или абсолютной координаты в EMU роняет тест.

Что разрешено и почему:
- пороги и доли (0.45, 12) — это правила вёрстки, а не оформление: они говорят
  «не мельче половины», но не «синий шрифт Arial»;
- имена ролей и слотов («title», «accent_primary») — словарь, а не значения;
- модули отчётов и отладочных превью: их вид не влияет на презентацию.
"""

from __future__ import annotations

import ast
import re
from pathlib import Path

BACKEND = Path(__file__).resolve().parents[1]

# Модули, принимающие решения об оформлении готовой презентации.
GENERATION = ["sd/compose", "sd/plan", "sd/fit", "sd/htmldeck"]

# Отладочная раскраска превью и стили анимации: на вид презентации не влияют.
EXCLUDED = {"sd/htmldeck/animate.py"}

# Таблица метрически совместимых замен. Названия здесь — не выбор оформления,
# а справочник для измерения: если шаблон просит Calibri, а его нет в системе,
# ширины считаются по Carlito. Шрифт на слайде всё равно приходит из шаблона.
FONT_EXEMPT = {"sd/fit/textmetrics.py"}

HEX_RE = re.compile(r"#(?:[0-9a-fA-F]{3}|[0-9a-fA-F]{6}|[0-9a-fA-F]{8})\b")

# Начертания, которые нельзя называть в коде: шрифт приходит из шаблона.
FONTS = ("arial", "calibri", "times new roman", "helvetica", "segoe ui",
         "verdana", "tahoma", "georgia", "roboto", "montserrat", "onest",
         "geologica", "unbounded", "century gothic", "cambria")

# EMU: 914 400 на дюйм. Любое такое число в коде — вбитая вручную геометрия.
EMU_SUSPECT = 100_000


def _sources() -> list[Path]:
    files: list[Path] = []
    for folder in GENERATION:
        for path in sorted((BACKEND / folder).rglob("*.py")):
            relative = path.relative_to(BACKEND).as_posix()
            if relative not in EXCLUDED:
                files.append(path)
    return files


def _strings(tree: ast.AST) -> list[tuple[int, str]]:
    """Строковые литералы кода без документации: она к делу не относится."""
    docstrings = set()
    for node in ast.walk(tree):
        if isinstance(node, (ast.Module, ast.FunctionDef, ast.AsyncFunctionDef,
                             ast.ClassDef)):
            first = node.body[0] if node.body else None
            if (isinstance(first, ast.Expr) and isinstance(first.value, ast.Constant)
                    and isinstance(first.value.value, str)):
                docstrings.add(id(first.value))

    return [(node.lineno, node.value) for node in ast.walk(tree)
            if isinstance(node, ast.Constant) and isinstance(node.value, str)
            and id(node) not in docstrings]


def test_no_hex_colors_in_generation():
    """Ни одного цвета: палитра целиком приходит из шаблона."""
    findings = []
    for path in _sources():
        tree = ast.parse(path.read_text(encoding="utf-8"))
        for line, value in _strings(tree):
            if HEX_RE.search(value):
                findings.append(f"{path.relative_to(BACKEND)}:{line} — {value[:40]!r}")
    assert not findings, "цвет зашит в код генерации:\n" + "\n".join(findings)


def test_no_font_names_in_generation():
    """Ни одного названия шрифта: типографика тоже из шаблона."""
    findings = []
    for path in _sources():
        if path.relative_to(BACKEND).as_posix() in FONT_EXEMPT:
            continue
        tree = ast.parse(path.read_text(encoding="utf-8"))
        for line, value in _strings(tree):
            lowered = value.lower()
            if any(font in lowered for font in FONTS):
                findings.append(f"{path.relative_to(BACKEND)}:{line} — {value[:40]!r}")
    assert not findings, "шрифт зашит в код генерации:\n" + "\n".join(findings)


def test_no_absolute_coordinates_in_generation():
    """Ни одной абсолютной координаты: геометрия считается от размера слайда."""
    findings = []
    for path in _sources():
        tree = ast.parse(path.read_text(encoding="utf-8"))
        for node in ast.walk(tree):
            if (isinstance(node, ast.Constant) and isinstance(node.value, int)
                    and not isinstance(node.value, bool)
                    and node.value >= EMU_SUSPECT):
                findings.append(f"{path.relative_to(BACKEND)}:{node.lineno} — {node.value}")
    assert not findings, "координата в EMU зашита в код:\n" + "\n".join(findings)


def test_linter_actually_catches_violations():
    """Проверка самого линтера: на подсунутом нарушении он обязан сработать.

    Зелёный тест, который ничего не проверяет, хуже отсутствующего: он создаёт
    ложное спокойствие. Поэтому линтер здесь ловит заведомо плохой код.
    """
    tree = ast.parse('BRAND = "#0077FF"\nFONT = "Arial"\nLEFT = 914400\n')
    strings = [value for _, value in _strings(tree)]
    assert any(HEX_RE.search(value) for value in strings)
    assert any("arial" in value.lower() for value in strings)
    assert any(isinstance(node, ast.Constant) and isinstance(node.value, int)
               and node.value >= EMU_SUSPECT for node in ast.walk(tree))
