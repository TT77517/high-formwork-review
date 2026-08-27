from __future__ import annotations

import re
import sys
import unicodedata
from dataclasses import dataclass
from pathlib import Path

import pdfplumber
from pypdf import PdfReader


DEFAULT_INPUT_DIR = Path("/Users/admin/Desktop/jisuan")
DEFAULT_OUTPUT_DIR = Path(__file__).resolve().parents[1] / "rule" / "source_md"


@dataclass
class PdfExtraction:
    path: Path
    page_count: int
    pages: list[str]
    method: str
    status: str
    reason: str


def main() -> int:
    input_dir = Path(sys.argv[1]) if len(sys.argv) > 1 else DEFAULT_INPUT_DIR
    output_dir = Path(sys.argv[2]) if len(sys.argv) > 2 else DEFAULT_OUTPUT_DIR
    output_dir.mkdir(parents=True, exist_ok=True)

    pdfs = sorted(input_dir.glob("*.pdf"))
    if not pdfs:
        print(f"No PDFs found in {input_dir}", file=sys.stderr)
        return 1

    results = [extract_pdf(pdf) for pdf in pdfs]
    for result in results:
        write_markdown(result, output_dir)
    write_index(results, input_dir, output_dir)
    print(f"Wrote {len(results)} markdown files to {output_dir}")
    return 0


def extract_pdf(path: Path) -> PdfExtraction:
    pypdf_pages, page_count = extract_with_pypdf(path)
    pypdf_score = quality_score(pypdf_pages)
    if pypdf_score >= 0.2 and has_enough_text_coverage(pypdf_pages, page_count):
        return PdfExtraction(
            path=path,
            page_count=page_count,
            pages=pypdf_pages,
            method="pypdf",
            status="TEXT_EXTRACTED",
            reason=f"CJK quality score {pypdf_score:.2f}",
        )

    plumber_pages, plumber_count = extract_with_pdfplumber(path)
    plumber_score = quality_score(plumber_pages)
    if plumber_score >= 0.2 and has_enough_text_coverage(plumber_pages, plumber_count):
        return PdfExtraction(
            path=path,
            page_count=plumber_count or page_count,
            pages=plumber_pages,
            method="pdfplumber",
            status="TEXT_EXTRACTED",
            reason=f"CJK quality score {plumber_score:.2f}",
        )

    reason = (
        "No extractable Chinese text found"
        if max(pypdf_score, plumber_score) == 0
        else (
            "Extracted text appears garbled or only contains repeated watermark/header text; "
            f"best CJK quality score {max(pypdf_score, plumber_score):.2f}"
        )
    )
    return PdfExtraction(
        path=path,
        page_count=plumber_count or page_count,
        pages=best_pages(pypdf_pages, plumber_pages),
        method="pypdf/pdfplumber",
        status="OCR_REQUIRED",
        reason=reason,
    )


def extract_with_pypdf(path: Path) -> tuple[list[str], int]:
    reader = PdfReader(str(path))
    pages: list[str] = []
    for page in reader.pages:
        try:
            pages.append(clean_text(page.extract_text() or ""))
        except Exception:
            pages.append("")
    return pages, len(reader.pages)


def extract_with_pdfplumber(path: Path) -> tuple[list[str], int]:
    pages: list[str] = []
    with pdfplumber.open(str(path)) as pdf:
        for page in pdf.pages:
            try:
                pages.append(clean_text(page.extract_text() or ""))
            except Exception:
                pages.append("")
        return pages, len(pdf.pages)


def clean_text(text: str) -> str:
    text = unicodedata.normalize("NFKC", text)
    text = text.replace("\r\n", "\n").replace("\r", "\n")
    text = re.sub(r"[ \t]+", " ", text)
    text = re.sub(r"\n{3,}", "\n\n", text)
    return text.strip()


