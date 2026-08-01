"""项目命令行入口。"""

from __future__ import annotations

import argparse
import asyncio
import json
import sys
from dataclasses import asdict
from pathlib import Path
from typing import Any

from .completeness_review import (
    build_evidence_check_markdown,
    load_rules,
    review_completeness_with_details,
)
from .completeness_review_selector import select_rules_for_dify_review
from .dify_config import resolve_dify_completeness_mode
from .mineru_client import MinerUClient
from .mineru_parser import parse_mineru


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
            client = MinerUClient()
            raw_dir = client.parse_pdf(
                pdf_path=args.pdf,
                output_dir=Path(args.output_dir) / "mineru_api",
            )
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
        (output_dir / "completeness_evidence_check.md").write_text(
            build_evidence_check_markdown(document, summary, details),
            encoding="utf-8",
        )
    except (OSError, RuntimeError, ValueError) as exc:
        print(f"错误：{exc}", file=sys.stderr)
        return 1

    _print_results(summary.results)
    if args.dify:
        try:
            mode = resolve_dify_completeness_mode(web_enable_dify=True)
            _write_dify_selection(output_dir, summary.results, mode)
            if mode == "off":
                print("Dify 完整性审查模式为 off，跳过 Dify 调用")
                return 0
            _run_dify_review(output_dir, rules)
        except (OSError, RuntimeError, ValueError) as exc:
            print(f"Dify 错误：{exc}", file=sys.stderr)
            return 1
    return 0


def _run_dify_review(
    output_dir: Path,
    rules: list[dict[str, Any]],
    mode: str | None = None,
    selected_rule_ids: list[str] | None = None,
) -> None:
    """执行 Dify 追加流程，并保证任意阶段失败都留下状态文件。"""
    try:
        _run_dify_review_impl(
            output_dir,
            rules,
            mode=mode,
            selected_rule_ids=selected_rule_ids,
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
) -> None:
    """读取已落盘的规范化文档并追加执行 Dify 完整性审查。"""
    from .dify_scheme import (
        DEFAULT_CHARACTER_LIMIT,
        build_dify_scheme_payload,
        build_rule_driven_batches,
        build_rule_evidence_packages,
    )

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
    _, overall_metadata = build_dify_scheme_payload(
        document_data,
        character_limit=DEFAULT_CHARACTER_LIMIT,
    )
    packages, config_warnings, fallback_results = build_rule_evidence_packages(
        document_data,
        rules,
        selected_rule_ids=package_rule_ids,
    )
    batches = build_rule_driven_batches(
        packages,
        rules,
        task_id,
        character_limit=DEFAULT_CHARACTER_LIMIT,
    )
    requested_rule_ids = list(
        dict.fromkeys(
            str(rule_id)
            for batch in batches
            for rule_id in batch.get("rule_ids", [])
        )
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
        "total_selected_rules": (
            len(selected_ids_for_audit)
            if selected_ids_for_audit is not None
            else len(rules)
        ),
        "actual_requested_rule_count": len(requested_rule_ids),
        "batch_count": len(batches),
        "per_rule_char_count": per_rule_char_count,
        "total_input_chars": sum(int(batch.get("character_count", 0)) for batch in batches),
        "task_id": task_id,
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
        request_audit["status"] = "skipped"
        request_audit["skip_reason"] = "selected_count=0 或未生成可用证据包"
        _write_json(output_dir / "dify_request.json", request_audit)
        return
    try:
        raw_records, parsed_records = asyncio.run(
            _execute_dify_batches(batches, task_id, output_dir)
        )
        from .services.dify_client import merge_batch_review_results

        oversized_rule_ids = {
            str(batch["oversized_rule_part"]["rule_id"])
            for batch in batches
            if "oversized_rule_part" in batch
        }
        expected_rule_ids = list(requested_rule_ids)
        expected_rule_ids.extend(
            str(item.get("rule_id"))
            for item in fallback_results
            if str(item.get("rule_id")) not in expected_rule_ids
        )
        review_result = merge_batch_review_results(
            parsed_records,
            expected_rule_ids=expected_rule_ids,
            fallback_results=fallback_results,
            oversized_rule_ids=oversized_rule_ids,
        )
        review_result["warnings"] = (
            config_warnings
            + [warning for batch in parsed_records for warning in batch.get("warnings", [])]
            + review_result["warnings"]
        )
        _write_json(
            output_dir / "dify_raw_response.json",
            {"task_id": task_id, "batches": raw_records},
        )
        _write_json(output_dir / "dify_review_result.json", review_result)
        _write_review_comparison_if_ready(output_dir, review_result)
        (output_dir / "dify_error.json").unlink(missing_ok=True)
    except Exception as exc:
        from .services.dify_client import DifyError

        if not isinstance(exc, (DifyError, OSError, RuntimeError, ValueError)):
            raise
        error_data = {
            "status": "DIFY_FAILED",
            "message": str(exc),
            "failed_batch_index": getattr(exc, "batch_index", None),
        }
        _write_json(output_dir / "dify_error.json", error_data)
        raise RuntimeError(str(exc)) from exc


async def _execute_dify_batches(
    batches: list[dict[str, Any]],
    task_id: str,
    output_dir: Path,
) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    """顺序执行批次；失败前已完成的原始响应仍会落盘。"""
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
    client = DifyClient.from_env()
    for batch in batches:
        batch_index = int(batch["batch_index"])
        try:
            raw_response = await client.run_workflow(
                batch["inputs"],
                user=task_id,
            )
            raw_records.append(
                {
                    "batch_index": batch_index,
                    "rule_ids": batch["rule_ids"],
                    "response": raw_response,
                }
            )
            _write_json(
                output_dir / "dify_raw_response.json",
                {"task_id": task_id, "batches": raw_records},
            )
            parsed_result, validation_warnings = validate_review_result_with_warnings(
                extract_review_result(raw_response),
                batch["rule_ids"],
                allow_unrequested=True,
            )
            parsed_records.append(
                {
                    "batch_index": batch_index,
                    "rule_ids": batch["rule_ids"],
                    "result": parsed_result,
                    "warnings": validation_warnings,
                }
            )
        except DifyError as exc:
            if exc.raw_response is not None:
                raw_records.append(
                    {
                        "batch_index": batch_index,
                        "rule_ids": batch["rule_ids"],
                        "response": exc.raw_response,
                    }
                )
                _write_json(
                    output_dir / "dify_raw_response.json",
                    {"task_id": task_id, "batches": raw_records},
                )
            exc.batch_index = batch_index
            raise
    return raw_records, parsed_records


def _write_json(path: Path, data: Any) -> None:
    path.write_text(
        json.dumps(data, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )


def _write_review_comparison_if_ready(
    output_dir: Path,
    dify_review_result: dict[str, Any],
) -> None:
    local_path = output_dir / "completeness_results.json"
    if not local_path.is_file():
        return
    from .review_comparison import build_review_comparison

    local_results = json.loads(local_path.read_text(encoding="utf-8"))
    comparison = build_review_comparison(local_results, dify_review_result)
    _write_json(output_dir / "review_comparison.json", comparison)


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
