"""Планирование истории: что показать и в каком порядке.

Модель получает **только** контент — состав блоков и их форму. Она не знает,
какие макеты есть в шаблоне, иначе начнёт заниматься дизайном вместо смысла;
подбор макета делает детерминированный матчер на следующем шаге.

Если LLM недоступна, работает эвристический планировщик: он строит план по
структуре документа. Качество истории ниже, но пайплайн проходит целиком —
это то, что позволяет показывать решение без сети.
"""

from __future__ import annotations

import json
import re

from ..content.model import Block, ContentIR
from ..llm import LLMClient, LLMError, Message, prompts, system, user
from . import variants as variant_set
from .model import DeckPlan, SlidePlan
from .variants import Variant

INTENTS = ["cover", "section", "agenda", "bullets", "two_column", "comparison",
           "metrics", "process", "table", "chart", "quote", "image_full",
           "image_text", "gallery", "team", "contacts"]

PLAN_SCHEMA = {
    "type": "object",
    "properties": {
        "title": {"type": "string"},
        "subtitle": {"type": "string"},
        "slides": {
            "type": "array",
            "minItems": 3,
            "items": {
                "type": "object",
                "properties": {
                    "intent": {"type": "string", "enum": INTENTS},
                    "key_message": {"type": "string"},
                    "blocks": {"type": "array", "items": {"type": "string"}},
                    "items": {"type": "array", "items": {"type": "string"},
                              "maxItems": 6},
                    "notes": {"type": "string"},
                },
                "required": ["intent", "key_message", "blocks", "items"],
                "additionalProperties": False,
            },
        },
    },
    "required": ["title", "slides"],
    "additionalProperties": False,
}

# Текст промпта живёт в prompts/planner.md — с версией и историей правок.
PROMPT = "planner"


def _content_digest(ir: ContentIR, max_chars: int = 220) -> str:
    """Компактное описание контента для модели: форма важнее текста."""
    lines = [f"Заголовок документа: {ir.meta.title}",
             f"Язык: {ir.meta.language}, объём: {ir.meta.words} слов", "", "Блоки:"]
    for block in ir.blocks:
        preview = block.text or " / ".join(block.items) or block.label
        if block.type == "table":
            preview = " | ".join(block.header)
        elif block.type == "series":
            preview = f"ряды: {', '.join(block.y)}; точек: {len(block.x)}"
        elif block.type == "metric":
            preview = f"{block.value} — {block.label}"
        lines.append(f"- {block.id} [{block.shape()}] {preview[:max_chars]}")
    return "\n".join(lines)


def plan_with_llm(ir: ContentIR, client: LLMClient, brief: str = "",
                  target_slides: int | None = None) -> DeckPlan:
    request = [
        system(prompts.load(PROMPT).text),
        user(_content_digest(ir)),
    ]
    if brief:
        request.append(user(f"Бриф: {brief}"))
    if target_slides:
        request.append(user(f"Ориентир по объёму: около {target_slides} слайдов."))

    response = client.complete(request, PLAN_SCHEMA, schema_name="deck_plan")
    data = response.data
    slides, warnings = _slides_from(data, ir, list(response.notes))

    _adopt_orphan_data(slides, ir, warnings)
    used = {block_id for slide in slides for block_id in slide.blocks}
    missed = [block.id for block in ir.blocks
              if block.id not in used and block.type not in ("heading", "metric")]
    if missed:
        warnings.append(f"вне плана осталось блоков: {len(missed)} ({', '.join(missed[:5])})")

    _drop_invented_contacts(slides, ir, warnings)

    return DeckPlan(title=data.get("title") or ir.meta.title,
                    subtitle=data.get("subtitle") or ir.meta.subtitle,
                    slides=slides, source="llm", warnings=warnings)


# Короче этого контент — не пакет, а бриф: слайды по нему нужно писать, а не
# раскладывать. Порог — в словах, и данных (таблиц, рядов, цифр) быть не должно.
BRIEF_WORDS = 120
NUMBER_RE = re.compile(r"\d+(?:[.,]\d+)?")
WRITER_PROMPT = "writer"


