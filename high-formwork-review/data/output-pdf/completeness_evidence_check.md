# 完整性审查证据核验报告

- physical_page_count: 87
- section_count: 75
- PASS: 9
- MISSING: 0
- UNCERTAIN: 1

## HF-COMP-001 工程概况

- rule_id: HF-COMP-001
- name: 工程概况
- status: PASS
- reason: 满足必要子项：工程名称、工程位置或范围、结构概况、高支模部位或主要参数（4/4），因此判定 PASS
- matched_sections:
  - 1. 工程概况 | level=1 | pages=5-10
  - 1.1 工程简介 | level=2 | pages=5-6
  - 1.2 高大支模概况 | level=2 | pages=6-7
  - 1.3 高大支模特点 | level=2 | pages=7-8
  - 1.3.1 模板荷载大，安全要求高 | level=3 | pages=7-7
  - 1.3.2 施工组织难度大 | level=3 | pages=7-7
  - 1.3.3 施工风险大 | level=3 | pages=7-8
  - 1.3.4 施工中弹性失稳较难察觉 | level=3 | pages=8-8
  - 1.3.5 支架搭设过程管理难度大 | level=3 | pages=8-8
  - 1.4 施工平面布置 | level=2 | pages=8-8
  - 1.5 施工要求和技术保证条件 | level=2 | pages=8-10
- physical_pages: 5、8
- printed_pages: 1、4
- matched_terms: 建筑面积、建设地点、项目名称、项目概况、高支模
- matched_subitems:
  - [已满足] 工程名称 | matched_terms=项目名称 | physical_pages=5
  - [已满足] 工程位置或范围 | matched_terms=建设地点 | physical_pages=5
  - [已满足] 结构概况 | matched_terms=层高、建筑面积、框架结构、结构体系 | physical_pages=5、7
  - [已满足] 高支模部位或主要参数 | matched_terms=搭设高度、超限梁、高支模 | physical_pages=6、8
- requires_human_review: false
- PASS 判定说明: 满足必要子项：工程名称、工程位置或范围、结构概况、高支模部位或主要参数；达到 4/4；因此判定 PASS。

| physical_page | printed_page | section_path | evidence block type | evidence quote 或 description | image_path | table_html 是否存在 | page_type | parse_status | whether_from_toc | requires_human_review |
|---:|---|---|---|---|---|---|---|---|---|---|
| 5 | 1 | 1. 工程概况 / 1.1 工程简介 | table | 序号 项目 内容 1 项目名称 徐工地块社区服务中心及规划中学项目规划中学 效果图 建设地点示意图 2 建设地点 南京市雨花台区铁心桥街道,南至数字大道,北至荷雨路,西至社区服务中心,东至规划纵一路 3 项目概况 徐工地块社区服务中心及规划中学项目规划中学项目主要建筑8轨24班初中,项目总占地面积33605.4平方米,总建筑面积50944.95平方米,其中地上总建筑面积为28219.96平方米,主要包括一栋地上四层的教学综合体,功能包括普通教师、专用教室、图书馆、报告厅... | images/5297f61db18609ff3698747f8ed0c0ab0245623c51014f6f0e421472cf5e818d.jpg | 是 | mixed | complete | false | false |
| 8 | 4 | 1. 工程概况 / 1.3 高大支模特点 / 1.3.4 施工中弹性失稳较难察觉 | paragraph | 结构板、梁支撑系统在施工时，支撑体统缺少主体结构在水平方向的受力约束作用，在施工过程中，施工中存在活荷载，较大的施工荷载对局部杆件形成的压力容易照成高支模局部杆件超越弹性范围失稳，而变形往往是细微的、渐进的，肉眼检查不容易发现，从而连带整体出现弹性失稳；高支模作业需严格按照经过专家论证后的施工方案进行，浇筑前对支架模板进行验收，合格后方能开始浇筑作业。 | 无 | 否 | mixed | complete | false | false |
| 8 | 4 | 1. 工程概况 / 1.3 高大支模特点 / 1.3.5 支架搭设过程管理难度大 | paragraph | 高支模支架搭设过程中，立柱、横杆、部分位置斜撑搭设较密集，给施工带来困难。现场作业人员不够重视，实际搭设过程中可能存在遗漏支撑杆件、搭设间距和步距偏大、杆件连接不规范、扣件扭矩不符合要求、未安装底座或底座未垫平等情况，影响施工安全，针对上诉管理难点，要求现场管理人员高度负责，作业前对施工人员进行技术交底工作，作业中对不合格搭设要求拆除重搭，严格执行高支模施工方案支架搭设参数。 | 无 | 否 | mixed | complete | false | false |

## HF-COMP-002 编制依据

- rule_id: HF-COMP-002
- name: 编制依据
- status: PASS
- reason: 满足必要子项：图纸或施工组织设计、规范标准、法律法规（3/3），因此判定 PASS
- matched_sections:
  - 2. 编制依据 | level=1 | pages=10-12
  - 2.1 设计图纸及施工组织设计施工方案 | level=2 | pages=10-10
  - 2.3 安全管理法律法规 | level=2 | pages=10-12
- physical_pages: 10
- printed_pages: 6
- matched_terms: GB、住建部令、图纸、施工图纸、施工组织设计、标准、管理条例、管理规定、规程、规范
- matched_subitems:
  - [已满足] 图纸或施工组织设计 | matched_terms=施工图纸、施工组织设计 | physical_pages=10
  - [已满足] 规范标准 | matched_terms=GB、JGJ、标准、规程、规范 | physical_pages=10
  - [已满足] 法律法规 | matched_terms=住建部令、管理条例、管理规定 | physical_pages=10
- requires_human_review: false
- PASS 判定说明: 满足必要子项：图纸或施工组织设计、规范标准、法律法规；达到 3/3；因此判定 PASS。

| physical_page | printed_page | section_path | evidence block type | evidence quote 或 description | image_path | table_html 是否存在 | page_type | parse_status | whether_from_toc | requires_human_review |
|---:|---|---|---|---|---|---|---|---|---|---|
| 10 | 6 | 2. 编制依据 / 2.1 设计图纸及施工组织设计施工方案 | table | 序号 名称 编制时间 1 徐工地块社区服务中心及规划中学项目规划中学项目施工图纸(结施) 2023年6月20日 2 徐工地块社区服务中心及规划中学项目规划中学项目施工组织设计 2023年3月12日<br>2.2 国家、行业、地方规范规程 | images/29cfefad9fac5ed825c84da0f3680b8ecda7eb1efaf8162a99eedffac1afdc86.jpg | 是 | mixed | complete | false | false |
| 10 | 6 | 2. 编制依据 / 2.1 设计图纸及施工组织设计施工方案 | table | 序号 类别 名称 编号 1 国家 建筑地基基础设计规范 GB50007-2011 2 建筑结构荷载规范 GB50009-2012 3 混凝土结构设计规范 GB50010-2010 4 建筑施工脚手架安全技术统一标准 GB51210-2016 5 钢结构设计标准 GB50017-2017 6 木结构设计标准 GB50005-2017 7 混凝土结构工程施工质量验收规范 GB50204-2015 8 钢结构工程施工质量验收标准 GB50205-2020 9 建筑工程施工质量... | images/b8d499d3c2244931921b3d9d3c1baec9a0a53c6a4158d18417464fc33a98027a.jpg | 是 | mixed | complete | false | false |
| 10 | 6 | 2. 编制依据 / 2.3 安全管理法律法规 | table | 序号 名称 编号 1 建设工程安全生产管理条例 国务院 393 号令 2 特种作业人员安全技术培训考核管理规定 国家安全生产监督管理总局令第30号 3 生产安全事故应急预案管理办法 国家安全生产监督管理总局令第17号 4 危险性较大的分部分项工程安全管理规定 住建部令【2018】37号文 5 住房城乡建设部办公厅关于实施《危险性较大的分部分项工程安全管理规定》有关问题的通知 建办质【2018】31号文 6 江苏省房屋建筑和市政基础设施工程危险性较大的分部分项工程安全管理... | images/6c830f4a75263cf1779b094fd473d709b83264b93d596d6d33bac2c31f01e451.jpg | 是 | mixed | complete | false | false |

