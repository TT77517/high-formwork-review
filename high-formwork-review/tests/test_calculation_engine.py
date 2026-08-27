from __future__ import annotations

from app.calculation_engine import (
    _evaluate_calculation,
    _extract_calculation_segments,
    run_calculation_engine,
)
from app.models import MinerUBlock, MinerUDocument, MinerUPage
from app.services.calculation_agent import trace_calculation_evidence


def _block(page: int, index: int, block_type: str, text: str) -> MinerUBlock:
    return MinerUBlock(
        block_id=f"p{page:04d}-b{index:04d}",
        physical_page=page,
        block_index=index,
        block_type=block_type,
        text=text,
        title_level=1 if block_type == "title" else None,
        bbox=None,
        image_path=None,
        table_html=None,
        source_file="demo",
        source_pointer=f"/{page - 1}/{index}",
    )


def _page(page: int, blocks: list[MinerUBlock]) -> MinerUPage:
    return MinerUPage(
        physical_page=page,
        source_page_index=page - 1,
        width=None,
        height=None,
        printed_page=str(page),
        page_type="text",
        parse_status="complete",
        text="\n".join(block.text for block in blocks),
        blocks=blocks,
    )


def test_calculation_segments_ignore_non_calculation_narrative() -> None:
    document = MinerUDocument(
        document_id="demo",
        source_file_name="demo.pdf",
        source_sha256="sha",
        physical_page_count=2,
        pages=[
            _page(1, [
                _block(1, 1, "title", "施工方法"),
                _block(1, 2, "paragraph", "支架搭设应关注长细比、稳定和承载力要求。"),
            ]),
            _page(2, [
                _block(2, 1, "title", "模板支架计算书"),
                _block(2, 2, "paragraph", "立杆长细比验算：λ = l0 / i = 141.5 ≤ 150，满足要求。"),
            ]),
        ],
    )

    segments = _extract_calculation_segments(document)

    assert [seg["block_id"] for seg in segments if seg["block_id"]] == [
        "p0002-b0001",
        "p0002-b0002",
    ]


def test_calculation_evidence_prefers_calculation_book_section() -> None:
    segments = [
        {
            "text": "施工方法说明：支架搭设应关注长细比。",
            "block_id": "p0001-b0002",
            "block_type": "paragraph",
            "physical_page": 1,
            "calculation_score": 0,
            "in_calculation_section": False,
        },
        {
            "text": "模板支架计算书：立杆长细比验算 λ = l0 / i = 141.5 ≤ 150。",
            "block_id": "p0002-b0002",
            "block_type": "paragraph",
            "physical_page": 2,
            "calculation_score": 8,
            "in_calculation_section": True,
        },
    ]
    rule = {
        "rule_id": "3.14",
        "rule_name": "长细比限值-盘扣式",
        "module": "03_structural_calculation",
        "check_type": "calculation",
        "severity": "A-mandatory",
        "risk_level": "high",
        "applicable_types": ["universal"],
        "code_ref": {},
        "check_logic": {"formula": "λ = l0/i ≤ 150"},
    }

    result = _evaluate_calculation(rule, "\n".join(seg["text"] for seg in segments), "pankou", segments)

    assert result["evidence"][0]["block_id"] == "p0002-b0002"
    assert result["evidence"][0]["in_calculation_section"] is True


def test_selected_rules_include_calculation_agent_trace() -> None:
    document = MinerUDocument(
        document_id="demo",
        source_file_name="demo.pdf",
        source_sha256="sha",
        physical_page_count=1,
        pages=[
            _page(1, [
                _block(1, 1, "title", "模板支架计算书"),
                _block(
                    1,
                    2,
                    "paragraph",
                    (
                        "荷载组合承载力极限状态采用1.3G+1.5Q。"
                        "混凝土侧压力F按0.22γc t0 β1 β2 V^0.5与γH取较小值。"
                        "地基承载力验算P=N/A底≤fa。"
                        "抗倾覆验算MR≥γ0MT，GB50666抗倾覆采用γ0Mo≤Mr。"
                    ),
                ),
            ])
        ],
    )

    result = run_calculation_engine(document, {"facts": {"support_system": {"value": "disk_lock"}}})
    by_id = {item["rule_id"]: item for item in result["results"]}

    for rule_id in ["2.8", "2.12", "3.19", "3.20", "3.25"]:
        assert by_id[rule_id]["route"] in {"agent_evidence", "deterministic_recheck"}
        assert by_id[rule_id]["calculation_agent"]["steps"]
        assert by_id[rule_id]["calculation_agent"]["evidence_ids"]


