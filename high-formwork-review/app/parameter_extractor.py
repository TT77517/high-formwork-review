"""从候选证据中抽取 ProjectFacts 参数候选值。"""

from __future__ import annotations

import re
import unicodedata
from html.parser import HTMLParser
from typing import Any

from .completeness_review import _find_terms
from .evidence_retriever import ParameterEvidence
from .text_utils import norm as _norm_shared, normalize_symbol_text


_VALUE_PATTERN = re.compile(r"(?P<value>\d+(?:\.\d+)?)(?!\s*[～~至到])\s*(?P<unit>kN/m2|kN/m²|kN/㎡|kN/m3|kN/m³|kN/立方米|kN/m|kN/米|kPa|mm|cm|m|毫米|厘米|米)?", re.I)
_RANGE_PATTERN = re.compile(r"\d+(?:\.\d+)?\s*(?:mm|cm|m|毫米|厘米|米)?\s*[～~至到]\s*\d+(?:\.\d+)?")
_DISK_LOCK_TERMS = ("承插型盘扣式钢管支架", "承插型盘扣式支撑架", "盘扣式支撑架", "盘扣式模板支架", "盘扣架", "盘扣式钢管架", "盘扣式")
_AREA_PATTERN = re.compile(r"(?P<scope>[A-Za-z0-9一二三四五六七八九十东西南北]+区|梁区|板区|[一二三四五六七八九十]+层|地下室|地上部分)")

# 荷载类参数的单位护栏：窗口内优先取单位兼容的数值，避免把"间距800mm"
# 当总荷载、把系数"1"当线荷载；长度类参数各长度单位可互转，不设限
_LOAD_UNIT_COMPAT = {
    "kN/m2": {"kn/m2", "kn/m²", "kn/㎡", "kpa"},
    "kN/m": {"kn/m", "kn/米"},
}


def _pick_compatible_match(text: str, parameter_definition: dict[str, Any], *, strict: bool = False) -> Any:
    """窗口内取第一个单位与参数兼容的数值；无兼容单位时退回首个数值。

    ``strict=True``（正文抽取）时荷载类参数找不到兼容单位数值即返回 None，
    避免把公式里的间距/系数当荷载；表格抽取保留兜底（表头单位由继承机制处理）。
    """
    canonical = str(parameter_definition.get("canonical_unit") or "")
    allowed = _LOAD_UNIT_COMPAT.get(canonical)
    first = None
    for match in _VALUE_PATTERN.finditer(text):
        if first is None:
            first = match
        if allowed is None:
            return match
        if (match.group("unit") or "").lower() in allowed:
            return match
    if strict and allowed is not None:
        return None
    return first


def extract_parameter_candidates(
    evidence_items: list[ParameterEvidence],
    parameter_definition: dict[str, Any],
) -> list[dict[str, Any]]:
    if parameter_definition.get("extraction_mode") == "categorical_semantic":
        return _extract_support_system(evidence_items, parameter_definition)
    if parameter_definition.get("extraction_mode") == "load_item_set":
        return _extract_load_item_set(evidence_items, parameter_definition)
    if parameter_definition.get("extraction_mode") == "standard_step_interval":
        return _extract_standard_step_interval(evidence_items, parameter_definition)
    if parameter_definition.get("extraction_mode") == "symbolic_numeric":
        return _extract_symbolic_numeric(evidence_items, parameter_definition)
    candidates: list[dict[str, Any]] = []
    for item in evidence_items:
        if item.is_toc:
            continue
        if item.block.block_type in {"table", "table_continuation"}:
            table_candidates = _extract_from_table(item, parameter_definition)
            candidates.extend(table_candidates)
            if table_candidates:
                continue
        candidates.extend(_extract_from_text(item, parameter_definition))
    return _dedupe_candidates(candidates)


def _extract_standard_step_interval(
    evidence_items: list[ParameterEvidence],
    parameter_definition: dict[str, Any],
) -> list[dict[str, Any]]:
    candidates: list[dict[str, Any]] = []
    pattern = re.compile(
        r"(?:每间隔|间隔)\s*(?P<minimum>\d+(?:\.\d+)?)\s*(?:个)?\s*[~～\\-至到]\s*"
        r"(?P<maximum>\d+(?:\.\d+)?)\s*(?:个)?\s*标准?步距"
    )
    for item in evidence_items:
        if item.is_toc:
            continue
        text = item.block.text
        if "水平剪刀撑" not in text or "步距" not in text:
            continue
        match = pattern.search(text)
        if not match:
            continue
        minimum = float(match.group("minimum"))
        maximum = float(match.group("maximum"))
        if minimum > maximum:
            minimum, maximum = maximum, minimum
        candidates.append(
            _candidate(
                item,
                parameter_definition,
                {
                    "minimum": minimum,
                    "maximum": maximum,
                },
                raw_value=match.group(0),
                raw_unit="standard_step",
                confidence=0.92 if item.block.block_type in {"table", "table_continuation"} else 0.88,
                scope_hint=_scope_hint(text),
            )
        )
    return _dedupe_candidates(candidates)


