"""Экспорт собранной HTML-колоды в PDF.

Печатает браузером — тем же, в котором колода и предназначена для показа.
Свой рендерер писать было бы неправильно: шаблоны опираются на CSS-градиенты,
`clip-path`, SVG и веб-шрифты, и любая самодельная отрисовка отличалась бы от
того, что видит зритель.

Файл отдаётся не с диска, а с временного локального сервера: `file://` ломает
загрузку соседних `support.js` и `deck-stage.js` политикой источника, и колода
приезжает пустой.
"""

from __future__ import annotations

import contextlib
import functools
import http.server
import shutil
import socket
import socketserver
import subprocess
import threading
from dataclasses import dataclass
from pathlib import Path

# Порядок важен: Chrome печатает ближе к тому, что показывает Chrome.
BROWSERS = [
    r"C:\Program Files\Google\Chrome\Application\chrome.exe",
    r"C:\Program Files (x86)\Google\Chrome\Application\chrome.exe",
    r"C:\Program Files\Microsoft\Edge\Application\msedge.exe",
    r"C:\Program Files (x86)\Microsoft\Edge\Application\msedge.exe",
]
COMMANDS = ["chrome", "google-chrome", "chromium", "msedge", "microsoft-edge"]


@dataclass
class ExportResult:
    path: Path
    browser: str
    pages: int = 0
    notes: list[str] = None            # type: ignore[assignment]

    def __post_init__(self) -> None:
        self.notes = self.notes or []


def find_browser() -> str | None:
    """Путь к Chromium-браузеру или None, если печатать нечем."""
    for candidate in BROWSERS:
        if Path(candidate).exists():
            return candidate
    for command in COMMANDS:
        found = shutil.which(command)
        if found:
            return found
    return None


@contextlib.contextmanager
def serve(directory: Path):
    """Временный http-сервер над папкой колоды. Отдаёт базовый URL."""
    with socket.socket() as probe:
        probe.bind(("127.0.0.1", 0))
        port = probe.getsockname()[1]

    handler = functools.partial(_QuietHandler, directory=str(directory))
    server = socketserver.TCPServer(("127.0.0.1", port), handler)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    try:
        yield f"http://127.0.0.1:{port}"
    finally:
        server.shutdown()
        server.server_close()


class _QuietHandler(http.server.SimpleHTTPRequestHandler):
    def log_message(self, *args) -> None:                 # noqa: D401 - гасим лог
        """Сервер живёт секунды и в вывод сборки лезть не должен."""


def to_pdf(deck_path: str | Path, out_path: str | Path,
           browser: str | None = None, timeout: int = 180) -> ExportResult:
    """Печатает колоду в PDF: один слайд — одна страница."""
    deck_path = Path(deck_path).resolve()
    out_path = Path(out_path).resolve()
    out_path.parent.mkdir(parents=True, exist_ok=True)

    executable = browser or find_browser()
    if executable is None:
        raise RuntimeError("не найден Chrome или Edge — печатать в PDF нечем")

    result = ExportResult(path=out_path, browser=Path(executable).name)
    with serve(deck_path.parent) as base:
        url = f"{base}/{deck_path.name}"
        command = [
            executable,
            "--headless=new",
            "--disable-gpu",
            "--no-first-run",
            "--no-default-browser-check",
            "--hide-scrollbars",
            # Веб-шрифты и разметка успевают загрузиться: без этого печатается
            # первый кадр, где текст ещё в подстановочном шрифте.
            "--virtual-time-budget=15000",
            "--run-all-compositor-stages-before-draw",
            "--no-pdf-header-footer",
            f"--print-to-pdf={out_path}",
            url,
        ]
        completed = subprocess.run(command, capture_output=True, timeout=timeout)

    if not out_path.exists() or out_path.stat().st_size == 0:
        message = (completed.stderr or b"").decode("utf-8", "replace").strip()
        raise RuntimeError(f"браузер не отдал PDF: {message[:300]}")

    result.pages = _page_count(out_path)
    return result


def to_images(deck_path: str | Path, out_dir: str | Path, count: int,
              width: int = 1920, height: int = 1080,
              browser: str | None = None, timeout: int = 120,
              hide_text: bool = False) -> list[Path]:
    """Снимает каждый слайд в PNG размером ровно со слайд.

    Движок держит номер слайда в `location.hash`, а `?_snthumb=` убирает
    боковую полосу навигации — иначе она попала бы в кадр.
    """
    deck_path = Path(deck_path).resolve()
    out_dir = Path(out_dir).resolve()
    out_dir.mkdir(parents=True, exist_ok=True)

    executable = browser or find_browser()
    if executable is None:
        raise RuntimeError("не найден Chrome или Edge — снимать слайды нечем")

    # Фон для редактируемого экспорта снимается без надписей: их положат
    # поверх настоящими текстовыми полями.
    page = deck_path
    if hide_text:
        from .textmap import HIDE_JS, variant

        page = variant(deck_path, HIDE_JS, "bg")

    images: list[Path] = []
    try:
      with serve(deck_path.parent) as base:
        for number in range(1, count + 1):
            target = out_dir / f"slide-{number:03d}.png"
            url = f"{base}/{page.name}?_snthumb=1#{number}"
            subprocess.run([
                executable, "--headless=new", "--disable-gpu", "--no-first-run",
                "--no-default-browser-check", "--hide-scrollbars",
                "--force-device-scale-factor=1",
                f"--window-size={width},{height}",
                "--virtual-time-budget=8000",
                "--run-all-compositor-stages-before-draw",
                f"--screenshot={target}", url,
            ], capture_output=True, timeout=timeout)
            if target.exists() and target.stat().st_size:
                images.append(target)
    finally:
        if hide_text and page != deck_path:
            page.unlink(missing_ok=True)
    return images


