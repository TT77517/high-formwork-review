from __future__ import annotations

from app.models import MinerUBlock, MinerUDocument, MinerUPage
from app.fact_conflict_detector import resolve_fact
from app.consistency_review import build_consistency_review
from app.drawing_review import build_drawing_review
from app.parameter_normalizer import normalize_candidate
from app.project_facts import build_project_facts
from app.project_qualification import build_project_qualification
from app.review_summary import build_review_results
from app.substantive_review import build_substantive_review


def _document(text: str) -> MinerUDocument:
    return MinerUDocument(
        document_id="demo",
        source_file_name="demo.pdf",
        source_sha256="sha",
        physical_page_count=1,
        pages=[
            MinerUPage(
                physical_page=1,
                source_page_index=0,
                width=None,
                height=None,
                printed_page="1",
                page_type="text",
                parse_status="complete",
                text=text,
                blocks=[
                    MinerUBlock(
                        block_id="p0001-b0001",
                        physical_page=1,
                        block_index=1,
                        block_type="paragraph",
                        text=text,
                        title_level=None,
                        bbox=None,
                        image_path=None,
                        table_html=None,
                        source_file="demo",
                        source_pointer="/0/1",
                    )
                ],
            )
        ],
    )


def _document_with_pages(pages: list[tuple[int, str, str]]) -> MinerUDocument:
    return MinerUDocument(
        document_id="demo",
        source_file_name="demo.pdf",
        source_sha256="sha",
        physical_page_count=len(pages),
        pages=[
            MinerUPage(
                physical_page=physical_page,
                source_page_index=index,
                width=None,
                height=None,
                printed_page=str(physical_page),
                page_type=page_type,
                parse_status="complete",
                text=text,
                blocks=[
                    MinerUBlock(
                        block_id=f"p{physical_page:04d}-b0001",
                        physical_page=physical_page,
                        block_index=1,
                        block_type="paragraph",
                        text=text,
                        title_level=None,
                        bbox=None,
                        image_path=None,
                        table_html=None,
                        source_file="demo",
                        source_pointer=f"/{index}/1",
                    )
                ],
            )
            for index, (physical_page, page_type, text) in enumerate(pages)
        ],
    )


def test_project_qualification_identifies_disk_lock_and_height() -> None:
    doc = _document("本工程采用盘扣式钢管架，支撑高度为10.2m。")

    facts = build_project_facts(doc)
    result = build_project_qualification(doc, facts)

    assert result["support_system"] == "disk_lock"
    assert result["risk_classification"] == "over_scale_dangerous"
    assert "disk_lock" in result["applicable_rule_packs"]
    assert result["requires_human_review"] is False


def test_project_qualification_missing_core_values_requires_review() -> None:
    doc = _document("本方案为模板支撑施工方案。")

    result = build_project_qualification(doc, build_project_facts(doc))

    assert result["support_system"] == "unknown"
    assert result["risk_classification"] == "unknown"
    assert result["requires_human_review"] is True


def test_project_qualification_lists_applicable_standards() -> None:
    doc = _document("本工程采用盘扣式钢管架，支撑高度为10.2m。")
    result = build_project_qualification(doc, build_project_facts(doc))

    ids = [s["standard_id"] for s in result["applicable_standards"]]
    assert "JGJT231-2021" in ids and "JGJ162-2016" in ids
    assert "JGJ130-2011" not in ids

    doc2 = _document("本方案为模板支撑施工方案。")
    unknown = build_project_qualification(doc2, build_project_facts(doc2))

    ids2 = [s["standard_id"] for s in unknown["applicable_standards"]]
    assert "JGJ162-2016" in ids2 and "JGJT231-2021" not in ids2
    assert all(s.get("note") for s in unknown["applicable_standards"])


