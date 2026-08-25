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

    # 从适用规则反推：盘扣专属规范在列且带规则数，参考层不出现
    ids = [s["standard_id"] for s in result["applicable_standards"]]
    assert "JGJT231-2021" in ids and "JGJ162-2016" in ids
    assert not {"JGJ166-2016", "GB15831"} & set(ids)
    assert all(s.get("rule_count", 0) > 0 for s in result["applicable_standards"])

    doc2 = _document("本方案为模板支撑施工方案。")
    unknown = build_project_qualification(doc2, build_project_facts(doc2))

    ids2 = [s["standard_id"] for s in unknown["applicable_standards"]]
    assert "JGJ162-2016" in ids2
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
    assert by_id["DR-90"]["status"] == "REVIEW"
    assert by_id["DR-90"]["drawing_evidence"][0]["physical_page"] == 2
    assert by_id["DR-90"]["automation_level"] == "evidence_recall_only"


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


# ===== Part B：参数识别修复回归 =====

def test_support_height_multi_region_resolves_to_max() -> None:
    """多区域不同高度取最大值（审查只关心最大搭设高度），不再整体判 uncertain。"""
    doc = _document("A区支撑高度5.87m。B区支撑高度8.05m。C区搭设高度13.88m。")
    facts = build_project_facts(doc)["facts"]
    assert facts["support_height"]["status"] == "confirmed"
    assert facts["support_height"]["value"] == 13.88
    # 全部候选证据保留供复核
    assert len(facts["support_height"]["candidates"]) >= 3


def test_total_load_rejects_spacing_numbers_in_text() -> None:
    """正文中无荷载单位数值时不得把间距 800mm 当总荷载，诚实报 missing。"""
    doc = _document("总荷载计算时支架立杆间距800mm，步距1500mm。")
    facts = build_project_facts(doc)["facts"]
    assert facts["total_load"]["status"] == "missing"
    assert facts["total_load"]["value"] is None


def test_concentrated_line_load_extracts_knm_and_takes_max() -> None:
    """识别 kN/m 单位（此前正则不认），多梁多值取最大。"""
    doc = _document("梁底面板传递线荷载3.237kN/m。集中线荷载设计值最大为20.0kN/m。")
    facts = build_project_facts(doc)["facts"]
    assert facts["concentrated_line_load"]["status"] == "confirmed"
    assert facts["concentrated_line_load"]["value"] == 20.0


def test_normalize_candidate_supports_kn_per_meter() -> None:
    result = normalize_candidate({"raw_value": "15kN/m", "value": None}, "kN/m")
    assert "normalization_error" not in result
    assert result["value"] == 15.0
    assert result["unit"] == "kN/m"


def test_project_qualification_key_parameters_carry_drives() -> None:
    """关键参数速览：带识别结果与驱动的下游审查环节。"""
    doc = _document("本工程采用盘扣式钢管架，支撑高度为10.2m。")
    result = build_project_qualification(doc, build_project_facts(doc))
    kps = {kp["id"]: kp for kp in result["key_parameters"]}
    height = kps["support_height"]
    assert height["status"] == "confirmed"
    assert "10.2" in height["value_text"]
    assert "；".join(height["drives"]).find("超规模") >= 0
    assert kps["support_span"]["status"] == "missing"
    assert all(kp["drives"] for kp in kps.values())


def test_system_specific_rules_gated_by_support_system() -> None:
    """体系专属规则门禁：扣件式/盘扣式语义规则只对对应体系执行。"""
    from app.rule_engine import load_rule_library

    rules = load_rule_library()
    by_id = {str(r["rule_id"]): r for r in rules}
    # 新增的扣件式语义规则存在且标注正确
    for rid in ("4.34", "4.35", "4.36"):
        assert by_id[rid]["applicable_types"] == ["koujian"], rid
    # 体系专属规则不得再标 universal（防止误审其他体系方案）
    assert by_id["5.1"]["applicable_types"] == ["koujian"]
    assert by_id["5.4"]["applicable_types"] == ["pankou"]

    # 盘扣方案：扣件式规则记 NOT_APPLICABLE（走本地引擎，避免测试联网）
    from app.semantic_engine import run_semantic_engine_local

    doc = _document("本工程采用盘扣式钢管架，支撑高度为10.2m。")
    facts = build_project_facts(doc)
    result = run_semantic_engine_local(doc, facts)
    status_by_id = {str(r["rule_id"]): r["status"] for r in result["results"]}
    assert status_by_id["4.34"] == "NOT_APPLICABLE"
    assert status_by_id["5.1"] == "NOT_APPLICABLE"
    assert status_by_id["5.4"] != "NOT_APPLICABLE"