## HF-COMP-003 施工计划

- rule_id: HF-COMP-003
- name: 施工计划
- status: PASS
- reason: 满足必要子项：施工进度、设备计划（2/4），因此判定 PASS
- matched_sections:
  - 3. 施工计划 | level=1 | pages=12-19
  - 3.1 施工进度计划 | level=2 | pages=12-12
  - 3.2 材料与设备计划 | level=2 | pages=12-19
  - 3.2.1 材料需用计划 | level=3 | pages=12-12
  - 3.2.2 材料的标准和进厂验收要求 | level=3 | pages=12-17
  - 3.2.3 设备需用计划 | level=3 | pages=17-19
- physical_pages: 12、13、17、18
- printed_pages: 13、14、8、9
- matched_terms: 工期、施工机具、施工进度、机具、机械设备、设备计划、进场、进度计划
- matched_subitems:
  - [已满足] 施工进度 | matched_terms=工期、施工进度、进度计划 | physical_pages=12、13
  - [未满足] 材料计划 | matched_terms=无 | physical_pages=无
  - [已满足] 设备计划 | matched_terms=施工机具、机具、机械设备、设备计划 | physical_pages=12、17、18
  - [未满足] 劳动力计划 | matched_terms=无 | physical_pages=无
- requires_human_review: false
- PASS 判定说明: 满足必要子项：施工进度、设备计划；达到 2/4；因此判定 PASS。

| physical_page | printed_page | section_path | evidence block type | evidence quote 或 description | image_path | table_html 是否存在 | page_type | parse_status | whether_from_toc | requires_human_review |
|---:|---|---|---|---|---|---|---|---|---|---|
| 12 | 8 | 3. 施工计划 / 3.1 施工进度计划 | paragraph | 详见附件 1：施工进度计划。 | 无 | 否 | mixed | complete | false | false |
| 12 | 8 | 3. 施工计划 / 3.2 材料与设备计划 / 3.2.1 材料需用计划 | paragraph | 合同工期要求中各节点均为整个建筑施工节点，工期要求严格，各类材料需求量巨大，需根据现场材料需求提前联系供应商备货，要求供应商确保本项目的材料使用需求。 | 无 | 否 | mixed | complete | false | false |
| 13 | 9 | 3. 施工计划 / 3.2 材料与设备计划 / 3.2.2 材料的标准和进厂验收要求 | paragraph | 盘扣式支架具有承载力大、稳定性好、零部件安装便捷、安全性好、耐久性好、可适应变化复杂的截面以及可使用吊车整体吊装施工等特点。在本工程中的应用，不但可以减少施工成本，还可以加快施工进度，从而取得良好的经济效益和社会效益。 | 无 | 否 | mixed | complete | false | false |
| 12 | 8 | 3. 施工计划 / 3.2 材料与设备计划 / 3.2.1 材料需用计划 | paragraph | 保证措施: 物资设备部门根据施工机具的配置计划和现场施工的具体要求合理安排机具的进退场时间。确保性能良好、满足施工要求的机械设备和工具按时进场，现场的机械要得到充分的利用，使用完毕后及时组织退场。 | 无 | 否 | mixed | complete | false | false |
| 17 | 13 | 3. 施工计划 / 3.2 材料与设备计划 / 3.2.3 设备需用计划 | table | 主要设备计划表<br>序号 材料名称 型号/规格 单位 数量 进场日期 1 圆盘锯 MJ-106 台 5 2023.9 2 平刨 MB-503 台 5 2023.9 3 台钻 VV508S 台 5 2023.9 4 手提电锯 M-651A 台 20 2023.9 5 压刨 MB1065 台 5 2023.9 6 锤子 重量 0.25、0.5kg 把 100 2023.9 7 扳手 17-19、22-24 开口 把 100 2023.9 8 线垂 0.5kg 个 20 2023... | images/ebf70f48ed8f0c7534d3ea0bee346d6c465afb650f845324c65a8443c253ec33.jpg | 是 | mixed | complete | false | false |
| 18 | 14 | 3. 施工计划 / 3.2 材料与设备计划 / 3.2.3 设备需用计划 | paragraph | 机具的进退场时间。确保性能良好、满足施工要求的机械设备和工具按时进场，现场的机械要得到充分的利用。 | 无 | 否 | text | complete | false | false |

## HF-COMP-004 施工工艺技术

- rule_id: HF-COMP-004
- name: 施工工艺技术
- status: PASS
- reason: 满足必要子项：技术参数、工艺流程、搭设或安装、拆除（4/4），因此判定 PASS
- matched_sections:
  - 4. 施工工艺技术 | level=1 | pages=19-62
  - 4.1 技术参数 | level=2 | pages=19-43
  - 4.1.1 板模板及支撑设计 | level=3 | pages=19-20
  - 4.1.2 梁模板及支撑设计 | level=3 | pages=20-36
  - 4.1.3 梁侧模板及支架设计 | level=3 | pages=36-38
  - 4.1.4 柱模板设计 | level=3 | pages=38-39
  - 4.1.5 架体有周边拉结设计 | level=3 | pages=39-40
  - 4.1.6 竖向斜杆布置型式选用要求 | level=3 | pages=40-42
  - 4.1.7 水平剪刀撑设置要求 | level=3 | pages=42-43
  - 4.1.8 后浇带处模板支架设计 | level=3 | pages=43-43
  - 4.2 工艺流程 | level=2 | pages=43-43
  - 4.3 施工方法 | level=2 | pages=43-51
  - 4.4 操作要求 | level=2 | pages=51-58
  - 4.5 检查要求 | level=2 | pages=58-59
  - 4.6 质量要求及管理措施 | level=2 | pages=59-62
  - 4.6.2 模板施工质量通病防治及保证措施 | level=3 | pages=60-62
