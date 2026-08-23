"""项目命令行入口。"""

from __future__ import annotations

import argparse
import asyncio
import json
import os
import re
import sys
import time
from dataclasses import asdict
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Callable

from .completeness_review import (
    build_evidence_check_markdown,
    load_rules,
    review_completeness_with_details,
)
from .completeness_review_selector import select_rules_for_dify_review
from .dify_config import (
    DifyReviewConfig,
    resolve_dify_completeness_mode,
    resolve_dify_review_config,
)
from .consistency_review import build_consistency_review
from .drawing_review import build_drawing_review
from .mineru_cache import parse_pdf_with_cache
from .mineru_client import MinerUClient
from .mineru_parser import parse_mineru
from .project_facts import build_project_facts
from .project_qualification import build_project_qualification
from .review_summary import build_review_results
from .report_generator import build_review_report_from_job_dir
from .rule_engine import run_rule_engine_safe
from .semantic_engine import run_semantic_engine_safe
from .calculation_engine import run_calculation_engine_safe
from .substantive_review import build_substantive_review


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="读取 MinerU 落盘结果并执行高支模方案完整性审查"
    )
    input_group = parser.add_mutually_exclusive_group(required=True)
    input_group.add_argument("--raw-dir", help="MinerU raw 结果目录")
    input_group.add_argument("--pdf", help="待提交 MinerU 解析的 PDF 文件")
    parser.add_argument("--output-dir", required=True, help="JSON 输出目录")
    parser.add_argument(
        "--dify",
        action="store_true",
        default=False,
        help="在文档解析完成后调用Dify完整性审查工作流",
    )
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    output_dir = Path(args.output_dir)
    rules_path = Path(__file__).resolve().parent.parent / "config" / "completeness_rules.json"

    try:
        if args.pdf is not None:
            document, _cache_info = parse_pdf_with_cache(
                pdf_path=args.pdf,
                raw_output_dir=Path(args.output_dir) / "mineru_api",
                document_output_path=output_dir / "mineru_document.json",
                client_factory=MinerUClient,
                parser=parse_mineru,
            )
            raw_dir = None
        else:
            raw_dir = args.raw_dir
            document = parse_mineru(raw_dir)
        rules = load_rules(rules_path)
        summary, details = review_completeness_with_details(document, rules)
        if output_dir.exists() and not output_dir.is_dir():
            raise ValueError(f"输出路径不是目录：{output_dir}")
        output_dir.mkdir(parents=True, exist_ok=True)
        _write_json(output_dir / "mineru_document.json", asdict(document))
        _write_json(
            output_dir / "completeness_results.json",
            [asdict(result) for result in summary.results],
        )
        _write_json(output_dir / "completeness_summary.json", asdict(summary))
        project_facts = build_project_facts(document)
        project_qualification = build_project_qualification(document, project_facts)
        rule_engine_result = run_rule_engine_safe(document, project_facts)
        from .services.semantic_dify import run_semantic_stage

        semantic_result = run_semantic_stage(document, project_facts)
        calculation_result = run_calculation_engine_safe(document, project_facts)
        substantive_review = build_substantive_review(project_qualification, project_facts)
        consistency_review = build_consistency_review(project_facts, document)
        drawing_review = build_drawing_review(
            document, project_facts, job_dir=output_dir
        )
        _write_json(output_dir / "project_facts.json", project_facts)
        _write_json(output_dir / "project_qualification.json", project_qualification)
        _write_json(output_dir / "rule_engine_results.json", rule_engine_result)
        _write_json(output_dir / "semantic_results.json", semantic_result)
        _write_json(output_dir / "calculation_results.json", calculation_result)
        _write_json(output_dir / "substantive_review.json", substantive_review)
        _write_json(output_dir / "consistency_review.json", consistency_review)
        _write_json(output_dir / "drawing_review.json", drawing_review)
        _write_json(
            output_dir / "review_results.json",
            build_review_results(
                project_qualification,
                summary,
                substantive_review,
                consistency_review=consistency_review,
                drawing_review=drawing_review,
                rule_engine=rule_engine_result,
            ),
        )
        (output_dir / "completeness_evidence_check.md").write_text(
            build_evidence_check_markdown(document, summary, details),
            encoding="utf-8",
        )
        # Generate full review report
        try:
            report = build_review_report_from_job_dir(output_dir)
            (output_dir / "review_report.md").write_text(report, encoding="utf-8")
        except Exception:
            pass
    except (OSError, RuntimeError, ValueError) as exc:
        print(f"错误：{exc}", file=sys.stderr)
        return 1

    _print_results(summary.results)
    if args.dify:
        try:
            mode = resolve_dify_completeness_mode(web_enable_dify=True)
            _write_dify_selection(output_dir, summary.results, mode)
            _write_review_comparison_if_ready(output_dir)
            if mode == "off":
                print("Dify 完整性审查模式为 off，跳过 Dify 调用")
                return 0
            _run_dify_review(output_dir, rules)
            _write_review_comparison_if_ready(output_dir)
            _write_review_results_if_ready(output_dir)
        except (OSError, RuntimeError, ValueError) as exc:
            _write_review_comparison_if_ready(output_dir)
            _write_review_results_if_ready(output_dir)
            print(f"Dify 错误：{exc}", file=sys.stderr)
            return 1
    else:
        _write_review_comparison_if_ready(output_dir)
        _write_review_results_if_ready(output_dir)
    return 0


