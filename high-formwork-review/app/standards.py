"""规范注册表与规范代号归一化。

config/standards.json 为唯一规范词汇来源：工程基础信息的"适用规范"、
规则库管理的规范筛选、规则 standard_id 标注共用同一注册表，保证两侧同步。
"""

from __future__ import annotations

import json
import re
import unicodedata
from functools import lru_cache
from pathlib import Path
from typing import Any

CONFIG_PATH = Path(__file__).resolve().parents[1] / "config" / "standards.json"

# 支撑体系识别值 → 注册表 applies_to 体系码
_SYSTEM_CODES = {
    "disk_lock": {"universal", "pankou"},
    "coupler": {"universal", "koujian"},
    "other": {"universal", "wankou"},
}

# 注册表 full_code 之外的实测变体别名（疑似误写等，待人工清洗）
_EXTRA_ALIASES = {
    "JIANBANZHI-2018-31": ["住建部令[2018]31号"],
}


@lru_cache(maxsize=1)
def get_standards_registry() -> list[dict[str, Any]]:
    data = json.loads(CONFIG_PATH.read_text(encoding="utf-8"))
    return data.get("standards", [])


def _normalize_text(raw: str) -> str:
    """NFKC + 去空格/斜杠 + 大写，使 'JGJ 162'/'JGJ162'/'JGJ/T231' 等可比对。"""
    return unicodedata.normalize("NFKC", raw).upper().replace(" ", "").replace("/", "")


@lru_cache(maxsize=1)
def _alias_table() -> list[tuple[str, str]]:
    """(归一化别名, standard_id) 列表，按别名长度降序（最长前缀优先）。"""
    aliases: list[tuple[str, str]] = []
    for entry in get_standards_registry():
        standard_id = str(entry["standard_id"])
        base = re.sub(r"-\d{4}$", "", _normalize_text(str(entry["full_code"])))
        aliases.append((base, standard_id))
        for extra in _EXTRA_ALIASES.get(standard_id, []):
            aliases.append((_normalize_text(extra), standard_id))
    aliases.sort(key=lambda item: len(item[0]), reverse=True)
    return aliases


def extract_standard_refs(raw: str | None) -> list[str]:
    """从规范来源串中按出现顺序提取全部 standard_id（支持 'A / B' 组合串）。"""
    if not raw:
        return []
    normalized = _normalize_text(raw)
    hits = []
    for alias, standard_id in _alias_table():
        pos = normalized.find(alias)
        if pos >= 0:
            hits.append((pos, standard_id))
    hits.sort(key=lambda item: item[0])
    seen: set[str] = set()
    ordered: list[str] = []
    for _, standard_id in hits:
        if standard_id not in seen:
            seen.add(standard_id)
            ordered.append(standard_id)
    return ordered


def normalize_standard_ref(raw: str | None) -> str | None:
    """返回规范来源串的首个 standard_id，未命中返回 None。"""
    refs = extract_standard_refs(raw)
    return refs[0] if refs else None


def applicable_standards_for(support_system: str | None) -> list[dict[str, Any]]:
    """按支撑体系派生适用规范列表；未识别时仅列通用规范并附 note。"""
    codes = _SYSTEM_CODES.get(str(support_system or ""))
    note = ""
    if codes is None:
        codes = {"universal"}
        note = "支撑体系未识别，仅列出通用规范"
    result = []
    for entry in get_standards_registry():
        if set(entry.get("applies_to", ["universal"])) & codes:
            item = {
                "standard_id": entry["standard_id"],
                "name": entry["name"],
                "full_code": entry["full_code"],
                "category": entry.get("category", ""),
            }
            if note:
                item["note"] = note
            result.append(item)
    return result


def standard_label(standard_id: str | None) -> str:
    for entry in get_standards_registry():
        if entry["standard_id"] == standard_id:
            return str(entry["full_code"])
    return str(standard_id or "")