def is_brief(ir: ContentIR) -> bool:
    """Бриф, а не контент-пакет: мало слов и нет данных, которые можно верстать."""
    words = sum(len((block.text or " ".join(block.items)).split()) for block in ir.blocks)
    data = any(block.type in ("table", "series", "metric", "image") for block in ir.blocks)
    return words < BRIEF_WORDS and not data


def plan_from_brief(ir: ContentIR, client: LLMClient, brief: str = "",
                    target_slides: int | None = None) -> DeckPlan:
    """План и текст слайдов по краткому брифу — когда контент-пакета нет.

    Здесь модель пишет содержание сама, поэтому проверка «план опирается на
    слова документа» не применяется — опираться не на что. Зато остаются
    остальные страховки: выдуманные контакты вычищаются, а цифры, которых нет
    в брифе, поймает аудит.
    """
    text = "\n".join(part for part in [ir.meta.title, *(block.text or "\n".join(block.items)
                                                        for block in ir.blocks)] if part)
    request = [system(prompts.load(WRITER_PROMPT).text), user(f"Бриф:\n{text}")]
    if brief:
        request.append(user(f"Назначение и пожелания: {brief}"))
    request.append(user(f"Объём: около {target_slides or 12} слайдов."))

    response = client.complete(request, PLAN_SCHEMA, schema_name="deck_plan")
    data = response.data
    slides, warnings = _slides_from(data, ir, list(response.notes), authored=True)
    _drop_invented_contacts(slides, ir, warnings)
    _tidy_authored(slides, text, warnings)
    warnings.insert(0, "текст слайдов написан моделью по брифу: контент-пакета нет — "
                       "формулировки и факты проверьте")
    return DeckPlan(title=data.get("title") or ir.meta.title,
                    subtitle=data.get("subtitle") or ir.meta.subtitle,
                    slides=slides, source="llm", authored=True, warnings=warnings)


# Число с тем, что его вводит и измеряет: «на 15 %», «до 1,5 часа», «в 2 раза».
INVENTED_NUMBER_RE = re.compile(
    r"\s*(?:(?:на|до|в|с|со|около|более|менее|свыше|порядка|за|по|—|–|-|:)\s+)?"
    r"\d+(?:[.,]\d+)?(?:[  ]\d{3})*"
    r"(?:\s*(?:%|процент\w*|п\.\s?п\.|пункт\w*|час\w*|минут\w*|дн\w*|недел\w*|"
    r"месяц\w*|раз\w*|тыс\.?|млн|млрд|руб\w*|₽|\$|€|клиент\w*|человек\w*|сотрудник\w*))?",
    re.IGNORECASE)
# Название финального слайда с реквизитами, которых нет в брифе, — тоже выдумка.
CONTACT_TOKEN_RE = re.compile(r"@|https?://|\+?\d[\d\s()-]{8,}\d|www\.", re.IGNORECASE)


