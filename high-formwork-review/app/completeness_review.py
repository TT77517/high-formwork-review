"""基于 MinerUDocument 执行完整性审查并生成证据核验报告。"""

from __future__ import annotations

import json
import re
from pathlib import Path
from typing import Any

from .models import (
    CompletenessResult,
    CompletenessSummary,
    MinerUBlock,
    MinerUDocument,
    MinerUPage,
    MinerUSection,
    ReviewEvidence,
)

IndexedBlock = tuple[MinerUPage, MinerUBlock, list[str], bool]

_DRAWING_SECTION_TERMS = (
    "相关图纸",
    "施工图纸",
    "附图",
    "节点图",
    "支模架布置图",
)
_DRAWING_TITLE_TERMS = (
    "平面图",
    "剖面图",
    "节点图",
    "立面图",
    "布置图",
    "支撑图",
)
_DRAWING_REFERENCE_TERMS = ("附图", "见图", "详见图纸")
_DRAWING_EVIDENCE_PAGE_LIMIT = 8


_SEMANTIC_CONFIDENCE_THRESHOLD = 0.70
_HIGH_CONFIDENCE = 0.80


def load_rules(path: str | Path) -> list[dict[str, Any]]:
    """读取规则并做最小结构校验。"""
    rule_path = Path(path)
    try:
        data = json.loads(rule_path.read_text(encoding="utf-8"))
    except FileNotFoundError as exc:
        raise ValueError(f"规则文件不存在：{rule_path}") from exc
    except json.JSONDecodeError as exc:
        raise ValueError(
            f"规则 JSON 格式错误：第 {exc.lineno} 行第 {exc.colno} 列"
        ) from exc

    if not isinstance(data, list):
        raise ValueError("规则文件顶层必须是列表")
    required = {
        "rule_id",
        "name",
        "section_aliases",
        "text_terms",
        "accepted_block_types",
        "accepted_page_types",
        "minimum_matches",
        "minimum_subitems",
        "mandatory_subitems",
        "required_subitems",
    }
    for index, rule in enumerate(data):
        if not isinstance(rule, dict):
            raise ValueError(f"第 {index + 1} 条规则不是 JSON 对象")
        missing = required - set(rule)
        if missing:
            raise ValueError(
                f"规则 {rule.get('rule_id', index + 1)} 缺少字段："
                + "、".join(sorted(missing))
            )
        if not isinstance(rule["required_subitems"], list):
            raise ValueError(f"规则 {rule['rule_id']} 的 required_subitems 必须是列表")
        for subitem in rule["required_subitems"]:
            if not isinstance(subitem, dict) or not {"id", "name", "terms"} <= set(
                subitem
            ):
                raise ValueError(
                    f"规则 {rule['rule_id']} 的必要子项必须包含 id、name、terms"
                )
    return data


def review_completeness(
    document: MinerUDocument, rules: list[dict[str, Any]]
) -> CompletenessSummary:
    """保持原有调用方式，只返回完整性汇总。"""
    summary, _ = review_completeness_with_details(document, rules)
    return summary


def review_completeness_with_details(
    document: MinerUDocument, rules: list[dict[str, Any]]
) -> tuple[CompletenessSummary, list[dict[str, Any]]]:
    """返回审查汇总和生成核验报告所需的同源明细。"""
    indexed_blocks = _index_blocks(document)
    evaluated = [
        _evaluate_rule(document, rule, indexed_blocks) for rule in rules
    ]
    results = [item[0] for item in evaluated]
    details = [item[1] for item in evaluated]
    summary = CompletenessSummary(
        total_rules=len(results),
        pass_count=sum(result.status == "PASS" for result in results),
        missing_count=sum(result.status == "MISSING" for result in results),
        uncertain_count=sum(result.status == "UNCERTAIN" for result in results),
        results=results,
    )
    return summary, details


