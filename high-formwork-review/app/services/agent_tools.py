"""Agent 工具层：文档检索工具（V3.1 Phase 1 检索质量改进）。

检索改进（解 Phase 0 发现 3：检索截断导致 5.1 阳性对照失败）：
- LaTeX 归一化匹配：表格 block 文本常为 "$\\Phi 48 \\times 3.0$" 形态，
  归一化后 "Φ48×3.0" 才能命中（normalize_for_match + 偏移映射回原文）
- 关键词中心窗口：命中 block 不再从头部截断，而是取关键词前后 ±120 字符，
  保证参数行（如材料表中的"钢管 Φ48×3.0"）不被截掉
- 全部工具返回内容登记进 EvidenceRegistry，输出携带 Evidence ID，
  供 agent finish 时引用（只准引用 ID，不准自填原文）

工具契约：入参 (document, registry, **args)，返回 (结果文本, evidence_ids)。
"""

from __future__ import annotations

import re
from typing import Any

from ..completeness_review import _find_terms, _index_blocks
from ..models import MinerUBlock, MinerUDocument
from .agent_guardrails import EvidenceRegistry, display_normalize, normalize_for_match

SEARCH_MAX_HITS = 8
SEARCH_WINDOW_BEFORE = 100
SEARCH_WINDOW_AFTER = 140
PAGE_TEXT_LIMIT = 6000


def _despaced_with_offsets(text: str) -> tuple[str, list[int]]:
    """去空白+LaTeX 归一化，并保留每个输出字符对应的原文偏移。

    despaced 串上做子串匹配，命中后用偏移表映射回原文区间取窗口。
    """
    latex_map = [
        ("\\times", "×"),
        ("\\gamma", "γ"),
        ("\\omega", "ω"),
        ("\\Phi", "Φ"),
        ("\\phi", "φ"),
        ("\\leq", "≤"),
        ("\\geq", "≥"),
        ("\\le", "≤"),
        ("\\ge", "≥"),
        ("\\pm", "±"),
    ]
    despaced_chars: list[str] = []
    offsets: list[int] = []
    i = 0
    n = len(text)
    while i < n:
        ch = text[i]
        if ch == "$":
            i += 1
            continue
        if ch == "\\":
            for token, plain in latex_map:
                if text.startswith(token, i):
                    for pc in plain:
                        despaced_chars.append(pc)
                        offsets.append(i)
                    i += len(token)
                    break
            else:
                i += 1  # 未知转义，丢弃
            continue
        if ch.isspace():
            i += 1
            continue
        despaced_chars.append(ch.lower())
        offsets.append(i)
        i += 1
    return "".join(despaced_chars), offsets


def _hit_window(text: str, start: int, end: int) -> str:
    """按原文偏移取关键词中心窗口。"""
    s = max(0, start - SEARCH_WINDOW_BEFORE)
    e = min(len(text), end + SEARCH_WINDOW_AFTER)
    window = display_normalize(text[s:e])
    prefix = "…" if s > 0 else ""
    suffix = "…" if e < len(text) else ""
    return f"{prefix}{window}{suffix}"


def _block_text(block: MinerUBlock) -> str:
    return block.text or ""


def _block_label(block: MinerUBlock) -> str:
    type_labels = {"table": "表格", "title": "标题", "image": "图"}
    return type_labels.get(block.block_type, block.block_type)


def search_document(
    document: MinerUDocument,
    registry: EvidenceRegistry,
    *,
    keywords: list[str],
    preferred_sections: list[str] | None = None,
) -> tuple[str, list[str]]:
    """关键词检索：目录降权 + 章节偏好 + 关键词中心窗口 + Evidence 登记。"""
    terms = [normalize_for_match(k) for k in keywords if k and normalize_for_match(k)]
    if not terms:
        return "keywords 为空或归一化后无有效内容", []
    section_terms = [str(s) for s in (preferred_sections or []) if str(s).strip()]
    hits: list[tuple[float, MinerUBlock, str, int, int, list[str], bool]] = []
    for _page, block, section_path, is_toc in _index_blocks(document):
        text = _block_text(block)
        if not text:
            continue
        despaced, offsets = _despaced_with_offsets(text)
        if not despaced:
            continue
        matched_terms = [t for t in terms if t in despaced]
        if not matched_terms:
            continue
        # 取首个命中词的窗口
        term = matched_terms[0]
        idx = despaced.find(term)
        raw_start = offsets[idx]
        raw_end = offsets[min(idx + len(term) - 1, len(offsets) - 1)] + 1
        section_text = " / ".join(section_path)
        section_bonus = 3.0 if _find_terms(section_text, section_terms) else 0.0
        block_bonus = 1.0 if block.block_type in {"table", "paragraph"} else 0.2
        toc_penalty = 12.0 if is_toc else 0.0
        score = len(matched_terms) * 10.0 + section_bonus + block_bonus - toc_penalty
        hits.append((score, block, text, raw_start, raw_end, section_path, is_toc))
    hits.sort(key=lambda item: item[0], reverse=True)
    if len([item for item in hits if not item[6]]) < 2:
        hits.extend(_section_chase_hits(document, terms, section_terms, hits))
        hits.sort(key=lambda item: item[0], reverse=True)
    lines: list[str] = []
    evidence_ids: list[str] = []
    seen_blocks: set[str] = set()
    for _, block, text, raw_start, raw_end, section_path, is_toc in hits:
        if block.block_id in seen_blocks:
            continue
        seen_blocks.add(block.block_id)
        window = _hit_window(text, raw_start, raw_end)
        prefix = "目录降权 " if is_toc else ""
        section = f"|{'/'.join(section_path)}" if section_path else ""
        eid = registry.register(
            page=block.physical_page,
            text=window,
            source_tool="search_document",
            block_id=block.block_id,
            block_type=block.block_type,
        )
        evidence_ids.append(eid)
        lines.append(f"{eid} [P{block.physical_page}|{prefix}{_block_label(block)}{section}] {window}")
        if len(lines) >= SEARCH_MAX_HITS:
            break
    if not lines:
        return "未找到相关内容，请换关键词或使用 get_page", []
    return "\n".join(lines), evidence_ids


