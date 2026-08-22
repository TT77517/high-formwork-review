/* ===== 高支模审查系统 — 前端逻辑 ===== */
const $ = (s) => document.querySelector(s);
const $$ = (s) => document.querySelectorAll(s);
const STAGE_NAMES = { waiting:'等待上传',uploaded:'已上传',mineru_parsing:'MinerU解析',document_parsing:'文档解析',completeness_review:'完整性审查',rerun_review:'重跑中',completed:'已完成',completed_with_warning:'已完成(警告)',failed:'失败' };
const STATUS_CN = { PASS:'已识别',MISSING:'疑似缺失',UNCERTAIN:'无法核验' };
const RE_STATUS_CN = { COMPLIANT:'合规',VIOLATED:'违规',UNCERTAIN:'无法判定',NOT_APPLICABLE:'不适用',PENDING_CONFIRMATION:'待确认' };
const COMP_CN = { AGREEMENT:'一致',DISAGREEMENT:'不一致',NOT_REQUESTED:'未请求',DIFY_FAILED:'暂未完成',BOTH_UNCERTAIN:'均不确定' };
const DIFY_CN = { not_requested:'增强复核：未请求',failed:'增强复核：暂未完成',cache:'增强复核：缓存',api:'增强复核：实时' };
const HUMAN_CN = { pending:'待复核',confirmed_pass:'确认已具备',confirmed_missing:'确认存在缺项',unable_to_verify:'暂无法核验',false_positive:'排除误报',need_supplement:'要求补充资料' };
const SEVERITY_CN = { 'A-mandatory':'A级强制','B-required':'B级应执行','C-recommended':'C级推荐','D-info':'D级提示' };
const MODULE_CN = { '01_procedure_compliance':'程序合规','02_load_values':'荷载取值','03_structural_calculation':'结构计算','04_construction_requirements':'构造要求','05_material_requirements':'材料要求','06_safety_measures':'安全措施' };
const MODES = {
  smart: { label:'智能预审', button:'开始智能预审', hint:'当前选择：智能预审（推荐），组合执行全部审查能力。' },
  completeness: { label:'完整性审查', button:'开始完整性审查', hint:'当前选择：完整性审查。' },
  semantic: { label:'规范语义审查', button:'开始规范语义审查', hint:'当前选择：规范语义审查，基于v4.0规则库比对方案与规范条款。' },
  drawing: { label:'图文一致性校验', button:'开始图文校验', hint:'当前选择：图文一致性校验，识别节点详图并与文本交叉验证。' },
  calculation: { label:'计算校核', button:'开始计算校核', hint:'当前选择：计算校核，针对力学计算书进行逻辑复核。' }
};
const MODE_TABS = {
  smart: ['home','overview','qualification','document','review','semantic','drawing','calculation','manual','rule-library','records'],
  completeness: ['home','overview','qualification','document','review','manual','rule-library','records'],
  semantic: ['home','overview','qualification','document','semantic','manual','rule-library','records'],
  drawing: ['home','overview','qualification','document','drawing','manual','rule-library','records'],
  calculation: ['home','overview','qualification','document','calculation','manual','rule-library','records']
};
let curJob=null, revData=null, compData=null, preData=null, decisions=[], difyErr=null, docMeta=null, pollTimer=null, manIdx=0, selMode='smart', ruleEngineData=null, semanticData=null, calcData=null, standardsData=null;
const STD_LABEL = {};
const RISK_CN = { over_scale_dangerous:'超过一定规模危大', dangerous:'危大', unknown:'未识别' };

initFromQuery();
$$('#reviewModeGrid .mode-card').forEach(c => c.addEventListener('click', () => {
  selMode = c.dataset.mode; if (selMode === 'drawing_consistency') selMode = 'smart';
  $$('#reviewModeGrid .mode-card').forEach(i => i.classList.toggle('selected', i.dataset.mode === c.dataset.mode));
  $('#modeHint').textContent = MODES[selMode]?.hint || '';
  $('#submitButton').textContent = MODES[selMode]?.button || '开始审查';
  applyNav();
}));

async function initFromQuery() {
  const p = new URLSearchParams(location.search); const jid = p.get('job_id');
  if (!jid || !/^[0-9a-f]{32}$/i.test(jid)) { applyNav(); return; }
  curJob = jid.toLowerCase();
  if (p.get('review_mode') && MODES[p.get('review_mode')]) selMode = p.get('review_mode');
  try {
    const r = await fetch(`/api/jobs/${curJob}/status`); const d = await r.json();
    if (!r.ok) throw new Error(d.detail||'读取失败');
    selMode = d.review_mode || selMode; renderMode(); renderStatus(d);
    if (d.status === 'completed' || d.status === 'completed_with_warning') await loadAll();
  } catch(e) { $('#uploadError').textContent = e.message; }
}

function renderMode() {
  $$('#reviewModeGrid .mode-card').forEach(i => i.classList.toggle('selected', i.dataset.mode === selMode));
  if (MODES[selMode]) { $('#modeHint').textContent = MODES[selMode].hint; $('#submitButton').textContent = MODES[selMode].button; }
  applyNav();
}

$('#pdfFile').addEventListener('change', e => { $('#fileLabel').textContent = e.target.files[0]?.name || '选择不超过50MB的PDF文件'; });
$('#uploadForm').addEventListener('submit', async e => {
  e.preventDefault(); const f = $('#pdfFile').files[0]; if (!f) return;
  $('#uploadError').textContent = ''; $('#submitButton').disabled = true;
  const fd = new FormData(); fd.append('file', f); fd.append('review_mode', selMode);
  try {
    const r = await fetch('/api/jobs', { method:'POST', body:fd }); const d = await r.json();
    if (!r.ok) throw new Error(d.detail||'上传失败');
    curJob = d.job_id; selMode = d.review_mode||selMode; renderStatus(d);
    startPolling();
  } catch(e) { $('#uploadError').textContent = e.message; $('#submitButton').disabled = false; }
});

function startPolling() { clearInterval(pollTimer); pollTimer = setInterval(poll, 2000); }

async function poll() {
  try {
    const r = await fetch(`/api/jobs/${curJob}/status`); const d = await r.json();
    if (!r.ok) throw new Error(d.detail||'状态读取失败');
    renderStatus(d);
    if (d.status === 'completed' || d.status === 'completed_with_warning') { clearInterval(pollTimer); await loadAll(); $('#submitButton').disabled = false; }
    else if (d.status === 'failed') { clearInterval(pollTimer); $('#submitButton').disabled = false; }
  } catch(e) { clearInterval(pollTimer); $('#uploadError').textContent = e.message; $('#submitButton').disabled = false; }
}

function renderStatus(d) {
  $('#taskFile').textContent = d.file_name||'—'; $('#taskTime').textContent = fmt(d.uploaded_at);
  $('#taskId').textContent = d.job_id||'—'; $('#taskStage').textContent = `${d.stage} · ${STAGE_NAMES[d.stage]||d.stage}`;
  $('#progressBar').style.width = `${d.progress||0}%`; $('#taskMessage').textContent = d.message||'';
  const b = $('#statusBadge'); b.textContent = STAGE_NAMES[d.status]||d.status;
  b.className = `badge-${d.status==='failed'?'failed':d.status==='completed'||d.status==='completed_with_warning'?'completed':'running'}`;
  $('#jobIdBadge').textContent = (d.job_id||'—').slice(0,8)+'…';
  $('#pageTitle').textContent = STAGE_NAMES[d.status]||d.status;
  if (d.status === 'completed'||d.status==='completed_with_warning') { $('#uploadStage').textContent='审查完成'; $('#uploadStage').style.color='var(--success)'; }
  if (d.error_stage) $('#uploadError').textContent = `失败阶段：${d.error_stage}。${d.message}`;
}

// Navigation
$$('#sideNav .menu-item').forEach(b => b.addEventListener('click', () => switchTab(b.dataset.tab)));
function switchTab(name) {
  $$('#sideNav .menu-item').forEach(b => b.classList.remove('active'));
  const nb = $(`#sideNav .menu-item[data-tab="${name}"]`); if (nb) nb.classList.add('active');
  $$('.tab-panel').forEach(p => p.classList.add('hidden'));
  const pn = $(`#tab-${name}`); if (pn) pn.classList.remove('hidden');
  const titles = { home:'首页上传',overview:'任务概览',qualification:'工程基础信息',document:'文档解析',review:'完整性审查',semantic:'规范语义审查',drawing:'图文一致性校验',calculation:'计算校核',manual:'人工复核','rule-library':'规则库管理',records:'审查记录' };
  $('#pageTitle').textContent = titles[name]||'';
  if (name === 'rule-library' && !ruleLibraryData) loadRuleLibrary('', '', '', '', '');
}
function applyNav() {
  const vis = new Set(MODE_TABS[selMode]||MODE_TABS.smart);
  $$('#sideNav .menu-item').forEach(b => b.classList.toggle('hidden', !vis.has(b.dataset.tab)));
}

// Load all results
async function loadAll() {
  try {
    const [dr, rr, pr] = await Promise.all([
      fetch(`/api/jobs/${curJob}/document`), fetch(`/api/jobs/${curJob}/review`), fetch(`/api/jobs/${curJob}/precheck`)
    ]);
    docMeta = await dr.json(); revData = await rr.json(); preData = pr.ok ? await pr.json() : null;
    if (!dr.ok || !rr.ok) throw new Error('加载失败');
    decisions = revData.decisions||[];
    try { const cr = await fetch(`/api/jobs/${curJob}/comparison`); if (cr.ok) compData = await cr.json(); } catch(_){}
    try { const er = await fetch(`/api/jobs/${curJob}/dify-error`); if (er.ok) difyErr = await er.json(); } catch(_){}
    try { const re = await fetch(`/api/jobs/${curJob}/rule-engine`); if (re.ok) ruleEngineData = await re.json(); } catch(_){}
    try { const sm = await fetch(`/api/jobs/${curJob}/semantic`); if (sm.ok) semanticData = await sm.json(); } catch(_){}
    try { const cl = await fetch(`/api/jobs/${curJob}/calculation`); if (cl.ok) calcData = await cl.json(); } catch(_){}
    try {
      const sr = await fetch('/api/standards');
      if (sr.ok) {
        standardsData = await sr.json();
        (standardsData.standards||[]).forEach(s => { STD_LABEL[s.standard_id] = s.full_code; });
      }
    } catch(_){}
    loadRuleLibrary('', '', '', '', '');  // Load rule library in background
    renderOverview(); renderQualification(); renderDocument(); renderRuleEngine(); renderReview();
    renderSemantic(); renderDrawing(); renderCalculation(); renderManual(); renderRecords();
    applyNav(); switchTab(defTab());
  } catch(e) { console.error('加载失败:', e); }
}
function defTab() { return { smart:'overview',completeness:'review',semantic:'semantic',drawing:'drawing',calculation:'calculation' }[selMode]||'overview'; }

