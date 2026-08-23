"""语义审查 Dify 集成测试：分批、门禁、校验、降级。"""

from __future__ import annotations

import json

import pytest

from app.dify_config import resolve_semantic_review_mode
from app.semantic_engine import load_semantic_rules
from app.services.dify_client import DifyError
from app.services.semantic_dify import (
    build_semantic_batches,
    run_semantic_review_dify,
    run_semantic_stage,
)
from tests.test_vertical_slice import _document


class _FakeDifyClient:
    """模拟 DifyClient.run_workflow，返回可控的 Workflow 响应。"""

    def __init__(self, responder=None, error: Exception | None = None):
        self.calls: list[dict] = []
        self._responder = responder
        self._error = error

    async def run_workflow(self, inputs, *, user):
        self.calls.append(dict(inputs))
        if self._error is not None:
            raise self._error
        rule_ids = [
            item["rule_id"]
            for item in json.loads(inputs["rules_json"])
        ]
        results = self._responder(rule_ids) if self._responder else [
            {
                "rule_id": rule_id,
                "status": "COMPLIANT",
                "reason": "证据充分",
                "evidence_quote": "原文引用",
                "confidence": "high",
            }
            for rule_id in rule_ids
        ]
        return {
            "data": {
                "outputs": {
                    "result_json": json.dumps(results, ensure_ascii=False)
                }
            }
        }


def _facts(system=None):
    if system is None:
        return {"facts": {}}
    return {
        "facts": {
            "support_system": {
                "value": system,
                "status": "confirmed",
                "evidence": [],
            }
        }
    }


def test_batches_split_and_carry_rule_ids():
    doc = _document("本方案由施工单位组织编制，包含工程概况与计算书。")
    rules = load_semantic_rules()[:20]
    batches = build_semantic_batches(rules, doc, batch_size=8)

    assert len(batches) == 3
    assert batches[0]["batch_count"] == 3
    flat_ids = [rid for batch in batches for rid in batch["rule_ids"]]
    assert flat_ids == [str(r["rule_id"]) for r in rules]
    evidence = json.loads(batches[0]["inputs"]["evidence_json"])
    assert [e["rule_id"] for e in evidence] == batches[0]["rule_ids"]


def test_dify_results_are_mapped_and_gate_applied():
    doc = _document("本方案由施工单位组织编制，包含工程概况。")
    client = _FakeDifyClient()

    result = run_semantic_review_dify(
        doc, _facts(None), client=client, cache_enabled=False
    )

    assert result["mode"] == "dify_llm_semantic"
    assert result["total_rules"] == len(load_semantic_rules())
    # 支撑体系未识别：体系专属规则本地记 PENDING，不进 LLM 批次
    pending = [
        r for r in result["results"] if r["status"] == "PENDING_CONFIRMATION"
    ]
    assert pending, "应存在体系专属待确认规则"
    sent_ids = {
        rid
        for call in client.calls
        for item in json.loads(call["rules_json"])
        for rid in [item["rule_id"]]
    }
    assert not {r["rule_id"] for r in pending} & sent_ids

    dify_items = [
        r for r in result["results"] if r.get("review_engine") == "dify_llm"
    ]
    assert dify_items
    assert all(item["status"] == "COMPLIANT" for item in dify_items)
    assert dify_items[0]["evidence"][0]["quote"] == "原文引用"