def build_evidence_check_markdown(
    document: MinerUDocument,
    summary: CompletenessSummary,
    details: list[dict[str, Any]],
) -> str:
    """把审查明细渲染为便于人工复核的 Markdown。"""
    lines = [
        "# 完整性审查证据核验报告",
        "",
        f"- physical_page_count: {document.physical_page_count}",
        f"- section_count: {len(document.sections)}",
        f"- PASS: {summary.pass_count}",
        f"- MISSING: {summary.missing_count}",
        f"- UNCERTAIN: {summary.uncertain_count}",
        "",
    ]
    page_by_number = {page.physical_page: page for page in document.pages}

    for detail in details:
        lines.extend(
            [
                f"## {detail['rule_id']} {detail['name']}",
                "",
                f"- rule_id: {detail['rule_id']}",
                f"- name: {detail['name']}",
                f"- status: {detail['status']}",
                f"- reason: {detail['reason']}",
                "- matched_sections:",
            ]
        )
        if detail["matched_sections"]:
            for section in detail["matched_sections"]:
                lines.append(
                    "  - "
                    f"{section['title']} | level={section['level']} | "
                    f"pages={section['physical_page_start']}-"
                    f"{section['physical_page_end']}"
                )
        else:
            lines.append("  - 无")

        lines.extend(
            [
                "- physical_pages: "
                + (_join_values(detail["physical_pages"]) or "无"),
                "- printed_pages: "
                + (_join_values(detail["printed_pages"]) or "无"),
                "- matched_terms: "
                + ("、".join(detail["matched_terms"]) or "无"),
                "- matched_subitems:",
            ]
        )
        for subitem in detail["matched_subitems"]:
            state = "已满足" if subitem["satisfied"] else "未满足"
            terms = "、".join(subitem["matched_terms"]) or "无"
            pages = _join_values(subitem["physical_pages"]) or "无"
            lines.append(
                f"  - [{state}] {subitem['name']} | "
                f"matched_terms={terms} | physical_pages={pages}"
            )

        lines.extend(
            [
                "- requires_human_review: "
                + ("true" if detail["requires_human_review"] else "false"),
            ]
        )
        if detail["status"] == "PASS":
            satisfied_names = [
                item["name"]
                for item in detail["matched_subitems"]
                if item["satisfied"]
            ]
            lines.append(
                "- PASS 判定说明: 满足必要子项："
                + "、".join(satisfied_names)
                + f"；达到 {len(satisfied_names)}/"
                f"{len(detail['matched_subitems'])}；因此判定 PASS。"
            )

        lines.extend(
            [
                "",
                "| physical_page | printed_page | section_path | "
                "evidence block type | evidence quote 或 description | "
                "image_path | table_html 是否存在 | page_type | parse_status | "
                "whether_from_toc | requires_human_review |",
                "|---:|---|---|---|---|---|---|---|---|---|---|",
            ]
        )
        if not detail["evidence"]:
            lines.append("| 无 | 无 | 无 | 无 | 无 | 无 | 否 | 无 | 无 | false | false |")
        else:
            for evidence in detail["evidence"]:
                page = page_by_number.get(evidence.physical_page)
                from_toc = bool(
                    page and any("目录页" in warning for warning in page.warnings)
                )
                quote = evidence.quote or evidence.description or "无"
                lines.append(
                    "| "
                    + " | ".join(
                        [
                            str(evidence.physical_page),
                            _md(evidence.printed_page or "无"),
                            _md(" / ".join(evidence.section_path) or "无"),
                            _md(evidence.block_type),
                            _md(quote),
                            _md(evidence.image_path or "无"),
                            "是" if bool((evidence.table_html or "").strip()) else "否",
                            _md(page.page_type if page else "无"),
                            _md(page.parse_status if page else "无"),
                            "true" if from_toc else "false",
                            "true"
                            if bool(page and page.requires_human_review)
                            else "false",
                        ]
                    )
                    + " |"
                )
        lines.append("")
    return "\n".join(lines).rstrip() + "\n"


