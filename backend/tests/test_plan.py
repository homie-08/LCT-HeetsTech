"""Планирование истории и подбор паттернов."""

from __future__ import annotations

import pytest
from conftest import ALL_TEMPLATES, PROJECT, requires_templates

from sd.content import parse_content
from sd.plan import affinity, build_plan, match_deck, plan_heuristic
from sd.template.analyze import analyze_template

CONTENT = PROJECT / "data" / "content" / "product"

pytestmark = pytest.mark.skipif(not CONTENT.exists(), reason="нет демо-контента")


@pytest.fixture(scope="module")
def ir():
    return parse_content(CONTENT)


@pytest.fixture(scope="module")
def plan(ir):
    return plan_heuristic(ir)


# --- план -----------------------------------------------------------------

def test_plan_starts_with_cover_and_ends_with_contacts(plan):
    assert plan.slides[0].intent == "cover"
    assert plan.slides[-1].intent == "contacts"
    assert [slide.n for slide in plan.slides] == list(range(1, len(plan.slides) + 1))


def test_plan_references_only_real_blocks(plan, ir):
    for slide in plan.slides:
        for block_id in slide.blocks:
            assert ir.block(block_id) is not None, f"слайд {slide.n}: нет блока {block_id}"


def test_plan_does_not_reuse_blocks(plan):
    used = [block_id for slide in plan.slides for block_id in slide.blocks]
    assert len(used) == len(set(used)), "один блок попал на несколько слайдов"


def test_plan_covers_the_content(plan, ir):
    """Значимый контент не должен молча пропасть из презентации."""
    used = {block_id for slide in plan.slides for block_id in slide.blocks}
    significant = [block for block in ir.blocks
                   if block.type in ("list", "steps", "table", "series", "quote")]
    covered = sum(1 for block in significant
                  if block.id in used
                  or any(metric.derived_from == block.id and metric.id in used
                         for metric in ir.of_type("metric")))
    assert covered >= len(significant) * 0.8


def test_target_slides_is_respected(ir):
    short = plan_heuristic(ir, target_slides=6)
    assert len(short.slides) <= 6
    assert short.slides[0].intent == "cover"


def test_build_plan_without_llm_falls_back(ir):
    assert build_plan(ir, client=None).source == "heuristic"


# --- подбор паттернов ------------------------------------------------------

@requires_templates
def test_every_slide_gets_a_pattern(plan, ir, design_systems, template_path):
    design = design_systems[template_path.name]
    spec = match_deck(plan, design, ir)
    assert len(spec.slides) == len(plan.slides)
    known = {pattern.id for pattern in design.patterns}
    for slide in spec.slides:
        assert slide.pattern_id in known
        assert slide.why, "выбор паттерна должен быть объяснён"


@requires_templates
def test_cover_slide_prefers_a_cover_pattern(plan, ir, design_systems, template_path):
    design = design_systems[template_path.name]
    if not any(pattern.archetype == "cover" for pattern in design.patterns):
        pytest.skip("в шаблоне нет обложки")
    spec = match_deck(plan, design, ir)
    chosen = design.pattern(spec.slides[0].pattern_id)
    assert chosen.archetype in ("cover", "section")


@requires_templates
def test_table_content_prefers_a_table_pattern(plan, ir, design_systems, template_path):
    design = design_systems[template_path.name]
    if not any(pattern.archetype == "table" for pattern in design.patterns):
        pytest.skip("в шаблоне нет паттерна таблицы")
    spec = match_deck(plan, design, ir)
    table_slides = [slide for slide in spec.slides if slide.plan.intent == "table"]
    if not table_slides:
        pytest.skip("в плане нет слайда с таблицей")
    assert design.pattern(table_slides[0].pattern_id).archetype == "table"


@pytest.mark.skipif(len(ALL_TEMPLATES) < 2, reason="нужно минимум два шаблона")
def test_same_plan_maps_differently_across_templates(plan, ir):
    """Главная проверка кейса на этом шаге: подбор зависит от шаблона."""
    signatures = {}
    for path in ALL_TEMPLATES[:3]:
        design = analyze_template(path)
        spec = match_deck(plan, design, ir)
        signatures[path.name] = tuple(
            design.pattern(slide.pattern_id).archetype for slide in spec.slides)
    assert len(set(signatures.values())) > 1, f"раскладка одинакова: {signatures}"


def test_affinity_prefers_exact_archetype():
    assert affinity("metrics", "metrics") == 1.0
    assert affinity("metrics", "two_column") < 1.0
    assert affinity("comparison", "two_column") > affinity("comparison", "gallery")
    assert affinity("bullets", "blank") < affinity("bullets", "two_column")
