import json

d = json.load(open("/Users/admin/high-formwork-data/web/jobs/1e0c25c0fd2c491cace87c6b09e71b43/calculation_results.json"))
for r in d["results"]:
    if r["rule_id"] == "3.17":
        rc = r.get("calculation_recheck", {})
        print("=== 3.17 ===")
        print("status:", rc.get("status"))
        print("warnings:", rc.get("warnings"))
        print("pages:", rc.get("pages"))
        print("inputs:", rc.get("inputs"))
        for ev in r.get("evidence", []):
            print(f"  ev p{ev.get('page')}: {ev.get('quote','')[:150]}")
