"""计算参数依赖 / 符号化抽取 / 图纸几何 反哺测试。"""

from __future__ import annotations

from app.calculation_dependencies import (
    CALCULATION_PARAMETER_DEPENDENCIES,
    all_dependency_parameters,
    calculation_impacts_for_parameter,
    dependencies_by_formula,
    parameters_for_calculation_rule,
    parameters_for_formula_id,
)
from app.drawing_geometry import (
    DRAWING_GEOMETRY_PARAMS,
    _is_drawing_page,
    cross_validate_with_body_facts,
    extract_drawing_geometry_candidates,
)
from app.models import MinerUBlock, MinerUDocument, MinerUPage
from app.parameter_definitions import get_parameter_definitions
from app.parameter_extractor import (
    ParameterEvidence,
    _normalize_symbol_text,
    extract_parameter_candidates,
)


# ---------------------------------------------------------------------------
# calculation_dependencies 覆盖
# ---------------------------------------------------------------------------


def test_dependency_covers_side_pressure_rules() -> None:
    params = parameters_for_calculation_rule("2.19")
    assert "concrete_unit_weight" in params
    assert "initial_set_time" in params
    assert "pouring_speed" in params
    # 2.8 (JGJ162) 与 2.19 (GB50666) 应被同一些参数覆盖
    params_28 = parameters_for_calculation_rule("2.8")
    assert "concrete_unit_weight" in params_28
    assert "slump" in params_28


def test_dependency_covers_panel_stringer_rules() -> None:
    for rule_id in ("3.1", "3.2", "3.3"):
        params = parameters_for_calculation_rule(rule_id)
        assert "panel_thickness" in params, rule_id
    for rule_id in ("3.4", "3.5"):
        params = parameters_for_calculation_rule(rule_id)
        assert "stringer_section_height" in params
    for rule_id in ("3.6", "3.7"):
        params = parameters_for_calculation_rule(rule_id)
        assert "main_beam_section_height" in params


def test_dependency_covers_foundation_and_overturning() -> None:
    f_params = parameters_for_calculation_rule("3.19")
    assert "vertical_axial_force" in f_params
    assert "base_plate_area" in f_params
    assert "foundation_bearing_capacity" in f_params

    for rule_id in ("3.20", "3.25"):
        o_params = parameters_for_calculation_rule(rule_id)
        assert "structure_importance_factor" in o_params
        assert "resisting_moment" in o_params
        assert "overturning_moment" in o_params


def test_calculation_impacts_includes_reason() -> None:
    impacts = calculation_impacts_for_parameter("concrete_unit_weight")
    assert impacts, "concrete_unit_weight 应至少有 1 条影响"
    for item in impacts:
        assert "rule_id" in item
        assert "reason" in item
        assert item["reason"]


def test_parameters_for_formula_id_aggregates() -> None:
    # side_pressure 同时被 2.8 与 2.19 引用
    params = parameters_for_formula_id("side_pressure")
    assert {"concrete_unit_weight", "initial_set_time", "pouring_speed", "side_pressure_height"} <= params


def test_dependencies_by_formula_keys() -> None:
    grouped = dependencies_by_formula()
    assert "side_pressure" in grouped
    assert "foundation_bearing" in grouped
    assert "overturning" in grouped
    assert any(d["parameter"] == "concrete_unit_weight" for d in grouped["side_pressure"])


def test_legacy_dependencies_preserved() -> None:
    """回归保护：原有 4 个参数 + 7 条规则不变。"""
    assert "standard_step_height" in CALCULATION_PARAMETER_DEPENDENCIES
    assert "head_jack_cantilever_length" in CALCULATION_PARAMETER_DEPENDENCIES
    assert "personnel_equipment_load_standard" in CALCULATION_PARAMETER_DEPENDENCIES
    assert "horizontal_scissor_brace_interval" in CALCULATION_PARAMETER_DEPENDENCIES
    legacy = calculation_impacts_for_parameter("standard_step_height")
    rule_ids = {impact["rule_id"] for impact in legacy}
    assert {"3.11", "3.14", "3.9", "3.27"} <= rule_ids


