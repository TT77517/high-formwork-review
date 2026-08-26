"""参数与计算校核规则的影响关系。

集中管理"参数 → 公式规则"的依赖映射，供：

* 计算结果展示"参数 → 影响公式验算"反向追溯
* 人工复核参数修正时列出受影响公式规则
* 路由分流（参数缺失时把对应公式规则升级为人工确认）

依赖项结构：
    parameter: ProjectFacts 中的参数键
    rule_id:   受影响的计算规则编号
    rule_name: 规则名（冗余便于展示/审计）
    formula_id: 公式标识（对接 calculation_rechecker/condition_evaluator）
    relationship: 关系类型
        - direct_input     直接作为公式输入
        - condition_input  作为适用条件/分支选择输入
        - stability_assumption 影响稳定验算的边界假定
    reason:  解释该参数为何影响该公式规则
"""

from __future__ import annotations

from typing import Any


# ---------------------------------------------------------------------------
# 已有参数：步距 / 顶托悬臂 / 人员设备荷载 / 水平剪刀撑间隔
# ---------------------------------------------------------------------------
_LEGACY_DEPENDENCIES: dict[str, list[dict[str, Any]]] = {
    "standard_step_height": [
        {
            "rule_id": "3.11",
            "rule_name": "立杆长细比验算",
            "formula_id": "slenderness",
            "relationship": "direct_input",
            "reason": "步距影响立杆计算长度 l0，进而影响长细比 λ。",
        },
        {
            "rule_id": "3.14",
            "rule_name": "立杆长细比验算",
            "formula_id": "slenderness",
            "relationship": "direct_input",
            "reason": "步距影响立杆计算长度 l0，进而影响长细比 λ。",
        },
        {
            "rule_id": "3.9",
            "rule_name": "立杆稳定性验算",
            "formula_id": "vertical_stability",
            "relationship": "direct_input",
            "reason": "步距影响计算长度和稳定系数，进而影响立杆稳定承载能力。",
        },
        {
            "rule_id": "3.12",
            "rule_name": "立杆稳定性验算",
            "formula_id": "vertical_stability",
            "relationship": "direct_input",
            "reason": "步距影响计算长度和稳定系数，进而影响立杆稳定承载能力。",
        },
        {
            "rule_id": "3.15",
            "rule_name": "立杆稳定性验算",
            "formula_id": "vertical_stability",
            "relationship": "direct_input",
            "reason": "步距影响计算长度和稳定系数，进而影响立杆稳定承载能力。",
        },
        {
            "rule_id": "3.27",
            "rule_name": "立杆稳定性验算-扣件式",
            "formula_id": "vertical_stability",
            "relationship": "direct_input",
            "reason": "步距 h 进入 l0=k·μ·h，进而影响立杆稳定。",
        },
        {
            "rule_id": "3.26",
            "rule_name": "立杆计算长度-扣件式",
            "formula_id": "calculation_length_koujian",
            "relationship": "direct_input",
            "reason": "步距 h 是扣件式 l0=k·μ·h 公式的输入。",
        },
        {
            "rule_id": "3.22",
            "rule_name": "顶层水平杆步距缩小条件",
            "formula_id": None,
            "relationship": "condition_input",
            "reason": "顶层步距是否缩小属于盘扣顶层稳定条件判定。",
        },
    ],
    "head_jack_cantilever_length": [
        {
            "rule_id": "3.17",
            "rule_name": "可调托撑承载力验算",
            "formula_id": "jack_capacity",
            "relationship": "condition_input",
            "reason": "托撑悬臂长度影响可调托撑承载力限值选取。",
        },
        {
            "rule_id": "3.17p",
            "rule_name": "盘扣可调托撑承载力验算",
            "formula_id": "jack_capacity",
            "relationship": "condition_input",
            "reason": "托撑悬臂长度影响盘扣可调托撑承载力限值选取。",
        },
        {
            "rule_id": "3.9",
            "rule_name": "立杆稳定性验算",
            "formula_id": "vertical_stability",
            "relationship": "stability_assumption",
            "reason": "顶托悬臂过大时会改变立杆顶部约束与稳定验算假定。",
        },
        {
            "rule_id": "3.12",
            "rule_name": "立杆稳定性验算",
            "formula_id": "vertical_stability",
            "relationship": "stability_assumption",
            "reason": "顶托悬臂过大时会改变立杆顶部约束与稳定验算假定。",
        },
    ],
    "personnel_equipment_load_standard": [
        {
            "rule_id": "2.4",
            "rule_name": "施工人员及设备荷载标准值",
            "formula_id": None,
            "relationship": "direct_input",
            "reason": "施工人员及设备荷载是施工可变荷载输入。",
        },
        {
            "rule_id": "2.12",
            "rule_name": "荷载组合分项系数",
            "formula_id": "load_combination",
            "relationship": "direct_input",
            "reason": "施工可变荷载进入承载能力极限状态荷载组合。",
        },
        {
            "rule_id": "2.23",
            "rule_name": "荷载组合分项系数",
            "formula_id": "load_combination",
            "relationship": "direct_input",
            "reason": "施工可变荷载进入承载能力极限状态荷载组合。",
        },
        {
            "rule_id": "3.8",
            "rule_name": "立杆轴力设计值",
            "formula_id": "vertical_stability",
            "relationship": "direct_input",
            "reason": "施工活荷载影响立杆轴力 N，进而影响稳定验算。",
        },
    ],
    "horizontal_scissor_brace_interval": [
        {
            "rule_id": "3.9",
            "rule_name": "立杆稳定性验算",
            "formula_id": "vertical_stability",
            "relationship": "stability_assumption",
            "reason": "水平剪刀撑设置影响架体整体稳定计算假定。",
        },
        {
            "rule_id": "3.12",
            "rule_name": "立杆稳定性验算",
            "formula_id": "vertical_stability",
            "relationship": "stability_assumption",
            "reason": "水平剪刀撑设置影响架体整体稳定计算假定。",
        },
    ],
}


