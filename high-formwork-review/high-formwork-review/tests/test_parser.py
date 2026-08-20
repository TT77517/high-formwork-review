import json
import os
from pathlib import Path

import pytest

from app.mineru_parser import parse_mineru


def _write_raw(tmp_path: Path) -> Path:
    raw_dir = tmp_path / "raw"
    image_dir = raw_dir / "images"
    image_dir.mkdir(parents=True)
    (image_dir / "drawing.jpg").write_bytes(b"test")

    pages = [
        [
            {
                "type": "title",
                "content": {
                    "title_content": [{"type": "text", "content": "目录"}],
                    "level": 1,
                },
                "bbox": [10, 10, 100, 30],
            },
            {
                "type": "paragraph",
                "content": {
                    "paragraph_content": [
                        {
                            "type": "text",
                            "content": "1. 工程概况....1\n2. 编制依据....2",
                        }
                    ]
                },
                "bbox": [10, 40, 200, 100],
            },
        ],
        [
            {
                "type": "title",
                "content": {
                    "title_content": [{"type": "text", "content": "1. 工程概况"}],
                    "level": 2,
                },
                "bbox": [10, 10, 160, 30],
            },
            {
                "type": "paragraph",
                "content": {
                    "paragraph_content": [
                        {
                            "type": "text",
                            "content": "工程名称为测试项目，建筑面积为一万平方米。",
                        }
                    ]
                },
                "bbox": [10, 40, 250, 80],
            },
            {
                "type": "page_number",
                "content": {
                    "page_number_content": [{"type": "text", "content": "1"}]
                },
                "bbox": [100, 280, 110, 290],
            },
        ],
        [
            {
                "type": "image",
                "content": {
                    "image_source": {"path": "images/drawing.jpg"},
                    "content": "",
                    "image_caption": [],
                    "image_footnote": [],
                },
                "bbox": [20, 20, 280, 250],
            }
        ],
        [
            {
                "type": "table",
                "content": {
                    "image_source": {"path": "images/drawing.jpg"},
                    "table_caption": [],
                    "table_footnote": [],
                    "html": "<table><tr><td>支架参数</td></tr></table>",
                },
                "bbox": [10, 20, 290, 250],
            }
        ],
        [
            {
                "type": "table",
                "content": {
                    "image_source": {"path": "images/drawing.jpg"},
                    "table_caption": [],
                    "table_footnote": [],
                    "html": "",
                },
                "bbox": [10, 20, 290, 250],
            }
        ],
    ]
    layout = {
        "pdf_info": [
            {"page_idx": index, "page_size": [300, 300]}
            for index in range(len(pages))
        ]
    }
    (raw_dir / "sample_content_list_v2.json").write_text(
        json.dumps(pages, ensure_ascii=False), encoding="utf-8"
    )
    (raw_dir / "layout.json").write_text(
        json.dumps(layout, ensure_ascii=False), encoding="utf-8"
    )
    return raw_dir


def _write_custom_raw(tmp_path: Path, pages: list[list[dict]]) -> Path:
    raw_dir = tmp_path / "custom-raw"
    raw_dir.mkdir()
    layout = {
        "pdf_info": [
            {"page_idx": index, "page_size": [300, 300]}
            for index in range(len(pages))
        ]
    }
    (raw_dir / "custom_content_list_v2.json").write_text(
        json.dumps(pages, ensure_ascii=False), encoding="utf-8"
    )
    (raw_dir / "layout.json").write_text(
        json.dumps(layout, ensure_ascii=False), encoding="utf-8"
    )
    return raw_dir


def test_parser_preserves_structure_and_page_mapping(tmp_path: Path) -> None:
    document = parse_mineru(_write_raw(tmp_path))

    assert document.physical_page_count == 5
    assert document.pages[1].physical_page == 2
    assert document.pages[1].source_page_index == 1
    assert document.pages[1].printed_page == "1"
    assert document.pages[1].width == 300
    assert document.pages[1].height == 300

    title = document.pages[1].blocks[0]
    assert title.title_level == 2
    assert title.bbox is not None
    assert title.bbox.x0 == 10
    assert title.source_pointer == "/1/0"


def test_parser_preserves_image_and_table_content(tmp_path: Path) -> None:
    document = parse_mineru(_write_raw(tmp_path))

    image = document.pages[2].blocks[0]
    table = document.pages[3].blocks[0]
    assert image.image_path == "images/drawing.jpg"
    assert table.image_path == "images/drawing.jpg"
    assert table.table_html == "<table><tr><td>支架参数</td></tr></table>"
    assert "支架参数" in table.text


def test_toc_titles_do_not_create_body_sections(tmp_path: Path) -> None:
    document = parse_mineru(_write_raw(tmp_path))

    assert any("目录页" in warning for warning in document.pages[0].warnings)
    assert all(section.title != "目录" for section in document.sections)
    assert any(section.title == "1. 工程概况" for section in document.sections)


def test_image_page_and_empty_table_are_partial(tmp_path: Path) -> None:
    document = parse_mineru(_write_raw(tmp_path))

    image_page = document.pages[2]
    empty_table_page = document.pages[4]
    assert image_page.page_type == "drawing"
    assert image_page.parse_status == "partial"
    assert image_page.requires_human_review is True
    assert empty_table_page.parse_status == "partial"
    assert empty_table_page.requires_human_review is True


def test_cross_page_empty_table_is_marked_as_continuation(tmp_path: Path) -> None:
    document = parse_mineru(_write_raw(tmp_path))

    assert document.pages[4].blocks[0].block_type == "table_continuation"


def test_section_builder_filters_list_captions_short_text_and_duplicates(
    tmp_path: Path,
) -> None:
    def title(text: str, level: int = 2) -> dict:
        return {
            "type": "title",
            "content": {
                "title_content": [{"type": "text", "content": text}],
                "level": level,
            },
            "bbox": [10, 10, 200, 30],
        }

    pages = [
        [
            title("4. 施工工艺技术"),
            title("1、准备工作"),
            title("(2) 模板拆除"),
            title("图 1：支架示意图"),
            title("5. 计算书....82"),
            title("A"),
            title("4.1 技术参数"),
            title("4.1 技术参数"),
            title("4.2无空格标题"),
            {
                "type": "paragraph",
                "content": {
                    "paragraph_content": [
                        {"type": "text", "content": "5. 普通段落中的数字编号"}
                    ]
                },
                "bbox": [10, 40, 200, 80],
            },
            {
                "type": "table",
                "content": {
                    "html": "<table><tr><td>6. 表格单元格标题</td></tr></table>"
                },
                "bbox": [10, 90, 200, 150],
            },
            {
                "type": "page_number",
                "content": {
                    "page_number_content": [{"type": "text", "content": "1"}]
                },
                "bbox": [100, 280, 110, 290],
            },
        ]
    ]

    document = parse_mineru(_write_custom_raw(tmp_path, pages))

    assert [section.title for section in document.sections] == [
        "4. 施工工艺技术",
        "4.1 技术参数",
        "4.2无空格标题",
    ]
    assert document.sections[-1].level == 2
    assert document.pages[0].blocks[0].title_level == 2


def test_real_sample_when_environment_variable_is_set() -> None:
    sample_dir = os.getenv("MINERU_SAMPLE_RAW_DIR")
    if not sample_dir:
        pytest.skip("未设置 MINERU_SAMPLE_RAW_DIR")

    document = parse_mineru(sample_dir)
    assert document.physical_page_count > 0
    assert document.source_sha256
    assert any(page.blocks for page in document.pages)