def _run_dify_review(
    output_dir: Path,
    rules: list[dict[str, Any]],
    mode: str | None = None,
    selected_rule_ids: list[str] | None = None,
    progress_callback: Callable[[int, int], None] | None = None,
) -> None:
    """执行 Dify 追加流程，并保证任意阶段失败都留下状态文件。"""
    try:
        _run_dify_review_impl(
            output_dir,
            rules,
            mode=mode,
            selected_rule_ids=selected_rule_ids,
            progress_callback=progress_callback,
        )
    except (OSError, RuntimeError, ValueError) as exc:
        error_path = output_dir / "dify_error.json"
        if not error_path.exists():
            _write_json(
                error_path,
                {
                    "status": "DIFY_FAILED",
                    "message": str(exc),
                    "failed_batch_index": getattr(exc, "batch_index", None),
                },
            )
        raise


def _run_dify_review_impl(
    output_dir: Path,
    rules: list[dict[str, Any]],
    *,
    mode: str | None = None,
    selected_rule_ids: list[str] | None = None,
    progress_callback: Callable[[int, int], None] | None = None,
) -> None:
    """读取已落盘的规范化文档并追加执行 Dify 完整性审查。"""
    from .dify_cache import (
        CACHE_ROOT as DIFY_CACHE_ROOT,
        build_dify_cache_key,
        cache_lock,
        load_cached_rule_result,
        stable_evidence_package_hash,
    )
    from .dify_scheme import (
        DEFAULT_CHARACTER_LIMIT,
        build_dify_scheme_payload,
        build_rule_driven_batches,
        build_rule_evidence_packages,
    )

    started_at = _utc_timestamp()
    started_monotonic = time.perf_counter()
    document_path = output_dir / "mineru_document.json"
    document_data = json.loads(document_path.read_text(encoding="utf-8"))
    task_id = str(document_data.get("document_id") or output_dir.name)
    selection_path = output_dir / "dify_selection.json"
    selection = {}
    if selection_path.is_file():
        selection = json.loads(selection_path.read_text(encoding="utf-8"))
    effective_mode = (mode or selection.get("mode") or "full").strip().lower()
    if effective_mode not in {"off", "on_demand", "full"}:
        raise ValueError(f"DIFY_COMPLETENESS_MODE invalid: {effective_mode}")
    if effective_mode == "off":
        return
    if effective_mode == "on_demand" and selected_rule_ids is None:
        selected_rule_ids = [
            str(value) for value in selection.get("selected_rule_ids", [])
        ]
    package_rule_ids = None if effective_mode == "full" else selected_rule_ids or []
    dify_config = resolve_dify_review_config()
    source_sha256 = _resolve_source_sha256(output_dir, document_data)
    _, overall_metadata = build_dify_scheme_payload(
        document_data,
        character_limit=DEFAULT_CHARACTER_LIMIT,
    )
    packages, config_warnings, fallback_results = build_rule_evidence_packages(
        document_data,
        rules,
        selected_rule_ids=package_rule_ids,
    )
    package_by_id = {str(package["rule_id"]): package for package in packages}
    package_hashes: dict[str, str] = {}
    cache_keys: dict[str, str] = {}
    cached_results: dict[str, dict[str, Any]] = {}
    cache_warnings: list[dict[str, Any]] = []
    for package in packages:
        rule_id = str(package["rule_id"])
        package_hash = stable_evidence_package_hash(package)
        package_hashes[rule_id] = package_hash
        cache_key = build_dify_cache_key(
            source_sha256,
            rule_id,
            package_hash,
            dify_config.workflow_version,
            dify_config.prompt_version,
            dify_config.model_identifier,
            dify_config.output_schema_version,
        )
        cache_keys[rule_id] = cache_key
        if not dify_config.cache_enabled:
            continue
        with cache_lock(cache_key, DIFY_CACHE_ROOT):
            lookup = load_cached_rule_result(
                cache_key=cache_key,
                source_sha256=source_sha256,
                rule_id=rule_id,
                evidence_package_hash=package_hash,
                workflow_version=dify_config.workflow_version,
                prompt_version=dify_config.prompt_version,
                model_identifier=dify_config.model_identifier,
                output_schema_version=dify_config.output_schema_version,
                cache_root=DIFY_CACHE_ROOT,
            )
        if lookup.result is not None:
            cached_results[rule_id] = lookup.result
        elif lookup.warning is not None:
            cache_warnings.append(lookup.warning)
    api_packages = [
        package
        for package in packages
        if str(package["rule_id"]) not in cached_results
    ]
    batches = build_rule_driven_batches(
        api_packages,
        rules,
        task_id,
        character_limit=DEFAULT_CHARACTER_LIMIT,
    )
    cache_hit_rule_ids = [
        str(package["rule_id"])
        for package in packages
        if str(package["rule_id"]) in cached_results
    ]
    cache_miss_rule_ids = [str(package["rule_id"]) for package in api_packages]
    unavailable_rule_ids = [
        str(item.get("rule_id"))
        for item in fallback_results
        if item.get("rule_id")
    ]
    requested_rule_ids = list(
        dict.fromkeys([*cache_hit_rule_ids, *cache_miss_rule_ids])
    )
    selected_ids_for_audit = (
        None
        if effective_mode == "full"
        else list(dict.fromkeys(str(value) for value in (selected_rule_ids or [])))
    )
    per_rule_char_count = {
        str(package["rule_id"]): sum(
            int(item.get("character_count", 0))
            for item in packages
            if str(item.get("rule_id")) == str(package["rule_id"])
        )
        for package in packages
    }
    request_audit = {
        "mode": effective_mode,
        "selected_rule_ids": selected_ids_for_audit,
        "selected_count": (
            len(selected_ids_for_audit)
            if selected_ids_for_audit is not None
            else len(rules)
        ),
        "requested_rule_ids": requested_rule_ids,
        "requested_rule_count": len(requested_rule_ids),
        "total_selected_rules": (
            len(selected_ids_for_audit)
            if selected_ids_for_audit is not None
            else len(rules)
        ),
        "actual_requested_rule_count": len(cache_miss_rule_ids),
        "cache_hit_rule_ids": cache_hit_rule_ids,
        "cache_hit_count": len(cache_hit_rule_ids),
        "cache_miss_rule_ids": cache_miss_rule_ids,
        "cache_miss_count": len(cache_miss_rule_ids),
        "api_requested_rule_ids": cache_miss_rule_ids,
        "api_requested_rule_count": len(cache_miss_rule_ids),
        "unavailable_rule_ids": unavailable_rule_ids,
        "cache_enabled": dify_config.cache_enabled,
        "batch_count": len(batches),
        "per_rule_char_count": per_rule_char_count,
        "total_input_chars": sum(int(batch.get("character_count", 0)) for batch in batches),
        "task_id": task_id,
        "source_sha256": source_sha256,
        "workflow_version": dify_config.workflow_version,
        "prompt_version": dify_config.prompt_version,
        "model_identifier": dify_config.model_identifier,
        "output_schema_version": dify_config.output_schema_version,
        "scheme_text_metadata": overall_metadata,
        "rule_evidence_packages": [
            {
                key: value
                for key, value in package.items()
                if not key.startswith("_")
            }
            for package in packages
        ],
        "warnings": config_warnings,
        "batches": batches,
    }
    _write_json(output_dir / "dify_request.json", request_audit)
    if not batches:
        if cached_results:
            from .services.dify_client import merge_batch_review_results

            expected_rule_ids = list(
                dict.fromkeys([*cache_hit_rule_ids, *unavailable_rule_ids])
            )
            review_result = merge_batch_review_results(
                _cached_result_records(cached_results),
                expected_rule_ids=expected_rule_ids,
                fallback_results=fallback_results,
            )
            review_result["warnings"] = (
                config_warnings + cache_warnings + review_result["warnings"]
            )
            _write_json(output_dir / "dify_review_result.json", review_result)
            _write_review_comparison_if_ready(output_dir, review_result)
            request_audit["status"] = "cache_hit_complete"
            _write_dify_call_audit(
                output_dir,
                _build_dify_call_audit(
                    mode=effective_mode,
                    source_sha256=source_sha256,
                    requested_rule_ids=requested_rule_ids,
                    cache_hit_rule_ids=cache_hit_rule_ids,
                    cache_miss_rule_ids=cache_miss_rule_ids,
                    api_requested_rule_ids=[],
                    batch_count=0,
                    per_rule_input_chars=per_rule_char_count,
                    total_input_chars=0,
                    config=dify_config,
                    started_at=started_at,
                    started_monotonic=started_monotonic,
                    status="cache_hit_complete",
                    warnings=config_warnings + cache_warnings,
                ),
            )
        else:
            request_audit["status"] = "skipped"
            request_audit["skip_reason"] = "selected_count=0 或未生成可用证据包"
        _write_json(output_dir / "dify_request.json", request_audit)
        if not cached_results:
            _write_dify_call_audit(
                output_dir,
                _build_dify_call_audit(
                    mode=effective_mode,
                    source_sha256=source_sha256,
                    requested_rule_ids=requested_rule_ids,
                    cache_hit_rule_ids=cache_hit_rule_ids,
                    cache_miss_rule_ids=cache_miss_rule_ids,
                    api_requested_rule_ids=[],
                    batch_count=0,
                    per_rule_input_chars=per_rule_char_count,
                    total_input_chars=0,
                    config=dify_config,
                    started_at=started_at,
                    started_monotonic=started_monotonic,
                    status="skipped",
                    warnings=config_warnings + cache_warnings,
                ),
            )
        return
    try:
        if progress_callback is not None:
            progress_callback(0, len(batches))
        raw_records, parsed_records = asyncio.run(
            _execute_dify_batches(
                batches, task_id, output_dir, progress_callback=progress_callback
            )
        )
        from .services.dify_client import merge_batch_review_results

        oversized_rule_ids = {
            str(batch["oversized_rule_part"]["rule_id"])
            for batch in batches
            if "oversized_rule_part" in batch
        }
        all_parsed_records = [
            *_cached_result_records(cached_results),
            *parsed_records,
        ]
        expected_rule_ids = list(
            dict.fromkeys([*cache_hit_rule_ids, *requested_rule_ids])
        )
        expected_rule_ids.extend(
            str(item.get("rule_id"))
            for item in fallback_results
            if str(item.get("rule_id")) not in expected_rule_ids
        )
        review_result = merge_batch_review_results(
            all_parsed_records,
            expected_rule_ids=expected_rule_ids,
            fallback_results=fallback_results,
            oversized_rule_ids=oversized_rule_ids,
        )
        cache_write_warnings = _cache_successful_rule_results(
            review_result.get("results", []),
            api_rule_ids=set(cache_miss_rule_ids),
            package_by_id=package_by_id,
            package_hashes=package_hashes,
            cache_keys=cache_keys,
            source_sha256=source_sha256,
            config=dify_config,
            duration_ms=int((time.perf_counter() - started_monotonic) * 1000),
        )
        review_result["warnings"] = (
            config_warnings
            + cache_warnings
            + [warning for batch in parsed_records for warning in batch.get("warnings", [])]
            + cache_write_warnings
            + review_result["warnings"]
        )
        _write_json(
            output_dir / "dify_raw_response.json",
            {"task_id": task_id, "batches": raw_records},
        )
        _write_json(output_dir / "dify_review_result.json", review_result)
        _write_review_comparison_if_ready(output_dir, review_result)
        (output_dir / "dify_error.json").unlink(missing_ok=True)
        status = "partial_cache_hit" if cache_hit_rule_ids else "api_success"
        request_audit["status"] = status
        _write_json(output_dir / "dify_request.json", request_audit)
        _write_dify_call_audit(
            output_dir,
            _build_dify_call_audit(
                mode=effective_mode,
                source_sha256=source_sha256,
                requested_rule_ids=requested_rule_ids,
                cache_hit_rule_ids=cache_hit_rule_ids,
                cache_miss_rule_ids=cache_miss_rule_ids,
                api_requested_rule_ids=cache_miss_rule_ids,
                batch_count=len(batches),
                per_rule_input_chars=per_rule_char_count,
                total_input_chars=request_audit["total_input_chars"],
                config=dify_config,
                started_at=started_at,
                started_monotonic=started_monotonic,
                status=status,
                warnings=(
                    config_warnings
                    + cache_warnings
                    + cache_write_warnings
                    + [
                        warning
                        for batch in parsed_records
                        for warning in batch.get("warnings", [])
                    ]
                ),
            ),
        )
    except Exception as exc:
        from .services.dify_client import DifyError

        if not isinstance(exc, (DifyError, OSError, RuntimeError, ValueError)):
            raise
        partial_raw_records = getattr(exc, "partial_raw_records", [])
        partial_parsed_records = getattr(exc, "partial_parsed_records", [])
        if partial_raw_records:
            _write_json(
                output_dir / "dify_raw_response.json",
                {"task_id": task_id, "batches": partial_raw_records},
            )
        partial_result_ids = _parsed_rule_ids(partial_parsed_records)
        partial_cache_warnings = _cache_successful_rule_results(
            [
                result
                for batch in partial_parsed_records
                for result in _result_items(batch.get("result"))
            ],
            api_rule_ids=partial_result_ids,
            package_by_id=package_by_id,
            package_hashes=package_hashes,
            cache_keys=cache_keys,
            source_sha256=source_sha256,
            config=dify_config,
            duration_ms=int((time.perf_counter() - started_monotonic) * 1000),
            oversized_rule_ids={
                str(batch["oversized_rule_part"]["rule_id"])
                for batch in batches
                if "oversized_rule_part" in batch
            },
        )
        failed_rule_ids = [
            rule_id
            for rule_id in cache_miss_rule_ids
            if rule_id not in partial_result_ids
        ]
        oversized_rule_ids = {
            str(batch["oversized_rule_part"]["rule_id"])
            for batch in batches
            if "oversized_rule_part" in batch
        }
        partial_items = [
            result
            for batch in partial_parsed_records
            for result in _result_items(batch.get("result"))
            if str(result.get("rule_id", "")) not in oversized_rule_ids
        ]
        partial_item_ids = list(
            dict.fromkeys(
                [
                    *cache_hit_rule_ids,
                    *[
                        str(item.get("rule_id"))
                        for item in partial_items
                        if item.get("rule_id")
                    ],
                ]
            )
        )
        if partial_item_ids:
            from .services.dify_client import merge_batch_review_results

            partial_review = merge_batch_review_results(
                [
                    *_cached_result_records(cached_results),
                    *[
                        {
                            "batch_index": 0,
                            "rule_ids": [str(item["rule_id"])],
                            "result": {"results": [item]},
                        }
                        for item in partial_items
                    ],
                ],
                expected_rule_ids=partial_item_ids,
            )
            partial_review["partial"] = True
            partial_review["failed_rule_ids"] = failed_rule_ids
            partial_review["warnings"] = (
                config_warnings + cache_warnings + partial_cache_warnings
            )
            _write_json(output_dir / "dify_review_result.json", partial_review)
        error_data = {
            "status": "DIFY_FAILED",
            "message": str(exc),
            "failed_batch_index": getattr(exc, "batch_index", None),
        }
        error_details = _safe_error_details(exc)
        if error_details:
            error_data["technical_details"] = error_details
        _write_json(output_dir / "dify_error.json", error_data)
        request_audit["status"] = (
            "partial_api_failure" if partial_result_ids else "api_failed"
        )
        _write_json(output_dir / "dify_request.json", request_audit)
        _write_dify_call_audit(
            output_dir,
            _build_dify_call_audit(
                mode=effective_mode,
                source_sha256=source_sha256,
                requested_rule_ids=requested_rule_ids,
                cache_hit_rule_ids=cache_hit_rule_ids,
                cache_miss_rule_ids=cache_miss_rule_ids,
                api_requested_rule_ids=cache_miss_rule_ids,
                batch_count=len(batches),
                per_rule_input_chars=per_rule_char_count,
                total_input_chars=request_audit["total_input_chars"],
                config=dify_config,
                started_at=started_at,
                started_monotonic=started_monotonic,
                status=(
                    "partial_api_failure" if partial_result_ids else "api_failed"
                ),
                warnings=config_warnings + cache_warnings + partial_cache_warnings,
                error_summary=_safe_error_summary(exc),
                error_details=error_details,
                failed_rule_ids=failed_rule_ids,
            ),
        )
        raise RuntimeError(str(exc)) from exc


