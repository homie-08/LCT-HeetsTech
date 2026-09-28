"""Три варианта вёрстки одного контента: ось — плотность.

ТЗ просит три визуально различимых варианта, одинаково верных правилам
шаблона. Здесь закреплено, чем именно они различаются (число слайдов, число
мыслей на слайде, разделители, предпочтения матчера) и чем не различаются:
шаблон, контент и правила укладки у всех одни.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from sd.content.parse import parse_text
from sd.plan import build_plan, variants
from sd.plan.model import DeckPlan, SlidePlan
from sd.plan.storyline import _chunks, apply_variant

CONTENT = Path(__file__).resolve().parents[2] / "data" / "content" / "product"


def _ir():
    return parse_text((CONTENT / "product.md").read_text(encoding="utf-8"))


def test_three_variants_with_distinct_density():
    ids = [variant.id for variant in variants.all_variants()]
    assert ids == ["compact", "balanced", "spacious"]
    theses = [variant.max_theses for variant in variants.all_variants()]
    assert theses[0] > theses[1] > theses[2]
    assert variants.get(None).id == variants.DEFAULT == "balanced"
    with pytest.raises(KeyError):
        variants.get("dense")


@pytest.mark.skipif(not CONTENT.exists(), reason="нет демо-контента")
def test_slide_counts_grow_from_compact_to_spacious():
    ir = _ir()
    counts = {name: len(build_plan(ir, None, variant=name).slides) for name in variants.ORDER}
    assert counts["compact"] < counts["balanced"] < counts["spacious"]


@pytest.mark.skipif(not CONTENT.exists(), reason="нет демо-контента")
def test_every_variant_respects_its_thesis_limit():
    ir = _ir()
    for name in variants.ORDER:
        limit = variants.get(name).max_theses
        for slide in build_plan(ir, None, variant=name).slides:
            if slide.intent == "agenda":                # у содержания своя мера
                assert len(slide.items) <= variants.get(name).agenda_items
                continue
            assert len(slide.items) <= limit, f"{name}: слайд {slide.n} — {len(slide.items)} тезисов"


@pytest.mark.skipif(not CONTENT.exists(), reason="нет демо-контента")
def test_compact_has_no_agenda_and_spacious_has_dividers():
    ir = _ir()
    compact = [slide.intent for slide in build_plan(ir, None, variant="compact").slides]
    spacious = [slide.intent for slide in build_plan(ir, None, variant="spacious").slides]
    assert "agenda" not in compact
    assert "section" in spacious and "section" not in compact


@pytest.mark.skipif(not CONTENT.exists(), reason="нет демо-контента")
def test_variants_keep_cover_and_contacts_in_place():
    ir = _ir()
    for name in variants.ORDER:
        plan = build_plan(ir, None, variant=name)
        assert plan.slides[0].intent == "cover" and plan.slides[-1].intent == "contacts"
        assert plan.variant == name


def test_chunks_are_balanced_not_greedy():
    """Пять шагов при норме в четыре — 3 + 2, а не 4 + 1."""
    items = [f"шаг {number}" for number in range(1, 6)]
    assert [len(part) for part in _chunks(items, 4)] == [3, 2]
    assert [len(part) for part in _chunks(items, 2)] == [2, 2, 1]
    assert _chunks([], 3) == [[]]
    assert _chunks(items, 10) == [items]


def test_llm_plan_is_split_to_the_variant_density():
    """План модели один на все варианты; плотность наводится после него."""
    plan = DeckPlan(title="t", source="llm", slides=[
        SlidePlan(n=1, intent="cover", key_message="Тема"),
        SlidePlan(n=2, intent="bullets", key_message="Пять мыслей",
                  blocks=["b1"], items=[f"тезис {number}" for number in range(1, 6)]),
        SlidePlan(n=3, intent="bullets", key_message="Три мысли",
                  blocks=["b2"], items=["а", "б", "в"]),
        SlidePlan(n=4, intent="metrics", key_message="Цифры", blocks=["b3"],
                  items=["10 %", "20 %", "30 %", "40 %"]),
        SlidePlan(n=5, intent="contacts", key_message="Контакты", blocks=["b4"]),
    ])
    spacious = apply_variant(plan, variants.get("spacious"))
    intents = [slide.intent for slide in spacious.slides]
    # Запас — половина плана (5 → 8): тяжёлый слайд делится на три части и
    # получает разделитель, на слайд с тремя мыслями запаса уже нет; цифры и
    # контакты не делятся никогда.
    assert intents == ["cover", "section", "bullets", "bullets", "bullets",
                       "bullets", "metrics", "contacts"]
    parts = [slide for slide in spacious.slides
             if slide.key_message == "Пять мыслей" and slide.intent == "bullets"]
    assert [len(part.items) for part in parts] == [2, 2, 1]
    assert parts[0].blocks == ["b1"] and parts[1].blocks == [] and parts[1].notes == "продолжение"
    assert [slide.n for slide in spacious.slides] == list(range(1, 9))

    compact = apply_variant(plan, variants.get("compact"))
    assert [slide.intent for slide in compact.slides] == [
        "cover", "bullets", "bullets", "metrics", "contacts"]


def test_split_budget_spreads_over_the_heaviest_slides():
    """Двенадцать слайдов по пять тезисов — просторно даёт восемнадцать, а не тридцать."""
    plan = DeckPlan(title="t", source="llm", slides=[
        SlidePlan(n=1, intent="cover", key_message="Тема"),
        *[SlidePlan(n=number, intent="bullets", key_message=f"Часть {number}",
                    items=[f"тезис {i}" for i in range(5)]) for number in range(2, 12)],
        SlidePlan(n=12, intent="contacts", key_message="Контакты"),
    ])
    spacious = apply_variant(plan, variants.get("spacious"), target_slides=12)
    assert len(spacious.slides) == 15                                # потолок ТЗ
    assert sum(slide.intent == "section" for slide in spacious.slides) == 1
    assert max(len(slide.items) for slide in spacious.slides) == 5   # остальные — как есть

    balanced = apply_variant(plan, variants.get("balanced"), target_slides=12)
    assert len(balanced.slides) == 14                                # 12 × 1.2
    assert all(slide.intent != "section" for slide in balanced.slides)

    # Пользователь просил больше — потолок растёт вместе с его числом.
    wide = apply_variant(plan, variants.get("spacious"), target_slides=20)
    assert len(wide.slides) == 18                                    # 12 × 1.5 < 25


def test_matcher_density_term_follows_the_variant():
    from sd.plan.match import score
    from sd.template.model import Capacity, Pattern, Slot

    def pattern(places: int) -> Pattern:
        slots = [Slot(role="title", bbox=[0.05, 0.05, 0.9, 0.1], capacity=Capacity(chars=60))]
        slots += [Slot(role="item", bbox=[0.05 + 0.15 * index, 0.3, 0.14, 0.3],
                       capacity=Capacity(chars=80, lines=3)) for index in range(places)]
        return Pattern(id=f"p{places}", archetype="bullets", source_kind="slide",
                       source_name="s", source_part="s", render_mode="clone_slide", slots=slots)

    ir = parse_text("# Т\n\n## Р\n\nПервая мысль. Вторая мысль. Третья мысль.\n")
    slide = next(slide for slide in build_plan(ir, None).slides if slide.intent == "bullets")
    grid, single = pattern(6), pattern(1)
    compact = variants.get("compact")
    spacious = variants.get("spacious")
    assert score(grid, slide, ir, variant=compact).density > score(single, slide, ir, variant=compact).density
    assert score(grid, slide, ir, variant=spacious).density < score(single, slide, ir, variant=spacious).density
    assert score(grid, slide, ir, variant=variants.get("balanced")).density == 0.0
