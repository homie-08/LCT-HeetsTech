"""Промпты агентов — из файлов, не из кода.

Каждый промпт лежит в `backend/prompts/<id>.md`: шапка с версией и историей,
дальше — текст, который уходит модели. Код только загружает их по имени.
Версии попадают в отчёт сборки, чтобы по готовой презентации было видно,
какими агентами она собрана.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from functools import lru_cache
from pathlib import Path

PROMPTS_DIR = Path(__file__).resolve().parents[2] / "prompts"
FRONTMATTER_RE = re.compile(r"\A---\s*\n(.*?)\n---\s*\n", re.S)


@dataclass(frozen=True)
class Prompt:
    id: str
    version: int
    text: str
    purpose: str = ""
    schema: str = ""
    path: Path | None = None
    meta: dict[str, str] = field(default_factory=dict)

    @property
    def label(self) -> str:
        return f"{self.id} v{self.version}"


class PromptError(RuntimeError):
    """Файл промпта не найден или без обязательной шапки."""


@lru_cache(maxsize=32)
def load(name: str, directory: Path | None = None) -> Prompt:
    """Читает промпт по имени. Отсутствие файла — ошибка, а не пустая строка."""
    path = (directory or PROMPTS_DIR) / f"{name}.md"
    if not path.exists():
        raise PromptError(f"нет файла промпта: {path}")
    source = path.read_text(encoding="utf-8")
    match = FRONTMATTER_RE.match(source)
    if match is None:
        raise PromptError(f"у промпта {name} нет шапки с версией")

    meta: dict[str, str] = {}
    for line in match.group(1).splitlines():
        if ":" in line and not line.startswith((" ", "-")):
            key, _, value = line.partition(":")
            meta[key.strip()] = value.strip()
    if meta.get("id") != name:
        raise PromptError(f"в шапке {path.name} id «{meta.get('id')}», ожидался «{name}»")
    try:
        version = int(meta.get("version", ""))
    except ValueError as error:
        raise PromptError(f"у промпта {name} версия не число") from error

    return Prompt(id=name, version=version, text=source[match.end():].strip() + "\n",
                  purpose=meta.get("purpose", ""), schema=meta.get("schema", ""),
                  path=path, meta=meta)


def catalogue(directory: Path | None = None) -> list[Prompt]:
    """Все промпты каталога — для отчёта и `/api/status`."""
    folder = directory or PROMPTS_DIR
    return [load(path.stem, folder) for path in sorted(folder.glob("*.md"))
            if path.stem.lower() != "readme"]


def versions(directory: Path | None = None) -> dict[str, int]:
    return {prompt.id: prompt.version for prompt in catalogue(directory)}
