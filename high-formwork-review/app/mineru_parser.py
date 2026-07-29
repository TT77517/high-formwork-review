"""把已经落盘的 MinerU 原始结果转换为 MinerUDocument。"""

from __future__ import annotations

import hashlib
import json
import re
from html import unescape
from pathlib import Path
from typing import Any

from .models import (
    BoundingBox,
    MinerUBlock,
    MinerUDocument,
    MinerUPage,
    MinerUSection,
)


def parse_mineru(raw_dir: str | Path) -> MinerUDocument:
    """读取一个 MinerU raw 目录并返回规范化文档。"""
    raw_path = Path(raw_dir)
    if not raw_path.is_dir():
        raise ValueError(f"MinerU raw 目录不存在：{raw_path}")

    content_files = sorted(raw_path.glob("*_content_list_v2.json"))
    if not content_files:
        raise ValueError(f"目录中没有 *_content_list_v2.json：{raw_path}")
    if len(content_files) > 1:
        names = "、".join(path.name for path in content_files)
        raise ValueError(f"目录中存在多个 *_content_list_v2.json：{names}")

    content_file = content_files[0]
    layout_file = raw_path / "layout.json"
    if not layout_file.is_file():
        raise ValueError(f"目录中缺少 layout.json：{raw_path}")

    raw_bytes = content_file.read_bytes()
    content_pages = _load_json(content_file)
    layout_data = _load_json(layout_file)
    if not isinstance(content_pages, list):
        raise ValueError(f"{content_file.name} 顶层必须是页面列表")
    if not isinstance(layout_data, dict) or not isinstance(
        layout_data.get("pdf_info"), list
    ):
        raise ValueError("layout.json 顶层必须包含 pdf_info 页面列表")

    document_warnings: list[str] = []
    if len(layout_data["pdf_info"]) != len(content_pages):
        document_warnings.append(
            "content_list_v2 与 layout.json 的页面数量不一致，缺失的页面尺寸将留空"
        )

    toc_page_indexes = _detect_toc_pages(content_pages)
    page_sizes = _page_sizes(layout_data["pdf_info"])
    pages: list[MinerUPage] = []

    for page_index, raw_blocks in enumerate(content_pages):
        physical_page = page_index + 1
        page_warnings: list[str] = []
        if not isinstance(raw_blocks, list):
            page_warnings.append("页面内容不是 block 列表")
            raw_blocks = []

        blocks: list[MinerUBlock] = []
        for block_index, raw_block in enumerate(raw_blocks):
            block = _parse_block(
                raw_block=raw_block,
                raw_dir=raw_path,
                source_file=content_file.name,
                physical_page=physical_page,
                page_index=page_index,
                block_index=block_index,
                warnings=page_warnings,
            )
            if block is not None:
                blocks.append(block)

        _mark_table_continuation(pages, blocks)
        width, height = page_sizes.get(page_index, (None, None))
        printed_page = _printed_page(blocks)
        page_type = _classify_page(blocks)
        parse_status, human_review = _parse_status(blocks, page_warnings)
        page_text = "\n".join(
            block.text
            for block in blocks
            if block.block_type != "page_number" and block.text
        )

        if page_index in toc_page_indexes:
            page_warnings.append("识别为目录页，标题不会生成正文 section")

        pages.append(
            MinerUPage(
                physical_page=physical_page,
                source_page_index=page_index,
                width=width,
                height=height,
                printed_page=printed_page,
                page_type=page_type,
                parse_status=parse_status,
                text=page_text,
                blocks=blocks,
                warnings=page_warnings,
                requires_human_review=human_review,
            )
        )

    sections = _build_sections(pages, toc_page_indexes)
    source_sha256 = hashlib.sha256(raw_bytes).hexdigest()
    return MinerUDocument(
        document_id=f"mineru-{source_sha256[:16]}",
        source_file_name=content_file.name,
        source_sha256=source_sha256,
        physical_page_count=len(pages),
        pages=pages,
        sections=sections,
        warnings=document_warnings,
        requires_human_review=bool(document_warnings)
        or any(page.requires_human_review for page in pages),
    )