def _evaluate_rule(
    document: MinerUDocument,
    rule: dict[str, Any],
    indexed_blocks: list[IndexedBlock],
) -> tuple[CompletenessResult, dict[str, Any]]:
    rule_id = str(rule["rule_id"])
    name = str(rule["name"])
    if rule_id == "HF-COMP-010":
        return _evaluate_drawing_rule(document, rule, indexed_blocks)

    aliases = _string_list(rule["section_aliases"])
    rule_terms = _string_list(rule["text_terms"])
    accepted_blocks = set(_string_list(rule["accepted_block_types"]))
    accepted_pages = set(_string_list(rule["accepted_page_types"]))
    subitems = [dict(item) for item in rule["required_subitems"]]
    minimum_subitems = max(1, int(rule["minimum_subitems"]))
    mandatory_subitems = set(_string_list(rule["mandatory_subitems"]))

    matching_sections = _matching_sections(document, rule_id, aliases)
    section_found = bool(matching_sections)
    states = {
        str(item["id"]): {
            "id": str(item["id"]),
            "name": str(item["name"]),
            "terms": _string_list(item.get("terms", [])),
            "all_evidence": [],
            "confirming_evidence": [],
            "matched_terms": set(),
        }
        for item in subitems
    }
    all_subitem_terms = [
        term for item in subitems for term in _string_list(item.get("terms", []))
    ]
    all_relevant_terms = list(dict.fromkeys(aliases + rule_terms + all_subitem_terms))
    title_evidence: list[ReviewEvidence] = []
    toc_evidence: list[ReviewEvidence] = []
    related_evidence: list[ReviewEvidence] = []
    risky_evidence: list[ReviewEvidence] = []
    risky_pages_seen: set[int] = set()

    for page, block, section_path, is_toc in indexed_blocks:
        path_text = " / ".join(section_path)
        in_target_section = _is_target_text(rule_id, path_text, aliases)
        found_relevant_terms = _find_terms(block.text, all_relevant_terms)

        if is_toc:
            if found_relevant_terms:
                toc_evidence.append(
                    _evidence(
                        page,
                        block,
                        section_path,
                        "仅在目录页命中，不能作为正文完整性证据",
                    )
                )
            continue

        if block.block_type == "title":
            if in_target_section:
                title_evidence.append(
                    _evidence(page, block, section_path, "命中正文 section 标题")
                )
            elif not section_found and found_relevant_terms:
                related_evidence.append(
                    _evidence(page, block, section_path, "找到标题线索但未形成目标 section")
                )
            continue

        if section_found and not in_target_section:
            if rule_id == "HF-COMP-010" and block.block_type in {"image", "chart"}:
                related_evidence.append(
                    _evidence(
                        page,
                        block,
                        section_path,
                        "找到图片，但不在相关施工图纸 section 中，关联不足",
                    )
                )
            continue

        if not section_found:
            if found_relevant_terms or (
                rule_id == "HF-COMP-010"
                and block.block_type in {"image", "chart"}
            ):
                related_evidence.append(
                    _evidence(
                        page,
                        block,
                        section_path,
                        "找到相关内容，但没有目标正文 section",
                    )
                )
            continue

        if (
            page.parse_status != "complete"
            and page.physical_page not in risky_pages_seen
        ):
            risky_pages_seen.add(page.physical_page)
            risky_evidence.append(
                _evidence(
                    page,
                    block,
                    section_path,
                    f"目标章节页面解析状态为 {page.parse_status}",
                )
            )

        matched_any_subitem = False
        for subitem in subitems:
            matched_terms = _subitem_match(
                block,
                page,
                subitem,
                accepted_blocks,
                accepted_pages,
            )
            if matched_terms is None:
                continue
            matched_any_subitem = True
            state = states[str(subitem["id"])]
            evidence = _evidence(
                page,
                block,
                section_path,
                f"满足必要子项：{subitem['name']}",
            )
            state["all_evidence"].append(evidence)
            state["matched_terms"].update(matched_terms)
            if page.parse_status == "complete" or _allow_partial_drawing(
                rule_id, page, block
            ):
                state["confirming_evidence"].append(evidence)

        if found_relevant_terms and not matched_any_subitem:
            related_evidence.append(
                _evidence(page, block, section_path, "命中相关词，但未满足必要子项")
            )

    satisfied_ids = {
        subitem_id
        for subitem_id, state in states.items()
        if state["confirming_evidence"]
    }
    threshold_met = len(satisfied_ids) >= minimum_subitems
    mandatory_met = mandatory_subitems <= satisfied_ids
    pass_allowed = section_found and threshold_met and mandatory_met

    if pass_allowed:
        status = "PASS"
        satisfied_names = [
            states[str(item["id"])]["name"]
            for item in subitems
            if str(item["id"]) in satisfied_ids
        ]
        reason = (
            "满足必要子项："
            + "、".join(satisfied_names)
            + f"（{len(satisfied_ids)}/{len(subitems)}），因此判定 PASS"
        )
        evidence = _representative_subitem_evidence(states, satisfied_ids)
        requires_human_review = False
    else:
        uncertain_evidence = _unique_evidence(
            title_evidence
            + _all_subitem_evidence(states)
            + toc_evidence
            + related_evidence
            + risky_evidence
        )
        has_any_signal = section_found or bool(uncertain_evidence)
        if has_any_signal:
            status = "UNCERTAIN"
            missing_names = [
                states[str(item["id"])]["name"]
                for item in subitems
                if str(item["id"]) not in satisfied_ids
            ]
            if toc_evidence and not section_found and not related_evidence:
                reason = "只在目录中命中，无法确认正文内容"
            elif not section_found:
                reason = "找到相关内容或结构，但没有目标正文 section"
            elif not mandatory_met:
                reason = "目标正文章节存在，但缺少必选子项：" + "、".join(
                    states[item]["name"] for item in mandatory_subitems - satisfied_ids
                )
            elif not threshold_met:
                reason = (
                    f"目标正文章节存在，但只满足 {len(satisfied_ids)}/"
                    f"{len(subitems)} 个必要子项；仍缺少："
                    + "、".join(missing_names)
                )
            else:
                reason = "相关证据主要来自 partial 或 unreadable 页面，需要人工复核"
            evidence = uncertain_evidence
            requires_human_review = True
        else:
            status = "MISSING"
            reason = "全文检查后未发现目标正文章节、相关内容或相关解析风险"
            evidence = []
            requires_human_review = False

    result = CompletenessResult(
        rule_id=rule_id,
        name=name,
        status=status,
        reason=reason,
        evidence=evidence,
        requires_human_review=requires_human_review,
    )
    detail = _build_detail(
        result,
        matching_sections,
        subitems,
        states,
        document,
        all_relevant_terms,
    )
    _attach_semantic_metadata(result, detail, document)
    return result, detail