- physical_pages: 19、43、47、48、51
- printed_pages: 15、39、43、44、47
- matched_terms: 工艺流程、拆除、搭设、施工流程、步距、流程、立杆、间距
- matched_subitems:
  - [已满足] 技术参数 | matched_terms=步距、立杆、荷载、间距 | physical_pages=19、20、21、36、39、40、42、43、44、45、46、47、48、49、50、51、53、55、57、59、60、61
  - [已满足] 工艺流程 | matched_terms=工艺流程、施工流程、流程 | physical_pages=43、51
  - [已满足] 搭设或安装 | matched_terms=搭设、模板安装 | physical_pages=19、20、39、40、42、43、44、45、46、48、51、53、54、57、58、59、60
  - [已满足] 拆除 | matched_terms=拆模、拆除 | physical_pages=43、47、48、55、56、57
- requires_human_review: false
- PASS 判定说明: 满足必要子项：技术参数、工艺流程、搭设或安装、拆除；达到 4/4；因此判定 PASS。

| physical_page | printed_page | section_path | evidence block type | evidence quote 或 description | image_path | table_html 是否存在 | page_type | parse_status | whether_from_toc | requires_human_review |
|---:|---|---|---|---|---|---|---|---|---|---|
| 19 | 15 | 4. 施工工艺技术 / 4.1 技术参数 | paragraph | 根据模板支撑体系施工部署，采用盘扣式支模体系，立杆管为<br>\Phi48\times3.2<br>，次龙骨为<br>40mm\times90mm<br>木枋，主龙骨为<br>\Phi48\times2.8<br>双钢管，架体顶部主要通过U托传力，架体底部垫专用底座，后浇带位置立杆立在工字钢上。模板采用15mm厚多层木模板，梁侧模采用对拉螺栓固定。 | 无 | 否 | mixed | complete | false | false |
| 19 | 15 | 4. 施工工艺技术 / 4.1 技术参数 / 4.1.1 板模板及支撑设计 | table | 非人防区域 350厚顶板 板厚mm 400mm 最大搭设高度m 5.40m 模板厚度mm 15 立杆纵距mm 900 立杆横距mm 900 步距mm 1500 立杆承重方式 可调顶托 次龙骨规格、间距 40mm×90mm木枋,间距400mm 主龙骨规格、间距 Φ48×2.8mm双钢管,同立杆间距600mm | images/86de153e7e95ce02b9716d5e10322c2dcfc4973db94900c46f0614fb2a53dfc2.jpg | 是 | mixed | complete | false | false |
| 19 | 15 | 4. 施工工艺技术 / 4.1 技术参数 / 4.1.1 板模板及支撑设计 | table | 非人防区域 400厚顶板 板厚mm 400mm 最大搭设高度m 5.40m 模板厚度mm 15 立杆纵距mm 600 立杆横距mm 600 步距mm 1500 立杆承重方式 可调顶托 次龙骨规格、间距 40mm×90mm木枋,间距400mm 主龙骨规格、间距 Φ48×2.8mm双钢管,同立杆间距600mm | images/bcb1a5e0a712696690951278db634028fa5345ca4b4333a4ece96d14f165744d.jpg | 是 | mixed | complete | false | false |
| 43 | 39 | 4. 施工工艺技术 / 4.2 工艺流程 | table | 序号 部位 施工流程 1 柱模板 放线→搭设灯笼架→焊定位筋→安装柱模板→初步加固→校正垂直度→加固→检查 2 墙模板 放线→焊定位筋→安设洞口模板→安装外侧模板→安装内侧模板→调整固定→检查 3 梁板模板 放线→搭设满堂脚手架→安装梁底模→校正标高→安装梁一侧侧模→安装另一侧侧模(待梁筋绑扎完成)→加固→检查 4 定型模架 设置立杆控制线→根据控制线布置立杆→横杆与相邻立杆形成稳定的结构→立杆顶部插入可调顶托,调整复核标高→主次龙骨安装→搭设梁板底模→设置架体剪刀撑 | images/22e0ea9c705af39e2a780ba6c60081c5e8a81bc9ceef4b759d3713aa5e4fbe1a.jpg | 是 | mixed | complete | false | false |
| 51 | 47 | 4. 施工工艺技术 / 4.3 施工方法 | paragraph | (1)、柱模安装工艺流程：弹线找平定位组装柱模涂刷脱模剂安装柱箍安装拉杆或斜撑校正轴线、垂直度固定柱模预检封堵清扫口； | 无 | 否 | text | complete | false | false |
| 19 | 15 | 4. 施工工艺技术 / 4.1 技术参数 / 4.1.1 板模板及支撑设计 | table | 人防区域 350厚顶板 板厚mm 350mm 最大搭设高度m 5.40m 模板厚度mm 15 立杆纵距mm 900 立杆横距mm 900 步距mm 1500 立杆承重方式 可调顶托 次龙骨规格、间距 40mm×90mm木枋,间距400mm 主龙骨规格、间距 Φ48×2.8mm双钢管,同立杆间距600mm | images/dea881a758feb09f168ac382e86e4348c22cb920296939947a3046b1c6c05e8d.jpg | 是 | mixed | complete | false | false |
| 43 | 39 | 4. 施工工艺技术 / 4.1 技术参数 / 4.1.8 后浇带处模板支架设计 | paragraph | 保证后浇带两侧有两排独立支撑体系，纵向龙骨在伸出后浇带两侧两排立杆后延伸400mm断开，并在两边各加设两排立杆，避免后浇带周边模板拆除时，形成悬挑对结构造成破坏。 | 无 | 否 | mixed | complete | false | false |
| 47 | 43 | 4. 施工工艺技术 / 4.3 施工方法 | paragraph | (2)、待一边混凝土浇筑完成拆除梁测模板后支设另一边梁测模，双梁中间用挤塑板填充。 | 无 | 否 | mixed | complete | false | false |
| 48 | 44 | 4. 施工工艺技术 / 4.3 施工方法 | paragraph | (1)、后浇带部位的支模架独立搭设，底部用槽钢横跨下部后浇带，立杆立在槽钢上，其它支模架拆除时后浇带支模架不拆除，下图后浇带处支模架做法中×表示不拆，此处用配套竖向斜撑加固。 | 无 | 否 | mixed | complete | false | false |

## HF-COMP-005 施工安全保证措施

- rule_id: HF-COMP-005
- name: 施工安全保证措施
- status: PASS
- reason: 满足必要子项：技术保障、监测监控、危险源或防护（3/4），因此判定 PASS
- matched_sections:
  - 5. 施工安全保证措施 | level=1 | pages=62-70
  - 5.1 组织和技术保障措施 | level=2 | pages=62-66
  - 5.1.1 组织保障措施 | level=3 | pages=62-64
  - 5.1.2 技术保障措施 | level=3 | pages=64-66
  - 5.2 监测监控措施 | level=2 | pages=66-67
  - 5.2.1 监测目的 | level=3 | pages=66-66
  - 5.2.2 影响因素 | level=3 | pages=66-66
  - 5.2.3 监测项目 | level=3 | pages=66-66
  - 5.2.4 监测点设置 | level=3 | pages=66-66
  - 5.2.5 仪器设备配置 | level=3 | pages=66-66
  - 5.2.6 监测标准 | level=3 | pages=66-67
  - 5.2.7 监测频率 | level=3 | pages=67-67
  - 5.2.8 监测说明 | level=3 | pages=67-67
  - 5.3 绿色施工要求 | level=2 | pages=67-68
  - 5.4 季节施工措施 | level=2 | pages=68-70