def _load_json(path: Path) -> Any:
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except UnicodeDecodeError as exc:
        raise ValueError(f"文件不是有效的 UTF-8：{path.name}") from exc
    except json.JSONDecodeError as exc:
        raise ValueError(
            f"JSON 格式错误：{path.name}，第 {exc.lineno} 行第 {exc.colno} 列"
        ) from exc


def _page_sizes(pdf_info: list[Any]) -> dict[int, tuple[float | None, float | None]]:
    sizes: dict[int, tuple[float | None, float | None]] = {}
    for fallback_index, page_info in enumerate(pdf_info):
        if not isinstance(page_info, dict):
            continue
        page_index = page_info.get("page_idx", fallback_index)
        if not isinstance(page_index, int):
            page_index = fallback_index
        size = page_info.get("page_size")
        width: float | None = None
        height: float | None = None
        if isinstance(size, (list, tuple)) and len(size) >= 2:
            width = _number_or_none(size[0])
            height = _number_or_none(size[1])
        elif isinstance(size, dict):
            width = _number_or_none(size.get("width"))
            height = _number_or_none(size.get("height"))
        sizes[page_index] = (width, height)
    return sizes


def _parse_block(
    raw_block: Any,
    raw_dir: Path,
    source_file: str,
    physical_page: int,
    page_index: int,
    block_index: int,
    warnings: list[str],
) -> MinerUBlock | None:
    pointer = f"/{page_index}/{block_index}"
    if not isinstance(raw_block, dict):
        warnings.append(f"{pointer} 不是 JSON 对象，已跳过")
        return None

    block_type = str(raw_block.get("type") or "unknown")
    content = raw_block.get("content")
    content_dict = content if isinstance(content, dict) else {}
    text = _block_text(block_type, content)
    title_level = None
    if block_type == "title":
        raw_level = content_dict.get("level")
        if isinstance(raw_level, int):
            title_level = max(1, raw_level)
        else:
            title_level = 1
            warnings.append(f"{pointer} 标题缺少有效 level，按 1 级处理")

    table_html = None
    if block_type == "table":
        raw_html = content_dict.get("html")
        table_html = raw_html if isinstance(raw_html, str) else ""

    image_path = None
    image_source = content_dict.get("image_source")
    if isinstance(image_source, dict) and isinstance(image_source.get("path"), str):
        image_path = image_source["path"]
        if image_path and not (raw_dir / image_path).is_file():
            warnings.append(f"{pointer} 引用的图片不存在：{image_path}")

    bbox = _bounding_box(raw_block.get("bbox"), pointer, warnings)
    return MinerUBlock(
        block_id=f"p{physical_page:04d}-b{block_index:04d}",
        physical_page=physical_page,
        block_index=block_index,
        block_type=block_type,
        text=text,
        title_level=title_level,
        bbox=bbox,
        image_path=image_path,
        table_html=table_html,
        source_file=source_file,
        source_pointer=pointer,
    )


def _block_text(block_type: str, content: Any) -> str:
    if not isinstance(content, dict):
        return content.strip() if isinstance(content, str) else ""

    key_by_type = {
        "paragraph": "paragraph_content",
        "title": "title_content",
        "page_number": "page_number_content",
    }
    if block_type in key_by_type:
        return _fragment_text(content.get(key_by_type[block_type]))

    if block_type == "table":
        caption = _fragment_text(content.get("table_caption"))
        footnote = _fragment_text(content.get("table_footnote"))
        html_text = _html_to_text(content.get("html"))
        return "\n".join(part for part in (caption, html_text, footnote) if part)

    if block_type in {"image", "chart"}:
        caption = _fragment_text(
            content.get("image_caption") or content.get("chart_caption")
        )
        body = content.get("content") if isinstance(content.get("content"), str) else ""
        footnote = _fragment_text(
            content.get("image_footnote") or content.get("chart_footnote")
        )
        return "\n".join(part for part in (caption, body.strip(), footnote) if part)

    return _fragment_text(content)


def _fragment_text(value: Any) -> str:
    """递归提取嵌套文本，但不把内部 type=text 创建成正文 block。"""
    if isinstance(value, str):
        return value.strip()
    if isinstance(value, list):
        return "\n".join(filter(None, (_fragment_text(item) for item in value)))
    if isinstance(value, dict):
        direct = value.get("content")
        if isinstance(direct, str):
            return direct.strip()
        return "\n".join(
            filter(
                None,
                (
                    _fragment_text(item)
                    for key, item in value.items()
                    if key not in {"image_source", "html"}
                ),
            )
        )
    return ""


