"""Инварианты разбора шаблона.

Золотых файлов здесь нет намеренно: решение должно работать на любом шаблоне,
поэтому проверяем свойства результата, а не конкретные значения. Отдельный
тест следит за главным требованием кейса — что разные шаблоны дают разные
дизайн-системы, то есть анализ действительно читает файл.
"""

from __future__ import annotations

import io
import re

import pytest
from conftest import ALL_TEMPLATES, requires_templates

from sd.ooxml.color import contrast_ratio
from sd.ooxml.package import Package
from sd.ooxml.shapes import iter_shapes

HEX = re.compile(r"^#[0-9A-F]{6}$")

pytestmark = requires_templates


# --- пакет ---------------------------------------------------------------

def test_package_structure(package: Package):
    width, height = package.slide_size
    assert width > 0 and height > 0
    assert package.masters, "у шаблона должен быть хотя бы один мастер"
    assert package.layouts, "у шаблона должны быть макеты"
    for layout in package.layouts:
        assert package.master_of(layout), f"макет {layout} без мастера"
        assert package.theme_of(layout), f"макет {layout} без темы"


def test_potx_opens_as_pptx(package: Package):
    """`.potx` отличается от `.pptx` одной строкой content-type — умеем подменять."""
    from pptx import Presentation

    presentation = Presentation(io.BytesIO(package.as_pptx_bytes()))
    assert len(presentation.slide_layouts) > 0


def test_shapes_have_absolute_coordinates(package: Package):
    width, height = package.slide_size
    for part in package.layouts:
        for shape in iter_shapes(package.xml(part), part):
            assert shape.x > -width and shape.y > -height, "координаты вне разумного диапазона"
            assert shape.cx >= 0 and shape.cy >= 0


# --- дизайн-система ------------------------------------------------------

def test_palette_is_complete(design_systems, template_path):
    palette = design_systems[template_path.name].palette
    assert len(palette.theme) >= 10, "в теме должны быть все слоты"
    assert all(HEX.match(color) for color in palette.theme.values())
    assert palette.roles.get("page_bg") and palette.roles.get("text_primary")
    assert palette.accent_seq, "нужен порядок акцентов для серий графиков"


def test_primary_text_is_readable_on_page(design_systems, template_path):
    """Основной текст обязан читаться на основном фоне — иначе роль выбрана неверно."""
    palette = design_systems[template_path.name].palette
    ratio = contrast_ratio(palette.roles["text_primary"], palette.roles["page_bg"])
    assert ratio >= 3.0, f"контраст {ratio:.1f}:1"


def test_every_role_has_provenance(design_systems, template_path):
    """Без источника в шаблоне значение появляться не должно."""
    palette = design_systems[template_path.name].palette
    for role in palette.roles:
        assert palette.role_provenance.get(role), f"роль {role} без провенанса"


def test_typography_has_title_and_body(design_systems, template_path):
    typo = design_systems[template_path.name].typography
    assert typo.fonts.major and typo.fonts.minor
    assert "title" in typo.styles
    title = typo.styles["title"]
    assert title.size_pt and 8 <= title.size_pt <= 200
    assert typo.scale_pt == sorted(typo.scale_pt, reverse=True)
    body = typo.styles.get("body_l1")
    if body and body.size_pt:
        assert body.size_pt <= title.size_pt, "тело крупнее заголовка — цепочка стилей сломана"


def test_geometry_is_sane(design_systems, template_path):
    geo = design_systems[template_path.name].geometry
    for side, value in geo.margins.items():
        assert 0.0 <= value < 0.5, f"поле {side} = {value}"
    x, y, w, h = geo.safe_area
    assert w > 0.3 and h > 0.05, "безопасная зона схлопнулась"
    assert 0 <= x and 0 <= y and x + w <= 1.001 and y + h <= 1.001
    assert 1 <= geo.columns.count <= 24
    assert geo.guides_x and geo.guides_y, "не найдено ни одной направляющей"


def test_decor_is_inside_slide(design_systems, template_path):
    for item in design_systems[template_path.name].decor.items:
        x, y, w, h = item.bbox
        assert w >= 0 and h >= 0
        assert -0.5 <= x <= 1.5 and -0.5 <= y <= 1.5


def test_serialises_to_json(design_systems, template_path):
    payload = design_systems[template_path.name].model_dump(mode="json", by_alias=True)
    assert payload["source"]["sha256"]
    assert payload["palette"]["theme"]


# --- главное требование кейса -------------------------------------------

@pytest.mark.skipif(len(ALL_TEMPLATES) < 2, reason="нужно минимум два шаблона")
def test_templates_produce_different_design_systems(design_systems):
    """Если бы стиль был зашит, дизайн-системы совпали бы. Они обязаны отличаться."""
    signatures = {}
    for name, design in design_systems.items():
        signatures[name] = (
            tuple(sorted(design.palette.theme.values())),
            design.typography.fonts.major,
            round(design.geometry.margins.get("l", 0), 3),
        )
    palettes = {signature[0] for signature in signatures.values()}
    fonts = {signature[1] for signature in signatures.values()}
    assert len(palettes) >= len(design_systems) - 1, "палитры шаблонов совпадают"
    assert len(fonts) >= 2, "все шаблоны свелись к одному шрифту"


@pytest.mark.skipif(len(ALL_TEMPLATES) < 2, reason="нужно минимум два шаблона")
def test_analysis_is_deterministic():
    """Повторный разбор того же файла обязан дать тот же JSON."""
    from sd.template.analyze import analyze_template

    path = ALL_TEMPLATES[0]
    first = analyze_template(path).model_dump(mode="json", by_alias=True)
    second = analyze_template(path).model_dump(mode="json", by_alias=True)
    assert first == second


# --- палитра шаблонов с инлайновыми цветами ----------------------------------

def test_observed_colors_are_collected(design_systems, template_path):
    """Палитра помнит, чем шаблон нарисован, а не только его тему."""
    palette = design_systems[template_path.name].palette
    assert palette.observed, "не собран ни один цвет шаблона"
    assert all(color.startswith("#") for color in palette.observed)


def test_accent_never_equals_page_background(design_systems, template_path):
    """Ведущий акцент, совпавший с фоном, — признак пустой темы, а не дизайна."""
    palette = design_systems[template_path.name].palette
    accent = palette.roles.get("accent_primary")
    if accent:
        assert accent.upper() != palette.roles["page_bg"].upper()


def test_accent_sequence_has_distinct_colors(design_systems, template_path):
    """Серии графика нельзя раскрасить одним цветом."""
    sequence = design_systems[template_path.name].palette.accent_seq
    if len(sequence) > 1:
        assert len(set(sequence)) > 1, "весь ряд акцентов одного цвета"


def test_theme_wins_when_it_is_real(design_systems):
    """У шаблона с настоящей темой акцент по-прежнему берётся из неё."""
    named = [name for name in design_systems if "Ion" in name]
    if not named:
        pytest.skip("нет шаблона из темы оформления")
    palette = design_systems[named[0]].palette
    assert palette.role_provenance["accent_primary"].startswith("theme.")