def test_drawing_cross_check_skips_unidentified_params() -> None:
    """方案未识别的参数（fact 值 None）不出图文比对条目——不编造方案值。"""
    doc = _document_with_pages(
        [(1, "text", "工程概况"), (2, "drawing", "高宽比验算图，高宽比2.5")]
    )
    facts = {"facts": {"height_to_width_ratio": {"value": None, "status": "missing"}}}

    result = build_drawing_review(doc, facts)

    ids = {item["review_item_id"] for item in result}
    # 高宽比 fact 未识别 → 不产生比对条目
    assert not any("高宽比" in item.get("title", "") for item in result if item["review_item_id"].startswith("DR-0"))
    assert "DR-90" in ids


def test_drawing_cross_check_extended_params_pass() -> None:
    """扩展参数（丝杆外露/高宽比/扫地杆）在方案值与图纸标注一致时 PASS。"""
    doc = _document_with_pages(
        [
            (1, "text", "参数表"),
            (2, "drawing", "构造详图：丝杆外露长度300mm，扫地杆距底板350mm"),
            (3, "drawing", "稳定性验算简图 高宽比 2.5"),
        ]
    )
    facts = {
        "facts": {
            "head_jack_screw_exposed_length": {
                "value": 300.0,
                "status": "confirmed",
                "evidence": [],
            },
            "height_to_width_ratio": {"value": 2.5, "status": "confirmed", "evidence": []},
            "sweeper_centerline_height_above_base_plate": {
                "value": 350.0,
                "status": "confirmed",
                "evidence": [],
            },
        }
    }

    result = build_drawing_review(doc, facts)

    by_title = {item.get("title", ""): item for item in result}
    screw = next(v for k, v in by_title.items() if "丝杆外露" in k)
    assert screw["status"] == "PASS"
    ratio = next(v for k, v in by_title.items() if "高宽比" in k)
    assert ratio["status"] == "PASS"
    sweeper = next(v for k, v in by_title.items() if "扫地杆" in k)
    assert sweeper["status"] == "PASS"
    assert sweeper["evidence_quality"]["label"] == "原文命中"
    assert sweeper["review_explanation"]["decision"]


def test_drawing_cross_check_spec_clause_filtered_for_extended_params() -> None:
    """规范条文引用（"丝杆外露长度严禁超过400mm"）不当成图纸标注。"""
    doc = _document_with_pages(
        [
            (1, "text", "构造要求"),
            (2, "drawing", "构造要求：丝杆外露长度严禁超过400mm"),
        ]
    )
    facts = {
        "facts": {
            "head_jack_screw_exposed_length": {
                "value": 300.0,
                "status": "confirmed",
                "evidence": [],
            },
        }
    }

    result = build_drawing_review(doc, facts)

    screw = next(
        item for item in result if "丝杆外露" in item.get("title", "")
    )
    # 条文值 400 被过滤 → 无图纸标注值 → REVIEW 而非 ISSUE(300 vs 400)
    assert screw["status"] == "REVIEW"


def test_drawing_ocr_disabled_by_default(monkeypatch) -> None:
    """OCR 默认关闭：未启用时引擎为 None，纯文本层行为不变。"""
    from app.drawing_review import _get_ocr_engine

    monkeypatch.setenv("DRAWING_OCR_ENABLED", "false")
    # 重置惰性缓存
    import app.drawing_review as dr

    monkeypatch.setattr(dr, "_OCR_ENGINE_LOADED", False)
    monkeypatch.setattr(dr, "_OCR_ENGINE", None)
    assert _get_ocr_engine() is None


