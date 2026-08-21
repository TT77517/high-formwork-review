"""高支模审查系统的本地 Web 演示入口。"""

from __future__ import annotations

import json
import os
import re
import uuid
from dataclasses import asdict
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from fastapi import BackgroundTasks, FastAPI, File, Form, HTTPException, Request, UploadFile
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates
from dotenv import load_dotenv
from pydantic import BaseModel, Field

from .completeness_review import (
    build_evidence_check_markdown,
    load_rules,
    review_completeness_with_details,
)
from .consistency_review import build_consistency_review
from .dify_config import resolve_dify_completeness_mode
from .drawing_review import build_drawing_review
from .mineru_cache import (
    CACHE_ROOT,
    ParseCacheInfo,
    PARSER_CONFIG_VERSION,
    PARSER_VERSION,
    build_cache_key,
    parse_pdf_with_cache,
    sha256_file,
)
from .mineru_client import MinerUClient
from .mineru_parser import parse_mineru
from .project_facts import build_project_facts
from .project_qualification import build_project_qualification
from .review_summary import build_review_results
from .report_generator import build_review_report_from_job_dir
from .rule_engine import load_rule_library, run_rule_engine_safe
from .semantic_engine import run_semantic_engine_safe
from .standards import extract_standard_refs, get_standards_registry
from .calculation_engine import run_calculation_engine_safe
from .substantive_review import build_substantive_review


PROJECT_ROOT = Path(__file__).resolve().parent.parent
load_dotenv(PROJECT_ROOT / ".env")
DATA_ROOT = Path(os.getenv("DATA_ROOT", PROJECT_ROOT / "data")).expanduser()
if not DATA_ROOT.is_absolute():
    DATA_ROOT = PROJECT_ROOT / DATA_ROOT
JOBS_ROOT = DATA_ROOT / "web" / "jobs"
MINERU_CACHE_ROOT = CACHE_ROOT
RULES_PATH = PROJECT_ROOT / "config" / "completeness_rules.json"
MAX_UPLOAD_BYTES = 50 * 1024 * 1024
UPLOAD_CHUNK_BYTES = 1024 * 1024
JOB_ID_PATTERN = re.compile(r"^[0-9a-f]{32}$")
HUMAN_DECISIONS = {
    "pending",
    "confirmed",
    "rejected",
    "confirmed_pass",
    "confirmed_missing",
    "unable_to_verify",
    "false_positive",
    "need_supplement",
}
AUTOMATIC_STATUSES = {"PASS", "MISSING", "UNCERTAIN"}
ASSET_EXTENSIONS = {".jpg", ".jpeg", ".png", ".webp", ".gif", ".bmp"}
REVIEW_MODES = {"smart", "completeness", "semantic", "drawing", "calculation"}

STAGE_PROGRESS = {
    "waiting": 0,
    "uploaded": 10,
    "mineru_parsing": 30,
    "document_parsing": 60,
    "completeness_review": 80,
    "completed": 100,
    "completed_with_warning": 100,
    "failed": 100,
}
COMPLETED_STATUSES = {"completed", "completed_with_warning"}

app = FastAPI(title="高支模专项施工方案智能审查系统")
templates = Jinja2Templates(directory=str(PROJECT_ROOT / "app" / "templates"))
app.mount(
    "/static",
    StaticFiles(directory=str(PROJECT_ROOT / "app" / "static")),
    name="static",
)


class DecisionInput(BaseModel):
    rule_id: str | None = Field(default=None, min_length=1, max_length=64)
    item_key: str | None = Field(default=None, min_length=1, max_length=128)
    automatic_status: str
    human_decision: str
    human_decision_label: str = Field(default="")
    note: str = Field(default="", max_length=2000)


class DecisionsPayload(BaseModel):
    decisions: list[DecisionInput] = Field(min_length=1, max_length=200)


@app.get("/")
def index(request: Request):
    return templates.TemplateResponse(request=request, name="index.html")


@app.post("/api/jobs", status_code=202)
async def create_job(
    background_tasks: BackgroundTasks,
    file: UploadFile = File(...),
    review_mode: str = Form(default="smart"),
) -> dict[str, Any]:
    if review_mode not in REVIEW_MODES:
        raise HTTPException(status_code=422, detail="审查方式暂不可用")
    original_name = _safe_filename(file.filename)
    if not original_name.lower().endswith(".pdf"):
        raise HTTPException(status_code=415, detail="只允许上传 PDF 文件")

    job_id = uuid.uuid4().hex
    job_dir = JOBS_ROOT / job_id
    job_dir.mkdir(parents=True, exist_ok=False)
    temp_source = job_dir / f".source-{uuid.uuid4().hex}.tmp"
    source_path = job_dir / "source.pdf"
    total_size = 0
    header = b""

    try:
        with temp_source.open("wb") as output:
            while chunk := await file.read(UPLOAD_CHUNK_BYTES):
                if not header:
                    header = chunk[:5]
                total_size += len(chunk)
                if total_size > MAX_UPLOAD_BYTES:
                    raise HTTPException(status_code=413, detail="PDF 文件不能超过 50MB")
                output.write(chunk)
        if header != b"%PDF-":
            raise HTTPException(status_code=415, detail="文件内容不是有效的 PDF")
        os.replace(temp_source, source_path)
    except Exception:
        temp_source.unlink(missing_ok=True)
        if not source_path.exists():
            _remove_empty_job_dir(job_dir)
        raise
    finally:
        await file.close()

    source_sha256 = sha256_file(source_path)
    parse_cache_key = build_cache_key(source_sha256)
    now = _utc_now()
    status = {
        "job_id": job_id,
        "file_name": original_name,
        "content_type": _safe_content_type(file.content_type),
        "uploaded_at": now,
        "updated_at": now,
        "status": "uploaded",
        "stage": "uploaded",
        "progress": STAGE_PROGRESS["uploaded"],
        "message": "PDF 已上传，等待开始解析",
        "error_stage": None,
        "source_sha256": source_sha256,
        "parse_cache_hit": None,
        "parse_cache_key": parse_cache_key,
        "parse_cache_source": "pending",
        "parser_version": PARSER_VERSION,
        "parser_config_version": PARSER_CONFIG_VERSION,
        "parse_cache_warning": None,
        "document_parse_message": None,
        "review_mode": review_mode,
    }
    _atomic_write_json(job_dir / "status.json", status)
    background_tasks.add_task(_process_job, job_id)
    return status