// ===== Overview =====
function renderOverview() {
  const s = revData?.summary||{}; const ss = preData?.summary||{};
  const cards = [
    { tab:'qualification', title:'工程基础信息', value: preData?.project_qualification?'已生成':'未生成', sub:'确定预审范围和规则包' },
    { tab:'review', title:'完整性审查', value: `${s.pass_count||0}/${s.total_rules||10}`, sub:`缺失 ${s.missing_count||0} · 无法核验 ${s.uncertain_count||0}` },
    { tab:'semantic', title:'规范语义审查', value: `${(ss.rule_engine_compliant||0)+(semanticData?.compliant||0)}/${(ss.rule_engine_total||0)+(semanticData?.total_rules||0)}`, sub:`违规 ${(ss.rule_engine_violated||0)+(semanticData?.violated||0)} · 无法判定 ${(ss.rule_engine_uncertain||0)+(semanticData?.uncertain||0)}`, warn: ((ss.rule_engine_violated||0)+(semanticData?.violated||0))>0 },
    { tab:'drawing', title:'图文一致性校验', value: `${ss.drawing_total||0}`, sub:`需复核 ${ss.drawing_review||0}`, warn: (ss.drawing_review||0)>0 },
    { tab:'calculation', title:'计算校核', value: `${(calcData?.compliant||0)}/${(calcData?.total_rules||0)+(ss.consistency_total||0)}`, sub:`验算问题 ${calcData?.violated||0} · 不一致 ${ss.consistency_issue||0}`, warn: (calcData?.violated||0)>0 || (ss.consistency_issue||0)>0 },
    { tab:'manual', title:'人工复核', value: (preData?.human_review_queue||[]).filter(i => { const d=(decisions||[]).find(x => (x.item_key||`completeness_review:${x.rule_id}`)===_queueKey(i)); return d && d.human_decision!=='pending'; }).length, sub:`待确认共 ${(preData?.human_review_queue||[]).length} 项`, warn: (preData?.human_review_queue||[]).length>0 }
  ];
  $('#overviewCards').innerHTML = cards.map(c => `<button class="stat-card${c.warn?' warn':''}" onclick="switchTab('${c.tab}')">
    <div class="stat-title">${c.title}</div><div class="stat-value">${c.value}</div><div class="stat-sub">${c.sub}</div></button>`).join('');
  const pri = [];
  if ((ss.rule_engine_violated||0)>0) pri.push(`规则引擎发现 ${ss.rule_engine_violated} 项违规，请在"规则引擎审查"中逐项核实`);
  if ((s.missing_count||0)>0) pri.push(`${s.missing_count} 条规则疑似缺失`);
  if ((ss.rule_engine_uncertain||0)>0) pri.push(`规则引擎有 ${ss.rule_engine_uncertain} 项无法判定，需人工确认`);
  if (pri.length===0) pri.push('暂无明显待处理事项');
  $('#priorityItems').classList.remove('hidden');
  $('#priorityList').innerHTML = pri.map(p => `<li>${p}</li>`).join('');
}

// ===== Qualification =====
function renderQualification() {
  const q = preData?.project_qualification; if (!q) { $('#qualificationPanel').innerHTML = '<div class="stat-card"><div class="stat-value">未生成</div><div class="stat-title">工程基础信息</div></div>'; $('#qualificationStandards').innerHTML = ''; return; }
  const p = q.identified_parameters||{}; const h = p.support_height||{}; const sp = p.support_span||{}; const t = p.total_load_design||{}; const l = p.concentrated_line_load_design||{};
  const PTYPE_CN = { concrete_formwork_support: '混凝土模板支撑（高支模）' };
  // 卡片只保留文字项
  const rows = [['工程类型',PTYPE_CN[q.project_type]||q.project_type],['风险属性',RISK_CN[q.risk_classification]||q.risk_classification],['支撑体系',q.support_system_label]];
  $('#qualificationPanel').innerHTML = rows.map(([l,v]) => `<div class="stat-card"><div class="stat-title">${esc(l)}</div><div class="stat-value">${esc(v||'未识别')}</div></div>`).join('');
  // 关键参数表格：展示已识别的数值参数（直接用 key_parameters，不再重复前三行）
  const kps = (q.key_parameters||[]).filter(kp => kp.status==='confirmed');
  const allParams = kps;
  $('#qualificationKeyParams').innerHTML = allParams.length ? `<div class="std-head">关键参数识别</div>
    <div class="table-wrap"><table class="data-table table-compact"><thead><tr><th>参数</th><th>识别结果</th><th>来源页</th><th>驱动的审查环节</th></tr></thead><tbody>
    ${allParams.map(kp => `<tr><td><b>${esc(kp.label)}</b></td><td><span class="tag-green">${esc(kp.value||kp.value_text||'已识别')}</span></td><td>${kp.evidence_page?('p.'+kp.evidence_page):'—'}</td><td><small>${esc((kp.drives||[]).join('；')||'—')}</small></td></tr>`).join('')}
    </tbody></table></div>` : '';
  const stds = q.applicable_standards||[];
  const note = stds.length && stds[0].note ? `<p class="mode-hint">${esc(stds[0].note)}，确认后重跑适用规则</p>` : '';
  const STD_CAT_CN = { regulation:'法规文件', document:'政策文件', national:'国家标准', industry:'行业标准' };
  const stdChip = s => `<button type="button" class="std-chip" data-std="${esc(s.standard_id)}" title="${esc(s.name)}">${esc(s.full_code)}<small>${esc(s.name)}${s.rule_count ? ' · ' + s.rule_count + '条规则' : ''}</small></button>`;
  const stdGroups = ['regulation','document','national','industry'].map(cat => {
    const list = stds.filter(s => (s.category||'') === cat);
    return list.length ? `<div class="std-head">${STD_CAT_CN[cat] || cat}</div><div class="std-chips">${list.map(stdChip).join('')}</div>` : '';
  }).join('');
  $('#qualificationStandards').innerHTML = stds.length
    ? `<div class="std-head">适用规范（识别工程信息后自动匹配）</div>${stdGroups}${note}`
    : '';
  $$('#qualificationStandards .std-chip').forEach(b => b.addEventListener('click', () => {
    switchTab('rule-library');
    $('#rlStandardFilter').value = b.dataset.std;
    loadRuleLibrary($('#rlModuleFilter').value, $('#rlTypeFilter').value, $('#rlSeverityFilter').value, $('#rlSearch').value, b.dataset.std);
  }));
}

// ===== Document =====
function renderDocument() {
  const d = docMeta; if (!d) return;
  const stats = [['引擎',d.engine],['总页数',d.physical_page_count],['章节',d.section_count],['Block',d.block_count],['完整页',d.complete_page_count],['部分解析',d.partial_page_count],['不可读',d.unreadable_page_count]];
  $('#documentStats').innerHTML = stats.map(([l,v]) => `<div class="stat-card"><div class="stat-title">${l}</div><div class="stat-value">${v}</div></div>`).join('');
  renderTechStats(); renderChapterTable('all');
  $('#pageFilter').onchange = function() { renderChapterTable(this.value); };
}
function renderTechStats() {
  const d = docMeta; if (!d) return;
  const total = (d.text_block_count||0)+(d.table_count||0)+(d.image_count||0)+(d.formula_count||0)||1;
  const bars = [['文本块',d.text_block_count],['表格',d.table_count],['图片',d.image_count],['公式',d.formula_count]];
  const pc = d.physical_page_count||1;
  $('#techStatsContent').innerHTML = `
    <div class="dist-bars">${bars.map(([l,v]) => `<div class="dist-row"><span class="dist-label">${l}</span><div class="dist-track"><div class="dist-fill" style="width:${Math.round((v||0)/total*100)}%"></div></div><span class="dist-val">${v||0}</span></div>`).join('')}</div>
    <p class="mode-hint">解析质量：完整页 ${d.complete_page_count||0}/${pc}（${Math.round((d.complete_page_count||0)/pc*100)}%）、部分解析 ${d.partial_page_count||0}、不可读 ${d.unreadable_page_count||0}；需人工复核 ${d.human_review_page_count??0} 页。</p>`;
}
function _chapterGroups() {
  const pages = docMeta?.pages||[]; const sections = docMeta?.sections||[];
  const chapters = []; const byName = {};
  sections.forEach(s => {
    const root = (s.path && s.path[0]) || s.title;
    if (!byName[root]) { byName[root] = { title: root, start: s.physical_page_start, end: s.physical_page_end, subs: [], pages: [] }; chapters.push(byName[root]); }
    const c = byName[root];
    c.start = Math.min(c.start, s.physical_page_start);
    c.end = Math.max(c.end, s.physical_page_end);
    if ((s.path||[]).length >= 2) c.subs.push(s);
  });
  chapters.forEach(c => c.subs.sort((a,b) => a.physical_page_start - b.physical_page_start));
  const unc = { title: '未分类（封面/目录等）', start: 1, end: 1, subs: [], pages: [] };
  pages.forEach(p => {
    const c = chapters.find(c => p.physical_page >= c.start && p.physical_page <= c.end);
    (c || unc).pages.push(p);
  });
  const inSec = (s, p) => p.physical_page >= s.physical_page_start && p.physical_page <= s.physical_page_end;
  chapters.forEach(c => {
    c.subs.forEach(s => {
      s._pages = c.pages.filter(p => inSec(s, p) && !c.subs.some(d => d !== s && (d.level||1) > (s.level||1) && inSec(d, p)));
    });
    c._direct = c.pages.filter(p => !c.subs.some(s => inSec(s, p)));
  });
  return unc.pages.length ? [unc, ...chapters] : chapters;
}
let docChapters = [];
function _pageRow(p, ci, si) {
  return `<tr class="page-sub hidden ${p.parse_status==='unreadable'?'row-unreadable':p.parse_status==='partial'?'row-partial':''}" data-ch="${ci}" data-sec="${si}" data-page="${p.physical_page}">
    <td style="padding-left:44px">${p.physical_page}</td><td>${esc(p.printed_page||'—')}</td><td>${esc(p.page_type)}</td><td>${esc(p.parse_status)}</td>
    <td>${p.text_length}</td><td>${p.image_count}/${p.table_count}/${p.formula_count}</td>
    <td class="${p.requires_human_review?'review-yes':''}">${p.requires_human_review?'需要':'否'}</td></tr>`;
}
function renderChapterTable(f) {
  const match = p => f==='all'||(f==='unreadable'&&p.parse_status==='unreadable')||(f==='partial'&&p.parse_status==='partial')||(f==='human-review'&&p.requires_human_review);
  const sum = (ps, k) => ps.reduce((a,p) => a+(p[k]||0), 0);
  docChapters = _chapterGroups();
  const rows = [];
  docChapters.forEach((c, ci) => {
    const shown = f==='all' ? c.pages : c.pages.filter(match);
    if (f!=='all' && !shown.length) return;
    const partial = c.pages.filter(p => p.parse_status==='partial').length;
    const review = c.pages.filter(p => p.requires_human_review).length;
    const leaf = !c.subs.length;
    rows.push(`<tr class="chapter-row" data-ch="${ci}"><td>${leaf?'<span class="tree-caret leaf">•</span>':'<span class="tree-caret">▶</span>'}<b>${esc(c.title)}</b><small style="color:var(--text-tertiary)"> ${c.subs.length} 节 · ${c.pages.length} 页</small> <button type="button" class="btn-small btn-content" data-ch="${ci}">查看内容</button></td><td>${c.start}-${c.end}</td><td>${c.pages.length}</td><td>${sum(c.pages,'text_length')}</td><td>${sum(c.pages,'image_count')}/${sum(c.pages,'table_count')}/${sum(c.pages,'formula_count')}</td><td>${partial}</td><td class="${review?'review-yes':''}">${review?`是(${review})`:'否'}</td></tr>`);
    (f==='all' ? c._direct : c._direct.filter(match)).forEach(p => rows.push(_pageRow(p, ci, -1)));
    c.subs.forEach((s, si) => {
      const sp = f==='all' ? s._pages : s._pages.filter(match);
      if (f!=='all' && !sp.length) return;
      const depth = Math.min(3, (s.path||[]).length - 2);
      const spartial = s._pages.filter(p => p.parse_status==='partial').length;
      const sreview = s._pages.filter(p => p.requires_human_review).length;
      rows.push(`<tr class="section-row hidden" data-ch="${ci}" data-sec="${si}"><td style="padding-left:${20+depth*16}px"><span class="tree-caret">▶</span>${esc(s.title)}<small style="color:var(--text-tertiary)"> ${s._pages.length} 页</small> <button type="button" class="btn-small btn-content" data-ch="${ci}" data-sec="${si}">查看内容</button></td><td>${s.physical_page_start}-${s.physical_page_end}</td><td>${s._pages.length}</td><td>${sum(s._pages,'text_length')}</td><td>${sum(s._pages,'image_count')}/${sum(s._pages,'table_count')}/${sum(s._pages,'formula_count')}</td><td>${spartial}</td><td class="${sreview?'review-yes':''}">${sreview?`是(${sreview})`:'否'}</td></tr>`);
      sp.forEach(p => rows.push(_pageRow(p, ci, si)));
    });
  });
  $('#chapterRows').innerHTML = rows.join('') || '<tr><td colspan="7" style="text-align:center;color:var(--text-tertiary)">无符合条件的页面</td></tr>';
  $$('#chapterRows tr.chapter-row').forEach(r => r.addEventListener('click', () => {
    const ci = +r.dataset.ch; const c = docChapters[ci];
    if (!c.subs.length) { openSectionReader(c.title, c.pages); return; }
    const open = !r.querySelector('.tree-caret').classList.contains('open');
    setChapterOpen(ci, open);
  }));
  $$('#chapterRows tr.section-row').forEach(r => r.addEventListener('click', () => {
    const ch = +r.dataset.ch, sec = +r.dataset.sec;
    const open = !r.querySelector('.tree-caret').classList.contains('open');
    setSectionOpen(ch, sec, open);
  }));
  $$('#chapterRows .btn-content').forEach(b => b.addEventListener('click', e => {
    e.stopPropagation();
    const c = docChapters[+b.dataset.ch];
    if (b.dataset.sec !== undefined) { const s = c.subs[+b.dataset.sec]; openSectionReader(s.title, s._pages); }
    else openSectionReader(c.title, c.pages);
  }));
  $$('#chapterRows tr[data-page]').forEach(r => r.addEventListener('click', e => { e.stopPropagation(); openPageDrawer(+r.dataset.page); }));
}
function setChapterOpen(ci, open) {
  const caret = $(`#chapterRows tr.chapter-row[data-ch="${ci}"] .tree-caret`);
  if (caret) caret.classList.toggle('open', open);
  $$(`#chapterRows tr[data-ch="${ci}"]`).forEach(k => {
    if (k.classList.contains('chapter-row')) return;
    if (!open) { k.classList.add('hidden'); return; }
    if (k.classList.contains('section-row') || (k.classList.contains('page-sub') && k.dataset.sec === '-1')) k.classList.remove('hidden');
  });
}
function setSectionOpen(ch, sec, open) {
  const caret = $(`#chapterRows tr.section-row[data-ch="${ch}"][data-sec="${sec}"] .tree-caret`);
  if (caret) caret.classList.toggle('open', open);
  $$(`#chapterRows tr.page-sub[data-ch="${ch}"][data-sec="${sec}"]`).forEach(k => k.classList.toggle('hidden', !open));
}
function renderBlocks(p) {
  return (p.blocks||[]).map(b => {
    const meta = `<div class="meta"><span><b>${esc(b.block_type)}</b></span><span>${esc(b.block_id)}</span><small>${esc(b.source_pointer||'')}</small></div>`;
    if (b.block_type==='table' && b.table_html) return `<div class="evidence-block">${meta}<div class="table-html">${b.table_html}</div></div>`;
    if ((b.block_type==='image'||b.block_type==='drawing') && b.image_path) return `<div class="evidence-block">${meta}<img src="/api/jobs/${curJob}/asset?path=${encodeURIComponent(b.image_path)}"></div>`;
    if (b.block_type==='title') return `<div class="evidence-block">${meta}<h4 style="margin:4px 0">${esc(b.text||'')}</h4></div>`;
    return `<div class="evidence-block">${meta}<p style="margin:4px 0;white-space:pre-wrap">${esc(b.text||'无文本')}</p></div>`;
  }).join('');
}
async function openPageDrawer(pn) {
  try {
    const r = await fetch(`/api/jobs/${curJob}/document/pages/${pn}`); const p = await r.json(); if (!r.ok) return;
    $('#drawerTitle').textContent = `第 ${p.physical_page} 页详情`;
    $('#drawerBody').innerHTML = `${renderBlocks(p) || '<p style="color:var(--text-tertiary)">本页无可用内容</p>'}<details class="fold-section" style="margin-top:12px"><summary>整页原始文本</summary><div class="fold-body"><p style="white-space:pre-wrap">${esc(p.text||'')}</p></div></details>`;
    $('#pageDetailPanel').classList.remove('hidden');
  } catch(_){}
}
async function openSectionReader(title, pages) {
  const list = (pages||[]).slice(0, 12);
  let html = '';
  for (const p of list) {
    try {
      const r = await fetch(`/api/jobs/${curJob}/document/pages/${p.physical_page}`);
      if (!r.ok) continue;
      const d = await r.json();
      html += `<h4 style="margin:12px 0 6px;color:var(--text-secondary);border-bottom:1px solid var(--border);padding-bottom:4px">第 ${d.physical_page} 页</h4>${renderBlocks(d)}`;
    } catch(_){}
  }
  if ((pages||[]).length > list.length) html += `<p class="mode-hint">仅展示前 ${list.length} 页，其余 ${(pages||[]).length - list.length} 页请展开左侧行后点击页码查看。</p>`;
  $('#drawerTitle').textContent = `章节内容：${title}`;
  $('#drawerBody').innerHTML = html || '<p style="color:var(--text-tertiary)">无可用内容</p>';
  $('#pageDetailPanel').classList.remove('hidden');
}
$('#drawerClose').addEventListener('click', () => $('#pageDetailPanel').classList.add('hidden'));
$('#pageDetailPanel').addEventListener('click', e => { if (e.target === $('#pageDetailPanel')) $('#pageDetailPanel').classList.add('hidden'); });

