import json, sys
from app.calculation_rechecker import _focused_segments, _join_text, _norm, _compact_formula, _parse_near_comparison, _find_explicit_value, _find_table_value
import unicodedata

d = json.load(open("/Users/admin/high-formwork-data/web/jobs/c28ce02e913c4d00b4750fb7fa805573/mineru_document.json"))
calc_keywords = ["计算", "验算", "荷载组合", "长细比", "稳定", "抗弯", "抗剪", "挠度", "侧压力", "轴力", "倾覆", "承载力"]
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

focused = _focused_segments(segments, ("托撑", "顶托", "承载力", "Nd", "N≤", "N<=", "托座"))
print(f"Focused: {len(focused)} segments")
for seg in focused:
    print(f"\n--- p{seg['physical_page']} {seg.get('block_type')} ---")
    print(repr(seg["text"][:200]))

text = _join_text(focused)
print("\n=== joined text ===")
print(repr(text[:500]))

ctext = _compact_formula(text)
print("\n=== compacted ===")
print(repr(ctext[:500]))

near = _parse_near_comparison(ctext)
print("\nnear_comparison:", near)

n = _find_explicit_value(text, (r"\bN\b","轴力","受力"))
print("N explicit:", n)

limit = _find_explicit_value(text, (r"Nd","承载力设计值","允许承载力","容许承载力"))
print("limit explicit:", limit)
limit2 = _find_table_value(text, ("承载力容许值","承载力设计值","容许承载力"))
print("limit table:", limit2)
