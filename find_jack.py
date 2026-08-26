import json

d = json.load(open("/Users/admin/high-formwork-data/web/jobs/371dc228db6a467f88909b64bf275f52/mineru_document.json"))
for page in d["pages"]:
    if page["physical_page"] in (87, 90):
        for block in page.get("blocks", []):
            text = block.get("text") or ""
            if any(kw in text for kw in ("托撑", "顶托", "承载力", "N≤", "N<=", "可调")):
                print(f"--- p{page['physical_page']} {block.get('block_type')} {block.get('block_id')} ---")
                print(text[:400])
                print()