def _tidy_authored(slides: list[SlidePlan], brief: str, warnings: list[str]) -> None:
    """Страховки автора: числа не из брифа, выдуманные контакты, чужие интенты.

    Маленькая модель нарушает запрет на цифры даже с примером в промпте —
    поэтому число, которого нет в брифе, вырезается вместе с предлогом и
    единицей: «время ответа сократилось на 15 %» → «время ответа сократилось».
    Это честнее, чем показать зрителю выдуманный процент.
    """
    allowed = {token.replace(",", ".") for token in NUMBER_RE.findall(brief)}

    def scrub(text: str) -> str | None:
        """Текст без выдуманного числа; None — если фраза без него не читается.

        Число в конце фразы отрезается вместе с предлогом и единицей, и фраза
        остаётся целой. Число в середине («в 3 квартале», «с 100 клиентами в
        июле») так не вырежешь — такую фразу честнее убрать целиком.
        """
        tail = len(text.rstrip(" .!?…"))
        for match in INVENTED_NUMBER_RE.finditer(text):
            digits = NUMBER_RE.findall(match.group(0))
            if not digits or all(token.replace(",", ".") in allowed for token in digits):
                continue
            if match.end() < tail:
                return None
            cleaned = text[:match.start()].strip(" ,;:—–-")
            return cleaned[0].upper() + cleaned[1:] if cleaned else cleaned
        return text

    cut = 0
    for slide in slides:
        title = scrub(slide.key_message)
        if title != slide.key_message:
            cut += 1
            lead, rest = _lead_title(slide.items) if title is None else ("", slide.items)
            slide.key_message = title or lead or slide.key_message
            slide.items = rest
        items = []
        for item in slide.items:
            cleaned = scrub(item)
            if cleaned != item:
                cut += 1
            if cleaned and len(cleaned) >= 12:
                items.append(cleaned)
        slide.items = items
    if cut:
        warnings.append(f"вырезано выдуманных чисел: {cut}")

    if not CONTACT_TOKEN_RE.search(brief):
        before = len(slides)
        slides[:] = [slide for slide in slides if slide.intent != "contacts"]
        if len(slides) != before:
            warnings.append("финальный слайд с выдуманными контактами убран")
    # Разделитель без названия берёт заголовок следующего слайда; повторный
    # заголовок уступает место первому тезису — одна мысль не идёт дважды.
    seen: set[str] = set()
    for slide in slides:
        if slide.intent in ("cover", "section"):
            seen.add(slide.key_message.strip().lower())  # название колоды не повторяют
            continue
        title = slide.key_message.strip().lower()
        if title in seen:
            lead, rest = _lead_title(slide.items)
            if lead and lead.lower() not in seen:
                slide.key_message, slide.items = lead, rest
                title = lead.lower()
        seen.add(title)
    kept: list[SlidePlan] = []
    cover = slides[0].key_message.strip().lower() if slides and slides[0].intent == "cover" else ""
    for index, slide in enumerate(slides):
        if slide.intent == "section" and (not slide.key_message.strip()
                                          or slide.key_message.strip().lower() == cover):
            following = slides[index + 1].key_message if index + 1 < len(slides) else ""
            if not following:
                continue
            slide.key_message = following
        kept.append(slide)
    slides[:] = kept

    for position, slide in enumerate(slides, start=1):
        if slide.intent == "agenda" and position > 2:
            slide.intent = "bullets"                    # содержание бывает одно
        if slide.intent == "metrics" and not any(NUMBER_RE.search(item) for item in slide.items):
            slide.intent = "bullets"                    # показатели без чисел — тезисы
        slide.n = position


def _slides_from(data: dict, ir: ContentIR, warnings: list[str], authored: bool = False
                 ) -> tuple[list[SlidePlan], list[str]]:
    """Слайды из ответа модели по схеме deck_plan — с проверками и подстраховками."""
    known = {block.id for block in ir.blocks}
    slides: list[SlidePlan] = []

    for index, item in enumerate(data.get("slides", []), start=1):
        blocks = [block_id for block_id in item.get("blocks", []) if block_id in known]
        if len(blocks) != len(item.get("blocks", [])) and not authored:
            warnings.append(f"слайд {index}: модель сослалась на несуществующие блоки")
        items = [str(thesis).strip() for thesis in item.get("items", [])
                 if str(thesis).strip()]
        # Строка таблицы через «|» тезисом не бывает: таблица уйдёт на слайд
        # настоящей таблицей, а такой тезис продублирует её текстом.
        rows = [thesis for thesis in items if " | " in thesis]
        if rows:
            warnings.append(f"слайд {index}: модель переписала строки таблицы в тезисы — убраны")
            items = [thesis for thesis in items if thesis not in rows]
        key_message = str(item.get("key_message", "")).strip()
        if not key_message and item["intent"] not in ("cover", "section"):
            # Модель оставила заголовок пустым — берём его из первого тезиса,
            # как делает эвристика: слайд без заголовка хуже, чем с тезисом
            # в заголовке. Обложка без key_message получит название документа.
            key_message, items = _lead_title(items)
            if key_message:
                warnings.append(f"слайд {index}: заголовок взят из первого тезиса")
        if not key_message and item["intent"] == "cover":
            key_message = ir.meta.title
        slides.append(SlidePlan(n=index, intent=item["intent"],
                                key_message=key_message,
                                blocks=blocks, items=items,
                                notes=item.get("notes", "")))
    return slides, warnings


