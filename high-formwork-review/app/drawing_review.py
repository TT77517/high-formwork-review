"""图文一致性校验。

从正文提取关键参数（步距、间距、托撑悬臂等），
从图纸页面文本 block 中尝试提取数值，
比对正文参数与图纸参数是否一致。

文本层为主；对文本稀疏的图片页可选启用 RapidOCR 二次识别
（DRAWING_OCR_ENABLED=true，轻量 onnx 本地推理，无外部服务依赖）。
OCR 来源的值仅作补充证据（source: ocr），置信度低于文本层。
输出 PASS / ISSUE / REVIEW

参数配置的规范依据（三方映射表 rule/三方映射表_Part1/Part3）：
- 步距           JGJ231-2010 6.2.3（≤1.5m，顶层≤1.0m）
- 托撑悬臂长度   JGJ231-2010 6.1.6（严禁超过650mm）
- 丝杆外露长度   JGJ231-2010 6.1.6（严禁超过400mm）
- 立杆纵/横距    JGJ231-2010 6.1.4（不宜大于1.5m）
- 搭设高度       住建部37号令（≥8m 超规模须专家论证）
- 高宽比         JGJ231-2010 6.1.4 / GB51210 8.3.2（不应大于3.0）
- 扫地杆高度     JGJ231-2010（最底层水平杆中心线离底板≤550mm）
"""

from __future__ import annotations

import os
import re
import unicodedata
from pathlib import Path
from typing import Any

from dotenv import load_dotenv

from .models import MinerUDocument, MinerUPage


PROJECT_ROOT = Path(__file__).resolve().parent.parent


def _load_project_env() -> None:
    """加载项目根 .env，与启动目录无关。"""
    load_dotenv(PROJECT_ROOT / ".env", override=False)


# 图文比对参数配置
# 只比对方案 facts 中已识别的参数（fact 值为 None 时跳过，不编造"方案值"）
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
        # "纵距"是"纵距内附加梁底支撑主梁根数"等字段名的前缀 → 排除
        "exclude_terms": ["附加", "根数", "是否相等"],
    },
    {
        "fact_id": "horizontal_spacing",
        "name": "立杆横距",
        "keywords": ["横距", "横向间距", "立杆横距"],
        "unit_pattern": r"(\d+\.?\d*)\s*(?:mm|cm|m|毫米|厘米|米)?",
        # 同 vertical_spacing：挡"横距是否相等 是 纵向间距la(mm) 900"这类跨字段抓取
        # （否则横距会抓到纵距的值，可能造成假 PASS）
        "exclude_terms": ["附加", "根数", "是否相等"],
    },
    {
        "fact_id": "support_height",
        "name": "搭设高度",
        "keywords": ["搭设高度", "支模高度", "支架高度"],
        "unit_pattern": r"(\d+\.?\d*)\s*(?:mm|cm|m|毫米|厘米|米)?",
    },
    {
        "fact_id": "head_jack_screw_exposed_length",
        "name": "可调托撑丝杆外露长度",
        # JGJ231 6.1.6：丝杆外露长度严禁超过400mm；"丝杆外露"须完整表述避免误命中
        "keywords": ["丝杆外露", "螺杆外露", "丝杆外露长度"],
        "unit_pattern": r"(\d+\.?\d*)\s*(?:mm|cm|毫米|厘米)?",
    },
    {
        "fact_id": "height_to_width_ratio",
        "name": "高宽比",
        # JGJ231 6.1.4 / GB51210 8.3.2：不应大于3.0（无量纲）
        "keywords": ["高宽比"],
        "unit_pattern": r"(\d+\.?\d*)",
        # 无单位参数：gap 必须收紧且不跨行，否则"高宽比验算"标题后
        # 任意数字（页码/规范号/日期）都会被误抓
        "gap_pattern": r"[^0-9\-—~～\n]{0,6}",
        # 合理值域护栏（规范限值 3.0，验算值域放宽到 20）
        "plausible_min": 0.1,
        "plausible_max": 20.0,
        "dimensionless": True,
    },
    {
        "fact_id": "sweeper_centerline_height_above_base_plate",
        "name": "扫地杆高度",
        # JGJ231：最底层水平杆中心线离可调底座底板高度不应大于550mm
        "keywords": ["扫地杆", "最底层水平杆"],
        "unit_pattern": r"(\d+\.?\d*)\s*(?:mm|cm|毫米|厘米)?",
    },
]