def _extract_load_item_set(
    evidence_items: list[ParameterEvidence],
    parameter_definition: dict[str, Any],
) -> list[dict[str, Any]]:
    candidates: list[dict[str, Any]] = []
    for item in evidence_items:
        if item.is_toc:
            continue
        rows = (
            _table_rows(item.block.table_html or item.block.text)
            if item.block.block_type in {"table", "table_continuation"}
            else [[item.block.text]]
        )
        for row in rows:
            row_text = " ".join(cell for cell in row if cell).strip()
            if not row_text or _looks_like_normative_load_text(row_text):
                continue
            for load_item in parameter_definition.get("load_items", []):
                matched_alias = _matched_load_alias(row_text, load_item)
                if not matched_alias:
                    continue
                candidates.append(
                    _candidate(
                        item,
                        parameter_definition,
                        str(load_item["id"]),
                        raw_value=matched_alias,
                        confidence=0.94 if item.block.block_type in {"table", "table_continuation"} else 0.84,
                        scope_hint=_scope_hint(row_text),
                    )
                )
    return _dedupe_candidates(candidates)


def _extract_support_system(
    evidence_items: list[ParameterEvidence],
    parameter_definition: dict[str, Any],
) -> list[dict[str, Any]]:
    candidates = []
    for item in evidence_items:
        if item.is_toc:
            continue
        text = item.block.text
        if any(term in text for term in _DISK_LOCK_TERMS) and "脚手架" not in text.replace("盘扣式脚手架", ""):
            candidates.append(_candidate(item, parameter_definition, "disk_lock", raw_value="disk_lock", confidence=0.94))
        elif any(term in text for term in _DISK_LOCK_TERMS):
            candidates.append(_candidate(item, parameter_definition, "disk_lock", raw_value="disk_lock", confidence=0.90))
    return _dedupe_candidates(candidates)


def _extract_symbolic_numeric(
    evidence_items: list[ParameterEvidence],
    parameter_definition: dict[str, Any],
) -> list[dict[str, Any]]:
    """抽取带数学符号标签的数值（γc=24、t0=4、β1=1.2、坍落度=180、fa=120）。

    设计要点：
    * 符号标签可能含希腊字母/LaTeX 残片（γ/β/Φ），通用别名窗口无法稳定匹配
    * 数值必须满足 plausible_min/plausible_max 范围（防止误抓系数 1.0 或大段位号）
    * 优先取表/计算书来源（calculation > parameter_table > body）
    """
    candidates: list[dict[str, Any]] = []
    symbol_labels = [str(label) for label in parameter_definition.get("symbol_labels", [])]
    if not symbol_labels:
        return candidates
    plausible_min = parameter_definition.get("plausible_min")
    plausible_max = parameter_definition.get("plausible_max")
    canonical_unit = parameter_definition.get("canonical_unit") or ""

    for item in evidence_items:
        if item.is_toc:
            continue
        text = _normalize_symbol_text(item.block.text)
        if not text:
            continue
        if not _symbol_context_allowed(text, parameter_definition):
            continue
        for label in symbol_labels:
            clean_label = label.replace(r"\b", "")
            value = _find_symbol_value(text, clean_label, canonical_unit)
            if value is None:
                continue
            if plausible_min is not None and value < plausible_min:
                continue
            if plausible_max is not None and value > plausible_max:
                continue
            candidates.append(
                _candidate(
                    item,
                    parameter_definition,
                    value,
                    raw_value=f"{clean_label}={value:g}",
                    raw_unit=canonical_unit,
                    confidence=0.92 if item.block.block_type in {"table", "table_continuation"} else 0.84,
                    scope_hint=_scope_hint(text),
                )
            )
            break  # one candidate per evidence item
    return _dedupe_candidates(candidates)


def _normalize_symbol_text(text: str) -> str:
    return normalize_symbol_text(text)


