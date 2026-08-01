"""把规范化 MinerU 文档转换为 Dify 完整性审查输入。"""

from __future__ import annotations

import json
import re
import unicodedata
from dataclasses import asdict, is_dataclass
from typing import Any


DEFAULT_CHARACTER_LIMIT = 50_000
IMAGE_REVIEW_MARKER = "[本页包含图片或图纸，需人工复核]"
_TOC_WARNING = "目录页"
_IMAGE_BLOCK_TYPES = {"image", "chart"}
_TEXT_BLOCK_TYPES = {"title", "paragraph", "table", "table_continuation", "formula", "equation"}
_CHAPTER_PREFIX = re.compile(
    r"^\s*第[零〇一二三四五六七八九十百千万\d]+[章节编篇部]\s*",
    re.IGNORECASE,
)
_NUMBER_PREFIX = re.compile(
    r"^\s*(?:"
    r"\d+(?:\.\d+)*(?:[.、．)）])?"
    r"|[（(][零〇一二三四五六七八九十百千万\d]+[)）]"
    r"|[零〇一二三四五六七八九十]+[、.．]"
    r")\s*"
)


def build_dify_scheme_text(parse_result: Any) -> str:
    """返回按物理页组织的完整方案文本，不执行永久裁剪。"""
    return build_dify_scheme_payload(parse_result)[0]


def build_dify_scheme_payload(
    parse_result: Any,
    character_limit: int = DEFAULT_CHARACTER_LIMIT,
) -> tuple[str, dict[str, Any]]:
    """返回完整方案文本和长度元数据。

    ``character_limit`` 是后续单次 Dify 请求上限；本函数不会因此丢弃正文。
    """
    document = _document_dict(parse_result)
    repeated_margins = _repeated_margin_texts(document)
    page_chunks = [
        _render_page(document, page, repeated_margins)
        for page in document.get("pages", [])
        if not _is_toc_page(page)
    ]
    scheme_text = "\n\n".join(chunk for chunk in page_chunks if chunk).strip()
    exceeds_limit = len(scheme_text) > character_limit
    metadata = {
        "character_limit": character_limit,
        "character_count": len(scheme_text),
        "omitted_sections": [],
        "truncation_warning": (
            "完整方案超过单次请求上限，将按规则证据包分批发送；未省略章节。"
            if exceeds_limit
            else None
        ),
    }
    return scheme_text, metadata


def normalize_section_title(title: str) -> str:
    """规范化章节标题，用于 ``section_aliases`` 包含匹配。"""
    value = unicodedata.normalize("NFKC", str(title or "")).strip().casefold()
    previous = None
    while value and value != previous:
        previous = value
        value = _CHAPTER_PREFIX.sub("", value)
        value = _NUMBER_PREFIX.sub("", value)
    value = re.sub(r"\s+", "", value)
    return value.strip("—-:：、.。")