# ---------------------------------------------------------------------------
# 侧压力（2.8 / 2.19）
# ---------------------------------------------------------------------------
_SIDE_PRESSURE_DEPENDENCIES: dict[str, list[dict[str, Any]]] = {
    "concrete_unit_weight": [
        {
            "rule_id": "2.8",
            "rule_name": "混凝土侧压力计算公式(JGJ162版)",
            "formula_id": "side_pressure",
            "relationship": "direct_input",
            "reason": "γc 是侧压力 F=0.22·γc·t0·β1·β2·V^0.5 与 γc·H 的乘积因子。",
        },
        {
            "rule_id": "2.19",
            "rule_name": "混凝土侧压力标准值计算(GB50666版)",
            "formula_id": "side_pressure",
            "relationship": "direct_input",
            "reason": "γc 是 GB50666 侧压力 F=0.28·γc·t0·β·V^0.5 与 γc·H 的乘积因子。",
        },
    ],
    "initial_set_time": [
        {
            "rule_id": "2.8",
            "rule_name": "混凝土侧压力计算公式(JGJ162版)",
            "formula_id": "side_pressure",
            "relationship": "direct_input",
            "reason": "t0 是 JGJ162 侧压力公式的关键输入。",
        },
        {
            "rule_id": "2.19",
            "rule_name": "混凝土侧压力标准值计算(GB50666版)",
            "formula_id": "side_pressure",
            "relationship": "direct_input",
            "reason": "t0 是 GB50666 侧压力公式的关键输入（无实测时按 200/(T+15)）。",
        },
    ],
    "pouring_speed": [
        {
            "rule_id": "2.8",
            "rule_name": "混凝土侧压力计算公式(JGJ162版)",
            "formula_id": "side_pressure",
            "relationship": "direct_input",
            "reason": "V 是侧压力公式的 V^0.5 项输入。",
        },
        {
            "rule_id": "2.19",
            "rule_name": "混凝土侧压力标准值计算(GB50666版)",
            "formula_id": "side_pressure",
            "relationship": "direct_input",
            "reason": "V 决定 GB50666 公式分支：V≤10 走 0.28 公式，V>10 走 γc·H 静水压。",
        },
    ],
    "side_pressure_height": [
        {
            "rule_id": "2.8",
            "rule_name": "混凝土侧压力计算公式(JGJ162版)",
            "formula_id": "side_pressure",
            "relationship": "direct_input",
            "reason": "H 是静水压分支 F=γc·H 的输入。",
        },
        {
            "rule_id": "2.19",
            "rule_name": "混凝土侧压力标准值计算(GB50666版)",
            "formula_id": "side_pressure",
            "relationship": "direct_input",
            "reason": "H 是 GB50666 静水压分支 F=γc·H 的输入。",
        },
    ],
    "slump": [
        {
            "rule_id": "2.8",
            "rule_name": "混凝土侧压力计算公式(JGJ162版)",
            "formula_id": "side_pressure",
            "relationship": "condition_input",
            "reason": "坍落度决定 JGJ162 β2（坍落度影响系数）取值。",
        },
        {
            "rule_id": "2.19",
            "rule_name": "混凝土侧压力标准值计算(GB50666版)",
            "formula_id": "side_pressure",
            "relationship": "condition_input",
            "reason": "坍落度>180mm 时 GB50666 静水压分支强制触发。",
        },
    ],
    "beta_correction": [
        {
            "rule_id": "2.19",
            "rule_name": "混凝土侧压力标准值计算(GB50666版)",
            "formula_id": "side_pressure",
            "relationship": "direct_input",
            "reason": "坍落度影响修正系数 β。",
        },
    ],
    "beta1_correction": [
        {
            "rule_id": "2.8",
            "rule_name": "混凝土侧压力计算公式(JGJ162版)",
            "formula_id": "side_pressure",
            "relationship": "direct_input",
            "reason": "外加剂影响修正系数 β1。",
        },
    ],
    "beta2_correction": [
        {
            "rule_id": "2.8",
            "rule_name": "混凝土侧压力计算公式(JGJ162版)",
            "formula_id": "side_pressure",
            "relationship": "direct_input",
            "reason": "坍落度影响系数 β2。",
        },
    ],
}


