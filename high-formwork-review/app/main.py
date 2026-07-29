"""项目命令行入口。"""

from __future__ import annotations

import argparse
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
    return 0


def _write_json(path: Path, data: Any) -> None:
    path.write_text(
        json.dumps(data, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )


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