- physical_pages: 64、66、67
- printed_pages: 60、62、63
- matched_terms: 安全技术、安全检查、检查、监测点、监测项目、防护措施
- matched_subitems:
  - [未满足] 组织保障 | matched_terms=无 | physical_pages=无
  - [已满足] 技术保障 | matched_terms=安全技术 | physical_pages=64
  - [已满足] 监测监控 | matched_terms=监测点、监测项目 | physical_pages=66
  - [已满足] 危险源或防护 | matched_terms=安全检查、防护措施 | physical_pages=67
- requires_human_review: false
- PASS 判定说明: 满足必要子项：技术保障、监测监控、危险源或防护；达到 3/4；因此判定 PASS。

| physical_page | printed_page | section_path | evidence block type | evidence quote 或 description | image_path | table_html 是否存在 | page_type | parse_status | whether_from_toc | requires_human_review |
|---:|---|---|---|---|---|---|---|---|---|---|
| 64 | 60 | 5. 施工安全保证措施 / 5.1 组织和技术保障措施 / 5.1.2 技术保障措施 | paragraph | （1）模板安装高度在 2m 及以上时，应符合现行国家标准《建筑施工高处作业安全技术规范》JGJ80 的有关规定。 | 无 | 否 | text | complete | false | false |
| 64 | 60 | 5. 施工安全保证措施 / 5.1 组织和技术保障措施 / 5.1.2 技术保障措施 | paragraph | （10）施工现场的用电，应符合国家现行标准《施工现场临时用电安全技术规范》JGJ46的有关规定。 | 无 | 否 | text | complete | false | false |
| 64 | 60 | 5. 施工安全保证措施 / 5.1 组织和技术保障措施 / 5.1.2 技术保障措施 | paragraph | （11）搭设应由专业持证人员安装，安全责任人应向作业人员进行安全技术交底，并做好记录及签证。 | 无 | 否 | text | complete | false | false |
| 66 | 62 | 5. 施工安全保证措施 / 5.2 监测监控措施 / 5.2.4 监测点设置 | paragraph | 支架监测点布设按监测项目分别选取在受力最大的立杆、支架周边稳定性薄弱的立杆及受力最大或地基承载力低的立杆设监测点。监测点布置根据支架平面大小设置各不少于2个立杆顶水平位移、支架整体水平位移及立杆基础沉降监测点。监测仪器精度满足现场监测要求，并设变形监测报警值。 | 无 | 否 | mixed | complete | false | false |
| 67 | 63 | 5. 施工安全保证措施 / 5.2 监测监控措施 / 5.2.8 监测说明 | paragraph | 班组每日进行安全检查，项目部进行安全周检查，公司进行安全月检查，模板工程日常检查重点部位： | 无 | 否 | mixed | complete | false | false |
| 67 | 63 | 5. 施工安全保证措施 / 5.2 监测监控措施 / 5.2.8 监测说明 | paragraph | (5) 安全防护措施是否符合规范要求; | 无 | 否 | mixed | complete | false | false |

## HF-COMP-006 施工管理及作业人员配备

- rule_id: HF-COMP-006
- name: 施工管理及作业人员配备
- status: PASS
- reason: 满足必要子项：施工管理人员、安全生产管理人员、特种作业人员、岗位职责（4/4），因此判定 PASS
- matched_sections:
  - 6. 施工管理及作业人员配备和分工 | level=1 | pages=70-76
  - 6.1 施工管理人员 | level=2 | pages=70-73
  - 6.1.1 组织架构 | level=3 | pages=70-70
  - 6.1.2 岗位职责 | level=3 | pages=70-73
  - 6.2 安全生产管理人员 | level=2 | pages=73-73
  - 6.3特种作业人员 | level=2 | pages=73-74
  - 6.4 其他作业人员配备及分工 | level=2 | pages=74-76
- physical_pages: 70、71、73、74
- printed_pages: 66、67、69、70
- matched_terms: 专职安全员、安全员、岗位职责、技术负责人、架子工、特种作业、特种作业人员
- matched_subitems:
  - [已满足] 施工管理人员 | matched_terms=技术负责人 | physical_pages=71
  - [已满足] 安全生产管理人员 | matched_terms=专职安全员、安全员 | physical_pages=71、73
  - [已满足] 特种作业人员 | matched_terms=架子工、特种作业、特种作业人员 | physical_pages=73、74
  - [已满足] 岗位职责 | matched_terms=岗位职责 | physical_pages=70、71、72、73
- requires_human_review: false
- PASS 判定说明: 满足必要子项：施工管理人员、安全生产管理人员、特种作业人员、岗位职责；达到 4/4；因此判定 PASS。

| physical_page | printed_page | section_path | evidence block type | evidence quote 或 description | image_path | table_html 是否存在 | page_type | parse_status | whether_from_toc | requires_human_review |
|---:|---|---|---|---|---|---|---|---|---|---|
| 71 | 67 | 6. 施工管理及作业人员配备和分工 / 6.1 施工管理人员 / 6.1.2 岗位职责 | paragraph | (3)项目技术负责人安全生产岗位职责 | 无 | 否 | text | complete | false | false |
| 71 | 67 | 6. 施工管理及作业人员配备和分工 / 6.1 施工管理人员 / 6.1.2 岗位职责 | paragraph | 6）每天组织安全总监安全主管或安全员及有关人员进行现场安全巡视，对当天施工现场存在的安全隐患制定有针对性的整改措施并责成有关人员负责整改。 | 无 | 否 | text | complete | false | false |
| 73 | 69 | 6. 施工管理及作业人员配备和分工 / 6.2 安全生产管理人员 | paragraph | 搭设过程中，因处在施工高峰期，各施工班组在交叉作业中，故应加强安全监控力度。水平和垂直材料运输必须设置临时警戒区域，用红白三角小旗围栏。谨防非施工人员进入。同时成立以项目经理为组长的安全领导小组以加强现场安全防护工作，组员为项目部专职安全员及劳务班组专职安全员。 | 无 | 否 | text | complete | false | false |
| 73 | 69 | 6. 施工管理及作业人员配备和分工 / 6.1 施工管理人员 / 6.1.2 岗位职责 | paragraph | 3）证件齐全特种作业持证上岗做好本队人员的岗位安全培训教育工作，经常组织学习安全操作规程，监督本队人员遵守劳动安全纪律，做到不违章指挥，制止违章作业必须保持本队人员的相对稳定。 | 无 | 否 | text | complete | false | false |
| 73 | 69 | 6. 施工管理及作业人员配备和分工 / 6.3特种作业人员 | paragraph | 为确保工程进度的需要，同时根据本工程的结构特征和模板支架的工程量，本工程模板支架搭设涉及架子工、电工、塔司、信号工等特种作业人员，要求特种作业人员均有在有效期内的上岗作业证书。 | 无 | 否 | text | complete | false | false |
| 74 | 70 | 6. 施工管理及作业人员配备和分工 / 6.4 其他作业人员配备及分工 | table | 劳动力投入计划表<br>单位:人 工种级别 按工程施工阶段投入劳动力情况 基坑围护及土方开挖施工阶段 地下室结构施工及基坑监测、维护阶段(可按地下室施工工期调整) 管理人员 18 36 测量工 3 3 基坑监测人员 5 5 钻孔桩人员 90 0 钢筋工 30 200 木工 20 160 砼工 15 40 架子工 10 60 电焊工 8 20 起重工 2 6 电工 3 5 土方车驾驶员 40 10 普工 40 90 合计 284 635 | images/372369425f8481d66f3351ce1f6c9f8a5cbe66932cfde7d87b526a87dd045c67.jpg | 是 | mixed | complete | false | false |
| 70 | 66 | 6. 施工管理及作业人员配备和分工 / 6.1 施工管理人员 / 6.1.2 岗位职责 | paragraph | （1）项目经理安全生产岗位职责 | 无 | 否 | organization_chart | complete | false | false |
| 71 | 67 | 6. 施工管理及作业人员配备和分工 / 6.1 施工管理人员 / 6.1.2 岗位职责 | paragraph | (2) 项目副经理安全生产岗位职责 | 无 | 否 | text | complete | false | false |