# ---------------------------------------------------------------------------
# 面板（3.1 / 3.2 / 3.3）
# ---------------------------------------------------------------------------
_PANEL_DEPENDENCIES: dict[str, list[dict[str, Any]]] = {
    "panel_thickness": [
        {
            "rule_id": "3.1",
            "rule_name": "面板抗弯承载力验算",
            "formula_id": "panel_bending",
            "relationship": "direct_input",
            "reason": "面板厚度 t 决定截面模量 W=bh²/6 与截面惯性矩 I=bh³/12。",
        },
        {
            "rule_id": "3.2",
            "rule_name": "面板抗剪承载力验算",
            "formula_id": "panel_shear",
            "relationship": "direct_input",
            "reason": "面板厚度影响抗剪截面 A=bh。",
        },
        {
            "rule_id": "3.3",
            "rule_name": "面板挠度验算",
            "formula_id": "panel_deflection",
            "relationship": "direct_input",
            "reason": "面板厚度影响惯性矩 I，进而影响挠度。",
        },
    ],
    "panel_section_width": [
        {
            "rule_id": "3.1",
            "rule_name": "面板抗弯承载力验算",
            "formula_id": "panel_bending",
            "relationship": "direct_input",
            "reason": "面板计算单元宽度 b（常取 1000mm）。",
        },
    ],
    "panel_stringer_spacing": [
        {
            "rule_id": "3.1",
            "rule_name": "面板抗弯承载力验算",
            "formula_id": "panel_bending",
            "relationship": "direct_input",
            "reason": "次楞/次龙骨间距即面板计算跨度 l。",
        },
        {
            "rule_id": "3.3",
            "rule_name": "面板挠度验算",
            "formula_id": "panel_deflection",
            "relationship": "direct_input",
            "reason": "面板计算跨度 l。",
        },
    ],
    "concentrated_line_load": [
        {
            "rule_id": "3.1",
            "rule_name": "面板抗弯承载力验算",
            "formula_id": "panel_bending",
            "relationship": "direct_input",
            "reason": "线荷载 q 经次楞间距 l 折算为面板面荷载。",
        },
        {
            "rule_id": "3.4",
            "rule_name": "次楞抗弯承载力验算",
            "formula_id": "stringer_bending",
            "relationship": "direct_input",
            "reason": "线荷载进入次楞抗弯。",
        },
        {
            "rule_id": "3.6",
            "rule_name": "主楞抗弯承载力验算",
            "formula_id": "main_beam_bending",
            "relationship": "direct_input",
            "reason": "线荷载进入主楞抗弯。",
        },
    ],
}