def _html_to_text(value: Any) -> str:
    if not isinstance(value, str) or not value.strip():
        return ""
    text = re.sub(r"<[^>]+>", " ", value)
    return re.sub(r"\s+", " ", unescape(text)).strip()


def _bounding_box(
    value: Any, pointer: str, warnings: list[str]
) -> BoundingBox | None:
    if value is None:
        return None
    if not isinstance(value, (list, tuple)) or len(value) != 4:
        warnings.append(f"{pointer} bbox 格式无效")
        return None
    numbers = [_number_or_none(item) for item in value]
    if any(item is None for item in numbers):
        warnings.append(f"{pointer} bbox 包含非数字")
        return None
    return BoundingBox(*numbers)  # type: ignore[arg-type]


def _number_or_none(value: Any) -> float | None:
    if isinstance(value, bool):
        return None
    if isinstance(value, (int, float)):
        return float(value)
    return None


def _printed_page(blocks: list[MinerUBlock]) -> str | None:
    for block in blocks:
        if block.block_type == "page_number" and block.text:
            return block.text.splitlines()[0].strip()
    return None


def _mark_table_continuation(
    previous_pages: list[MinerUPage], blocks: list[MinerUBlock]
) -> None:
    if not previous_pages:
        return
    previous_has_table = any(
        block.block_type in {"table", "table_continuation"}
        and bool((block.table_html or "").strip())
        for block in previous_pages[-1].blocks
    )
    if not previous_has_table:
        return
    for block in blocks:
        if block.block_type == "table" and not (block.table_html or "").strip():
            block.block_type = "table_continuation"


def _classify_page(blocks: list[MinerUBlock]) -> str:
    has_text = any(
        block.block_type in {"paragraph", "title"} and bool(block.text)
        for block in blocks
    )
    has_table = any(
        block.block_type in {"table", "table_continuation"} for block in blocks
    )
    visual_blocks = [
        block for block in blocks if block.block_type in {"image", "chart"}
    ]
    has_visual = bool(visual_blocks)
    all_text = " ".join(block.text for block in blocks if block.text)
    organization_terms = ("组织机构", "组织架构", "组织体系", "领导小组")

    if has_visual and any(term in all_text for term in organization_terms):
        return "organization_chart"
    category_count = sum((has_text, has_table, has_visual))
    if category_count > 1:
        return "mixed"
    if has_table:
        return "table"
    if has_visual:
        return "drawing"
    if has_text:
        return "text"
    return "unknown"


def _parse_status(
    blocks: list[MinerUBlock], warnings: list[str]
) -> tuple[str, bool]:
    body_text = any(
        block.block_type == "paragraph" and bool(block.text.strip()) for block in blocks
    )
    nonempty_table = any(
        block.block_type == "table" and bool((block.table_html or "").strip())
        for block in blocks
    )
    has_visual = any(block.block_type in {"image", "chart"} for block in blocks)
    empty_table = any(
        block.block_type in {"table", "table_continuation"}
        and not (block.table_html or "").strip()
        for block in blocks
    )
    has_usable_content = body_text or nonempty_table or has_visual or any(
        block.block_type == "title" and block.text for block in blocks
    )

    if empty_table or (has_visual and not body_text and not nonempty_table):
        return "partial", True
    if not has_usable_content:
        return "unreadable", True
    if warnings:
        return "partial", True
    return "complete", False