def _symbol_context_allowed(text: str, parameter_definition: dict[str, Any]) -> bool:
    for term in parameter_definition.get("exclude_terms", []):
        if str(term) in text:
            return False
    include_terms = [str(term) for term in parameter_definition.get("include_terms", [])]
    if include_terms and not any(term in text for term in include_terms):
        return False
    return True


def _find_symbol_value(text: str, label: str, canonical_unit: str) -> float | None:
    """从 γc=24 / 坍落度=180mm / fa=120kPa 等显式赋值中取数值。

    模式：
        label 空白? = 空白? 数字 单位?
    """
    unit_pattern = ""
    if canonical_unit:
        unit_pattern = rf"\s*{re.escape(canonical_unit)}?"
    patterns = [
        rf"{re.escape(label)}\s*(?:=|:|＝|：)\s*(-?\d+(?:\.\d+)?)\s*{re.escape(canonical_unit)}?",
        rf"{re.escape(label)}[^\d\-]{{0,8}}(-?\d+(?:\.\d+)?)",
    ]
    for pattern in patterns:
        match = re.search(pattern, text, re.IGNORECASE)
        if match:
            try:
                return float(match.group(1))
            except (ValueError, IndexError):
                continue
    return None


def _extract_from_table(
    item: ParameterEvidence,
    parameter_definition: dict[str, Any],
) -> list[dict[str, Any]]:
    rows = _table_rows(item.block.table_html or item.block.text)
    candidates: list[dict[str, Any]] = []
    aliases = [str(value) for value in parameter_definition.get("aliases", [])]
    inherited_unit = _inherited_table_unit(rows)
    for row in rows:
        row_text = " ".join(row)
        if _looks_like_normative_limit(row_text):
            continue
        for index, cell in enumerate(row):
            if not _cell_matches_alias(cell, aliases):
                continue
            if not _context_allowed(cell, parameter_definition):
                continue
            for value_cell in row[index + 1:]:
                value_match = _pick_compatible_match(value_cell, parameter_definition)
                if value_match:
                    candidates.append(
                        _candidate(
                            item,
                            parameter_definition,
                            float(value_match.group("value")),
                            raw_value=value_match.group(0),
                            raw_unit=value_match.group("unit") or _unit_from_label(cell) or inherited_unit,
                            confidence=0.95,
                            scope_hint=_scope_hint(" ".join(row)),
                        )
                    )
                    break
    return candidates


def _extract_from_text(
    item: ParameterEvidence,
    parameter_definition: dict[str, Any],
) -> list[dict[str, Any]]:
    text = item.block.text
    aliases = [str(value) for value in parameter_definition.get("aliases", [])]
    candidates: list[dict[str, Any]] = []
    for alias in aliases:
        for match in re.finditer(re.escape(alias), text):
            window = text[match.start(): min(len(text), match.end() + 80)]
            window = re.split(r"[。；;，,]", window, maxsplit=1)[0]
            if _RANGE_PATTERN.search(window):
                candidates.append(
                    _candidate(
                        item,
                        parameter_definition,
                        None,
                        raw_value=_RANGE_PATTERN.search(window).group(0),  # type: ignore[union-attr]
                        raw_unit="",
                        confidence=0.65,
                        scope_hint=_scope_hint(window),
                    )
                )
                continue
            if _looks_like_normative_limit(window):
                actual_window = _actual_value_window(text, match.end())
                if actual_window is None:
                    continue
                window = actual_window
            if not _context_allowed(window, parameter_definition):
                continue
            value_match = _pick_compatible_match(window, parameter_definition, strict=True)
            if value_match:
                candidates.append(
                    _candidate(
                        item,
                        parameter_definition,
                        float(value_match.group("value")),
                        raw_value=value_match.group(0),
                        raw_unit=value_match.group("unit") or "",
                        confidence=0.86 if item.evidence_quality != "low" else 0.55,
                        scope_hint=_scope_hint(window),
                    )
                )
    return candidates


def _candidate(
    item: ParameterEvidence,
    parameter_definition: dict[str, Any],
    value: Any,
    *,
    raw_value: str,
    raw_unit: str = "",
    confidence: float,
    scope_hint: str | None = None,
) -> dict[str, Any]:
    text = item.block.text.strip()
    if len(text) > 240:
        text = text[:237] + "..."
    return {
        "parameter": parameter_definition["parameter"],
        "value": value,
        "unit": parameter_definition.get("canonical_unit"),
        "raw_value": raw_value,
        "raw_unit": raw_unit,
        "confidence": confidence,
        "source_role": item.source_role,
        "evidence_quality": item.evidence_quality,
        "scope_hint": scope_hint,
        "evidence": {
            "physical_page": item.page.physical_page,
            "printed_page": item.page.printed_page,
            "section_path": item.section_path,
            "block_id": item.block.block_id,
            "block_type": item.block.block_type,
            "text": text,
            "source_role": item.source_role,
        },
    }


