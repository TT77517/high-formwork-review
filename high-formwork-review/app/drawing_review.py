"""图文一致性校验。

从正文提取关键参数（步距、间距、托撑悬臂等），
从图纸页面文本 block 中尝试提取数值，
比对正文参数与图纸参数是否一致。

当前为文本级图文交叉验证，不做图片 OCR。
输出 PASS / ISSUE / REVIEW
"""

from __future__ import annotations

import re
import unicodedata
from typing import Any

from .models import MinerUDocument, MinerUPage


# 图文比对参数配置
DRAWING_CROSS_CHECK_PARAMS = [
    {
        "fact_id": "standard_step_height",
        "name": "步距",
        "keywords": ["步距", "水平杆步距", "标准步距", "架体步距"],
        "unit_pattern": r"(\d+\.?\d*)\s*(?:mm|cm|m|毫米|厘米|米)?",
    },
    {
        "fact_id": "head_jack_cantilever_length",
        "name": "可调托撑悬臂长度",
        # "托撑"单用会误命中"托撑+承插型插槽式"等支架名称行；
        # "悬臂"单用会误命中"悬臂端计算长度折减系数k"等计算参数 → 都用完整表述
        "keywords": ["悬臂长度", "顶托悬臂", "悬臂长", "伸出顶层"],
        "unit_pattern": r"(\d+\.?\d*)\s*(?:mm|cm|毫米|厘米)?",
    },
    {
        "fact_id": "vertical_spacing",
        "name": "立杆纵距",
        "keywords": ["纵距", "纵向间距", "立杆纵距"],
        "unit_pattern": r"(\d+\.?\d*)\s*(?:mm|cm|m|毫米|厘米|米)?",
    },
    {
        "fact_id": "horizontal_spacing",
        "name": "立杆横距",
        "keywords": ["横距", "横向间距", "立杆横距"],
        "unit_pattern": r"(\d+\.?\d*)\s*(?:mm|cm|m|毫米|厘米|米)?",
    },
    {
        "fact_id": "support_height",
        "name": "搭设高度",
        "keywords": ["搭设高度", "支模高度", "支架高度"],
        "unit_pattern": r"(\d+\.?\d*)\s*(?:mm|cm|m|毫米|厘米|米)?",
    },
]


def build_drawing_review(
    parsed_document: MinerUDocument,
    project_facts: dict[str, Any],
) -> list[dict[str, Any]]:
    facts = project_facts.get("facts", {})
    results: list[dict[str, Any]] = []

    # 1. 图文参数交叉验证
    for param_config in DRAWING_CROSS_CHECK_PARAMS:
        result = _cross_check_param(parsed_document, facts, param_config)
        if result:
            results.append(result)

    # 2. 图纸证据召回（保留原有功能）
    results.append(
        _drawing_recall_card(
            "DR-90",
            "支撑架关键构造图文复核",
            "核对步距、可调托撑悬臂、立杆布置等正文/计算参数是否在图纸中有对应表达。",
            _merge_fact_evidence(
                facts,
                ("standard_step_height", "head_jack_cantilever_length", "support_system"),
            ),
            parsed_document,
            ("支撑架", "立杆", "水平杆", "可调托撑", "节点", "剖面", "立面"),
        )
    )

    return results