async def _execute_dify_batches(
    batches: list[dict[str, Any]],
    task_id: str,
    output_dir: Path,
    *,
    progress_callback: Callable[[int, int], None] | None = None,
) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    """并发执行批次（并发数 DIFY_COMPLETENESS_CONCURRENCY，默认 3）；失败时已完成的原始响应仍会落盘。

    错误语义与串行版一致：任一批次失败时，等待进行中的批次收尾后抛出首个错误
    （携带 batch_index 与已完成的部分记录），尚未开始的批次不再发起。
    """
    from .services.dify_client import (
        DifyClient,
        DifyError,
        extract_review_result,
        validate_review_result_with_warnings,
    )

    raw_records: list[dict[str, Any]] = []
    parsed_records: list[dict[str, Any]] = []
    if not batches:
        return raw_records, parsed_records

    try:
        concurrency = max(1, int(os.getenv("DIFY_COMPLETENESS_CONCURRENCY", "3")))
    except ValueError:
        concurrency = 3
    client = DifyClient.from_env()
    semaphore = asyncio.Semaphore(concurrency)
    lock = asyncio.Lock()
    total = len(batches)
    first_error: list[DifyError] = []

    def _flush_raw_locked() -> None:
        raw_records.sort(key=lambda item: int(item["batch_index"]))
        _write_json(
            output_dir / "dify_raw_response.json",
            {"task_id": task_id, "batches": raw_records},
        )

    async def run_batch(batch: dict[str, Any]) -> None:
        if first_error:
            return
        batch_index = int(batch["batch_index"])
        try:
            async with semaphore:
                raw_response = await client.run_workflow(
                    batch["inputs"],
                    user=task_id,
                )
            parsed_result, validation_warnings = validate_review_result_with_warnings(
                extract_review_result(raw_response),
                batch["rule_ids"],
                allow_unrequested=True,
            )
        except DifyError as exc:
            async with lock:
                if exc.raw_response is not None:
                    raw_records.append(
                        {
                            "batch_index": batch_index,
                            "rule_ids": batch["rule_ids"],
                            "response": exc.raw_response,
                        }
                    )
                    _flush_raw_locked()
                exc.batch_index = batch_index
                exc.partial_raw_records = list(raw_records)
                exc.partial_parsed_records = list(parsed_records)
                first_error.append(exc)
                if progress_callback is not None:
                    progress_callback(len(raw_records), total)
            return
        async with lock:
            raw_records.append(
                {
                    "batch_index": batch_index,
                    "rule_ids": batch["rule_ids"],
                    "response": raw_response,
                }
            )
            _flush_raw_locked()
            parsed_records.append(
                {
                    "batch_index": batch_index,
                    "rule_ids": batch["rule_ids"],
                    "result": parsed_result,
                    "warnings": validation_warnings,
                }
            )
            parsed_records.sort(key=lambda item: int(item["batch_index"]))
            done = len(parsed_records)
        if progress_callback is not None:
            progress_callback(done, total)

    await asyncio.gather(*(run_batch(batch) for batch in batches))
    if first_error:
        raise first_error[0]
    return raw_records, parsed_records


