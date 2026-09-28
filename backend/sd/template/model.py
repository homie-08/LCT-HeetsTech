"""Типы дизайн-системы шаблона.

Это контракт между анализатором шаблона и всем, что идёт дальше: планировщиком,
укладчиком, сборщиком и нормоконтролем. Модели pydantic, потому что тот же тип
уезжает в JSON, в API и в тесты.

Соглашение по координатам: всё, что описывает положение, хранится в **долях
стороны слайда** `[x, y, w, h]`, 0..1. Абсолютные EMU остаются внутри анализатора —
так дизайн-система не зависит от формата слайда (4:3 против 16:9).
"""

from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, Field

Bbox = list[float]  # [x, y, w, h] в долях слайда

Archetype = Literal[
    "cover", "section", "agenda", "bullets", "two_column", "comparison",
    "metrics", "process", "table", "chart", "quote", "image_full",
    "image_text", "gallery", "team", "contacts", "blank",
]

SlotRole = Literal[
    "title", "subtitle", "kicker", "body", "item", "metric_value", "metric_label",
    "quote", "author", "image", "chart", "table", "footer", "caption", "number",
    "diagram",
]


class Provenance(BaseModel):
    """Откуда в шаблоне взято значение. Без источника значение не появляется."""

    value: str
    origin: str = Field(alias="from")

    model_config = {"populate_by_name": True}


class SlideSize(BaseModel):
    w_emu: int
    h_emu: int
    ratio: str


class Source(BaseModel):
    file: str
    sha256: str
    slide_size: SlideSize
    masters: int = 1
    layouts: int = 0
    example_slides: int = 0


class Palette(BaseModel):
    theme: dict[str, str] = Field(default_factory=dict)
    """Слоты темы как есть: dk1, lt1, dk2, lt2, accent1..6, hlink, folHlink."""

    roles: dict[str, str] = Field(default_factory=dict)
    """Роли, выведенные из фактического употребления: page_bg, text_primary, …"""

    role_provenance: dict[str, str] = Field(default_factory=dict)
    """Для каждой роли — слот темы или контекст, откуда она взята."""

    accent_seq: list[str] = Field(default_factory=list)
    """Порядок акцентов для серий графиков — как в теме."""

    usage: dict[str, int] = Field(default_factory=dict)
    """Сколько раз слот темы фактически использован в шаблоне."""

    observed: list[str] = Field(default_factory=list)
    """Цвета, которыми шаблон действительно нарисован, по убыванию заметности.

    У шаблонов, свёрстанных вручную или выгруженных из другого редактора, цвета
    прописаны прямо в фигурах, а тема остаётся пустой заготовкой. Тогда палитра
    шаблона — это не его тема, а вот этот список.
    """

    is_dark: bool = False
    """Тёмная ли основа: влияет на выбор начертания текста поверх фона."""

    backgrounds: list[dict] = Field(default_factory=list)

    def color(self, role_or_slot: str) -> str | None:
        return self.roles.get(role_or_slot) or self.theme.get(role_or_slot)


class Bullet(BaseModel):
    char: str | None = None
    font: str | None = None
    color: str | None = None
    indent: float = 0.0        # доля ширины слайда
    kind: Literal["none", "char", "auto_num", "picture"] = "none"


class TextStyle(BaseModel):
    font: str | None = None
    size_pt: float | None = None
    bold: bool = False
    italic: bool = False
    caps: Literal["none", "all", "small"] = "none"
    color: str | None = None
    color_slot: str | None = None
    align: Literal["l", "ctr", "r", "just"] = "l"
    line_spacing: float | None = None
    space_before_pt: float = 0.0
    space_after_pt: float = 0.0
    bullet: Bullet | None = None
    provenance: str = ""


class Fonts(BaseModel):
    major: str = ""
    minor: str = ""
    embedded: list[str] = Field(default_factory=list)
    fallback: dict[str, str] = Field(default_factory=dict)
    used: list[str] = Field(default_factory=list)
    """Все начертания, встречающиеся в шаблоне, — включая декоративные.

    Пара темы описывает замысел, но дизайнер мог поставить рукописный шрифт на
    одном слайде-примере. При клонировании такого слайда он попадает в результат,
    и это по-прежнему шрифт шаблона, а не наш.
    """


class Typography(BaseModel):
    fonts: Fonts = Field(default_factory=Fonts)
    scale_pt: list[float] = Field(default_factory=list)
    styles: dict[str, TextStyle] = Field(default_factory=dict)


class Columns(BaseModel):
    count: int = 12
    gutter: float = 0.02
    width: float = 0.0


class Geometry(BaseModel):
    margins: dict[str, float] = Field(default_factory=dict)
    columns: Columns = Field(default_factory=Columns)
    guides_x: list[float] = Field(default_factory=list)
    guides_y: list[float] = Field(default_factory=list)
    safe_area: Bbox = Field(default_factory=lambda: [0.05, 0.05, 0.9, 0.9])
    gaps: dict[str, float] = Field(default_factory=dict)


class DecorItem(BaseModel):
    kind: Literal["logo", "bar", "shape", "picture", "line"]
    bbox: Bbox
    fill: str | None = None
    image: str | None = None
    scope: list[str] = Field(default_factory=list)
    geom: str | None = None


class Decor(BaseModel):
    items: list[DecorItem] = Field(default_factory=list)
    shape_style: dict = Field(default_factory=dict)


class Capacity(BaseModel):
    chars: int = 0
    lines: int = 1


class Slot(BaseModel):
    role: SlotRole
    bbox: Bbox
    style: str = "body_l1"
    """Ссылка на стиль дизайн-системы — эталон роли."""

    size_pt: float | None = None
    """Фактический кегль именно этого слота: макет может отличаться от эталона."""

    font: str | None = None
    bold: bool = False
    """Начертание именно этого слота: стикер жирный, хотя стиль роли — нет."""

    ph_type: str | None = None
    ph_idx: int | None = None
    group: str | None = None
    index: int = 0
    capacity: Capacity = Field(default_factory=Capacity)
    required: bool = False
    shape_id: int | None = None


class RepeatGroup(BaseModel):
    group: str
    min: int = 1
    max: int = 1
    step: dict[str, float] = Field(default_factory=dict)


class Pattern(BaseModel):
    id: str
    archetype: Archetype
    source_kind: Literal["layout", "slide"]
    source_name: str
    source_part: str
    render_mode: Literal["use_layout", "clone_slide"]
    layout_part: str | None = None
    slots: list[Slot] = Field(default_factory=list)
    repeat: RepeatGroup | None = None
    accepts: dict = Field(default_factory=dict)
    fit: dict = Field(default_factory=dict)
    confidence: float = 0.0
    evidence: list[str] = Field(default_factory=list)
    preview: str | None = None

    def slots_by_role(self, role: str) -> list[Slot]:
        return [s for s in self.slots if s.role == role]


class DesignSystem(BaseModel):
    source: Source
    palette: Palette = Field(default_factory=Palette)
    typography: Typography = Field(default_factory=Typography)
    geometry: Geometry = Field(default_factory=Geometry)
    decor: Decor = Field(default_factory=Decor)
    patterns: list[Pattern] = Field(default_factory=list)
    warnings: list[str] = Field(default_factory=list)

    def pattern(self, pattern_id: str) -> Pattern | None:
        return next((p for p in self.patterns if p.id == pattern_id), None)
