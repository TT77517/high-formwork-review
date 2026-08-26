import json

d = json.load(open("/Users/admin/high-formwork-data/web/jobs/fa7e28e48b22420488aa215c67a30564/mineru_document.json"))
calc_keywords = ["长细比", "λ", "slenderness", "l0/i", "计算长度", "回转半径"]
found = []
for page in d["pages"]:
    for block in page.get("blocks", []):
        text = block.get("text") or ""
        if any(kw in text for kw in calc_keywords):
            found.append({
                "page": page["physical_page"],
                "block_id": block.get("block_id"),
                "block_type": block.get("block_type"),
                "text": text[:300],
            })

print(f"Found {len(found)} blocks with slenderness keywords:")
for item in found[:15]:
    print(f"\n--- p{item['page']} {item['block_type']} {item['block_id']} ---")
    print(item["text"][:300])
