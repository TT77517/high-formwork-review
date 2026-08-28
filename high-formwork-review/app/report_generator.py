"""审查报告生成与导出模块。

汇总所有审查模块结果，生成结构化 Markdown 审查报告：
工程概况 → 审查依据 → 逐模块审查结果 → 违规项汇总 → 整改建议 → 人工复核记录
"""

from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


def build_review_report(
    job_id: str | None = None,
    file_name: str | None = None,
    project_qualification: dict[str, Any] | None = None,
    completeness_summary: dict[str, Any] | None = None,
    completeness_results: list[dict[str, Any]] | None = None,
    rule_engine_results: dict[str, Any] | None = None,
    substantive_review: list[dict[str, Any]] | None = None,
    consistency_review: list[dict[str, Any]] | None = None,
    drawing_review: list[dict[str, Any]] | None = None,
    agent_drawing_review: dict[str, Any] | None = None,
    decisions: list[dict[str, Any]] | None = None,
    document_meta: dict[str, Any] | None = None,
) -> str:
    """生成完整审查报告 Markdown。"""
    now = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M:%S UTC")
    lines: list[str] = []

    # ===== 报告头 =====
    lines.extend([
        "# 高支模专项施工方案智能审查报告",
        "",
        f"- **方案文件：** {file_name or '—'}",
        f"- **任务编号：** {job_id or '—'}",
        f"- **审查时间：** {now}",
        f"- **审查系统：** 高支模方案智能审查系统 v4.0",
        "",
        "> ⚠️ 本报告由系统自动生成，仅作为专项施工方案预审辅助，需由审查人员人工确认，不作为最终审查结论。",
        "",
    ])

    # ===== 一、工程概况 =====
    q = project_qualification or {}
    params = q.get("identified_parameters", {})
    lines.extend([
        "---",
        "",
        "## 一、工程基础信息",
        "",
        f"- **工程类型：** {_project_type_label(q.get('project_type'))}",
        f"- **风险属性：** {_risk_label(q.get('risk_classification', ''))}",
        f"- **支撑体系：** {q.get('support_system_label', q.get('support_system', '—'))}",
        f"- **支撑高度：** {_param_str(params.get('support_height', {}))}",
        f"- **跨度：** {_param_str(params.get('support_span', {}))}",
        f"- **总荷载：** {_param_str(params.get('total_load_design', {}))}",
        f"- **线荷载：** {_param_str(params.get('concentrated_line_load_design', {}))}",
        f"- **适用规则包：** {'、'.join(q.get('applicable_rule_packs', [])) or '—'}",
        f"- **适用规范：** {'、'.join(s.get('full_code', '') for s in q.get('applicable_standards', [])) or '—'}",
        "",
    ])
    conditions = q.get("triggered_conditions", [])
    if conditions:
        lines.append("**触发条件：**")
        for c in conditions:
            lines.append(f"- {c.get('name', '')}：{c.get('condition', '')}")
        lines.append("")
    key_params = q.get("key_parameters", [])
    if key_params:
        lines.append("**关键参数识别：**")
        for kp in key_params:
            status_cn = {"confirmed": "已识别", "uncertain": "需复核", "conflict": "需复核"}.get(
                kp.get("status", ""), "未识别"
            )
            value = kp.get("value_text") or "—"
            page = kp.get("evidence_page")
            source = f"，来源第{page}页" if page else ""
            drives = "；".join(kp.get("drives", []))
            lines.append(f"- {kp.get('label', '')}：{value}（{status_cn}{source}）→ {drives}")
        lines.append("")

    # ===== 二、文档解析概况 =====
    doc = document_meta or {}
    if doc:
        lines.extend([
            "---",
            "",
            "## 二、文档解析概况",
            "",
            f"- **解析引擎：** {doc.get('engine', 'MinerU')}",
            f"- **总页数：** {doc.get('physical_page_count', '—')}",
            f"- **有效章节：** {doc.get('section_count', '—')}",
            f"- **Block 总数：** {doc.get('block_count', '—')}",
            f"- **完整页：** {doc.get('complete_page_count', '—')}",
            f"- **部分解析：** {doc.get('partial_page_count', '—')}",
            f"- **不可读页：** {doc.get('unreadable_page_count', '—')}",
            "",
        ])

    # ===== 三、审查结果汇总 =====
    lines.extend([
        "---",
        "",
        "## 三、审查结果汇总",
        "",
        "| 审查模块 | 总数 | 合规/通过 | 违规/问题 | 需复核/无法判定 |",
        "|---------|------|----------|----------|----------------|",
    ])

    cs = completeness_summary or {}
    cr_total = cs.get("total_rules", 10)
    cr_pass = cs.get("pass_count", 0)
    cr_issue = 0
    cr_review = cs.get("missing_count", 0) + cs.get("uncertain_count", 0)
    lines.append(f"| 完整性审查 | {cr_total} | {cr_pass} | {cr_issue} | {cr_review} |")

    re = rule_engine_results or {}
    re_total = re.get("total_rules", 0)
    re_compliant = re.get("compliant", 0)
    re_violated = re.get("violated", 0)
    re_uncertain = re.get("uncertain", 0) + re.get("not_applicable", 0) + re.get("pending_confirmation", 0)
    lines.append(f"| 规则引擎审查 | {re_total} | {re_compliant} | {re_violated} | {re_uncertain} |")

    sr = substantive_review or []
    sr_total = len(sr)
    sr_pass = sum(1 for i in sr if i.get("status") == "PASS")
    sr_issue = sum(1 for i in sr if i.get("status") == "ISSUE")
    sr_review = sum(1 for i in sr if i.get("status") == "REVIEW")
    lines.append(f"| 规范符合性审查 | {sr_total} | {sr_pass} | {sr_issue} | {sr_review} |")

    cos = consistency_review or []
    cos_total = len(cos)
    cos_pass = sum(1 for i in cos if i.get("status") == "PASS")
    cos_issue = sum(1 for i in cos if i.get("status") == "ISSUE")
    cos_review = sum(1 for i in cos if i.get("status") == "REVIEW")
    lines.append(f"| 参数一致性检查 | {cos_total} | {cos_pass} | {cos_issue} | {cos_review} |")

    dr = drawing_review or []
    adr = agent_drawing_review or {}
    adr_counts = adr.get("status_counts") or {}
    dr_total = adr.get("total_tasks", len(dr))
    dr_ok = adr_counts.get("CONSISTENT", "—")
    dr_issue = adr_counts.get("CONFLICT", "—")
    dr_review = (
        adr_counts.get("UNCERTAIN", 0)
        + adr_counts.get("TEXT_ONLY", 0)
        + adr_counts.get("DRAWING_ONLY", 0)
        + adr_counts.get("NOT_FOUND", 0)
        if adr_counts
        else sum(1 for i in dr if i.get("requires_human_review"))
    )
    lines.append(f"| 图文一致性审查 | {dr_total} | {dr_ok} | {dr_issue} | {dr_review} |")

    lines.append("")

    # ===== 四、违规项详情 =====
    lines.extend(["---", "", "## 四、违规项与需重点关注事项", ""])

    # 4.1 规则引擎违规
    if re_violated > 0:
        lines.append("### 4.1 规则引擎违规项")
        lines.append("")
        violated = [r for r in re.get("results", []) if r.get("status") == "VIOLATED"]
        for r in violated:
            th = r.get("threshold", {})
            unit = th.get("unit")
            actual_value = _value_unit(r.get("actual_value"), unit, missing_label="—")
            threshold_value = _value_unit(th.get("value"), unit, missing_label="—")
            threshold = f"{th.get('operator', '')} {threshold_value}".strip()
            lines.append(f"**{r.get('rule_id')} {r.get('rule_name')}**")
            lines.append(f"- 风险等级：{r.get('risk_level', '—')}")
            lines.append(f"- 实际值：{actual_value}")
            lines.append(f"- 阈值要求：{threshold or '—'}")
            lines.append(f"- 判定依据：{_format_rule_reason(r.get('reason'))}")
            code = r.get("code_ref", {})
            if code.get("standard"):
                lines.append(f"- 规范依据：{code['standard']}")
            if r.get("remedy_suggestion"):
                lines.append(f"- 整改建议：{_format_rule_reason(r['remedy_suggestion'])}")
            lines.append("")

    # 4.2 规范符合性问题
    if sr_issue > 0:
        lines.append("### 4.2 规范符合性审查问题")
        lines.append("")
        for i in sr:
            if i.get("status") == "ISSUE":
                lines.append(f"**{i.get('review_item_id')} {i.get('title')}**")
                lines.append(f"- 结论：{i.get('conclusion', '—')}")
                basis = i.get("basis", [])
                if basis and isinstance(basis, list) and basis:
                    b0 = basis[0] if isinstance(basis[0], dict) else {}
                    lines.append(f"- 依据：{b0.get('standard', '—')}")
                lines.append("")

    # 4.3 参数一致性不一致
    if cos_issue > 0:
        lines.append("### 4.3 参数一致性问题")
        lines.append("")
        for i in cos:
            if i.get("status") == "ISSUE":
                lines.append(f"**{i.get('review_item_id')} {i.get('title')}**")
                ds = i.get("design_side", {})
                cs2 = i.get("calculation_side", {})
                lines.append(f"- 正文/构造侧：{_side_str(ds)}")
                lines.append(f"- 计算书侧：{_side_str(cs2)}")
                lines.append(f"- 结论：{i.get('conclusion', '—')}")
                lines.append("")

    # 4.4 完整性缺失
    if cs.get("missing_count", 0) > 0:
        lines.append("### 4.4 完整性审查缺项")
        lines.append("")
        for r in (completeness_results or []):
            if r.get("status") == "MISSING":
                lines.append(f"**{r.get('rule_id')} {r.get('name')}**")
                lines.append(f"- {r.get('reason', '—')}")
                lines.append("")

    if adr:
        lines.append("### 4.5 图文一致性审查")
        lines.append("")
        lines.append(
            f"- 检查项：{dr_total}；图文一致：{adr_counts.get('CONSISTENT', 0)}；"
            f"图文冲突：{adr_counts.get('CONFLICT', 0)}；暂无法确定：{adr_counts.get('UNCERTAIN', 0)}；"
            f"仅文本证据：{adr_counts.get('TEXT_ONLY', 0)}；仅图纸证据：{adr_counts.get('DRAWING_ONLY', 0)}；"
            f"未找到足够证据：{adr_counts.get('NOT_FOUND', 0)}"
        )
        lines.append("")
        for item in adr.get("items", []):
            if item.get("status") == "CONSISTENT":
                continue
            lines.append(
                f"- **{item.get('display_name') or item.get('fact_id')}**："
                f"{_agent_drawing_status_label(item.get('status'))}；"
                f"{_agent_drawing_reason_label(item.get('reason'))}"
            )
            text_value = _value_unit(item.get("text_value"), item.get("text_unit"))
            drawing_value = _value_unit(item.get("drawing_value"), item.get("drawing_unit"))
            lines.append(f"  - 文本侧实际值：{text_value}")
            lines.append(f"  - 图纸侧实际值：{drawing_value}")
            for evidence in (item.get("text_evidence") or [])[:2]:
                lines.append(f"  - 文本证据：第{evidence.get('physical_page') or evidence.get('page') or '—'}页，{evidence.get('quote') or evidence.get('text') or '—'}")
            for evidence in (item.get("drawing_evidence") or [])[:2]:
                lines.append(f"  - 图纸证据：第{evidence.get('physical_page') or evidence.get('page') or '—'}页，{evidence.get('quote') or evidence.get('evidence_text') or evidence.get('text') or '—'}")
        lines.append("")

    # ===== 五、人工复核记录 =====
    if decisions:
        lines.extend(["---", "", "## 五、人工复核记录", ""])
        lines.append("| 事项编号 | 自动状态 | 人工决定 | 备注 |")
        lines.append("|---------|---------|---------|------|")
        for d in decisions:
            lines.append(
                f"| {d.get('item_key', d.get('rule_id', '—'))} | {d.get('automatic_status', '—')} "
                f"| {d.get('human_decision_label', d.get('human_decision', '—'))} "
                f"| {d.get('note', '') or '—'} |"
            )
        lines.append("")

    # ===== 六、输出文件清单 =====
    lines.extend([
        "---",
        "",
        "## 六、系统输出文件",
        "",
        "| 文件名 | 说明 |",
        "|--------|------|",
        "| mineru_document.json | MinerU 解析结构化文档 |",
        "| project_facts.json | 工程事实识别结果 |",
        "| project_qualification.json | 工程基础信息与审查范围 |",
        "| completeness_results.json | 完整性审查结果 |",
        "| completeness_summary.json | 完整性审查汇总 |",
        "| rule_engine_results.json | v4.0 规则引擎审查结果 |",
        "| substantive_review.json | 规范符合性审查结果 |",
        "| consistency_review.json | 参数一致性检查结果 |",
        "| drawing_review.json | 图文复核提示结果 |",
        "| review_results.json | 智能预审统一汇总 |",
        "| completeness_evidence_check.md | 证据核对报告 |",
        "| decisions.json | 人工复核记录 |",
        "",
        "---",
        "",
        "> 系统辅助审查结果仅供参考，需人工确认。数据仅保存在本机。",
    ])

    return "\n".join(lines)


