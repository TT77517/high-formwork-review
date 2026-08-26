import json

d = json.load(open("/Users/admin/high-formwork-data/web/jobs/371dc228db6a467f88909b64bf275f52/calculation_results.json"))
for r in d["results"]:
    if r["rule_id"] == "3.17":
        rc = r.get("calculation_recheck", {})
        print("=== 3.17 ===")
        print("status:", rc.get("status"))
        print("warnings:", rc.get("warnings"))
        print("pages:", rc.get("pages"))
        for ev in r.get("evidence", []):
            print(f"  evidence p{ev.get('page')}: {ev.get('quote','')[:200]}")
