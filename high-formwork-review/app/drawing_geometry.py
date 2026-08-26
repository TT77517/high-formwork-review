"""图纸几何/构造参数抽取与反哺参数校核。

目标：
* 从图纸页（OCR 或文本层）抽取结构几何与构造参数：
  - 立杆横距/纵距/步距（图纸标注）
  - 扫地杆高度（构造大样）
  - 垫板尺寸、剪刀撑间距
  - 主楞/次楞截面、间距
* 输出独立于正文 facts 的"图纸参数候选"列表
* 提供与正文 facts 的交叉比对：
  - 一致 → 增强事实置信度
  - 不一致 → 列入人工复核（图文冲突）
  - 图纸有正文无 → 提示补充
  - 正文有图纸无 → 现有逻辑不动（正文优先）

设计原则：
* 不重写 drawing_review.build_drawing_review，而是新增独立函数
* 复用 MinerU 文本层；OCR 通道交由调用方按需启用
* 抽取规则明确写入 DRAWING_GEOMETRY_PARAMS，便于审查与扩展
"""

from __future__ import annotations

import re
from collections import Counter
from typing import Any

from .models import MinerUDocument
from .text_utils import norm as _norm


# 图纸几何/构造参数抽取配置
# 复用 drawing_review 的排除词风格，避免误抓规范条文/页码/图号
DRAWING_GEOMETRY_PARAMS: list[dict[str, Any]] = [
    {
        "fact_id": "vertical_spacing",
        "name": "立杆纵距",
        "aliases": ["立杆纵距", "纵距", "纵向间距", "la", "LA"],
        "unit_pattern": r"(\d+(?:\.\d+)?)\s*(?:mm|cm|m|毫米|厘米|米)?",
        "exclude_terms": ["附加", "根数", "是否相等", "说明", "应符合"],
        "plausible_min": 0.4,
        "plausible_max": 2.0,
    },
    {
        "fact_id": "horizontal_spacing",
        "name": "立杆横距",
        "aliases": ["立杆横距", "横距", "横向间距", "lb", "LB"],
        "unit_pattern": r"(\d+(?:\.\d+)?)\s*(?:mm|cm|m|毫米|厘米|米)?",
        "exclude_terms": ["附加", "根数", "是否相等", "说明", "应符合"],
        "plausible_min": 0.4,
        "plausible_max": 2.0,
    },
    {
        "fact_id": "standard_step_height",
        "name": "标准步距",
        "aliases": ["标准步距", "步距", "h", "架体步距"],
        "unit_pattern": r"(\d+(?:\.\d+)?)\s*(?:mm|cm|m|毫米|厘米|米)?",
        "exclude_terms": ["顶层", "水平杆步距", "扫地", "插入"],
        "plausible_min": 0.5,
        "plausible_max": 2.0,
    },
    {
        "fact_id": "sweeper_centerline_height_above_base_plate",
        "name": "扫地杆中心线高度",
        "aliases": ["扫地杆", "最底层水平杆", "扫地杆中心线", "扫地杆高度"],
        "unit_pattern": r"(\d+(?:\.\d+)?)\s*(?:mm|cm|毫米|厘米)?",
        "plausible_min": 50,
        "plausible_max": 600,
    },
    {
        "fact_id": "head_jack_cantilever_length",
        "name": "可调托撑悬臂长度",
        "aliases": ["悬臂长度", "顶托悬臂", "伸出顶层", "可调托撑悬臂"],
        "unit_pattern": r"(\d+(?:\.\d+)?)\s*(?:mm|cm|毫米|厘米)?",
        "plausible_min": 0,
        "plausible_max": 700,
    },
    {
        "fact_id": "head_jack_screw_exposed_length",
        "name": "可调托撑丝杆外露长度",
        "aliases": ["丝杆外露", "螺杆外露", "丝杆外露长度"],
        "unit_pattern": r"(\d+(?:\.\d+)?)\s*(?:mm|cm|毫米|厘米)?",
        "plausible_min": 0,
        "plausible_max": 450,
    },
    {
        "fact_id": "base_plate_area",
        "name": "垫板/底座尺寸",
        "aliases": ["垫板", "底座", "底板", "垫板尺寸", "底座尺寸"],
        # 垫板面积常以"长×宽"或"mm×mm"形式标注 → 支持两数
        "unit_pattern": r"(\d+(?:\.\d+)?)\s*[xX×*]\s*(\d+(?:\.\d+)?)\s*(?:mm|cm|毫米|厘米)?",
        "plausible_min": 50,
        "plausible_max": 1000,
    },
    {
        "fact_id": "horizontal_scissor_brace_interval",
        "name": "水平剪刀撑设置间隔",
        "aliases": ["水平剪刀撑", "剪刀撑间距", "每间隔", "标准步距"],
        "unit_pattern": r"(\d+(?:\.\d+)?)\s*(?:个)?\s*[~～\-至到]?\s*(\d+(?:\.\d+)?)?\s*(?:个)?\s*标准?步距",
        "plausible_min": 2,
        "plausible_max": 12,
    },
    {
        "fact_id": "panel_thickness",
        "name": "面板厚度",
        "aliases": ["面板厚度", "模板厚度", "胶合板厚度"],
        "unit_pattern": r"(\d+(?:\.\d+)?)\s*(?:mm|毫米)?",
        "plausible_min": 8,
        "plausible_max": 25,
    },
    {
        "fact_id": "stringer_spacing",
        "name": "次楞间距",
        "aliases": ["次楞间距", "次龙骨间距", "小楞间距"],
        "unit_pattern": r"(\d+(?:\.\d+)?)\s*(?:mm|cm|毫米|厘米)?",
        "plausible_min": 100,
        "plausible_max": 600,
    },
    {
        "fact_id": "main_beam_spacing",
        "name": "主楞间距",
        "aliases": ["主楞间距", "主龙骨间距", "大楞间距"],
        "unit_pattern": r"(\d+(?:\.\d+)?)\s*(?:mm|cm|毫米|厘米)?",
        "plausible_min": 200,
        "plausible_max": 1500,
    },
]