def build_drawing_review(
    parsed_document: MinerUDocument,
    project_facts: dict[str, Any],
    *,
    job_dir: Path | None = None,
) -> list[dict[str, Any]]:
    facts = project_facts.get("facts", {})
    results: list[dict[str, Any]] = []

    # 1. 图文参数交叉验证（含可选 OCR 通道）
    ocr_engine = _get_ocr_engine()
    ocr_texts = (
        _ocr_sparse_pages(parsed_document, ocr_engine, job_dir=job_dir)
        if ocr_engine
        else {}
    )
    for param_config in DRAWING_CROSS_CHECK_PARAMS:
        result = _cross_check_param(
            parsed_document, facts, param_config, ocr_texts=ocr_texts
        )
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
    *,
    ocr_texts: dict[int, str] | None = None,
) -> dict[str, Any] | None:
    """比对正文参数值与图纸页面文本中的数值。

    ocr_texts: 稀疏图片页的 OCR 识别结果（页码→文本），作为文本层的补充来源。
    OCR 命中的值标 source: ocr，仅作辅助证据。
    """
    fact_id = config["fact_id"]
    param_name = config["name"]
    keywords = config["keywords"]
    unit_pattern = config["unit_pattern"]
    # 无单位参数（高宽比）需要更紧的 gap 防止误抓无关数字；有单位参数默认
    # gap 也不得跨句读标点（。，；：半角逗号分号）和换行——否则条文编号
    # （";3"）、页码（跨行"方案\n7"）、图号（"示意图如下:\n(10"）都会被当成图纸标注值。
    # 顿号、不挡：组合字段标注"纵距、横距(mm) 900×900"中顿号是字段名并列，值共用
    gap_pattern = config.get("gap_pattern", r"[^0-9\-—~～。，；：,;\n]{0,30}?")
    plausible_min = config.get("plausible_min")
    plausible_max = config.get("plausible_max")
    exclude_terms = config.get("exclude_terms", [])

    # 获取正文参数值
    fact = facts.get(fact_id, {})
    if not isinstance(fact, dict):
        return None
    body_value = fact.get("value")
    if body_value is None:
        return None  # 方案未识别该参数 → 不比对（不编造方案值）

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
        # OCR 补充文本拼接（文本层稀疏的图片页）
        ocr_extra = unicodedata.normalize("NFKC", (ocr_texts or {}).get(page.physical_page, ""))
        if ocr_extra:
            norm = norm + "\n" + ocr_extra
        # 遍历全部关键词（别名形式不同：同一参数可能"纵距"和"纵向间距"都出现，
        # 短词只命中被排除的字段名时，长词别名仍能匹配真值）。
        # 同一处数值可能被多个别名命中（"悬臂长"⊂"悬臂长度"，span 宽窄不同）→
        # 按数值捕获组终点去重，否则众数计数被别名倍数扭曲、证据槽被重复挤占
        seen_value_ends: set[int] = set()
        for kw in keywords:
            if kw not in norm:
                continue
            # 在关键词附近找数值
            pattern = re.escape(kw) + gap_pattern + unit_pattern
            for m in re.finditer(pattern, norm, re.IGNORECASE):
                if m.start(1) in seen_value_ends:
                    continue
                seen_value_ends.add(m.start(1))
                quote = m.group(0).strip()
                if _is_spec_clause_quote(quote, kw):
                    continue  # 规范条文引用（"不得大于/严禁超过…"）不是图纸标注
                # 排除词护栏：关键词只是其他字段名前缀（"纵距内附加…根数 0"）
                if any(term in quote for term in exclude_terms):
                    continue
                val_str = m.group(1)
                try:
                    val = float(val_str)
                except ValueError:
                    continue
                # 合理值域护栏（无量纲参数防误抓页码/规范号等）
                if plausible_min is not None and val < plausible_min:
                    continue
                if plausible_max is not None and val > plausible_max:
                    continue
                entry = {
                    "value": val,
                    "page": page.physical_page,
                    "quote": quote,
                    "keyword": kw,
                }
                # 值来自 OCR 拼接段时标注来源（按捕获组位置判定，关键词
                # 可在文本层而数值落在 OCR 段），便于人工区分置信度
                if ocr_extra and m.start(1) > len(norm) - len(ocr_extra) - 1:
                    entry["source"] = "ocr"
                drawing_values.append(entry)

    # 按值去重：_page_text 拼接 page.text 与 block text（内容重叠），
    # 同一标注天然匹配两次；众数按"出现的标注处数"计，不按文本重复次数
    deduped: list[dict[str, Any]] = []
    seen: set[tuple[Any, Any, Any]] = set()
    for item in drawing_values:
        key = (item["page"], item["value"], item["quote"])
        if key in seen:
            continue
        seen.add(key)
        deduped.append(item)
    drawing_values = deduped

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

    # 无量纲参数（高宽比）：不做 mm 单位归一，按原值比对（容差取小值）
    dimensionless = config.get("dimensionless", False)

    def _normalize_to_mm(val: float, text: str) -> float:
        """根据上下文推测单位并统一为mm。"""
        if dimensionless:
            return val  # 无量纲：不换算
        # 如果值很小（<50），可能是m
        if val < 50:
            return val * 1000  # m -> mm
        return val  # 已经是mm

    def _fmt(val: float) -> str:
        return f"{val}" if dimensionless else f"{val}mm"

    body_mm = _normalize_to_mm(float(body_value), str(body_value))
    # 多跨/多部位工程同一参数会有多个合法标注值（如梁下 1200、板下 900），
    # 图纸值集合中任一值与正文一致即 PASS；全部不一致才 ISSUE
    drawing_mms = [
        _normalize_to_mm(item["value"], item.get("quote", ""))
        for item in drawing_values
    ]
    if dimensionless:
        tolerance = 0.01  # 高宽比等比值：1% 绝对容差（规范限值 3.0，5% 相对容差过宽）
    else:
        tolerance = 0.05 * abs(body_mm)  # 5% 容差
    matched = [v for v in drawing_mms if abs(v - body_mm) <= tolerance]
    if matched:
        status = "PASS"
        matched_value = drawing_values[drawing_mms.index(matched[0])]["value"]
        reason = (
            f"正文参数={body_value}，图纸标注含一致值（{matched_value}，"
            f"全部标注值：{sorted(set(drawing_mms))}），图文一致"
            if dimensionless
            else f"正文参数={body_value}，图纸标注含一致值（{matched_value}，"
            f"全部标注值：{sorted(set(drawing_mms))}mm），图文一致"
        )
    else:
        drawing_value = _representative_value(drawing_values)
        status = "ISSUE"
        reason = (
            f"正文参数={body_value}，图纸标注={drawing_value}，"
            f"不一致（{body_value} vs 全部标注值 {sorted(set(drawing_mms))}）"
            if dimensionless
            else f"正文参数={body_value}，图纸标注={drawing_value}，单位统一后不一致"
            f"（{body_mm}mm vs 全部标注值 {sorted(set(drawing_mms))}mm）"
        )
        matched_value = drawing_value

    return _build_cross_result(
        review_id, param_name, body_value, matched_value,
        _enrich_drawing_evidence(document, drawing_values[:3]),
        status, reason,
        text_evidence=[_evidence_dict(item) for item in fact.get("evidence", [])[:3]],
    )