def _evaluate_drawing_rule(
    document: MinerUDocument,
    rule: dict[str, Any],
    indexed_blocks: list[IndexedBlock],
) -> tuple[CompletenessResult, dict[str, Any]]:
    """只为相关施工图纸筛选少量、高相关、可追溯的候选证据。"""
    rule_id = str(rule["rule_id"])
    name = str(rule["name"])
    aliases = list(
        dict.fromkeys(
            _string_list(rule["section_aliases"]) + list(_DRAWING_SECTION_TERMS)
        )
    )
    relevant_terms = list(
        dict.fromkeys(
            aliases
            + _string_list(rule["text_terms"])
            + list(_DRAWING_TITLE_TERMS)
            + list(_DRAWING_REFERENCE_TERMS)
        )
    )
    matching_sections = _matching_sections(document, rule_id, aliases)
    section_ranges = [
        (section.physical_page_start, section.physical_page_end)
        for section in matching_sections
    ]
    candidates: list[tuple[int, int, int, ReviewEvidence, str]] = []
    fallback_images: list[tuple[MinerUPage, MinerUBlock, list[str]]] = []
    confirming_association = False

    for page, block, section_path, is_toc in indexed_blocks:
        if is_toc:
            continue

        is_image = (
            block.block_type in {"image", "chart"} and bool(block.image_path)
        )
        if is_image:
            fallback_images.append((page, block, section_path))

        in_section = any(
            start <= page.physical_page <= end
            for start, end in section_ranges
        )
        near_section = any(
            start - 2 <= page.physical_page <= end + 2
            for start, end in section_ranges
        )
        page_title_terms = _find_terms(page.text, list(_DRAWING_TITLE_TERMS))
        block_title_terms = _find_terms(block.text, list(_DRAWING_TITLE_TERMS))
        reference_terms = _find_terms(block.text, list(_DRAWING_REFERENCE_TERMS))
        is_target_title = (
            block.block_type == "title"
            and _is_target_text(rule_id, block.text, aliases)
        )

        if is_image and in_section:
            if page_title_terms:
                description = (
                    "标题关键词证据：本页包含"
                    + "、".join(page_title_terms)
                    + "，并有对应 image/drawing block"
                )
                mode = "标题关键词证据"
            else:
                description = (
                    "section 内证据：位于目标图纸正文 section 范围内的 "
                    "image/drawing block"
                )
                mode = "section 内证据"
            candidates.append(
                (0, page.physical_page, block.block_index, _evidence(
                    page, block, section_path, description
                ), mode)
            )
            if page.parse_status == "complete" or _allow_partial_drawing(
                rule_id, page, block
            ):
                confirming_association = True
            continue

        if is_image and page_title_terms and not matching_sections:
            candidates.append(
                (
                    0,
                    page.physical_page,
                    block.block_index,
                    _evidence(
                        page,
                        block,
                        section_path,
                        "标题关键词证据：本页包含"
                        + "、".join(page_title_terms)
                        + "，并有对应 image/drawing block",
                    ),
                    "标题关键词证据",
                )
            )
            if page.parse_status == "complete" or _allow_partial_drawing(
                rule_id, page, block
            ):
                confirming_association = True
            continue

        if (is_target_title or block_title_terms) and (
            not matching_sections or near_section
        ):
            matched = block_title_terms or _find_terms(block.text, aliases)
            candidates.append(
                (
                    1,
                    page.physical_page,
                    block.block_index,
                    _evidence(
                        page,
                        block,
                        section_path,
                        "标题关键词证据：命中" + "、".join(matched),
                    ),
                    "标题关键词证据",
                )
            )
            continue

        if is_image and near_section:
            candidates.append(
                (
                    2,
                    page.physical_page,
                    block.block_index,
                    _evidence(
                        page,
                        block,
                        section_path,
                        "邻近页证据：位于目标图纸 section 前后 2 页内的 "
                        "image/drawing block，关联尚不完整",
                    ),
                    "邻近页证据",
                )
            )
            continue

        if reference_terms and (not matching_sections or near_section):
            candidates.append(
                (
                    3,
                    page.physical_page,
                    block.block_index,
                    _evidence(
                        page,
                        block,
                        section_path,
                        "正文引用证据：明示" + "、".join(reference_terms),
                    ),
                    "正文引用证据",
                )
            )

    if not candidates and fallback_images:
        page, block, section_path = fallback_images[0]
        candidates.append(
            (
                4,
                page.physical_page,
                block.block_index,
                _evidence(
                    page,
                    block,
                    section_path,
                    "无 OCR 图纸页证据：仅用于避免误判 MISSING，"
                    "尚不能确认与相关施工图纸的关联",
                ),
                "无 OCR 图纸页证据",
            )
        )

    selected: list[ReviewEvidence] = []
    selected_modes: list[str] = []
    selected_pages: set[int] = set()
    for _, physical_page, _, evidence, mode in sorted(
        candidates, key=lambda item: (item[0], item[1], item[2])
    ):
        if physical_page in selected_pages:
            continue
        selected_pages.add(physical_page)
        selected.append(evidence)
        if mode not in selected_modes:
            selected_modes.append(mode)
        if len(selected_pages) >= _DRAWING_EVIDENCE_PAGE_LIMIT:
            break

    has_signal = bool(matching_sections or selected or fallback_images)
    mode_summary = "、".join(selected_modes) or "无"
    if confirming_association:
        status = "PASS"
        reason = (
            "找到明确相关图纸 section 或标题关键词及对应图片；"
            f"所选页属于：{mode_summary}"
        )
        requires_human_review = False
    elif has_signal:
        status = "UNCERTAIN"
        reason = (
            "仅找到相关标题、邻近 drawing/image 页面或无 OCR 图纸页，"
            f"关联尚不完整；所选页属于：{mode_summary}"
        )
        requires_human_review = True
    else:
        status = "MISSING"
        reason = "全文检查后未发现相关图纸 section、标题、引用或图纸页面"
        requires_human_review = False

    subitem = dict(rule["required_subitems"][0])
    matched_terms = {
        term
        for page in document.pages
        if page.physical_page in selected_pages
        for term in _find_terms(page.text, relevant_terms)
    }
    states = {
        str(subitem["id"]): {
            "id": str(subitem["id"]),
            "name": str(subitem["name"]),
            "terms": _string_list(subitem.get("terms", [])),
            "all_evidence": selected,
            "confirming_evidence": selected if status == "PASS" else [],
            "matched_terms": matched_terms,
        }
    }
    result = CompletenessResult(
        rule_id=rule_id,
        name=name,
        status=status,
        reason=reason,
        evidence=selected,
        requires_human_review=requires_human_review,
    )
    detail = _build_detail(
        result,
        matching_sections,
        [subitem],
        states,
        document,
        relevant_terms,
    )
    _attach_semantic_metadata(result, detail, document)
    return result, detail


