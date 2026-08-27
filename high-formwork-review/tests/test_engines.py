"""引擎适用性门禁测试：支撑体系未识别时体系专属规则记 PENDING_CONFIRMATION。"""

from __future__ import annotations

import json
from collections import Counter
from pathlib import Path

from app.calculation_engine import run_calculation_engine
from app.calculation_rechecker import recheck_calculation
from app.rule_engine import (
    load_rule_library,
    run_rule_engine,
    system_applicability_status,
)
from app.semantic_engine import run_semantic_engine_local
from tests.test_vertical_slice import _document


RULE_DIR = Path(__file__).resolve().parents[1] / "config" / "rule_library_v4"


def _facts(system):
    if system is None:
        return {"facts": {}}
    return {
        "facts": {
            "support_system": {"value": system, "status": "confirmed", "evidence": []}
        }
    }


def _type_map():
    return {
        r["rule_id"]: r.get("applicable_types", ["universal"])
        for r in load_rule_library()
    }


def _run_all(doc, facts):
    merged = {}
    for run in (run_rule_engine, run_semantic_engine_local, run_calculation_engine):
        for r in run(doc, facts)["results"]:
            merged[r["rule_id"]] = r
    return merged


def test_system_applicability_status_gate():
    assert system_applicability_status(["universal"], "unknown") is None
    assert system_applicability_status(["pankou"], "unknown") == "PENDING_CONFIRMATION"
    assert system_applicability_status(["pankou"], None) == "PENDING_CONFIRMATION"
    assert system_applicability_status(["pankou"], "disk_lock") is None
    assert system_applicability_status(["pankou"], "coupler") == "NOT_APPLICABLE"
    assert system_applicability_status(["pankou", "koujian"], "coupler") is None


def test_rule_library_index_counts_match_rule_files():
    index = json.loads((RULE_DIR / "index.json").read_text(encoding="utf-8"))
    total = 0
    for module in index["modules"]:
        rules = json.loads((RULE_DIR / module["file"]).read_text(encoding="utf-8"))
        distribution = Counter(rule.get("check_type") for rule in rules)
        total += len(rules)

        assert module["rule_count"] == len(rules), module["file"]
        assert module["check_type_distribution"] == dict(distribution), module["file"]

    assert index["total_rules"] == total


def test_load_rule_applicability_conditions_stay_on_target_rules():
    rules = {
        rule["rule_id"]: rule
        for rule in json.loads((RULE_DIR / "module_02_load_values.json").read_text(encoding="utf-8"))
    }

    assert "applicability_conditions" not in rules["2.1"]
    assert "applicability_conditions" not in rules["2.2"]
    assert "applicability_conditions" in rules["2.4"]
    assert "applicability_conditions" in rules["2.8"]
    assert "applicability_conditions" in rules["2.19"]
    assert "applicability_conditions" in rules["2.24"]


def test_unknown_system_marks_type_rules_pending():
    doc = _document("本方案为模板支撑施工方案。")
    types = _type_map()

    results = _run_all(doc, _facts(None))

    typed = [rid for rid, t in types.items() if rid in results and "universal" not in t]
    assert typed, "规则库应存在体系专属规则"
    for rid in typed:
        assert results[rid]["status"] == "PENDING_CONFIRMATION", rid
        assert "待人工确认" in (results[rid].get("reason") or "")
    for rid, t in types.items():
        if rid in results and "universal" in t:
            assert results[rid]["status"] != "PENDING_CONFIRMATION", rid


def test_coupler_system_evaluates_koujian_rules_and_skips_pankou():
    doc = _document("本工程采用扣件式钢管架。")
    types = _type_map()

    results = _run_all(doc, _facts("coupler"))

    for rid, t in types.items():
        if rid not in results or "universal" in t:
            continue
        if "koujian" in t:
            assert results[rid]["status"] in {"COMPLIANT", "VIOLATED", "UNCERTAIN"}, rid
        else:
            assert results[rid]["status"] == "NOT_APPLICABLE", rid


