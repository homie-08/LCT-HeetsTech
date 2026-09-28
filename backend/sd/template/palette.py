"""Извлечение палитры шаблона.

Слоты темы (`accent1`, `dk2`, …) — это ещё не палитра: важно, **как** шаблон ими
пользуется. Фон страницы, основной и приглушённый текст, ведущий акцент, порядок
серий для графиков выводятся из фактического употребления цвета в мастере,
макетах и слайдах-примерах — с весом по площади шейпа и объёму текста.
"""

from __future__ import annotations

from collections import Counter, defaultdict
from dataclasses import dataclass

from lxml import etree

from ..ooxml.color import (contrast_ratio, hex_to_rgb, read_scheme, relative_luminance,
                           resolve_color)
from ..ooxml.fill import (Fill, StyleContext, background_fill, line_color, read_clr_map,
                          read_fill, shape_fill)
from ..ooxml.ns import NS, attr_int
from ..ooxml.package import Package
from ..ooxml.shapes import Shape, background_element
from .model import Palette

# Слоты, которые не считаем «акцентными» при выборе ведущего акцента.
NEUTRAL_SLOTS = {"dk1", "lt1", "dk2", "lt2"}


@dataclass
class ColorUse:
    hex: str
    slot: str | None
    context: str          # bg | fill | line | text
    weight: float         # площадь в долях слайда либо число символов
    part: str
    size_pt: float | None = None


def build_context(pkg: Package, part: str) -> StyleContext:
    """Контекст разворачивания цвета для конкретной части пакета (с кешем)."""
    cache: dict[str, StyleContext] = pkg.__dict__.setdefault("_style_ctx_cache", {})
    if part in cache:
        return cache[part]
    cache[part] = context = _build_context(pkg, part)
    return context


def _build_context(pkg: Package, part: str) -> StyleContext:
    master = pkg.master_of(part) or part
    theme_part = pkg.theme_of(part)
    theme_root = pkg.xml(theme_part) if theme_part else None
    scheme = read_scheme(theme_root) if theme_root is not None else {}
    clr_map = read_clr_map(pkg.xml(master)) if pkg.has(master) else {}
    fmt_scheme = (theme_root.find(".//a:themeElements/a:fmtScheme", NS)
                  if theme_root is not None else None)
    return StyleContext(scheme, clr_map, fmt_scheme)


def _text_uses(shape: Shape, ctx: StyleContext, part: str) -> list[ColorUse]:
    uses: list[ColorUse] = []
    for para in shape.paragraphs:
        if para.is_field:
            continue
        for run in para.runs:
            text = run.text.strip()
            if not text or run.rpr is None:
                continue
            fill = read_fill(run.rpr, ctx)
            if fill.color is None:
                continue
            size = attr_int(run.rpr, "sz", None)
            uses.append(ColorUse(fill.color.hex, fill.color.scheme_slot, "text",
                                 float(len(text)), part,
                                 size / 100.0 if size else None))
    return uses


def collect_uses(pkg: Package) -> list[ColorUse]:
    """Все употребления цвета в шаблоне с весами."""
    width, height = pkg.slide_size
    slide_area = float(width * height) or 1.0
    uses: list[ColorUse] = []

    parts = [*pkg.masters, *pkg.layouts, *pkg.slides]
    for part in parts:
        ctx = build_context(pkg, part)
        root = pkg.xml(part)

        bg = background_fill(background_element(root), ctx)
        if bg.color is not None:
            uses.append(ColorUse(bg.color.hex, bg.color.scheme_slot, "bg", 1.0, part))

        for shape in pkg.shapes(part):
            weight = shape.area / slide_area
            sp_pr, style = shape.sp_pr(), shape.style()

            fill = shape_fill(sp_pr, style, ctx)
            if fill.color is not None and fill.kind != "none":
                uses.append(ColorUse(fill.color.hex, fill.color.scheme_slot,
                                     "fill", weight, part))
            for stop in fill.stops[1:]:
                uses.append(ColorUse(stop.hex, stop.scheme_slot, "fill",
                                     weight * 0.5, part))

            if (line := line_color(sp_pr, style, ctx)) is not None:
                uses.append(ColorUse(line.hex, line.scheme_slot, "line",
                                     weight * 0.2, part))

            uses.extend(_text_uses(shape, ctx, part))
    return uses


def _master_background(pkg: Package) -> tuple[str, str]:
    """Цвет фона мастера и его происхождение."""
    master = pkg.masters[0] if pkg.masters else None
    if master is None:
        return "#FFFFFF", "default"
    ctx = build_context(pkg, master)
    fill = background_fill(background_element(pkg.xml(master)), ctx)
    if fill.color is not None:
        slot = fill.color.scheme_slot
        return fill.color.hex, f"theme.{slot}" if slot else "master.bg"
    fallback = ctx.clr_map.get("bg1", "lt1")
    return ctx.scheme.get(fallback, "#FFFFFF"), f"theme.{fallback}"