def _detect_toc_pages(content_pages: list[Any]) -> set[int]:
    toc_pages: set[int] = set()
    in_toc = False
    for page_index, raw_blocks in enumerate(content_pages):
        if not isinstance(raw_blocks, list):
            if in_toc:
                break
            continue
        title_texts: list[str] = []
        page_texts: list[str] = []
        for raw_block in raw_blocks:
            if not isinstance(raw_block, dict):
                continue
            block_type = str(raw_block.get("type") or "")
            text = _block_text(block_type, raw_block.get("content"))
            if text:
                page_texts.append(text)
            if block_type == "title" and text:
                title_texts.append(text)

        normalized_titles = {
            re.sub(r"\s+", "", title) for title in title_texts
        }
        has_toc_title = any(title in {"目录", "目次"} for title in normalized_titles)
        combined = "\n".join(page_texts)
        toc_line_count = sum(
            1
            for line in combined.splitlines()
            if re.search(r"(?:\.{2,}|…{2,}|·{2,})\s*\d+\s*$", line.strip())
        )
        looks_like_toc = has_toc_title or toc_line_count >= 2

        if has_toc_title:
            in_toc = True
        if in_toc and looks_like_toc:
            toc_pages.add(page_index)
        elif in_toc:
            break
    return toc_pages


def _build_sections(
    pages: list[MinerUPage], toc_page_indexes: set[int]
) -> list[MinerUSection]:
    sections: list[MinerUSection] = []
    open_section_indexes: list[int] = []
    previous_title: tuple[int, int, str] | None = None

    for page in pages:
        if page.source_page_index in toc_page_indexes:
            continue
        for block in page.blocks:
            if not _is_section_title(block):
                continue
            normalized_title = _normalize_title(block.text)
            if (
                previous_title is not None
                and previous_title[0] == page.physical_page
                and previous_title[1] + 1 == block.block_index
                and previous_title[2] == normalized_title
            ):
                continue
            previous_title = (
                page.physical_page,
                block.block_index,
                normalized_title,
            )
            level = _effective_title_level(block.text, block.title_level)
            new_root = _title_root_number(block.text)
            current_root = (
                _title_root_number(sections[open_section_indexes[0]].title)
                if open_section_indexes
                else None
            )
            if new_root and current_root and new_root != current_root:
                while open_section_indexes:
                    closed_index = open_section_indexes.pop()
                    sections[closed_index].physical_page_end = page.physical_page
            while (
                open_section_indexes
                and sections[open_section_indexes[-1]].level >= level
            ):
                closed_index = open_section_indexes.pop()
                sections[closed_index].physical_page_end = page.physical_page
            path = [
                sections[index].title for index in open_section_indexes
            ] + [block.text.strip()]
            sections.append(
                MinerUSection(
                    section_id=f"section-{len(sections) + 1:04d}",
                    title=block.text.strip(),
                    level=level,
                    path=path,
                    physical_page_start=page.physical_page,
                    physical_page_end=page.physical_page,
                )
            )
            open_section_indexes.append(len(sections) - 1)

    for section_index in open_section_indexes:
        sections[section_index].physical_page_end = len(pages)
    return sections


def _is_section_title(block: MinerUBlock) -> bool:
    """保守判断一个 MinerU title block 是否可创建正文 section。"""
    if block.block_type != "title" or not block.text.strip():
        return False
    title = block.text.strip()
    if re.search(r"(?:\.{2,}|…{2,}|·{2,})\s*\d+\s*$", title):
        return False
    if re.match(
        r"^\s*(?:[（(]\d+[）)]|\d+[）)]|\d+[、，,])(?:[、，,.)）．.\s]*)",
        title,
    ):
        return False
    if re.match(r"^\s*(?:图|表|附图|附件)\s*\d+\s*[:：、.．-]", title):
        return False

    core = re.sub(r"^\s*\d+(?:\.\d+)*[.．]?\s*", "", title)
    useful_characters = re.findall(r"[\u4e00-\u9fffA-Za-z]", core)
    return len(useful_characters) >= 2


def _normalize_title(title: str) -> str:
    return re.sub(r"[\s　]+", "", title).strip()


def _effective_title_level(title: str, mineru_level: int | None) -> int:
    """MinerU 层级全相同时，用常见的数字标题补充判断。"""
    multi_level = re.match(r"^\s*(\d+(?:\.\d+)+)(?=[^\d.]|$)", title)
    if multi_level:
        return len(multi_level.group(1).split("."))
    top_level = re.match(r"^\s*(\d+)[.．\s]", title)
    if top_level:
        return 1
    return max(1, mineru_level or 1)


def _title_root_number(title: str) -> str | None:
    match = re.match(r"^\s*(\d+)(?:\.|\s)", title)
    return match.group(1) if match else None
