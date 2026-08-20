"""ProjectFacts 构建入口。"""

from __future__ import annotations

import json
import logging
from pathlib import Path
from typing import Any

from .evidence_retriever import retrieve_parameter_evidence
from .fact_conflict_detector import resolve_fact
from .models import MinerUDocument
from .parameter_definitions import get_parameter_definitions
from .parameter_extractor import extract_parameter_candidates
from .parameter_normalizer import normalize_candidate


logger = logging.getLogger(__name__)


def build_project_facts(parsed_document: MinerUDocument) -> dict[str, Any]:
    facts: dict[str, Any] = {}
    definitions = get_parameter_definitions()
    for definition in definitions:
        parameter = str(definition["parameter"])
        try:
            evidence = retrieve_parameter_evidence(parsed_document, definition)
            candidates = extract_parameter_candidates(evidence, definition)
            normalized = [
                normalize_candidate(candidate, definition.get("canonical_unit"))
                for candidate in candidates
            ]
            fact = resolve_fact(definition, normalized)
            facts[parameter] = fact
            values = [item.get("value") for item in normalized if item.get("value") is not None]
            logger.info(
                "parameter=%s candidates=%s normalized_values=%s status=%s",
                parameter,
                len(normalized),
                values,
                fact["status"],
            )
        except Exception as exc:  # pragma: no cover - defensive continuity
            facts[parameter] = {
                "value": None,
                "unit": definition.get("canonical_unit"),
                "raw_value": None,
                "status": "uncertain",
                "confidence": None,
                "candidates": [],
                "evidence": [],
                "source_role": None,
                "has_conflict": False,
                "requires_human_review": True,
                "error": str(exc),
            }
            logger.warning("parameter=%s status=uncertain error=%s", parameter, exc)
    return {
        "project_id": parsed_document.document_id,
        "source_file_name": parsed_document.source_file_name,
        "facts": facts,
    }


def build_project_facts_debug(
    parsed_document: MinerUDocument,
    parameter_ids: set[str] | None = None,
) -> dict[str, Any]:
    debug: dict[str, Any] = {}
    for definition in get_parameter_definitions():
        parameter = str(definition["parameter"])
        if parameter_ids is not None and parameter not in parameter_ids:
            continue
        evidence = retrieve_parameter_evidence(parsed_document, definition)
        candidates = extract_parameter_candidates(evidence, definition)
        normalized = [
            normalize_candidate(candidate, definition.get("canonical_unit"))
            for candidate in candidates
        ]
        debug[parameter] = [
            {
                "raw_value": item.get("raw_value"),
                "normalized_value": item.get("value"),
                "unit": item.get("unit"),
                "page": (item.get("evidence") or {}).get("physical_page"),
                "block_id": (item.get("evidence") or {}).get("block_id"),
                "block_type": (item.get("evidence") or {}).get("block_type"),
                "section": " / ".join((item.get("evidence") or {}).get("section_path") or []),
                "source_role": item.get("source_role"),
                "text": (item.get("evidence") or {}).get("text"),
                "confidence": item.get("confidence"),
                "context_tags": [
                    tag
                    for tag in ("standard_value", "design_value", "combination", "normative_limit")
                    if _tag_applies(tag, str((item.get("evidence") or {}).get("text") or ""))
                ],
                "possible_reason": item.get("normalization_error") or item.get("evidence_quality"),
            }
            for item in normalized
        ]
    return debug


def write_project_facts(parsed_document: MinerUDocument, output_dir: str | Path) -> Path:
    path = Path(output_dir) / "project_facts.json"
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps(build_project_facts(parsed_document), ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )
    return path


def write_project_facts_debug(
    parsed_document: MinerUDocument,
    output_dir: str | Path,
    parameter_ids: set[str] | None = None,
) -> Path:
    path = Path(output_dir) / "project_facts_debug"
    path.mkdir(parents=True, exist_ok=True)
    debug = build_project_facts_debug(parsed_document, parameter_ids)
    for parameter, candidates in debug.items():
        (path / f"{parameter}_candidates.json").write_text(
            json.dumps(candidates, ensure_ascii=False, indent=2) + "\n",
            encoding="utf-8",
        )
    return path


def _tag_applies(tag: str, text: str) -> bool:
    terms = {
        "standard_value": ("标准值",),
        "design_value": ("设计值",),
        "combination": ("组合", "1.4", "1.5"),
        "normative_limit": ("不得", "不应", "不小于", "不得小于"),
    }
    return any(term in text for term in terms[tag])
