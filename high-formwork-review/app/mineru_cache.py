"""缓存 MinerU PDF 解析结果，避免相同文件重复调用远端服务。"""

from __future__ import annotations

import hashlib
import json
import os
import re
import shutil
import tempfile
import threading
from contextlib import contextmanager
from dataclasses import asdict, dataclass, replace
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Callable, Iterator

from dotenv import load_dotenv

from .mineru_client import MinerUClient
from .mineru_parser import parse_mineru
from .models import (
    BoundingBox,
    MinerUBlock,
    MinerUDocument,
    MinerUPage,
    MinerUSection,
)


PROJECT_ROOT = Path(__file__).resolve().parent.parent
load_dotenv(PROJECT_ROOT / ".env")
DATA_ROOT = Path(os.getenv("DATA_ROOT", PROJECT_ROOT / "data")).expanduser()
if not DATA_ROOT.is_absolute():
    DATA_ROOT = PROJECT_ROOT / DATA_ROOT
CACHE_ROOT = DATA_ROOT / "cache" / "mineru"
PARSER_NAME = "app.mineru_parser.parse_mineru"
PARSER_VERSION = "mineru-parser-v1"
PARSER_CONFIG_VERSION = "mineru-config-v1"
MAX_MINERU_PDF_PAGES = 200
PDF_CHUNK_SIZE = 180
_CACHE_KEY_SAFE = re.compile(r"[^A-Za-z0-9_.-]+")
_LOCKS: dict[str, threading.Lock] = {}
_LOCKS_GUARD = threading.Lock()


@dataclass(frozen=True)
class ParseCacheInfo:
    source_sha256: str
    cache_key: str
    cache_hit: bool
    cache_source: str
    parser_version: str
    parser_config_version: str
    warning: str | None = None


@dataclass(frozen=True)
class PdfPart:
    path: Path
    start_page: int
    page_count: int


def sha256_file(path: str | Path) -> str:
    source_path = Path(path)
    digest = hashlib.sha256()
    with source_path.open("rb") as source:
        while chunk := source.read(1024 * 1024):
            digest.update(chunk)
    return digest.hexdigest()


def build_cache_key(
    source_sha256: str,
    parser_version: str = PARSER_VERSION,
    parser_config_version: str = PARSER_CONFIG_VERSION,
) -> str:
    """Build a readable, path-safe key from file and parser versions."""
    if not source_sha256 or not re.fullmatch(r"[0-9a-f]{64}", source_sha256):
        raise ValueError("source_sha256 must be a SHA-256 hex digest")
    return "-".join(
        (
            source_sha256,
            _safe_component(parser_version),
            _safe_component(parser_config_version),
        )
    )


def cache_directory(
    cache_key: str,
    cache_root: str | Path = CACHE_ROOT,
) -> Path:
    if not cache_key or Path(cache_key).name != cache_key or ".." in cache_key:
        raise ValueError("cache_key is invalid")
    return Path(cache_root) / cache_key