def test_drawing_ocr_sparse_page_detection() -> None:
    """文本稀疏且含图片 block 的页才触发 OCR。"""
    from app.drawing_review import _is_sparse_drawing_page

    def _page(page_type: str, blocks: list[tuple[str, str]]) -> MinerUPage:
        return MinerUPage(
            physical_page=1,
            source_page_index=0,
            width=None,
            height=None,
            printed_page="1",
            page_type=page_type,
            parse_status="complete",
            text="",
            blocks=[
                MinerUBlock(
                    block_id=f"b{i}",
                    physical_page=1,
                    block_index=i,
                    block_type=bt,
                    text=tx,
                    title_level=None,
                    bbox=None,
                    image_path=None,
                    table_html=None,
                    source_file="demo",
                    source_pointer="/0/1",
                )
                for i, (bt, tx) in enumerate(blocks)
            ],
        )

    # 图片为主、文本稀疏 → OCR 候选
    assert _is_sparse_drawing_page(_page("mixed", [("image", ""), ("image", ""), ("text", "节点图")]))
    # 文本充足 → 不触发
    assert not _is_sparse_drawing_page(
        _page("text", [("paragraph", "构造要求：" + "长" * 300)])
    )
    # 无图片 → 不触发
    assert not _is_sparse_drawing_page(_page("text", [("paragraph", "短文本")]))


def test_drawing_cross_check_le_symbol_filtered_as_spec_clause() -> None:
    """图纸说明简写"丝杆外露长度≤400mm"是规范限值，不当成图纸标注比对。"""
    doc = _document_with_pages(
        [(1, "text", "构造要求"), (2, "drawing", "构造要求：丝杆外露长度≤400mm，扫地杆高度不大于550mm")]
    )
    facts = {
        "facts": {
            "head_jack_screw_exposed_length": {"value": 300.0, "status": "confirmed", "evidence": []},
            "sweeper_centerline_height_above_base_plate": {"value": 350.0, "status": "confirmed", "evidence": []},
        }
    }

    result = build_drawing_review(doc, facts)

    by_title = {item.get("title", ""): item for item in result}
    screw = next(v for k, v in by_title.items() if "丝杆外露" in k)
    assert screw["status"] == "REVIEW"  # ≤400 是条文限值被过滤，非 ISSUE(300 vs 400)
    sweeper = next(v for k, v in by_title.items() if "扫地杆" in k)
    assert sweeper["status"] == "REVIEW"  # "不大于550"同样过滤


def test_drawing_ratio_gap_tight_no_crossline_capture() -> None:
    """高宽比 gap 收紧：跨行后的页码/规范号/无关数值不被误抓。"""
    doc = _document_with_pages(
        [
            (1, "text", "计算书"),
            (2, "drawing", "高宽比验算\n第3页\n共10页\n依据GB51210-2016"),
        ]
    )
    facts = {
        "facts": {"height_to_width_ratio": {"value": 2.5, "status": "confirmed", "evidence": []}}
    }

    result = build_drawing_review(doc, facts)

    ratio = next(item for item in result if "高宽比" in item.get("title", ""))
    # 页码10/规范号51210 都没被当成"高宽比图纸值" → 无有效标注 → REVIEW 而非 ISSUE(2.5 vs 10)
    assert ratio["status"] == "REVIEW"


def test_drawing_ratio_dimensionless_reason_no_mm_unit() -> None:
    """无量纲参数（高宽比）结论不带 mm 单位、不做 ×1000 归一。"""
    doc = _document_with_pages(
        [(1, "text", "参数表"), (2, "drawing", "稳定性验算简图 高宽比 2.5")]
    )
    facts = {
        "facts": {"height_to_width_ratio": {"value": 2.5, "status": "confirmed", "evidence": []}}
    }

    result = build_drawing_review(doc, facts)

    ratio = next(item for item in result if "高宽比" in item.get("title", ""))
    assert ratio["status"] == "PASS"
    assert "mm" not in str(ratio["conclusion"])
    assert "2500" not in str(ratio["conclusion"])