def _enrich_drawing_evidence(
    document: MinerUDocument,
    evidence: list[dict[str, Any]],
) -> list[dict[str, Any]]:
    """给图纸证据补 image_path/table_html/block 定位（前端证据缩略图依赖）。

    优先补该页数值所在性质的素材：有 image block 的页补图片（图纸页），
    否则补表格 HTML（参数表/规格表页，前端真渲染表格）。
    """
    pages_by_no = {page.physical_page: page for page in document.pages}
    for item in evidence:
        page = pages_by_no.get(item.get("page"))
        if page is None:
            continue
        image_block = next(
            (
                block
                for block in page.blocks
                if block.block_type in {"image", "figure", "chart"}
                and getattr(block, "image_path", None)
            ),
            None,
        )
        if image_block is not None:
            item["image_path"] = image_block.image_path
            item["block_id"] = image_block.block_id
            item["block_type"] = image_block.block_type
            item.setdefault("source", "ocr" if item.get("source") == "ocr" else "native_text")
            continue
        # 无图片：找含关键词的表格 block，补 table_html 供前端渲染
        keyword = item.get("keyword", "")
        table_block = next(
            (
                block
                for block in page.blocks
                if block.block_type in {"table", "table_continuation"}
                and getattr(block, "table_html", None)
                and (keyword in (block.text or "") or not keyword)
            ),
            None,
        )
        if table_block is not None:
            item["table_html"] = table_block.table_html
            item["block_id"] = table_block.block_id
            item["block_type"] = table_block.block_type
            item.setdefault("source", "table")
    return evidence


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
    evidence_quality = _evidence_quality(drawing_evidence, status)
    explanation = _review_explanation(
        status=status,
        conclusion=reason,
        text_evidence=text_evidence or [],
        drawing_evidence=drawing_evidence,
        body_value=body_value,
        drawing_value=drawing_value,
        evidence_quality=evidence_quality,
    )
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
        "evidence_quality": evidence_quality,
        "review_explanation": explanation,
        "automation_level": "text_level_cross_check",
        "requires_human_review": status != "PASS",
        "boundary": (
            "图纸页文本层 + 图片OCR（如启用）提取数值；图片内无文字标注的尺寸仍需人工复核。"
            if _ocr_enabled()
            else "当前仅从图纸页面文本block中提取数值，不做图片OCR。图纸中无文字标注的尺寸需人工复核。"
        ),
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
    evidence_quality = _evidence_quality(drawings, status)
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
        "evidence_quality": evidence_quality,
        "review_explanation": _review_explanation(
            status=status,
            conclusion=conclusion,
            text_evidence=text_evidence,
            drawing_evidence=drawings,
            body_value=None,
            drawing_value=None,
            evidence_quality=evidence_quality,
        ),
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
                "source": "native_text",
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