def parse_pdf_with_cache(
    pdf_path: str | Path,
    raw_output_dir: str | Path,
    document_output_path: str | Path,
    *,
    cache_root: str | Path = CACHE_ROOT,
    parser_version: str = PARSER_VERSION,
    parser_config_version: str = PARSER_CONFIG_VERSION,
    client_factory: Callable[[], Any] | None = None,
    parser: Callable[[str | Path], MinerUDocument] = parse_mineru,
    before_document_parse: Callable[[], None] | None = None,
) -> tuple[MinerUDocument, ParseCacheInfo]:
    """Load a valid cached document or execute the existing MinerU pipeline."""
    source_path = Path(pdf_path).expanduser().resolve()
    if not source_path.is_file():
        raise FileNotFoundError(f"PDF file does not exist: {source_path}")
    if source_path.stat().st_size == 0:
        raise ValueError("PDF file is empty")

    source_sha256 = sha256_file(source_path)
    cache_key = build_cache_key(
        source_sha256,
        parser_version=parser_version,
        parser_config_version=parser_config_version,
    )
    target_document = Path(document_output_path)
    cache_dir = cache_directory(cache_key, cache_root)
    warning: str | None = None

    with cache_lock(cache_key):
        cached_document, cache_warning = _load_cached_document(
            cache_dir,
            source_sha256=source_sha256,
            parser_version=parser_version,
            parser_config_version=parser_config_version,
        )
        if cached_document is not None:
            try:
                if before_document_parse is not None:
                    before_document_parse()
                target_document.parent.mkdir(parents=True, exist_ok=True)
                shutil.copy2(cache_dir / "mineru_document.json", target_document)
                return cached_document, ParseCacheInfo(
                    source_sha256=source_sha256,
                    cache_key=cache_key,
                    cache_hit=True,
                    cache_source="cache",
                    parser_version=parser_version,
                    parser_config_version=parser_config_version,
                )
            except (OSError, shutil.Error) as exc:
                target_document.unlink(missing_ok=True)
                cache_warning = "MinerU 解析缓存复制失败，已回退重新解析"
                warning = cache_warning

        if cache_warning:
            warning = cache_warning

        target_document.unlink(missing_ok=True)
        client = client_factory() if client_factory is not None else MinerUClient()
        page_count = _pdf_page_count(source_path)
        if page_count > MAX_MINERU_PDF_PAGES:
            parts = _write_pdf_parts(
                source_path,
                Path(raw_output_dir) / "split",
                chunk_size=PDF_CHUNK_SIZE,
            )
            part_documents: list[tuple[PdfPart, MinerUDocument, str]] = []
            asset_root = Path(raw_output_dir) / "raw"
            for index, part in enumerate(parts, start=1):
                part_name = f"part-{index:03d}"
                raw_dir = client.parse_pdf(
                    pdf_path=part.path,
                    output_dir=asset_root / part_name,
                )
                relative_raw_dir = _relative_asset_path(raw_dir, asset_root)
                part_documents.append((part, parser(raw_dir), relative_raw_dir))
            if before_document_parse is not None:
                before_document_parse()
            document = _merge_part_documents(
                part_documents,
                source_path=source_path,
                source_sha256=source_sha256,
                physical_page_count=page_count,
            )
        else:
            raw_dir = client.parse_pdf(
                pdf_path=source_path,
                output_dir=Path(raw_output_dir),
            )
            if before_document_parse is not None:
                before_document_parse()
            document = parser(raw_dir)
        _validate_document(document)
        _atomic_write_json(target_document, asdict(document))
        _write_cache(
            cache_dir,
            document,
            source_sha256=source_sha256,
            parser_version=parser_version,
            parser_config_version=parser_config_version,
        )
        return document, ParseCacheInfo(
            source_sha256=source_sha256,
            cache_key=cache_key,
            cache_hit=False,
            cache_source="mineru",
            parser_version=parser_version,
            parser_config_version=parser_config_version,
            warning=warning,
        )


def _pdf_page_count(pdf_path: Path) -> int:
    from pypdf import PdfReader
    from pypdf.errors import PdfReadError

    try:
        reader = PdfReader(pdf_path)
    except PdfReadError:
        # 保持原有流程的兼容性：页数预检失败时仍交由 MinerU 返回权威错误。
        return 1
    if reader.is_encrypted:
        raise ValueError("暂不支持加密 PDF")
    page_count = len(reader.pages)
    if page_count <= 0:
        raise ValueError("PDF 没有可解析页面")
    return page_count


def _write_pdf_parts(
    source_path: Path,
    split_dir: Path,
    *,
    chunk_size: int,
) -> list[PdfPart]:
    from pypdf import PdfReader, PdfWriter

    if chunk_size <= 0 or chunk_size > MAX_MINERU_PDF_PAGES:
        raise ValueError("PDF 分片页数必须介于 1 和 MinerU 页数上限之间")
    reader = PdfReader(source_path)
    if reader.is_encrypted:
        raise ValueError("暂不支持加密 PDF")
    split_dir.mkdir(parents=True, exist_ok=True)
    parts: list[PdfPart] = []
    total_pages = len(reader.pages)
    for index, start_index in enumerate(range(0, total_pages, chunk_size), start=1):
        end_index = min(start_index + chunk_size, total_pages)
        part_path = split_dir / f"part-{index:03d}.pdf"
        writer = PdfWriter()
        for page_index in range(start_index, end_index):
            writer.add_page(reader.pages[page_index])
        with part_path.open("wb") as output:
            writer.write(output)
        parts.append(
            PdfPart(
                path=part_path,
                start_page=start_index + 1,
                page_count=end_index - start_index,
            )
        )
    return parts