## HF-COMP-007 验收要求

- rule_id: HF-COMP-007
- name: 验收要求
- status: PASS
- reason: 满足必要子项：支架验收、搭设验收、验收程序、验收标准、验收内容、验收人员（6/7），因此判定 PASS
- matched_sections:
  - 7. 验收要求 | level=1 | pages=76-77
  - 7.1 验收标准 | level=2 | pages=76-76
  - 7.2 验收程序及内容 | level=2 | pages=76-77
  - 7.3 验收人员 | level=2 | pages=77-77
- physical_pages: 76
- printed_pages: 72
- matched_terms: 应符合下列规定、搭设和组装完毕、搭设的架体、支撑架应进行检查与验收、支撑架检查与验收、架子搭设、检查与验收应符合、班组检查、程序内容、符合本标准、项目安全负责人、验收小组
- matched_subitems:
  - [已满足] 支架验收 | matched_terms=支撑架应进行检查与验收、支撑架检查与验收 | physical_pages=76
  - [未满足] 模板验收 | matched_terms=无 | physical_pages=无
  - [已满足] 搭设验收 | matched_terms=搭设和组装完毕、搭设的架体、架子搭设 | physical_pages=76
  - [已满足] 验收程序 | matched_terms=业主、监理验收、班组检查、程序内容、质量员专检、验收程序 | physical_pages=76、77
  - [已满足] 验收标准 | matched_terms=应符合下列规定、符合本标准 | physical_pages=76
  - [已满足] 验收内容 | matched_terms=检查与验收应符合、程序内容、验收内容 | physical_pages=76、77
  - [已满足] 验收人员 | matched_terms=项目安全负责人、验收小组 | physical_pages=76
- requires_human_review: false
- PASS 判定说明: 满足必要子项：支架验收、搭设验收、验收程序、验收标准、验收内容、验收人员；达到 6/7；因此判定 PASS。

| physical_page | printed_page | section_path | evidence block type | evidence quote 或 description | image_path | table_html 是否存在 | page_type | parse_status | whether_from_toc | requires_human_review |
|---:|---|---|---|---|---|---|---|---|---|---|
| 76 | 72 | 7. 验收要求 / 7.1 验收标准 | paragraph | 1、当出现下列情况之一时，支撑架应进行检查与验收： | 无 | 否 | mixed | complete | false | false |
| 76 | 72 | 7. 验收要求 / 7.1 验收标准 | paragraph | 4、支撑架检查与验收应符合下列规定： | 无 | 否 | mixed | complete | false | false |
| 76 | 72 | 7. 验收要求 / 7.1 验收标准 | paragraph | 3、架子搭设和组装完毕，使用前必须由项目经理、技术负责人、项目安全负责人、架子班长等人员组成验收小组，进行验收，并填写验收单。 | 无 | 否 | mixed | complete | false | false |
| 76 | 72 | 7. 验收要求 / 7.1 验收标准 | paragraph | （2）搭设的架体应符合设计要求，搭设方法和斜杆、剪刀撑等设置应符合本标准的规定； | 无 | 否 | mixed | complete | false | false |
| 76 | 72 | 7. 验收要求 / 7.2 验收程序及内容 | table | 序号 程序 程序内容 1 材料进场检查 材料进场应有脚手架产品标识及产品质量合格证、型式检验报告;应有脚手架产品主要技术参数及产品使用说明书;当对脚手架及构件质量有疑问时,应进行质量抽检和整架试验。 2 班组检查 班组检查分为自检和互检。自检。生产工人对自己生产的产品或完成的工作任务进行检验,实行“三自”,即自己检查,自己把合格区域和不合格区域分开,自己记录有关数据,防止不合格品转入下道工序。互检。生产工人之间对所制产品、零件和完成的工作进行相互检验。互检有多种形式,如... | images/2c0a99095505de15811bdc0331a2a080fd56b5e0ee203aadf28ec1d33a2e783b.jpg | 是 | mixed | complete | false | false |
| 76 | 72 | 7. 验收要求 / 7.1 验收标准 | paragraph | （3）可调托撑和可调底座伸出水平杆的悬臂长度应符合本标准的规定； | 无 | 否 | mixed | complete | false | false |

## HF-COMP-008 应急处置措施

- rule_id: HF-COMP-008
- name: 应急处置措施
- status: PASS
- reason: 满足必要子项：应急组织、事故报告、抢险救援、应急物资（4/6），因此判定 PASS
- matched_sections:
  - 8. 应急处置措施 | level=1 | pages=77-86
  - 8.1 目的 | level=2 | pages=78-78
  - 8.2 应急救援组织机构及职责 | level=2 | pages=78-79
  - 领导小组职责 | level=2 | pages=79-79
  - 救援救护组 | level=2 | pages=79-80
  - 8.3 应急反应预案 | level=2 | pages=80-81
  - 8.4 危险源与风险分析 | level=2 | pages=81-81
  - 8.5 救援方法 | level=2 | pages=81-83
  - 8.6 应急资源 | level=2 | pages=83-84
  - 8.7 应急救援路线 | level=2 | pages=84-86
- physical_pages: 78、79、80、83
- printed_pages: 74、75、76、79
- matched_terms: 上报、事故报告、应急救援、应急资源、报告程序、领导小组
- matched_subitems:
  - [已满足] 应急组织 | matched_terms=领导小组 | physical_pages=78、79、80、81
  - [未满足] 应急职责 | matched_terms=无 | physical_pages=无
  - [未满足] 应急响应 | matched_terms=无 | physical_pages=无
  - [已满足] 事故报告 | matched_terms=上报、事故报告、报告程序 | physical_pages=79、80、81、82
  - [已满足] 抢险救援 | matched_terms=应急救援、救援措施、救援方法 | physical_pages=78、79、80、81、82、83
  - [已满足] 应急物资 | matched_terms=应急资源 | physical_pages=83
- requires_human_review: false
- PASS 判定说明: 满足必要子项：应急组织、事故报告、抢险救援、应急物资；达到 4/6；因此判定 PASS。