# ---------------------------------------------------------------------------
# 可选 RapidOCR 通道（轻量 onnx 本地推理）
# 开关：DRAWING_OCR_ENABLED=true；未安装 rapidocr 或初始化失败时静默降级为纯文本层
# 只对"文本稀疏且含图片 block"的图纸页触发，控制成本与噪声
# ---------------------------------------------------------------------------

_OCR_ENGINE: Any = None
_OCR_ENGINE_LOADED = False
_SPARSE_TEXT_THRESHOLD = 200  # 页面非图片文本低于此字符数视为"文本稀疏"


def _ocr_enabled() -> bool:
    """DRAWING_OCR_ENABLED 开关状态（仅查配置，不初始化引擎）。"""
    _load_project_env()
    return os.getenv("DRAWING_OCR_ENABLED", "false").strip().lower() in {
        "1", "true", "yes", "on",
    }


def _get_ocr_engine() -> Any:
    """惰性初始化 RapidOCR 引擎；未启用/未安装/初始化失败返回 None。"""
    global _OCR_ENGINE, _OCR_ENGINE_LOADED
    if _OCR_ENGINE_LOADED:
        return _OCR_ENGINE
    _OCR_ENGINE_LOADED = True
    if not _ocr_enabled():
        return None
    try:
        from rapidocr_onnxruntime import RapidOCR  # type: ignore

        _OCR_ENGINE = RapidOCR()
    except Exception:
        _OCR_ENGINE = None  # 未安装或初始化失败 → 纯文本层，不阻断审查
    return _OCR_ENGINE


def _is_sparse_drawing_page(page: MinerUPage) -> bool:
    """图纸页且文本层稀疏（内容主要在图片里）→ OCR 候选页。"""
    text_len = sum(
        len(block.text or "")
        for block in page.blocks
        if block.block_type not in {"image", "figure", "chart"}
    )
    has_image = any(
        block.block_type in {"image", "figure", "chart"} for block in page.blocks
    )
    return has_image and text_len < _SPARSE_TEXT_THRESHOLD


def _ocr_sparse_pages(
    document: MinerUDocument, engine: Any, *, job_dir: Path | None = None
) -> dict[int, str]:
    """对文本稀疏的图纸页跑 OCR，返回 页码→识别文本。

    job_dir 提供时优先直接拼路径（O(1)，无文件系统搜索）；
    未提供时按文件名在 DATA_ROOT/web/jobs 下搜索（O(全部任务)，慢，兜底）。
    任何页识别失败都跳过（静默降级），不影响主流程。
    """
    if engine is None:
        return {}
    results: dict[int, str] = {}
    for page in document.pages:
        if page.parse_status == "unreadable" or not _is_sparse_drawing_page(page):
            continue
        page_texts: list[str] = []
        for block in page.blocks:
            rel = getattr(block, "image_path", None)
            if not rel or block.block_type not in {"image", "figure", "chart"}:
                continue
            img_path = (
                _resolve_image_path_direct(job_dir, rel)
                if job_dir is not None
                else _resolve_image_path(rel)
            )
            if img_path is None:
                continue
            try:
                ocr_result, _ = engine(str(img_path))
            except Exception:
                continue
            if not ocr_result:
                continue
            for item in ocr_result:
                # rapidocr 返回 [box, text, score]
                if isinstance(item, (list, tuple)) and len(item) >= 2:
                    page_texts.append(str(item[1]))
        if page_texts:
            results[page.physical_page] = "\n".join(page_texts)
    return results