# ---------------------------------------------------------------------------
# 楞梁（3.4 / 3.5 / 3.6 / 3.7）
# ---------------------------------------------------------------------------
_STRINGER_DEPENDENCIES: dict[str, list[dict[str, Any]]] = {
    "stringer_section_width": [
        {
            "rule_id": "3.4",
            "rule_name": "次楞抗弯承载力验算",
            "formula_id": "stringer_bending",
            "relationship": "direct_input",
            "reason": "次楞截面宽度 b。",
        },
        {
            "rule_id": "3.5",
            "rule_name": "次楞挠度验算",
            "formula_id": "stringer_deflection",
            "relationship": "direct_input",
            "reason": "次楞截面宽度 b。",
        },
    ],
    "stringer_section_height": [
        {
            "rule_id": "3.4",
            "rule_name": "次楞抗弯承载力验算",
            "formula_id": "stringer_bending",
            "relationship": "direct_input",
            "reason": "次楞截面高度 h 决定 W=bh²/6。",
        },
        {
            "rule_id": "3.5",
            "rule_name": "次楞挠度验算",
            "formula_id": "stringer_deflection",
            "relationship": "direct_input",
            "reason": "次楞截面高度 h 决定 I=bh³/12。",
        },
    ],
    "stringer_spacing": [
        {
            "rule_id": "3.4",
            "rule_name": "次楞抗弯承载力验算",
            "formula_id": "stringer_bending",
            "relationship": "direct_input",
            "reason": "次楞间距 l1（主楞方向跨度）。",
        },
        {
            "rule_id": "3.5",
            "rule_name": "次楞挠度验算",
            "formula_id": "stringer_deflection",
            "relationship": "direct_input",
            "reason": "次楞计算跨度 l1。",
        },
    ],
    "main_beam_section_width": [
        {
            "rule_id": "3.6",
            "rule_name": "主楞抗弯承载力验算",
            "formula_id": "main_beam_bending",
            "relationship": "direct_input",
            "reason": "主楞截面宽度 b。",
        },
        {
            "rule_id": "3.7",
            "rule_name": "主楞挠度验算",
            "formula_id": "main_beam_deflection",
            "relationship": "direct_input",
            "reason": "主楞截面宽度 b。",
        },
    ],
    "main_beam_section_height": [
        {
            "rule_id": "3.6",
            "rule_name": "主楞抗弯承载力验算",
            "formula_id": "main_beam_bending",
            "relationship": "direct_input",
            "reason": "主楞截面高度 h 决定 W=bh²/6。",
        },
        {
            "rule_id": "3.7",
            "rule_name": "主楞挠度验算",
            "formula_id": "main_beam_deflection",
            "relationship": "direct_input",
            "reason": "主楞截面高度 h 决定 I=bh³/12。",
        },
    ],
    "main_beam_spacing": [
        {
            "rule_id": "3.6",
            "rule_name": "主楞抗弯承载力验算",
            "formula_id": "main_beam_bending",
            "relationship": "direct_input",
            "reason": "主楞间距（立杆纵距方向）l2。",
        },
        {
            "rule_id": "3.7",
            "rule_name": "主楞挠度验算",
            "formula_id": "main_beam_deflection",
            "relationship": "direct_input",
            "reason": "主楞计算跨度 l2。",
        },
    ],
    "support_span": [
        {
            "rule_id": "3.3",
            "rule_name": "面板挠度验算",
            "formula_id": "panel_deflection",
            "relationship": "condition_input",
            "reason": "跨度决定外露/隐蔽挠度限值 l/400 或 l/250。",
        },
        {
            "rule_id": "3.5",
            "rule_name": "次楞挠度验算",
            "formula_id": "stringer_deflection",
            "relationship": "condition_input",
            "reason": "跨度决定外露/隐蔽挠度限值。",
        },
        {
            "rule_id": "3.7",
            "rule_name": "主楞挠度验算",
            "formula_id": "main_beam_deflection",
            "relationship": "condition_input",
            "reason": "跨度决定外露/隐蔽挠度限值。",
        },
        {
            "rule_id": "3.23",
            "rule_name": "变形限值",
            "formula_id": "deflection_limit",
            "relationship": "condition_input",
            "reason": "跨度是变形限值公式 l/n 的分母。",
        },
    ],
}