def _matching_sections(
    document: MinerUDocument, rule_id: str, aliases: list[str]
) -> list[MinerUSection]:
    matches: list[MinerUSection] = []
    seen: set[str] = set()
    for section in document.sections:
        if (
            _is_target_text(rule_id, section.title, aliases)
            or _is_target_text(rule_id, " / ".join(section.path), aliases)
        ) and section.section_id not in seen:
            matches.append(section)
            seen.add(section.section_id)
    return matches


def _subitem_match(
    block: MinerUBlock,
    page: MinerUPage,
    subitem: dict[str, Any],
    accepted_blocks: set[str],
    accepted_pages: set[str],
) -> list[str] | None:
    if block.block_type in {"title", "page_number"}:
        return None
    block_kind = (
        "table" if block.block_type == "table_continuation" else block.block_type
    )
    subitem_blocks = set(_string_list(subitem.get("block_types", [])))
    allowed_blocks = subitem_blocks or accepted_blocks
    if block_kind not in allowed_blocks or page.page_type not in accepted_pages:
        return None
    if block_kind == "table" and not (block.table_html or "").strip():
        return None
    if block_kind in {"image", "chart"} and not block.image_path:
        return None

    terms = _string_list(subitem.get("terms", []))
    if not terms:
        return [] if subitem_blocks else None
    matched_terms = _find_terms(block.text, terms)
    return matched_terms or None