def _relative_asset_path(raw_dir: str | Path, asset_root: Path) -> str:
    try:
        return Path(raw_dir).resolve().relative_to(asset_root.resolve()).as_posix()
    except ValueError as exc:
        raise ValueError("MinerU 分片输出不在预期资源目录中") from exc


def _merge_part_documents(
    part_documents: list[tuple[PdfPart, MinerUDocument, str]],
    *,
    source_path: Path,
    source_sha256: str,
    physical_page_count: int,
) -> MinerUDocument:
    from .mineru_parser import _build_sections

    pages: list[MinerUPage] = []
    warnings = [
        f"原始 PDF 共 {physical_page_count} 页，已自动分片调用 MinerU 并合并结果"
    ]
    requires_human_review = False
    for part_index, (part, document, asset_prefix) in enumerate(
        part_documents, start=1
    ):
        if document.physical_page_count != part.page_count:
            raise ValueError(
                f"MinerU 分片 {part_index} 返回页数与输入不一致"
            )
        page_offset = part.start_page - 1
        part_label = f"part-{part_index:03d}"
        for page in document.pages:
            physical_page = page.physical_page + page_offset
            blocks = [
                replace(
                    block,
                    block_id=f"p{physical_page:04d}-b{block.block_index:04d}",
                    physical_page=physical_page,
                    image_path=(
                        f"{asset_prefix}/{block.image_path}"
                        if block.image_path
                        else None
                    ),
                    source_file=f"{part_label}/{block.source_file}",
                    source_pointer=f"{part_label}:{block.source_pointer}",
                )
                for block in page.blocks
            ]
            pages.append(
                replace(
                    page,
                    physical_page=physical_page,
                    source_page_index=page.source_page_index + page_offset,
                    blocks=blocks,
                )
            )
        warnings.extend(
            f"{part_label}: {message}" for message in document.warnings
        )
        requires_human_review = (
            requires_human_review or document.requires_human_review
        )
    pages.sort(key=lambda page: page.physical_page)
    if len(pages) != physical_page_count:
        raise ValueError("MinerU 分片合并后页数与原始 PDF 不一致")
    toc_page_indexes = {
        page.source_page_index
        for page in pages
        if any("目录页" in warning for warning in page.warnings)
    }
    sections = _build_sections(pages, toc_page_indexes)
    return MinerUDocument(
        document_id=f"mineru-{source_sha256[:16]}",
        source_file_name=source_path.name,
        source_sha256=source_sha256,
        physical_page_count=physical_page_count,
        pages=pages,
        sections=sections,
        warnings=warnings,
        requires_human_review=requires_human_review,
    )


@contextmanager
def cache_lock(cache_key: str) -> Iterator[None]:
    with _LOCKS_GUARD:
        lock = _LOCKS.setdefault(cache_key, threading.Lock())
    with lock:
        yield


def _load_cached_document(
    cache_dir: Path,
    *,
    source_sha256: str,
    parser_version: str,
    parser_config_version: str,
) -> tuple[MinerUDocument | None, str | None]:
    document_path = cache_dir / "mineru_document.json"
    metadata_path = cache_dir / "metadata.json"
    if not document_path.is_file() or not metadata_path.is_file():
        return None, None
    try:
        if document_path.stat().st_size == 0 or metadata_path.stat().st_size == 0:
            return None, "MinerU 解析缓存文件为空，已忽略并重新解析"
        metadata = json.loads(metadata_path.read_text(encoding="utf-8"))
        if not isinstance(metadata, dict):
            return None, "MinerU 解析缓存 metadata.json 无效，已忽略并重新解析"
        expected = {
            "source_sha256": source_sha256,
            "parser_name": PARSER_NAME,
            "parser_version": parser_version,
            "parser_config_version": parser_config_version,
            "parse_status": "success",
        }
        if any(metadata.get(key) != value for key, value in expected.items()):
            return None, "MinerU 解析缓存版本或来源不匹配，已重新解析"
        data = json.loads(document_path.read_text(encoding="utf-8"))
        document = _document_from_dict(data)
        return document, None
    except (OSError, json.JSONDecodeError, TypeError, ValueError, KeyError):
        return None, "MinerU 解析缓存损坏，已忽略并重新解析"