def test_all_dependency_parameters_returns_unique() -> None:
    params = all_dependency_parameters()
    assert len(params) == len(CALCULATION_PARAMETER_DEPENDENCIES)
    # 新参数必须出现
    for must in [
        "concrete_unit_weight",
        "initial_set_time",
        "panel_thickness",
        "stringer_section_height",
        "vertical_axial_force",
        "foundation_bearing_capacity",
        "structure_importance_factor",
    ]:
        assert must in params


# ---------------------------------------------------------------------------
# parameter_definitions / symbolic_numeric 抽取
# ---------------------------------------------------------------------------


def test_calculation_input_params_defined() -> None:
    defs = {d["parameter"]: d for d in get_parameter_definitions()}
    for must in [
        "concrete_unit_weight",
        "initial_set_time",
        "side_pressure_height",
        "slump",
        "beta_correction",
        "beta1_correction",
        "beta2_correction",
        "panel_section_width",
        "panel_stringer_spacing",
        "stringer_section_width",
        "stringer_section_height",
        "stringer_spacing",
        "main_beam_section_width",
        "main_beam_section_height",
        "main_beam_spacing",
        "vertical_axial_force",
        "base_plate_area",
        "foundation_bearing_capacity",
        "structure_importance_factor",
        "resisting_moment",
        "overturning_moment",
        "wind_load",
        "wind_pressure_height",
    ]:
        assert must in defs, f"{must} 必须出现在 parameter_definitions"
        if defs[must].get("extraction_mode") == "symbolic_numeric":
            assert defs[must].get("symbol_labels"), f"{must} 缺 symbol_labels"


def test_symbolic_numeric_extraction_picks_gamma_c() -> None:
    defs = {d["parameter"]: d for d in get_parameter_definitions()}
    param = defs["concrete_unit_weight"]
    block = _block("侧压力验算：γc=24kN/m³，t0=4h，V=2m/h，H=4.5m，坍落度=160mm。")
    evidence = _evidence([block])
    cands = extract_parameter_candidates(evidence, param)
    assert cands, "应至少提取 1 个 γc 候选"
    assert cands[0]["value"] == 24.0


def test_symbolic_numeric_extraction_respects_plausible_range() -> None:
    """超出 plausible 范围的值（如误抓 1.0 系数）应被过滤。"""
    defs = {d["parameter"]: d for d in get_parameter_definitions()}
    param = defs["concrete_unit_weight"]  # plausible 22-27
    # γc=1.0 显然是误抓，应被排除
    block = _block("侧压力公式系数γc=1.0不应作为重力密度。")
    evidence = _evidence([block])
    cands = extract_parameter_candidates(evidence, param)
    assert not cands, "plausible 范围外的值必须被过滤"


def test_symbolic_numeric_handles_latex_fragments() -> None:
    """LaTeX 残片 \\gamma_c / \\beta1 应被归一化为 γc / β1 后抽取。"""
    text = _normalize_symbol_text(
        "侧压力计算：\\gamma_c=25kN/m³，\\beta1=1.2，\\beta2=1.0。"
    )
    assert "γc" in text
    assert "β1" in text
    assert "β2" in text


def test_symbolic_numeric_handles_kPa_fa() -> None:
    defs = {d["parameter"]: d for d in get_parameter_definitions()}
    param = defs["foundation_bearing_capacity"]
    block = _block("地基承载力验算：P=85kPa，fa=150kPa。")
    evidence = _evidence([block])
    cands = extract_parameter_candidates(evidence, param)
    assert cands, "应识别 fa=150kPa"
    assert cands[0]["value"] == 150.0


def test_symbolic_numeric_handles_gamma0() -> None:
    defs = {d["parameter"]: d for d in get_parameter_definitions()}
    param = defs["structure_importance_factor"]
    block = _block("抗倾覆验算：γ0=1.0，MR=80kN·m，MT=30kN·m。")
    evidence = _evidence([block])
    cands = extract_parameter_candidates(evidence, param)
    assert cands
    assert cands[0]["value"] == 1.0


def test_symbolic_numeric_handles_table_format() -> None:
    defs = {d["parameter"]: d for d in get_parameter_definitions()}
    param = defs["concrete_unit_weight"]
    block = _block("混凝土容重 24 kN/m³", block_type="table")
    evidence = _evidence([block])
    cands = extract_parameter_candidates(evidence, param)
    assert cands
    assert cands[0]["value"] == 24.0
    assert cands[0]["confidence"] >= 0.9