def _allow_partial_drawing(
    rule_id: str, page: MinerUPage, block: MinerUBlock
) -> bool:
    return (
        rule_id == "HF-COMP-010"
        and page.parse_status == "partial"
        and block.block_type in {"image", "chart"}
        and bool(block.image_path)
        and not page.warnings
    )


def calculate_completeness_confidence(
    result: CompletenessResult,
    detail: dict[str, Any],
    document: MinerUDocument,
) -> float:
    """Calculate a small, explainable confidence score for the local verdict."""
    evidence = list(result.evidence)
    evidence_pages = {item.physical_page for item in evidence}
    pages_by_number = {page.physical_page: page for page in document.pages}
    incomplete_pages = [
        pages_by_number[page]
        for page in evidence_pages
        if page in pages_by_number and pages_by_number[page].parse_status != "complete"
    ]
    toc_only = _evidence_is_toc_only(evidence, pages_by_number)
    title_only = _evidence_is_title_only(evidence)
    satisfied_count = sum(
        1 for item in detail.get("matched_subitems", []) if item.get("satisfied")
    )
    subitem_count = len(detail.get("matched_subitems", []))
    section_count = len(detail.get("matched_sections", []))

    if result.status == "PASS":
        score = _HIGH_CONFIDENCE
        if satisfied_count >= 2:
            score += 0.08
        if evidence and not incomplete_pages and not toc_only:
            score += 0.05
        if section_count:
            score += 0.03
        if title_only:
            score -= 0.25
    elif result.status == "MISSING":
        score = 0.74
        if document.requires_human_review:
            score -= 0.30
        if evidence:
            score -= 0.18
    else:
        score = 0.48
        if toc_only:
            score -= 0.22
        if title_only:
            score -= 0.12
        if incomplete_pages:
            score -= 0.16
        if section_count and satisfied_count:
            score += 0.10
        elif section_count:
            score += 0.04

    if subitem_count and 0 < satisfied_count < subitem_count:
        score -= 0.08
    if _evidence_spans_many_sections(evidence):
        score -= 0.08
    if not evidence and document.requires_human_review:
        score = min(score, 0.35)
    return max(0.0, min(1.0, round(score, 2)))


def _attach_semantic_metadata(
    result: CompletenessResult,
    detail: dict[str, Any],
    document: MinerUDocument,
) -> None:
    confidence = calculate_completeness_confidence(result, detail, document)
    needs_review, reason = _semantic_review_decision(result, detail, document, confidence)
    result.confidence = confidence
    result.needs_semantic_review = needs_review
    result.semantic_review_reason = reason
    detail["confidence"] = confidence
    detail["needs_semantic_review"] = needs_review
    detail["semantic_review_reason"] = reason


