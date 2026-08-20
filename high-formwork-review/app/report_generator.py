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
        f"- **工程类型：** {q.get('project_type', '—')}",
        f"- **风险属性：** {_risk_label(q.get('risk_classification', ''))}",
        f"- **支撑体系：** {q.get('support_system_label', q.get('support_system', '—'))}",
        f"- **支撑高度：** {_param_str(params.get('support_height', {}))}",
        f"- **跨度：** {_param_str(params.get('support_span', {}))}",
        f"- **总荷载：** {_param_str(params.get('total_load_design', {}))}",
        f"- **线荷载：** {_param_str(params.get('concentrated_line_load_design', {}))}",
        f"- **适用规则包：** {'、'.join(q.get('applicable_rule_packs', [])) or '—'}",
        "",
    ])
    conditions = q.get("triggered_conditions", [])
    if conditions:
        lines.append("**触发条件：**")
        for c in conditions:
            lines.append(f"- {c.get('name', '')}：{c.get('condition', '')}")
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
    re_uncertain = re.get("uncertain", 0) + re.get("not_applicable", 0)
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
    dr_total = len(dr)
    dr_review = sum(1 for i in dr if i.get("requires_human_review"))
    lines.append(f"| 图文复核提示 | {dr_total} | — | — | {dr_review} |")

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
            lines.append(f"**{r.get('rule_id')} {r.get('rule_name')}**")
            lines.append(f"- 风险等级：{r.get('risk_level', '—')}")
            lines.append(f"- 实际值：{r.get('actual_value', '—')}{th.get('unit', '')}")
            lines.append(f"- 阈值要求：{th.get('operator', '')} {th.get('value', '')}{th.get('unit', '')}")
            lines.append(f"- 判定依据：{r.get('reason', '—')}")
            code = r.get("code_ref", {})
            if code.get("standard"):
                lines.append(f"- 规范依据：{code['standard']}")
            if r.get("remedy_suggestion"):
                lines.append(f"- 整改建议：{r['remedy_suggestion']}")
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

    # ===== 五、人工复核记录 =====
    if decisions:
        lines.extend(["---", "", "## 五、人工复核记录", ""])
        lines.append("| 规则编号 | 自动状态 | 人工决定 | 备注 |")
        lines.append("|---------|---------|---------|------|")
        for d in decisions:
            lines.append(
                f"| {d.get('rule_id', '—')} | {d.get('automatic_status', '—')} "
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
        decisions=_read("decisions.json") or [],
    )