def _adopt_orphan_data(slides: list[SlidePlan], ir: ContentIR, warnings: list[str]) -> None:
    """Таблица или ряд данных, которые модель не взяла в план, получают свой слайд.

    Данные — самое дорогое в контенте: их нельзя потерять из-за того, что
    модель о них забыла. Слайд встаёт перед контактами, заголовок — от
    ближайшего заголовка раздела в исходнике, иначе от самих данных.
    """
    used = {block_id for slide in slides for block_id in slide.blocks}
    heading = ""
    adopted: list[SlidePlan] = []
    for block in ir.blocks:
        if block.type == "heading":
            heading = block.text.strip()
            continue
        if block.type not in ("table", "series") or block.id in used:
            continue
        title = heading or _implied_title([block]) or ir.meta.title
        adopted.append(SlidePlan(
            n=0, intent="table" if block.type == "table" else "chart",
            key_message=title, blocks=[block.id], items=[],
            notes="данные, которые план модели не взял"))
    if not adopted:
        return
    tail = len(slides)
    if slides and slides[-1].intent == "contacts":
        tail -= 1
    slides[tail:tail] = adopted
    for position, slide in enumerate(slides, start=1):
        slide.n = position
    warnings.append("данные без слайда в плане модели получили свои слайды: "
                    + ", ".join(block_id for slide in adopted for block_id in slide.blocks))


def _drop_invented_contacts(slides: list[SlidePlan], ir: ContentIR,
                            warnings: list[str]) -> None:
    """Вычищает реквизиты, которых нет в исходном контенте.

    Маленькая модель охотно дописывает финальному слайду «info@company.ru» и
    телефон — выглядят они убедительно, но это выдумка, и на слайде заказчика
    ей не место. Настоящие контакты из контента проходят без изменений.
    """
    import re

    # Шире, чем CONTACT_RE из разбора: модель пишет и голые домены вида
    # «www.potok.ai», которые без схемы не похожи ни на почту, ни на ссылку.
    invented = re.compile(
        r"[\w.+-]+@[\w-]+\.[\w.]+|\+?\d[\d\s()-]{8,}\d|https?://\S+|www\.\S+")

    corpus = " ".join(" ".join([block.text or "", *block.items])
                      for block in ir.blocks)

    def clean(text: str) -> str:
        result = text
        for match in invented.findall(text):
            if match and match not in corpus:
                result = result.replace(match, "").strip(" ,;:|·—–-")
        return re.sub(r"\s{2,}", " ", result).strip(" ,;:|·—–-")

    for slide in slides:
        cleaned = clean(slide.key_message)
        if cleaned != slide.key_message:
            warnings.append(
                f"слайд {slide.n}: модель выдумала контакты — убраны")
            slide.key_message = cleaned or ("Спасибо за внимание"
                                            if slide.intent == "contacts" else "")
        slide.items = [item for item in (clean(text) for text in slide.items) if item]


# --- эвристический планировщик ----------------------------------------------

def _section_intent(blocks: list[Block]) -> str:
    kinds = {block.type for block in blocks}
    if "series" in kinds:
        return "chart"
    if "table" in kinds:
        return "table"
    if "steps" in kinds:
        return "process"
    if "quote" in kinds:
        return "quote"
    if "contact" in kinds:
        return "contacts"
    if "image" in kinds:
        return "image_text"
    return "bullets"


def _implied_title(blocks: list[Block]) -> str:
    """Заголовок для раздела без заголовка — данные приходят из отдельных файлов."""
    for block in blocks:
        if block.type == "series" and block.y:
            return next(iter(block.y))
        if block.type == "table" and block.header:
            return block.header[0]
    return ""


# Длиннее этого заголовок слайда не бывает: дальше это уже абзац.
TITLE_LIMIT = 72