def test_llm_evidence_quote_located_to_block():
    """LLM 引用文本应定位回本地 block（页码/block_id），不匹配时保持 source:llm 不报错。"""
    from app.services.semantic_dify import (
        _locate_llm_quote,
        _map_llm_item,
    )

    blocks = [
        {
            "block_id": "p0003-b0003",
            "block_type": "table",
            "physical_page": 3,
            "text": "倾倒混凝土时对垂直面模板荷载标准值Q3k(kN/m2) 2",
        },
        {
            "block_id": None,
            "block_type": "section",
            "physical_page": 45,
            "text": "脚手架安全等级 I级 结构重要性系数 1",
        },
    ]
    # 逐字引用 → 精确定位
    hit = _locate_llm_quote(
        "倾倒混凝土时对垂直面模板荷载标准值Q3k(kN/m2) 2", blocks
    )
    assert hit and hit["block_id"] == "p0003-b0003"
    assert hit["physical_page"] == 3
    # 片段引用 → 定位到所在 block
    hit2 = _locate_llm_quote("结构重要性系数 1", blocks)
    assert hit2 and hit2["physical_page"] == 45
    # 无关引用 → None
    assert _locate_llm_quote("完全无关的引用文本", blocks) is None
    assert _locate_llm_quote("", blocks) is None

    # 集成：_map_llm_item 携带 evidence_blocks 时回填页码
    rules_by_id = {
        "2.17": {
            "rule_id": "2.17",
            "rule_name": "结构重要性系数γ₀",
            "module": "02_design_requirements",
            "code_ref": {"standard": "JGJ162", "original_text": "γ0≥1.1"},
            "check_logic": {},
        }
    }
    item = {
        "rule_id": "2.17",
        "status": "VIOLATED",
        "reason": "γ0 取 1，低于 1.1",
        "evidence_quote": "结构重要性系数 1",
        "confidence": "high",
    }
    mapped = _map_llm_item(item, rules_by_id, {"2.17": blocks})
    assert mapped["evidence"][0]["page"] == 45
    assert mapped["evidence"][0]["source"] == "llm"
    # 不传 blocks：行为与旧版一致（无 page 字段）
    mapped_old = _map_llm_item(item, rules_by_id)
    assert "page" not in mapped_old["evidence"][0]


def test_invalid_status_in_batch_triggers_local_fallback():
    doc = _document("本方案由施工单位组织编制。")

    def bad_responder(rule_ids):
        return [
            {
                "rule_id": rule_id,
                "status": "PASS",  # 非允许状态
                "reason": "x",
                "evidence_quote": "",
            }
            for rule_id in rule_ids
        ]

    client = _FakeDifyClient(responder=bad_responder)
    result = run_semantic_review_dify(
        doc, _facts("coupler"), client=client, cache_enabled=False
    )

    fallbacks = [
        r
        for r in result["results"]
        if r.get("review_engine") == "local_fallback"
    ]
    assert fallbacks, "非法状态批次应降级为本地结果"
    assert any(
        w["code"] == "SEMANTIC_DIFY_BATCH_FALLBACK" for w in result["warnings"]
    )


def test_connection_error_falls_back_batch_by_batch():
    doc = _document("本方案由施工单位组织编制。")
    client = _FakeDifyClient(error=DifyError("无法连接 Dify Workflow API"))

    result = run_semantic_review_dify(
        doc, _facts("coupler"), client=client, cache_enabled=False
    )

    assert result["total_rules"] == len(load_semantic_rules())
    assert all(
        r.get("review_engine") == "local_fallback"
        for r in result["results"]
        if r["status"] not in {"PENDING_CONFIRMATION", "NOT_APPLICABLE"}
    )


def test_stage_dispatch_respects_mode(monkeypatch):
    monkeypatch.setenv("SEMANTIC_REVIEW_MODE", "local")
    assert resolve_semantic_review_mode() == "local"
    monkeypatch.setenv("SEMANTIC_REVIEW_MODE", "dify")
    assert resolve_semantic_review_mode() == "dify"
    monkeypatch.setenv("SEMANTIC_REVIEW_MODE", "bogus")
    with pytest.raises(ValueError):
        resolve_semantic_review_mode()

    monkeypatch.setenv("SEMANTIC_REVIEW_MODE", "local")
    doc = _document("本方案由施工单位组织编制。")
    result = run_semantic_stage(doc, _facts(None))
    assert result["mode"] == "local_keyword_match"