// ===== 分页与卡片联动 =====
function slicePage(items, st) {
  const pages = Math.max(1, Math.ceil(items.length / st.size));
  if (st.page > pages) st.page = pages;
  if (st.page < 1) st.page = 1;
  const s = (st.page - 1) * st.size;
  return items.slice(s, s + st.size);
}
function pagerHtml(st, total) {
  const pages = Math.max(1, Math.ceil(total / st.size));
  return `<div class="pager"><span class="pager-info">共 ${total} 条</span>
    <select class="select-field pager-size">${[10,20,50].map(x => `<option value="${x}" ${st.size===x?'selected':''}>${x} / 页</option>`).join('')}</select>
    <button type="button" class="btn-small pager-prev" ${st.page<=1?'disabled':''}>上一页</button>
    <span class="pager-num">${st.page} / ${pages}</span>
    <button type="button" class="btn-small pager-next" ${st.page>=pages?'disabled':''}>下一页</button></div>`;
}
function bindPager(sel, st, rerender) {
  const root = $(sel); if (!root) return;
  const prev = root.querySelector('.pager-prev'), next = root.querySelector('.pager-next'), size = root.querySelector('.pager-size');
  if (prev) prev.addEventListener('click', () => { st.page -= 1; rerender(); });
  if (next) next.addEventListener('click', () => { st.page += 1; rerender(); });
  if (size) size.addEventListener('change', () => { st.size = +size.value; st.page = 1; rerender(); });
}
function statCardsHtml(cards, active) {
  const warnLbl = ['违规','待确认','验算问题','需人工复核','不一致'];
  return cards.map(([f,l,v]) => `<div class="stat-card${warnLbl.includes(l)&&v>0?' warn':''}${active===f?' active':''}" data-f="${f}" style="cursor:pointer" title="点击筛选下方列表"><div class="stat-title">${l}</div><div class="stat-value">${v}</div></div>`).join('');
}
function evLine(e, label) {
  const pg = e.physical_page ?? e.page;
  return `<div class="ev-line">${evThumb(e, pg)}<blockquote>${esc(e.quote||e.text||'')}</blockquote>${pg?`<button type="button" class="btn-small jq-page" data-page="${pg}">${label||'原文'} P${pg}</button>`:''}</div>`;
}
function evThumb(e, pg) {
  if (e.table_html) return `<button type="button" class="ev-thumb ev-thumb-table" data-page="${pg||''}" data-thtml="${esc(e.table_html)}" title="点击查看表格原样">▦ 表格</button>`;
  if (!e.image_path) return '';
  return `<img class="ev-thumb" loading="lazy" alt="证据图像" src="/api/jobs/${curJob}/asset?path=${encodeURIComponent(e.image_path)}" data-img="${esc(e.image_path)}" data-page="${pg||''}" title="点击查看大图">`;
}

// ===== 图片/表格证据灯箱 =====
function _openLightbox(title, bodyHtml, page, rawUrl) {
  $('#lightboxTitle').textContent = title;
  $('#lightboxBody').innerHTML = bodyHtml;
  const openBtn = $('#lightboxOpenPage');
  openBtn.dataset.page = page || '';
  openBtn.style.display = page ? '' : 'none';
  const rawLink = $('#lightboxRawLink');
  if (rawUrl) { rawLink.href = rawUrl; rawLink.style.display = ''; } else { rawLink.style.display = 'none'; }
  $('#imageLightbox').classList.remove('hidden');
}
function openImageLightbox(path, page) {
  const url = `/api/jobs/${curJob}/asset?path=${encodeURIComponent(path)}`;
  _openLightbox(page ? `图像证据 · P${page}` : '图像证据', `<img src="${url}" alt="证据图像">`, page, url);
}
function openTableLightbox(html, page) {
  _openLightbox(page ? `表格证据 · P${page}` : '表格证据', `<div class="table-html">${html}</div>`, page, null);
}
document.addEventListener('click', e => {
  const tbtn = e.target.closest && e.target.closest('.ev-thumb-table');
  if (tbtn && tbtn.dataset.thtml) { openTableLightbox(tbtn.dataset.thtml, tbtn.dataset.page); return; }
  const thumb = e.target.closest && e.target.closest('.ev-thumb');
  if (thumb && thumb.dataset.img) openImageLightbox(thumb.dataset.img, thumb.dataset.page);
});
// 图像资源缺失时移除缩略图，不影响文本证据
document.addEventListener('error', e => {
  if (e.target && e.target.classList && e.target.classList.contains('ev-thumb')) e.target.remove();
}, true);
$('#lightboxClose').addEventListener('click', () => $('#imageLightbox').classList.add('hidden'));
$('#imageLightbox').addEventListener('click', e => { if (e.target === $('#imageLightbox')) $('#imageLightbox').classList.add('hidden'); });
$('#lightboxOpenPage').addEventListener('click', e => {
  const pg = +e.currentTarget.dataset.page;
  $('#imageLightbox').classList.add('hidden');
  if (pg) openPageDrawer(pg);
});

// ===== Rule Engine =====
let reState = { page: 1, size: 10 };
function renderRuleEngine() {
  const re = ruleEngineData; if (!re) { $('#ruleEngineStats').innerHTML = '<div class="stat-card"><div class="stat-value">—</div><div class="stat-title">规则引擎未运行</div></div>'; return; }
  $('#ruleEngineStats').innerHTML = statCardsHtml([
    ['all','总规则数',re.total_rules], ['COMPLIANT','合规',re.compliant], ['VIOLATED','违规',re.violated], ['UNCERTAIN','无法判定',re.uncertain], ['NOT_APPLICABLE','不适用',re.not_applicable], ['PENDING_CONFIRMATION','待确认',re.pending_confirmation||0]
  ], $('#ruleEngineStatusFilter').value);
  $$('#ruleEngineStats .stat-card').forEach(c => c.addEventListener('click', () => {
    $('#ruleEngineStatusFilter').value = c.dataset.f;
    reState.page = 1;
    renderRuleEngineTable($('#ruleEngineModuleFilter').value, c.dataset.f);
  }));

  // Populate module filter
  const mods = [...new Set((re.results||[]).map(r => r.module))].filter(Boolean);
  const sel = $('#ruleEngineModuleFilter');
  if (sel.options.length <= 1) {
    mods.forEach(m => { const opt = document.createElement('option'); opt.value = m; opt.textContent = MODULE_CN[m]||m; sel.appendChild(opt); });
  }
  renderRuleEngineTable('all','all');
  $('#ruleEngineModuleFilter').onchange = function() { renderRuleEngineTable(this.value, $('#ruleEngineStatusFilter').value); };
  $('#ruleEngineStatusFilter').onchange = function() { renderRuleEngineTable($('#ruleEngineModuleFilter').value, this.value); };
  const drawer = $('#ruleEngineDetailPanel');
  drawer.querySelector('.drawer-close').addEventListener('click', () => drawer.classList.add('hidden'));
  drawer.addEventListener('click', e => { if (e.target === drawer) drawer.classList.add('hidden'); });
}

