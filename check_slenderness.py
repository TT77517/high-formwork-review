import json

d = json.load(open("/Users/admin/high-formwork-data/web/jobs/fa7e28e48b22420488aa215c67a30564/calculation_results.json"))
for r in d["results"]:
    if r["rule_id"] in ("3.11", "3.14"):
        rc = r.get("calculation_recheck", {})
        print(f"=== {r['rule_id']} ===")
        print(f"  status: {rc.get('status')}")
        print(f"  computed: {rc.get('computed_value')}")
        print(f"  substituted: {rc.get('substituted_expression','')}")
        print(f"  inputs: {rc.get('inputs',[])}")
        print(f"  warnings: {rc.get('warnings',[])}")
        print(f"  pages: {rc.get('pages',[])}")
        print(f"  evidence: {r.get('evidence',[])[:2]}")