def to_pptx(deck_path: str | Path, out_path: str | Path, count: int,
            notes: list[str] | None = None, work_dir: str | Path | None = None,
            browser: str | None = None, editable: bool = True) -> ExportResult:
    """Собирает .pptx: оформление — картинкой, текст — настоящими надписями.

    Перенести CSS-градиенты, `clip-path` и SVG в фигуры OOXML без потерь нельзя,
    поэтому оформление слайда уходит фоном-снимком. А вот текст снимком быть не
    должен: презентацию почти всегда правят перед выступлением. Надписи
    измеряются в браузере и переносятся текстовыми полями поверх фона — с их
    настоящим положением, кеглем, цветом и выключкой.

    Если измерить не удалось (нет браузера, чужая вёрстка), остаётся прежний
    путь — цельный снимок и текст в заметках. Хуже, но не пусто.
    """
    from pptx import Presentation
    from pptx.util import Emu, Inches

    deck_path = Path(deck_path).resolve()
    out_path = Path(out_path).resolve()
    out_path.parent.mkdir(parents=True, exist_ok=True)
    work_dir = Path(work_dir or out_path.parent / "_slides")
    executable = browser or find_browser()

    layout: list = []
    if editable and executable:
        from .textmap import measure

        try:
            layout = measure(deck_path, executable)
        except Exception:                       # измерение — улучшение, не основа
            layout = []

    # Фон снимается без текста: иначе надписи будут и на картинке, и поверх неё.
    images = to_images(deck_path, work_dir, count, browser=browser,
                       hide_text=bool(layout))
    if not images:
        raise RuntimeError("не удалось снять ни одного слайда")

    presentation = Presentation()
    presentation.slide_width = Inches(13.333)
    presentation.slide_height = Inches(7.5)
    blank = presentation.slide_layouts[6]
    placed = 0

    for index, image in enumerate(images):
        slide = presentation.slides.add_slide(blank)
        slide.shapes.add_picture(str(image), Emu(0), Emu(0),
                                 width=presentation.slide_width,
                                 height=presentation.slide_height)
        if index < len(layout):
            placed += _add_text_boxes(slide, layout[index], presentation)
        if notes and index < len(notes) and notes[index].strip():
            slide.notes_slide.notes_text_frame.text = notes[index].strip()

    presentation.save(str(out_path))
    result = ExportResult(path=out_path, browser=Path(executable or "").name)
    result.pages = len(images)
    if len(images) < count:
        result.notes.append(f"снято {len(images)} слайдов из {count}")
    if placed:
        result.notes.append(f"текст перенесён редактируемым: {placed} надписей")
    else:
        result.notes.append("текст остался на картинке — измерить надписи не вышло")
    return result


ALIGNMENT = {"center": "CENTER", "right": "RIGHT", "justify": "JUSTIFY",
             "start": "LEFT", "end": "RIGHT", "left": "LEFT"}
# Поле внутри надписи. Браузер текст к краю рамки не отодвигает, PowerPoint —
# отодвигает, поэтому собственные отступы обнуляем, а рамку раздвигаем на
# запас: перенос строк у него чуть другой, и без запаса срывается последнее
# слово.
SLACK = 45720                                            # 0.05 дюйма в EMU


def _add_text_boxes(slide, page, presentation) -> int:
    """Кладёт надписи слайда настоящими текстовыми полями поверх фона."""
    from pptx.dml.color import RGBColor
    from pptx.enum.text import MSO_ANCHOR, PP_ALIGN
    from pptx.util import Emu, Pt

    from .textmap import parse_rgb

    width = presentation.slide_width
    height = presentation.slide_height
    points = height / 12700                              # высота слайда в пунктах

    added = 0
    for item in page.items:
        left = int(item.x * width) - SLACK
        top = int(item.y * height) - SLACK // 2
        box = slide.shapes.add_textbox(
            Emu(max(0, left)), Emu(max(0, top)),
            Emu(int(item.w * width) + 2 * SLACK), Emu(int(item.h * height) + SLACK))
        frame = box.text_frame
        frame.word_wrap = True
        frame.margin_left = frame.margin_right = Emu(SLACK)
        frame.margin_top = frame.margin_bottom = Emu(0)
        frame.vertical_anchor = MSO_ANCHOR.TOP

        paragraph = frame.paragraphs[0]
        paragraph.alignment = getattr(PP_ALIGN, ALIGNMENT.get(item.align, "LEFT"))
        if item.line and item.size:
            paragraph.line_spacing = round(item.line / item.size, 2)
        run = paragraph.add_run()
        run.text = item.text.upper() if item.upper else item.text
        run.font.size = Pt(max(6.0, round(item.size * points, 1)))
        run.font.bold = item.weight >= 600
        run.font.italic = item.italic
        if item.family:
            run.font.name = item.family
        red, green, blue = parse_rgb(item.color)
        run.font.color.rgb = RGBColor(red, green, blue)
        added += 1
    return added


def _page_count(path: Path) -> int:
    """Число страниц — по счётчику в самом PDF, без сторонних библиотек."""
    data = path.read_bytes()
    marker = data.rfind(b"/Count")
    if marker < 0:
        return data.count(b"/Type /Page") or data.count(b"/Type/Page")
    tail = data[marker + 6:marker + 20].split(b"/")[0].strip()
    digits = b"".join(character.to_bytes(1, "big") for character in tail
                      if 48 <= character <= 57)
    return int(digits) if digits else 0
