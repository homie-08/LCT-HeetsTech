"""Разбор контента в Content IR."""

from __future__ import annotations

from pathlib import Path

import pytest
from conftest import PROJECT

from sd.content import parse_content
from sd.content.parse import _Counter, extract_metrics

CONTENT = PROJECT / "data" / "content" / "product"

pytestmark = pytest.mark.skipif(not CONTENT.exists(), reason="нет демо-контента")


@pytest.fixture(scope="module")
def ir():
    return parse_content(CONTENT)


def test_structure_is_recognised(ir):
    kinds = {block.type for block in ir.blocks}
    assert {"heading", "paragraph", "list", "steps", "table", "series",
            "quote", "contact", "metric"} <= kinds


def test_meta_detects_language_and_title(ir):
    assert ir.meta.language == "ru"
    assert ir.meta.title
    assert ir.meta.words > 100


def test_ids_are_unique(ir):
    ids = [block.id for block in ir.blocks]
    assert len(ids) == len(set(ids))


def test_series_has_numeric_columns(ir):
    series = ir.of_type("series")
    assert series, "числовые колонки таблицы должны стать рядом данных"
    block = series[0]
    assert block.x and block.y
    assert all(isinstance(value, float) for values in block.y.values() for value in values)


def test_table_keeps_header_and_rows(ir):
    table = ir.of_type("table")[0]
    assert len(table.header) >= 2 and table.rows


def test_metrics_are_derived_not_invented(ir):
    metrics = ir.of_type("metric")
    assert len(metrics) >= 4
    for metric in metrics:
        assert metric.derived_from, "метрика обязана ссылаться на исходный блок"
        assert ir.block(metric.derived_from) is not None
        assert metric.value and metric.label


def test_sections_exclude_derived_blocks(ir):
    for _, blocks in ir.sections():
        assert all(block.derived_from is None for block in blocks)


def test_sections_split_on_source_change(ir):
    """Данные из другого файла — свой раздел, а не хвост чужого заголовка."""
    for _, blocks in ir.sections():
        assert len({block.source for block in blocks}) <= 1


def test_metric_patterns():
    counter = _Counter()
    from sd.content.model import Block

    samples = Block(id="x", type="list", items=[
        "срок обработки сократился в 4 раза",
        "экономия — 45 млн ₽ в год",
        "доля ручного ввода упала до 8 %",
        "просто текст без чисел",
    ])
    metrics = extract_metrics([samples], counter)
    values = {metric.value for metric in metrics}
    assert len(metrics) == 3
    assert any("раза" in value for value in values)
    assert any("млн" in value for value in values)
    assert any("%" in value for value in values)


def test_plain_text_lists(tmp_path: Path):
    path = tmp_path / "note.txt"
    path.write_text("Заголовок\n\n- первый\n- второй\n- третий\n\nАбзац текста здесь.",
                    encoding="utf-8")
    ir = parse_content(path)
    assert [block.type for block in ir.blocks][:3] == ["heading", "list", "paragraph"]
    assert len(ir.blocks[1].items) == 3