def test_drawing_ocr_source_tagging_by_capture_position() -> None:
    """OCR 来源标注按捕获组位置判定：关键词在文本层、数值在 OCR 段 → source: ocr。"""
    from app.drawing_review import _cross_check_param, DRAWING_CROSS_CHECK_PARAMS

    doc = _document_with_pages(
        [(1, "drawing", "节点详图 步距")]  # 文本层只有关键词，无数值
    )
    # 注意：_cross_check_param 接收的是内层 facts dict（build_drawing_review 已解包）
    facts = {"standard_step_height": {"value": 1.6, "status": "confirmed", "evidence": []}}
    config = DRAWING_CROSS_CHECK_PARAMS[0]
    # 模拟 OCR 段：数值 1600 只出现在 OCR 文本里
    ocr_texts = {1: "步距 1600"}

    result = _cross_check_param(doc, facts, config, ocr_texts=ocr_texts)

    assert result is not None
    assert result["status"] == "PASS"
    ocr_evidence = [e for e in (result.get("drawing_evidence") or []) if e.get("source") == "ocr"]
    assert ocr_evidence, "跨文本层/OCR段的匹配必须标 source: ocr"
    assert result["evidence_quality"]["label"] == "OCR命中"


def test_drawing_ocr_direct_path_resolution(tmp_path) -> None:
    """job_dir 直连路径解析：mineru_api/raw/<rel> 优先，无文件系统搜索。"""
    from app.drawing_review import _resolve_image_path_direct

    rel = "part-001/raw/images/abc.jpg"
    # mineru_api/raw 锚点存在 → 命中
    img = tmp_path / "mineru_api" / "raw" / "part-001" / "raw" / "images" / "abc.jpg"
    img.parent.mkdir(parents=True)
    img.write_bytes(b"x")
    assert _resolve_image_path_direct(tmp_path, rel) == img
    # 不存在 → None
    assert _resolve_image_path_direct(tmp_path, "part-001/raw/images/none.jpg") is None


def test_drawing_cross_check_clause_number_not_captured() -> None:
    """条款编号（";3"）、跨行页码、图号不得被当成图纸标注值。"""
    doc = _document_with_pages(
        [
            (1, "text", "构造要求"),
            (
                2,
                "drawing",
                "1)步距应符合设计和规范要求,水平杆应连续设置;3\n"
                "模板专项施工方案\n7\n"
                "横向间距应相等或成倍数。示意图如下:\n(10",
            ),
        ]
    )
    facts = {
        "facts": {"standard_step_height": {"value": 1.5, "status": "confirmed", "evidence": []}}
    }

    result = build_drawing_review(doc, facts)

    step = next(item for item in result if "步距" in item.get("title", ""))
    # 全部是条文编号/页码/图号 → 无有效图纸标注 → REVIEW
    assert step["status"] == "REVIEW"


def test_drawing_cross_check_spec_narrative_filtered() -> None:
    """条文叙述（"步距超过1.5m时应加密""符合规范要求"）不当成图纸标注。

    注意用无标点叙述：半角逗号本身就被 gap 挡住，测不到 marker 过滤。
    """
    doc = _document_with_pages(
        [
            (1, "text", "构造要求"),
            (2, "drawing", "步距超过1.5m时应加密设置水平剪刀撑\n伸出顶层水平杆的长度符合规范要求"),
        ]
    )
    facts = {
        "facts": {"standard_step_height": {"value": 1.5, "status": "confirmed", "evidence": []}}
    }

    result = build_drawing_review(doc, facts)

    step = next(item for item in result if "步距" in item.get("title", ""))
    assert step["status"] == "REVIEW"  # "超过4"是条文引用，被过滤


def test_drawing_cross_check_prefix_field_excluded() -> None:
    """关键词是其他字段名前缀（"纵距内附加梁底支撑主梁根数 0"）→ 排除。"""
    doc = _document_with_pages(
        [(1, "text", "参数表"), (2, "drawing", "纵距内附加梁底支撑主梁根数 0 纵向间距la(mm) 900")]
    )
    facts = {
        "facts": {"vertical_spacing": {"value": 0.9, "status": "confirmed", "evidence": []}}
    }

    result = build_drawing_review(doc, facts)

    spacing = next(item for item in result if "纵距" in item.get("title", ""))
    # "根数 0"被排除词过滤；900 是真标注 → PASS（不是 ISSUE 0.9 vs 0）
    assert spacing["status"] == "PASS"
    values = [e["value"] for e in spacing.get("drawing_evidence", [])]
    assert 0.0 not in values
    assert 900.0 in values