function renderRuleEngineTable(modFilter, stFilter) {
  const re = ruleEngineData; if (!re) return;
  $$('#ruleEngineStats .stat-card').forEach(x => x.classList.toggle('active', x.dataset.f === stFilter));
  const results = (re.results||[]).filter(r => {
    if (modFilter !== 'all' && r.module !== modFilter) return false;
    if (stFilter !== 'all' && r.status !== stFilter) return false;
    return true;
  });
  const shown = slicePage(results, reState);
  $('#ruleEngineRows').innerHTML = shown.length ? shown.map(r => {
    const th = r.threshold||{}; const thStr = th.value !== undefined ? `${th.operator||''} ${th.value}${th.unit||''}` : '—';
    const valStr = r.actual_value !== null && r.actual_value !== undefined ? `${r.actual_value}${th.unit||''}` : '—';
    return `<tr>
      <td><b>${esc(r.rule_id)}</b></td>
      <td>${esc(r.rule_name)}</td>
      <td><small>${esc(MODULE_CN[r.module]||r.module)}</small></td>
      <td><span class="tag-${r.severity==='A-mandatory'?'orange':'default'}">${esc(SEVERITY_CN[r.severity]||r.severity)}</span></td>
      <td><span class="status-chip status-${r.status}">${RE_STATUS_CN[r.status]||r.status}</span></td>
      <td>${valStr}</td><td>${thStr}</td>
      <td><small>${esc(r.reason||'')}</small></td>
      <td><button class="btn-small btn-detail" data-rule="${esc(r.rule_id)}">详情</button></td>
    </tr>`;
  }).join('') : '<tr><td colspan="9" style="text-align:center;color:var(--text-tertiary)">无符合条件的规则</td></tr>';
  $('#ruleEnginePager').innerHTML = pagerHtml(reState, results.length);
  bindPager('#ruleEnginePager', reState, () => renderRuleEngineTable(modFilter, stFilter));
  $$('#ruleEngineRows .btn-detail').forEach(b => b.addEventListener('click', () => openRuleEngineDrawer(b.dataset.rule)));
}

function openRuleEngineDrawer(rid) {
  const re = ruleEngineData; if (!re) return;
  const rule = (re.results||[]).find(r => r.rule_id === rid); if (!rule) return;
  const th = rule.threshold||{}; const ev = rule.evidence||[];
  const evHtml = ev.length ? ev.map(e => `<div class="evidence-block"><div class="meta"><span><b>页 ${e.page||'—'}</b></span><span>${esc(e.block_id||'')}</span><span>${esc(e.section||'')}</span></div>${evThumb(e, e.page)}<blockquote>${esc(e.quote||'')}</blockquote></div>`).join('') : '<p style="color:var(--text-tertiary)">无证据</p>';
  $('#reDrawerTitle').textContent = `${rule.rule_id} — ${rule.rule_name}`;
  $('#reDrawerBody').innerHTML = `
    <div class="detail-section"><h4>审查结果</h4>
      <p><span class="status-chip status-${rule.status}">${RE_STATUS_CN[rule.status]||rule.status}</span></p>
      <p>${esc(rule.reason||'')}</p></div>
    <div class="detail-section"><h4>参数比对</h4>
      <div style="display:grid;grid-template-columns:1fr 1fr;gap:8px">
        <div><b>实际值</b><br>${rule.actual_value !== null && rule.actual_value !== undefined ? esc(`${rule.actual_value}${th.unit||''}`) : '未提取到'}</div>
        <div><b>阈值要求</b><br>${esc(`${th.operator||''} ${th.value}${th.unit||''}`)}</div>
      </div></div>
    <div class="detail-section"><h4>规范依据</h4>
      <p><b>${esc(rule.code_ref?.standard||'')}</b></p>
      <p style="color:var(--text-secondary)">${esc(rule.code_ref?.original_text||'')}</p></div>
    <div class="detail-section"><h4>整改建议</h4>
      <p>${esc(rule.remedy_suggestion||'')}</p></div>
    <div class="detail-section"><h4>典型违规表现</h4>
      <p>${esc(rule.typical_violation||'')}</p></div>
    <div class="detail-section"><h4>证据</h4>${evHtml}</div>`;
  $('#ruleEngineDetailPanel').classList.remove('hidden');
}

// ===== Completeness Review =====
function renderReview() {
  const results = revData?.results||[];
  if (difyErr) { $('#difyWarning').textContent = `⚠ Dify审查失败：${difyErr.message||''}`; $('#difyWarning').classList.remove('hidden'); }
  else if (!compData) { $('#difyWarning').textContent = 'ℹ Dify审查未启用'; $('#difyWarning').classList.remove('hidden'); }
  else { $('#difyWarning').classList.add('hidden'); }
  renderReviewTable('all');
  $('#reviewFilter').onchange = function() { renderReviewTable(this.value); };
  const rd = $('#reviewDetailPanel');
  rd.querySelector('.drawer-close').addEventListener('click', () => rd.classList.add('hidden'));
  rd.addEventListener('click', e => { if (e.target === rd) rd.classList.add('hidden'); });
}
function renderReviewTable(f) {
  const results = revData?.results||[]; const cb = {}; (compData?.results||[]).forEach(r => cb[r.rule_id]=r);
  const db = {}; decisions.forEach(d => db[d.rule_id]=d);
  const filtered = results.filter(r => {
    const c = cb[r.rule_id]||{}; const d = db[r.rule_id];
    const nr = (c.manual_review)||r.status==='MISSING'||r.status==='UNCERTAIN'||r.requires_human_review||(d&&d.human_decision==='pending');
    if (f==='manual-review') return nr; if (f==='disagree') return c?.comparison_status==='DISAGREEMENT';
    if (f==='MISSING') return r.status==='MISSING'; if (f==='UNCERTAIN') return r.status==='UNCERTAIN'; return true;
  });
  $('#reviewRows').innerHTML = filtered.map(r => {
    const c = cb[r.rule_id]||{}; const d = db[r.rule_id];
    const ll = STATUS_CN[r.status]||r.status; const dl = c.dify_status;
    const compLbl = c?.comparison_status ? (COMP_CN[c.comparison_status]||'') : '未请求';
    const humanLbl = d && d.human_decision !== 'pending' ? (HUMAN_CN[d.human_decision]||'') : '待复核';
    
    // 本地预审列：部分匹配显示黄色"部分匹配"，完全匹配显示绿色"已识别"
    let localChip, localClass;
    if (r.status === 'PASS' && r.needs_semantic_review) {
      localChip = '部分匹配';
      localClass = 'status-PARTIAL';
    } else if (r.status === 'PASS') {
      localChip = '已识别';
      localClass = 'status-PASS';
    } else {
      localChip = ll;
      localClass = `status-${r.status}`;
    }
    
    // Dify列：只有三种状态 - 已复核(绿)、未复核(绿)、复核失败(橙)
    let difyChip, difyClass;
    const src = c.dify_result_source;
    const comp = c.comparison_status;
    if (src === 'failed') {
      difyChip = '复核失败';
      difyClass = 'status-UNCERTAIN'; // 橙色
    } else if (src === 'not_requested') {
      difyChip = '未复核';
      difyClass = 'status-PASS'; // 绿色
    } else if (src === 'cache' || src === 'api' || comp === 'AGREEMENT' || comp === 'DISAGREEMENT') {
      difyChip = '已复核';
      difyClass = 'status-PASS'; // 绿色
    } else {
      difyChip = '未复核';
      difyClass = 'status-PASS'; // 绿色
    }
    
    const compClass = c?.comparison_status === 'DISAGREEMENT' ? 'comp-disagree' : '';
    return `<tr><td><b>${esc(r.rule_id)}</b></td><td>${esc(r.name)}</td>
      <td><span class="status-chip ${localClass}">${localChip}</span></td>
      <td><span class="status-chip ${difyClass}">${difyChip}</span></td>
      <td class="${compClass}">${esc(compLbl)}</td><td>${esc(humanLbl)}</td>
      <td><button class="btn-small btn-detail" data-rule="${esc(r.rule_id)}">详情</button></td></tr>`;
  }).join('');
  $$('#reviewRows .btn-detail').forEach(b => b.addEventListener('click', () => openReviewDrawer(b.dataset.rule)));
}
function openReviewDrawer(rid) {
  const results = revData?.results||[]; const rule = results.find(r => r.rule_id===rid); if (!rule) return;
  const cb = {}; (compData?.results||[]).forEach(r => cb[r.rule_id]=r);
  const comp = cb[rid]||{};
  const isDisagree = comp.comparison_status === 'DISAGREEMENT';
  
  // 本地证据
  const localEv = (rule.evidence||[]).map(e => `<div class="evidence-block"><div class="meta"><span><b>页 ${e.physical_page}</b></span><span>${esc(e.block_type||'')}</span></div>${evThumb(e, e.physical_page)}<blockquote>${esc(e.quote||e.description||'')}</blockquote></div>`).join('') || '<p style="color:var(--text-tertiary)">无证据</p>';
  
  // Dify 证据（不一致时显示）
  let difySection = '';
  if (isDisagree && comp.dify_evidence && comp.dify_evidence.length > 0) {
    const difyEv = comp.dify_evidence.map(e => `<div class="evidence-block"><div class="meta"><span><b>页 ${e.physical_page||'—'}</b></span><span>${esc(e.block_type||'')}</span></div><blockquote>${esc(e.quote||e.description||'')}</blockquote></div>`).join('');
    difySection = `<div class="detail-section"><h4>Dify 语义复核证据 <span class="status-chip status-MISSING">不一致</span></h4><p style="color:var(--text-secondary);margin-bottom:8px">${esc(comp.dify_reason||'')}</p>${difyEv}</div>`;
  } else if (isDisagree) {
    difySection = `<div class="detail-section"><h4>Dify 语义复核证据 <span class="status-chip status-MISSING">不一致</span></h4><p style="color:var(--text-secondary)">${esc(comp.dify_reason||'Dify 未返回证据')}</p></div>`;
  }
  
  // 一致性说明
  let consistencyNote = '';
  if (isDisagree) {
    consistencyNote = `<div class="detail-section" style="background:var(--error-bg);padding:12px;border-radius:8px;margin-bottom:16px"><p style="color:var(--error);font-weight:600;margin:0">⚠ 本地预审与 Dify 复核结论不一致</p><p style="margin:8px 0 0 0;color:var(--text-secondary)">本地判定：<span class="status-chip status-${rule.status}">${STATUS_CN[rule.status]||rule.status}</span>，Dify 判定：${esc(comp.dify_status||'未知')}。请以人工复核为准。</p></div>`;
  }
  
  $('#reviewDrawerTitle').textContent = `${rule.rule_id} — ${rule.name}`;
  $('#reviewDrawerBody').innerHTML = `${consistencyNote}<div class="detail-section"><h4>检查要求</h4><p>${esc(rule.reason)}</p><p>本地预审结果：<span class="status-chip status-${rule.status}">${STATUS_CN[rule.status]||rule.status}</span></p></div><div class="detail-section"><h4>本地预审证据</h4>${localEv}</div>${difySection}`;
  $('#reviewDetailPanel').classList.remove('hidden');
}