def _weighted(uses: list[ColorUse], contexts: set[str]) -> Counter:
    totals: Counter = Counter()
    for use in uses:
        if use.context in contexts:
            totals[use.hex] += use.weight
    return totals


def _slot_usage(uses: list[ColorUse]) -> Counter:
    counter: Counter = Counter()
    for use in uses:
        if use.slot:
            counter[use.slot] += 1
    return counter


def extract_palette(pkg: Package) -> Palette:
    master = pkg.masters[0] if pkg.masters else pkg.presentation_part
    ctx = build_context(pkg, master)
    scheme = ctx.scheme
    uses = collect_uses(pkg)

    page_bg, bg_origin = _master_background(pkg)
    is_dark = relative_luminance(page_bg) < 0.35

    roles: dict[str, str] = {"page_bg": page_bg}
    provenance: dict[str, str] = {"page_bg": bg_origin}

    # --- текст: основной и приглушённый ------------------------------------
    text_totals = _weighted(uses, {"text"})
    text_by_slot = {use.hex: use.slot for use in uses if use.context == "text"}
    readable = [(color, weight) for color, weight in text_totals.items()
                if contrast_ratio(color, page_bg) >= 3.0]
    readable.sort(key=lambda item: item[1], reverse=True)

    if readable:
        roles["text_primary"] = readable[0][0]
        provenance["text_primary"] = _origin(text_by_slot.get(readable[0][0]), "text")
    else:
        # В шаблоне из одной темы текста ещё нет, употребление подсказки не даёт.
        # Тема всегда предлагает пару «тёмное/светлое» — берём из неё то, что
        # читается на фоне, а не первое попавшееся.
        candidates = [(ctx.clr_map.get("tx1", "dk1"), scheme.get(ctx.clr_map.get("tx1", "dk1"), "")),
                      ("dk1", scheme.get("dk1", "")), ("lt1", scheme.get("lt1", "")),
                      ("dk2", scheme.get("dk2", "")), ("lt2", scheme.get("lt2", ""))]
        best = max(((slot, color) for slot, color in candidates if color),
                   key=lambda item: contrast_ratio(item[1], page_bg), default=None)
        roles["text_primary"] = best[1] if best else "#000000"
        provenance["text_primary"] = f"theme.{best[0]}" if best else "default"

    muted = next((color for color, _ in readable[1:]
                  if color != roles["text_primary"]
                  and contrast_ratio(color, page_bg) < contrast_ratio(roles["text_primary"], page_bg)),
                 None)
    if muted:
        roles["text_muted"] = muted
        provenance["text_muted"] = _origin(text_by_slot.get(muted), "text")

    # Текст поверх тёмных плашек и обложек — берём самый контрастный к акценту.
    inverse = "#FFFFFF" if is_dark else _pick_inverse(text_totals, page_bg)
    if inverse:
        roles["text_inverse"] = inverse
        provenance["text_inverse"] = "usage.text_on_dark"

    # --- акценты ------------------------------------------------------------
    slot_usage = _slot_usage(uses)
    accent_slots = [slot for slot, _ in slot_usage.most_common()
                    if slot.startswith("accent")]
    observed = _observed_accents(uses, page_bg, roles.get("text_primary", ""))

    theme_leads = bool(accent_slots) and _theme_accents_usable(scheme, accent_slots)
    if theme_leads:
        lead = accent_slots[0]
        roles["accent_primary"] = scheme.get(lead, "#000000")
        provenance["accent_primary"] = f"theme.{lead}"
        if len(accent_slots) > 1:
            roles["accent_secondary"] = scheme.get(accent_slots[1], "")
            provenance["accent_secondary"] = f"theme.{accent_slots[1]}"
    elif observed:
        # Тема бесполезна: акценты в ней либо не используются, либо совпадают
        # между собой (шаблон нарисован цветами прямо в фигурах). Тогда акцент —
        # это самый заметный цвет, которым шаблон действительно рисует.
        roles["accent_primary"] = observed[0]
        provenance["accent_primary"] = "usage.accent"
        if len(observed) > 1:
            roles["accent_secondary"] = observed[1]
            provenance["accent_secondary"] = "usage.accent"
    else:
        lead = accent_slots[0] if accent_slots else "accent1"
        roles["accent_primary"] = scheme.get(lead, "#000000")
        provenance["accent_primary"] = f"theme.{lead}"

    # --- подложка -----------------------------------------------------------
    fill_totals = _weighted(uses, {"fill"})
    fill_by_slot = {use.hex: use.slot for use in uses if use.context == "fill"}
    for color, _ in fill_totals.most_common():
        slot = fill_by_slot.get(color)
        if color == page_bg or (slot and slot.startswith("accent")):
            continue
        if contrast_ratio(color, page_bg) > 4.5:      # это не подложка, а плашка-контраст
            continue
        roles["surface"] = color
        provenance["surface"] = _origin(slot, "fill")
        break

    theme_seq = [scheme[f"accent{i}"] for i in range(1, 7) if f"accent{i}" in scheme]
    # Ряд для серий графика берётся оттуда же, откуда ведущий акцент: если тема
    # шаблоном не используется, её палитра раскрасит серии чужими цветами.
    accent_seq = theme_seq if theme_leads and len(set(theme_seq)) > 1 else (
        observed or theme_seq)

    backgrounds = _layout_backgrounds(pkg)

    return Palette(
        theme=scheme,
        roles={key: value for key, value in roles.items() if value},
        role_provenance=provenance,
        accent_seq=accent_seq,
        usage={slot: count for slot, count in slot_usage.most_common()},
        observed=_palette_colors(uses),
        is_dark=is_dark,
        backgrounds=backgrounds,
    )