def _resolve_source_sha256(
    output_dir: Path,
    document_data: dict[str, Any],
) -> str:
    status_path = output_dir / "status.json"
    if status_path.is_file():
        try:
            status = json.loads(status_path.read_text(encoding="utf-8"))
            if isinstance(status, dict) and str(status.get("source_sha256", "")).strip():
                return str(status["source_sha256"]).strip()
        except (OSError, json.JSONDecodeError):
            pass
    for key in ("source_sha256", "document_id"):
        value = str(document_data.get(key, "")).strip()
        if value:
            return value
    return output_dir.name


def _utc_timestamp() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def _cached_result_records(
    cached_results: dict[str, dict[str, Any]],
) -> list[dict[str, Any]]:
    return [
        {
            "batch_index": 0,
            "rule_ids": [rule_id],
            "result": {"results": [result]},
            "warnings": [],
        }
        for rule_id, result in cached_results.items()
    ]


def _result_items(value: Any) -> list[dict[str, Any]]:
    if isinstance(value, list):
        items = value
    elif isinstance(value, dict) and isinstance(value.get("results"), list):
        items = value["results"]
    elif isinstance(value, dict) and value.get("rule_id"):
        items = [value]
    else:
        return []
    return [item for item in items if isinstance(item, dict)]


def _parsed_rule_ids(parsed_batches: list[dict[str, Any]]) -> set[str]:
    return {
        str(result.get("rule_id")).strip()
        for batch in parsed_batches
        for result in _result_items(batch.get("result"))
        if str(result.get("rule_id", "")).strip()
    }


