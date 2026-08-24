"""Agent 护栏层：Evidence Registry + Result Validator（V3.1 Phase 1）。

职责（架构设计见 docs/agent_architecture_v3_1.md §4.2/§4.4 与 V3 §9/§13）：
- EvidenceObject/EvidenceID：所有 Agent 工具返回内容统一登记为证据对象，
  finish 时只准引用 Evidence ID、不准自填原文（结构性杜绝伪造引用）
- EvidenceRegistry：登记/去重/解析/落盘（job 目录 evidence_registry.json）
- validate_finish：finish 结果校验（状态枚举/页码范围/证据 ID 真实存在/
  VIOLATED 必须带证据）

Budget（轮次/次数上限）在 Phase 5 收尾时并入本文件。
"""

from __future__ import annotations

import hashlib
import json
import re
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Any

ALLOWED_FINISH_STATUSES = {"COMPLIANT", "VIOLATED", "UNCERTAIN"}


# ---------------------------------------------------------------------------
# LaTeX 归一化（表格 block 的文本常为 $\Phi 48 \times 3.0$ 形态，
# 关键词匹配前必须归一，否则 "Φ48" 永远搜不到 -- Phase 0 发现 3 的根因之一）
# ---------------------------------------------------------------------------

_LATEX_SYMBOLS = {
    r"\Phi": "Φ",
    r"\phi": "φ",
    r"\times": "×",
    r"\le": "≤",
    r"\ge": "≥",
    r"\gamma": "γ",
    r"\omega": "ω",
    r"\leq": "≤",
    r"\geq": "≥",
    r"\pm": "±",
}


def normalize_for_match(text: str) -> str:
    """归一化文本用于关键词匹配：LaTeX 符号转直写、去 $、压空白、小写。"""
    value = text or ""
    for latex, plain in _LATEX_SYMBOLS.items():
        value = value.replace(latex, plain)
    value = value.replace("$", " ")
    value = re.sub(r"\s+", "", value)
    return value.lower()


def display_normalize(text: str) -> str:
    """展示归一化：LaTeX 符号转直写、去 $、空白压成单空格（保留大小写与可读性）。

    Agent 工具返回给 LLM 的文本一律过此函数：模型看到的是 "Φ 48 × 3.0"
    而非 "$\\Phi 48 \\times 3.0$"，引用时也以此形态登记为证据原文。
    """
    value = text or ""
    for latex, plain in _LATEX_SYMBOLS.items():
        value = value.replace(latex, plain)
    value = value.replace("$", " ")
    value = re.sub(r"\s+", " ", value)
    return value.strip()


# ---------------------------------------------------------------------------
# Evidence Object / Registry
# ---------------------------------------------------------------------------

@dataclass
class EvidenceObject:
    evidence_id: str
    document_id: str
    source_type: str  # text | table | page | drawing
    page: int
    block_id: str | None
    block_type: str
    text: str  # 证据原文片段（工具返回中实际可见的内容）
    source_tool: str  # 产生该证据的工具名
    source_role: str = "scheme_content"


def build_evidence_id(page: int, block_id: str | None) -> str:
    """EV-P{page}-B{block序号}；页级证据为 EV-P{page}-PAGE。"""
    if block_id:
        suffix = block_id.split("-")[-1] if "-" in block_id else block_id
        suffix = re.sub(r"^[bB]", "", suffix)  # p0013-b0002 -> B0002
        return f"EV-P{page}-B{suffix.upper()}"
    return f"EV-P{page}-PAGE"