def test_project_qualification_reads_parameters_from_facts() -> None:
    facts = {"facts": {
        "support_system": {"value": "disk_lock", "status": "confirmed", "evidence": []},
        "support_height": {"value": 8.5, "unit": "m", "status": "confirmed", "evidence": []},
        "support_span": {"value": 18.0, "unit": "m", "status": "confirmed", "evidence": []},
        "total_load": {"value": 16.0, "unit": "kN/m2", "status": "confirmed", "evidence": []},
        "concentrated_line_load": {"value": 20.0, "unit": "kN/m", "status": "uncertain", "evidence": []},
    }}

    result = build_project_qualification(None, facts)

    p = result["identified_parameters"]
    assert p["support_span"]["value"] == 18.0 and p["support_span"]["status"] == "confirmed"
    assert p["total_load_design"]["value"] == 16.0
    assert p["concentrated_line_load_design"]["status"] == "uncertain"
    assert result["pending_confirmation"] is None


def test_project_qualification_pending_confirmation_when_unknown() -> None:
    result = build_project_qualification(None, {"facts": {}})

    pending = result["pending_confirmation"]
    assert pending and pending["field"] == "support_system"
    counts = {o["value"]: o["pending_rule_count"] for o in pending["options"]}
    assert counts["disk_lock"] > 0 and counts["coupler"] > 0


def test_substantive_review_handles_numeric_and_missing_facts() -> None:
    doc = _document(
        "采用盘扣式钢管架，支撑高度为10.2m，步距1.5m，"
        "可调托撑悬臂长度450mm。"
        "永久荷载包括模板支架自重、新浇混凝土自重、钢筋自重。"
        "可变荷载包括施工人员及设备荷载、振捣混凝土荷载、风荷载。"
    )
    facts = build_project_facts(doc)
    qualification = build_project_qualification(doc, facts)

    results = build_substantive_review(qualification, facts)

    by_id = {item["review_item_id"]: item for item in results}
    assert by_id["SR-03"]["status"] == "PASS"
    assert by_id["SR-04"]["status"] == "PASS"
    assert by_id["SR-05"]["status"] == "PASS"
    assert by_id["SR-02"]["status"] in {"PASS", "REVIEW"}


def test_substantive_review_checks_horizontal_scissor_brace_interval_scope() -> None:
    doc = _document(
        "采用盘扣式钢管架，支撑高度为10.2m，步距1.5m，"
        "支撑架应沿高度每间隔4个~6个标准步距应设置水平剪刀撑。"
    )
    facts = build_project_facts(doc)
    qualification = build_project_qualification(doc, facts)

    results = build_substantive_review(qualification, facts)

    by_id = {item["review_item_id"]: item for item in results}
    assert by_id["SR-06"]["status"] == "PASS"
    assert by_id["SR-06"]["actual"]["value"] == {"minimum": 4.0, "maximum": 6.0}
    assert by_id["SR-06"]["external_dependency_status"] == "not_integrated"
    assert "JGJ 130" in by_id["SR-06"]["scope_notice"]


def test_large_meter_like_step_value_is_treated_as_millimeters() -> None:
    candidate = {
        "parameter": "standard_step_height",
        "value": 1500,
        "unit": "m",
        "raw_value": "1500",
        "raw_unit": "m",
    }

    result = normalize_candidate(candidate, "m")

    assert result["value"] == 1.5
    assert result["unit"] == "m"


def test_upper_limit_parameters_resolve_to_max_plausible_value() -> None:
    definition = {
        "parameter": "standard_step_height",
        "canonical_unit": "m",
        "resolution_mode": "max_numeric",
        "plausible_min": 0.1,
        "plausible_max": 5.0,
    }
    candidates = [
        {
            "value": 1.0,
            "unit": "m",
            "raw_value": "1000",
            "confidence": 0.95,
            "evidence_quality": "high",
            "evidence": {"physical_page": 1, "text": "顶层步距h'(mm) 1000"},
        },
        {
            "value": 1.5,
            "unit": "m",
            "raw_value": "1500",
            "confidence": 0.95,
            "evidence_quality": "high",
            "evidence": {"physical_page": 2, "text": "最大步距h(mm) 1500"},
        },
        {
            "value": 3001.5,
            "unit": "m",
            "raw_value": "3001500",
            "confidence": 0.95,
            "evidence_quality": "high",
            "evidence": {"physical_page": 3, "text": "误拼接数值 3001500"},
        },
    ]

    result = resolve_fact(definition, candidates)

    assert result["status"] == "confirmed"
    assert result["value"] == 1.5
    assert result["has_conflict"] is False