def _lead_title(theses: list[str]) -> tuple[str, list[str]]:
    """Заголовок из первого тезиса и тезисы без того, что ушло в заголовок."""
    if not theses:
        return "", theses
    first = theses[0].strip()
    for mark in (": ", " — "):
        lead, _, tail = first.partition(mark)
        if tail and len(lead) <= TITLE_LIMIT:
            rest = tail[0].upper() + tail[1:] if tail else tail
            return lead, [rest, *theses[1:]]
    if len(first.rstrip(".")) <= TITLE_LIMIT:
        return first.rstrip("."), theses[1:]
    return "", theses


# Сколько тезисов уносит один слайд: больше — уже не слайд, а конспект.
MAX_THESES = 5
# Тезис — это целое предложение, и своей мерки у него нет: поместится ли он,
# знает только вёрстка, которой известен размер слота. Она же умеет уменьшить
# кегль. Поэтому здесь режется лишь то, что не прочитается ни в каком макете, —
# иначе половина мысли теряется ещё до того, как выбран шаблон.
THESIS_LIMIT = 200


# Меньше этого слайд выглядит недоделанным: одна строка на весь экран.
MIN_THESES = 3   # ниже этого слайд выглядит недоделанным


def _theses(blocks: list[Block], limit: int = MAX_THESES) -> list[str]:
    """Тезисы раздела: то, что зритель прочитает со слайда.

    Абзац на слайд не переносят. Без модели работает простое правило,
    проверенное школой письма: мысль абзаца стоит в его первом предложении.
    Списки берём как есть — они уже тезисы.

    Но раздел из одного абзаца по этому правилу даёт один тезис — и слайд с
    единственной строкой. Такой абзац обычно и есть перечисление, только
    записанное подряд: «Проект занимает восемь недель. Первые две — обследование.
    Далее пилот. Затем тираж». Поэтому, если тезисов набралось мало, берём из
    абзацев следующие предложения — по кругу, чтобы ни один абзац не забрал
    слайд себе целиком.
    """
    sentences = [_sentences(block) for block in blocks]
    theses: list[str] = []
    for block, own in zip(blocks, sentences):
        if block.type in ("list", "steps"):
            theses.extend(block.items)
        elif own:
            theses.append(own[0])
        if len(theses) >= limit:
            return theses[:limit]

    # Добираем до полного слайда: раздел из одного абзаца на четыре фразы —
    # это четыре тезиса, а не три.
    depth = 1
    while len(theses) < limit and any(len(own) > depth for own in sentences):
        for own in sentences:
            if len(own) > depth and len(theses) < limit:
                theses.append(own[depth])
        depth += 1
    return theses[:limit]


def _sentences(block: Block) -> list[str]:
    """Предложения абзаца, каждое не длиннее тезиса."""
    from ..content.parse import summarize

    if block.type not in ("paragraph", "quote") or not block.text:
        return []
    # Мягкие переносы строк внутри абзаца на слайде стали бы настоящими.
    parts = re.split(r"(?<=[.!?])\s+", re.sub(r"\s+", " ", block.text.strip()))
    # Фраза с двоеточием на конце подводит к списку, которого здесь нет:
    # «Из-за этого:» на слайде — обещание без продолжения.
    parts = [part for part in parts
             if part.strip() and not part.rstrip().endswith(":") and len(part.split()) >= 3]
    return [part if len(part) <= THESIS_LIMIT else summarize(part, THESIS_LIMIT)
            for part in parts]


def _metrics_for(ir: ContentIR, blocks: list[Block]) -> list[Block]:
    """Метрики, вытащенные из блоков этого раздела."""
    ids = {block.id for block in blocks}
    return [block for block in ir.blocks
            if block.type == "metric" and block.derived_from in ids]