def _semantic_review_decision(
    result: CompletenessResult,
    detail: dict[str, Any],
    document: MinerUDocument,
    confidence: float,
) -> tuple[bool, str]:
    pages_by_number = {page.physical_page: page for page in document.pages}
    toc_only = _evidence_is_toc_only(result.evidence, pages_by_number)
    title_only = _evidence_is_title_only(result.evidence)
    incomplete_evidence = any(
        pages_by_number[item.physical_page].parse_status != "complete"
        for item in result.evidence
        if item.physical_page in pages_by_number
    )
    partial_subitems = _has_partial_subitem_match(detail)
    weak_keyword_signal = _has_weak_keyword_signal(result, detail)
    reason_text = result.reason
    if result.status == "UNCERTAIN":
        return True, "本地结果为 UNCERTAIN，需进行完整性语义复核"
    if confidence < _SEMANTIC_CONFIDENCE_THRESHOLD:
        return True, f"本地规则置信度为 {confidence:.2f}，低于语义复核阈值"
    if toc_only:
        return True, "仅在目录中识别到相关章节，正文证据不足"
    if title_only:
        return True, "仅识别到标题线索，正文证据不足"
    if "附件" in reason_text and not result.evidence:
        return True, "仅发现附件名称或线索，附件正文未形成可靠证据"
    if _evidence_spans_many_sections(result.evidence):
        return True, "证据分散在多个章节，建议进行完整性语义复核"
    if partial_subitems:
        return True, "识别到部分必备要素，但无法确认整体是否满足"
    if weak_keyword_signal:
        return True, "仅命中弱关键词或同义线索，缺少明确必备要素证据"
    if "无法确认" in reason_text or "不能确认" in reason_text:
        return True, "本地原因中已说明无法确认，需要语义复核"
    if incomplete_evidence:
        return True, "证据页面解析状态不完整，需人工或语义复核辅助判断"
    if result.status == "PASS":
        return False, "正文证据较充分，本地规则置信度较高，暂无需语义复核"
    if result.status == "MISSING" and not result.evidence and not document.requires_human_review:
        return False, "文档解析完整且未发现相关证据，本地 MISSING 判断置信度较高"
    return False, "本地规则置信度达到阈值，暂无需语义复核"


def _evidence_is_toc_only(
    evidence: list[ReviewEvidence],
    pages_by_number: dict[int, MinerUPage],
) -> bool:
    if not evidence:
        return False
    pages = [pages_by_number.get(item.physical_page) for item in evidence]
    if any(page is None for page in pages):
        return False
    return all(
        any("目录页" in warning for warning in page.warnings)
        for page in pages
        if page is not None
    )


def _evidence_is_title_only(evidence: list[ReviewEvidence]) -> bool:
    return bool(evidence) and all(item.block_type == "title" for item in evidence)


def _evidence_spans_many_sections(evidence: list[ReviewEvidence]) -> bool:
    section_roots = {
        item.section_path[0]
        for item in evidence
        if item.section_path and item.block_type != "title"
    }
    return len(section_roots) >= 3


def _has_partial_subitem_match(detail: dict[str, Any]) -> bool:
    subitems = detail.get("matched_subitems", [])
    if not subitems:
        return False
    satisfied = sum(1 for item in subitems if item.get("satisfied"))
    return 0 < satisfied < len(subitems)


def _has_weak_keyword_signal(
    result: CompletenessResult,
    detail: dict[str, Any],
) -> bool:
    if not result.evidence:
        return False
    has_satisfied_subitem = any(
        item.get("satisfied") for item in detail.get("matched_subitems", [])
    )
    return not has_satisfied_subitem and not detail.get("matched_terms", [])


def _build_detail(
    result: CompletenessResult,
    matching_sections: list[MinerUSection],
    subitems: list[dict[str, Any]],
    states: dict[str, dict[str, Any]],
    document: MinerUDocument,
    relevant_terms: list[str],
) -> dict[str, Any]:
    physical_pages = sorted({item.physical_page for item in result.evidence})
    printed_pages = sorted(
        {
            item.printed_page
            for item in result.evidence
            if item.printed_page is not None
        }
    )
    matched_terms = sorted(
        {
            term
            for item in result.evidence
            for term in _find_terms(item.quote, relevant_terms)
        }
    )
    subitem_details = []
    for subitem in subitems:
        state = states[str(subitem["id"])]
        confirming = _unique_evidence(state["confirming_evidence"])
        all_evidence = _unique_evidence(state["all_evidence"])
        subitem_details.append(
            {
                "id": str(subitem["id"]),
                "name": str(subitem["name"]),
                "satisfied": bool(confirming),
                "matched_terms": sorted(state["matched_terms"]),
                "physical_pages": sorted(
                    {item.physical_page for item in all_evidence}
                ),
            }
        )

    return {
        "rule_id": result.rule_id,
        "name": result.name,
        "status": result.status,
        "reason": result.reason,
        "matched_sections": [
            {
                "title": section.title,
                "level": section.level,
                "physical_page_start": section.physical_page_start,
                "physical_page_end": section.physical_page_end,
            }
            for section in matching_sections
        ],
        "physical_pages": physical_pages,
        "printed_pages": printed_pages,
        "matched_terms": matched_terms,
        "matched_subitems": subitem_details,
        "evidence": result.evidence,
        "requires_human_review": result.requires_human_review,
        "document_requires_human_review": document.requires_human_review,
    }