def _write_cache(
    cache_dir: Path,
    document: MinerUDocument,
    *,
    source_sha256: str,
    parser_version: str,
    parser_config_version: str,
) -> None:
    cache_dir.mkdir(parents=True, exist_ok=True)
    _atomic_write_json(cache_dir / "mineru_document.json", asdict(document))
    _atomic_write_json(
        cache_dir / "metadata.json",
        {
            "source_sha256": source_sha256,
            "parser_name": PARSER_NAME,
            "parser_version": parser_version,
            "parser_config_version": parser_config_version,
            "created_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
            "parse_status": "success",
        },
    )


def _validate_document(document: MinerUDocument) -> None:
    if not isinstance(document, MinerUDocument):
        raise TypeError("MinerU parser did not return MinerUDocument")
    if document.physical_page_count <= 0 or not document.pages:
        raise ValueError("MinerU parser returned an empty document")
    if any(not isinstance(page.physical_page, int) for page in document.pages):
        raise ValueError("MinerU document page structure is invalid")


def _document_from_dict(data: Any) -> MinerUDocument:
    if not isinstance(data, dict):
        raise ValueError("cached MinerU document must be a JSON object")
    pages = []
    for page in data.get("pages", []):
        if not isinstance(page, dict):
            raise ValueError("cached MinerU page is invalid")
        blocks = []
        for block in page.get("blocks", []):
            if not isinstance(block, dict):
                raise ValueError("cached MinerU block is invalid")
            bbox = block.get("bbox")
            blocks.append(
                MinerUBlock(
                    block_id=str(block.get("block_id", "")),
                    physical_page=int(block.get("physical_page", page.get("physical_page", 0))),
                    block_index=int(block.get("block_index", 0)),
                    block_type=str(block.get("block_type", "")),
                    text=str(block.get("text") or ""),
                    title_level=block.get("title_level"),
                    bbox=BoundingBox(**bbox) if isinstance(bbox, dict) else None,
                    image_path=block.get("image_path"),
                    table_html=block.get("table_html"),
                    source_file=str(block.get("source_file", "")),
                    source_pointer=str(block.get("source_pointer", "")),
                )
            )
        pages.append(
            MinerUPage(
                physical_page=int(page.get("physical_page", 0)),
                source_page_index=int(page.get("source_page_index", 0)),
                width=page.get("width"),
                height=page.get("height"),
                printed_page=page.get("printed_page"),
                page_type=str(page.get("page_type", "")),
                parse_status=str(page.get("parse_status", "")),
                text=str(page.get("text") or ""),
                blocks=blocks,
                warnings=[str(item) for item in page.get("warnings", [])],
                requires_human_review=bool(page.get("requires_human_review", False)),
            )
        )
    sections = [
        MinerUSection(
            section_id=str(section.get("section_id", "")),
            title=str(section.get("title", "")),
            level=int(section.get("level", 0)),
            path=[str(item) for item in section.get("path", [])],
            physical_page_start=int(section.get("physical_page_start", 0)),
            physical_page_end=int(section.get("physical_page_end", 0)),
        )
        for section in data.get("sections", [])
        if isinstance(section, dict)
    ]
    document = MinerUDocument(
        document_id=str(data.get("document_id", "")),
        source_file_name=str(data.get("source_file_name", "")),
        source_sha256=str(data.get("source_sha256", "")),
        physical_page_count=int(data.get("physical_page_count", len(pages))),
        pages=pages,
        sections=sections,
        warnings=[str(item) for item in data.get("warnings", [])],
        requires_human_review=bool(data.get("requires_human_review", False)),
    )
    _validate_document(document)
    return document


def _atomic_write_json(path: Path, data: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    descriptor, temp_name = tempfile.mkstemp(
        prefix=f".{path.name}-",
        suffix=".tmp",
        dir=path.parent,
    )
    try:
        with os.fdopen(descriptor, "w", encoding="utf-8") as handle:
            json.dump(data, handle, ensure_ascii=False, indent=2)
            handle.write("\n")
        os.replace(temp_name, path)
    finally:
        Path(temp_name).unlink(missing_ok=True)


def _safe_component(value: str) -> str:
    component = _CACHE_KEY_SAFE.sub("-", str(value).strip())
    return component.strip(".-") or "unknown"