def build_rule_evidence_packages(
    parse_result: Any,
    rules: list[dict[str, Any]],
) -> tuple[list[dict[str, Any]], list[dict[str, Any]], list[dict[str, Any]]]:
    """为每条有效规则收集完整相关章节。

    返回 ``(packages, warnings, fallback_results)``。缺少章节别名的规则不会
    匹配全篇，而是生成需要人工复核的本地兜底结果。
    """
    document = _document_dict(parse_result)
    sections = list(document.get("sections", []))
    repeated_margins = _repeated_margin_texts(document)
    packages: list[dict[str, Any]] = []
    warnings: list[dict[str, Any]] = []
    fallback_results: list[dict[str, Any]] = []

    for rule in rules:
        rule_id = str(rule.get("rule_id", "")).strip()
        item_name = str(rule.get("name", "")).strip()
        aliases = [
            str(value).strip()
            for value in rule.get("section_aliases", [])
            if str(value).strip()
        ]
        if not aliases:
            message = "section_aliases 缺失或为空，未自动匹配全部章节"
            warnings.append(
                {
                    "code": "RULE_CONFIG_WARNING",
                    "rule_id": rule_id,
                    "message": message,
                }
            )
            fallback_results.append(
                {
                    "rule_id": rule_id,
                    "name": item_name,
                    "status": "UNCERTAIN",
                    "reason": message,
                    "evidence": [],
                    "manual_review": True,
                    "requires_human_review": True,
                }
            )
            continue

        matched_sections = [
            section
            for section in sections
            if any(_titles_match(section.get("title", ""), alias) for alias in aliases)
        ]
        unmatched_aliases = [
            alias
            for alias in aliases
            if not any(_titles_match(section.get("title", ""), alias) for section in sections)
        ]
        page_ranges = _merged_page_ranges(matched_sections)
        page_numbers = {
            page_number
            for page_range in page_ranges
            for page_number in range(page_range["start_page"], page_range["end_page"] + 1)
        }
        page_chunks = [
            _render_page(document, page, repeated_margins, matched_sections)
            for page in document.get("pages", [])
            if page.get("physical_page") in page_numbers and not _is_toc_page(page)
        ]
        evidence_body = "\n\n".join(chunk for chunk in page_chunks if chunk).strip()
        if not evidence_body:
            evidence_body = "[未匹配到可用的正文章节内容，需人工复核]"
        evidence_text = (
            f"【规则证据包】\n"
            f"rule_id: {rule_id}\n"
            f"item_name: {item_name}\n"
            f"matched_sections: "
            f"{'、'.join(section.get('title', '') for section in matched_sections) or '无'}\n\n"
            f"{evidence_body}"
        )
        packages.append(
            {
                "rule_id": rule_id,
                "item_name": item_name,
                "section_aliases": aliases,
                "matched_sections": [
                    {
                        "title": section.get("title"),
                        "level": section.get("level"),
                        "path": section.get("path", []),
                        "start_page": section.get("physical_page_start"),
                        "end_page": section.get("physical_page_end"),
                    }
                    for section in matched_sections
                ],
                "unmatched_aliases": unmatched_aliases,
                "page_ranges": page_ranges,
                "evidence_text": evidence_text,
                "character_count": len(evidence_text),
                "_page_chunks": page_chunks,
            }
        )
    return packages, warnings, fallback_results


def build_rule_driven_batches(
    packages: list[dict[str, Any]],
    rules: list[dict[str, Any]],
    task_id: str,
    character_limit: int = DEFAULT_CHARACTER_LIMIT,
) -> list[dict[str, Any]]:
    """把完整规则证据包组合为不重复规则的 Dify 请求批次。"""
    if character_limit <= 0:
        raise ValueError("Dify 单次字符上限必须大于 0")
    rule_by_id = {str(rule.get("rule_id")): rule for rule in rules}
    normal_packages: list[dict[str, Any]] = []
    oversized_parts: list[dict[str, Any]] = []
    for package in packages:
        if len(package["evidence_text"]) <= character_limit:
            normal_packages.append(package)
        else:
            oversized_parts.extend(_split_oversized_package(package, character_limit))

    groups: list[list[dict[str, Any]]] = []
    current: list[dict[str, Any]] = []
    current_length = 0
    for package in normal_packages:
        separator_length = 2 if current else 0
        proposed = current_length + separator_length + len(package["evidence_text"])
        if current and proposed > character_limit:
            groups.append(current)
            current = []
            current_length = 0
        current.append(package)
        current_length += (2 if current_length else 0) + len(package["evidence_text"])
    if current:
        groups.append(current)
    groups.extend([[part] for part in oversized_parts])

    batch_count = len(groups)
    batches: list[dict[str, Any]] = []
    for index, group in enumerate(groups, start=1):
        scheme_text = "\n\n".join(item["evidence_text"] for item in group)
        rule_ids = list(dict.fromkeys(str(item["rule_id"]) for item in group))
        batch_rules = [rule_by_id[rule_id] for rule_id in rule_ids if rule_id in rule_by_id]
        included_sections = list(
            dict.fromkeys(
                section["title"]
                for item in group
                for section in item.get("matched_sections", [])
                if section.get("title")
            )
        )
        pages = [
            page
            for item in group
            for page_range in item.get("page_ranges", [])
            for page in (page_range["start_page"], page_range["end_page"])
        ]
        inputs = {
            "task_id": task_id,
            "scheme_text": scheme_text,
            "review_rules": json.dumps(batch_rules, ensure_ascii=False),
            "expected_rule_count": len(rule_ids),
        }
        batch = {
            "batch_index": index,
            "batch_count": batch_count,
            "rule_ids": rule_ids,
            "included_sections": included_sections,
            "start_page": min(pages) if pages else None,
            "end_page": max(pages) if pages else None,
            "character_count": len(scheme_text),
            "expected_rule_count": len(rule_ids),
            "scheme_text_metadata": {
                "character_limit": character_limit,
                "character_count": len(scheme_text),
                "omitted_sections": [],
                "truncation_warning": None,
            },
            "inputs": inputs,
        }
        part = group[0] if len(group) == 1 else {}
        if part.get("part_count"):
            batch["oversized_rule_part"] = {
                "rule_id": part["rule_id"],
                "part_index": part["part_index"],
                "part_count": part["part_count"],
            }
        batches.append(batch)
    return batches