# 合理值域护栏（防止误抓页码/图号/规范号）
_DEFAULT_GAP = r"[^\d\-—~～\n]{0,30}"


_DRAWING_PAGE_KEYWORDS = (
    "剖面图", "平面图", "立面图", "大样图", "节点图", "构造图",
    "立杆", "横距", "纵距", "步距", "剪刀撑", "扫地杆", "垫板",
    "图例", "说明", "标注", "示意", "剖面", "平面布置",
)


def _is_drawing_page(page: Any) -> bool:
    """判断是否图纸页。

    判定条件（任一满足即视为图纸页）：
    1. MinerUPage.page_type == "drawing"（结构化判定）
    2. 文本层极短（<30 字符）且至少命中一个图纸关键词
       — 防止空白/极短页被误判（之前 <30 直接判 drawing 是 bug）
    3. 文本层中等长度（30~500 字符）但命中 2+ 个图纸关键词
    """
    text = ""
    for block in getattr(page, "blocks", []) or []:
        text += str(getattr(block, "text", "") or "")
    compact = _norm(text)
    if getattr(page, "page_type", None) == "drawing":
        return True
    if not compact:
        return False
    keyword_hits = sum(1 for kw in _DRAWING_PAGE_KEYWORDS if kw in compact)
    if len(compact) < 30 and keyword_hits >= 1:
        return True
    if 30 <= len(compact) <= 500 and keyword_hits >= 2:
        return True
    return False


def _extract_single_param_from_text(
    text: str,
    param_def: dict[str, Any],
) -> list[dict[str, Any]]:
    """从单段文本中按 param_def 抽取一个或多个候选值。"""
    compact = _norm(text)
    candidates: list[dict[str, Any]] = []
    exclude_terms = [str(t) for t in param_def.get("exclude_terms", [])]
    if any(t in compact for t in exclude_terms):
        return candidates
    unit_pattern = param_def.get("unit_pattern", r"(\d+(?:\.\d+)?)")
    plausible_min = param_def.get("plausible_min")
    plausible_max = param_def.get("plausible_max")

    for alias in param_def.get("aliases", []):
        alias_norm = _norm(alias)
        if alias_norm and alias_norm not in compact:
            continue
        for match in re.finditer(re.escape(alias_norm), compact):
            window = compact[match.end(): min(len(compact), match.end() + 60)]
            window = re.split(r"[。；;，,\n]", window, maxsplit=1)[0]
            if not window:
                continue
            value_match = re.search(unit_pattern, window)
            if not value_match:
                continue
            try:
                if value_match.lastindex and value_match.lastindex >= 2 and value_match.group(2):
                    # 形如"长×宽"的两数结果，合成记录但 value 取较小者用于一致性比对
                    v1 = float(value_match.group(1))
                    v2 = float(value_match.group(2))
                    raw = value_match.group(0)
                    primary = min(v1, v2)
                else:
                    v1 = float(value_match.group(1))
                    v2 = None
                    raw = value_match.group(0)
                    primary = v1
            except (ValueError, IndexError):
                continue
            if plausible_min is not None and primary < plausible_min:
                continue
            if plausible_max is not None and primary > plausible_max:
                continue
            candidates.append({
                "fact_id": param_def["fact_id"],
                "name": param_def["name"],
                "value": primary,
                "raw_value": raw,
                "unit": "mm" if "mm" in raw or "毫米" in raw else "m" if "m" in raw or "米" in raw else "",
            })
            # 不 break：收集同一 param_def 在本段文本的所有 alias 命中
            # 由外层 _dedupe_candidates 按 (fact_id, raw_value, block_id) 去重
    return candidates