def plan_heuristic(ir: ContentIR, target_slides: int | None = None,
                   variant: Variant | None = None) -> DeckPlan:
    variant = variant or variant_set.get(None)
    slides: list[SlidePlan] = []
    number = 1

    slides.append(SlidePlan(n=number, intent="cover", key_message=ir.meta.title,
                            blocks=[], notes="обложка"))
    number += 1

    sections = [(heading, blocks) for heading, blocks in ir.sections()
                if heading is not None or blocks]

    # Содержание — это план рассказа, а не оглавление файла: название документа
    # и контакты в нём не пункты. И пунктов не больше, чем тезисов на слайде,
    # иначе список не влезет ни в одну раскладку и уедет в таймлайн.
    agenda = [head.text for head, blocks in sections if head
              and head.text.strip().lower() != ir.meta.title.strip().lower()
              and not any(block.type == "contact" for block in blocks)]
    if len(agenda) >= 4 and variant.agenda_items:
        slides.append(SlidePlan(
            n=number, intent="agenda", key_message="Содержание", blocks=[],
            items=agenda[:variant.agenda_items]))
        number += 1

    for heading, blocks in sections:
        content = [block for block in blocks if block.type != "heading"]
        if not content:
            continue

        metrics = _metrics_for(ir, content)
        # Раздел, где почти каждый пункт списка — измеримое утверждение,
        # показываем цифрами, а не текстом.
        if len(metrics) >= 3:
            numbers = SlidePlan(n=number, intent="metrics",
                                key_message=heading.text if heading else "",
                                blocks=[block.id for block in metrics[:4]])
            slides.append(numbers)
            number += 1
            leftovers = [block for block in content if block.type == "paragraph"]
            # Абзац, из которого остались одна-две фразы, отдельного слайда не
            # стоит: он превратится в слайд с одной строкой. Пусть будет
            # подводкой к цифрам — «остаётся ручной» и рядом четыре числа.
            spare = _theses(leftovers)
            if 0 < len(spare) <= 2:
                # Заголовок-вывод лучше заголовка-темы: «остаётся ручной»
                # говорит больше, чем «Проблема», а тема и так есть в содержании.
                lead, rest = _lead_title(spare)
                if lead:
                    numbers.key_message = lead
                numbers.items = rest if lead else spare
                leftovers = []
            content = leftovers

        if not content:
            continue

        intent = _section_intent(content)
        # Просторный вариант берёт все тезисы раздела и раскладывает их по
        # нескольким слайдам; сжатый — столько, сколько унесёт один слайд.
        theses = _theses(content, limit=max(variant.max_theses, MAX_THESES))
        title = heading.text if heading else _implied_title(content)
        if not title:
            # Раздел без заголовка — обычно вводный абзац сразу под названием
            # документа. Заголовок для него берём из первого тезиса: до
            # двоеточия или тире, если такая зацепка есть, — «Единая среда для
            # сквозной работы с документами», а перечисление после двоеточия
            # остаётся тезисом. Иначе укладчик поднял бы в заголовок целую
            # фразу и обрезал её посреди слова.
            title, theses = _lead_title(theses)
        parts = _chunks(theses, variant.max_theses)
        if variant.dividers and heading is not None and len(parts) > 1:
            # Разделитель перед частью, которой досталось несколько слайдов:
            # в просторной вёрстке он даёт залу передышку и держит структуру.
            slides.append(SlidePlan(n=number, intent="section",
                                    key_message=heading.text, blocks=[]))
            number += 1
        for index, part in enumerate(parts):
            slides.append(SlidePlan(n=number, intent=intent, key_message=title,
                                    blocks=[block.id for block in content] if index == 0 else [],
                                    items=part,
                                    notes="" if index == 0 else "продолжение"))
            number += 1

    # Контакты — всегда последними, даже если в исходном документе они в
    # середине: порядок файлов не должен определять порядок истории.
    slides.sort(key=lambda slide: slide.intent == "contacts")
    _deduplicate_titles(slides, ir)

    if target_slides and len(slides) > target_slides:
        # Режем наименее важные слайды с конца, но обложку и контакты сохраняем.
        keep = [slide for slide in slides if slide.intent in ("cover", "contacts")]
        body = [slide for slide in slides if slide not in keep]
        body = body[:max(0, target_slides - len(keep))]
        slides = sorted(keep + body, key=lambda slide: slide.n)

    for position, slide in enumerate(slides, start=1):
        slide.n = position

    return DeckPlan(title=ir.meta.title, subtitle=ir.meta.subtitle, slides=slides,
                    source="heuristic", variant=variant.id)


