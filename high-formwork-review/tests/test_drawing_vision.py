"""Task 5C: Vision Provider Adapter 单测（mock client，不访问网络）。"""
from __future__ import annotations

import json
import tempfile
from pathlib import Path


class _FakeClient:
    """模拟 LLMChatClient：返回预设 content（同步接口）。"""

    def __init__(self, content: str) -> None:
        self.content = content
        self.calls: list[dict] = []

    def chat_sync(self, messages, *, tools=None, temperature=0.1):
        self.calls.append({"messages": messages, "temperature": temperature})
        from dataclasses import dataclass

        @dataclass
        class _R:
            content: str

        return _R(content=self.content)


def _make_page(image_rel: str = "part-001/raw/images/abc.png"):
    """构造一个含 image block 的 fake MinerUPage。"""
    class _Block:
        pass

    block = _Block()
    block.block_type = "image"
    block.image_path = image_rel

    class _Page:
        pass

    page = _Page()
    page.blocks = [block]
    return page


def _task():
    from app.drawing_agent import DrawingReviewTask

    return DrawingReviewTask(
        fact_id="head_jack_insertion_length",
        display_name="可调托撑插入长度",
        aliases=["托撑插入长度"],
        text_value=None,
        unit="mm",
    )


def test_inspect_drawing_page_normalizes_full_contract() -> None:
    """Case 1: 模型返回完整 contract → Adapter 返回 6 字段。"""
    from app.drawing_vision import inspect_drawing_page

    with tempfile.TemporaryDirectory() as tmp:
        image_path = Path(tmp) / "demo.png"
        image_path.write_bytes(b"\x89PNG\r\n\x1a\n-fake")
        page = _make_page(image_rel=str(image_path))  # 绝对路径走 _resolve_image_path 的 is_absolute 分支
        client = _FakeClient(
            json.dumps(
                {
                    "found": True,
                    "value": 150,
                    "unit": "mm",
                    "evidence_text": "托撑插入长度150mm",
                    "confidence": 0.95,
                    "scope": {},
                },
                ensure_ascii=False,
            )
        )
        result = inspect_drawing_page(page, _task(), client=client)
        assert set(result.keys()) == {"found", "value", "unit", "evidence_text", "confidence", "scope"}
        assert result["found"] is True
        assert result["value"] == 150
        assert result["unit"] == "mm"
        assert result["evidence_text"] == "托撑插入长度150mm"
        assert result["confidence"] == 0.95
        assert result["scope"] == {}
        assert len(client.calls) == 1
        # messages 含 vision content
        m = client.calls[0]["messages"]
        assert m[0]["role"] == "system"
        assert m[1]["role"] == "user"
        content = m[1]["content"]
        assert isinstance(content, list) and any(c.get("type") == "image_url" for c in content)


def test_inspect_drawing_page_drops_extra_fields() -> None:
    """Case 2: Provider 返回多余字段（compliant / suggestion / reason / rule） → 一律丢弃。"""
    from app.drawing_vision import inspect_drawing_page

    with tempfile.TemporaryDirectory() as tmp:
        image_path = Path(tmp) / "demo.png"
        image_path.write_bytes(b"\x89PNG\r\n\x1a\n-fake")
        page = _make_page(image_rel=str(image_path))
        client = _FakeClient(
            json.dumps(
                {
                    "found": True,
                    "value": 150,
                    "unit": "mm",
                    "evidence_text": "150",
                    "confidence": 0.9,
                    "scope": {},
                    "compliant": True,  # 违规字段
                    "suggestion": "应改为 200",  # 违规字段
                    "rule": "JGJ231 6.1.6",  # 违规字段
                    "reason": "因为规范要求",  # 违规字段
                },
                ensure_ascii=False,
            )
        )
        result = inspect_drawing_page(page, _task(), client=client)
        assert set(result.keys()) == {"found", "value", "unit", "evidence_text", "confidence", "scope"}
        for forbidden in ("compliant", "suggestion", "rule", "reason"):
            assert forbidden not in result


def test_inspect_drawing_page_found_false_no_fabrication() -> None:
    """Case 3: found=false → Adapter 不编造 value。"""
    from app.drawing_vision import inspect_drawing_page

    with tempfile.TemporaryDirectory() as tmp:
        image_path = Path(tmp) / "demo.png"
        image_path.write_bytes(b"\x89PNG\r\n\x1a\n-fake")
        page = _make_page(image_rel=str(image_path))
        # 异常情况：模型给 found=false 但附带 value（防幻觉：丢弃 value）
        client = _FakeClient(
            json.dumps(
                {"found": False, "value": 999, "unit": "mm",
                 "evidence_text": "x", "confidence": 0.9, "scope": {}},
                ensure_ascii=False,
            )
        )
        result = inspect_drawing_page(page, _task(), client=client)
        assert result["found"] is False
        assert result["value"] is None
        assert result["unit"] is None
        assert result["evidence_text"] is None


def test_inspect_drawing_page_image_missing_no_client_call() -> None:
    """Case 4: 图片不存在 → 0 client calls，found=false。"""
    from app.drawing_vision import inspect_drawing_page

    class _EmptyPage:
        blocks = []

    client = _FakeClient("should not be called")
    result = inspect_drawing_page(_EmptyPage(), _task(), client=client)
    assert result["found"] is False
    assert result["value"] is None
    assert len(client.calls) == 0


def test_inspect_drawing_page_malformed_response_does_not_crash() -> None:
    """Case 5: Provider 返回非 JSON / 非法 JSON → found=false 不 crash。"""
    from app.drawing_vision import inspect_drawing_page

    for bad in [
        "not json at all",
        "{ broken json",
        "[1,2,3]",  # 不是 dict
        "",  # 空
    ]:
        with tempfile.TemporaryDirectory() as tmp:
            image_path = Path(tmp) / "demo.png"
            image_path.write_bytes(b"\x89PNG\r\n\x1a\n-fake")
            page = _make_page(image_rel=str(image_path))
            client = _FakeClient(bad)
            result = inspect_drawing_page(page, _task(), client=client)
            assert result["found"] is False, f"bad input should yield found=False: {bad!r}"
            assert result["value"] is None


def test_inspect_drawing_page_compatible_with_agent_construction() -> None:
    """Agent + Adapter 接口兼容 smoke：构造器不报错，不要求真实运行。"""
    from app.drawing_agent import DrawingConsistencyAgent
    from app.drawing_review import (
        cross_check_param,
        ocr_drawing_page,
        recall_drawing_pages,
    )
    from app.drawing_vision import inspect_drawing_page

    agent = DrawingConsistencyAgent(
        recall_tool=recall_drawing_pages,
        check_tool=cross_check_param,
        ocr_tool=ocr_drawing_page,
        vision_tool=inspect_drawing_page,
    )
    assert agent is not None
    assert callable(inspect_drawing_page)