# ---------------------------------------------------------------------------
# drawing_geometry 抽取 + 反哺
# ---------------------------------------------------------------------------


def test_drawing_geometry_extracts_spacing_from_drawing_page() -> None:
    doc = _make_doc(
        pages=[
            _page(1, [_block_text(1, "目录与说明。")]),
            _page(2, [
                _block_text(2, "立面图：立杆纵距 0.9m，立杆横距 0.9m，标准步距 1.5m。"),
            ]),
        ]
    )
    cands = extract_drawing_geometry_candidates(doc)
    ids = {c["fact_id"] for c in cands}
    assert "vertical_spacing" in ids
    assert "horizontal_spacing" in ids
    assert "standard_step_height" in ids


def test_drawing_geometry_skips_non_drawing_page() -> None:
    doc = _make_doc(
        pages=[
            _page(1, [_block_text(
                1,
                "本工程位于北京市朝阳区，建筑面积约 1.2 万平方米，立杆纵距 0.9m 仅供参考说明。",
            )]),
        ]
    )
    cands = extract_drawing_geometry_candidates(doc)
    # 该页是说明性正文，文本较长且无图纸关键词 → 应被跳过
    assert cands == []


def test_drawing_geometry_respects_plausible_range() -> None:
    """超出 plausible_max 的值（如把"立面图 100"误抓为步距）应被过滤。"""
    doc = _make_doc(
        pages=[
            _page(1, [_block_text(1, "立面图：标准步距 100mm 是图号。")]),
        ]
    )
    cands = extract_drawing_geometry_candidates(doc)
    standard_step = [c for c in cands if c["fact_id"] == "standard_step_height"]
    # 100mm=0.1m < plausible_min 0.5 → 被过滤
    assert standard_step == []


def test_cross_validate_match_and_conflict() -> None:
    body_facts = {
        "vertical_spacing": {"value": 0.9, "unit": "m"},
        "standard_step_height": {"value": 1.5, "unit": "m"},
    }
    drawing_cands = [
        {"fact_id": "vertical_spacing", "name": "立杆纵距", "value": 0.9, "page": 5, "block_id": "p5-1"},
        {"fact_id": "standard_step_height", "name": "步距", "value": 1.8, "page": 5, "block_id": "p5-2"},
    ]
    issues = cross_validate_with_body_facts(drawing_cands, body_facts)
    by_id = {i["fact_id"]: i for i in issues}
    assert by_id["vertical_spacing"]["status"] == "MATCH"
    assert by_id["standard_step_height"]["status"] == "CONFLICT"
    assert by_id["standard_step_height"]["diff_ratio"] > 0.05


def test_cross_validate_supplement_when_body_missing() -> None:
    body_facts: dict = {}  # 正文未识别
    drawing_cands = [
        {"fact_id": "sweeper_centerline_height_above_base_plate", "name": "扫地杆高度",
         "value": 200, "page": 7, "block_id": "p7-3"},
    ]
    issues = cross_validate_with_body_facts(drawing_cands, body_facts)
    assert len(issues) == 1
    assert issues[0]["status"] == "SUPPLEMENT"
    assert issues[0]["drawing_value"] == 200


def test_cross_validate_skips_zero_body_value() -> None:
    body_facts = {"standard_step_height": {"value": 0}}
    drawing_cands = [
        {"fact_id": "standard_step_height", "name": "步距", "value": 1.5, "page": 5, "block_id": "p5-1"},
    ]
    issues = cross_validate_with_body_facts(drawing_cands, body_facts)
    assert issues == []


def test_drawing_geometry_params_complete() -> None:
    """DRAWING_GEOMETRY_PARAMS 必须包含核心构造参数。"""
    ids = {p["fact_id"] for p in DRAWING_GEOMETRY_PARAMS}
    for must in [
        "vertical_spacing", "horizontal_spacing", "standard_step_height",
        "sweeper_centerline_height_above_base_plate",
        "head_jack_cantilever_length", "base_plate_area",
    ]:
        assert must in ids, f"必须覆盖 {must}"