// ===== Semantic Review (规范语义审查) =====
let semState = { page: 1, size: 10 };
function renderSemantic() {
  // Combine deterministic (ruleEngineData) and semantic (semanticData) results
  const detResults = ruleEngineData?.results || [];
  const semResults = semanticData?.results || [];
  const allResults = [...detResults, ...semResults];
  const detTotal = ruleEngineData?.total_rules || 0;
  const semTotal = semanticData?.total_rules || 0;
  const total = detTotal + semTotal;
  const compliant = (ruleEngineData?.compliant||0) + (semanticData?.compliant||0);
  const violated = (ruleEngineData?.violated||0) + (semanticData?.violated||0);
  const uncertain = (ruleEngineData?.uncertain||0) + (semanticData?.uncertain||0);
  const notApp = (ruleEngineData?.not_applicable||0) + (semanticData?.not_applicable||0);
  const pendingConf = (ruleEngineData?.pending_confirmation||0) + (semanticData?.pending_confirmation||0);
  if (!total) {
    $('#semanticStats').innerHTML = '<div class="stat-card"><div class="stat-value">—</div><div class="stat-title">规范语义审查未运行</div></div>';
    $('#semanticRows').innerHTML = '<tr><td colspan="7" style="text-align:center;color:var(--text-tertiary)">请先上传方案执行审查</td></tr>';
    return;
  }
  $('#semanticStats').innerHTML = statCardsHtml([
    ['all','总规则数',total], ['COMPLIANT','合规',compliant], ['VIOLATED','违规',violated], ['UNCERTAIN','无法判定',uncertain], ['NOT_APPLICABLE','不适用',notApp], ['PENDING_CONFIRMATION','待确认',pendingConf]
  ], $('#semanticStatusFilter').value);
  $$('#semanticStats .stat-card').forEach(c => c.addEventListener('click', () => {
    $('#semanticStatusFilter').value = c.dataset.f;
    semState.page = 1;
    renderSemanticTable();
  }));
  // Populate module filter from all results
  const mods = [...new Set(allResults.map(r => r.module))].filter(Boolean);
  const modSel = $('#semanticModuleFilter');
  if (modSel.options.length <= 1) { mods.forEach(m => { const o=document.createElement('option'); o.value=m; o.textContent=MODULE_CN[m]||m; modSel.appendChild(o); }); }
  // Populate standard filter from results
  const stdSel = $('#semanticStandardFilter');
  if (stdSel.options.length <= 1 && standardsData) {
    const stdIds = new Set();
    allResults.forEach(r => { (r.standard_refs||[]).forEach(id => stdIds.add(id)); });
    (standardsData.standards||[]).forEach(s => {
      if (stdIds.has(s.standard_id)) {
        const o = document.createElement('option');
        o.value = s.standard_id;
        o.textContent = s.full_code;
        o.title = s.name;
        stdSel.appendChild(o);
      }
    });
  }
  renderSemanticTable();
  const refilter = () => { semState.page = 1; renderSemanticTable(); };
  $('#semanticModuleFilter').onchange = refilter;
  $('#semanticStatusFilter').onchange = refilter;
  $('#semanticSeverityFilter').onchange = refilter;
  $('#semanticStandardFilter').onchange = refilter;
  const drawer = $('#semanticDetailPanel');
  drawer.querySelector('.drawer-close').addEventListener('click', () => drawer.classList.add('hidden'));
  drawer.addEventListener('click', e => { if (e.target === drawer) drawer.classList.add('hidden'); });
}
function renderSemanticTable() {
  const allResults = [...(ruleEngineData?.results||[]), ...(semanticData?.results||[])];
  const modF = $('#semanticModuleFilter').value;
  const stF = $('#semanticStatusFilter').value;
  const sevF = $('#semanticSeverityFilter').value;
  const stdF = $('#semanticStandardFilter').value;
  $$('#semanticStats .stat-card').forEach(x => x.classList.toggle('active', x.dataset.f === stF));
  const results = allResults.filter(r => {
    if (modF!=='all' && r.module!==modF) return false;
    if (stF!=='all' && r.status!==stF) return false;
    if (sevF!=='all' && r.severity!==sevF) return false;
    if (stdF!=='all' && !(r.standard_refs||[]).includes(stdF)) return false;
    return true;
  });
  const shown = slicePage(results, semState);
  $('#semanticRows').innerHTML = shown.length ? shown.map(r => {
    const th = r.threshold||{};
    const thStr = th.value!==undefined ? `${th.operator||''} ${th.value}${th.unit||''}` : '—';
    const valStr = r.actual_value!==null && r.actual_value!==undefined ? `${r.actual_value}${th.unit||''}` : '—';
    const combined = valStr !== '—' || thStr !== '—' ? `${valStr} / ${thStr}` : '—';
    const typeTag = r.check_type==='semantic' ? '<span class="tag-blue">语义</span>' : '<span class="tag-default">确定性</span>';
    return `<tr><td><b>${esc(r.rule_id)}</b></td><td>${esc(r.rule_name)} ${typeTag}</td><td>${esc(MODULE_CN[r.module]||r.module)}</td><td><span class="tag-${r.severity==='A-mandatory'?'orange':'default'}">${esc(SEVERITY_CN[r.severity]||r.severity)}</span></td><td><span class="status-chip status-${r.status}">${RE_STATUS_CN[r.status]||r.status}</span></td><td>${esc(combined)}</td><td><button class="btn-small btn-detail" data-rule="${esc(r.rule_id)}" data-type="${esc(r.check_type||'')}">详情</button></td></tr>`;
  }).join('') : '<tr><td colspan="7" style="text-align:center;color:var(--text-tertiary)">无符合条件的规则</td></tr>';
  $('#semanticPager').innerHTML = pagerHtml(semState, results.length);
  bindPager('#semanticPager', semState, renderSemanticTable);
  $$('#semanticRows .btn-detail').forEach(b => b.addEventListener('click', () => openSemanticDrawer(b.dataset.rule, b.dataset.type, allResults)));
}
function openSemanticDrawer(rid, rtype, allResults) {
  const rule = (allResults||[]).find(r => r.rule_id===rid); if (!rule) return;
  const th = rule.threshold||{}; const ev = rule.evidence||[];
  const evHtml = ev.length ? ev.map(e => `<div class="evidence-block"><div class="meta"><span><b>页 ${e.page||'—'}</b></span></div>${evThumb(e, e.page)}<blockquote>${esc(e.quote||'')}</blockquote></div>`).join('') : '<p style="color:var(--text-tertiary)">无证据</p>';
  const sjHtml = rule.semantic_judgment ? `<div class="detail-section"><h4>语义判断指引</h4><p>${esc(rule.semantic_judgment)}</p></div>` : '';
  $('#semanticDrawerTitle').textContent = `${rule.rule_id} — ${rule.rule_name}`;
  $('#semanticDrawerBody').innerHTML = `<div class="detail-section"><h4>审查结果</h4><p><span class="status-chip status-${rule.status}">${RE_STATUS_CN[rule.status]||rule.status}</span></p><p>${esc(rule.reason||'')}</p></div><div class="detail-section"><h4>参数比对</h4><div style="display:grid;grid-template-columns:1fr 1fr;gap:8px"><div><b>实际值</b><br>${rule.actual_value!==null?esc(`${rule.actual_value}${th.unit||''}`):'—'}</div><div><b>阈值要求</b><br>${th.value!==undefined?esc(`${th.operator||''} ${th.value}${th.unit||''}`):'—'}</div></div></div>${sjHtml}<div class="detail-section"><h4>规范依据</h4><p><b>${esc(rule.code_ref?.standard||'')}</b></p><p style="color:var(--text-secondary)">${esc(rule.code_ref?.original_text||'')}</p></div><div class="detail-section"><h4>整改建议</h4><p>${esc(rule.remedy_suggestion||'')}</p></div><div class="detail-section"><h4>典型违规表现</h4><p>${esc(rule.typical_violation||'')}</p></div><div class="detail-section"><h4>证据</h4>${evHtml}</div>`;
  $('#semanticDetailPanel').classList.remove('hidden');
}