def extract_drawing_geometry_candidates(
    document: MinerUDocument,
) -> list[dict[str, Any]]:
    """从 MinerUDocument 图纸页抽取几何/构造参数候选。

    Returns: list of {fact_id, name, value, raw_value, unit, page, block_id, source}
    """
    candidates: list[dict[str, Any]] = []
    seen: set[tuple[str, str, Any]] = set()
    for page in getattr(document, "pages", []) or []:
        if not _is_drawing_page(page):
            continue
        page_num = getattr(page, "physical_page", None) or getattr(page, "page_number", None)
        for block in getattr(page, "blocks", []) or []:
            text = str(getattr(block, "text", "") or "")
            if not text:
                continue
            block_id = getattr(block, "block_id", None)
            for param_def in DRAWING_GEOMETRY_PARAMS:
                extracted = _extract_single_param_from_text(text, param_def)
                for item in extracted:
                    key = (item["fact_id"], item["raw_value"], block_id)
                    if key in seen:
                        continue
                    seen.add(key)
                    item["page"] = page_num
                    item["block_id"] = block_id
                    item["source"] = "drawing_text"
                    candidates.append(item)
    return candidates


def cross_validate_with_body_facts(
    drawing_candidates: list[dict[str, Any]],
    body_facts: dict[str, Any],
    *,
    tolerance_ratio: float = 0.05,
) -> list[dict[str, Any]]:
    """将图纸几何候选与正文 ProjectFacts 交叉比对。

    判定规则（按 fact_id 分组）：
    * body 缺失 + drawing 有值 → SUPPLEMENT（提示补充）
    * body 有值 + drawing 缺失 → NO_DRAWING_EVIDENCE（中性）
    * 两者都有，差值 ≤ tolerance → MATCH（增强信心）
    * 两者都有，差值 > tolerance → CONFLICT（图文冲突）
    """
    if not drawing_candidates:
        return []

    by_fact: dict[str, list[dict[str, Any]]] = {}
    for c in drawing_candidates:
        by_fact.setdefault(c["fact_id"], []).append(c)

    issues: list[dict[str, Any]] = []
    for fact_id, items in by_fact.items():
        body_fact = body_facts.get(fact_id)
        body_value = body_fact.get("value") if isinstance(body_fact, dict) else None

        drawing_values = [it["value"] for it in items if it.get("value") is not None]
        if not drawing_values:
            continue
        # 图纸侧取众数（同 fact_id 多 block 同值更稳）
        counter = Counter(drawing_values)
        drawing_value, count = counter.most_common(1)[0]

        if body_value is None:
            issues.append({
                "fact_id": fact_id,
                "status": "SUPPLEMENT",
                "body_value": None,
                "drawing_value": drawing_value,
                "drawing_count": count,
                "drawing_pages": sorted({it.get("page") for it in items if it.get("page")}),
                "message": f"正文未识别{_fact_label(fact_id)}，图纸标注值 {drawing_value}，可补充",
            })
            continue

        if body_value == 0:
            continue
        diff_ratio = abs(drawing_value - body_value) / abs(body_value)
        if diff_ratio <= tolerance_ratio:
            issues.append({
                "fact_id": fact_id,
                "status": "MATCH",
                "body_value": body_value,
                "drawing_value": drawing_value,
                "drawing_count": count,
                "message": f"{_fact_label(fact_id)} 正文 {body_value} 与图纸 {drawing_value} 一致",
            })
        else:
            issues.append({
                "fact_id": fact_id,
                "status": "CONFLICT",
                "body_value": body_value,
                "drawing_value": drawing_value,
                "drawing_count": count,
                "diff_ratio": round(diff_ratio, 4),
                "message": (
                    f"{_fact_label(fact_id)} 正文 {body_value} 与图纸 {drawing_value} "
                    f"不一致（差异 {diff_ratio:.1%}）"
                ),
            })
    return issues


def _fact_label(fact_id: str) -> str:
    for item in DRAWING_GEOMETRY_PARAMS:
        if item["fact_id"] == fact_id:
            return item["name"]
    return fact_id