# ---------------------------------------------------------------------------
# 代码审查回归保护
# ---------------------------------------------------------------------------


def test_is_drawing_page_rejects_blank_page() -> None:
    """空白页（无文本）不应被误判为图纸页。"""
    page = _page(1, [])
    assert _is_drawing_page(page) is False


def test_is_drawing_page_rejects_pure_text_page() -> None:
    """纯正文页（文本长但无图纸关键词）不应被误判。"""
    page = _page(1, [_block_text(1, "本工程位于北京市朝阳区，建筑面积 1.2 万平方米，结构形式为框架结构。")])
    assert _is_drawing_page(page) is False


def test_is_drawing_page_accepts_page_type_drawing() -> None:
    """page_type='drawing' 直接判定为图纸页。"""
    blocks = [_block_text(1, "任意内容均可。")]
    blocks[0].block_type = "image"  # not relevant
    page = _page_with_type(1, blocks, "drawing")
    assert _is_drawing_page(page) is True


def test_is_drawing_page_short_text_with_keyword() -> None:
    """短文本（<30 字符）含 1 个图纸关键词应判定为图纸页。"""
    page = _page(1, [_block_text(1, "立面图：横距 0.9m")])
    assert _is_drawing_page(page) is True


def test_latex_beta_does_not_match_betac() -> None:
    """\\betac 这样的伪词不应被归一化为 βc（应保留原样或归为 β）。"""
    normalized = _normalize_symbol_text(r"\betac=1.5")
    # \\betac 后面跟 c 字符 → 不应错误归一为 βc；我们的正则要求 \\beta 后面不能跟 \\w
    assert "β" not in normalized or normalized == r"\betac=1.5", (
        f"\\betac 不应被错误归一化为 βc，得到: {normalized!r}"
    )


def test_base_plate_area_uses_mm2_unit() -> None:
    """base_plate_area canonical_unit 应为 mm²（避免与 m² 混淆）。"""
    defs = {d["parameter"]: d for d in get_parameter_definitions()}
    assert defs["base_plate_area"]["canonical_unit"] == "mm2"
    assert defs["base_plate_area"]["plausible_min"] >= 100  # 0.01 m² = 10000 mm²



# ---------------------------------------------------------------------------
# 共享测试辅助
# ---------------------------------------------------------------------------


def _block(text: str, block_type: str = "paragraph") -> MinerUBlock:
    return MinerUBlock(
        block_id=f"b-{abs(hash(text)) % 10000:04d}",
        physical_page=1,
        block_index=1,
        block_type=block_type,
        text=text,
        title_level=1 if block_type == "title" else None,
        bbox=None,
        image_path=None,
        table_html=None,
        source_file="demo",
        source_pointer="/0/0",
    )


def _block_text(page: int, text: str) -> MinerUBlock:
    return MinerUBlock(
        block_id=f"p{page:04d}-b0001",
        physical_page=page,
        block_index=1,
        block_type="paragraph",
        text=text,
        title_level=None,
        bbox=None,
        image_path=None,
        table_html=None,
        source_file="demo",
        source_pointer=f"/{page - 1}/0",
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
        text="\n".join(b.text for b in blocks),
        blocks=blocks,
    )


def _page_with_type(page: int, blocks: list[MinerUBlock], page_type: str) -> MinerUPage:
    return MinerUPage(
        physical_page=page,
        source_page_index=page - 1,
        width=None,
        height=None,
        printed_page=str(page),
        page_type=page_type,
        parse_status="complete",
        text="\n".join(b.text for b in blocks),
        blocks=blocks,
    )


def _make_doc(pages: list[MinerUPage]) -> MinerUDocument:
    return MinerUDocument(
        document_id="DOC-GEOM",
        source_file_name="demo.pdf",
        source_sha256="sha",
        physical_page_count=len(pages),
        pages=pages,
    )


def _evidence(blocks: list[MinerUBlock]) -> list[ParameterEvidence]:
    """包装为 ParameterEvidence 列表。"""
    if blocks:
        page = _page(1, blocks)
        return [
            ParameterEvidence(
                block=blocks[0],
                page=page,
                source_role="body",
                evidence_quality="high",
                is_toc=False,
                section_path="计算书",
                score=0.9,
            )
        ]
    return []
