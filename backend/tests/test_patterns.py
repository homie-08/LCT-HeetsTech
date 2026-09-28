"""Библиотека паттернов: структура, ёмкость слотов, классификация."""

from __future__ import annotations

import pytest
from conftest import ALL_TEMPLATES, requires_templates

from sd.fit.textmetrics import capacity_chars, metrics_for

pytestmark = requires_templates


def test_patterns_extracted(design_systems, template_path):
    patterns = design_systems[template_path.name].patterns
    assert len(patterns) >= 3, "с шаблона снялось меньше трёх раскладок"
    assert len({pattern.id for pattern in patterns}) == len(patterns), "id не уникальны"


def test_every_pattern_slot_is_visible(design_systems, template_path):
    """Слот должен быть виден на слайде.

    Выход за край сам по себе нормален — фотографии часто «в обрез», — но слот,
    который виден меньше чем наполовину, это припаркованная за холстом заготовка.
    """
    for pattern in design_systems[template_path.name].patterns:
        assert pattern.slots, f"паттерн {pattern.id} без слотов"
        for slot in pattern.slots:
            x, y, w, h = slot.bbox
            assert w > 0 and h > 0, f"{pattern.id}/{slot.role} нулевого размера"
            visible = (max(0.0, min(x + w, 1.0) - max(x, 0.0))
                       * max(0.0, min(y + h, 1.0) - max(y, 0.0)))
            assert visible >= 0.5 * w * h, f"{pattern.id}/{slot.role} почти вне слайда"


def test_text_slots_have_capacity(design_systems, template_path):
    """Без ёмкости укладчик не сможет решить, влезает ли текст."""
    for pattern in design_systems[template_path.name].patterns:
        for slot in pattern.slots:
            if slot.role in ("image", "chart", "table"):
                continue
            assert slot.capacity.chars > 0, f"{pattern.id}/{slot.role} без ёмкости"
            assert slot.capacity.lines >= 1


def test_repeat_groups_are_consistent(design_systems, template_path):
    for pattern in design_systems[template_path.name].patterns:
        if pattern.repeat is None:
            continue
        members = [slot for slot in pattern.slots if slot.group == pattern.repeat.group]
        assert len(members) == pattern.repeat.max >= 2
        assert sorted(slot.index for slot in members) == list(range(len(members)))
        step = pattern.repeat.step
        assert abs(step.get("dx", 0)) > 0 or abs(step.get("dy", 0)) > 0


def test_structural_archetypes_are_found(design_systems, template_path):
    """В любом нормальном шаблоне есть обложка или разделитель."""
    archetypes = {pattern.archetype for pattern in design_systems[template_path.name].patterns}
    assert archetypes & {"cover", "section"}, f"не найдено ни обложки, ни раздела: {archetypes}"


def test_classification_is_explained(design_systems, template_path):
    for pattern in design_systems[template_path.name].patterns:
        assert pattern.evidence, f"паттерн {pattern.id} без объяснения выбора"
        assert 0.0 <= pattern.confidence <= 1.0


def test_slot_styles_exist_in_typography(design_systems, template_path):
    design = design_systems[template_path.name]
    for pattern in design.patterns:
        for slot in pattern.slots:
            assert slot.style in design.typography.styles or slot.style == "body_l1", \
                f"{pattern.id}: стиль {slot.style} отсутствует в дизайн-системе"


@pytest.mark.skipif(len(ALL_TEMPLATES) < 2, reason="нужно минимум два шаблона")
def test_capacity_depends_on_template(design_systems):
    """Ёмкость заголовка считается по шрифту и кеглю шаблона, а не константой."""
    capacities = {}
    for name, design in design_systems.items():
        titles = [slot for pattern in design.patterns
                  for slot in pattern.slots_by_role("title")]
        if titles:
            capacities[name] = max(slot.capacity.chars for slot in titles)
    assert len(set(capacities.values())) > 1, f"ёмкость одинакова везде: {capacities}"


def test_capacity_matches_direct_measurement(design_systems, template_path):
    """Сверяем ёмкость слота с прямым расчётом по метрикам шрифта."""
    design = design_systems[template_path.name]
    width, height = design.source.slide_size.w_emu, design.source.slide_size.h_emu
    checked = 0
    for pattern in design.patterns:
        for slot in pattern.slots_by_role("title"):
            style = design.typography.styles.get(slot.style)
            if not slot.size_pt or not style:
                continue
            metrics = metrics_for(slot.font or style.font or "", style.bold, style.italic)
            expected, _ = capacity_chars(int(slot.bbox[2] * width), int(slot.bbox[3] * height),
                                         metrics, slot.size_pt, style.line_spacing, style.caps)
            assert abs(expected - slot.capacity.chars) <= max(2, expected * 0.35)
            checked += 1
    if checked == 0:
        pytest.skip("в шаблоне нет слотов заголовка")


def test_cyrillic_is_wider_than_latin():
    """Ради этого и нужны настоящие метрики: лимит символов зависит от языка."""
    metrics = metrics_for("Calibri")
    assert metrics.text_width("Платформа сокращает", 18) > metrics.text_width("Platform reduces", 18)