@app.get("/api/jobs/{job_id}/status")
def get_status(job_id: str) -> dict[str, Any]:
    job_dir = _job_dir(job_id)
    return _read_json(job_dir / "status.json", "任务状态不存在")


@app.get("/api/jobs/{job_id}/document")
def get_document(job_id: str) -> dict[str, Any]:
    job_dir = _completed_job_dir(job_id)
    document = _read_json(job_dir / "mineru_document.json", "解析结果不存在")
    pages = document.get("pages", [])
    blocks = [block for page in pages for block in page.get("blocks", [])]
    block_counts: dict[str, int] = {}
    for block in blocks:
        block_type = str(block.get("block_type", "unknown"))
        block_counts[block_type] = block_counts.get(block_type, 0) + 1

    return {
        "engine": "MinerU",
        "agent_role": "结果校验、章节构建、页面分类和风险标记",
        "document_id": document.get("document_id"),
        "physical_page_count": document.get("physical_page_count", len(pages)),
        "section_count": len(document.get("sections", [])),
        "block_count": len(blocks),
        "text_block_count": sum(
            block_counts.get(name, 0) for name in ("title", "paragraph")
        ),
        "table_count": block_counts.get("table", 0),
        "image_count": block_counts.get("image", 0) + block_counts.get("chart", 0),
        "formula_count": block_counts.get("formula", 0),
        "complete_page_count": _count_pages(pages, "complete"),
        "partial_page_count": _count_pages(pages, "partial"),
        "unreadable_page_count": _count_pages(pages, "unreadable"),
        "human_review_page_count": sum(
            bool(page.get("requires_human_review")) for page in pages
        ),
        "requires_human_review": bool(document.get("requires_human_review")),
        "warnings": document.get("warnings", []),
        "sections": document.get("sections", []),
        "pages": [_page_summary(page) for page in pages],
    }


@app.get("/api/jobs/{job_id}/document/pages/{physical_page}")
def get_document_page(job_id: str, physical_page: int) -> dict[str, Any]:
    if physical_page < 1:
        raise HTTPException(status_code=404, detail="页面不存在")
    job_dir = _completed_job_dir(job_id)
    document = _read_json(job_dir / "mineru_document.json", "解析结果不存在")
    for page in document.get("pages", []):
        if page.get("physical_page") == physical_page:
            return {
                **_page_summary(page),
                "text": page.get("text", ""),
                "blocks": [
                    {
                        "block_id": block.get("block_id"),
                        "block_type": block.get("block_type"),
                        "text": block.get("text", ""),
                        "title_level": block.get("title_level"),
                        "bbox": block.get("bbox"),
                        "source_pointer": block.get("source_pointer"),
                        "image_path": block.get("image_path"),
                        "table_html": block.get("table_html"),
                    }
                    for block in page.get("blocks", [])
                ],
            }
    raise HTTPException(status_code=404, detail="页面不存在")


@app.get("/api/jobs/{job_id}/review")
def get_review(job_id: str) -> dict[str, Any]:
    job_dir = _completed_job_dir(job_id)
    results = _read_json(job_dir / "completeness_results.json", "审查结果不存在")
    summary = _read_json(job_dir / "completeness_summary.json", "审查汇总不存在")
    decisions_path = job_dir / "decisions.json"
    decisions = _read_json(decisions_path, "人工复核记录不存在") if decisions_path.exists() else []
    return {
        "agent_role": "执行 10 条完整性规则并组织可追溯证据",
        "summary": {
            key: summary.get(key)
            for key in ("total_rules", "pass_count", "missing_count", "uncertain_count")
        },
        "results": results,
        "decisions": decisions,
    }


@app.get("/api/jobs/{job_id}/precheck")
def get_precheck(job_id: str) -> dict[str, Any]:
    job_dir = _completed_job_dir(job_id)
    return _read_json(job_dir / "review_results.json", "智能预审汇总不存在")


@app.get("/api/jobs/{job_id}/rule-engine")
def get_rule_engine(job_id: str) -> dict[str, Any]:
    """返回 v4.0 规则引擎确定性规则审查结果。"""
    job_dir = _completed_job_dir(job_id)
    return _read_json(job_dir / "rule_engine_results.json", "规则引擎结果不存在")


@app.get("/api/jobs/{job_id}/semantic")
def get_semantic(job_id: str) -> dict[str, Any]:
    """返回语义规则审查结果。"""
    job_dir = _completed_job_dir(job_id)
    return _read_json(job_dir / "semantic_results.json", "语义审查结果不存在")


