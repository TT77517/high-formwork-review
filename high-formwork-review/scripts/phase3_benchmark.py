"""Phase 3 Benchmark：批式 vs Agent 双模式对比（V3.1 §8 Phase 3 / §7）。

从批式基线（job 2d6b084f，Dify LLM）挑选疑难规则跑 Evidence Agent，
统计 Recovery Rate / Citation Validity / 平均 tool calls / 耗时，
输出 markdown 对比表（比赛 PPT 数据页素材）。

用法：
    cd high-formwork-review
    .venv/bin/python scripts/phase3_benchmark.py [job_dir] [rule_id ...]
"""

from __future__ import annotations

import json
import shutil
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from app.mineru_cache import document_from_dict  # noqa: E402
from app.semantic_engine import load_semantic_rules  # noqa: E402
from app.services import semantic_agent  # noqa: E402
from app.services.llm_chat_client import LLMChatClient  # noqa: E402

DEFAULT_JOB_DIR = Path(
    "/Users/admin/high-formwork-data/web/jobs/2d6b084fbe1046858e89208cb8dd32fd"
)
# 批式 UNCERTAIN 疑难规则（含跨章节查证/计算书取值/管理类证据缺失）+ 5.1 阳性对照
DEFAULT_RULES = ["1.10", "1.12", "1.17", "1.18", "2.1", "2.5", "2.7", "2.11", "2.20", "5.1"]


def main() -> int:
    job_dir = Path(sys.argv[1]) if len(sys.argv) > 1 else DEFAULT_JOB_DIR
    rule_ids = sys.argv[2:] or DEFAULT_RULES
    document = document_from_dict(
        json.loads((job_dir / "mineru_document.json").read_text(encoding="utf-8"))
    )
    rules = {str(r.get("rule_id")): r for r in load_semantic_rules()}
    baseline = {
        str(r["rule_id"]): r["status"]
        for r in json.loads(
            (job_dir / "semantic_results.json").read_text(encoding="utf-8")
        )["results"]
    }
    baseline_reason = {
        str(r["rule_id"]): r.get("reason", "")
        for r in json.loads(
            (job_dir / "semantic_results.json").read_text(encoding="utf-8")
        )["results"]
    }

    client = LLMChatClient.from_env()
    print(f"模型链：{client.model_identifier}")
    print(f"基线：{job_dir.name}（Dify 批式）\n")

    rows = []
    started = time.perf_counter()
    for rid in rule_ids:
        rule = rules.get(rid)
        if not rule:
            print(f"[{rid}] 规则不存在，跳过")
            continue
        t0 = time.perf_counter()
        try:
            result = semantic_agent.run_evidence_agent(
                rule, document, client=client, cache_enabled=True
            )
        except Exception as exc:  # noqa: BLE001 - 单规则失败记录后继续
            rows.append({
                "rule_id": rid, "rule_name": rule.get("rule_name", ""),
                "baseline": baseline.get(rid, "?"), "agent": "ERROR",
                "reason": str(exc)[:100], "confidence": None,
                "tool_calls": 0, "llm_calls": 0, "latency_ms": 0,
                "evidence_count": 0, "steps": [], "forced": False, "cache_hit": False,
            })
            print(f"[{rid}] ERROR: {exc}")
            continue
        a = result["agent"]
        rows.append({
            "rule_id": rid,
            "rule_name": result["rule_name"],
            "baseline": baseline.get(rid, "?"),
            "agent": result["status"],
            "reason": result["reason"],
            "confidence": result.get("confidence"),
            "tool_calls": a["tool_calls"],
            "llm_calls": a["llm_calls"],
            "latency_ms": a["latency_ms"],
            "evidence_count": len(result["evidence"]),
            "steps": [
                {"action": s["action"], "args": s["args"]} for s in a["steps"]
            ],
            "forced": a["forced_finish"],
            "cache_hit": a["cache_hit"],
        })
        flag = "（缓存命中）" if a["cache_hit"] else ""
        print(
            f"[{rid}] {result['rule_name'][:18]} "
            f"{baseline.get(rid, '?')} -> {result['status']} "
            f"conf={result.get('confidence')} "
            f"tools={a['tool_calls']} llm={a['llm_calls']} "
            f"{a['latency_ms']}ms ev={len(result['evidence'])}{flag}"
        )
    total_seconds = time.perf_counter() - started

    # ---------------- 统计 ----------------
    baseline_uncertain = [r for r in rows if r["baseline"] == "UNCERTAIN"]
    recovered = [
        r for r in baseline_uncertain if r["agent"] in ("COMPLIANT", "VIOLATED")
    ]
    citation_valid = [r for r in rows if r["agent"] != "ERROR" and (
        r["agent"] != "VIOLATED" or r["evidence_count"] > 0
    )]
    avg_tools = (
        sum(r["tool_calls"] for r in rows if not r["cache_hit"]) /
        max(1, len([r for r in rows if not r["cache_hit"]]))
    )
    avg_latency = (
        sum(r["latency_ms"] for r in rows if not r["cache_hit"]) /
        max(1, len([r for r in rows if not r["cache_hit"]]))
    )

    summary = {
        "job": job_dir.name,
        "model_chain": client.model_identifier,
        "total_rules": len(rows),
        "baseline_uncertain": len(baseline_uncertain),
        "recovered": len(recovered),
        "recovery_rate": (
            f"{len(recovered)}/{len(baseline_uncertain)}"
            f"（{len(recovered) / len(baseline_uncertain) * 100:.0f}%）"
            if baseline_uncertain else "N/A"
        ),
        "citation_validity": (
            f"{len(citation_valid)}/{len(rows)}"
            f"（{len(citation_valid) / len(rows) * 100:.0f}%）"
        ),
        "avg_tool_calls": round(avg_tools, 1),
        "avg_latency_s": round(avg_latency / 1000, 1),
        "forced_finish_count": sum(1 for r in rows if r["forced"]),
        "total_wall_seconds": round(total_seconds, 1),
    }

    print("\n===== 汇总 =====")
    for key, value in summary.items():
        print(f"{key}: {value}")

    out = {
        "summary": summary,
        "rows": rows,
    }
    out_path = ROOT / "docs" / "phase3_benchmark_data.json"
    out_path.write_text(
        json.dumps(out, ensure_ascii=False, indent=2), encoding="utf-8"
    )
    print(f"\n明细已写入：{out_path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
