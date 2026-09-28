"""Аудит готовой презентации по чек-листу заказчика (ТЗ, Приложение 1).

Проверки двух родов, и они честно разделены:

- **детерминированные** — смотрят на то, что уже есть в файле: координаты,
  размеры, кегли, цвета, текст. На одном и том же файле дают один и тот же
  ответ. Их можно гонять в тестах.
- **контекстуальные** — про смысл: заголовок содержит вывод или называет
  тему, связаны ли соседние слайды. Их задаёт модель, и на повторе ответ может
  отличаться; поэтому они помечены и никогда не считаются ошибкой сборки.

Аудит — часть конвейера, а не внешняя проверка: он идёт после сборки, его
находки ложатся в отчёт с номером слайда, и часть из них можно исправить
пересборкой — какие именно, решает пользователь.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from pathlib import Path

from ..content.model import ContentIR
from ..template.model import DesignSystem
from .model import Defect

# --- каталог проверок --------------------------------------------------------

@dataclass(frozen=True)
class Check:
    id: str
    nature: str                  # deterministic | contextual
    group: str                   # вёрстка | шаблон | плотность | целостность | содержание
    title: str
    fixable: bool = False
    fix: str = ""


CHECKS: dict[str, Check] = {check.id: check for check in [
    # вёрстка
    Check("out_of_bounds", "deterministic", "вёрстка", "элемент вышел за границы слайда",
          True, "пересборка слайда с ужатым бюджетом"),
    Check("overlap", "deterministic", "вёрстка", "два текстовых блока наложились",
          True, "пересборка слайда с ужатым бюджетом"),
    Check("overflow", "deterministic", "вёрстка", "текст не поместился в свою рамку",
          True, "пересборка слайда с ужатым бюджетом"),
    Check("margins", "deterministic", "вёрстка", "контент заходит в поля у краёв",
          True, "пересборка слайда с ужатым бюджетом"),
    Check("stretched_image", "deterministic", "вёрстка", "картинка растянута, пропорции нарушены"),
    Check("grid", "deterministic", "вёрстка", "блок не по направляющим макета"),
    # шаблон
    Check("font", "deterministic", "шаблон", "шрифт не из шаблона"),
    Check("too_many_fonts", "deterministic", "шаблон", "гарнитур в колоде больше двух"),
    Check("type_scale", "deterministic", "шаблон", "кегль не из типографической шкалы шаблона"),
    Check("palette", "deterministic", "шаблон", "цвет не из палитры шаблона"),
    Check("foreign_layout", "deterministic", "шаблон", "слайд собран не на макете шаблона"),
    Check("contrast", "deterministic", "шаблон", "контраст текста к фону ниже 4.5:1"),
    # плотность
    Check("too_many_bullets", "deterministic", "плотность", "больше 6 буллетов на слайде",
          True, "пересборка слайда: лишние пункты уходят в «не размещено»"),
    Check("long_bullet", "deterministic", "плотность", "буллет длиннее 15 слов",
          True, "сокращение моделью или обрезка по словам"),
    Check("big_table", "deterministic", "плотность", "таблица больше 7 строк или 5 колонок"),
    Check("many_series", "deterministic", "плотность", "больше 5 серий на диаграмме"),
    Check("fill_ratio", "deterministic", "плотность",
          "слайд заполнен меньше чем на четверть или больше чем на три четверти"),
    # целостность
    Check("unreadable", "deterministic", "целостность", "файл не открывается"),
    Check("placeholder_text", "deterministic", "целостность",
          "остался текст-заглушка или текст шаблона"),
    Check("empty_slide", "deterministic", "целостность", "пустой слайд или слайд с одним заголовком"),
    Check("raster_slide", "deterministic", "целостность",
          "слайд оказался картинкой, а не редактируемыми объектами"),
    Check("chart_labels", "deterministic", "целостность",
          "у диаграммы нет подписей осей, единиц или легенды"),
    Check("duplicate_slides", "deterministic", "целостность", "два слайда дублируют друг друга"),
    # содержание — детерминированная часть
    Check("unsourced_number", "deterministic", "содержание",
          "цифра на слайде отсутствует в исходных материалах"),
    Check("service_junk", "deterministic", "содержание",
          "служебный мусор: реплики спикера, куски промпта"),
    Check("mixed_language", "deterministic", "содержание", "слайд не на языке колоды"),
    # содержание — контекстуальная часть (модель)
    Check("title_not_conclusion", "contextual", "содержание",
          "заголовок называет тему, а не содержит вывод"),
    Check("content_off_title", "contextual", "содержание",
          "содержимое слайда не соответствует заголовку"),
    Check("not_one_idea", "contextual", "содержание",
          "слайд не пересказывается одним предложением — на нём несколько мыслей"),
    Check("broken_flow", "contextual", "содержание",
          "соседние слайды не связаны по логике"),
]}

# Что ТЗ просит, но что здесь не проверяется — с причиной, а не молчанием.
NOT_COVERED: dict[str, str] = {
    "логотип или колонтитул сдвинуты с положенного места":
        "сборка не двигает элементы макета — сдвинуть их некому; проверка была бы тождественно зелёной",
    "картинки и иконки относятся к теме слайда":
        "картинок в контенте нет, а иконки подбираются по словарю смысла — проверка совпала бы с подбором",
    "текст без опечаток": "требует модели-корректора; на открытой 4B-модели даёт больше ложных срабатываний, чем находок",
    "все строки таблицы и элементы легенды работают на мысль слайда":
        "таблица переносится как есть — решение об этом за автором контента",
}


@dataclass
class AuditResult:
    defects: list[Defect] = field(default_factory=list)
    checked: list[str] = field(default_factory=list)
    skipped: dict[str, str] = field(default_factory=dict)


def _defect(check_id: str, slide: int, message: str, severity: str = "warning",
            bbox: list[float] | None = None) -> Defect:
    check = CHECKS[check_id]
    return Defect(kind="audit", severity=severity, slide=slide, message=message,  # type: ignore[arg-type]
                  bbox=bbox, detail=check_id, check=check_id, nature=check.nature,
                  fixable=check.fixable, fix=check.fix, group=check.group)


# --- вспомогательное ---------------------------------------------------------

NUMBER_RE = re.compile(r"\d+(?:[.,]\d+)?")
# Разряды через пробел («9 999») — одно число, а не два; проценты идут с числом.
THOUSANDS_RE = re.compile(r"(?<=\d)[ \u00a0](?=\d{3}\b)")
SIGNIFICANT_NUMBER_RE = re.compile(
    r"\d{1,3}(?:[ \u00a0]\d{3})+(?:[.,]\d+)?(?:\s?%)?|\d+[.,]\d+(?:\s?%)?|\d{3,}(?:\s?%)?|\d+\s?%")
JUNK_RE = re.compile(r"(?:^|\s)(?:бриф:|json|верни только|схем[аы]\b|```|\{\"|assistant|system:)",
                     re.IGNORECASE)
PLACEHOLDER_RE = re.compile(r"lorem ipsum|\bXXX\b|\bTODO\b|вставьте текст|заголовок в одну|"
                            r"click to add|нажмите, чтобы|образец текста|sample text",
                            re.IGNORECASE)
SYMBOL_FONT_RE = re.compile(r"symbol|wingdings|webdings|emoji|icons?$", re.IGNORECASE)
CYRILLIC_RE = re.compile(r"[а-яё]", re.IGNORECASE)
LATIN_RE = re.compile(r"[a-z]", re.IGNORECASE)
CONTACT_RE = re.compile(r"[\w.+-]+@[\w-]+\.[\w.]+|https?://\S+|\b[\w-]+\.(?:ru|com|io|org|net)\b")
# Ближе этой доли к краю слайда текст стоять не должен.
EDGE_BAND = 0.015
# Макеты, где мало содержания по замыслу: обложка, разделитель, финал.
SPARSE_BY_DESIGN = {"cover", "section", "contacts"}
# Макет, чьи слоты вместе занимают меньше этой доли слайда, редок по замыслу.
SPARSE_LAYOUT_AREA = 0.25


def _designed_area(pattern) -> float:
    """Доля слайда под слотами макета — сколько дизайнер отвёл под содержание."""
    slots = getattr(pattern, "slots", None) or []
    return min(1.0, sum(max(0.0, slot.bbox[2]) * max(0.0, slot.bbox[3]) for slot in slots))


def _text_shapes(slide):
    return [shape for shape in slide.shapes
            if shape.has_text_frame and shape.text_frame.text.strip()]


def _box(shape, width: int, height: int) -> list[float] | None:
    if shape.left is None or shape.width is None:
        return None
    return [shape.left / width, shape.top / height, shape.width / width, shape.height / height]


def _overlap_area(a: list[float], b: list[float]) -> float:
    dx = min(a[0] + a[2], b[0] + b[2]) - max(a[0], b[0])
    dy = min(a[1] + a[3], b[1] + b[3]) - max(a[1], b[1])
    return max(0.0, dx) * max(0.0, dy)


def _bullets(shape) -> list[str]:
    return [paragraph.text.strip() for paragraph in shape.text_frame.paragraphs
            if paragraph.text.strip()]


# --- детерминированные проверки ----------------------------------------------

def audit_deck(deck_path: str | Path, design: DesignSystem, ir: ContentIR,
               filled_slides=None, template_fonts: set[str] | None = None,
               client=None, contextual: bool = True) -> AuditResult:
    """Прогоняет чек-лист по собранному файлу."""
    from pptx import Presentation
    from pptx.util import Emu

    result = AuditResult()
    try:
        presentation = Presentation(str(deck_path))
    except Exception as error:                        # noqa: BLE001 — это и есть проверка
        result.defects.append(_defect("unreadable", 0, f"файл не открывается: {error}", "error"))
        result.checked.append("unreadable")
        return result
    result.checked.append("unreadable")

    width, height = presentation.slide_width, presentation.slide_height
    # Поля считаем от края слайда, а не от безопасной зоны шаблона: где именно
    # стоит заголовок, решил дизайнер макета, и спорить с ним аудиту не о чем.
    # Дефект — когда текст практически упирается в край.
    margins = (EDGE_BAND, EDGE_BAND, 1 - EDGE_BAND, 1 - EDGE_BAND)
    sparse_ok: set[int] = set()
    if filled_slides:
        # Редкий по замыслу — обложка, разделитель, финал; и любой макет, в
        # котором дизайнер сам отвёл под содержание меньше четверти слайда:
        # заполнить его плотнее, не нарушив макет, нельзя.
        sparse_ok = {slide.n for slide in filled_slides
                     if slide.pattern.archetype in SPARSE_BY_DESIGN
                     or _designed_area(slide.pattern) < SPARSE_LAYOUT_AREA}
    scale = {round(size, 1) for size in design.typography.scale_pt}
    for style in design.typography.styles.values():
        if style.size_pt:
            scale.add(round(style.size_pt, 1))
    corpus = _corpus(ir)
    layouts = {layout.name for master in presentation.slide_masters
               for layout in master.slide_layouts}

    fingerprints: dict[str, int] = {}
    deck_cyrillic = deck_latin = 0
    slide_scripts: list[tuple[int, int, int]] = []

    for number, slide in enumerate(presentation.slides, start=1):
        shapes = list(slide.shapes)
        texts = _text_shapes(slide)
        boxes = [(shape, box) for shape in shapes
                 if (box := _box(shape, width, height)) is not None]

        # --- вёрстка
        for shape, box in boxes:
            if shape.has_text_frame and not shape.text_frame.text.strip() and not (
                    getattr(shape, "has_table", False) or getattr(shape, "has_chart", False)):
                continue
            if box[0] < -0.005 or box[1] < -0.005 or box[0] + box[2] > 1.005 or box[1] + box[3] > 1.005:
                result.defects.append(_defect(
                    "out_of_bounds", number, f"«{shape.name}» выходит за границы слайда", "error", box))
            elif shape.has_text_frame and shape.text_frame.text.strip() and (
                    box[0] < margins[0] - 0.01 or box[1] < margins[1] - 0.01
                    or box[0] + box[2] > margins[2] + 0.01 or box[1] + box[3] > margins[3] + 0.01):
                # Декор макета живёт в полях по праву — смотрим только на текст.
                if not _is_chrome(shape, box):
                    result.defects.append(_defect(
                        "margins", number, f"«{shape.name}» заходит в поля слайда", "warning", box))

        text_boxes = [(shape, box) for shape, box in boxes
                      if shape.has_text_frame and shape.text_frame.text.strip()]
        for index, (first, box_a) in enumerate(text_boxes):
            for second, box_b in text_boxes[index + 1:]:
                overlap = _overlap_area(box_a, box_b)
                smaller = min(box_a[2] * box_a[3], box_b[2] * box_b[3]) or 1e-9
                if overlap / smaller > 0.25:
                    result.defects.append(_defect(
                        "overlap", number,
                        f"«{first.name}» и «{second.name}» наложились", "error", box_a))

        for shape, box in boxes:
            if shape.shape_type == 13:                  # PICTURE
                ratio = _picture_ratio(shape)
                if ratio is not None and shape.height:
                    shown = (shape.width / shape.height)
                    if abs(shown / ratio - 1.0) > 0.08:
                        result.defects.append(_defect(
                            "stretched_image", number,
                            f"«{shape.name}»: пропорции {shown:.2f} вместо {ratio:.2f}", "warning", box))

        # --- шаблон
        if scale:
            for shape in texts:
                for paragraph in shape.text_frame.paragraphs:
                    for run in paragraph.runs:
                        if run.font.size is None:
                            continue
                        size = round(run.font.size.pt, 1)
                        if all(abs(size - step) > 1.0 for step in scale):
                            result.defects.append(_defect(
                                "type_scale", number,
                                f"кегль {size:g} pt не из шкалы шаблона ({', '.join(f'{s:g}' for s in sorted(scale))})",
                                "info"))
                            break
                    else:
                        continue
                    break
        if layouts and slide.slide_layout.name not in layouts:
            result.defects.append(_defect("foreign_layout", number,
                                          f"макет «{slide.slide_layout.name}» не из шаблона", "error"))

        # --- плотность
        for shape in texts:
            bullets = _bullets(shape)
            if len(bullets) > 6:
                result.defects.append(_defect(
                    "too_many_bullets", number, f"{len(bullets)} пунктов в «{shape.name}»", "warning"))
            for bullet in bullets:
                if len(bullet.split()) > 15:
                    result.defects.append(_defect(
                        "long_bullet", number, f"пункт из {len(bullet.split())} слов: «{bullet[:60]}…»",
                        "warning"))
        for shape in shapes:
            if getattr(shape, "has_table", False) and shape.has_table:
                rows, cols = len(shape.table.rows), len(shape.table.columns)
                if rows > 7 or cols > 5:
                    result.defects.append(_defect(
                        "big_table", number, f"таблица {rows}×{cols}", "warning"))
            if getattr(shape, "has_chart", False) and shape.has_chart:
                chart = shape.chart
                series = sum(len(list(plot.series)) for plot in chart.plots)
                if series > 5:
                    result.defects.append(_defect("many_series", number,
                                                  f"на диаграмме {series} серий", "warning"))
                if not _chart_labelled(chart, series):
                    result.defects.append(_defect(
                        "chart_labels", number, "у диаграммы нет подписей осей или легенды", "warning"))

        fill = _fill_share(boxes, width, height)
        if fill is not None and (fill < 0.25 or fill > 0.75) and number not in sparse_ok:
            result.defects.append(_defect(
                "fill_ratio", number, f"занято {fill:.0%} площади слайда", "info"))

        # --- целостность
        content_shapes = [shape for shape in shapes if _is_content(shape)]
        if len(shapes) == 1 and shapes[0].shape_type == 13:
            result.defects.append(_defect("raster_slide", number,
                                          "единственный объект — картинка", "error"))
        elif number not in sparse_ok and (not content_shapes or (
                len(content_shapes) == 1 and _is_title(content_shapes[0]))):
            # Одна цитата на слайде — это слайд-цитата, а не пустой слайд;
            # пустой — это когда кроме заголовка нет ничего.
            result.defects.append(_defect(
                "empty_slide", number,
                "на слайде только заголовок" if content_shapes else "слайд пуст", "warning"))

        for shape in texts:
            text = shape.text_frame.text
            if PLACEHOLDER_RE.search(text):
                result.defects.append(_defect("placeholder_text", number,
                                              f"«{text.strip()[:50]}»", "error"))
            if JUNK_RE.search(text):
                result.defects.append(_defect("service_junk", number,
                                              f"«{text.strip()[:50]}»", "error"))

        joined = " ".join(shape.text_frame.text.strip() for shape in texts)
        key = re.sub(r"\W+", " ", joined.lower()).strip()
        if key and len(key) > 30:
            if key in fingerprints:
                result.defects.append(_defect(
                    "duplicate_slides", number, f"повторяет слайд {fingerprints[key]}", "warning"))
            else:
                fingerprints[key] = number

        # --- содержание (детерминированное)
        for token in set(SIGNIFICANT_NUMBER_RE.findall(CONTACT_RE.sub(" ", joined))):
            normalized = re.sub(r"[\s\u00a0%]", "", token).replace(",", ".")
            if normalized not in corpus:
                result.defects.append(_defect(
                    "unsourced_number", number, f"«{token.strip()}» нет в исходных материалах", "error"))

        plain = CONTACT_RE.sub(" ", joined)             # почта и ссылки языка не имеют
        cyr, lat = len(CYRILLIC_RE.findall(plain)), len(LATIN_RE.findall(plain))
        deck_cyrillic += cyr
        deck_latin += lat
        slide_scripts.append((number, cyr, lat))

    families: dict[str, set[int]] = {}
    for number, slide in enumerate(presentation.slides, start=1):
        for shape in _text_shapes(slide):
            for paragraph in shape.text_frame.paragraphs:
                for run in paragraph.runs:
                    name = (run.font.name or "").strip()
                    if name and not SYMBOL_FONT_RE.search(name):
                        families.setdefault(name, set()).add(number)
    if len(families) > 2:
        # Тема допускает пару гарнитур — заголовочную и основную; третья и
        # дальше — это уже чужой шрифт, и говорим, где он.
        extra = sorted(families, key=lambda name: len(families[name]))[:-2]
        result.defects.append(_defect(
            "too_many_fonts", 0,
            f"гарнитур {len(families)}: {', '.join(sorted(families))}; лишние — "
            + ", ".join(f"{name} (слайды {', '.join(map(str, sorted(families[name])))})"
                        for name in extra), "warning"))

    deck_is_cyrillic = deck_cyrillic >= deck_latin
    for number, cyr, lat in slide_scripts:
        if cyr + lat < 20:
            continue
        share = cyr / (cyr + lat)
        if (deck_is_cyrillic and share < 0.5) or (not deck_is_cyrillic and share > 0.5):
            result.defects.append(_defect("mixed_language", number,
                                          f"кириллицы {share:.0%} при языке колоды", "warning"))

    result.checked.extend(check.id for check in CHECKS.values()
                          if check.nature == "deterministic" and check.id not in result.checked)

    contextual_ids = [check.id for check in CHECKS.values() if check.nature == "contextual"]
    if contextual and client is not None:
        try:
            result.defects.extend(contextual_audit(presentation, client))
        except ContextualUnavailable as why:
            # Модель не ответила — это «не проверено», а не «замечаний нет».
            result.skipped.update({check_id: str(why) for check_id in contextual_ids})
        else:
            result.checked.extend(contextual_ids)
    else:
        result.skipped.update({check_id: "модель не подключена" for check_id in contextual_ids})
    return result


class ContextualUnavailable(Exception):
    """Контекстуальные вопросы задать не удалось: модель молчит или бюджет вышел."""


def _corpus(ir: ContentIR) -> set[str]:
    """Все числа исходника в нормальном виде — без пробелов, с точкой."""
    parts: list[str] = []
    for block in ir.blocks:
        parts.extend([block.text or "", *block.items, block.value or "", block.label or "",
                      *block.header, *(cell for row in block.rows for cell in row),
                      *[str(x) for x in block.x],
                      *[str(v) for values in block.y.values() for v in values]])
    found = set()
    for token in NUMBER_RE.findall(THOUSANDS_RE.sub("", " ".join(parts))):
        found.add(token.replace(",", "."))
    return found


def _is_chrome(shape, box: list[float]) -> bool:
    """Логотип, номер слайда, колонтитул — им положено стоять в полях."""
    name = (shape.name or "").lower()
    small = box[2] * box[3] < 0.01
    return small or any(word in name for word in ("logo", "лого", "footer", "колонтитул",
                                                    "slide number", "номер"))


def _is_title(shape) -> bool:
    try:
        return shape.is_placeholder and str(shape.placeholder_format.type).startswith(
            ("TITLE", "CENTER_TITLE"))
    except Exception:                                 # noqa: BLE001 — не плейсхолдер
        return False


def _is_content(shape) -> bool:
    if getattr(shape, "has_table", False) and shape.has_table:
        return True
    if getattr(shape, "has_chart", False) and shape.has_chart:
        return True
    if shape.shape_type == 13:
        return True
    return bool(shape.has_text_frame and shape.text_frame.text.strip())


def _picture_ratio(shape) -> float | None:
    try:
        image = shape.image
        from PIL import Image
        import io
        with Image.open(io.BytesIO(image.blob)) as picture:
            w, h = picture.size
        crop = (1 - shape.crop_left - shape.crop_right, 1 - shape.crop_top - shape.crop_bottom)
        if crop[0] <= 0 or crop[1] <= 0 or not h:
            return None
        return (w * crop[0]) / (h * crop[1])
    except Exception:                                 # noqa: BLE001 — нет картинки или формат
        return None


def _chart_labelled(chart, series: int) -> bool:
    """Подписана ли диаграмма: несколько рядов — нужна легенда; и хоть какая-то
    подпись — заголовок диаграммы или оси."""
    try:
        if series > 1 and not chart.has_legend:
            return False
        titled = bool(chart.has_title)
        for axis in (chart.category_axis, chart.value_axis):
            titled = titled or bool(axis.has_title)
        return titled
    except Exception:                                 # noqa: BLE001 — у круговой нет осей
        return bool(getattr(chart, "has_title", False)) or series <= 1


def _fill_share(boxes, width: int, height: int) -> float | None:
    """Доля площади слайда под содержанием — по сетке 96×54, чтобы не считать
    наложения дважды."""
    cells = [[False] * 96 for _ in range(54)]
    any_content = False
    for shape, box in boxes:
        if not _is_content(shape) or _is_chrome(shape, box):
            continue
        if shape.shape_type == 13 and box[2] * box[3] > 0.9:
            continue                                    # фон во весь слайд — не контент
        any_content = True
        x0, y0 = max(0, int(box[0] * 96)), max(0, int(box[1] * 54))
        x1, y1 = min(96, int((box[0] + box[2]) * 96) + 1), min(54, int((box[1] + box[3]) * 54) + 1)
        for row in range(y0, y1):
            for col in range(x0, x1):
                cells[row][col] = True
    if not any_content:
        return None
    return sum(cell for row in cells for cell in row) / (96 * 54)


# --- контекстуальные проверки (модель) ----------------------------------------

CONTEXT_SCHEMA = {
    "type": "object",
    "properties": {
        "slides": {
            "type": "array",
            "items": {
                "type": "object",
                "properties": {
                    "n": {"type": "integer"},
                    "title_is_conclusion": {"type": "boolean"},
                    "content_matches_title": {"type": "boolean"},
                    "linked_to_previous": {"type": "boolean"},
                    "one_idea": {"type": "boolean"},
                },
                "required": ["n", "title_is_conclusion", "content_matches_title",
                             "linked_to_previous", "one_idea"],
                "additionalProperties": False,
            },
        },
    },
    "required": ["slides"],
    "additionalProperties": False,
}


def contextual_audit(presentation, client) -> list[Defect]:
    """Вопросы «да/нет» модели по тексту слайдов. Ответы — контекстуальные."""
    from ..llm import LLMError, prompts, system, user

    lines = []
    for number, slide in enumerate(presentation.slides, start=1):
        texts = [shape.text_frame.text.strip() for shape in _text_shapes(slide)]
        if not texts:
            continue
        title, *rest = texts
        lines.append(f"Слайд {number}\nЗаголовок: {title[:120]}\nТекст: "
                     + " / ".join(part[:160] for part in rest)[:600])
    if not lines:
        return []
    request = [system(prompts.load("auditor").text), user("\n\n".join(lines))]
    try:
        response = client.complete(request, CONTEXT_SCHEMA, schema_name="audit", max_tokens=4000)
    except LLMError as error:
        raise ContextualUnavailable(f"модель не ответила: {error}") from error

    defects: list[Defect] = []
    for item in response.data.get("slides", []):
        number = int(item.get("n", 0))
        if number <= 1:
            continue                                    # обложку не судят
        if not item.get("title_is_conclusion", True):
            defects.append(_defect("title_not_conclusion", number,
                                   "заголовок называет тему, а не вывод", "info"))
        if not item.get("content_matches_title", True):
            defects.append(_defect("content_off_title", number,
                                   "содержимое не про то, что в заголовке", "warning"))
        if not item.get("linked_to_previous", True):
            defects.append(_defect("broken_flow", number,
                                   "логической связки с предыдущим слайдом нет", "info"))
        if not item.get("one_idea", True):
            defects.append(_defect("not_one_idea", number,
                                   "слайд не пересказать одним предложением", "info"))
    return defects