| physical_page | printed_page | section_path | evidence block type | evidence quote 或 description | image_path | table_html 是否存在 | page_type | parse_status | whether_from_toc | requires_human_review |
|---:|---|---|---|---|---|---|---|---|---|---|
| 78 | 74 | 8. 应急处置措施 / 8.2 应急救援组织机构及职责 | paragraph | 总承包单位成立以项目经理为组长的应急小组，总包单位各职能部门成员为组员，各专业分包单位现场负责人也是应急救援小组成员。项目应急领导小组成员通讯录如下： | 无 | 否 | organization_chart | complete | false | false |
| 79 | 75 | 8. 应急处置措施 / 8.2 应急救援组织机构及职责 | paragraph | 总承包项目部事故应急救援指挥领导小组负责本工程事故应急救援工作的组织和指挥，日常工作由总承包项目部施工部兼管。一旦发生重大事故或紧急情况时，以指挥领导小组为基础，立即成立事故应急救援指挥部。施工现场应急救援小组负责事故的现场抢救和应急处置及报警工作。 | 无 | 否 | text | complete | false | false |
| 80 | 76 | 8. 应急处置措施 / 救援救护组 | paragraph | 7）承办领导小组负责人交办的其它工作。 | 无 | 否 | text | complete | false | false |
| 79 | 75 | 8. 应急处置措施 / 领导小组职责 | paragraph | 1）项目领导在接到事故报告后，应首先组织有经验的突击队员进行抢救。若事态情况严重，难以控制和处理，应立即在自救的同时向专业救援队伍求救，并密切配合救援队伍。同时报告给监理和甲方、公司及地方政府，并视事故的严重程度报上级单位。 | 无 | 否 | text | complete | false | false |
| 80 | 76 | 8. 应急处置措施 / 8.3 应急反应预案 | paragraph | (1) 事故报告程序 | 无 | 否 | text | complete | false | false |
| 80 | 76 | 8. 应急处置措施 / 8.3 应急反应预案 | paragraph | 事故发生后，作业人员、班组长、现场负责人、项目部安全主管领导应逐级上报，并联络报警，组织抢救。 | 无 | 否 | text | complete | false | false |
| 79 | 75 | 8. 应急处置措施 / 领导小组职责 | paragraph | 4）现场组织制定并实施深基坑坍塌事故的应急救援工作。 | 无 | 否 | text | complete | false | false |
| 83 | 79 | 8. 应急处置措施 / 8.6 应急资源 | paragraph | 应急资源的准备是应急救援工作的重要保障，项目部应根据潜在事性质和后果分析，配备应急救援中所需的消防手段、救援机械和设备、交通工具、医疗设备和药品、生活保障物资。 | 无 | 否 | mixed | complete | false | false |

## HF-COMP-009 计算书

- rule_id: HF-COMP-009
- name: 计算书
- status: PASS
- reason: 满足必要子项：明确计算内容（1/3），因此判定 PASS
- matched_sections:
  - 9.3 计算书 | level=2 | pages=86-87
- physical_pages: 86
- printed_pages: 82
- matched_terms: 计算、计算书
- matched_subitems:
  - [未满足] 计算公式 | matched_terms=无 | physical_pages=无
  - [未满足] 计算表格 | matched_terms=无 | physical_pages=无
  - [已满足] 明确计算内容 | matched_terms=计算书 | physical_pages=86、87
- requires_human_review: false
- PASS 判定说明: 满足必要子项：明确计算内容；达到 1/3；因此判定 PASS。

| physical_page | printed_page | section_path | evidence block type | evidence quote 或 description | image_path | table_html 是否存在 | page_type | parse_status | whether_from_toc | requires_human_review |
|---:|---|---|---|---|---|---|---|---|---|---|
| 86 | 82 | 9.3 计算书 | paragraph | 附件 2、非人防 180mm 厚板计算书 | 无 | 否 | text | complete | false | false |
| 86 | 82 | 9.3 计算书 | paragraph | 附件 3、非人防区域 350 厚板计算书 | 无 | 否 | text | complete | false | false |
| 86 | 82 | 9.3 计算书 | paragraph | 附件 4、非人防区域 400 厚板计算书 | 无 | 否 | text | complete | false | false |

## HF-COMP-010 相关施工图纸

- rule_id: HF-COMP-010
- name: 相关施工图纸
- status: UNCERTAIN
- reason: 目标正文章节存在，但只满足 0/1 个必要子项；仍缺少：可关联施工图图片
- matched_sections:
  - 9.3 相关图纸 | level=2 | pages=87-87
- physical_pages: 1、3、4、13、23、24、25、26、29、30、31、33、35、36、37、38、39、40、41、42、44、45、46、47、48、49、50、62、63、70、78、85、87
- printed_pages: 19、20、21、22、25、26、27、29、31、32、33、34、35、36、37、38、40、41、42、43、44、45、46、58、59、66、74、81、83、9
- matched_terms: 平面布置图、相关图纸、立面图、附图
- matched_subitems:
  - [未满足] 可关联施工图图片 | matched_terms=无 | physical_pages=无
- requires_human_review: true

