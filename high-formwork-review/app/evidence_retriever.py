"""从 ParsedDocument 中召回参数抽取证据。"""

from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Any

from .completeness_review import _find_terms, _index_blocks
from .models import MinerUBlock, MinerUDocument, MinerUPage


@dataclass
class ParameterEvidence:
    page: MinerUPage
    block: MinerUBlock
    section_path: list[str]
    source_role: str
    evidence_quality: str
    score: float
    is_toc: bool = False


def retrieve_parameter_evidence(
    parsed_document: MinerUDocument,
    parameter_definition: dict[str, Any],
    top_k: int = 20,
) -> list[ParameterEvidence]:
    aliases = [str(item) for item in parameter_definition.get("aliases", [])]
    preferred_sections = [
        str(item) for item in parameter_definition.get("preferred_sections", [])
    ]
    expected_block_types = set(parameter_definition.get("expected_block_types", []))
    expected_block_types.add("table_continuation")
    results: list[ParameterEvidence] = []

    for page, block, section_path, is_toc in _index_blocks(parsed_document):
        if block.block_type in {"title", "page_number"}:
            continue
        if expected_block_types and block.block_type not in expected_block_types:
            continue

        text = _evidence_text(block)
        alias_hits = _find_terms(text, aliases)
        section_hits = _find_terms(" / ".join(section_path), preferred_sections)
        has_numeric = bool(re.search(r"\d+(?:\.\d+)?\s*(?:mm|cm|m|毫米|厘米|米)?", text, re.I))
        if not alias_hits and not section_hits:
            continue
        if is_toc and not alias_hits:
            continue

        score = 0.0
        score += 5.0 if alias_hits else 0.0
        score += 2.0 if section_hits else 0.0
        score += 1.0 if has_numeric else 0.0
        score += 1.5 if block.block_type in {"table", "table_continuation"} else 0.5
        if is_toc:
            score -= 5.0
        source_role = _source_role(block, section_path)
        quality = "high" if block.block_type in {"table", "table_continuation"} and alias_hits else "medium"
        if is_toc:
            quality = "low"
        results.append(
            ParameterEvidence(
                page=page,
                block=block,
                section_path=section_path,
                source_role=source_role,
                evidence_quality=quality,
                score=score,
                is_toc=is_toc,
            )
        )

    results.sort(key=lambda item: item.score, reverse=True)
    return results[:top_k]


def _evidence_text(block: MinerUBlock) -> str:
    if block.block_type in {"table", "table_continuation"}:
        return "\n".join(part for part in (block.text, block.table_html or "") if part)
    return block.text


def _source_role(block: MinerUBlock, section_path: list[str]) -> str:
    path = " / ".join(section_path)
    if "目录" in path:
        return "toc"
    if block.block_type in {"table", "table_continuation"}:
        return "parameter_table"
    if "计算" in path or "验算" in path:
        return "calculation"
    return "body"