def test_foundation_bearing_recheck_passes_when_pressure_within_limit() -> None:
    document = MinerUDocument(
        document_id="demo",
        source_file_name="demo.pdf",
        source_sha256="sha",
        physical_page_count=1,
        pages=[
            _page(1, [
                _block(1, 1, "title", "模板支架计算书"),
                _block(1, 2, "paragraph", "地基承载力验算：P=80kPa≤fa=120kPa，满足要求。"),
            ])
        ],
    )

    result = run_calculation_engine(document, {"facts": {"support_system": {"value": "disk_lock"}}})
    item = {row["rule_id"]: row for row in result["results"]}["3.19"]

    assert item["route"] == "deterministic_recheck"
    assert item["status"] == "COMPLIANT"
    assert item["calculation_recheck"]["formula_id"] == "foundation_bearing"
    assert item["calculation_agent"]["evidence_ids"]


def test_foundation_bearing_recheck_flags_exceedance() -> None:
    document = MinerUDocument(
        document_id="demo",
        source_file_name="demo.pdf",
        source_sha256="sha",
        physical_page_count=1,
        pages=[
            _page(1, [
                _block(1, 1, "title", "模板支架计算书"),
                _block(1, 2, "paragraph", "地基承载力验算：P=150kPa≤fa=120kPa。"),
            ])
        ],
    )

    result = run_calculation_engine(document, {"facts": {"support_system": {"value": "disk_lock"}}})
    item = {row["rule_id"]: row for row in result["results"]}["3.19"]

    assert item["route"] == "deterministic_recheck"
    assert item["status"] == "VIOLATED"
    assert item["calculation_recheck"]["status"] == "ISSUE"


def test_load_combination_recheck_detects_ultimate_coefficients() -> None:
    document = MinerUDocument(
        document_id="demo",
        source_file_name="demo.pdf",
        source_sha256="sha",
        physical_page_count=1,
        pages=[
            _page(1, [
                _block(1, 1, "title", "模板支架计算书"),
                _block(1, 2, "paragraph", "荷载组合：承载能力极限状态S=1.3G+1.5Q。"),
            ])
        ],
    )

    result = run_calculation_engine(document, {"facts": {"support_system": {"value": "disk_lock"}}})
    item = {row["rule_id"]: row for row in result["results"]}["2.12"]

    assert item["route"] == "deterministic_recheck"
    assert item["status"] == "COMPLIANT"
    assert item["calculation_recheck"]["formula_id"] == "load_combination"


def test_side_pressure_recheck_jgj162_uses_022_beta1_beta2_formula() -> None:
    document = MinerUDocument(
        document_id="demo",
        source_file_name="demo.pdf",
        source_sha256="sha",
        physical_page_count=1,
        pages=[
            _page(1, [
                _block(1, 1, "title", "模板支架计算书"),
                _block(
                    1,
                    2,
                    "paragraph",
                    "混凝土侧压力验算：γc=24kN/m³，t0=5h，β1=1.0，β2=1.15，V=2m/h，H=3m，F=43.0kN/m²。",
                ),
            ])
        ],
    )

    result = run_calculation_engine(document, {"facts": {"support_system": {"value": "disk_lock"}}})
    item = {row["rule_id"]: row for row in result["results"]}["2.8"]

    assert item["route"] == "deterministic_recheck"
    assert item["status"] == "COMPLIANT"
    assert item["calculation_recheck"]["formula_id"] == "side_pressure"