| physical_page | printed_page | section_path | evidence block type | evidence quote 或 description | image_path | table_html 是否存在 | page_type | parse_status | whether_from_toc | requires_human_review |
|---:|---|---|---|---|---|---|---|---|---|---|
| 87 | 83 | 9.3 相关图纸 | title | 9.3 相关图纸 | 无 | 否 | text | complete | false | false |
| 3 | 无 | 无 | paragraph | 4.6.2 模板施工质量通病防治及保证措施....56<br>5. 施工安全保证措施....58<br>5.1 组织和技术保障措施....58<br>5.1.1 组织保障措施....58<br>5.1.2 技术保障措施....60<br>5.2 监测监控措施....62<br>5.2.1 监测目的....62<br>5.2.2 影响因素....62<br>5.2.3 监测项目....62<br>5.2.4 监测点设置....62<br>5.2.5 仪器设备配置....62<br>5.2.6 监测标准....62<br>5.2.7 监测频率.... | 无 | 否 | text | complete | true | false |
| 4 | 无 | 无 | paragraph | 9.1 施工进度计划....82<br>9.2 施工平面布置图....82<br>9.3 计算书....82<br>9.3 相关图纸....83 | 无 | 否 | text | complete | true | false |
| 1 | 无 | 无 | image | 找到图片，但不在相关施工图纸 section 中，关联不足 | images/e3ceb53503e4e2bfa6142ff4124ee174e3a4a90a64a99b0cbcd63d93d445f4f5.jpg | 否 | mixed | complete | false | false |
| 13 | 9 | 3. 施工计划 / 3.2 材料与设备计划 / 3.2.2 材料的标准和进厂验收要求 | image | 找到图片，但不在相关施工图纸 section 中，关联不足 | images/3ae24f28154391c1056a6549cce43aa1d3378f15f98b3f6e39c6c0c1e793b6e7.jpg | 否 | mixed | complete | false | false |
| 13 | 9 | 3. 施工计划 / 3.2 材料与设备计划 / 3.2.2 材料的标准和进厂验收要求 | image | 1-连接盘；2-扣接头插销；3-水平杆杆端扣接头； | images/b08028cacf4eca391b67f768fec7b1d42b85229655319756943ae734e5260986.jpg | 否 | mixed | complete | false | false |
| 23 | 19 | 4. 施工工艺技术 / 4.1 技术参数 / 4.1.2 梁模板及支撑设计 | image | 梁板不共用（非人防区域）L400×1950: | images/148f6a7ac3168e57a61790d4e54b14c53760d110500bfdb2198ee80e8fb0097e.jpg | 否 | drawing | partial | false | true |
| 24 | 20 | 4. 施工工艺技术 / 4.1 技术参数 / 4.1.2 梁模板及支撑设计 | image | 找到图片，但不在相关施工图纸 section 中，关联不足 | images/e2773b7d06af9aa76d56fbd35bc57be0d417d7ca43a8eb203b1d33d8404e671a.jpg | 否 | drawing | partial | false | true |
| 25 | 21 | 4. 施工工艺技术 / 4.1 技术参数 / 4.1.2 梁模板及支撑设计 | image | 找到图片，但不在相关施工图纸 section 中，关联不足 | images/3414398f1536a816d768f0aca870cdd2ca4da92fb23e25a4c81deb9e0100da40.jpg | 否 | drawing | partial | false | true |
| 26 | 22 | 4. 施工工艺技术 / 4.1 技术参数 / 4.1.2 梁模板及支撑设计 | image | 找到图片，但不在相关施工图纸 section 中，关联不足 | images/bd09d76b90c8e77a63ad1ab1efcc2847d5f1fd357bb5df4fd33675a42be3eed0.jpg | 否 | drawing | partial | false | true |
| 29 | 25 | 4. 施工工艺技术 / 4.1 技术参数 / 4.1.2 梁模板及支撑设计 | image | 找到图片，但不在相关施工图纸 section 中，关联不足 | images/899a34e38d7d8456328a2434f5d18194c9d25c2f35ab804f3efc759bd285d659.jpg | 否 | drawing | partial | false | true |
| 30 | 26 | 4. 施工工艺技术 / 4.1 技术参数 / 4.1.2 梁模板及支撑设计 | image | 找到图片，但不在相关施工图纸 section 中，关联不足 | images/9c6e738dd9771d6f9aecdf89ce799e411da6e3d472c4aad8152e93ad4c55fb3c.jpg | 否 | mixed | complete | false | false |
| 31 | 27 | 4. 施工工艺技术 / 4.1 技术参数 / 4.1.2 梁模板及支撑设计 | image | 找到图片，但不在相关施工图纸 section 中，关联不足 | images/88d3756ea98526fd5275ed3a81a8cb2d05aabd7e91141b5e182a15c66b90b137.jpg | 否 | mixed | complete | false | false |
| 33 | 29 | 4. 施工工艺技术 / 4.1 技术参数 / 4.1.2 梁模板及支撑设计 | image | 找到图片，但不在相关施工图纸 section 中，关联不足 | images/392d1fc8c83c59654bcdfdc9c92794f1f1915050faa143b303ac4089b66b8751.jpg | 否 | drawing | partial | false | true |
| 35 | 31 | 4. 施工工艺技术 / 4.1 技术参数 / 4.1.2 梁模板及支撑设计 | image | 找到图片，但不在相关施工图纸 section 中，关联不足 | images/6a5b668064d18ff2f654c0060e715408cb04a39154717b1419da5a289e619aaf.jpg | 否 | drawing | partial | false | true |
| 36 | 32 | 4. 施工工艺技术 / 4.1 技术参数 / 4.1.3 梁侧模板及支架设计 | image | 400×1950 梁 | images/4d0d4a2949a490c601f3038b4b80b63cb8f2dd49a47ddd10ac8fc90eda9f684f.jpg | 否 | mixed | complete | false | false |
| 37 | 33 | 4. 施工工艺技术 / 4.1 技术参数 / 4.1.3 梁侧模板及支架设计 | image | 400 \times 2300<br>梁 | images/80881b3d66e8e23db7e0fb1767b34b0404ac047eba39bbe43effb76f84771db6.jpg | 否 | drawing | partial | false | true |
| 38 | 34 | 4. 施工工艺技术 / 4.1 技术参数 / 4.1.3 梁侧模板及支架设计 | image | 600×2150 梁 | images/a934bcfe8db8a9d9c514f2e760f0ae43df04b1062c2493929d0da1d048b0e50b.jpg | 否 | mixed | complete | false | false |
| 39 | 35 | 4. 施工工艺技术 / 4.1 技术参数 / 4.1.4 柱模板设计 | image | 柱模板设计立面图 | images/0f5e16e9799e270cb5cd07e0da85479db248983f5bc7afd81c144248c5e9b733.jpg | 否 | mixed | partial | false | true |
| 40 | 36 | 4. 施工工艺技术 / 4.1 技术参数 / 4.1.5 架体有周边拉结设计 | chart | 找到图片，但不在相关施工图纸 section 中，关联不足 | images/c2118242118916b4ecfa57f29604bbd6862e39de183e7db048091c43aa551680.jpg | 否 | mixed | complete | false | false |
| 41 | 37 | 4. 施工工艺技术 / 4.1 技术参数 / 4.1.6 竖向斜杆布置型式选用要求 | image | (a) 立面图 | images/98d4fda0935c2b700e9288886dd7c5121c834e1d4f390705747e787a95e29932.jpg | 否 | drawing | partial | false | true |
| 41 | 37 | 4. 施工工艺技术 / 4.1 技术参数 / 4.1.6 竖向斜杆布置型式选用要求 | image | (b) 平面图 | images/c1735e1ca61855f1804367e0cb455057e05a2098d943ed7ca15292f0909f0edb.jpg | 否 | drawing | partial | false | true |
| 41 | 37 | 4. 施工工艺技术 / 4.1 技术参数 / 4.1.6 竖向斜杆布置型式选用要求 | image | 1—立杆；2—水平杆；3—竖向斜杆<br>图 4.1.6-1 每跨型式支撑架斜杆设置图<br>(a) 立面图 | images/2eef5b9559a6baf3b69a67320dc9ca40ed410cef7d2cfad376399ed3be35f1de.jpg | 否 | drawing | partial | false | true |
| 41 | 37 | 4. 施工工艺技术 / 4.1 技术参数 / 4.1.6 竖向斜杆布置型式选用要求 | image | (b) 平面图<br>1—立杆；2—水平杆；3—竖向斜杆<br>图 4.1.6-2 间隔1 跨型式支撑架斜杆设置图 | images/781c732dbaed91287af5f7c8eed15b5b5ae3515bc80f0efa5ec04c29d8d91168.jpg | 否 | drawing | partial | false | true |
| 42 | 38 | 4. 施工工艺技术 / 4.1 技术参数 / 4.1.6 竖向斜杆布置型式选用要求 | image | (a) 立面图 | images/d23141a7526173b5500b637b0b215476093c125072307d8c7adcaaf3ac3f595b.jpg | 否 | mixed | complete | false | false |
| 42 | 38 | 4. 施工工艺技术 / 4.1 技术参数 / 4.1.6 竖向斜杆布置型式选用要求 | image | (b) 平面图 | images/6f351927686eaafe718d8de40c7611b40d7bb28520a47bf13b1511f409cff3b7.jpg | 否 | mixed | complete | false | false |
| 42 | 38 | 4. 施工工艺技术 / 4.1 技术参数 / 4.1.6 竖向斜杆布置型式选用要求 | image | 1—立杆；2—水平杆；3—竖向斜杆<br>图 4.1.6-3 间隔2 跨型式支撑架斜杆设置图<br>(a) 立面图 | images/40af4ae5698fa9649e9907bf730ca4278f3e411e7181398b78723bc567c53a1e.jpg | 否 | mixed | complete | false | false |
| 42 | 38 | 4. 施工工艺技术 / 4.1 技术参数 / 4.1.6 竖向斜杆布置型式选用要求 | image | b) 平面图<br>1—立杆；2—水平杆；3—竖向斜杆<br>图 4.1.6-4 间隔3 跨型式支撑架斜杆设置图<br>当支撑架搭设高度大于 16m 时，顶层步距内应每跨布置竖向斜杆。 | images/668b8fdaaf344f0ba7835997e83d6522c98799d56e3f2765afba14b23a5502d8.jpg | 否 | mixed | complete | false | false |
| 44 | 40 | 4. 施工工艺技术 / 4.3 施工方法 | image | 可调托撑伸出顶层水平杆的悬臂长度<br>1—可调托撑；2—螺杆；3—调节螺母；4—立杆；5—水平杆 | images/d84fa1d94d024e7cff8ef750daacbb740a5ffece1ac467601a8a4b34d3d1c873.jpg | 否 | mixed | complete | false | false |
| 45 | 41 | 4. 施工工艺技术 / 4.3 施工方法 | image | 找到图片，但不在相关施工图纸 section 中，关联不足 | images/e1dc17c10f5dc70e9ec1c10564c8ba866f74138dd52a15aef8b0eb07a46cf527.jpg | 否 | mixed | complete | false | false |
| 46 | 42 | 4. 施工工艺技术 / 4.3 施工方法 | image | 找到图片，但不在相关施工图纸 section 中，关联不足 | images/2371442477f4634f02072a71f069cb5ca366430b6f9c702276487e189d442672.jpg | 否 | mixed | complete | false | false |
| 46 | 42 | 4. 施工工艺技术 / 4.3 施工方法 | image | 调节跨搭设示意图（一）<br>调节跨搭设示意图（二） | images/49ccb2d4a47100ce6881c59e724da96edb40e3e7bd725d8eb017bbd5f9202e39.jpg | 否 | mixed | complete | false | false |
| 47 | 43 | 4. 施工工艺技术 / 4.3 施工方法 | image | 坡上支模架做法示意图 | images/bedc339efcf1ef619f429209dc8d420ac87d18bad3c2913f13caf7b5f9af66c4.jpg | 否 | mixed | complete | false | false |
| 47 | 43 | 4. 施工工艺技术 / 4.3 施工方法 | image | 伸缩缝双梁支模架做法 | images/53b12986c48f153de89277552b4273abe7e1b4a613a2e85b1c07eec0dfef6087.jpg | 否 | mixed | complete | false | false |
| 48 | 44 | 4. 施工工艺技术 / 4.3 施工方法 | image | 找到图片，但不在相关施工图纸 section 中，关联不足 | images/d814e2edd278277ab18b4d8a969c0f47d88a767e349f5958bfff5b6626c33edc.jpg | 否 | mixed | complete | false | false |
| 49 | 45 | 4. 施工工艺技术 / 4.3 施工方法 | image | 后浇带处支模架做法 | images/e80fa8bc64a96051d73682a2eb686e5bcd77eb2ba8e934f08a3f901ca299e3c7.jpg | 否 | mixed | complete | false | false |
| 50 | 46 | 4. 施工工艺技术 / 4.3 施工方法 | image | 斜交梁支模架做法示意图 | images/a5abcbf9dbdbeeaa0401e77e9711b3d10d3b05def10cbf9e4c4825430590b599.jpg | 否 | mixed | complete | false | false |
| 50 | 46 | 4. 施工工艺技术 / 4.3 施工方法 | image | 13、当地基高差较大时，可利用立杆节点位差配合可调底座进行调整。<br>可调底座调整立杆连接盘示意<br>1—立杆；2—水平杆；3—连接盘；4—可调底座 | images/a9865c628f2643041be71ddc8a716e91cf563b6f24a048802b36d5898787ebbb.jpg | 否 | mixed | complete | false | false |
| 62 | 58 | 5. 施工安全保证措施 / 5.1 组织和技术保障措施 / 5.1.1 组织保障措施 | image | 找到图片，但不在相关施工图纸 section 中，关联不足 | images/999f2ab1bb18004664b9b31c64d7d9084f5a5250a972bb2a95f6a09e2e5961ff.jpg | 否 | mixed | complete | false | false |
| 63 | 59 | 5. 施工安全保证措施 / 5.1 组织和技术保障措施 / 5.1.1 组织保障措施 | image | 找到图片，但不在相关施工图纸 section 中，关联不足 | images/9c1d3b6961d89d537cc6ec9ed0de1158c54ed3316bbf433c3080dfa179e977ca.jpg | 否 | mixed | complete | false | false |
| 70 | 66 | 6. 施工管理及作业人员配备和分工 / 6.1 施工管理人员 / 6.1.1 组织架构 | image | 管理人员组织架构 | images/4e994125936d04bc515be4689ba731fcc8d6603924a5adef9a787a1aa172ac76.jpg | 否 | organization_chart | complete | false | false |
| 78 | 74 | 8. 应急处置措施 / 8.1 目的 | image | 找到图片，但不在相关施工图纸 section 中，关联不足 | images/83fe98b17b00f4a383ca88650b93136a529ed422707298fb56e07f9285fafa3f.jpg | 否 | organization_chart | complete | false | false |
| 85 | 81 | 8. 应急处置措施 / 8.7 应急救援路线 | image | 找到图片，但不在相关施工图纸 section 中，关联不足 | images/0003a6e85e0522d76dddb2da22ee3e2dca82fe49daba8f60de20e91348548d46.jpg | 否 | drawing | partial | false | true |
| 87 | 83 | 9.3 相关图纸 | paragraph | 附图 2：徐工中学高支模超厚板分布图（非人防区域） | 无 | 否 | text | complete | false | false |
| 87 | 83 | 9.3 相关图纸 | paragraph | 附图 3：徐工中学高支模超厚板分布图（人防区域） | 无 | 否 | text | complete | false | false |
| 87 | 83 | 9.3 相关图纸 | paragraph | 附图 4：徐工中学高支模地下部分超限梁分布图（非人防区域） | 无 | 否 | text | complete | false | false |
| 87 | 83 | 9.3 相关图纸 | paragraph | 附图 5：徐工中学高支模地下部分超限梁分布图（人防区域） | 无 | 否 | text | complete | false | false |