# ---------------------------------------------------------------------------
# 地基（3.19）
# ---------------------------------------------------------------------------
_FOUNDATION_DEPENDENCIES: dict[str, list[dict[str, Any]]] = {
    "vertical_axial_force": [
        {
            "rule_id": "3.19",
            "rule_name": "地基承载力验算",
            "formula_id": "foundation_bearing",
            "relationship": "direct_input",
            "reason": "立杆轴力 N 进入 P=N/A。",
        },
        {
            "rule_id": "3.8",
            "rule_name": "立杆轴力设计值",
            "formula_id": "vertical_stability",
            "relationship": "direct_input",
            "reason": "立杆轴力 N 是稳定验算和地基验算共用输入。",
        },
    ],
    "base_plate_area": [
        {
            "rule_id": "3.19",
            "rule_name": "地基承载力验算",
            "formula_id": "foundation_bearing",
            "relationship": "direct_input",
            "reason": "垫板/底座面积 A 是 P=N/A 的分母，规范要求≥0.01m²。",
        },
    ],
    "foundation_bearing_capacity": [
        {
            "rule_id": "3.19",
            "rule_name": "地基承载力验算",
            "formula_id": "foundation_bearing",
            "relationship": "direct_input",
            "reason": "地基承载力特征值 fa（kPa），与 P=N/A 比较。",
        },
    ],
}


# ---------------------------------------------------------------------------
# 抗倾覆（3.20 / 3.25）+ 风荷载
# ---------------------------------------------------------------------------
_OVERTURNING_DEPENDENCIES: dict[str, list[dict[str, Any]]] = {
    "structure_importance_factor": [
        {
            "rule_id": "3.20",
            "rule_name": "抗倾覆验算",
            "formula_id": "overturning",
            "relationship": "direct_input",
            "reason": "结构重要性系数 γ0（0.9/1.0/1.1）放大倾覆力矩。",
        },
        {
            "rule_id": "3.25",
            "rule_name": "抗倾覆验算(GB50666版)",
            "formula_id": "overturning",
            "relationship": "direct_input",
            "reason": "结构重要性系数 γ0。",
        },
    ],
    "resisting_moment": [
        {
            "rule_id": "3.20",
            "rule_name": "抗倾覆验算",
            "formula_id": "overturning",
            "relationship": "direct_input",
            "reason": "抗倾覆力矩 MR/Mr，验算式 MR≥γ0·MT 的左侧。",
        },
        {
            "rule_id": "3.25",
            "rule_name": "抗倾覆验算(GB50666版)",
            "formula_id": "overturning",
            "relationship": "direct_input",
            "reason": "抗倾覆力矩 Mr，验算式 γ0·Mo≤Mr 的右侧。",
        },
    ],
    "overturning_moment": [
        {
            "rule_id": "3.20",
            "rule_name": "抗倾覆验算",
            "formula_id": "overturning",
            "relationship": "direct_input",
            "reason": "倾覆力矩 MT/Mo，含风荷载与浇筑工况附加水平荷载。",
        },
        {
            "rule_id": "3.25",
            "rule_name": "抗倾覆验算(GB50666版)",
            "formula_id": "overturning",
            "relationship": "direct_input",
            "reason": "倾覆力矩 Mo，验算式 γ0·Mo≤Mr 的左侧。",
        },
    ],
    "wind_load": [
        {
            "rule_id": "3.20",
            "rule_name": "抗倾覆验算",
            "formula_id": "overturning",
            "relationship": "condition_input",
            "reason": "风荷载 Wk 是浇筑前工况抗倾覆的主要水平作用。",
        },
        {
            "rule_id": "3.27",
            "rule_name": "立杆稳定性验算-扣件式",
            "formula_id": "vertical_stability",
            "relationship": "condition_input",
            "reason": "组合风荷载工况下立杆稳定性 N/(φA)+Mw/W≤f。",
        },
    ],
    "wind_pressure_height": [
        {
            "rule_id": "3.20",
            "rule_name": "抗倾覆验算",
            "formula_id": "overturning",
            "relationship": "direct_input",
            "reason": "风压高度变化系数 μz 与架体高度相关。",
        },
    ],
}


