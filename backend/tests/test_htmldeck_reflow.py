"""Подгонка собранной колоды по месту — измерением, а не оценкой по знакам.

Сколько текста влезет в слот, по длине образца шаблона не узнать: та же
подпись в узкой карточке займёт вчетверо больше строк, чем в широкой. Оценка
поэтому перестраховывается и обрывает фразу там, где место ещё было.
"""

from __future__ import annotations

import re
from pathlib import Path

import pytest
from lxml import html as lxml_html

from sd.content.parse import parse_text, summarize
from sd.htmldeck import parse_template
from sd.htmldeck.build import _fit, build_deck
from sd.htmldeck.export import find_browser
from sd.htmldeck.parse import Slot
from sd.htmldeck.reflow import Fix, apply
from sd.plan.storyline import build_plan

PACKAGE = Path(__file__).resolve().parents[2] / "templates" / "incoming" / "package"
DECK = PACKAGE / "03 Dark Tech.dc.html"

pytestmark = pytest.mark.skipif(not DECK.exists(), reason="нет пакета шаблонов")


def _slot(sample: str = "Короткий образец", font: float = 30) -> Slot:
    return Slot(path="0", role="body", sample=sample, font_px=font, bold=False)


def test_estimate_does_not_cut_when_layout_will_check():
    """С браузером фраза остаётся целой: резать будет измерение."""
    text = "Скольжение саней происходит под действием скатывающей силы. " * 3
    kept = _fit(text, _slot(), cut=False)
    assert kept.text == text
    assert kept.over, "длину всё равно надо отметить — её увидит модель"
    assert not kept.cut

    guessed = _fit(text, _slot(), cut=True)
    assert guessed.text != text and guessed.cut


def test_fixes_land_by_node_address():
    """Правки возвращаются адресами узлов и находят те же места, что и слоты."""
    section = lxml_html.fromstring(
        '<section><div><p style="font-size:30px">Очень длинная подпись</p></div></section>')
    shrunk, trimmed = apply([section], [Fix(slide=0, path="0/0", size=19.5, limit=12)])
    node = section.find("div/p")
    assert (shrunk, trimmed) == (1, 1)
    assert "font-size:19.5px" in node.get("style")
    assert len(node.text) <= 12


def test_fix_for_a_missing_slide_is_ignored():
    section = lxml_html.fromstring("<section><p>текст</p></section>")
    assert apply([section], [Fix(slide=7, path="0", size=20, limit=0)]) == (0, 0)


def test_summary_ends_on_a_clause():
    """Обрыв посреди оборота читается как сбой вёрстки, а не как сокращение."""
    text = ("Когда говорят о трении, различают три несколько отличных физических "
            "явления: сопротивление, возникающее при движении тела в жидкости или "
            "газе – его называют жидким трением; сопротивление, возникающее, когда "
            "тело катится по неподвижной опоре.")
    short = summarize(text, 200)
    assert short.endswith("…")
    assert short.rstrip("…").endswith("жидким трением"), short
    assert "когда" not in short, "оборван посреди придаточного"


@pytest.mark.skipif(find_browser() is None, reason="нет браузера для подгонки")
def test_layout_fits_what_the_estimate_would_have_cut():
    """Полный проход: с подгонкой текста на слайдах больше, а обрывов меньше.

    Проверка идёт на одном и том же контенте и шаблоне — разница только в том,
    кто решает, влезло ли: счёт по знакам или сама вёрстка.
    """
    # Каждый абзац — одно предложение, заведомо короче потолка планировщика:
    # проверяется именно укладка, а не его собственное сокращение.
    sentence = ("Трение сопровождает всякое движение соприкасающихся тел и "
                "определяет разгон, торможение и устойчивость спортсмена")
    assert len(sentence) < 200
    paragraphs = "\n\n".join(f"{sentence} в случае {number}." for number in range(1, 4))
    ir = parse_text("# Сила трения\n\n"
                    + "".join(f"## Раздел {number}\n\n{paragraphs}\n\n"
                              for number in range(1, 5)))
    plan = build_plan(ir, None)
    template = parse_template(DECK)

    guessed = build_deck(template, plan, ir, PACKAGE / "test-guessed.dc.html",
                         reflow=False)
    measured = build_deck(template, plan, ir, PACKAGE / "test-measured.dc.html",
                          reflow=True)
    try:
        before = _ellipses(guessed.path)
        after = _ellipses(measured.path)
        assert before, "нечего проверять — оценка ничего не обрезала"
        assert after < before, f"подгонка не помогла: было {before}, стало {after}"
    finally:
        guessed.path.unlink(missing_ok=True)
        measured.path.unlink(missing_ok=True)


def _ellipses(path: Path) -> int:
    source = path.read_text(encoding="utf-8")
    return sum(1 for chunk in source.split("<section")[1:]
               for text in re.split(r"<[^>]+>", re.sub(r"<svg.*?</svg>", "", chunk, flags=re.S))
               if text.strip().endswith("…"))