def _cache_successful_rule_results(
    results: list[dict[str, Any]],
    *,
    api_rule_ids: set[str],
    package_by_id: dict[str, dict[str, Any]],
    package_hashes: dict[str, str],
    cache_keys: dict[str, str],
    source_sha256: str,
    config: DifyReviewConfig,
    duration_ms: int,
    oversized_rule_ids: set[str] | None = None,
) -> list[dict[str, Any]]:
    if not config.cache_enabled:
        return []
    from .dify_cache import CACHE_ROOT as DIFY_CACHE_ROOT, cache_lock, save_cached_rule_result

    warnings: list[dict[str, Any]] = []
    skipped_oversized = oversized_rule_ids or set()
    for result in results:
        rule_id = str(result.get("rule_id", "")).strip()
        if (
            not rule_id
            or rule_id not in api_rule_ids
            or rule_id in skipped_oversized
            or rule_id not in package_by_id
        ):
            continue
        package = package_by_id[rule_id]
        try:
            with cache_lock(cache_keys[rule_id], DIFY_CACHE_ROOT):
                save_cached_rule_result(
                    cache_key=cache_keys[rule_id],
                    source_sha256=source_sha256,
                    rule_id=rule_id,
                    evidence_package_hash=package_hashes[rule_id],
                    workflow_version=config.workflow_version,
                    prompt_version=config.prompt_version,
                    model_identifier=config.model_identifier,
                    output_schema_version=config.output_schema_version,
                    result=result,
                    input_chars=int(package.get("character_count", 0)),
                    duration_ms=duration_ms,
                    cache_root=DIFY_CACHE_ROOT,
                )
        except (OSError, RuntimeError, ValueError) as exc:
            warnings.append(
                {
                    "code": "DIFY_CACHE_WRITE_WARNING",
                    "rule_id": rule_id,
                    "message": _safe_error_summary(exc),
                }
            )
    return warnings