class EvidenceRegistry:
    """本轮 Agent 运行的证据登记簿：登记去重、按 ID 解析、落盘。"""

    def __init__(self, document_id: str = "") -> None:
        self.document_id = document_id
        self._evidence: dict[str, EvidenceObject] = {}
        self._dedupe: dict[str, str] = {}  # 去重键 -> evidence_id

    def register(
        self,
        *,
        page: int,
        text: str,
        source_tool: str,
        block_id: str | None = None,
        block_type: str = "text",
        source_type: str | None = None,
    ) -> str:
        """登记证据，返回 evidence_id；同内容重复登记返回原 ID。"""
        dedupe_key = hashlib.sha256(
            f"{page}|{block_id}|{normalize_for_match(text[:500])}".encode("utf-8")
        ).hexdigest()
        if dedupe_key in self._dedupe:
            return self._dedupe[dedupe_key]
        evidence_id = build_evidence_id(page, block_id)
        # 同一 block 多次登记不同片段时追加序号保证唯一
        if evidence_id in self._evidence:
            evidence_id = f"{evidence_id}-{len(self._evidence)}"
        stype = source_type or ("table" if block_type == "table" else "text")
        obj = EvidenceObject(
            evidence_id=evidence_id,
            document_id=self.document_id,
            source_type=stype,
            page=page,
            block_id=block_id,
            block_type=block_type,
            text=text,
            source_tool=source_tool,
        )
        self._evidence[evidence_id] = obj
        self._dedupe[dedupe_key] = evidence_id
        return evidence_id

    def get(self, evidence_id: str) -> EvidenceObject | None:
        return self._evidence.get(evidence_id)

    def resolve(self, evidence_ids: list[str]) -> tuple[list[EvidenceObject], list[str]]:
        """返回 (解析成功列表, 未知 ID 列表)。"""
        found, missing = [], []
        for eid in evidence_ids:
            obj = self._evidence.get(str(eid).strip())
            if obj is None:
                missing.append(str(eid))
            else:
                found.append(obj)
        return found, missing

    def all_evidence(self) -> list[EvidenceObject]:
        return list(self._evidence.values())

    def to_dict(self) -> dict[str, Any]:
        return {
            "document_id": self.document_id,
            "evidence_count": len(self._evidence),
            "evidence": [asdict(obj) for obj in self._evidence.values()],
        }

    def save(self, path: Path) -> None:
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(
            json.dumps(self.to_dict(), ensure_ascii=False, indent=2) + "\n",
            encoding="utf-8",
        )

    @classmethod
    def load(cls, path: Path) -> "EvidenceRegistry":
        registry = cls()
        if not path.is_file():
            return registry
        data = json.loads(path.read_text(encoding="utf-8"))
        registry.document_id = str(data.get("document_id", ""))
        for item in data.get("evidence", []):
            obj = EvidenceObject(**item)
            registry._evidence[obj.evidence_id] = obj
        return registry


# ---------------------------------------------------------------------------
# Result Validator（V3 §13 + Phase 0 发现 4：page 范围校验）
# ---------------------------------------------------------------------------

def validate_finish(
    finish: dict[str, Any],
    *,
    registry: EvidenceRegistry,
    rule_id: str,
    total_pages: int,
) -> tuple[bool, list[str]]:
    """校验 agent 的 finish 结果；返回 (是否通过, 错误列表)。"""
    errors: list[str] = []
    status = str(finish.get("status", "")).upper()
    if status not in ALLOWED_FINISH_STATUSES:
        errors.append(f"status 非法：{status!r}（允许 {sorted(ALLOWED_FINISH_STATUSES)}）")
    evidence_ids = [str(e) for e in (finish.get("evidence_ids") or [])]
    if status == "VIOLATED" and not evidence_ids:
        errors.append("VIOLATED 判定必须携带 evidence_ids")
    _, missing = registry.resolve(evidence_ids)
    if missing:
        errors.append(f"evidence_ids 不存在于本轮证据登记簿：{missing}")
    page = finish.get("page")
    if page is not None:
        try:
            page_num = int(page)
        except (TypeError, ValueError):
            errors.append(f"page 非整数：{page!r}")
        else:
            if not 1 <= page_num <= total_pages:
                errors.append(f"page 超出范围 [1, {total_pages}]：{page_num}")
    if not str(finish.get("reason") or "").strip():
        errors.append("reason 不能为空")
    return (not errors, errors)