def _section_chase_hits(
    document: MinerUDocument,
    terms: list[str],
    section_terms: list[str],
    existing_hits: list[tuple[float, MinerUBlock, str, int, int, list[str], bool]],
) -> list[tuple[float, MinerUBlock, str, int, int, list[str], bool]]:
    """初始召回不足时，对命中章节做二次追证。"""
    if not section_terms and not existing_hits:
        return []
    target_sections = {
        tuple(hit[5])
        for hit in existing_hits
        if hit[5] and not hit[6]
    }
    extra: list[tuple[float, MinerUBlock, str, int, int, list[str], bool]] = []
    for _page, block, section_path, is_toc in _index_blocks(document):
        if is_toc or not section_path:
            continue
        section_match = tuple(section_path) in target_sections
        if not section_match and not _find_terms(" / ".join(section_path), section_terms):
            continue
        text = _block_text(block)
        if not text:
            continue
        despaced, offsets = _despaced_with_offsets(text)
        matched = [term for term in terms if term in despaced]
        if not matched:
            continue
        idx = despaced.find(matched[0])
        raw_start = offsets[idx]
        raw_end = offsets[min(idx + len(matched[0]) - 1, len(offsets) - 1)] + 1
        extra.append((6.0 + len(matched), block, text, raw_start, raw_end, section_path, is_toc))
    return extra


def get_page(
    document: MinerUDocument,
    registry: EvidenceRegistry,
    *,
    page: int,
) -> tuple[str, list[str]]:
    """页级兜底：返回该页全部 block 文本并登记为页级证据。"""
    chunks: list[str] = []
    for pg in document.pages:
        if pg.physical_page != page:
            continue
        for block in pg.blocks:
            if block.text:
                chunks.append(f"[{block.block_id}|{_block_label(block)}] {block.text}")
    if not chunks:
        return f"第 {page} 页无文本 block", []
    body = display_normalize("\n".join(chunks))[:PAGE_TEXT_LIMIT]
    eid = registry.register(
        page=page,
        text=body,
        source_tool="get_page",
        block_id=None,
        block_type="page",
        source_type="page",
    )
    return f"{eid} [P{page}|整页]\n{body}", [eid]


def get_table(
    document: MinerUDocument,
    registry: EvidenceRegistry,
    *,
    block_id: str,
) -> tuple[str, list[str]]:
    """读取指定表格 block 的完整内容（block_id 或 EV ID 均可定位）。"""
    block_id = _resolve_block_id(block_id, registry)
    for pg in document.pages:
        for block in pg.blocks:
            if block.block_id == block_id:
                text = display_normalize(_block_text(block) or block.table_html or "")
                if not text:
                    return f"表格 {block_id} 无文本内容", []
                eid = registry.register(
                    page=block.physical_page,
                    text=text,
                    source_tool="get_table",
                    block_id=block.block_id,
                    block_type="table",
                )
                return f"{eid} [P{block.physical_page}|表格] {text}", [eid]
    return f"block {block_id} 不存在", []


def _resolve_block_id(reference: str, registry: EvidenceRegistry) -> str:
    """把模型给的定位引用解析成 block_id：支持直接给 block_id 或 EV ID。

    模型常用 EV ID（如 EV-P50-B0000）当 block_id 传——先查证据登记簿
    解析出真实 block_id，解析不了再原样返回。
    """
    reference = str(reference or "").strip()
    if not reference:
        return reference
    evidence = registry.get(reference)
    if evidence is not None and evidence.block_id:
        return evidence.block_id
    return reference


def get_context(
    document: MinerUDocument,
    registry: EvidenceRegistry,
    *,
    block_id: str,
    before: int = 1,
    after: int = 1,
) -> tuple[str, list[str]]:
    """读取目标 block 前后 N 个 block 的上下文（block_id 或 EV ID 均可定位）。"""
    before = max(0, min(int(before), 3))
    after = max(0, min(int(after), 3))
    block_id = _resolve_block_id(block_id, registry)
    for pg in document.pages:
        for index, block in enumerate(pg.blocks):
            if block.block_id != block_id:
                continue
            lo = max(0, index - before)
            hi = min(len(pg.blocks), index + after + 1)
            chunks: list[str] = []
            for neighbor in pg.blocks[lo:hi]:
                if neighbor.text:
                    marker = "→" if neighbor.block_id == block_id else " "
                    chunks.append(
                        f"{marker}[{neighbor.block_id}|{_block_label(neighbor)}] {neighbor.text}"
                    )
            if not chunks:
                return f"block {block_id} 前后无文本内容", []
            body = display_normalize("\n".join(chunks))
            eid = registry.register(
                page=pg.physical_page,
                text=body,
                source_tool="get_context",
                block_id=block_id,
                block_type="context",
            )
            return f"{eid} [P{pg.physical_page}|上下文]\n{body}", [eid]
    return f"block {block_id} 不存在", []


TOOL_HANDLERS: dict[str, Any] = {
    "search_document": search_document,
    "get_page": get_page,
    "get_table": get_table,
    "get_context": get_context,
}