@app.get("/api/jobs/{job_id}/calculation")
def get_calculation(job_id: str) -> dict[str, Any]:
    """返回计算规则审查结果。"""
    job_dir = _completed_job_dir(job_id)
    return _read_json(job_dir / "calculation_results.json", "计算审查结果不存在")


@app.get("/api/jobs/{job_id}/report")
def get_review_report(job_id: str) -> dict[str, Any]:
    """生成并返回审查报告（Markdown 格式）。"""
    job_dir = _completed_job_dir(job_id)
    report_path = job_dir / "review_report.md"
    if not report_path.is_file():
        report = build_review_report_from_job_dir(job_dir)
        report_path.write_text(report, encoding="utf-8")
    return {"job_id": job_id, "format": "markdown", "content": report_path.read_text(encoding="utf-8")}


@app.get("/api/jobs/{job_id}/report/download")
def download_review_report(job_id: str) -> FileResponse:
    """下载审查报告 Markdown 文件。"""
    job_dir = _completed_job_dir(job_id)
    report_path = job_dir / "review_report.md"
    if not report_path.is_file():
        report = build_review_report_from_job_dir(job_dir)
        report_path.write_text(report, encoding="utf-8")
    return FileResponse(report_path, filename=f"审查报告_{job_id[:8]}.md")


# ===== 规则库管理 API =====

@app.get("/api/standards")
def list_standards() -> dict[str, Any]:
    """规范注册表：工程基础信息"适用规范"与规则库管理规范筛选的同一词汇。"""
    counts: dict[str, int] = {}
    for rule in load_rule_library():
        for sid in extract_standard_refs((rule.get("code_ref") or {}).get("standard")):
            counts[sid] = counts.get(sid, 0) + 1
    standards = [
        {**entry, "rule_count": counts.get(str(entry["standard_id"]), 0)}
        for entry in get_standards_registry()
    ]
    return {"total": len(standards), "standards": standards}


@app.get("/api/rules")
def list_rules(
    module: str | None = None,
    check_type: str | None = None,
    severity: str | None = None,
    status: str | None = None,
    standard: str | None = None,
) -> dict[str, Any]:
    """浏览/筛选规则库（164条）。"""
    rules = []
    for rule in load_rule_library():
        refs = extract_standard_refs((rule.get("code_ref") or {}).get("standard"))
        rules.append({**rule, "standard_refs": refs, "standard_id": refs[0] if refs else None})
    if module:
        rules = [r for r in rules if r.get("module") == module]
    if check_type:
        rules = [r for r in rules if r.get("check_type") == check_type]
    if severity:
        rules = [r for r in rules if r.get("severity") == severity]
    if status:
        rules = [r for r in rules if r.get("status") == status]
    if standard:
        known_ids = {str(e["standard_id"]) for e in get_standards_registry()}
        if standard in known_ids:
            rules = [r for r in rules if standard in r.get("standard_refs", [])]
        else:
            # 回退：非注册表词汇时保留旧的宽松子串匹配，兼容旧调用
            std_norm = standard.replace(" ", "").replace("/", "")
            rules = [
                r for r in rules
                if std_norm in (r.get("code_ref", {}).get("standard", "") or "").replace(" ", "").replace("/", "")
            ]
    modules_summary: dict[str, int] = {}
    for r in rules:
        m = r.get("module", "unknown")
        modules_summary[m] = modules_summary.get(m, 0) + 1
    return {
        "total": len(rules),
        "modules": modules_summary,
        "rules": rules,
    }


@app.get("/api/rules/{rule_id}")
def get_rule(rule_id: str) -> dict[str, Any]:
    """查询单条规则详情。"""
    for rule in load_rule_library():
        if rule.get("rule_id") == rule_id:
            refs = extract_standard_refs((rule.get("code_ref") or {}).get("standard"))
            return {
                **rule,
                "standard_refs": refs,
                "standard_id": refs[0] if refs else None,
            }
    raise HTTPException(status_code=404, detail=f"规则 {rule_id} 不存在")


class RuleUpdateInput(BaseModel):
    field: str = Field(min_length=1, max_length=64)
    value: Any = None


class RuleCreateInput(BaseModel):
    rule_id: str = Field(min_length=1, max_length=64)
    rule_name: str = Field(min_length=1, max_length=200)
    module: str = Field(min_length=1, max_length=64)
    category: str = Field(default="", max_length=64)
    check_type: str = Field(default="deterministic", max_length=32)
    severity: str = Field(default="B-required", max_length=32)
    risk_level: str = Field(default="medium", max_length=32)
    applicable_types: list[str] = Field(default_factory=lambda: ["universal"])
    code_ref: dict[str, Any] = Field(default_factory=dict)
    check_content: str = Field(default="", max_length=2000)
    check_logic: dict[str, Any] = Field(default_factory=dict)
    threshold: Any = Field(default=None)
    remedy_suggestion: str = Field(default="", max_length=2000)
    typical_violation: str = Field(default="", max_length=2000)
    manual_review: bool = Field(default=False)
    notes: str = Field(default="", max_length=2000)


_MODULE_FILE_MAP = {
    "01_procedure_compliance": "module_01_procedure_compliance.json",
    "02_load_values": "module_02_load_values.json",
    "03_structural_calculation": "module_03_structural_calculation.json",
    "04_construction_requirements": "module_04_construction_requirements.json",
    "05_material_requirements": "module_05_material_requirements.json",
    "06_safety_measures": "module_06_safety_measures.json",
}