def _build_dify_call_audit(
    *,
    mode: str,
    source_sha256: str,
    requested_rule_ids: list[str],
    cache_hit_rule_ids: list[str],
    cache_miss_rule_ids: list[str],
    api_requested_rule_ids: list[str],
    batch_count: int,
    per_rule_input_chars: dict[str, int],
    total_input_chars: int,
    config: DifyReviewConfig,
    started_at: str,
    started_monotonic: float,
    status: str,
    warnings: list[dict[str, Any]],
    error_summary: str | None = None,
    error_details: dict[str, Any] | None = None,
    failed_rule_ids: list[str] | None = None,
) -> dict[str, Any]:
    return {
        "mode": mode,
        "source_sha256": source_sha256,
        "requested_rule_ids": requested_rule_ids,
        "requested_rule_count": len(requested_rule_ids),
        "cache_hit_rule_ids": cache_hit_rule_ids,
        "cache_hit_count": len(cache_hit_rule_ids),
        "cache_miss_rule_ids": cache_miss_rule_ids,
        "cache_miss_count": len(cache_miss_rule_ids),
        "api_requested_rule_ids": api_requested_rule_ids,
        "api_requested_rule_count": len(api_requested_rule_ids),
        "batch_count": batch_count,
        "per_rule_input_chars": per_rule_input_chars,
        "total_input_chars": total_input_chars,
        "workflow_version": config.workflow_version,
        "prompt_version": config.prompt_version,
        "model_identifier": config.model_identifier,
        "output_schema_version": config.output_schema_version,
        "started_at": started_at,
        "finished_at": _utc_timestamp(),
        "duration_ms": max(0, int((time.perf_counter() - started_monotonic) * 1000)),
        "status": status,
        "warnings": warnings,
        "error_summary": error_summary,
        "error_details": error_details,
        "failed_rule_ids": failed_rule_ids or [],
    }


