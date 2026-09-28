"""Content IR — единое представление входного контента.

Формат входа (md, docx, xlsx, txt) не должен просачиваться дальше парсера:
планировщик и укладчик работают с блоками. Блок — это минимальная смысловая
единица, которую можно целиком положить в один слот слайда.
"""

from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, Field

BlockType = Literal["heading", "paragraph", "list", "steps", "metric", "table",
                    "series", "quote", "image", "contact"]


class Asset(BaseModel):
    id: str
    path: str
    width: int = 0
    height: int = 0
    kind: Literal["photo", "logo", "diagram", "screenshot"] = "photo"
    caption: str = ""


class Block(BaseModel):
    id: str
    type: BlockType
    text: str = ""
    level: int = 1                                  # для heading
    items: list[str] = Field(default_factory=list)  # для list / steps
    value: str = ""                                 # для metric
    label: str = ""                                 # для metric / quote (автор)
    header: list[str] = Field(default_factory=list)
    rows: list[list[str]] = Field(default_factory=list)
    x: list[str] = Field(default_factory=list)       # подписи оси для series
    y: dict[str, list[float]] = Field(default_factory=dict)
    suggest: Literal["bar", "line", "pie", "column"] | None = None
    asset_id: str | None = None
    importance: float = 0.5
    source: str = ""                                 # откуда взято: файл/лист
    derived_from: str | None = None                  # id исходного блока

    @property
    def size(self) -> int:
        """Грубый объём блока в знаках — нужен и матчеру, и укладчику."""
        return (len(self.text) + sum(len(item) for item in self.items)
                + sum(len(cell) for row in self.rows for cell in row))

    def shape(self) -> str:
        """Форма контента — то, по чему подбирается паттерн."""
        if self.type == "list":
            return f"list:{len(self.items)}"
        if self.type == "steps":
            return f"steps:{len(self.items)}"
        if self.type == "table":
            return f"table:{len(self.rows)}x{len(self.header)}"
        if self.type == "series":
            return f"series:{len(self.y)}"
        return self.type


class ContentMeta(BaseModel):
    title: str = ""
    subtitle: str = ""
    language: str = "ru"
    words: int = 0
    sources: list[str] = Field(default_factory=list)


class ContentIR(BaseModel):
    meta: ContentMeta = Field(default_factory=ContentMeta)
    blocks: list[Block] = Field(default_factory=list)
    assets: list[Asset] = Field(default_factory=list)

    def block(self, block_id: str) -> Block | None:
        return next((b for b in self.blocks if b.id == block_id), None)

    def of_type(self, *types: str) -> list[Block]:
        return [b for b in self.blocks if b.type in types]

    def sections(self) -> list[tuple[Block | None, list[Block]]]:
        """Разбиение по заголовкам: (заголовок, блоки под ним).

        Производные блоки (метрики, вытащенные из текста) в разбиение не входят:
        они не занимают своё место в документе и относятся к исходному блоку.
        """
        result: list[tuple[Block | None, list[Block]]] = []
        current_heading: Block | None = None
        current: list[Block] = []
        current_source = ""

        for block in self.blocks:
            if block.derived_from:
                continue
            # Данные из отдельного файла — самостоятельный раздел, а не хвост
            # последнего заголовка соседнего документа.
            new_source = bool(current) and block.source != current_source
            if block.type == "heading" or new_source:
                if current_heading is not None or current:
                    result.append((current_heading, current))
                current, current_source = [], block.source
                current_heading = block if block.type == "heading" else None
                if block.type == "heading":
                    continue
            current.append(block)
            current_source = block.source
        if current_heading is not None or current:
            result.append((current_heading, current))
        return result
