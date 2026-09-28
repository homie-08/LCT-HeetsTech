"""HTTP-интерфейс: загрузка шаблона, сборка, отчёт, скачивание."""

from __future__ import annotations

import io
import time
from pathlib import Path

import pytest
from conftest import ALL_TEMPLATES, PROJECT, requires_templates
from fastapi.testclient import TestClient

from sd.api import app, store

CONTENT = PROJECT / "data" / "content" / "product"

pytestmark = [requires_templates,
              pytest.mark.skipif(not CONTENT.exists(), reason="нет демо-контента")]


@pytest.fixture(scope="module")
def client():
    with TestClient(app) as test_client:
        yield test_client
    store.clear()


def _wait(client: TestClient, url: str, timeout: float = 600) -> dict:
    """Фоновая задача в TestClient выполняется синхронно, но опрос честнее."""
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        payload = client.get(url).json()
        if payload["status"] in ("ready", "failed"):
            return payload
        time.sleep(0.5)
    raise AssertionError(f"{url}: не дождались готовности")


@pytest.fixture(scope="module")
def template(client):
    path = ALL_TEMPLATES[0]
    response = client.post("/api/templates",
                           files={"file": (path.name, path.read_bytes())})
    assert response.status_code == 200
    return _wait(client, f"/api/templates/{response.json()['id']}")


def test_status_reports_environment(client):
    payload = client.get("/api/status").json()
    assert "llm" in payload and isinstance(payload["renderers"], list)


def test_template_analysis_is_exposed(template):
    assert template["status"] == "ready", template.get("error")
    assert template["palette"]["theme"]
    assert template["typography"]["fonts"]["major"]
    assert len(template["patterns"]) >= 3
    for pattern in template["patterns"]:
        assert pattern["archetype"] and pattern["slots"]


def test_rejects_foreign_file(client):
    response = client.post("/api/templates",
                           files={"file": ("notes.txt", b"hello")})
    assert response.status_code == 400


def test_unknown_ids_are_404(client):
    assert client.get("/api/templates/нет").status_code == 404
    assert client.get("/api/decks/нет").status_code == 404


def test_deck_is_built_and_downloadable(client, template):
    files = [("files", (path.name, path.read_bytes()))
             for path in sorted(CONTENT.iterdir()) if path.is_file()]
    response = client.post("/api/decks", data={"template_id": template["id"],
                                               "use_llm": "false"}, files=files)
    assert response.status_code == 200
    deck = _wait(client, f"/api/decks/{response.json()['id']}")
    assert deck["status"] == "ready", deck.get("error")
    assert len(deck["slides"]) >= 5
    assert deck["metrics"]["font_conformance"] == 1.0

    for slide in deck["slides"]:
        assert slide["pattern"] and slide["why"]

    download = client.get(deck["download"])
    assert download.status_code == 200
    assert download.content[:2] == b"PK"                 # это zip, то есть pptx

    from pptx import Presentation

    presentation = Presentation(io.BytesIO(download.content))
    assert len(presentation.slides) == len(deck["slides"])


def test_slide_previews_available_when_rendered(client, template):
    from sd.render import available_backends

    if not available_backends():
        pytest.skip("нет рендерера")
    deck_id = next(job.id for job in store.list("deck"))
    payload = client.get(f"/api/decks/{deck_id}").json()
    image_urls = [slide["image"] for slide in payload["slides"] if slide["image"]]
    assert image_urls, "рендер есть, а превью слайдов не отдаются"
    assert client.get(image_urls[0]).headers["content-type"] == "image/png"


def test_three_layout_variants_come_from_one_job(client):
    """ТЗ: три варианта вёрстки одного контента на одном шаблоне.

    Различаются плотностью — числом слайдов и мыслей на слайде, — но все три
    собраны из макетов одного шаблона и скачиваются по отдельности.
    """
    deck_id = next(job.id for job in store.list("deck"))
    payload = client.get(f"/api/decks/{deck_id}").json()
    variants = payload["variants"]
    assert [item["id"] for item in variants] == ["compact", "balanced", "spacious"]

    counts = {item["id"]: len(item["slides"]) for item in variants}
    assert counts["compact"] <= counts["balanced"] <= counts["spacious"]
    assert counts["compact"] < counts["spacious"], "варианты не различаются"

    densest = max(len(slide["key_message"]) for slide in variants[0]["slides"])
    assert densest > 0
    for item in variants:
        assert item["metrics"]["font_conformance"] == 1.0, "вариант отступил от шрифтов шаблона"
        download = client.get(item["download"])
        assert download.status_code == 200 and download.content[:2] == b"PK"
        assert item["skills"].get("planner", 0) >= 1

    # Основные поля задачи — это сбалансированный вариант.
    assert payload["variant"] == "balanced"
    assert payload["download"].endswith("variant=balanced")


def test_audit_findings_are_addressed_and_selected_ones_get_repaired(client):
    """ТЗ: аудит показывает находки, пользователь выбирает, что чинить.

    Каждая находка несёт природу (детерминированная/контекстуальная), группу
    и признак исправимости; исправимые пересобираются ужатым бюджетом.
    """
    deck_id = next(job.id for job in store.list("deck"))
    payload = client.get(f"/api/decks/{deck_id}").json()
    balanced = next(item for item in payload["variants"] if item["id"] == "balanced")
    assert set(balanced["checks"]) >= {"out_of_bounds", "overlap", "placeholder_text",
                                       "unsourced_number", "fill_ratio"}
    assert "title_not_conclusion" in balanced["skipped_checks"]   # без модели

    for defect in balanced["defects"]:
        assert defect["nature"] in ("deterministic", "contextual")
        assert defect["id"] and defect["group"]

    fixable = [defect for defect in balanced["defects"] if defect["fixable"]]
    if not fixable:
        # Нечего чинить — проверяем, что сервис так и отвечает, а не молчит.
        response = client.post(f"/api/decks/{deck_id}/repair",
                               data={"variant": "balanced", "defects": "нет"})
        assert response.status_code == 400
        return

    response = client.post(f"/api/decks/{deck_id}/repair",
                           data={"variant": "balanced",
                                 "defects": ",".join(defect["id"] for defect in fixable[:2])})
    assert response.status_code == 200
    assert response.json()["slides"]
    repaired = _wait(client, f"/api/decks/{deck_id}")
    assert repaired["status"] == "ready"
    entry = next(item for item in repaired["variants"] if item["id"] == "balanced")
    assert entry["repaired"] == response.json()["slides"]
    assert any("ремонт по выбору" in note for note in entry["notes"])