// ===== Calculation Review (计算校核) =====
let calcState = { page: 1, size: 10 }, consState = { page: 1, size: 10 };
let calcFilter = 'all', consFilter = 'all';
function renderCalculation() {
  const calc = calcData;
  const items = preData?.consistency_review||[];
  const calcResults = calc?.results || [];
  $('#calcStats').innerHTML = statCardsHtml([
    ['all','验算项',calc?.total_rules||0], ['COMPLIANT','验算通过',calc?.compliant||0], ['VIOLATED','验算问题',calc?.violated||0], ['UNCERTAIN','无法判定',calc?.uncertain||0]
  ], calcFilter);
  $('#consStats').innerHTML = statCardsHtml([
    ['all','参数校核项',items.length],
    ['PASS','一致',items.filter(i => i.status==='PASS').length],
    ['ISSUE','不一致',items.filter(i => i.status==='ISSUE').length],
    ['REVIEW','需复核',items.filter(i => i.status==='REVIEW').length]
  ], consFilter);
  $$('#calcStats .stat-card').forEach(c => c.addEventListener('click', () => { calcFilter = c.dataset.f; calcState.page = 1; renderCalculation(); }));
  $$('#consStats .stat-card').forEach(c => c.addEventListener('click', () => { consFilter = c.dataset.f; consState.page = 1; renderCalculation(); }));

  // 公式验算表格
  const filteredCalc = calcResults.filter(r => calcFilter==='all' || r.status===calcFilter);
  const shownCalc = slicePage(filteredCalc, calcState);
  $('#calcRows').innerHTML = shownCalc.length ? shownCalc.map(r => {
    return `<tr><td><b>${esc(r.rule_id)}</b></td><td>${esc(r.rule_name)}</td><td>${esc(MODULE_CN[r.module]||r.module)}</td><td><span class="tag-${r.severity==='A-mandatory'?'orange':'default'}">${esc(SEVERITY_CN[r.severity]||r.severity)}</span></td><td><span class="status-chip status-${r.status}">${RE_STATUS_CN[r.status]||r.status}</span></td><td><button class="btn-small btn-detail" data-rule="${esc(r.rule_id)}">详情</button></td></tr>`;
  }).join('') : '<tr><td colspan="6" style="text-align:center;color:var(--text-tertiary)">无符合条件的验算项</td></tr>';
  $('#calcPager').innerHTML = pagerHtml(calcState, filteredCalc.length);
  bindPager('#calcPager', calcState, renderCalculation);

  // 参数一致性表格
  const filteredCons = items.filter(i => consFilter==='all' || i.status===consFilter);
  const shownCons = slicePage(filteredCons, consState);
  $('#consRows').innerHTML = shownCons.length ? shownCons.map(i => {
    const dv = i.design_side?.value;
    const cv = i.calculation_side?.value;
    const dvStr = dv!=null ? (Array.isArray(dv) ? dv.join('/') : `${dv}`) : '—';
    const cvStr = cv!=null ? (Array.isArray(cv) ? cv.join('/') : `${cv}`) : '—';
    return `<tr><td><b>${esc(i.review_item_id)}</b></td><td>${esc(i.title)}</td><td>${esc(dvStr)}</td><td>${esc(cvStr)}</td><td><span class="status-chip status-${i.status}">${stTxt(i.status)}</span></td><td><button class="btn-small btn-detail" data-id="${esc(i.review_item_id)}">详情</button></td></tr>`;
  }).join('') : '<tr><td colspan="6" style="text-align:center;color:var(--text-tertiary)">无符合条件的检查项</td></tr>';
  $('#consPager').innerHTML = pagerHtml(consState, filteredCons.length);
  bindPager('#consPager', consState, renderCalculation);
  $$('#calcRows .btn-detail').forEach(b => b.addEventListener('click', () => openCalcDrawer(b.dataset.rule)));
  $$('#consRows .btn-detail').forEach(b => b.addEventListener('click', () => openConsDrawer(b.dataset.id)));
}
function openCalcDrawer(ruleId) {
  const calc = calcData; if (!calc) return;
  const rule = (calc.results||[]).find(r => r.rule_id === ruleId); if (!rule) return;
  const evs = (rule.evidence||[]).map(e => `<div class="evidence-block"><div class="meta"><span><b>页 ${e.page||'—'}</b></span><span>${esc(e.block_type||'')}</span></div><blockquote>${esc(e.quote||'')}</blockquote></div>`).join('') || '<p style="color:var(--text-tertiary)">无证据</p>';
  const formulaHtml = rule.formula ? `<p><code>${esc(rule.formula)}</code></p>` : '';
  $('#calcDrawerTitle').textContent = `${rule.rule_id} — ${rule.rule_name}`;
  $('#calcDrawerBody').innerHTML = `<div class="detail-section"><h4>审查结果</h4><p><span class="status-chip status-${rule.status}">${RE_STATUS_CN[rule.status]||rule.status}</span></p><p>${esc(rule.reason||'')}</p>${formulaHtml}</div><div class="detail-section"><h4>规范依据</h4><p><b>${esc(rule.code_ref?.standard||'')}</b></p><p style="color:var(--text-secondary)">${esc(rule.code_ref?.original_text||'')}</p></div><div class="detail-section"><h4>整改建议</h4><p>${esc(rule.remedy_suggestion||'')}</div><div class="detail-section"><h4>典型违规表现</h4><p>${esc(rule.typical_violation||'')}</div><div class="detail-section"><h4>证据</h4>${evs}</div>`;
  $('#calcDetailPanel').classList.remove('hidden');
  const drawer = $('#calcDetailPanel');
  drawer.querySelector('.drawer-close').onclick = () => drawer.classList.add('hidden');
  drawer.onclick = e => { if (e.target === drawer) drawer.classList.add('hidden'); };
}
function openConsDrawer(id) {
  const items = preData?.consistency_review||[];
  const item = items.find(i => i.review_item_id === id); if (!item) return;
  const dEv = (item.design_side?.evidence||[]).map(e => `<div class="evidence-block"><div class="meta"><span><b>页 ${e.page||'—'}</b></span></div><blockquote>${esc(e.quote||'')}</blockquote></div>`).join('') || '<p style="color:var(--text-tertiary)">无证据</p>';
  const cEv = (item.calculation_side?.evidence||[]).map(e => `<div class="evidence-block"><div class="meta"><span><b>页 ${e.page||'—'}</b></span></div><blockquote>${esc(e.quote||'')}</blockquote></div>`).join('') || '<p style="color:var(--text-tertiary)">无证据</p>';
  const dv = item.design_side?.value; const cv = item.calculation_side?.value;
  const dvStr = dv!=null ? (Array.isArray(dv) ? dv.join('/') : `${dv}`) : '未识别';
  const cvStr = cv!=null ? (Array.isArray(cv) ? cv.join('/') : `${cv}`) : '未识别';
  $('#calcDrawerTitle').textContent = `${item.review_item_id} — ${item.title}`;
  $('#calcDrawerBody').innerHTML = `<div class="detail-section"><h4>审查结果</h4><p><span class="status-chip status-${item.status}">${stTxt(item.status)}</span></p><p>${esc(item.conclusion||'')}</p></div><div class="detail-section"><h4>参数比对</h4><div style="display:grid;grid-template-columns:1fr 1fr;gap:8px"><div><b>正文/构造侧</b><br>${esc(dvStr)}</div><div><b>计算书侧</b><br>${esc(cvStr)}</div></div></div><div class="detail-section"><h4>正文/构造侧证据</h4>${dEv}</div><div class="detail-section"><h4>计算书侧证据</h4>${cEv}</div>${item.boundary?`<div class="detail-section"><h4>说明</h4><p style="color:var(--text-tertiary)">${esc(item.boundary)}</p></div>`:''}`;
  $('#calcDetailPanel').classList.remove('hidden');
  const drawer = $('#calcDetailPanel');
  drawer.querySelector('.drawer-close').onclick = () => drawer.classList.add('hidden');
  drawer.onclick = e => { if (e.target === drawer) drawer.classList.add('hidden'); };
}

// ===== Drawing =====
let drawState = { page: 1, size: 10 };
let drawFilter = 'all';
function renderDrawing() {
  const items = preData?.drawing_review||[]; const s = preData?.summary||{};
  $('#drawingStats').innerHTML = statCardsHtml([
    ['all','检查项',s.drawing_total??items.length],
    ['review','需人工复核',s.drawing_review??items.filter(i => i.requires_human_review).length],
    ['PASS','一致',items.filter(i => i.status==='PASS').length],
    ['ISSUE','不一致',items.filter(i => i.status==='ISSUE').length]
  ], drawFilter);
  $$('#drawingStats .stat-card').forEach(c => c.addEventListener('click', () => { drawFilter = c.dataset.f; drawState.page = 1; renderDrawing(); }));
  const filtered = items.filter(i => drawFilter==='all' || (drawFilter==='review' ? i.requires_human_review : i.status===drawFilter));
  const shown = slicePage(filtered, drawState);
  $('#drawingRows').innerHTML = shown.length ? shown.map(i => {
    const bv = i.body_value!=null ? `${i.body_value}` : '—';
    const dv = i.drawing_value!=null ? `${i.drawing_value}` : '—';
    return `<tr><td><b>${esc(i.review_item_id)}</b></td><td>${esc(i.title)}</td><td>${esc(bv)}</td><td>${esc(dv)}</td><td><span class="status-chip status-${i.status}">${stTxt(i.status)}</span></td><td><button class="btn-small btn-detail" data-id="${esc(i.review_item_id)}">详情</button></td></tr>`;
  }).join('') : '<tr><td colspan="6" style="text-align:center;color:var(--text-tertiary)">暂无结果</td></tr>';
  $('#drawingPager').innerHTML = pagerHtml(drawState, filtered.length);
  bindPager('#drawingPager', drawState, renderDrawing);
  $$('#drawingRows .btn-detail').forEach(b => b.addEventListener('click', () => openDrawingDrawer(b.dataset.id)));
}
function openDrawingDrawer(id) {
  const items = preData?.drawing_review||[];
  const item = items.find(i => i.review_item_id === id); if (!item) return;
  const evT = (item.text_evidence||[]).map(e => {
    const pg = e.page || e.physical_page;
    return `<div class="evidence-block"><div class="meta"><span><b>页 ${pg||'—'}</b></span><span>${esc(e.section||'')}</span></div>${evThumb(e, pg)}<blockquote>${esc(e.quote||'')}</blockquote></div>`;
  }).join('') || '<p style="color:var(--text-tertiary)">无正文证据</p>';
  const evD = (item.drawing_evidence||[]).map(e => {
    const pg = e.physical_page||e.page;
    const lbl = e.quote ? `标注「${esc(e.quote)}」` : (e.keyword_hits||[]).map(esc).join('、');
    return `<div class="evidence-block"><div class="meta"><span><b>页 ${pg||'—'}</b></span></div>${pg?`<div class="ev-thumb-wrap"><button class="btn-small jq-page" data-page="${pg}">查看图纸 P${pg}</button></div>`:''}<blockquote>${esc(lbl)}${e.value!=null?` = <b>${e.value}</b>`:''}</blockquote></div>`;
  }).join('') || '<p style="color:var(--text-tertiary)">无图纸证据</p>';
  const cmp = (item.body_value!=null || item.drawing_value!=null) ? `<div style="display:grid;grid-template-columns:1fr 1fr;gap:8px;margin-top:8px"><div><b>正文值</b><br>${esc(item.body_value??'—')}</div><div><b>图纸标注值</b><br>${esc(item.drawing_value??'—')}</div></div>` : '';
  $('#drawingDrawerTitle').textContent = `${item.review_item_id} — ${item.title}`;
  $('#drawingDrawerBody').innerHTML = `<div class="detail-section"><h4>审查结果</h4><p><span class="status-chip status-${item.status}">${stTxt(item.status)}</span></p><p>${esc(item.conclusion||'')}</p>${cmp}</div><div class="detail-section"><h4>正文原文证据</h4>${evT}</div><div class="detail-section"><h4>图纸证据</h4>${evD}</div>${item.boundary?`<div class="detail-section"><h4>说明</h4><p style="color:var(--text-tertiary)">${esc(item.boundary)}</p></div>`:''}`;
  $('#drawingDetailPanel').classList.remove('hidden');
  $$('#drawingDrawerBody .jq-page').forEach(b => b.addEventListener('click', () => openPageDrawer(+b.dataset.page)));
  const drawer = $('#drawingDetailPanel');
  drawer.querySelector('.drawer-close').onclick = () => drawer.classList.add('hidden');
  drawer.onclick = e => { if (e.target === drawer) drawer.classList.add('hidden'); };
}