@app.post("/api/rules", status_code=201)
def create_rule(payload: RuleCreateInput) -> dict[str, Any]:
    """新增规则到指定模块 JSON。"""
    module = payload.module
    filename = _MODULE_FILE_MAP.get(module)
    if not filename:
        raise HTTPException(status_code=422, detail=f"模块 {module} 不存在")
    path = PROJECT_ROOT / "config" / "rule_library_v4" / filename
    if not path.is_file():
        raise HTTPException(status_code=500, detail="规则文件不存在")
    rules = json.loads(path.read_text(encoding="utf-8"))
    for existing in rules:
        if existing.get("rule_id") == payload.rule_id:
            raise HTTPException(status_code=409, detail=f"规则 {payload.rule_id} 已存在")
    rule = {
        "rule_id": payload.rule_id,
        "rule_name": payload.rule_name,
        "module": module,
        "category": payload.category or module.split("_", 1)[1] if "_" in module else "",
        "check_type": payload.check_type,
        "severity": payload.severity,
        "risk_level": payload.risk_level,
        "applicable_types": payload.applicable_types,
        "code_ref": payload.code_ref,
        "legacy_code_ref": None,
        "check_content": payload.check_content,
        "check_logic": payload.check_logic,
        "threshold": payload.threshold,
        "remedy_suggestion": payload.remedy_suggestion,
        "typical_violation": payload.typical_violation,
        "manual_review": payload.manual_review,
        "notes": payload.notes,
        "status": "active",
    }
    rules.append(rule)
    path.write_text(json.dumps(rules, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    return {"rule_id": payload.rule_id, "created": True}


@app.delete("/api/rules/{rule_id}")
def delete_rule(rule_id: str) -> dict[str, Any]:
    """删除规则（软删除：status→deprecated）。"""
    for filename in _MODULE_FILE_MAP.values():
        path = PROJECT_ROOT / "config" / "rule_library_v4" / filename
        if not path.is_file():
            continue
        rules = json.loads(path.read_text(encoding="utf-8"))
        for rule in rules:
            if rule.get("rule_id") == rule_id:
                rule["status"] = "deprecated"
                path.write_text(
                    json.dumps(rules, ensure_ascii=False, indent=2) + "\n",
                    encoding="utf-8",
                )
                return {"rule_id": rule_id, "deleted": True, "status": "deprecated"}
    raise HTTPException(status_code=404, detail=f"规则 {rule_id} 不存在")


@app.patch("/api/rules/{rule_id}")
def update_rule(rule_id: str, payload: RuleUpdateInput) -> dict[str, Any]:
    """编辑单条规则的指定字段。

    仅支持修改 check_logic 和 threshold 下的可编辑字段，
    修改直接写回 config/rule_library_v4/ 对应模块 JSON。
    """
    editable_fields = {
        "threshold", "remedy_suggestion", "typical_violation",
        "manual_review", "notes", "check_content", "status",
    }
    if payload.field not in editable_fields:
        raise HTTPException(
            status_code=422,
            detail=f"字段 {payload.field} 不可编辑，仅支持: {', '.join(sorted(editable_fields))}",
        )
    # 定位规则所在文件
    for filename in (
        "module_01_procedure_compliance.json",
        "module_02_load_values.json",
        "module_03_structural_calculation.json",
        "module_04_construction_requirements.json",
        "module_05_material_requirements.json",
        "module_06_safety_measures.json",
    ):
        path = PROJECT_ROOT / "config" / "rule_library_v4" / filename
        if not path.is_file():
            continue
        rules = json.loads(path.read_text(encoding="utf-8"))
        for rule in rules:
            if rule.get("rule_id") == rule_id:
                old_value = rule.get(payload.field)
                rule[payload.field] = payload.value
                path.write_text(
                    json.dumps(rules, ensure_ascii=False, indent=2) + "\n",
                    encoding="utf-8",
                )
                return {
                    "rule_id": rule_id,
                    "field": payload.field,
                    "old_value": old_value,
                    "new_value": payload.value,
                    "updated": True,
                }
    raise HTTPException(status_code=404, detail=f"规则 {rule_id} 不存在")


@app.get("/api/jobs/{job_id}/comparison")
def get_comparison(job_id: str) -> dict[str, Any]:
    job_dir = _completed_job_dir(job_id)
    return _read_json(job_dir / "review_comparison.json", "对比结果不存在")


@app.post("/api/jobs/{job_id}/decisions")
def save_decisions(job_id: str, payload: DecisionsPayload) -> dict[str, Any]:
    job_dir = _completed_job_dir(job_id)
    completeness_results = _read_json(
        job_dir / "completeness_results.json", "审查结果不存在"
    )
    valid_rules = {
        str(item.get("rule_id")): str(item.get("status")) for item in completeness_results
    }
    decisions_path = job_dir / "decisions.json"
    existing = (
        _read_json(decisions_path, "人工复核记录不存在")
        if decisions_path.exists()
        else []
    )
    by_key: dict[str, dict[str, Any]] = {}
    for item in existing or []:
        key = str(item.get("item_key") or f"completeness_review:{item.get('rule_id')}")
        by_key[key] = {**item, "item_key": key, "source": key.split(":", 1)[0]}

    for decision in payload.decisions:
        if not decision.rule_id and not decision.item_key:
            raise HTTPException(status_code=422, detail="rule_id 或 item_key 必填其一")
        item_key = decision.item_key or f"completeness_review:{decision.rule_id}"
        source, _, item_id = item_key.partition(":")
        record_rule_id = None
        if source == "completeness_review":
            rule_id = decision.rule_id or item_id
            expected_status = valid_rules.get(rule_id)
            if expected_status is None:
                raise HTTPException(status_code=422, detail="规则编号不存在")
            if (
                decision.automatic_status not in AUTOMATIC_STATUSES
                or decision.automatic_status != expected_status
            ):
                raise HTTPException(status_code=422, detail="自动审查状态不匹配")
            record_rule_id = rule_id
        elif source in {"rule_engine", "semantic_engine"}:
            fname = "rule_engine_results.json" if source == "rule_engine" else "semantic_results.json"
            data = _read_json(job_dir / fname, "") if (job_dir / fname).is_file() else None
            statuses = {
                str(r.get("rule_id")): str(r.get("status"))
                for r in (data or {}).get("results", [])
            }
            expected_status = statuses.get(item_id)
            if expected_status is None or decision.automatic_status != expected_status:
                raise HTTPException(status_code=422, detail="自动审查状态不匹配")
        elif source in {"substantive_review", "consistency_review", "drawing_review"}:
            fpath = job_dir / f"{source}.json"
            items = _read_json(fpath, "") if fpath.is_file() else None
            statuses = {
                str(i.get("review_item_id")): str(i.get("status")) for i in items or []
            }
            expected_status = statuses.get(item_id)
            if expected_status is None or decision.automatic_status != expected_status:
                raise HTTPException(status_code=422, detail="自动审查状态不匹配")
        else:
            # 聚合项（engine_scope/document_parse/project_qualification）不比对自动状态
            if decision.automatic_status not in {"REVIEW", "PENDING_CONFIRMATION"}:
                raise HTTPException(status_code=422, detail="自动审查状态不匹配")
        if decision.human_decision not in HUMAN_DECISIONS:
            raise HTTPException(status_code=422, detail="人工决定无效")
        record = {
            "job_id": job_id,
            "item_key": item_key,
            "source": source,
            "automatic_status": decision.automatic_status,
            "human_decision": decision.human_decision,
            "human_decision_label": decision.human_decision_label.strip() or decision.human_decision,
            "note": decision.note.strip(),
            "decided_at": _utc_now(),
        }
        if record_rule_id:
            record["rule_id"] = record_rule_id
        by_key[item_key] = record

    saved = [by_key[key] for key in sorted(by_key)]
    _atomic_write_json(decisions_path, saved)
    return {"job_id": job_id, "saved_count": len(payload.decisions), "decisions": saved}


@app.get("/api/jobs/{job_id}/asset")
def get_asset(job_id: str, path: str) -> FileResponse:
    job_dir = _job_dir(job_id)
    if not path or Path(path).is_absolute() or ".." in Path(path).parts:
        raise HTTPException(status_code=400, detail="资源路径无效")
    asset_root = (job_dir / "mineru_api" / "raw").resolve()
    target = (asset_root / path).resolve()
    if target == asset_root or asset_root not in target.parents:
        raise HTTPException(status_code=400, detail="资源路径无效")
    if target.suffix.lower() not in ASSET_EXTENSIONS:
        raise HTTPException(status_code=415, detail="只允许读取任务图片资源")
    if not target.is_file():
        raise HTTPException(status_code=404, detail="资源不存在")
    return FileResponse(target)


@app.get("/api/jobs/{job_id}/dify-error")
def get_dify_error(job_id: str) -> dict[str, Any]:
    """读取 Dify 错误文件（如果存在）。"""
    job_dir = _completed_job_dir(job_id)
    error_path = job_dir / "dify_error.json"
    if not error_path.exists():
        raise HTTPException(status_code=404, detail="无 Dify 错误记录")
    return _read_json(error_path, "Dify 错误记录不存在")


@app.get("/api/jobs/{job_id}/timeline")
def get_timeline(job_id: str) -> dict[str, Any]:
    """构建任务处理时间线。"""
    job_dir = _completed_job_dir(job_id)
    status = _read_json(job_dir / "status.json", "任务状态不存在")
    events: list[dict[str, Any]] = []

    # 上传事件
    events.append({
        "time": status.get("uploaded_at", ""),
        "stage": "uploaded",
        "description": f"上传文件：{status.get('file_name', '未知')}",
    })

    # 解析开始
    events.append({
        "time": status.get("updated_at", ""),
        "stage": "mineru_parsing",
        "description": "MinerU 多模态解析",
    })

    # 文档解析
    events.append({
        "time": status.get("updated_at", ""),
        "stage": "document_parsing",
        "description": status.get(
            "document_parse_message",
            "文档解析 Agent：章节构建与风险标记",
        ),
    })

    # 完整性审查
    events.append({
        "time": status.get("updated_at", ""),
        "stage": "completeness_review",
        "description": "完整性审查 Agent：执行 10 条规则",
    })

    # Dify 审查
    dify_result = None
    try:
        dify_result = _read_json(job_dir / "dify_review_result.json", "")
    except HTTPException:
        pass
    dify_error = None
    try:
        dify_error = _read_json(job_dir / "dify_error.json", "")
    except HTTPException:
        pass

    if dify_result:
        events.append({
            "time": status.get("updated_at", ""),
            "stage": "dify_review",
            "description": f"Dify 审查完成（{dify_result.get('total_rules', '?')} 条规则）",
        })
    elif dify_error:
        events.append({
            "time": status.get("updated_at", ""),
            "stage": "dify_failed",
            "error": True,
            "description": f"Dify 审查失败：{dify_error.get('message', '未知错误')}",
        })
    else:
        events.append({
            "time": status.get("updated_at", ""),
            "stage": "dify_disabled",
            "description": "Dify 未启用，跳过 AI 审查",
        })

    # 人工复核
    decisions_path = job_dir / "decisions.json"
    if decisions_path.exists():
        decisions = _read_json(decisions_path, "")
        if decisions:
            reviewed = sum(1 for d in decisions if d.get("human_decision") != "pending")
            events.append({
                "time": decisions[-1].get("decided_at", status.get("updated_at", "")),
                "stage": "human_review",
                "description": f"人工复核：{reviewed}/{len(decisions)} 条已处理",
            })

    # 完成
    events.append({
        "time": status.get("updated_at", ""),
        "stage": status.get("status", "completed"),
        "description": status.get("message", "任务完成"),
    })

    return {"job_id": job_id, "events": events}


@app.get("/api/jobs/{job_id}/files")
def get_output_files(job_id: str) -> dict[str, Any]:
    """列出任务输出文件（不含敏感信息）。"""
    job_dir = _completed_job_dir(job_id)
    files: list[dict[str, str]] = []

    file_descriptions = {
        "mineru_document.json": "MinerU 解析结构化文档",
        "project_facts.json": "工程事实识别结果",
        "project_qualification.json": "工程基础信息与审查范围",
        "completeness_results.json": "完整性审查结果（10 项）",
        "completeness_summary.json": "完整性审查汇总",
        "substantive_review.json": "规范符合性审查结果（部分可用）",
        "rule_engine_results.json": "v4.0规则引擎确定性审查结果",
        "semantic_results.json": "语义规则审查结果",
        "calculation_results.json": "计算规则审查结果",
        "review_report.md": "完整审查报告（Markdown）",
        "consistency_review.json": "正文-计算书参数一致性检查结果",
        "drawing_review.json": "图文复核提示结果",
        "review_results.json": "智能预审统一汇总",
        "completeness_evidence_check.md": "证据核对报告（Markdown）",
        "decisions.json": "人工复核记录",
        "review_comparison.json": "本地与 Dify 审查对比",
        "dify_review_result.json": "Dify AI 审查结果",
        "dify_request.json": "Dify 请求审计日志",
        "dify_call_audit.json": "Dify 调用与缓存审计",
        "dify_raw_response.json": "Dify 原始响应",
        "dify_error.json": "Dify 错误记录",
        "status.json": "任务状态",
    }

    for file_name, desc in file_descriptions.items():
        file_path = job_dir / file_name
        if file_path.is_file():
            size_bytes = file_path.stat().st_size
            size_str = f"{size_bytes / 1024:.1f} KB" if size_bytes < 1024 * 1024 else f"{size_bytes / 1048576:.1f} MB"
            files.append({
                "name": file_name,
                "description": desc,
                "size": size_str,
                "downloadable": True,
            })

    return {"job_id": job_id, "files": files}


@app.get("/api/jobs/{job_id}/download/{filename:path}")
def download_output_file(job_id: str, filename: str) -> FileResponse:
    """下载任务输出文件（排除含敏感信息的文件）。"""
    job_dir = _completed_job_dir(job_id)
    # 不允许下载含 API Key 的文件
    sensitive_names = {"dify_request.json", "dify_raw_response.json"}
    safe_name = Path(filename).name
    if safe_name in sensitive_names:
        raise HTTPException(status_code=403, detail="此文件可能包含敏感信息，不支持直接下载")
    if ".." in safe_name or Path(safe_name).is_absolute():
        raise HTTPException(status_code=400, detail="文件名无效")
    target = job_dir / safe_name
    if not target.is_file():
        raise HTTPException(status_code=404, detail="文件不存在")
    return FileResponse(target, filename=safe_name)


def _process_job(job_id: str) -> None:
    job_dir = _job_dir(job_id)
    source_path = job_dir / "source.pdf"
    stage = "mineru_parsing"
    try:
        _update_status(job_dir, stage, "MinerU 正在进行底层多模态解析")
        document, cache_info = parse_pdf_with_cache(
            pdf_path=source_path,
            raw_output_dir=job_dir / "mineru_api",
            document_output_path=job_dir / "mineru_document.json",
            cache_root=MINERU_CACHE_ROOT,
            client_factory=MinerUClient,
            parser=parse_mineru,
            before_document_parse=lambda: _update_status(
                job_dir,
                "document_parsing",
                "文档解析 Agent 正在构建章节与标记风险",
            ),
        )
        _record_parse_cache_status(job_dir, cache_info)

        stage = "document_parsing"

        stage = "completeness_review"
        _update_status(job_dir, stage, "完整性审查 Agent 正在执行 10 条规则")
        rules = load_rules(RULES_PATH)
        summary, details = review_completeness_with_details(document, rules)
        page_by_number = {
            page.physical_page: page for page in document.pages
        }
        enriched_results = []
        for result, detail in zip(summary.results, details):
            item = asdict(result)
            for evidence in item["evidence"]:
                page = page_by_number.get(evidence["physical_page"])
                evidence["page_type"] = page.page_type if page else None
                evidence["parse_status"] = page.parse_status if page else None
                evidence["whether_from_toc"] = bool(
                    page
                    and any("目录页" in warning for warning in page.warnings)
                )
                evidence["requires_human_review"] = bool(
                    page and page.requires_human_review
                )
            item.update(
                {
                    "matched_sections": detail["matched_sections"],
                    "matched_terms": detail["matched_terms"],
                    "matched_subitems": detail["matched_subitems"],
                    "physical_pages": detail["physical_pages"],
                    "printed_pages": detail["printed_pages"],
                }
            )
            enriched_results.append(item)
        _atomic_write_json(job_dir / "completeness_results.json", enriched_results)
        _atomic_write_json(job_dir / "completeness_summary.json", asdict(summary))
        project_facts = build_project_facts(document)
        project_qualification = build_project_qualification(document, project_facts)
        rule_engine_result = run_rule_engine_safe(document, project_facts)
        semantic_result = run_semantic_engine_safe(document, project_facts)
        calculation_result = run_calculation_engine_safe(document, project_facts)
        substantive_review = build_substantive_review(project_qualification, project_facts)
        consistency_review = build_consistency_review(project_facts, document)
        drawing_review = build_drawing_review(document, project_facts)
        _atomic_write_json(job_dir / "project_facts.json", project_facts)
        _atomic_write_json(job_dir / "project_qualification.json", project_qualification)
        _atomic_write_json(job_dir / "rule_engine_results.json", rule_engine_result)
        _atomic_write_json(job_dir / "semantic_results.json", semantic_result)
        _atomic_write_json(job_dir / "calculation_results.json", calculation_result)
        _atomic_write_json(job_dir / "substantive_review.json", substantive_review)
        _atomic_write_json(job_dir / "consistency_review.json", consistency_review)
        _atomic_write_json(job_dir / "drawing_review.json", drawing_review)
        _atomic_write_json(
            job_dir / "review_results.json",
            build_review_results(
                project_qualification,
                asdict(summary),
                substantive_review,
                consistency_review=consistency_review,
                drawing_review=drawing_review,
                rule_engine=rule_engine_result,
                semantic=semantic_result,
                document_pages=[
                    {
                        "physical_page": p.physical_page,
                        "requires_human_review": p.requires_human_review,
                    }
                    for p in document.pages
                ],
            ),
        )
        _atomic_write_text(
            job_dir / "completeness_evidence_check.md",
            build_evidence_check_markdown(document, summary, details),
        )
        try:
            mode = _web_dify_mode()
            from .main import (
                _write_dify_selection,
                _write_review_comparison_if_ready,
            )

            _write_dify_selection(job_dir, summary.results, mode)
        except ValueError as exc:
            _atomic_write_json(
                job_dir / "dify_error.json",
                {
                    "status": "DIFY_FAILED",
                    "message": str(exc),
                    "failed_batch_index": None,
                },
            )
            _update_status(
                job_dir,
                "completed_with_warning",
                "Dify配置无效，本地结果可用",
                error_stage="dify_review",
            )
            _write_review_comparison_if_ready(job_dir)
            return

        if mode != "off":
            try:
                _run_optional_dify_review(job_dir, rules)
                _update_status(job_dir, "completed", "解析、本地审查与 Dify 审查已完成")
            except (OSError, RuntimeError, ValueError):
                _update_status(
                    job_dir,
                    "completed_with_warning",
                    "Dify审查失败，本地结果可用",
                    error_stage="dify_review",
                )
        else:
            _update_status(job_dir, "completed", "解析与完整性审查已完成")
        _write_review_comparison_if_ready(job_dir)
        _write_precheck_summary_if_ready(job_dir)
        # Generate review report
        try:
            report = build_review_report_from_job_dir(job_dir)
            _atomic_write_text(job_dir / "review_report.md", report)
        except Exception:
            pass
    except Exception:
        _update_status(
            job_dir,
            "failed",
            _failure_message(stage),
            error_stage=stage,
        )


def _update_status(
    job_dir: Path,
    stage: str,
    message: str,
    error_stage: str | None = None,
) -> None:
    status_path = job_dir / "status.json"
    status = _read_json(status_path, "任务状态不存在")
    status.update(
        {
            "status": stage,
            "stage": stage,
            "progress": STAGE_PROGRESS[stage],
            "updated_at": _utc_now(),
            "message": message,
            "error_stage": error_stage,
        }
    )
    _atomic_write_json(status_path, status)


def _record_parse_cache_status(job_dir: Path, cache_info: ParseCacheInfo) -> None:
    status_path = job_dir / "status.json"
    status = _read_json(status_path, "任务状态不存在")
    status.update(
        {
            "source_sha256": cache_info.source_sha256,
            "parse_cache_hit": cache_info.cache_hit,
            "parse_cache_key": cache_info.cache_key,
            "parse_cache_source": cache_info.cache_source,
            "parser_version": cache_info.parser_version,
            "parser_config_version": cache_info.parser_config_version,
            "parse_cache_warning": cache_info.warning,
            "document_parse_message": (
                "文档解析：复用缓存"
                if cache_info.cache_hit
                else "文档解析：调用 MinerU"
            ),
        }
    )
    _atomic_write_json(status_path, status)


def _failure_message(stage: str) -> str:
    return {
        "mineru_parsing": "MinerU 解析失败，请检查网络和 API 配置后重试",
        "document_parsing": "文档解析失败，请检查 MinerU 结果是否完整",
        "completeness_review": "完整性审查失败，请检查规则配置和解析结果",
    }.get(stage, "任务处理失败，请稍后重试")


def _web_dify_mode() -> str:
    load_dotenv()
    return resolve_dify_completeness_mode(
        explicit_mode=os.getenv("DIFY_COMPLETENESS_MODE"),
        web_enable_dify=os.getenv("WEB_ENABLE_DIFY", "false"),
        load_environment=False,
    )


def _run_optional_dify_review(job_dir: Path, rules: list[dict[str, Any]]) -> None:
    from .main import _run_dify_review

    _run_dify_review(job_dir, rules)


def _write_precheck_summary_if_ready(job_dir: Path) -> None:
    paths = {
        "qualification": job_dir / "project_qualification.json",
        "completeness": job_dir / "completeness_summary.json",
        "substantive": job_dir / "substantive_review.json",
        "rule_engine": job_dir / "rule_engine_results.json",
        "consistency": job_dir / "consistency_review.json",
        "drawing": job_dir / "drawing_review.json",
        "comparison": job_dir / "review_comparison.json",
    }
    if not all(paths[key].is_file() for key in ("qualification", "completeness", "substantive")):
        return
    comparison = _read_json(paths["comparison"], "") if paths["comparison"].is_file() else None
    consistency = _read_json(paths["consistency"], "") if paths["consistency"].is_file() else None
    drawing = _read_json(paths["drawing"], "") if paths["drawing"].is_file() else None
    rule_engine = _read_json(paths["rule_engine"], "") if paths["rule_engine"].is_file() else None
    semantic_path = job_dir / "semantic_results.json"
    semantic = _read_json(semantic_path, "") if semantic_path.is_file() else None
    document_pages = None
    doc_path = job_dir / "mineru_document.json"
    if doc_path.is_file():
        doc_data = _read_json(doc_path, "")
        if isinstance(doc_data, dict):
            document_pages = [
                {
                    "physical_page": p.get("physical_page"),
                    "requires_human_review": p.get("requires_human_review"),
                }
                for p in doc_data.get("pages", [])
            ]
    _atomic_write_json(
        job_dir / "review_results.json",
        build_review_results(
            _read_json(paths["qualification"], ""),
            _read_json(paths["completeness"], ""),
            _read_json(paths["substantive"], ""),
            comparison=comparison,
            consistency_review=consistency,
            drawing_review=drawing,
            rule_engine=rule_engine,
            semantic=semantic,
            document_pages=document_pages,
        ),
    )


def _job_dir(job_id: str) -> Path:
    if not JOB_ID_PATTERN.fullmatch(job_id):
        raise HTTPException(status_code=404, detail="任务不存在")
    job_dir = JOBS_ROOT / job_id
    if not job_dir.is_dir():
        raise HTTPException(status_code=404, detail="任务不存在")
    return job_dir


def _completed_job_dir(job_id: str) -> Path:
    job_dir = _job_dir(job_id)
    status = _read_json(job_dir / "status.json", "任务状态不存在")
    if status.get("status") not in COMPLETED_STATUSES:
        raise HTTPException(status_code=409, detail="任务尚未完成")
    return job_dir


def _safe_filename(filename: str | None) -> str:
    name = Path(filename or "").name
    name = "".join(char for char in name if char.isprintable()).strip()
    if not name or len(name) > 255:
        raise HTTPException(status_code=400, detail="文件名无效")
    return name


def _safe_content_type(content_type: str | None) -> str:
    value = (content_type or "").lower()
    return value if value in {"application/pdf", "application/octet-stream"} else "unknown"


def _atomic_write_json(path: Path, data: Any) -> None:
    _atomic_write_text(
        path,
        json.dumps(data, ensure_ascii=False, indent=2) + "\n",
    )


def _atomic_write_text(path: Path, content: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temp_path = path.with_name(f".{path.name}-{uuid.uuid4().hex}.tmp")
    try:
        temp_path.write_text(content, encoding="utf-8")
        os.replace(temp_path, path)
    finally:
        temp_path.unlink(missing_ok=True)


def _read_json(path: Path, missing_message: str) -> Any:
    if not path.is_file():
        raise HTTPException(status_code=404, detail=missing_message)
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise HTTPException(status_code=500, detail="任务数据暂时无法读取") from exc


def _page_summary(page: dict[str, Any]) -> dict[str, Any]:
    blocks = page.get("blocks", [])
    return {
        "physical_page": page.get("physical_page"),
        "printed_page": page.get("printed_page"),
        "page_type": page.get("page_type"),
        "parse_status": page.get("parse_status"),
        "text_length": len(page.get("text", "")),
        "image_count": sum(
            block.get("block_type") in {"image", "chart"} for block in blocks
        ),
        "table_count": sum(block.get("block_type") == "table" for block in blocks),
        "formula_count": sum(
            block.get("block_type") == "formula" for block in blocks
        ),
        "warnings": page.get("warnings", []),
        "requires_human_review": bool(page.get("requires_human_review")),
    }


def _count_pages(pages: list[dict[str, Any]], status: str) -> int:
    return sum(page.get("parse_status") == status for page in pages)


def _utc_now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def _remove_empty_job_dir(job_dir: Path) -> None:
    try:
        job_dir.rmdir()
    except OSError:
        pass
