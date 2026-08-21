"""引擎适用性门禁测试：支撑体系未识别时体系专属规则记 PENDING_CONFIRMATION。"""

from __future__ import annotations

from app.calculation_engine import run_calculation_engine
from app.rule_engine import (
    load_rule_library,
    run_rule_engine,
    system_applicability_status,
)
from app.semantic_engine import run_semantic_engine_local
from tests.test_vertical_slice import _document


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