def _context_allowed(text: str, parameter_definition: dict[str, Any]) -> bool:
    for term in parameter_definition.get("exclude_terms", []):
        if str(term) in text:
            return False
    include_terms = [str(term) for term in parameter_definition.get("include_terms", [])]
    return not include_terms or any(term in text for term in include_terms)


def _looks_like_normative_limit(text: str) -> bool:
    return any(term in text for term in ("严禁", "不得", "不应", "应不", "不大于", "不小于"))


def _looks_like_normative_load_text(text: str) -> bool:
    return any(term in text for term in ("应包括", "应计入", "不得小于", "不应小于", "不得超过", "不应超过"))


def _matched_load_alias(text: str, load_item: dict[str, Any]) -> str | None:
    for term in load_item.get("exclude_context", []):
        if str(term) in text:
            return None
    include_context = [str(term) for term in load_item.get("include_context", [])]
    if include_context and not any(term in text for term in include_context):
        return None
    for alias in load_item.get("aliases", []):
        if str(alias) in text:
            return str(alias)
    return None


def _actual_value_window(text: str, start: int) -> str | None:
    tail = text[start: min(len(text), start + 120)]
    match = re.search(r"(?:实际|本工程|设置|采用|取值|为)\D{0,12}(?P<value>\d+(?:\.\d+)?\s*(?:kN/m2|kN/m²|kN/㎡|kN/m3|kN/m³|kN/立方米|kN/m|kN/米|kPa|mm|cm|m|毫米|厘米|米)?)", tail, re.I)
    return match.group(0) if match else None


def _cell_matches_alias(cell: str, aliases: list[str]) -> bool:
    compact = "".join(str(cell).split()).lower()
    for alias in aliases:
        normalized = "".join(alias.split()).lower()
        if normalized and normalized in compact:
            return True
    return False


def _unit_from_label(text: str) -> str:
    match = re.search(r"[（(](kN/m2|kN/m²|kN/㎡|kN/m3|kN/m³|kN/立方米|kN/m|kN/米|mm|cm|m|毫米|厘米|米)[）)]", text, re.I)
    return match.group(1) if match else ""


def _inherited_table_unit(rows: list[list[str]]) -> str:
    for row in rows[:2]:
        for cell in row:
            unit = _unit_from_label(cell)
            if unit:
                return unit
            match = re.search(r"单位\s*[：:]?\s*(kN/m2|kN/m²|kN/㎡|kN/m3|kN/m³|kN/立方米|kN/m|kN/米|mm|cm|m|毫米|厘米|米)", cell, re.I)
            if match:
                return match.group(1)
    return ""


def _scope_hint(text: str) -> str | None:
    match = _AREA_PATTERN.search(text)
    return match.group("scope") if match else None


def _dedupe_candidates(candidates: list[dict[str, Any]]) -> list[dict[str, Any]]:
    seen: set[tuple[Any, str, str]] = set()
    unique = []
    for candidate in candidates:
        evidence = candidate.get("evidence", {})
        key = (candidate.get("raw_value"), str(candidate.get("raw_unit")), str(evidence.get("block_id")))
        if key in seen:
            continue
        seen.add(key)
        unique.append(candidate)
    return unique


class _TableParser(HTMLParser):
    def __init__(self) -> None:
        super().__init__()
        self.rows: list[list[str]] = []
        self._row: list[str] | None = None
        self._cell: list[str] | None = None

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        if tag == "tr":
            self._row = []
        elif tag in {"td", "th"}:
            self._cell = []

    def handle_data(self, data: str) -> None:
        if self._cell is not None:
            self._cell.append(data)

    def handle_endtag(self, tag: str) -> None:
        if tag in {"td", "th"} and self._row is not None and self._cell is not None:
            self._row.append("".join(self._cell).strip())
            self._cell = None
        elif tag == "tr" and self._row is not None:
            self.rows.append(self._row)
            self._row = None


def _table_rows(value: str) -> list[list[str]]:
    if "<tr" not in value:
        return [[part.strip() for part in line.split("|") if part.strip()] for line in value.splitlines()]
    parser = _TableParser()
    parser.feed(value)
    return parser.rows