def quality_score(pages: list[str]) -> float:
    text = "\n".join(remove_repeated_watermark_lines(pages))
    compact = re.sub(r"\s+", "", text)
    if len(compact) < 200:
        return 0.0
    cjk = sum(1 for char in compact if "\u4e00" <= char <= "\u9fff")
    return cjk / max(len(compact), 1)


def has_enough_text_coverage(pages: list[str], page_count: int) -> bool:
    body_pages = remove_repeated_watermark_lines(pages)
    body_text = "\n".join(body_pages)
    nonempty_pages = sum(1 for page in body_pages if len(re.sub(r"\s+", "", page)) >= 80)
    avg_chars = len(re.sub(r"\s+", "", body_text)) / max(page_count, 1)
    return nonempty_pages >= max(2, int(page_count * 0.25)) and avg_chars >= 180


def remove_repeated_watermark_lines(pages: list[str]) -> list[str]:
    watermark = "开公息信部设建用乡专城览房浏住"
    cleaned = []
    for page in pages:
        chars = re.sub(r"\s+", "", page)
        if chars and set(chars) <= set(watermark) and len(chars) <= 80:
            cleaned.append("")
            continue
        cleaned.append(page)
    return cleaned


def best_pages(first: list[str], second: list[str]) -> list[str]:
    return first if len("\n".join(first)) >= len("\n".join(second)) else second


def write_markdown(result: PdfExtraction, output_dir: Path) -> None:
    md_path = output_dir / f"{safe_stem(result.path)}.md"
    lines = [
        f"# {result.path.stem}",
        "",
        "## Extraction Metadata",
        "",
        f"- Source PDF: `{result.path}`",
        f"- Pages: {result.page_count}",
        f"- Status: {result.status}",
        f"- Method: {result.method}",
        f"- Reason: {result.reason}",
        "",
    ]
    if result.status == "OCR_REQUIRED":
        lines.extend([
            "## OCR Required",
            "",
            "This PDF has no reliable embedded Chinese text or the embedded text is garbled.",
            "Run OCR before using it as a source for rule extraction.",
            "",
        ])
        sample = first_nonempty(result.pages)
        if sample:
            lines.extend(["## Extracted Sample For Diagnosis", "", fence(sample[:2000]), ""])
    else:
        lines.extend(["## Extracted Text", ""])
        for index, text in enumerate(result.pages, start=1):
            lines.append(f"### Page {index}")
            lines.append("")
            lines.append(text or "_No extractable text on this page._")
            lines.append("")

    md_path.write_text("\n".join(lines), encoding="utf-8")


def write_index(results: list[PdfExtraction], input_dir: Path, output_dir: Path) -> None:
    lines = [
        "# 规范 PDF 转 Markdown 索引",
        "",
        f"- Source directory: `{input_dir}`",
        f"- Output directory: `{output_dir}`",
        "",
        "| 文件 | 页数 | 状态 | 方法 | 说明 |",
        "| --- | ---: | --- | --- | --- |",
    ]
    for result in results:
        md_name = f"{safe_stem(result.path)}.md"
        lines.append(
            f"| [{result.path.name}](./{md_name}) | {result.page_count} | "
            f"{result.status} | {result.method} | {result.reason} |"
        )

    ocr_required = [result.path.name for result in results if result.status == "OCR_REQUIRED"]
    lines.extend(["", "## OCR Required", ""])
    if ocr_required:
        lines.extend(f"- {name}" for name in ocr_required)
    else:
        lines.append("- None")

    (output_dir / "INDEX.md").write_text("\n".join(lines) + "\n", encoding="utf-8")


def safe_stem(path: Path) -> str:
    stem = path.stem.strip()
    stem = re.sub(r"[\\/:*?\"<>|]+", "_", stem)
    return stem


def first_nonempty(pages: list[str]) -> str:
    for page in pages:
        if page.strip():
            return page.strip()
    return ""


def fence(text: str) -> str:
    return "```text\n" + text.replace("```", "'''") + "\n```"


if __name__ == "__main__":
    raise SystemExit(main())
