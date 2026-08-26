import json

d = json.load(open("/Users/admin/high-formwork-data/web/jobs/fa7e28e48b22420488aa215c67a30564/calculation_results.json"))
for r in d["results"]:
    if r["rule_id"] in ("3.11", "3.14"):
        rc = r.get("calculation_recheck", {})
        pages = rc.get("pages", [])
        print(f"=== {r['rule_id']} pages={pages} ===")
        for ev in r.get("evidence", []):
            print(f"  evidence p{ev.get('page')}: {ev.get('quote','')[:200]}")
