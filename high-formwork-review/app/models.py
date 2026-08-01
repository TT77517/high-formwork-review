"""项目使用的全部数据模型。

这些模型只描述数据，不负责读取 MinerU 文件或执行审查。
"""

from __future__ import annotations

from dataclasses import dataclass, field


@dataclass
class BoundingBox:
    x0: float
    y0: float
    x1: float
    y1: float


@dataclass
class MinerUBlock:
    block_id: str
    physical_page: int
    block_index: int
    block_type: str
    text: str
    title_level: int | None
    bbox: BoundingBox | None
    image_path: str | None
    table_html: str | None
    source_file: str
    source_pointer: str


@dataclass
class MinerUPage:
    physical_page: int
    source_page_index: int
    width: float | None
    height: float | None
    printed_page: str | None
    page_type: str
    parse_status: str
    text: str
    blocks: list[MinerUBlock] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)
    requires_human_review: bool = False


@dataclass
class MinerUSection:
    section_id: str
    title: str
    level: int
    path: list[str]
    physical_page_start: int
    physical_page_end: int


@dataclass
class MinerUDocument:
    document_id: str
    source_file_name: str
    source_sha256: str
    physical_page_count: int
    pages: list[MinerUPage] = field(default_factory=list)
    sections: list[MinerUSection] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)
    requires_human_review: bool = False


@dataclass
class ReviewEvidence:
    physical_page: int
    printed_page: str | None
    section_path: list[str]
    block_id: str
    block_type: str
    quote: str
    description: str
    bbox: BoundingBox | None
    image_path: str | None
    table_html: str | None
    source_pointer: str


@dataclass
class CompletenessResult:
    rule_id: str
    name: str
    status: str
    reason: str
    evidence: list[ReviewEvidence] = field(default_factory=list)
    requires_human_review: bool = False
    confidence: float | None = None
    needs_semantic_review: bool = False
    semantic_review_reason: str | None = None


@dataclass
class CompletenessSummary:
    total_rules: int
    pass_count: int
    missing_count: int
    uncertain_count: int
    results: list[CompletenessResult] = field(default_factory=list)
