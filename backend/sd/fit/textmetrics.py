"""Метрики текста по реальным файлам шрифтов.

Ёмкость слота нельзя оценивать «на глаз»: у кириллицы средняя ширина знака
заметно больше латиницы, а у шрифтов шаблона она своя. Поэтому ширину строки
считаем по таблицам `cmap`/`hmtx` настоящего файла шрифта — тогда и лимит
символов для LLM, и решение «влезает / не влезает» опираются на факт.

Если шрифта шаблона в системе нет (обычная ситуация на чужой машине),
подставляем метрически совместимый и честно записываем это в отчёт.
"""

from __future__ import annotations

import json
import os
from dataclasses import dataclass
from functools import lru_cache
from pathlib import Path

from fontTools.ttLib import TTCollection, TTFont

from ..ooxml.ns import EMU_PER_PT

# Метрически совместимые замены: ширины знаков совпадают, вёрстка не едет.
SUBSTITUTES = {
    "calibri": ["carlito", "segoe ui", "arial", "dejavu sans"],
    "cambria": ["caladea", "georgia", "times new roman", "dejavu serif"],
    "arial": ["liberation sans", "helvetica", "segoe ui", "dejavu sans"],
    "helvetica": ["arial", "liberation sans", "dejavu sans"],
    "times new roman": ["liberation serif", "georgia", "dejavu serif"],
    "courier new": ["liberation mono", "consolas", "dejavu sans mono"],
    "segoe ui": ["calibri", "arial", "dejavu sans"],
}
FALLBACK_CHAIN = ["segoe ui", "arial", "calibri", "tahoma", "verdana", "dejavu sans"]

FONT_DIRS = [
    Path(os.environ.get("WINDIR", r"C:\Windows")) / "Fonts",
    Path(os.environ.get("LOCALAPPDATA", "")) / "Microsoft" / "Windows" / "Fonts",
    Path("/usr/share/fonts"),
    Path("/usr/local/share/fonts"),
    Path.home() / ".fonts",
]
CACHE_PATH = Path(__file__).resolve().parents[3] / ".cache" / "fonts.json"

# Строки для оценки средней ширины знака: кириллица шире латиницы примерно на 5 %.
SAMPLE_RU = "в и на с по для от к из что это как рабочий процесс данные система"
SAMPLE_EN = "the and for with from that this data system process report value"


@dataclass(frozen=True)
class FontFile:
    path: str
    family: str
    bold: bool
    italic: bool
    index: int = 0


def _read_names(font: TTFont) -> tuple[str, str] | None:
    try:
        table = font["name"]
    except (KeyError, AssertionError):
        return None
    family = subfamily = ""
    for record in table.names:
        if record.nameID not in (1, 2, 16, 17):
            continue
        try:
            value = record.toUnicode()
        except UnicodeDecodeError:
            continue
        if record.nameID in (1, 16) and not family:
            family = value
        elif record.nameID in (2, 17) and not subfamily:
            subfamily = value
    return (family, subfamily) if family else None


def _scan_file(path: Path) -> list[FontFile]:
    found: list[FontFile] = []
    container = None
    try:
        if path.suffix.lower() == ".ttc":
            # У коллекции один файловый дескриптор на все шрифты: закрывать
            # каждый отдельно нельзя — остальные останутся без файла.
            container = TTCollection(str(path), lazy=True)
            fonts = list(container.fonts)
        else:
            container = TTFont(str(path), lazy=True, fontNumber=0)
            fonts = [container]

        for index, font in enumerate(fonts):
            names = _read_names(font)
            if names is None:
                continue
            family, subfamily = names
            lowered = subfamily.lower()
            found.append(FontFile(str(path), family.lower().strip(),
                                  "bold" in lowered,
                                  "italic" in lowered or "oblique" in lowered,
                                  index))
    except Exception:
        return found
    finally:
        if container is not None:
            try:
                container.close()
            except Exception:
                pass
    return found


def _build_index() -> dict[str, list[dict]]:
    index: dict[str, list[dict]] = {}
    for directory in FONT_DIRS:
        if not directory.exists():
            continue
        for path in directory.rglob("*"):
            if path.suffix.lower() not in (".ttf", ".ttc", ".otf"):
                continue
            for entry in _scan_file(path):
                index.setdefault(entry.family, []).append(vars(entry))
    return index


@lru_cache(maxsize=1)
def font_index() -> dict[str, list[dict]]:
    """Карта «семейство -> файлы». Строится один раз и кешируется на диск."""
    if CACHE_PATH.exists():
        try:
            data = json.loads(CACHE_PATH.read_text(encoding="utf-8"))
            if data.get("families"):
                return data["families"]
        except (json.JSONDecodeError, OSError):
            pass

    families = _build_index()
    try:
        CACHE_PATH.parent.mkdir(parents=True, exist_ok=True)
        CACHE_PATH.write_text(json.dumps({"families": families}, ensure_ascii=False),
                              encoding="utf-8")
    except OSError:
        pass
    return families


