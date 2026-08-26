import json
from app.calculation_rechecker import _focused_segments, _join_text

d = json.load(open("/Users/admin/high-formwork-data/web/jobs/371dc228db6a467f88909b64bf275f52/mineru_document.json"))
# Reproduce the calculation segments extraction
calc_keywords = ["计算", "验算", "荷载组合", "长细比", "稳定", "抗弯", "抗剪", "挠度", "侧压力", "轴力", "倾覆", "承载力"]
import unicodedata
segments = []
in_calc = False
for page in d["pages"]:
    if page.get("parse_status") == "unreadable":
        continue
    for block in page.get("blocks", []):
        text = block.get("text") or ""
        if not text.strip():
            continue
        norm = unicodedata.normalize("NFKC", text)
        if block.get("block_type") == "title":
            in_calc = any(kw in norm for kw in calc_keywords)
        if in_calc:
            segments.append({"text": text, "block_id": block.get("block_id"), "block_type": block.get("block_type"), "physical_page": page["physical_page"]})

# Find jack-related segments
focused = _focused_segments(segments, ("托撑", "顶托", "承载力", "Nd", "N≤", "N<=", "托座"))
print(f"Focused segments: {len(focused)}")
for seg in focused:
    print(f"\n--- p{seg['physical_page']} {seg['block_type']} ---")
    print(seg["text"][:300])