def _split_oversized_package(
    package: dict[str, Any],
    character_limit: int,
) -> list[dict[str, Any]]:
    base_units = _paragraph_units(package)
    if not base_units:
        raise ValueError(f"{package['rule_id']} 没有可分片的证据内容")
    placeholder_header = _oversized_header(package["rule_id"], 9999, 9999)
    available = character_limit - len(placeholder_header) - 2
    if available <= 0:
        raise ValueError("Dify 单次字符上限过小，无法容纳分片说明")

    chunks: list[list[dict[str, Any]]] = []
    current: list[dict[str, Any]] = []
    current_length = 0
    for unit in base_units:
        unit_text = unit["text"]
        if len(unit_text) > available:
            raise ValueError(
                f"{package['rule_id']} 存在超过单次上限的单个完整段落"
            )
        proposed = current_length + (2 if current else 0) + len(unit_text)
        if current and proposed > available:
            chunks.append(current)
            current = []
            current_length = 0
        current.append(unit)
        current_length += (2 if current_length else 0) + len(unit_text)
    if current:
        chunks.append(current)

    part_count = len(chunks)
    parts: list[dict[str, Any]] = []
    for part_index, units in enumerate(chunks, start=1):
        header = _oversized_header(package["rule_id"], part_index, part_count)
        evidence_text = header + "\n\n" + "\n\n".join(
            unit["text"] for unit in units
        )
        part_pages = sorted(
            {
                int(unit["physical_page"])
                for unit in units
                if unit.get("physical_page") is not None
            }
        )
        part_sections = [
            section
            for section in package.get("matched_sections", [])
            if any(
                section.get("start_page", 10**9)
                <= page
                <= section.get("end_page", -1)
                for page in part_pages
            )
        ]
        part = dict(package)
        part.update(
            {
                "evidence_text": evidence_text,
                "character_count": len(evidence_text),
                "part_index": part_index,
                "part_count": part_count,
                "matched_sections": part_sections,
                "page_ranges": _ranges_from_page_numbers(part_pages),
            }
        )
        parts.append(part)
    return parts


def _oversized_header(rule_id: str, part_index: int, part_count: int) -> str:
    return (
        "【超大单规则证据分片】\n"
        f"rule_id: {rule_id}\n"
        f"part_index: {part_index}\n"
        f"part_count: {part_count}\n"
        "本分片只是完整证据的一部分。\n"
        "本分片未出现某项必需内容时，不得据此判定整条规则 MISSING；"
        "证据不足时应输出 UNCERTAIN，并设置 manual_review=true。"
        "分片级 PASS 仅表示当前分片覆盖内容无明显缺失，不代表规则级最终 PASS。"
    )


def _paragraph_units(package: dict[str, Any]) -> list[dict[str, Any]]:
    units: list[dict[str, Any]] = []
    for page_chunk in package.get("_page_chunks", []):
        paragraphs = [part.strip() for part in page_chunk.split("\n\n") if part.strip()]
        if not paragraphs:
            continue
        page_match = re.match(r"【第(\d+)页】", paragraphs[0])
        physical_page = int(page_match.group(1)) if page_match else None
        prefix_parts = [paragraphs[0]]
        content_start = 1
        if len(paragraphs) > 1 and paragraphs[1].startswith("章节："):
            prefix_parts.append(paragraphs[1])
            content_start = 2
        prefix = "\n".join(prefix_parts)
        content = paragraphs[content_start:] or ["[本页无可用正文，需人工复核]"]
        units.extend(
            {
                "physical_page": physical_page,
                "text": prefix + "\n\n" + paragraph,
            }
            for paragraph in content
        )
    return units


def _ranges_from_page_numbers(page_numbers: list[int]) -> list[dict[str, int]]:
    if not page_numbers:
        return []
    merged: list[list[int]] = []
    for page in sorted(set(page_numbers)):
        if not merged or page > merged[-1][1] + 1:
            merged.append([page, page])
        else:
            merged[-1][1] = page
    return [
        {"start_page": start, "end_page": end}
        for start, end in merged
    ]