def _origin(slot: str | None, context: str) -> str:
    return f"theme.{slot}" if slot else f"usage.{context}"


# Сколько цветов шаблона запоминаем: больше — уже не палитра, а гистограмма.
PALETTE_LIMIT = 24
# Насколько цвет должен быть насыщен, чтобы сойти за акцент, а не за серый.
ACCENT_SATURATION = 0.25
# Насколько акцент обязан отличаться от фона и основного текста.
ACCENT_DISTANCE = 0.12


def _saturation(hex_color: str) -> float:
    """Насыщенность по HSL: у серого и белого — ноль."""
    red, green, blue = hex_to_rgb(hex_color)
    high, low = max(red, green, blue), min(red, green, blue)
    if high == low:
        return 0.0
    lightness = (high + low) / 2
    return (high - low) / (2 - high - low if lightness > 0.5 else high + low)


def _distance(first: str, second: str) -> float:
    """Грубое расстояние между цветами — достаточно, чтобы отличить оттенки."""
    if not first or not second:
        return 1.0
    return max(abs(a - b) for a, b in zip(hex_to_rgb(first), hex_to_rgb(second)))


def _theme_accents_usable(scheme: dict[str, str], accent_slots: list[str]) -> bool:
    """Различает ли тема свои акценты.

    У шаблонов, выгруженных из других редакторов, тема остаётся заготовкой: все
    акценты одинаковые (часто просто белые). Опираться на такую тему нельзя —
    ведущим акцентом окажется цвет фона.
    """
    colors = {scheme.get(slot, "") for slot in accent_slots}
    colors.discard("")
    return len(colors) > 1


def _observed_accents(uses: list[ColorUse], page_bg: str, text: str) -> list[str]:
    """Заметные цвета шаблона: чем крупнее пятно, тем выше в списке."""
    totals: Counter = Counter()
    for use in uses:
        if use.context in ("fill", "line", "text"):
            totals[use.hex] += use.weight

    accents: list[str] = []
    for color, _ in totals.most_common():
        if _saturation(color) < ACCENT_SATURATION:
            continue
        if _distance(color, page_bg) < ACCENT_DISTANCE:
            continue
        if text and _distance(color, text) < ACCENT_DISTANCE:
            continue
        if any(_distance(color, chosen) < ACCENT_DISTANCE for chosen in accents):
            continue                                   # оттенок уже взятого
        accents.append(color)
        if len(accents) >= 6:
            break
    return accents


def _palette_colors(uses: list[ColorUse]) -> list[str]:
    """Все цвета, которыми шаблон нарисован, по убыванию заметности.

    Нужны нормоконтролю: цвет, пришедший из фигуры шаблона, обязан считаться
    «своим», даже если в теме документа его нет.
    """
    totals: Counter = Counter()
    for use in uses:
        totals[use.hex] += use.weight
    return [color for color, _ in totals.most_common(PALETTE_LIMIT)]


def _pick_inverse(text_totals: Counter, page_bg: str) -> str | None:
    """Цвет текста, который шаблон использует поверх тёмных плашек."""
    candidates = [color for color in text_totals
                  if relative_luminance(color) > 0.7 and contrast_ratio(color, page_bg) < 3.0]
    return candidates[0] if candidates else None


def _layout_backgrounds(pkg: Package) -> list[dict]:
    """Какие фоны встречаются у макетов — обложки часто отличаются от остальных."""
    grouped: dict[tuple[str, str], list[str]] = defaultdict(list)
    for part in pkg.layouts:
        ctx = build_context(pkg, part)
        fill = background_fill(background_element(pkg.xml(part)), ctx)
        if fill.kind == "inherit":
            continue
        key = (fill.kind, fill.hex or "")
        grouped[key].append(pkg.name_of(part))

    return [{"kind": kind, "color": color, "layouts": names}
            for (kind, color), names in sorted(grouped.items(),
                                               key=lambda item: -len(item[1]))]