def _resolve_image_path_direct(job_dir: Path, rel: str) -> Path | None:
    """job 目录内直接拼路径：mineru_api/raw/<rel>，不存在再试 mineru_api/<rel>。"""
    for base in (
        job_dir / "mineru_api" / "raw",
        job_dir / "mineru_api",
    ):
        candidate = base / rel
        if candidate.is_file():
            return candidate
    return None


def _resolve_image_path(rel: str) -> Path | None:
    """把 MinerU 相对图片路径解析为可读文件。

    相对路径形如 part-001/raw/images/<hash>.jpg，锚点在 DATA_ROOT/web/jobs/
    <job>/mineru_api/raw/ 下。文件名是内容 hash，全任务唯一 → 按文件名
    rglob 定位；找不到（旧任务无 raw 资源）返回 None，该页静默跳过。
    """
    _load_project_env()
    p = Path(rel)
    if p.is_absolute():
        return p if p.is_file() else None
    data_root = os.getenv("DATA_ROOT", "").strip()
    if not data_root:
        return None
    jobs_root = Path(data_root).expanduser() / "web" / "jobs"
    if not jobs_root.is_dir():
        return None
    filename = p.name
    try:
        matches = sorted(jobs_root.rglob(filename))
    except (OSError, ValueError):
        return None
    return matches[0] if matches else None


# 规范条文式表述：引用的数值是规范限值而非本工程图纸标注
_SPEC_CLAUSE_MARKERS = (
    "不得大于", "不应大于", "严禁超过", "不得超过", "不宜大于",
    "不应小于", "不得小于", "不应超过", "不宜超过", "不应高于",
    "不应低于", "最大不得超过", "限值",
    # 图纸说明常用简写："丝杆外露长度≤400mm""高宽比≤3.0""扫地杆高度不大于550"
    "≤", "≥", "不大于", "不超过", "小于", "大于",
    # 条文叙述里的数量引用："当架体高度超过4m…""步距大于1.5m时"
    "超过", "应为", "宜为", "符合规范", "符合要求", "按规范",
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


def _evidence_quality(
    drawing_evidence: list[dict[str, Any]],
    status: str,
) -> dict[str, Any]:
    if not drawing_evidence:
        return {
            "level": "weak",
            "label": "证据弱",
            "reasons": ["未召回可定位的图纸文字或表格证据"],
        }

    values = {
        str(item.get("value"))
        for item in drawing_evidence
        if item.get("value") is not None
    }
    if len(values) >= 2:
        return {
            "level": "conflict",
            "label": "数值冲突",
            "reasons": [f"图纸证据出现多个候选值：{', '.join(sorted(values))}"],
        }

    sources = {item.get("source") or item.get("block_type") for item in drawing_evidence}
    if "ocr" in sources:
        return {
            "level": "medium",
            "label": "OCR命中",
            "reasons": ["图纸值来自图片 OCR，需人工核对识别准确性"],
        }
    if any(item.get("table_html") or item.get("block_type") in {"table", "table_continuation"} for item in drawing_evidence):
        return {
            "level": "high",
            "label": "表格命中",
            "reasons": ["图纸值来自 MinerU 表格结构化证据"],
        }
    if any(item.get("quote") or item.get("keyword_hits") for item in drawing_evidence):
        return {
            "level": "high" if status == "PASS" else "medium",
            "label": "原文命中",
            "reasons": ["图纸页文本层命中构造关键词或参数标注"],
        }
    return {
        "level": "weak",
        "label": "证据弱",
        "reasons": ["仅召回图片页，缺少可解析的文字标注"],
    }


def _review_explanation(
    *,
    status: str,
    conclusion: str,
    text_evidence: list[dict[str, Any]],
    drawing_evidence: list[dict[str, Any]],
    body_value: float | None,
    drawing_value: float | None,
    evidence_quality: dict[str, Any],
) -> dict[str, Any]:
    found: list[str] = []
    missing: list[str] = []
    if body_value is not None:
        found.append(f"正文识别值：{body_value}")
    elif text_evidence:
        found.append(f"召回正文证据 {len(text_evidence)} 条")
    else:
        missing.append("未取得正文参数证据")
    if drawing_value is not None:
        found.append(f"图纸标注值：{drawing_value}")
    elif drawing_evidence:
        found.append(f"召回图纸页/图纸证据 {len(drawing_evidence)} 条")
    else:
        missing.append("未取得图纸标注值")
    if evidence_quality.get("level") in {"weak", "conflict"}:
        missing.extend(evidence_quality.get("reasons") or [])
    return {
        "found": found,
        "missing": missing,
        "decision": conclusion if conclusion else f"当前状态：{status}",
    }