def _index_blocks(document: MinerUDocument) -> list[IndexedBlock]:
    """只用 document.sections 中已接受的标题更新章节路径。"""
    indexed: list[IndexedBlock] = []
    section_stack: list[str] = []
    accepted_levels: dict[tuple[int, str], list[int]] = {}
    for section in document.sections:
        key = (section.physical_page_start, section.title)
        accepted_levels.setdefault(key, []).append(section.level)

    for page in document.pages:
        is_toc = any("目录页" in warning for warning in page.warnings)
        for block in page.blocks:
            key = (page.physical_page, block.text.strip())
            levels = accepted_levels.get(key, [])
            if not is_toc and block.block_type == "title" and levels:
                level = levels.pop(0)
                new_root = _title_root_number(block.text)
                current_root = (
                    _title_root_number(section_stack[0]) if section_stack else None
                )
                if new_root and current_root and new_root != current_root:
                    section_stack.clear()
                while len(section_stack) >= level:
                    section_stack.pop()
                while len(section_stack) < level - 1:
                    section_stack.append("")
                section_stack.append(block.text.strip())
            indexed.append(
                (page, block, [part for part in section_stack if part], is_toc)
            )
    return indexed


def _evidence(
    page: MinerUPage,
    block: MinerUBlock,
    section_path: list[str],
    description: str,
) -> ReviewEvidence:
    quote = block.text.strip()
    if len(quote) > 240:
        quote = quote[:237] + "..."
    return ReviewEvidence(
        physical_page=page.physical_page,
        printed_page=page.printed_page,
        section_path=section_path,
        block_id=block.block_id,
        block_type=block.block_type,
        quote=quote,
        description=description,
        bbox=block.bbox,
        image_path=block.image_path,
        table_html=block.table_html,
        source_pointer=block.source_pointer,
    )


def _representative_subitem_evidence(
    states: dict[str, dict[str, Any]], satisfied_ids: set[str]
) -> list[ReviewEvidence]:
    evidence: list[ReviewEvidence] = []
    for subitem_id, state in states.items():
        if subitem_id in satisfied_ids:
            evidence.extend(_unique_evidence(state["confirming_evidence"])[:3])
    return _unique_evidence(evidence)


def _all_subitem_evidence(
    states: dict[str, dict[str, Any]]
) -> list[ReviewEvidence]:
    evidence: list[ReviewEvidence] = []
    for state in states.values():
        evidence.extend(_unique_evidence(state["all_evidence"])[:3])
    return _unique_evidence(evidence)


def _unique_evidence(items: list[ReviewEvidence]) -> list[ReviewEvidence]:
    unique: list[ReviewEvidence] = []
    seen: set[str] = set()
    for item in items:
        if item.block_id not in seen:
            seen.add(item.block_id)
            unique.append(item)
    return unique


def _find_terms(text: str, terms: list[str]) -> list[str]:
    normalized = _normalize(text)
    return [
        term
        for term in terms
        if _normalize(term) and _normalize(term) in normalized
    ]


def _matches_any(text: str, terms: list[str]) -> bool:
    return bool(_find_terms(text, terms))


def _is_target_text(rule_id: str, text: str, aliases: list[str]) -> bool:
    if not _matches_any(text, aliases):
        return False
    if rule_id == "HF-COMP-007" and "材料" in text:
        specific_terms = (
            "支架验收",
            "模板验收",
            "搭设验收",
            "验收程序",
            "验收标准",
            "验收人员",
            "验收内容",
        )
        return any(term in text for term in specific_terms)
    return True


def _normalize(text: str) -> str:
    return "".join(str(text).lower().split())


def _string_list(value: Any) -> list[str]:
    if not isinstance(value, list):
        return []
    return [str(item) for item in value if str(item).strip()]


def _title_root_number(title: str) -> str | None:
    match = re.match(r"^\s*(\d+)(?:\.|\s)", title)
    return match.group(1) if match else None


def _join_values(values: list[Any]) -> str:
    return "、".join(str(value) for value in values)


def _md(value: Any) -> str:
    return str(value).replace("|", "\\|").replace("\r", " ").replace("\n", "<br>")