def _risk_label(val: str) -> str:
    return {
        "over_scale_dangerous": "超过一定规模危大工程",
        "dangerous": "危大工程",
        "unknown": "未确定",
    }.get(val, val or "—")


def _project_type_label(val: str | None) -> str:
    return {
        "concrete_formwork_support": "混凝土模板支撑（高支模）",
    }.get(val or "", val or "—")


def _param_str(param: dict[str, Any]) -> str:
    if not param:
        return "—"
    value = param.get("value")
    unit = param.get("unit", "") or ""
    if value is None:
        return param.get("status", "—") or "—"
    return f"{value}{unit}"


def _side_str(side: dict[str, Any]) -> str:
    if not side:
        return "—"
    value = side.get("value")
    if value is None:
        return "未识别"
    return str(value)


def _value_unit(
    value: Any,
    unit: str | None,
    *,
    missing_label: str = "未提取到可比较的实际值",
) -> str:
    if value is None:
        return missing_label
    if isinstance(value, list):
        text = "/".join(str(item) for item in value)
    else:
        text = str(value)
    return f"{text}{unit or ''}"


def _format_rule_reason(reason: Any) -> str:
    if reason is None:
        return "—"
    return str(reason).replace("None", "")


def _agent_drawing_status_label(status: str | None) -> str:
    return {
        "CONSISTENT": "图文一致",
        "CONFLICT": "图文冲突",
        "TEXT_ONLY": "仅文本有证据",
        "DRAWING_ONLY": "仅图纸有证据",
        "UNCERTAIN": "暂无法确定",
        "NOT_FOUND": "未找到足够证据",
    }.get(status or "", status or "—")


