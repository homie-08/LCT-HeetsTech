"""Матрица «один контент × N шаблонов» — главная демонстрация адаптивности."""

from __future__ import annotations

import pytest
from conftest import ALL_TEMPLATES, PROJECT, requires_templates

from sd.matrix import run_matrix

CONTENT = PROJECT / "data" / "content" / "product"

pytestmark = [requires_templates,
              pytest.mark.skipif(not CONTENT.exists(), reason="нет демо-контента"),
              pytest.mark.skipif(len(ALL_TEMPLATES) < 2, reason="нужно два шаблона")]


@pytest.fixture(scope="module")
def matrix(tmp_path_factory):
    out = tmp_path_factory.mktemp("matrix")
    templates = out / "templates"
    templates.mkdir()
    for path in ALL_TEMPLATES[:3]:
        (templates / path.name).write_bytes(path.read_bytes())
    # Без рендера: проверяем логику сравнения, а не картинки.
    return run_matrix(CONTENT, templates, out, render=False, progress=lambda *_: None), out


def test_every_template_is_built(matrix):
    (_, _, entries), out = matrix
    assert len(entries) == 3
    for entry in entries:
        assert not entry.error, entry.error
        assert entry.deck.exists()
        assert len(entry.patterns) > 3
    assert (out / "index.html").exists()


def test_plan_is_shared_across_templates(matrix):
    """Ключевая гарантия: план один, значит различия — от шаблона."""
    (_, plan, entries), _ = matrix
    for entry in entries:
        assert len(entry.patterns) == len(plan.slides)


def test_templates_choose_different_layouts(matrix):
    (_, _, entries), _ = matrix
    signatures = {entry.template.name: tuple(entry.patterns) for entry in entries}
    assert len(set(signatures.values())) > 1, signatures


def test_report_mentions_every_template(matrix):
    (_, _, entries), out = matrix
    report = (out / "index.html").read_text(encoding="utf-8")
    for entry in entries:
        assert entry.template.name in report
    assert "построен один раз" in report
    assert "Нормоконтроль" in report


def test_style_conformance_holds_everywhere(matrix):
    (_, _, entries), _ = matrix
    for entry in entries:
        assert entry.report.metrics.font_conformance == 1.0
        assert entry.report.metrics.palette_conformance == 1.0
