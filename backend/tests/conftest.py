from __future__ import annotations

import os
import sys
import tempfile
from pathlib import Path

import pytest

BACKEND = Path(__file__).resolve().parents[1]
PROJECT = BACKEND.parent
TEMPLATES = PROJECT / "templates" / "deck"

# Песочница для хранилища задач — ДО импорта sd.api: его store.clear() сносит
# свой корень целиком, и без изоляции прогон тестов удалял бы собранные
# пользователем проекты из боевого data/api.
os.environ.setdefault("SD_DATA_DIR", tempfile.mkdtemp(prefix="sd-api-tests-"))

if str(BACKEND) not in sys.path:
    sys.path.insert(0, str(BACKEND))

from sd.ooxml.package import Package          # noqa: E402
from sd.template.analyze import analyze_template  # noqa: E402


def template_paths() -> list[Path]:
    if not TEMPLATES.exists():
        return []
    return sorted(p for p in TEMPLATES.iterdir() if p.suffix.lower() in {".pptx", ".potx"})


ALL_TEMPLATES = template_paths()

requires_templates = pytest.mark.skipif(
    not ALL_TEMPLATES,
    reason="нет шаблонов: запустите `python templates/fetch_local.py`",
)


@pytest.fixture(scope="session", params=[p.name for p in ALL_TEMPLATES])
def template_path(request) -> Path:
    return TEMPLATES / request.param


@pytest.fixture(scope="session")
def design_systems() -> dict[str, object]:
    """Разбор всех шаблонов один раз на сессию — анализ детерминирован."""
    return {path.name: analyze_template(path) for path in ALL_TEMPLATES}


@pytest.fixture()
def package(template_path: Path) -> Package:
    return Package.open(template_path)