// ===== Manual（统一复核工作台） =====
const QUEUE_SOURCE_CN = { project_qualification:'工程识别', engine_scope:'审查范围', rule_engine:'规则引擎', semantic_engine:'规范语义', completeness_review:'完整性', substantive_review:'实质性审查', consistency_review:'参数一致性', drawing_review:'图文一致性', document_parse:'文档解析' };
function _queueKey(i) { return i.item_key || `${i.source}:${i.review_item_id}`; }
function renderManual() {
  const q = preData?.human_review_queue||[];
  const db = {}; decisions.forEach(d => db[d.item_key || `completeness_review:${d.rule_id}`] = d);
  const groups = [];
  q.forEach(item => {
    let g = groups.find(x => x.source === item.source);
    if (!g) { g = { source: item.source, items: [] }; groups.push(g); }
    g.items.push({ item, key: _queueKey(item), decision: db[_queueKey(item)] || { human_decision: 'pending' } });
  });
  const showAll = $('#showAllDecisions').checked;
  const visGroups = groups
    .map(g => ({ source: g.source, items: showAll ? g.items : g.items.filter(i => i.decision.human_decision === 'pending') }))
    .filter(g => g.items.length);
  const done = q.filter(i => { const d = db[_queueKey(i)]; return d && d.human_decision !== 'pending'; }).length;
  $('#manualProgress').textContent = `进度：${done}/${q.length} 已确认`;
  if (!visGroups.length) {
    $('#manualList').innerHTML = '<p style="text-align:center;padding:40px;color:var(--text-tertiary)">暂无待复核事项。</p>';
    return;
  }
  $('#manualList').innerHTML = visGroups.map(g => `
    <div class="manual-group"><h4>${QUEUE_SOURCE_CN[g.source]||g.source}（${g.items.length}）</h4>
    ${g.items.map(({item,key,decision}) => _manualItemHtml(item,key,decision)).join('')}</div>`).join('');
  bindManualEvents();
}
function _manualItemHtml(item, key, decision) {
  const isDone = decision.human_decision !== 'pending';
  const opts = item.source === 'completeness_review'
    ? ['pending','confirmed_pass','confirmed_missing','unable_to_verify','false_positive','need_supplement']
    : ['pending','confirmed','false_positive','unable_to_verify','need_supplement'];
  const chipLbl = RE_STATUS_CN[item.system_result]||STATUS_CN[item.system_result]||item.system_result||'';
  const pages = (item.evidence||[]).map(e => e.physical_page||e.page).filter(Boolean);
  const jumps = [];
  if (item.link) jumps.push(`<button type="button" class="btn-small jq-link" data-tab="${esc(item.link.tab)}" data-filter="${esc(item.link.filter||'')}">跳转查看</button>`);
  pages.slice(0,3).forEach(p => jumps.push(`<button type="button" class="btn-small jq-page" data-page="${p}">P${p}</button>`));
  if (item.source==='rule_engine'||item.source==='semantic_engine') jumps.push(`<button type="button" class="btn-small jq-rule" data-rule="${esc(item.review_item_id)}">规则详情</button>`);
  const actionable = item.actionable ? `
    <div class="field"><label>确认支撑体系（确认后重跑适用规则）</label>
      <div class="std-chips">${(item.actionable.options||[]).map(o => `<label class="std-chip"><input type="radio" name="rerunSystem" value="${esc(o.value)}"> ${esc(o.label)}（专属规则 ${o.pending_rule_count} 条）</label>`).join('')}</div>
      <button id="rerunBtn" type="button" class="btn-primary" style="margin-top:8px">确认并重跑适用规则</button><span id="rerunMsg" class="ml-16"></span></div>` : '';
  return `<div class="manual-item${isDone?' manual-done':''}" data-key="${esc(key)}">
    <div class="manual-head"><b>${esc(item.title||item.review_item_id)}</b><span class="status-chip status-${esc(item.system_result||'UNCERTAIN')}">${esc(chipLbl)}</span></div>
    ${item.reason?`<p class="manual-reason">${esc(item.reason)}</p>`:''}
    ${jumps.length?`<div class="manual-jumps">${jumps.join(' ')}</div>`:''}
    <div class="manual-body"><div class="field"><label>复核决定</label>
      <select data-key="${esc(key)}" class="manual-decision">
        ${opts.map(v => `<option value="${v}" ${decision.human_decision===v?'selected':''}>${HUMAN_CN[v]}</option>`).join('')}
      </select></div>
    <div class="field"><label>备注</label><textarea data-key="${esc(key)}" class="manual-note" maxlength="2000">${esc(decision.note||'')}</textarea></div></div>
    ${actionable}
  </div>`;
}
function bindManualEvents() {
  $$('#manualList .jq-link').forEach(b => b.addEventListener('click', () => {
    const tab = b.dataset.tab; switchTab(tab);
    if (tab==='document' && b.dataset.filter) { $('#pageFilter').value = b.dataset.filter; renderChapterTable(b.dataset.filter); }
  }));
  $$('#manualList .jq-page').forEach(b => b.addEventListener('click', () => { switchTab('document'); openPageDrawer(+b.dataset.page); }));
  $$('#manualList .jq-rule').forEach(b => b.addEventListener('click', () => {
    switchTab('semantic');
    openSemanticDrawer(b.dataset.rule, '', [...(ruleEngineData?.results||[]), ...(semanticData?.results||[])]);
  }));
  const rb = $('#rerunBtn');
  if (rb) rb.addEventListener('click', async () => {
    const sel = $('#manualList input[name="rerunSystem"]:checked');
    if (!sel) { $('#rerunMsg').textContent = '请先选择支撑体系'; return; }
    rb.disabled = true; $('#rerunMsg').textContent = '重跑中…';
    try {
      const r = await fetch(`/api/jobs/${curJob}/rerun`, { method:'POST', headers:{'Content-Type':'application/json'}, body: JSON.stringify({ overrides:{ support_system: sel.value } }) });
      const d = await r.json(); if (!r.ok) throw new Error(d.detail||'重跑失败');
      startPolling();
    } catch(e) { $('#rerunMsg').textContent = e.message; rb.disabled = false; }
  });
}
$('#showAllDecisions').addEventListener('change', renderManual);
$('#saveDecisions').addEventListener('click', saveAllDecisions);
$('#saveAndNext').addEventListener('click', async () => {
  await saveAllDecisions();
  const ni = $('#manualList .manual-item:not(.manual-done)');
  if (ni) ni.scrollIntoView({ behavior:'smooth', block:'center' });
  else $('#decisionMessage').textContent = '所有项目已完成复核';
});
async function saveAllDecisions() {
  const q = preData?.human_review_queue||[];
  const byKey = {}; q.forEach(i => byKey[_queueKey(i)] = i);
  const sels = $$('#manualList .manual-decision'); const tas = $$('#manualList .manual-note');
  const decs = [];
  for (let i=0; i<sels.length; i++) {
    const key = sels[i].dataset.key; const item = byKey[key]; if (!item) continue;
    const v = sels[i].value; const n = (tas[i]?.value||'').trim();
    if ((v==='confirmed_missing'||v==='false_positive'||v==='need_supplement') && !n) { alert(`${item.title||key}：需填写备注`); tas[i].focus(); return; }
    const base = { automatic_status: item.system_result||'UNCERTAIN', human_decision: v, human_decision_label: HUMAN_CN[v]||v, note: n };
    decs.push(item.source==='completeness_review' ? { rule_id: item.review_item_id, ...base } : { item_key: key, ...base });
  }
  if (!decs.length) { $('#decisionMessage').textContent = '无可保存项'; return; }
  $('#saveDecisions').disabled = true;
  try { const r = await fetch(`/api/jobs/${curJob}/decisions`, {method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({decisions:decs})}); const d = await r.json(); if (!r.ok) throw new Error(d.detail||'保存失败'); decisions = d.decisions||[]; $('#decisionMessage').textContent = `✓ 已保存 ${d.saved_count} 条`; renderReviewTable($('#reviewFilter').value); renderManual(); renderOverview(); } catch(e) { $('#decisionMessage').textContent = '保存失败: '+e.message; }
  $('#saveDecisions').disabled = false;
}

// ===== Rule Library Management =====
let ruleLibraryData = null;
let rlState = { page: 1, size: 10 };

async function loadRuleLibrary(mod='', type='', sev='', search='', std='') {
  const params = new URLSearchParams();
  if (mod) params.set('module', mod);
  if (type) params.set('check_type', type);
  if (sev) params.set('severity', sev);
  if (search) params.set('search', search);
  if (std) params.set('standard', std);
  try {
    const r = await fetch(`/api/rules?${params}`);
    if (!r.ok) throw new Error('加载失败');
    ruleLibraryData = await r.json();
    rlState.page = 1;
    renderRuleLibrary();
  } catch(e) { console.error('规则库加载失败:', e); }
}

function renderRuleLibrary() {
  if (!ruleLibraryData) return;
  const rules = ruleLibraryData.rules || [];
  const total = ruleLibraryData.total || 0;
  const typeCount = { deterministic:0, semantic:0, calculation:0 };
  const sevCount = { 'A-mandatory':0, 'B-required':0, 'C-recommended':0 };
  rules.forEach(r => { typeCount[r.check_type]=(typeCount[r.check_type]||0)+1; sevCount[r.severity]=(sevCount[r.severity]||0)+1; });
  $('#ruleLibraryStats').innerHTML = [
    ['总规则数', total], ['确定性', typeCount.deterministic||0], ['语义', typeCount.semantic||0], ['计算', typeCount.calculation||0], ['A级强制', sevCount['A-mandatory']||0], ['B级应执行', sevCount['B-required']||0]
  ].map(([l,v]) => `<div class="stat-card"><div class="stat-title">${l}</div><div class="stat-value">${v}</div></div>`).join('');
  // Populate module filter
  const mods = [...new Set(rules.map(r => r.module))].filter(Boolean);
  const sel = $('#rlModuleFilter');
  if (sel.options.length <= 1) { mods.forEach(m => { const o=document.createElement('option'); o.value=m; o.textContent=MODULE_CN[m]||m; sel.appendChild(o); }); }
  // Populate standard filter from registry（与工程基础信息"适用规范"同一词汇，按核心/参考分组）
  const stdSel = $('#rlStandardFilter');
  if (stdSel.options.length <= 1 && standardsData) {
    const groups = [['core', '核心规范'], ['reference', '参考规范']];
    groups.forEach(([tier, label]) => {
      const list = (standardsData.standards||[]).filter(s => (s.tier||'core') === tier);
      if (!list.length) return;
      const og = document.createElement('optgroup'); og.label = label;
      list.forEach(s => { 
        const o = document.createElement('option'); 
        o.value = s.standard_id; 
        o.textContent = s.full_code;
        o.title = `${s.name}（${s.rule_count||0}条）`;
        og.appendChild(o); 
      });
      stdSel.appendChild(og);
    });
  }
  // Paginate and render table
  const shown = slicePage(rules, rlState);
  $('#ruleLibraryRows').innerHTML = shown.length ? shown.map(r => {
    const typeLabel = { deterministic:'确定性', semantic:'语义', calculation:'计算' }[r.check_type]||r.check_type;
    const sevClass = r.severity==='A-mandatory'?'orange':'default';
    const sevLabel = SEVERITY_CN[r.severity]||r.severity;
    const stdText = (r.standard_refs||[]).map(id => STD_LABEL[id]||id).join(' / ') || (r.code_ref?.standard||'').substring(0,15);
    const actions = r.status==='active'
      ? `<button class="btn-small btn-detail" onclick="openRuleLibraryDrawer('${esc(r.rule_id)}')">详情</button>`
      : `<button class="btn-small btn-detail" onclick="openRuleLibraryDrawer('${esc(r.rule_id)}')">详情</button>`;
    return `<tr><td><b>${esc(r.rule_id)}</b></td><td>${esc(r.rule_name)}</td><td>${esc(MODULE_CN[r.module]||r.module)}</td><td>${typeLabel}</td><td><span class="tag-${sevClass}">${sevLabel}</span></td><td>${esc(stdText)}</td><td>${r.status==='active'?'<span class="tag-green">启用</span>':'<span class="tag-default">停用</span>'}</td><td>${actions}</td></tr>`;
  }).join('') : '<tr><td colspan="8" style="text-align:center;color:var(--text-tertiary)">无符合条件的规则</td></tr>';
  $('#ruleLibraryPager').innerHTML = pagerHtml(rlState, rules.length);
  bindPager('#ruleLibraryPager', rlState, renderRuleLibrary);
}

async function openRuleLibraryDrawer(rid) {
  try {
    const r = await fetch(`/api/rules/${encodeURIComponent(rid)}`);
    if (!r.ok) return;
    const rule = await r.json();
    const th = rule.threshold;
    const thStr = th ? (Array.isArray(th)
      ? th.map(t => `${t.param||''} ${t.operator||''} ${t.value||''}${t.unit||''}${t.applicable?` (${t.applicable})`:''}`).join('<br>')
      : `${th.param||''} ${th.operator||''} ${th.value||''}${th.unit||''}`)
      : '无';
    const cl = rule.check_logic || {};
    const clStr = `<div style="display:grid;grid-template-columns:1fr 1fr;gap:8px;font-size:13px"><div><b>描述</b><br>${esc(cl.description||'')}</div><div><b>提取关键词</b><br>${esc((cl.extraction_keywords||[]).join('、')||'无')}</div><div><b>操作符</b><br>${esc(cl.operator||'')}</div><div><b>判定条件</b><br>${esc(cl.fail_condition||cl.expected_value||'')}</div></div>`;
    $('#rlDrawerTitle').textContent = `${rule.rule_id} — ${rule.rule_name}`;
    $('#rlDrawerBody').innerHTML = `
      <div class="detail-section"><h4>规则信息</h4>
        <div style="display:grid;grid-template-columns:1fr 1fr;gap:8px;font-size:13px">
          <div><b>所属模块</b><br>${esc(MODULE_CN[rule.module]||rule.module)}</div>
          <div><b>审查方式</b><br>${esc(rule.check_type)}</div>
          <div><b>强制等级</b><br>${esc(SEVERITY_CN[rule.severity]||rule.severity)}</div>
          <div><b>风险等级</b><br>${esc(rule.risk_level||'')}</div>
          <div><b>适用支架类型</b><br>${esc((rule.applicable_types||[]).join('、'))}</div>
          <div><b>规则状态</b><br>${esc(rule.status)}</div>
        </div></div>
      <div class="detail-section"><h4>审查内容</h4><p>${esc(rule.check_content||'')}</p></div>
      <div class="detail-section"><h4>判定逻辑</h4>${clStr}</div>
      <div class="detail-section"><h4>限值参数</h4><p>${thStr}</p></div>
      <div class="detail-section"><h4>规范依据</h4>
        <p><b>${esc(rule.code_ref?.standard||'')}</b></p>
        <p style="color:var(--text-secondary)">${esc(rule.code_ref?.original_text||'')}</p></div>
      <div class="detail-section"><h4>整改建议</h4><p>${esc(rule.remedy_suggestion||'')}</p></div>
      <div class="detail-section"><h4>典型违规表现</h4><p>${esc(rule.typical_violation||'')}</p></div>
      <div class="detail-section"><h4>备注</h4><p>${esc(rule.notes||'')}</p></div>
      <div class="action-row" style="padding:0">
        <button class="btn-primary" onclick="editRule('${esc(rid)}')">编辑</button>
        <button class="btn-default" style="color:var(--error);border-color:var(--error)" onclick="if(confirm('确定删除此规则？（将标记为已停用）')) deleteRule('${esc(rid)}')">删除</button>
      </div>`;
    $('#ruleLibraryDetailPanel').classList.remove('hidden');
  } catch(e) { console.error('规则详情加载失败:', e); }
}

