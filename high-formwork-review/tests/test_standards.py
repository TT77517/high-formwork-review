"""规范注册表与代号归一化测试。"""

from __future__ import annotations

from app.standards import (
    applicable_standards_for,
    extract_standard_refs,
    get_standards_registry,
    normalize_standard_ref,
)


# 规则库 code_ref.standard 实测变体 → 期望 standard_id（首命中）
VARIANT_CASES = [
    ("JGJ/T 231-2021", "JGJT231-2021"),
    ("JGJ/T231-2021 第7.4.6条(≤2mm)", "JGJT231-2021"),
    ("GB50666-2011", "GB50666-2011"),
    ("GB 50666-2011 第4.1.5条", "GB50666-2011"),
    ("GB55023-2022", "GB55023-2022"),
    ("GB 55023-2022 第2.0.3条（全文强制）", "GB55023-2022"),
    ("JGJ162-2016", "JGJ162-2016"),
    ("JGJ 162-2016 第5.3节", "JGJ162-2016"),
    ("住建部37号令-第十一条", "MOHURD-ORDER-37"),
    ("住建部37号令第十一条", "MOHURD-ORDER-37"),
    ("住建部令[2018]31号", "JIANBANZHI-2018-31"),
    ("建办质〔2018〕31号-附件一第4项", "JIANBANZHI-2018-31"),
    ("建办质〔2018〕31号附件第八项", "JIANBANZHI-2018-31"),
    ("JGJ 130-2011 第6.9.2条", "JGJ130-2011"),
    ("JGJ 166-2016 第5.5条", "JGJ166-2016"),
    ("GB55001-2021", "GB55001-2021"),
    ("GB 55008-2021 第5.2.1条(全文强制)", "GB55008-2021"),
    ("GB 15831", "GB15831"),
    ("GB/T 3091", "GBT3091"),
    ("GB/T 17656", "GBT17656"),
    ("GB 50017-2017 第4.4节", "GB50017-2017"),
    ("GB 50009-2012 第3.2节", "GB50009-2012"),
    ("JGJ 300-2013 第6.2.2条", "JGJ300-2013"),
    ("JGJ 80-2016 第7.1节", "JGJ80-2016"),
    ("JGJ 59-2011", "JGJ59-2011"),
]


def test_registry_loads_all_entries():
    registry = get_standards_registry()
    assert len(registry) >= 18
    ids = {entry["standard_id"] for entry in registry}
    assert {"JGJT231-2021", "JGJ162-2016", "GB55023-2022", "MOHURD-ORDER-37"} <= ids


def test_normalize_standard_ref_maps_real_variants():
    for raw, expected in VARIANT_CASES:
        assert normalize_standard_ref(raw) == expected, raw


def test_normalize_unknown_returns_none():
    assert normalize_standard_ref("") is None
    assert normalize_standard_ref(None) is None
    assert normalize_standard_ref("不存在的规范 XYZ-9999") is None


def test_extract_standard_refs_handles_combinations():
    assert extract_standard_refs(
        "GB 50666-2011 第4.1.5条 / JGJ 162-2016 第4.2.4条"
    ) == ["GB50666-2011", "JGJ162-2016"]
    assert extract_standard_refs(
        "住建部37号令第十一条 / 建办质〔2018〕31号附件第八项 / GB50666-2011第3.1.6条"
    ) == ["MOHURD-ORDER-37", "JIANBANZHI-2018-31", "GB50666-2011"]
    assert extract_standard_refs(
        "GB 55023-2022 第4.4.5条(强制:应设置) / JGJ 130-2011 第6.3.2条(扣件式≤200mm) / "
        "JGJ/T231-2021 第6.2.5条(盘扣式≤550mm) / JGJ 162-2016 第6.1.9条"
    ) == ["GB55023-2022", "JGJ130-2011", "JGJT231-2021", "JGJ162-2016"]
    # 单规范串只返回一个
    assert extract_standard_refs("JGJ/T231-2021 第5.3.1条") == ["JGJT231-2021"]


def test_applicable_standards_for_support_systems():
    disk = [s["standard_id"] for s in applicable_standards_for("disk_lock")]
    assert "JGJT231-2021" in disk and "JGJ162-2016" in disk
    assert "JGJ130-2011" not in disk

    coupler = [s["standard_id"] for s in applicable_standards_for("coupler")]
    assert "JGJ130-2011" in coupler and "GB15831" in coupler
    assert "JGJT231-2021" not in coupler

    unknown = applicable_standards_for("unknown")
    assert unknown and all(s.get("note") for s in unknown)
    assert "JGJT231-2021" not in [s["standard_id"] for s in unknown]
    assert applicable_standards_for(None) == unknown