def _cross_check_param(
    document: MinerUDocument,
    facts: dict[str, Any],
    config: dict[str, Any],
) -> dict[str, Any] | None:
    """比对正文参数值与图纸页面文本中的数值。"""
    fact_id = config["fact_id"]
    param_name = config["name"]
    keywords = config["keywords"]
    unit_pattern = config["unit_pattern"]

    # 获取正文参数值
    fact = facts.get(fact_id, {})
    if not isinstance(fact, dict):
        return None
    body_value = fact.get("value")
    if body_value is None:
        return None

    # 从图纸页面提取数值
    drawing_values: list[dict[str, Any]] = []
    for page in document.pages:
        if page.parse_status == "unreadable":
            continue
        # 判断是否为图纸相关页面
        page_text = _page_text(page)
        norm = unicodedata.normalize("NFKC", page_text)
        is_drawing_page = page.page_type in {"drawing", "mixed", "image"} or any(
            block.block_type in {"image", "figure", "chart"} for block in page.blocks
        )
        if not is_drawing_page:
            continue
        for kw in keywords:
            if kw not in norm:
                continue
            # 在关键词附近找数值
            pattern = re.escape(kw) + r"[^0-9\-—~～]*?" + unit_pattern
            for m in re.finditer(pattern, norm, re.IGNORECASE):
                quote = m.group(0).strip()
                if _is_spec_clause_quote(quote, kw):
                    continue  # 规范条文引用（"不得大于/严禁超过…"）不是图纸标注
                val_str = m.group(1)
                try:
                    val = float(val_str)
                    drawing_values.append({
                        "value": val,
                        "page": page.physical_page,
                        "quote": quote,
                        "keyword": kw,
                    })
                except ValueError:
                    continue
            break  # 只用第一个匹配的关键词

    review_id = f"DR-{DRAWING_CROSS_CHECK_PARAMS.index(config) + 1:02d}"

    if not drawing_values:
        return _build_cross_result(
            review_id, param_name, body_value, None, [],
            "REVIEW",
            f"正文参数={body_value}，未在图纸页面文本中找到该参数的对应数值，需人工复核图纸标注",
            text_evidence=[_evidence_dict(item) for item in fact.get("evidence", [])[:3]],
        )

    # 取图纸中的代表值：出现次数最多的值（规格表多次标注同一值时更稳，避免取到第一条无关数值）
    drawing_value = _representative_value(drawing_values)

    # 比对 — 先统一单位（mm和m之间换算）
    def _normalize_to_mm(val: float, text: str) -> float:
        """根据上下文推测单位并统一为mm。"""
        # 如果值很小（<50），可能是m
        if val < 50:
            return val * 1000  # m -> mm
        return val  # 已经是mm

    body_mm = _normalize_to_mm(float(body_value), str(body_value))
    # 多跨/多部位工程同一参数会有多个合法标注值（如梁下 1200、板下 900），
    # 图纸值集合中任一值与正文一致即 PASS；全部不一致才 ISSUE
    drawing_mms = [
        _normalize_to_mm(item["value"], item.get("quote", ""))
        for item in drawing_values
    ]
    tolerance = 0.05 * abs(body_mm)  # 5% 容差
    matched = [v for v in drawing_mms if abs(v - body_mm) <= tolerance]
    if matched:
        status = "PASS"
        matched_value = drawing_values[drawing_mms.index(matched[0])]["value"]
        reason = (
            f"正文参数={body_value}，图纸标注含一致值（{matched_value}，"
            f"全部标注值：{sorted(set(drawing_mms))}mm），图文一致"
        )
    else:
        drawing_value = _representative_value(drawing_values)
        drawing_mm = _normalize_to_mm(
            float(drawing_value), drawing_values[0].get("quote", "")
        )
        status = "ISSUE"
        reason = (
            f"正文参数={body_value}，图纸标注={drawing_value}，单位统一后不一致"
            f"（{body_mm}mm vs 全部标注值 {sorted(set(drawing_mms))}mm）"
        )
        matched_value = drawing_value

    return _build_cross_result(
        review_id, param_name, body_value, matched_value, drawing_values[:3],
        status, reason,
        text_evidence=[_evidence_dict(item) for item in fact.get("evidence", [])[:3]],
    )


def _build_cross_result(
    review_id: str,
    param_name: str,
    body_value: float | None,
    drawing_value: float | None,
    drawing_evidence: list[dict[str, Any]],
    status: str,
    reason: str,
    text_evidence: list[dict[str, Any]] | None = None,
) -> dict[str, Any]:
    return {
        "review_item_id": review_id,
        "category": "图文一致性",
        "title": f"{param_name}图文交叉验证",
        "review_method": "text_drawing_cross_check",
        "status": status,
        "conclusion": reason,
        "body_value": body_value,
        "drawing_value": drawing_value,
        "text_evidence": text_evidence or [],
        "drawing_evidence": drawing_evidence,
        "automation_level": "text_level_cross_check",
        "requires_human_review": status != "PASS",
        "boundary": "当前仅从图纸页面文本block中提取数值，不做图片OCR。图纸中无文字标注的尺寸需人工复核。",
    }


def _drawing_recall_card(
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
        conclusion = "已召回正文证据和相关图纸页；需人工进行图文一致性复核。"
    elif drawings:
        conclusion = "已召回相关图纸页，但正文参数证据不足，需人工复核。"
    else:
        conclusion = "未召回相关图纸页，需人工从图纸目录确认。"
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
        "boundary": "系统仅召回疑似相关图纸页和正文证据；图纸尺寸需人工复核。",
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


# 规范条文式表述：引用的数值是规范限值而非本工程图纸标注
_SPEC_CLAUSE_MARKERS = (
    "不得大于", "不应大于", "严禁超过", "不得超过", "不宜大于",
    "不应小于", "不得小于", "不应超过", "不宜超过", "不应高于",
    "不应低于", "最大不得超过", "限值",
)


def _is_spec_clause_quote(quote: str, keyword: str) -> bool:
    """判断引用文本是否为规范条文（限值表述）而非工程图纸标注。

    图纸/规格表标注通常形如"步距(mm) 1500""横距 900"；
    条文引用形如"步距不得大于1.5m""悬臂长度严禁超过650mm"。
    """
    # 关键词与数值之间的连接文本含限值表述 → 条文
    tail = quote[len(keyword):] if quote.startswith(keyword) else quote
    return any(marker in tail for marker in _SPEC_CLAUSE_MARKERS)


def _representative_value(drawing_values: list[dict[str, Any]]) -> float:
    """取出现次数最多的值；并列时取首次出现的（规格表最先标注的值）。"""
    counts: dict[float, int] = {}
    order: dict[float, int] = {}
    for index, item in enumerate(drawing_values):
        val = item["value"]
        counts[val] = counts.get(val, 0) + 1
        order.setdefault(val, index)
    return max(counts, key=lambda v: (counts[v], -order[v]))


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
