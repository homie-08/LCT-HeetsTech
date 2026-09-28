"""Нормоконтроль: метрики, визуальные проверки, цикл ремонта."""

from __future__ import annotations

from pathlib import Path

import pytest
from conftest import ALL_TEMPLATES, PROJECT, requires_templates

from sd.content import parse_content
from sd.content.parse import summarize
from sd.plan import build_plan, match_deck
from sd.qa import VisualInspector, build_with_repair
from sd.template.analyze import analyze_template

CONTENT = PROJECT / "data" / "content" / "product"

pytestmark = [requires_templates,
              pytest.mark.skipif(not CONTENT.exists(), reason="нет демо-контента")]

needs_renderer = pytest.mark.skipif(not VisualInspector.available(),
                                    reason="нет ни PowerPoint, ни LibreOffice")


@pytest.fixture(scope="module")
def ir():
    return parse_content(CONTENT)


def _build(template: Path, ir, tmp_path: Path, rounds: int = 0, visual: bool = False):
    design = analyze_template(template)
    spec = match_deck(build_plan(ir, client=None), design, ir)
    return build_with_repair(design, spec, ir, template,
                             tmp_path / f"{template.stem}.pptx",
                             rounds=rounds, visual=visual, work_dir=tmp_path / "qa")


# --- разбор контента ---------------------------------------------------------

def test_summarize_cuts_on_sentence_boundary():
    """Регресс: подзаголовок резался ровно на 120 знаков, посреди слова."""
    text = ("Единая среда для сквозной работы с документами: приём, распознавание, "
            "маршрутизация и контроль сроков. Заменяет связку из четырёх систем.")
    result = summarize(text)
    assert result.endswith("сроков.")
    assert "…" not in result


def test_summarize_falls_back_to_word_boundary():
    long_sentence = "слово " * 60
    result = summarize(long_sentence, limit=50)
    assert len(result) <= 51 and result.endswith("…")
    assert not result[:-1].endswith(" ")


# --- статические метрики -----------------------------------------------------

def test_style_comes_only_from_template(template_path, ir, tmp_path):
    """Главное обещание кейса, выраженное числом."""
    _, report, _ = _build(template_path, ir, tmp_path)
    assert report.metrics.font_conformance == 1.0
    assert report.metrics.palette_conformance == 1.0


def test_content_is_covered(template_path, ir, tmp_path):
    _, report, _ = _build(template_path, ir, tmp_path)
    assert report.metrics.coverage >= 0.6, report.metrics.summary()


def test_patterns_are_varied(template_path, ir, tmp_path):
    _, report, _ = _build(template_path, ir, tmp_path)
    assert report.metrics.pattern_diversity >= 0.4


def test_report_serialises(template_path, ir, tmp_path):
    _, report, _ = _build(template_path, ir, tmp_path)
    payload = report.model_dump(mode="json")
    assert payload["metrics"]["slides"] > 0
    assert isinstance(payload["defects"], list)


# --- визуальные проверки и ремонт -------------------------------------------

@needs_renderer
def test_repair_loop_leaves_no_visual_errors(ir, tmp_path):
    _, report, _ = _build(ALL_TEMPLATES[0], ir, tmp_path, rounds=2, visual=True)
    visual_errors = [defect for defect in report.errors
                     if defect.kind in ("overflow", "stray", "collision")]
    assert not visual_errors, [str(defect) for defect in visual_errors]
    assert report.metrics.contrast_pass >= 0.8


@needs_renderer
def test_repair_does_not_make_things_worse(ir, tmp_path):
    _, before, _ = _build(ALL_TEMPLATES[0], ir, tmp_path / "a", rounds=0, visual=True)
    _, after, _ = _build(ALL_TEMPLATES[0], ir, tmp_path / "b", rounds=2, visual=True)
    assert len(after.errors) <= len(before.errors)


@needs_renderer
def test_cache_hit_still_fills_output_directory(tmp_path):
    """Регресс: при попадании в кеш каталог назначения оставался старым."""
    from sd.render import render_deck

    deck = tmp_path / "deck.pptx"
    design = analyze_template(ALL_TEMPLATES[0])
    ir = parse_content(CONTENT)
    spec = match_deck(build_plan(ir, client=None), design, ir)
    build_with_repair(design, spec, ir, ALL_TEMPLATES[0], deck, rounds=0, visual=False)

    first = render_deck(deck, tmp_path / "first", 480)
    second_dir = tmp_path / "second"
    second = render_deck(deck, second_dir, 480)

    assert "кеш" in second.note
    assert len(list(second_dir.glob("slide-*.png"))) == len(first.images)
