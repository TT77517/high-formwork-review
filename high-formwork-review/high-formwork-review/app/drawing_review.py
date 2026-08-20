"""图文复核提示。

本模块只做图纸证据召回和人工复核卡片生成，不进行图纸尺寸识别，
避免把图纸召回误表达为多模态自动判定结论。
"""

from __future__ import annotations

from typing import Any

from .models import MinerUDocument, MinerUPage


def build_drawing_review(
    parsed_document: MinerUDocument,
    project_facts: dict[str, Any],
) -> list[dict[str, Any]]:
    facts = project_facts.get("facts", {})
    return [
        _drawing_card(
            "DR-01",
            "水平剪刀撑图文复核",
            "核对正文中水平剪刀撑设置间隔与相关图纸表达是否一致。",
            facts.get("horizontal_scissor_brace_interval", {}),
            parsed_document,
            ("水平剪刀撑", "剪刀撑", "支撑架", "平面", "剖面"),
        ),
        _drawing_card(
            "DR-02",
            "支撑架关键构造图文复核",
            "核对步距、可调托撑悬臂、立杆布置等正文/计算参数是否在图纸中有对应表达。",
            _merge_fact_evidence(
                facts,
                (
                    "standard_step_height",
                    "head_jack_cantilever_length",
                    "support_system",
                ),
            ),
            parsed_document,
            ("支撑架", "立杆", "水平杆", "可调托撑", "节点", "剖面", "立面"),
        ),
    ]


def _drawing_card(
    review_item_id: str,
    title: str,
    purpose: str,
    fact: dict[str, Any],
    parsed_document: MinerUDocument,
    keywords: tuple[str, ...],
) -> dict[str, Any]:
    text_evidence = [_evidence_dict(item) for item in fact.get("evidence", [])[:5]]
    drawings = _find_drawing_pages(parsed_document, keywords)
    status = "REVIEW" if drawings else "UNCERTAIN"
    if drawings and text_evidence:
        conclusion = "已召回正文证据和相关图纸页；当前仅能提示人工进行图文一致性复核，未自动判定图纸尺寸。"
    elif drawings:
        conclusion = "已召回相关图纸页，但正文参数证据不足，需人工结合方案文本复核。"
    else:
        conclusion = "未可靠召回相关图纸页，需人工从图纸目录或附件中确认。"
    return {
        "review_item_id": review_item_id,
        "category": "图文复核",
        "title": title,
        "review_method": "drawing_evidence_recall",
        "status": status,
        "purpose": purpose,
        "conclusion": conclusion,
        "text_evidence": text_evidence,
        "drawing_evidence": drawings,
        "automation_level": "evidence_recall_only",
        "requires_human_review": True,
        "boundary": "系统仅召回疑似相关图纸页和正文证据；图纸中的构造尺寸、节点做法和图文一致性需人工复核。",
    }


def _find_drawing_pages(
    parsed_document: MinerUDocument,
    keywords: tuple[str, ...],
    *,
    limit: int = 8,
) -> list[dict[str, Any]]:
    matched: list[dict[str, Any]] = []
    seen_pages: set[int] = set()
    drawing_types = {"drawing", "mixed", "image"}
    for page in parsed_document.pages:
        if page.physical_page in seen_pages:
            continue
        text = _page_text(page)
        keyword_hits = [keyword for keyword in keywords if keyword in text]
        is_drawing_like = page.page_type in drawing_types or any(
            block.block_type in {"image", "figure"} for block in page.blocks
        )
        if not keyword_hits or not is_drawing_like:
            continue
        matched.append(
            {
                "physical_page": page.physical_page,
                "printed_page": page.printed_page,
                "page_type": page.page_type,
                "parse_status": page.parse_status,
                "keyword_hits": keyword_hits[:5],
                "requires_human_review": True,
                "reason": "图纸/混合页面命中构造关键词，适合作为图文一致性人工复核入口。",
            }
        )
        seen_pages.add(page.physical_page)
        if len(matched) >= limit:
            break
    return matched


def _page_text(page: MinerUPage) -> str:
    block_text = "\n".join(block.text or "" for block in page.blocks)
    return f"{page.text or ''}\n{block_text}"


def _merge_fact_evidence(
    facts: dict[str, Any],
    parameter_ids: tuple[str, ...],
) -> dict[str, Any]:
    evidence: list[dict[str, Any]] = []
    for parameter_id in parameter_ids:
        fact = facts.get(parameter_id, {})
        if not isinstance(fact, dict):
            continue
        evidence.extend(fact.get("evidence", [])[:2])
    return {"evidence": evidence}


def _evidence_dict(item: Any) -> dict[str, Any]:
    if not isinstance(item, dict):
        return {}
    return {
        "page": item.get("physical_page") or item.get("page"),
        "printed_page": item.get("printed_page"),
        "section": " / ".join(item.get("section_path", []))
        if isinstance(item.get("section_path"), list)
        else item.get("section"),
        "block_id": item.get("block_id"),
        "block_type": item.get("block_type"),
        "quote": item.get("quote") or item.get("text"),
    }