def test_side_pressure_recheck_gb50666_uses_028_single_beta_formula() -> None:
    document = MinerUDocument(
        document_id="demo",
        source_file_name="demo.pdf",
        source_sha256="sha",
        physical_page_count=1,
        pages=[
            _page(1, [
                _block(1, 1, "title", "模板支架计算书"),
                _block(
                    1,
                    2,
                    "paragraph",
                    "GB50666混凝土侧压力验算：γc=24kN/m³，t0=5h，β=1.0，V=2m/h，H=3m，坍落度=160mm，F=47.5kN/m²。",
                ),
            ])
        ],
    )

    result = run_calculation_engine(document, {"facts": {"support_system": {"value": "disk_lock"}}})
    item = {row["rule_id"]: row for row in result["results"]}["2.19"]

    assert item["route"] == "deterministic_recheck"
    assert item["status"] == "COMPLIANT"
    assert item["calculation_recheck"]["allowed_value"] == 47.5176
    conditions = item["applicability_conditions"]
    assert any("V≤10m/h" in condition["condition"] for condition in conditions)
    assert any("F=γc·H" in condition["expected"] for condition in conditions)


def test_side_pressure_recheck_flags_wrong_reported_value() -> None:
    document = MinerUDocument(
        document_id="demo",
        source_file_name="demo.pdf",
        source_sha256="sha",
        physical_page_count=1,
        pages=[
            _page(1, [
                _block(1, 1, "title", "模板支架计算书"),
                _block(
                    1,
                    2,
                    "paragraph",
                    "GB50666混凝土侧压力验算：γc=24kN/m³，t0=5h，β=1.0，V=2m/h，H=3m，坍落度=160mm，F=60.0kN/m²。",
                ),
            ])
        ],
    )

    result = run_calculation_engine(document, {"facts": {"support_system": {"value": "disk_lock"}}})
    item = {row["rule_id"]: row for row in result["results"]}["2.19"]

    assert item["route"] == "deterministic_recheck"
    assert item["status"] == "VIOLATED"
    assert item["calculation_recheck"]["status"] == "ISSUE"


def test_side_pressure_condition_evaluation_selects_hydrostatic_branch() -> None:
    document = MinerUDocument(
        document_id="demo",
        source_file_name="demo.pdf",
        source_sha256="sha",
        physical_page_count=1,
        pages=[
            _page(1, [
                _block(1, 1, "title", "模板支架计算书"),
                _block(
                    1,
                    2,
                    "paragraph",
                    "GB50666混凝土侧压力验算：γc=24kN/m³，V=12m/h，H=3m，坍落度=160mm，F=72kN/m²。",
                ),
            ])
        ],
    )

    result = run_calculation_engine(document, {"facts": {"support_system": {"value": "disk_lock"}}})
    item = {row["rule_id"]: row for row in result["results"]}["2.19"]

    assert item["status"] == "COMPLIANT"
    assert item["condition_evaluation"]["selected_branch"] == "hydrostatic_gamma_h"
    assert item["calculation_agent"]["condition_evaluation"]["selected_branch"] == "hydrostatic_gamma_h"


def test_side_pressure_condition_is_unknown_when_velocity_missing() -> None:
    document = MinerUDocument(
        document_id="demo",
        source_file_name="demo.pdf",
        source_sha256="sha",
        physical_page_count=1,
        pages=[
            _page(1, [
                _block(1, 1, "title", "模板支架计算书"),
                _block(
                    1,
                    2,
                    "paragraph",
                    "GB50666混凝土侧压力验算：γc=24kN/m³，H=3m，坍落度=160mm。",
                ),
            ])
        ],
    )

    result = run_calculation_engine(document, {"facts": {"support_system": {"value": "disk_lock"}}})
    item = {row["rule_id"]: row for row in result["results"]}["2.19"]

    assert item["condition_evaluation"]["selected_branch"] == "unknown"
    assert item["condition_evaluation"]["items"][0]["status"] == "UNKNOWN"


def test_jack_capacity_recheck_still_runs_after_new_recheckers() -> None:
    document = MinerUDocument(
        document_id="demo",
        source_file_name="demo.pdf",
        source_sha256="sha",
        physical_page_count=1,
        pages=[
            _page(1, [
                _block(1, 1, "title", "模板支架计算书"),
                _block(1, 2, "paragraph", "可调托撑承载力验算：N=30kN≤Nd=40kN，满足要求。"),
            ])
        ],
    )

    result = run_calculation_engine(document, {"facts": {"support_system": {"value": "coupler"}}})
    item = {row["rule_id"]: row for row in result["results"]}["3.17"]

    assert item["route"] == "deterministic_recheck"
    assert item["status"] == "COMPLIANT"
    assert item["calculation_recheck"]["formula_id"] == "jack_capacity"