CALCULATION_PARAMETER_DEPENDENCIES: dict[str, list[dict[str, Any]]] = {
    **_LEGACY_DEPENDENCIES,
    **_SIDE_PRESSURE_DEPENDENCIES,
    **_PANEL_DEPENDENCIES,
    **_STRINGER_DEPENDENCIES,
    **_FOUNDATION_DEPENDENCIES,
    **_OVERTURNING_DEPENDENCIES,
}


def calculation_impacts_for_parameter(parameter: str) -> list[dict[str, Any]]:
    """返回某参数影响的所有公式规则（用于参数详情抽屉展示"影响公式验算"）。"""
    return [dict(item) for item in CALCULATION_PARAMETER_DEPENDENCIES.get(parameter, [])]


def parameters_for_calculation_rule(rule_id: str, formula_id: str | None = None) -> set[str]:
    """反向查询：返回某公式规则（按 rule_id 或 formula_id）依赖的所有 ProjectFacts 参数键。

    用于：
    * 公式规则详情展示"输入参数依赖"
    * 人工复核队列按规则聚合缺失参数
    * 路由分流：参数缺失时把对应规则升级为人工确认
    """
    params: set[str] = set()
    for parameter, impacts in CALCULATION_PARAMETER_DEPENDENCIES.items():
        for impact in impacts:
            if str(impact.get("rule_id")) == str(rule_id):
                params.add(parameter)
            if formula_id and impact.get("formula_id") == formula_id:
                params.add(parameter)
    return params


def parameters_for_formula_id(formula_id: str) -> set[str]:
    """按 formula_id 聚合参数（formula_id 可能被多条规则共享）。"""
    return parameters_for_calculation_rule("", formula_id=formula_id)


def all_dependency_parameters() -> set[str]:
    """返回所有已声明依赖的 ProjectFacts 参数键。"""
    return set(CALCULATION_PARAMETER_DEPENDENCIES.keys())


def dependencies_by_formula() -> dict[str, list[dict[str, Any]]]:
    """按 formula_id 聚合依赖（用于总控展示"公式→参数"反查）。"""
    out: dict[str, list[dict[str, Any]]] = {}
    for parameter, impacts in CALCULATION_PARAMETER_DEPENDENCIES.items():
        for impact in impacts:
            formula_id = impact.get("formula_id")
            if not formula_id:
                continue
            out.setdefault(str(formula_id), []).append(
                {
                    "parameter": parameter,
                    "rule_id": impact.get("rule_id"),
                    "rule_name": impact.get("rule_name"),
                    "relationship": impact.get("relationship"),
                }
            )
    return out