def _document_dict(parse_result: Any) -> dict[str, Any]:
    if is_dataclass(parse_result):
        return asdict(parse_result)
    if isinstance(parse_result, dict):
        return parse_result
    raise TypeError("parse_result 必须是 MinerUDocument 或 mineru_document.json 字典")


def _titles_match(title: str, alias: str) -> bool:
    normalized_title = normalize_section_title(title)
    normalized_alias = normalize_section_title(alias)
    if not normalized_title or not normalized_alias:
        return False
    return normalized_alias in normalized_title or normalized_title in normalized_alias


def _merged_page_ranges(sections: list[dict[str, Any]]) -> list[dict[str, int]]:
    raw_ranges = sorted(
        (
            int(section["physical_page_start"]),
            int(section["physical_page_end"]),
        )
        for section in sections
        if section.get("physical_page_start") is not None
        and section.get("physical_page_end") is not None
    )
    merged: list[list[int]] = []
    for start, end in raw_ranges:
        if not merged or start > merged[-1][1] + 1:
            merged.append([start, end])
        else:
            merged[-1][1] = max(merged[-1][1], end)
    return [
        {"start_page": start, "end_page": end}
        for start, end in merged
    ]


def _render_page(
    document: dict[str, Any],
    page: dict[str, Any],
    repeated_margins: set[str],
    relevant_sections: list[dict[str, Any]] | None = None,
) -> str:
    page_number = page.get("physical_page")
    all_sections = relevant_sections if relevant_sections is not None else document.get("sections", [])
    active_sections = [
        section
        for section in all_sections
        if section.get("physical_page_start", 10**9)
        <= page_number
        <= section.get("physical_page_end", -1)
    ]
    active_sections.sort(key=lambda item: (item.get("level", 0), item.get("physical_page_start", 0)))
    section_titles = list(
        dict.fromkeys(str(section.get("title", "")).strip() for section in active_sections)
    )
    lines = [f"【第{page_number}页】"]
    if section_titles:
        lines.append("章节：" + " / ".join(section_titles))

    content_parts: list[str] = []
    has_image = False
    has_substantive_text = False
    normalized_section_titles = {normalize_section_title(title) for title in section_titles}
    for block in page.get("blocks", []):
        block_type = block.get("block_type")
        if block_type == "page_number":
            continue
        if block_type in _IMAGE_BLOCK_TYPES:
            has_image = True
        text = str(block.get("text") or "").strip()
        if not text or block_type not in _TEXT_BLOCK_TYPES:
            continue
        if _margin_key(block, page) in repeated_margins:
            continue
        if block_type == "title" and normalize_section_title(text) in normalized_section_titles:
            continue
        content_parts.append(text)
        if block_type != "title":
            has_substantive_text = True

    if has_image and (
        not has_substantive_text
        or page.get("parse_status") in {"partial", "unreadable"}
        and len("\n".join(content_parts)) < 80
    ):
        content_parts.append(IMAGE_REVIEW_MARKER)
    if not content_parts and not section_titles:
        return ""
    lines.extend(content_parts)
    return "\n\n".join(lines)


def _is_toc_page(page: dict[str, Any]) -> bool:
    return any(_TOC_WARNING in str(warning) for warning in page.get("warnings", []))


def _repeated_margin_texts(document: dict[str, Any]) -> set[str]:
    pages_by_text: dict[str, set[int]] = {}
    for page in document.get("pages", []):
        if _is_toc_page(page):
            continue
        for block in page.get("blocks", []):
            key = _margin_key(block, page)
            if key:
                pages_by_text.setdefault(key, set()).add(int(page.get("physical_page", 0)))
    return {
        text
        for text, page_numbers in pages_by_text.items()
        if len(page_numbers) >= 3
    }


def _margin_key(block: dict[str, Any], page: dict[str, Any]) -> str:
    if block.get("block_type") != "paragraph":
        return ""
    text = re.sub(r"\s+", " ", str(block.get("text") or "")).strip()
    if not text or len(text) > 120:
        return ""
    bbox = block.get("bbox")
    height = page.get("height")
    if not isinstance(bbox, dict) or not isinstance(height, (int, float)) or height <= 0:
        return ""
    y0 = bbox.get("y0")
    y1 = bbox.get("y1")
    if not isinstance(y0, (int, float)) or not isinstance(y1, (int, float)):
        return ""
    if y0 <= height * 0.08 or y1 >= height * 0.92:
        return unicodedata.normalize("NFKC", text).casefold()
    return ""