def test_pankou_jack_capacity_uses_pankou_design_capacity() -> None:
    document = MinerUDocument(
        document_id="demo",
        source_file_name="demo.pdf",
        source_sha256="sha",
        physical_page_count=1,
        pages=[
            _page(1, [
                _block(1, 1, "title", "模板支架计算书"),
                _block(1, 2, "paragraph", "盘扣式可调托撑承载力验算：N=90kN≤Nd=100kN，满足要求。"),
            ])
        ],
    )

    result = run_calculation_engine(document, {"facts": {"support_system": {"value": "disk_lock"}}})
    item = {row["rule_id"]: row for row in result["results"]}["3.17p"]

    assert item["route"] == "deterministic_recheck"
    assert item["status"] == "COMPLIANT"
    assert item["calculation_recheck"]["allowed_value"] == 100.0


def test_overturning_recheck_passes_with_explicit_moments() -> None:
    document = MinerUDocument(
        document_id="demo",
        source_file_name="demo.pdf",
        source_sha256="sha",
        physical_page_count=1,
        pages=[
            _page(1, [
                _block(1, 1, "title", "模板支架计算书"),
                _block(1, 2, "paragraph", "抗倾覆验算：MR=180kN·m，MT=120kN·m，γ0=1.2，满足要求。"),
            ])
        ],
    )

    result = run_calculation_engine(document, {"facts": {"support_system": {"value": "disk_lock"}}})
    item = {row["rule_id"]: row for row in result["results"]}["3.20"]

    assert item["route"] == "deterministic_recheck"
    assert item["status"] == "COMPLIANT"
    assert item["calculation_recheck"]["formula_id"] == "overturning"


def test_overturning_recheck_flags_insufficient_resisting_moment() -> None:
    document = MinerUDocument(
        document_id="demo",
        source_file_name="demo.pdf",
        source_sha256="sha",
        physical_page_count=1,
        pages=[
            _page(1, [
                _block(1, 1, "title", "模板支架计算书"),
                _block(1, 2, "paragraph", "抗倾覆验算：MR=120kN·m，MT=120kN·m，γ0=1.2。"),
            ])
        ],
    )

    result = run_calculation_engine(document, {"facts": {"support_system": {"value": "disk_lock"}}})
    item = {row["rule_id"]: row for row in result["results"]}["3.20"]

    assert item["route"] == "deterministic_recheck"
    assert item["status"] == "VIOLATED"
    assert item["calculation_recheck"]["status"] == "ISSUE"


def test_pankou_top_step_condition_triggers_when_b_type_load_exceeds_40kn() -> None:
    document = MinerUDocument(
        document_id="demo",
        source_file_name="demo.pdf",
        source_sha256="sha",
        physical_page_count=1,
        pages=[
            _page(1, [
                _block(1, 1, "title", "模板支架计算书"),
                _block(
                    1,
                    2,
                    "paragraph",
                    "盘扣标准型B型支撑架，单肢立杆荷载设计值=45kN，顶层步距缩小0.5m。",
                ),
            ])
        ],
    )

    result = run_calculation_engine(document, {"facts": {"support_system": {"value": "disk_lock"}}})
    item = {row["rule_id"]: row for row in result["results"]}["3.22"]

    assert item["route"] == "agent_evidence"
    assert item["condition_evaluation"]["selected_branch"] == "top_step_must_reduce"
    assert item["condition_evaluation"]["items"][0]["status"] == "TRIGGERED"
    assert item["calculation_agent"]["steps"][0]["action"] == "evaluate_applicability_conditions"