def _chunks(items: list[str], size: int) -> list[list[str]]:
    """Режет список тезисов на слайды не длиннее `size` — поровну.

    Пять шагов при норме в четыре — это 3 + 2, а не 4 + 1: слайд-продолжение
    с одной строкой выглядит как обрывок.
    """
    if not items:
        return [[]]
    return _split_even(items, -(-len(items) // max(1, size)))


def _split_even(items: list[str], count: int) -> list[list[str]]:
    """Режет список ровно на `count` частей, длинные — первыми."""
    if not items:
        return [[]]
    count = max(1, min(count, len(items)))
    base, extra = divmod(len(items), count)
    parts: list[list[str]] = []
    start = 0
    for index in range(count):
        length = base + (1 if index < extra else 0)
        parts.append(items[start:start + length])
        start += length
    return parts


def _deduplicate_titles(slides: list[SlidePlan], ir: ContentIR) -> None:
    """Убирает подряд идущие слайды с одинаковым заголовком.

    Раздел, из которого вышли и «цифры», и текст, давал два слайда с шапкой
    «Проблема». Второму заголовок берётся из его собственного содержания —
    выдумывать ничего не нужно, он там уже есть.
    """
    from ..content.parse import summarize

    seen: set[str] = set()
    for slide in slides:
        title = slide.key_message.strip()
        if not title or title.lower() not in seen:
            seen.add(title.lower())
            continue
        replacement = ""
        for block_id in slide.blocks:
            block = ir.block(block_id)
            if block and block.type in ("paragraph", "quote"):
                # Не обрубок первой фразы, а её зацепка — до двоеточия или тире;
                # целиком фраза идёт в заголовок только если коротка.
                lead, _ = _lead_title(_sentences(block)[:1])
                replacement = lead or summarize(block.text, TITLE_LIMIT)
                break
            if block and block.items:
                replacement = summarize(block.items[0], TITLE_LIMIT)
                break
        if replacement and replacement.lower() not in seen:
            slide.key_message = replacement
            seen.add(replacement.lower())


def build_plan(ir: ContentIR, client: LLMClient | None = None, brief: str = "",
               target_slides: int | None = None,
               variant: Variant | str | None = None) -> DeckPlan:
    """План истории: моделью, если она есть, иначе эвристикой."""
    chosen = variant if isinstance(variant, Variant) else variant_set.get(variant)
    if client is not None and client.provider.name != "stub":
        authored = is_brief(ir)
        try:
            plan = (plan_from_brief(ir, client, brief, target_slides) if authored
                    else plan_with_llm(ir, client, brief, target_slides))
        except (LLMError, KeyError, json.JSONDecodeError) as error:
            plan = plan_heuristic(ir, target_slides, chosen)
            plan.warnings.append(f"LLM недоступна ({error}) — план построен эвристикой")
            return plan

        share = 1.0 if authored else grounding(plan, ir)
        if share < MIN_GROUNDING:
            # Модель написала не про этот документ. Небольшая модель на длинном
            # тексте иногда сочиняет презентацию «вообще» — показать такое
            # нельзя: зритель увидит чужие факты под своим заголовком.
            plan = plan_heuristic(ir, target_slides, chosen)
            plan.warnings.append(
                f"план модели не опирается на текст (совпадение слов "
                f"{share:.0%}) — построен эвристикой")
            return plan
        return apply_variant(plan, chosen, target_slides)
    plan = plan_heuristic(ir, target_slides, chosen)
    if is_brief(ir):
        plan.warnings.append("это бриф, а не контент: без модели слайды по нему не написать — "
                             "подключите модель или приложите текст")
    return plan


# Слайды, которые не делятся на продолжения: у них нет «списка тезисов»,
# который можно резать, — обложка, разделитель, контакты, цитата; цифры и
# таблицы держатся вместе по смыслу.
UNSPLITTABLE = {"cover", "section", "contacts", "quote", "metrics", "chart", "table",
                "image_full", "gallery", "team", "agenda"}


# Целевой объём колоды по ТЗ — 10–15 слайдов, если пользователь не задал свой.
TARGET_MAX = 15


def apply_variant(plan: DeckPlan, variant: Variant,
                  target_slides: int | None = None) -> DeckPlan:
    """Приводит план модели к плотности варианта.

    Модель спрашивают один раз — план от неё один на все три варианта, и это
    правильно: история одна, различается подача. Слайд, на котором тезисов
    больше нормы варианта, делится на продолжения; в просторной вёрстке перед
    такой частью встаёт разделитель.

    Делению есть предел: колода может вырасти не больше чем в `stretch` раз.
    Запас тратится по одному слайду за шаг, каждый раз на самый тяжёлый
    кусок; когда запас кончается, остальное остаётся как есть — матчер и так
    предпочтёт таким слайдам просторный макет.
    """
    # Рост ограничен и объёмом по ТЗ: просторный вариант на плане из двенадцати
    # слайдов даёт пятнадцать, а не восемнадцать. Если пользователь просил
    # больше, потолок поднимается вместе с его числом.
    ceiling = max(TARGET_MAX, round((target_slides or 0) * 1.25), len(plan.slides))
    limit = min(round(len(plan.slides) * variant.stretch), ceiling)
    budget = max(0, limit - len(plan.slides))
    parts_of: dict[int, list[list[str]]] = {id(slide): [slide.items] for slide in plan.slides}

    def heaviest(slide: SlidePlan) -> int:
        return max(len(part) for part in parts_of[id(slide)])

    while budget > 0:
        candidates = sorted((slide for slide in plan.slides
                             if slide.intent not in UNSPLITTABLE
                             and heaviest(slide) > variant.max_theses),
                            key=lambda slide: (-heaviest(slide), slide.n))
        for slide in candidates:
            current = parts_of[id(slide)]
            cost = 1 + (1 if variant.dividers and len(current) == 1 else 0)
            if cost > budget:
                continue
            parts_of[id(slide)] = _split_even(slide.items, len(current) + 1)
            budget -= cost
            break
        else:
            break

    slides: list[SlidePlan] = []
    for slide in plan.slides:
        parts = parts_of[id(slide)]
        if variant.dividers and len(parts) > 1:
            slides.append(SlidePlan(n=0, intent="section", key_message=slide.key_message,
                                    blocks=[]))
        for index, part in enumerate(parts):
            slides.append(slide.model_copy(update={
                "items": part, "blocks": slide.blocks if index == 0 else [],
                "notes": slide.notes if index == 0 else "продолжение"}))
    for position, slide in enumerate(slides, start=1):
        slide.n = position
    return plan.model_copy(update={"slides": slides, "variant": variant.id})


# Ниже этой доли слов из документа план считается выдуманным.
MIN_GROUNDING = 0.55
WORD_RE = re.compile(r"[а-яёa-z]{4,}", re.IGNORECASE)


def grounding(plan: DeckPlan, ir: ContentIR) -> float:
    """Какая доля значимых слов плана встречается в исходном тексте.

    Проверка от выдумывания: пересказ опирается на слова оригинала, а сочинение
    приносит свои. Считаются слова от четырёх букв — служебные ничего не
    доказывают. Числа не проверяем: они и так должны совпадать, а их подмену
    ловит нормоконтроль.
    """
    source = " ".join([ir.meta.title, *(block.text or " ".join(block.items)
                                        for block in ir.blocks)]).lower()
    vocabulary = {word.lower() for word in WORD_RE.findall(source)}
    if not vocabulary:
        return 1.0

    words = [word.lower() for slide in plan.slides
             for text in [slide.key_message, *slide.items]
             for word in WORD_RE.findall(text)]
    if not words:
        return 1.0

    # Слово засчитывается и по основе: «трение» в тексте покрывает «трения».
    def known(word: str) -> bool:
        return any(word.startswith(stem[:5]) or stem.startswith(word[:5])
                   for stem in vocabulary if abs(len(stem) - len(word)) <= 4)

    return sum(1 for word in words if word in vocabulary or known(word)) / len(words)