// Rule CRUD: add/edit/delete
window.editRule = function(rid) {
  // Close detail drawer if open
  $('#ruleLibraryDetailPanel').classList.add('hidden');
  // Open edit modal
  const modal = $('#ruleEditModal');
  $('#ruleEditTitle').textContent = `编辑规则 ${rid}`;
  fetch(`/api/rules/${encodeURIComponent(rid)}`).then(r => r.json()).then(rule => {
    $('#ruleEditBody').innerHTML = renderRuleEditForm(rule);
    modal.classList.remove('hidden');
  });
};
window.deleteRule = async function(rid) {
  if (!confirm(`确定删除规则 ${rid}？（将标记为已停用）`)) return;
  try {
    const r = await fetch(`/api/rules/${encodeURIComponent(rid)}`, { method: 'DELETE' });
    if (!r.ok) throw new Error('删除失败');
    await loadRuleLibrary($('#rlModuleFilter').value, $('#rlTypeFilter').value, $('#rlSeverityFilter').value, $('#rlSearch').value, rlStd());
  } catch(e) { alert('删除失败: '+e.message); }
};

function renderRuleEditForm(rule) {
  const fields = [
    ['rule_id', '规则编号', 'text'], ['rule_name', '规则名称', 'text'],
    ['module', '所属模块', 'text'], ['category', '规则分类', 'text'],
    ['check_type', '审查方式', 'text'], ['severity', '强制等级', 'text'],
    ['risk_level', '风险等级', 'text'], ['check_content', '审查内容', 'textarea'],
    ['remedy_suggestion', '整改建议', 'textarea'], ['typical_violation', '典型违规表现', 'textarea'],
    ['notes', '备注', 'textarea'],
  ];
  return fields.map(([key, label, type]) => {
    const val = rule[key] || '';
    if (type === 'textarea') return `<div class="manual-body" style="margin-bottom:12px"><div class="field full-width"><label>${label}</label><textarea id="ef_${key}" class="manual-note" maxlength="2000">${esc(String(val))}</textarea></div></div>`;
    return `<div class="manual-body" style="margin-bottom:12px"><div class="field"><label>${label}</label><input id="ef_${key}" type="text" class="manual-note" value="${esc(String(val))}"></div></div>`;
  }).join('');
}

$('#addRuleBtn')?.addEventListener('click', () => {
  $('#ruleEditTitle').textContent = '新增规则';
  $('#ruleEditBody').innerHTML = renderRuleEditForm({ rule_id:'', rule_name:'', module:'04_construction_requirements', category:'', check_type:'deterministic', severity:'B-required', risk_level:'medium', check_content:'', remedy_suggestion:'', typical_violation:'', notes:'' });
  $('#ruleEditModal').classList.remove('hidden');
});

// 规范版本校验
$('#versionValidationBtn')?.addEventListener('click', async () => {
  try {
    const res = await fetch('/api/rules/version-validation');
    const data = await res.json();
    let html = '';
    if (data.conflicts && data.conflicts.length > 0) {
      html += '<p style="color:var(--error);font-weight:600;margin-bottom:12px">⚠ 发现 ' + data.conflicts.length + ' 个规范存在版本冲突：</p>';
      data.conflicts.forEach(c => {
        html += '<div style="margin-bottom:16px;padding:12px;border:1px solid var(--error);border-radius:8px;background:var(--error-bg)">';
        html += '<p><b>' + c.standard + '</b> 存在多个版本：</p>';
        c.versions.forEach(v => {
          html += '<p style="margin:4px 0 4px 16px">v' + v.version + '：' + v.rule_ids.length + ' 条规则 → ' + v.rule_ids.slice(0, 5).join(', ') + (v.rule_ids.length > 5 ? '...' : '') + '</p>';
        });
        html += '</div>';
      });
    } else {
      html += '<p style="color:var(--success);font-weight:600;margin-bottom:12px">✅ 未发现规范版本冲突</p>';
    }
    html += '<h4 style="margin-top:20px">规范版本清单（共 ' + data.total_standards + ' 个规范）：</h4>';
    html += '<table class="data-table table-compact"><thead><tr><th>规范编号</th><th>版本</th><th>规则数</th></tr></thead><tbody>';
    const registry = data.registry || {};
    Object.keys(registry).sort().forEach(std => {
      const vers = registry[std];
      vers.forEach(v => {
        html += '<tr><td>' + std + '</td><td>' + v + '</td><td>—</td></tr>';
      });
    });
    html += '</tbody></table>';
    $('#versionValidationBody').innerHTML = html;
    $('#versionValidationModal').classList.remove('hidden');
  } catch (e) {
    $('#versionValidationBody').innerHTML = '<p style="color:var(--error)">校验失败：' + e.message + '</p>';
    $('#versionValidationModal').classList.remove('hidden');
  }
});
$('#versionValidationClose')?.addEventListener('click', () => $('#versionValidationModal').classList.add('hidden'));
$('#ruleEditCancel')?.addEventListener('click', () => $('#ruleEditModal').classList.add('hidden'));
$('#ruleEditSave')?.addEventListener('click', async () => {
  const data = {};
  ['rule_id','rule_name','module','category','check_type','severity','risk_level','check_content','remedy_suggestion','typical_violation','notes'].forEach(k => {
    const el = $(`#ef_${k}`);
    if (el) data[k] = el.value.trim();
  });
  const rid = data.rule_id;
  if (!rid) { alert('规则编号不能为空'); return; }
  try {
    // Try create first, if exists will get 409
    const r = await fetch('/api/rules', { method:'POST', headers:{'Content-Type':'application/json'}, body:JSON.stringify(data) });
    if (r.status === 409) {
      // Exists, update via patch for each field
      for (const [k,v] of Object.entries(data)) {
        if (k === 'rule_id') continue;
        await fetch(`/api/rules/${encodeURIComponent(rid)}`, { method:'PATCH', headers:{'Content-Type':'application/json'}, body:JSON.stringify({field:k, value:v}) });
      }
    } else if (!r.ok) {
      throw new Error((await r.json()).detail || '保存失败');
    }
    $('#ruleEditModal').classList.add('hidden');
    await loadRuleLibrary($('#rlModuleFilter').value, $('#rlTypeFilter').value, $('#rlSeverityFilter').value, $('#rlSearch').value, rlStd());
  } catch(e) { alert('保存失败: '+e.message); }
});

// Rule library filters
function rlStd() { return $('#rlStandardFilter').value; }
$('#rlModuleFilter').addEventListener('change', function() { loadRuleLibrary(this.value, $('#rlTypeFilter').value, $('#rlSeverityFilter').value, $('#rlSearch').value, rlStd()); });
$('#rlTypeFilter').addEventListener('change', function() { loadRuleLibrary($('#rlModuleFilter').value, this.value, $('#rlSeverityFilter').value, $('#rlSearch').value, rlStd()); });
$('#rlSeverityFilter').addEventListener('change', function() { loadRuleLibrary($('#rlModuleFilter').value, $('#rlTypeFilter').value, this.value, $('#rlSearch').value, rlStd()); });
$('#rlStandardFilter').addEventListener('change', function() { loadRuleLibrary($('#rlModuleFilter').value, $('#rlTypeFilter').value, $('#rlSeverityFilter').value, $('#rlSearch').value, this.value); });
$('#rlSearch').addEventListener('input', function() { loadRuleLibrary($('#rlModuleFilter').value, $('#rlTypeFilter').value, $('#rlSeverityFilter').value, this.value, rlStd()); });
const rlDrawer = $('#ruleLibraryDetailPanel');
rlDrawer.querySelector('.drawer-close').addEventListener('click', () => rlDrawer.classList.add('hidden'));
rlDrawer.addEventListener('click', e => { if (e.target === rlDrawer) rlDrawer.classList.add('hidden'); });
const ruleEditModal = $('#ruleEditModal');
ruleEditModal.querySelector('.drawer-close').addEventListener('click', () => ruleEditModal.classList.add('hidden'));
ruleEditModal.addEventListener('click', e => { if (e.target === ruleEditModal) ruleEditModal.classList.add('hidden'); });

const versionValidationModal = $('#versionValidationModal');
if (versionValidationModal) {
  const vvb = $('#versionValidationCloseBtn');
  if (vvb) vvb.addEventListener('click', () => versionValidationModal.classList.add('hidden'));
  versionValidationModal.addEventListener('click', e => { if (e.target === versionValidationModal) versionValidationModal.classList.add('hidden'); });
}

// ===== Records =====
function renderRecords() {
  fetch(`/api/jobs/${curJob}/timeline`).then(r => r.json()).then(d => {
    $('#timeline').innerHTML = (d.events||[]).map(e => `<div class="timeline-item${e.stage==='completed'||e.stage==='completed_with_warning'?' tl-active':''}"><span class="tl-time">${fmt(e.time)}</span> <span class="tl-desc">${esc(e.description)}</span></div>`).join('');
  }).catch(()=>{});
  fetch(`/api/jobs/${curJob}/files`).then(r => r.json()).then(d => {
    $('#outputFiles').innerHTML = (d.files||[]).map(f => `<div class="output-file"><div><span class="file-name">${esc(f.name)}</span><br><span class="file-desc">${esc(f.description)}</span></div><span class="file-size">${esc(f.size||'—')}</span>${f.downloadable?` <a href="/api/jobs/${curJob}/download/${encodeURIComponent(f.name)}" download>下载</a>`:''}</div>`).join('');
  }).catch(()=>{});
}

// Report download
$('#downloadReportBtn')?.addEventListener('click', () => {
  if (!curJob) return;
  window.open(`/api/jobs/${curJob}/report/download`, '_blank');
});

// ===== Utils =====
function fmt(v) { return v ? new Date(v).toLocaleString('zh-CN',{hour12:false}) : '—'; }
function esc(v) { return String(v??'').replace(/[&<>"']/g, c => ({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#039;'})[c]); }
function vwu(i) { if (!i||i.value===null||i.value===undefined) return i?.status==='unknown'?'未识别':'需复核'; return i.status==='conflict' ? `${fmtv(i.value)}${i.unit||''}(冲突需复核)` : `${fmtv(i.value)}${i.unit||''}`; }
function fmtv(v) { return v === +v && v === (v|0) ? String(v) : String(v); }
function stTxt(s) { return {PASS:'支持通过',ISSUE:'发现问题',REVIEW:'需复核',NOT_APPLICABLE:'不适用'}[s]||s; }
function actTxt(a) { if (!a) return '未识别'; if (Array.isArray(a.items)) return esc(a.items.join('、')); if (a.value!==undefined&&a.value!==null) return esc(`${a.value}${a.unit||''}`); return esc(a.status||'未识别'); }
function sideTxt(s) { return !s||s.value===null||s.value===undefined ? '<span style="color:var(--text-tertiary)">未识别</span>' : `<b>${esc(fmtv(s.value))}</b>`; }