def test_drawing_cross_check_real_annotation_survives_tight_gap() -> None:
    """收紧后的 gap 不误杀真实标注：字段名与数值间的正常连接（括号/空格）仍命中。"""
    doc = _document_with_pages(
        [(1, "text", "参数表"), (2, "drawing", "步距h(mm) 1500\n悬臂长(mm) 125\n横距(mm) 900")]
    )
    facts = {
        "facts": {
            "standard_step_height": {"value": 1.5, "status": "confirmed", "evidence": []},
            "head_jack_cantilever_length": {"value": 125.0, "status": "confirmed", "evidence": []},
            "horizontal_spacing": {"value": 0.9, "status": "confirmed", "evidence": []},
        }
    }

    result = build_drawing_review(doc, facts)

    by_title = {item.get("title", ""): item for item in result}
    assert next(v for k, v in by_title.items() if "步距" in k)["status"] == "PASS"
    assert next(v for k, v in by_title.items() if "悬臂" in k)["status"] == "PASS"
    assert next(v for k, v in by_title.items() if "横距" in k)["status"] == "PASS"


def test_drawing_cross_check_combined_dunhao_annotation() -> None:
    """组合字段标注"纵距、横距(mm) 900×900"顿号不阻断匹配。"""
    doc = _document_with_pages(
        [(1, "text", "参数表"), (2, "drawing", "搭设参数 板立杆纵、横距(mm) 900×900 纵距、横距(mm) 900×900")]
    )
    facts = {
        "facts": {
            "vertical_spacing": {"value": 0.9, "status": "confirmed", "evidence": []},
            "horizontal_spacing": {"value": 0.9, "status": "confirmed", "evidence": []},
        }
    }

    result = build_drawing_review(doc, facts)

    by_title = {item.get("title", ""): item for item in result}
    v = next(v for k, v in by_title.items() if "纵距" in k)
    h = next(v for k, v in by_title.items() if "横距" in k)
    assert v["status"] == "PASS", "纵距、横距组合标注不应因顿号丢失"
    assert h["status"] == "PASS"


def test_drawing_cross_check_conflicting_values_get_quality_label() -> None:
    """图纸存在多个候选值时，结果打数值冲突标签，方便人工优先复核。"""
    doc = _document_with_pages(
        [(1, "text", "参数表"), (2, "drawing", "步距h(mm) 1500\n步距h(mm) 1800")]
    )
    facts = {
        "facts": {"standard_step_height": {"value": 1.5, "status": "confirmed", "evidence": []}}
    }

    result = build_drawing_review(doc, facts)

    step = next(item for item in result if "步距" in item.get("title", ""))
    assert step["status"] == "PASS"
    assert step["evidence_quality"]["label"] == "数值冲突"
    assert "图纸证据出现多个候选值" in step["review_explanation"]["missing"][0]


def test_drawing_cross_check_alias_overlap_deduped() -> None:
    """别名重叠（悬臂长⊂悬臂长度）同一处数值只计一次，证据不重复。"""
    doc = _document_with_pages(
        [(1, "text", "参数表"), (2, "drawing", "悬臂长度(mm) 200")]
    )
    facts = {
        "facts": {"head_jack_cantilever_length": {"value": 200.0, "status": "confirmed", "evidence": []}}
    }

    result = build_drawing_review(doc, facts)

    cantilever = next(item for item in result if "悬臂" in item.get("title", ""))
    evs = cantilever.get("drawing_evidence") or []
    # 同一处 200 只出现一次（别名去重）
    assert [e["value"] for e in evs].count(200.0) == 1
    assert cantilever["status"] == "PASS"


def test_drawing_cross_check_horizontal_cross_field_excluded() -> None:
    """横距不通过"是否相等"行抓到纵距的值（跨字段误抓会造成假 PASS）。"""
    doc = _document_with_pages(
        [
            (1, "text", "参数表"),
            (2, "drawing", "立杆纵距是否相等 是 立杆横距是否相等 是 纵向间距la(mm) 900 横向间距lb(mm) 1200"),
        ]
    )
    facts = {
        "facts": {"horizontal_spacing": {"value": 0.9, "status": "confirmed", "evidence": []}}
    }

    result = build_drawing_review(doc, facts)

    h = next(item for item in result if "横距" in item.get("title", ""))
    values = [e["value"] for e in h.get("drawing_evidence", [])]
    # 900 是纵距的值：不得作为横距证据（否则 0.9=900mm 会假 PASS）
    assert 900.0 not in values
    assert 1200.0 in values  # lb 1200 是横距真值
