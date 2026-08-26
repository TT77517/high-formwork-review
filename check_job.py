import json, sys

JOB = sys.argv[1]
BASE = "/Users/admin/high-formwork-data/web/jobs"

d = json.load(open(f"{BASE}/{JOB}/calculation_results.json"))
print("=== Calculation recheck ===")
for r in d["results"]:
    rc = r.get("calculation_recheck")
    if rc:
        print(f"  {r['rule_id']}: recheck={rc['status']}, computed={rc.get('computed_value')}, expr={rc.get('substituted_expression','')[:80]}")
    else:
        print(f"  {r['rule_id']}: status={r['status']} (no recheck)")

print("\n=== Drawing review evidence quality ===")
dr = json.load(open(f"{BASE}/{JOB}/drawing_review.json"))
for item in dr:
    eq = item.get("evidence_quality", {})
    exp = item.get("review_explanation", {})
    print(f"  {item.get('review_item_id')}: status={item.get('status')}, quality={eq.get('label','N/A')}, level={eq.get('level','N/A')}")

print("\n=== Orchestrator ===")
orch = json.load(open(f"{BASE}/{JOB}/orchestrator_agent.json"))
print(f"  formula_recalculations: {len(orch.get('formula_recalculations', []))}")
for fr in orch.get("formula_recalculations", []):
    print(f"    {fr.get('rule_id')}: {fr.get('recalculated_status')}, computed={fr.get('computed_value')}")
print(f"  drawing_evidence_quality: {orch.get('drawing_evidence_quality', {}).get('counts', 'N/A')}")
print(f"  parameter_to_rules keys: {list(orch.get('parameter_to_rules', {}).keys())[:10]}")
print(f"  uncertainty total: {orch.get('uncertainty_analysis', {}).get('total_uncertain', 'N/A')}")
cats = {c["category"]: c["count"] for c in orch.get("uncertainty_analysis", {}).get("categories", [])}
print(f"  uncertainty categories: {cats}")
