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

from fastapi import BackgroundTasks, FastAPI, File, HTTPException, Request, UploadFile
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
from .dify_config import resolve_dify_completeness_mode
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


PROJECT_ROOT = Path(__file__).resolve().parent.parent
JOBS_ROOT = PROJECT_ROOT / "data" / "web" / "jobs"
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
    rule_id: str = Field(min_length=1, max_length=64)
    automatic_status: str
    human_decision: str
    human_decision_label: str = Field(default="")
    note: str = Field(default="", max_length=2000)


class DecisionsPayload(BaseModel):
    decisions: list[DecisionInput] = Field(min_length=1, max_length=10)


@app.get("/")
def index(request: Request):
    return templates.TemplateResponse(request=request, name="index.html")


@app.post("/api/jobs", status_code=202)
async def create_job(
    background_tasks: BackgroundTasks,
    file: UploadFile = File(...),
) -> dict[str, Any]:
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


@app.get("/api/jobs/{job_id}/comparison")
def get_comparison(job_id: str) -> dict[str, Any]:
    job_dir = _completed_job_dir(job_id)
    return _read_json(job_dir / "review_comparison.json", "对比结果不存在")


@app.post("/api/jobs/{job_id}/decisions")
def save_decisions(job_id: str, payload: DecisionsPayload) -> dict[str, Any]:
    job_dir = _completed_job_dir(job_id)
    review_results = _read_json(
        job_dir / "completeness_results.json", "审查结果不存在"
    )
    valid_rules = {
        str(item.get("rule_id")): str(item.get("status")) for item in review_results
    }
    decisions_path = job_dir / "decisions.json"
    existing = (
        _read_json(decisions_path, "人工复核记录不存在")
        if decisions_path.exists()
        else []
    )
    by_rule = {str(item.get("rule_id")): item for item in existing}

    for decision in payload.decisions:
        expected_status = valid_rules.get(decision.rule_id)
        if expected_status is None:
            raise HTTPException(status_code=422, detail="规则编号不存在")
        if (
            decision.automatic_status not in AUTOMATIC_STATUSES
            or decision.automatic_status != expected_status
        ):
            raise HTTPException(status_code=422, detail="自动审查状态不匹配")
        if decision.human_decision not in HUMAN_DECISIONS:
            raise HTTPException(status_code=422, detail="人工决定无效")
        by_rule[decision.rule_id] = {
            "job_id": job_id,
            "rule_id": decision.rule_id,
            "automatic_status": decision.automatic_status,
            "human_decision": decision.human_decision,
            "human_decision_label": decision.human_decision_label.strip() or decision.human_decision,
            "note": decision.note.strip(),
            "decided_at": _utc_now(),
        }

    saved = [by_rule[rule_id] for rule_id in sorted(by_rule)]
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
        "completeness_results.json": "完整性检查结果（10 条规则）",
        "completeness_summary.json": "完整性检查汇总",
        "completeness_evidence_check.md": "证据核对报告（Markdown）",
        "decisions.json": "人工复核记录",
        "review_comparison.json": "本地与 Dify 审查对比",
        "dify_review_result.json": "Dify AI 审查结果",
        "dify_request.json": "Dify 请求审计日志",
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
        _atomic_write_text(
            job_dir / "completeness_evidence_check.md",
            build_evidence_check_markdown(document, summary, details),
        )
        try:
            mode = _web_dify_mode()
            from .main import _write_dify_selection

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