def test_review_summary_collects_human_review_queue() -> None:
    qualification = {
        "requires_human_review": True,
        "human_review_reason": "工程识别参数不足",
    }
    completeness = {
        "total_rules": 1,
        "pass_count": 0,
        "missing_count": 1,
        "uncertain_count": 0,
        "results": [
            {
                "rule_id": "HF-COMP-001",
                "name": "工程概况",
                "status": "MISSING",
                "reason": "未发现",
                "evidence": [],
            }
        ],
    }
    substantive = [
        {
            "review_item_id": "SR-03",
            "title": "可调托撑悬臂长度",
            "status": "REVIEW",
            "conclusion": "证据不足",
            "evidence": [],
            "basis": [],
        }
    ]

    result = build_review_results(qualification, completeness, substantive)

    assert result["summary"]["completeness_missing"] == 1
    assert result["summary"]["substantive_review"] == 1
    assert len(result["human_review_queue"]) == 3


def test_drawing_review_recalls_related_drawing_pages() -> None:
    doc = _document_with_pages(
        [
            (1, "text", "支撑架应沿高度每间隔4个~6个标准步距应设置水平剪刀撑。"),
            (2, "drawing", "水平剪刀撑平面布置图，支撑架剖面图。"),
        ]
    )
    facts = build_project_facts(doc)

    result = build_drawing_review(doc, facts)

    by_id = {item["review_item_id"]: item for item in result}
    assert by_id["DR-01"]["status"] == "REVIEW"
    assert by_id["DR-01"]["drawing_evidence"][0]["physical_page"] == 2
    assert by_id["DR-01"]["automation_level"] == "evidence_recall_only"


def test_consistency_review_compares_design_and_calculation_values() -> None:
    facts = {
        "facts": {
            "standard_step_height": {
                "value": 1.5,
                "unit": "m",
                "status": "confirmed",
                "candidates": [
                    {
                        "value": 1.5,
                        "unit": "m",
                        "raw_value": "1.5",
                        "source_role": "parameter_table",
                        "evidence": {"physical_page": 2, "text": "水平杆步距1.5m"},
                    },
                    {
                        "value": 1.5,
                        "unit": "m",
                        "raw_value": "1.5",
                        "source_role": "calculation",
                        "evidence": {"physical_page": 20, "text": "计算书 步距1.5m"},
                    },
                ],
            }
        }
    }

    result = build_consistency_review(facts)

    assert result[0]["status"] == "PASS"
    assert result[0]["automation_level"] == "parameter_consistency_only"


def test_review_summary_accepts_consistency_and_drawing_reviews() -> None:
    qualification = {"requires_human_review": False}
    completeness = {
        "total_rules": 0,
        "pass_count": 0,
        "missing_count": 0,
        "uncertain_count": 0,
        "results": [],
    }
    consistency = [
        {
            "review_item_id": "CR-01",
            "title": "水平杆标准步距",
            "status": "ISSUE",
            "conclusion": "正文/计算书不一致",
            "design_side": {"evidence": []},
            "calculation_side": {"evidence": []},
        }
    ]
    drawing = [
        {
            "review_item_id": "DR-01",
            "title": "水平剪刀撑图文复核",
            "status": "REVIEW",
            "conclusion": "需人工复核",
            "requires_human_review": True,
            "text_evidence": [],
            "drawing_evidence": [],
        }
    ]

    result = build_review_results(
        qualification,
        completeness,
        [],
        consistency_review=consistency,
        drawing_review=drawing,
    )

    assert result["summary"]["consistency_issue"] == 1
    assert result["summary"]["drawing_review"] == 1
    assert len(result["human_review_queue"]) == 2