def test_pankou_top_step_agent_requires_reduction_phrase() -> None:
    document = MinerUDocument(
        document_id="demo",
        source_file_name="demo.pdf",
        source_sha256="sha",
        physical_page_count=1,
        pages=[
            _page(1, [
                _block(1, 1, "title", "模板支架计算书"),
                _block(
                    1,
                    2,
                    "paragraph",
                    "盘扣标准型B型支撑架，单肢立杆荷载设计值=45kN，顶层步距按方案布置。",
                ),
            ])
        ],
    )

    result = run_calculation_engine(document, {"facts": {"support_system": {"value": "disk_lock"}}})
    item = {row["rule_id"]: row for row in result["results"]}["3.22"]

    assert item["condition_evaluation"]["selected_branch"] == "top_step_must_reduce"
    assert "顶层步距缩小措施" in item["calculation_agent"]["missing"]


def test_calculation_rules_are_gated_by_support_system() -> None:
    document = MinerUDocument(
        document_id="demo",
        source_file_name="demo.pdf",
        source_sha256="sha",
        physical_page_count=1,
        pages=[
            _page(1, [
                _block(1, 1, "title", "模板支架计算书"),
                _block(
                    1,
                    2,
                    "paragraph",
                    "立杆轴力、计算长度、稳定性、长细比、扣件抗滑移、连墙件、托撑承载力验算。",
                ),
            ])
        ],
    )

    pankou = run_calculation_engine(document, {"facts": {"support_system": {"value": "disk_lock"}}})
    coupler = run_calculation_engine(document, {"facts": {"support_system": {"value": "coupler"}}})
    other = run_calculation_engine(document, {"facts": {"support_system": {"value": "other"}}})

    pankou_by_id = {row["rule_id"]: row for row in pankou["results"]}
    coupler_by_id = {row["rule_id"]: row for row in coupler["results"]}
    other_by_id = {row["rule_id"]: row for row in other["results"]}

    for rule_id in ["3.8", "3.11", "3.16", "3.17", "3.18", "3.26", "3.27"]:
        assert pankou_by_id[rule_id]["status"] == "NOT_APPLICABLE"
        assert coupler_by_id[rule_id]["status"] != "NOT_APPLICABLE"

    for rule_id in ["3.8a", "3.9", "3.10", "3.12", "3.13", "3.14", "3.17p", "3.20", "3.21", "3.22"]:
        assert pankou_by_id[rule_id]["status"] != "NOT_APPLICABLE"
        assert coupler_by_id[rule_id]["status"] == "NOT_APPLICABLE"

    assert other_by_id["3.15"]["status"] != "NOT_APPLICABLE"
    assert pankou_by_id["3.15"]["status"] == "NOT_APPLICABLE"
    assert coupler_by_id["3.15"]["status"] == "NOT_APPLICABLE"


def test_koujian_stability_recheck_runs_for_coupler_system() -> None:
    document = MinerUDocument(
        document_id="demo",
        source_file_name="demo.pdf",
        source_sha256="sha",
        physical_page_count=1,
        pages=[
            _page(1, [
                _block(1, 1, "title", "模板支架计算书"),
                _block(1, 2, "paragraph", "扣件式立杆稳定性验算：σ=180N/mm²≤f=205N/mm²，满足要求。"),
            ])
        ],
    )

    result = run_calculation_engine(document, {"facts": {"support_system": {"value": "coupler"}}})
    item = {row["rule_id"]: row for row in result["results"]}["3.27"]

    assert item["route"] == "deterministic_recheck"
    assert item["status"] == "COMPLIANT"
    assert item["calculation_recheck"]["formula_id"] == "vertical_stability"


def test_calculation_agent_falls_back_to_shared_search_document_tool() -> None:
    document = MinerUDocument(
        document_id="demo",
        source_file_name="demo.pdf",
        source_sha256="sha",
        physical_page_count=1,
        pages=[
            _page(1, [
                _block(1, 1, "paragraph", "计算书 地基承载力验算P=80kPa≤fa=120kPa。"),
            ])
        ],
    )
    rule = {
        "rule_id": "3.19",
        "rule_name": "地基承载力验算",
        "check_logic": {"extraction_keywords": ["地基", "承载力", "fa"]},
    }

    agent = trace_calculation_evidence(rule, document, [])

    assert agent["steps"][1]["action"] == "search_document"
    assert agent["evidence_ids"]