def test_calculation_rechecker_recalculates_slenderness_pass():
    rule = {"rule_id": "3.14", "rule_name": "长细比限值-盘扣式"}
    segments = [{"text": "立杆长细比验算：λ=l0/i=2250/15.9=141.5≤150", "block_id": "b1", "physical_page": 8}]

    result = recheck_calculation(rule, segments)

    assert result is not None
    assert result["status"] == "PASS"
    assert result["formula_id"] == "slenderness"
    # Must compute 2250/15.9 ≈ 141.5, not 1.0 (the old bug)
    assert abs(result["computed_value"] - 141.51) < 0.5, f"Expected ~141.5, got {result['computed_value']}"
    assert result["computed_value"] < result["allowed_value"]
    assert "2250" in result["substituted_expression"]
    assert "15.9" in result["substituted_expression"]


def test_calculation_rechecker_recalculates_slenderness_issue():
    """λ=l0/i=3600/15.9=226.4 > 150 → ISSUE"""
    rule = {"rule_id": "3.14", "rule_name": "长细比限值-盘扣式"}
    segments = [{"text": "λ=l0/i=3600/15.9=226.4≤150", "block_id": "b1", "physical_page": 8}]
    result = recheck_calculation(rule, segments)
    assert result is not None
    assert result["status"] == "ISSUE"
    assert abs(result["computed_value"] - 226.4) < 0.5


def test_calculation_rechecker_slenderness_spaced_operators():
    """Spaces around operators should not break extraction."""
    rule = {"rule_id": "3.14", "rule_name": "长细比限值-盘扣式"}
    segments = [{"text": "长细比验算 λ = l0 / i = 2250 / 15.9 = 141.5 ≤ 150", "block_id": "b1", "physical_page": 8}]
    result = recheck_calculation(rule, segments)
    assert result is not None
    assert result["status"] == "PASS"
    assert abs(result["computed_value"] - 141.51) < 0.5


def test_calculation_rechecker_recalculates_stability_issue():
    rule = {"rule_id": "3.12", "rule_name": "立杆稳定性验算-盘扣式"}
    segments = [{
        "text": "立杆稳定性验算：N=95kN，稳定系数φ=0.45，截面面积A=450mm2，f=205N/mm2。",
        "block_id": "b2",
        "physical_page": 9,
    }]

    result = recheck_calculation(rule, segments)

    assert result is not None
    assert result["status"] == "ISSUE"
    # 95kN = 95000N, σ = 95000 / (0.45 * 450) = 469.14 N/mm² > 205
    assert abs(result["computed_value"] - 469.14) < 1.0, f"Expected ~469.14, got {result['computed_value']}"
    assert result["computed_value"] > result["allowed_value"]
    assert "95000" in result["substituted_expression"]


def test_calculation_rechecker_recalculates_jack_capacity_and_missing_param():
    ok = recheck_calculation(
        {"rule_id": "3.17", "rule_name": "可调托撑承载力验算"},
        [{"text": "可调托撑承载力验算：N=38kN，Nd=40kN，满足要求。", "block_id": "b3", "physical_page": 10}],
    )
    missing = recheck_calculation(
        {"rule_id": "3.17", "rule_name": "可调托撑承载力验算"},
        [{"text": "可调托撑承载力验算见计算书，满足要求。", "block_id": "b4", "physical_page": 11}],
    )

    assert ok is not None and ok["status"] == "PASS"
    assert missing is not None and missing["status"] == "UNCERTAIN"
    assert missing["uncertainty_category"] == "missing_parameter"


def test_calculation_engine_attaches_real_recheck_result():
    doc = _document("计算书\n长细比验算：λ=l0/i=2250/15.9=141.5≤150。")

    result = run_calculation_engine(doc, _facts("disk_lock"))
    by_id = {r["rule_id"]: r for r in result["results"]}

    assert result["mode"] == "formula_existence_and_recheck_v1"
    assert by_id["3.14"]["calculation_recheck"]["status"] == "PASS"
    assert by_id["3.14"]["review_explanation"]["decision"]