def _agent_drawing_reason_label(reason: str | None) -> str:
    return {
        "values_equal": "文本与图纸同一作用范围下参数值一致",
        "values_differ": "文本与图纸同一作用范围下参数值不一致",
        "text_evidence_only": "仅找到文本侧证据",
        "drawing_evidence_only": "仅找到图纸侧证据",
        "scope_unknown": "文本与图纸的作用部位无法可靠对应",
        "scope_incompatible": "文本与图纸作用范围不一致",
        "no_evidence": "未找到足够文本或图纸证据",
        "no_candidate_pages": "未召回到可靠的图纸候选页",
        "no_usable_image": "找到相关页面，但没有可用于视觉核验的图像",
        "value_not_visible": "图中存在相关构造，但目标数值无法可靠读取",
        "constraint_not_actual_value": "图中信息为约束条件，不是实际参数取值",
    }.get(reason or "", reason or "—")


def build_review_report_from_job_dir(job_dir: Path) -> str:
    """从任务目录读取各 JSON 结果，生成审查报告。"""
    def _read(name: str) -> Any:
        p = job_dir / name
        if not p.is_file():
            return None
        try:
            return json.loads(p.read_text(encoding="utf-8"))
        except Exception:
            return None

    status = _read("status.json") or {}
    orchestrator = _read("orchestrator_agent.json") or {}
    return build_review_report(
        job_id=status.get("job_id", ""),
        file_name=status.get("file_name", ""),
        project_qualification=_read("project_qualification.json"),
        completeness_summary=_read("completeness_summary.json"),
        completeness_results=_read("completeness_results.json"),
        rule_engine_results=_read("rule_engine_results.json"),
        substantive_review=_read("substantive_review.json"),
        consistency_review=_read("consistency_review.json"),
        drawing_review=_read("drawing_review.json"),
        agent_drawing_review=orchestrator.get("agent_drawing_review"),
        decisions=_read("decisions.json") or [],
    )