def _write_dify_call_audit(output_dir: Path, audit: dict[str, Any]) -> None:
    _write_json(output_dir / "dify_call_audit.json", audit)


def _safe_error_summary(error: Exception | str) -> str:
    value = str(error)
    value = re.sub(r"(?i)bearer\s+\S+", "Bearer [redacted]", value)
    value = re.sub(r"https?://\S+", "[url redacted]", value)
    return value[:300]


def _safe_error_details(error: Exception | str) -> dict[str, Any] | None:
    details = getattr(error, "technical_details", None)
    if not isinstance(details, dict):
        return None
    sanitized: dict[str, Any] = {}
    for key, value in details.items():
        if isinstance(value, str):
            value = re.sub(r"(?i)bearer\s+\S+", "Bearer [redacted]", value)
            value = re.sub(r"https?://\S+", "[url redacted]", value)
            value = value[:500]
        sanitized[str(key)] = value
    return sanitized or None


def _write_json(path: Path, data: Any) -> None:
    path.write_text(
        json.dumps(data, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )


def _write_review_comparison_if_ready(
    output_dir: Path,
    dify_review_result: dict[str, Any] | None = None,
) -> None:
    local_path = output_dir / "completeness_results.json"
    if not local_path.is_file():
        return
    from .review_comparison import build_review_comparison

    local_results = json.loads(local_path.read_text(encoding="utf-8"))
    if dify_review_result is None:
        dify_path = output_dir / "dify_review_result.json"
        if dify_path.is_file():
            dify_review_result = json.loads(dify_path.read_text(encoding="utf-8"))
    selection = _read_optional_json(output_dir / "dify_selection.json")
    audit = _read_optional_json(output_dir / "dify_call_audit.json")
    dify_error = _read_optional_json(output_dir / "dify_error.json")
    comparison = build_review_comparison(
        local_results,
        dify_review_result,
        selection=selection,
        audit=audit,
        dify_error=dify_error,
    )
    _write_json(output_dir / "review_comparison.json", comparison)


def _write_review_results_if_ready(output_dir: Path) -> None:
    required = [
        output_dir / "project_qualification.json",
        output_dir / "completeness_summary.json",
        output_dir / "substantive_review.json",
    ]
    if not all(path.is_file() for path in required):
        return
    project_qualification = json.loads(required[0].read_text(encoding="utf-8"))
    completeness = json.loads(required[1].read_text(encoding="utf-8"))
    substantive = json.loads(required[2].read_text(encoding="utf-8"))
    consistency = _read_optional_json_list(output_dir / "consistency_review.json")
    drawing = _read_optional_json_list(output_dir / "drawing_review.json")
    comparison = _read_optional_json(output_dir / "review_comparison.json")
    _write_json(
        output_dir / "review_results.json",
        build_review_results(
            project_qualification,
            completeness,
            substantive,
            comparison=comparison,
            consistency_review=consistency,
            drawing_review=drawing,
        ),
    )


def _read_optional_json(path: Path) -> dict[str, Any] | None:
    if not path.is_file():
        return None
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return None
    return value if isinstance(value, dict) else None


def _read_optional_json_list(path: Path) -> list[dict[str, Any]] | None:
    if not path.is_file():
        return None
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return None
    if not isinstance(value, list):
        return None
    return [item for item in value if isinstance(item, dict)]


def _write_dify_selection(
    output_dir: Path,
    local_results: list[Any],
    mode: str,
) -> None:
    selection = select_rules_for_dify_review(local_results, mode)  # type: ignore[arg-type]
    _write_json(output_dir / "dify_selection.json", selection)


def _print_results(results: list[Any]) -> None:
    print("规则编号 | 检查项 | 状态 | 页码 | 人工复核")
    for result in results:
        pages = sorted(
            {item.physical_page for item in result.evidence}
        )
        page_text = ",".join(str(page) for page in pages) if pages else "-"
        human_review = "是" if result.requires_human_review else "否"
        print(
            f"{result.rule_id} | {result.name} | {result.status} | "
            f"{page_text} | {human_review}"
        )


if __name__ == "__main__":
    raise SystemExit(main())