def resolve_font_file(family: str, bold: bool = False,
                      italic: bool = False) -> tuple[FontFile | None, str]:
    """Файл шрифта и пометка о подстановке."""
    index = font_index()
    wanted = (family or "").lower().strip()

    candidates = [wanted]
    candidates += SUBSTITUTES.get(wanted, [])
    candidates += FALLBACK_CHAIN

    for position, name in enumerate(candidates):
        entries = index.get(name)
        if not entries:
            continue
        best = min(entries, key=lambda entry: (entry["bold"] != bold,
                                               entry["italic"] != italic))
        note = "" if position == 0 else f"подстановка: {family} → {best['family']}"
        return FontFile(**best), note
    return None, f"шрифт {family!r} не найден и подстановка не подобрана"


class FontMetrics:
    """Ширины знаков одного начертания в долях кегля."""

    def __init__(self, font_file: FontFile | None, note: str = ""):
        self.file = font_file
        self.note = note
        self._widths: dict[int, float] = {}
        self._cmap: dict[int, str] | None = None
        self._font: TTFont | None = None
        self.units_per_em = 1000
        self.default_width = 0.5

        if font_file is None:
            return
        try:
            if font_file.path.lower().endswith(".ttc"):
                self._font = TTCollection(font_file.path, lazy=True).fonts[font_file.index]
            else:
                self._font = TTFont(font_file.path, lazy=True, fontNumber=font_file.index)
            self.units_per_em = self._font["head"].unitsPerEm or 1000
            self._cmap = self._font.getBestCmap()
            hmtx = self._font["hmtx"]
            space = self._cmap.get(ord(" ")) if self._cmap else None
            if space:
                self.default_width = hmtx[space][0] / self.units_per_em
        except Exception:
            self._font = None

    def char_width(self, char: str) -> float:
        code = ord(char)
        if code in self._widths:
            return self._widths[code]
        width = self.default_width
        if self._font is not None and self._cmap is not None:
            glyph = self._cmap.get(code)
            if glyph is not None:
                try:
                    width = self._font["hmtx"][glyph][0] / self.units_per_em
                except (KeyError, TypeError):
                    width = self.default_width
        self._widths[code] = width
        return width

    def text_width(self, text: str, size_pt: float) -> float:
        """Ширина строки в пунктах (без кернинга — расхождение с PowerPoint ~1 %)."""
        return sum(self.char_width(char) for char in text) * size_pt

    def average_width(self, size_pt: float, sample: str = SAMPLE_RU) -> float:
        return self.text_width(sample, size_pt) / len(sample)


@lru_cache(maxsize=256)
def metrics_for(family: str, bold: bool = False, italic: bool = False) -> FontMetrics:
    font_file, note = resolve_font_file(family, bold, italic)
    return FontMetrics(font_file, note)


# --- перенос строк и ёмкость ------------------------------------------------

def wrap_lines(text: str, width_pt: float, metrics: FontMetrics, size_pt: float,
               caps: str = "none") -> list[str]:
    """Жадный перенос по словам — так же, как это делает PowerPoint."""
    if width_pt <= 0 or not text:
        return [text] if text else []
    if caps == "all":
        text = text.upper()

    lines: list[str] = []
    for hard_line in text.split("\n"):
        current = ""
        for word in hard_line.split(" "):
            candidate = f"{current} {word}".strip()
            if current and metrics.text_width(candidate, size_pt) > width_pt:
                lines.append(current)
                current = word
            else:
                current = candidate
        lines.append(current)
    return lines


def line_height_pt(size_pt: float, line_spacing: float | None) -> float:
    """Высота строки. `line_spacing` < 0 означает точный кегль в пунктах."""
    if line_spacing is not None and line_spacing < 0:
        return -line_spacing
    return size_pt * 1.2 * (line_spacing if line_spacing else 1.0)


def fits(text: str, width_emu: int, height_emu: int, metrics: FontMetrics,
         size_pt: float, line_spacing: float | None = None, caps: str = "none",
         insets: tuple[int, int, int, int] = (91440, 45720, 91440, 45720)) -> tuple[bool, int]:
    """Влезает ли текст в бокс. Возвращает (влезает, сколько строк вышло)."""
    left, top, right, bottom = insets
    usable_w = (width_emu - left - right) / EMU_PER_PT
    usable_h = (height_emu - top - bottom) / EMU_PER_PT
    lines = wrap_lines(text, usable_w, metrics, size_pt, caps)
    needed = len(lines) * line_height_pt(size_pt, line_spacing)
    return needed <= usable_h + 0.5, len(lines)


def capacity_chars(width_emu: int, height_emu: int, metrics: FontMetrics, size_pt: float,
                   line_spacing: float | None = None, caps: str = "none",
                   sample: str = SAMPLE_RU,
                   insets: tuple[int, int, int, int] = (91440, 45720, 91440, 45720)
                   ) -> tuple[int, int]:
    """Сколько знаков и строк помещается в бокс при данном стиле.

    Оценка по средней ширине знака на языке контента, а не по «магическим» 60
    символам: у Trebuchet 20 pt и Calibri 11 pt ёмкость отличается в разы.
    """
    if size_pt <= 0:
        return 0, 0
    left, top, right, bottom = insets
    usable_w = max(0.0, (width_emu - left - right) / EMU_PER_PT)
    usable_h = max(0.0, (height_emu - top - bottom) / EMU_PER_PT)

    average = metrics.average_width(size_pt, sample) or (size_pt * 0.5)
    if caps == "all":
        average *= 1.12                       # прописные шире строчных
    per_line = int(usable_w // average) if average else 0
    lines = max(1, int(usable_h // line_height_pt(size_pt, line_spacing)))
    return max(0, per_line * lines), lines
