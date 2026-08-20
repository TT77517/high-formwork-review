/* ===== 高支模审查系统 — 前端逻辑 ===== */
const $ = (s) => document.querySelector(s);
const $$ = (s) => document.querySelectorAll(s);
const STAGE_NAMES = { waiting:'等待上传',uploaded:'已上传',mineru_parsing:'MinerU解析',document_parsing:'文档解析',completeness_review:'完整性审查',completed:'已完成',completed_with_warning:'已完成(警告)',failed:'失败' };
const STATUS_CN = { PASS:'已识别',MISSING:'疑似缺失',UNCERTAIN:'无法核验' };
const RE_STATUS_CN = { COMPLIANT:'合规',VIOLATED:'违规',UNCERTAIN:'无法判定',NOT_APPLICABLE:'不适用' };
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
let curJob=null, revData=null, compData=null, preData=null, decisions=[], difyErr=null, docMeta=null, pollTimer=null, manIdx=0, selMode='smart', ruleEngineData=null, semanticData=null, calcData=null;

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
    pollTimer = setInterval(poll, 2000);
  } catch(e) { $('#uploadError').textContent = e.message; $('#submitButton').disabled = false; }
});

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
    { tab:'manual', title:'人工复核', value: decisions.filter(d=>d.human_decision!=='pending').length, sub:`共 ${decisions.length} 条`, warn: decisions.filter(d=>d.human_decision==='pending').length>0 }
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
  const q = preData?.project_qualification; if (!q) { $('#qualificationPanel').innerHTML = '<div class="stat-card"><div class="stat-value">未生成</div><div class="stat-title">工程基础信息</div></div>'; return; }
  const p = q.identified_parameters||{}; const h = p.support_height||{}; const sp = p.support_span||{}; const t = p.total_load_design||{}; const l = p.concentrated_line_load_design||{};
  const rows = [['工程类型',q.project_type],['风险属性',q.risk_classification],['支撑体系',q.support_system_label],['支撑高度',vwu(h)],['跨度',vwu(sp)],['总荷载',vwu(t)],['线荷载',vwu(l)],['适用规则包',(q.applicable_rule_packs||[]).join('、')]];
  $('#qualificationPanel').innerHTML = rows.map(([l,v]) => `<div class="stat-card"><div class="stat-title">${esc(l)}</div><div class="stat-value">${esc(v||'未识别')}</div></div>`).join('');
}

// ===== Document =====
function renderDocument() {
  const d = docMeta; if (!d) return;
  const stats = [['引擎',d.engine],['总页数',d.physical_page_count],['章节',d.section_count],['Block',d.block_count],['文本块',d.text_block_count],['表格',d.table_count],['图片',d.image_count],['公式',d.formula_count],['完整页',d.complete_page_count],['部分解析',d.partial_page_count],['不可读',d.unreadable_page_count]];
  $('#documentStats').innerHTML = stats.map(([l,v]) => `<div class="stat-card"><div class="stat-title">${l}</div><div class="stat-value">${v}</div></div>`).join('');
  renderPageTable('all'); renderSections();
  $('#pageFilter').onchange = function() { renderPageTable(this.value); };
}
function renderPageTable(f) {
  const pages = docMeta?.pages||[]; const filtered = pages.filter(p => f==='all'||(f==='unreadable'&&p.parse_status==='unreadable')||(f==='partial'&&p.parse_status==='partial')||(f==='human-review'&&p.requires_human_review));
  $('#pageRows').innerHTML = filtered.map(p => `<tr class="${p.parse_status==='unreadable'?'row-unreadable':p.parse_status==='partial'?'row-partial':''}" data-page="${p.physical_page}">
    <td>${p.physical_page}</td><td>${esc(p.printed_page||'—')}</td><td>${esc(p.page_type)}</td><td>${esc(p.parse_status)}</td>
    <td>${p.text_length}</td><td>${p.image_count}/${p.table_count}/${p.formula_count}</td>
    <td class="${p.requires_human_review?'review-yes':''}">${p.requires_human_review?'需要':'否'}</td></tr>`).join('');
  $$('#pageRows tr').forEach(r => r.addEventListener('click', () => openPageDrawer(+r.dataset.page)));
}
function renderSections() {
  const ss = docMeta?.sections||[];
  $('#sectionList').innerHTML = ss.map(s => `<span class="toc-item" data-page="${s.physical_page_start}">${esc(s.title)} <small>${s.physical_page_start}-${s.physical_page_end}</small></span>`).join('');
  $$('#sectionList .toc-item').forEach(i => i.addEventListener('click', () => openPageDrawer(+i.dataset.page)));
}
async function openPageDrawer(pn) {
  try {
    const r = await fetch(`/api/jobs/${curJob}/document/pages/${pn}`); const p = await r.json(); if (!r.ok) return;
    const blocks = (p.blocks||[]).map(b => `<div class="evidence-block"><div class="meta"><span><b>${esc(b.block_type)}</b></span><span>${esc(b.block_id)}</span></div><blockquote>${esc(b.text||'无文本')}</blockquote>${b.image_path?`<img src="/api/jobs/${curJob}/asset?path=${encodeURIComponent(b.image_path)}">`:''}</div>`).join('');
    $('#drawerTitle').textContent = `第 ${p.physical_page} 页详情`;
    $('#drawerBody').innerHTML = `<div><p>${esc(p.text||'本页无可用文本')}</p></div><h4 style="margin-top:14px">Block列表</h4>${blocks}`;
    $('#pageDetailPanel').classList.remove('hidden');
  } catch(_){}
}
$('#drawerClose').addEventListener('click', () => $('#pageDetailPanel').classList.add('hidden'));
$('#pageDetailPanel').addEventListener('click', e => { if (e.target === $('#pageDetailPanel')) $('#pageDetailPanel').classList.add('hidden'); });

// ===== Rule Engine =====
function renderRuleEngine() {
  const re = ruleEngineData; if (!re) { $('#ruleEngineStats').innerHTML = '<div class="stat-card"><div class="stat-value">—</div><div class="stat-title">规则引擎未运行</div></div>'; return; }
  $('#ruleEngineStats').innerHTML = [
    ['总规则数', re.total_rules], ['合规', re.compliant], ['违规', re.violated], ['无法判定', re.uncertain], ['不适用', re.not_applicable]
  ].map(([l,v]) => `<div class="stat-card${l==='违规'&&v>0?' warn':''}"><div class="stat-title">${l}</div><div class="stat-value">${v}</div></div>`).join('');

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
  const results = (re.results||[]).filter(r => {
    if (modFilter !== 'all' && r.module !== modFilter) return false;
    if (stFilter !== 'all' && r.status !== stFilter) return false;
    return true;
  });
  $('#ruleEngineRows').innerHTML = results.length ? results.map(r => {
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
  $$('#ruleEngineRows .btn-detail').forEach(b => b.addEventListener('click', () => openRuleEngineDrawer(b.dataset.rule)));
}

function openRuleEngineDrawer(rid) {
  const re = ruleEngineData; if (!re) return;
  const rule = (re.results||[]).find(r => r.rule_id === rid); if (!rule) return;
  const th = rule.threshold||{}; const ev = rule.evidence||[];
  const evHtml = ev.length ? ev.map(e => `<div class="evidence-block"><div class="meta"><span><b>页 ${e.page||'—'}</b></span><span>${esc(e.block_id||'')}</span><span>${esc(e.section||'')}</span></div><blockquote>${esc(e.quote||'')}</blockquote></div>`).join('') : '<p style="color:var(--text-tertiary)">无证据</p>';
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
    const difyLbl = c && Object.keys(c).length ? (DIFY_CN[c.dify_result_source]||'未请求') : '未请求';
    const compLbl = c?.comparison_status ? (COMP_CN[c.comparison_status]||'') : '未请求';
    const humanLbl = d && d.human_decision !== 'pending' ? (HUMAN_CN[d.human_decision]||'') : '待复核';
    return `<tr><td><b>${esc(r.rule_id)}</b></td><td>${esc(r.name)}</td>
      <td><span class="status-chip status-${r.status}">${ll}</span></td>
      <td><span class="status-chip status-${dl||'uncertain'}">${esc(difyLbl)}</span></td>
      <td>${esc(compLbl)}</td><td>${esc(humanLbl)}</td>
      <td><button class="btn-small btn-detail" data-rule="${esc(r.rule_id)}">详情</button></td></tr>`;
  }).join('');
  $$('#reviewRows .btn-detail').forEach(b => b.addEventListener('click', () => openReviewDrawer(b.dataset.rule)));
}
function openReviewDrawer(rid) {
  const results = revData?.results||[]; const rule = results.find(r => r.rule_id===rid); if (!rule) return;
  const ev = (rule.evidence||[]).map(e => `<div class="evidence-block"><div class="meta"><span><b>页 ${e.physical_page}</b></span><span>${esc(e.block_type||'')}</span></div><blockquote>${esc(e.quote||e.description||'')}</blockquote></div>`).join('') || '<p style="color:var(--text-tertiary)">无证据</p>';
  $('#reviewDrawerTitle').textContent = `${rule.rule_id} — ${rule.name}`;
  $('#reviewDrawerBody').innerHTML = `<div class="detail-section"><h4>检查要求</h4><p>${esc(rule.reason)}</p><p>结果：<span class="status-chip status-${rule.status}">${STATUS_CN[rule.status]||rule.status}</span></p></div><div class="detail-section"><h4>原文证据</h4>${ev}</div>`;
  $('#reviewDetailPanel').classList.remove('hidden');
}

// ===== Semantic Review (规范语义审查) =====
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
  if (!total) {
    $('#semanticStats').innerHTML = '<div class="stat-card"><div class="stat-value">—</div><div class="stat-title">规范语义审查未运行</div></div>';
    $('#semanticRows').innerHTML = '<tr><td colspan="9" style="text-align:center;color:var(--text-tertiary)">请先上传方案执行审查</td></tr>';
    return;
  }
  $('#semanticStats').innerHTML = [
    ['总规则数', total], ['合规', compliant], ['违规', violated], ['无法判定', uncertain], ['不适用', notApp]
  ].map(([l,v]) => `<div class="stat-card${l==='违规'&&v>0?' warn':''}"><div class="stat-title">${l}</div><div class="stat-value">${v}</div></div>`).join('');
  // Populate module filter from all results
  const mods = [...new Set(allResults.map(r => r.module))].filter(Boolean);
  const sel = $('#semanticModuleFilter');
  if (sel.options.length <= 1) { mods.forEach(m => { const o=document.createElement('option'); o.value=m; o.textContent=MODULE_CN[m]||m; sel.appendChild(o); }); }
  renderSemanticTable('all','all', allResults);
  $('#semanticModuleFilter').onchange = function() { renderSemanticTable(this.value, $('#semanticStatusFilter').value, allResults); };
  $('#semanticStatusFilter').onchange = function() { renderSemanticTable($('#semanticModuleFilter').value, this.value, allResults); };
  const drawer = $('#semanticDetailPanel');
  drawer.querySelector('.drawer-close').addEventListener('click', () => drawer.classList.add('hidden'));
  drawer.addEventListener('click', e => { if (e.target === drawer) drawer.classList.add('hidden'); });
}
function renderSemanticTable(modF, stF, allResults) {
  const results = (allResults||[]).filter(r => (modF==='all'||r.module===modF) && (stF==='all'||r.status===stF));
  $('#semanticRows').innerHTML = results.length ? results.map(r => {
    const th = r.threshold||{}; const thStr = th.value!==undefined ? `${th.operator||''} ${th.value}${th.unit||''}` : '—';
    const valStr = r.actual_value!==null && r.actual_value!==undefined ? `${r.actual_value}${th.unit||''}` : '—';
    const typeTag = r.check_type==='semantic' ? '<span class="tag-blue">语义</span>' : '<span class="tag-default">确定性</span>';
    return `<tr><td><b>${esc(r.rule_id)}</b></td><td>${esc(r.rule_name)} ${typeTag}</td><td><small>${esc(MODULE_CN[r.module]||r.module)}</small></td><td><span class="tag-${r.severity==='A-mandatory'?'orange':'default'}">${esc(SEVERITY_CN[r.severity]||r.severity)}</span></td><td><span class="status-chip status-${r.status}">${RE_STATUS_CN[r.status]||r.status}</span></td><td>${valStr}</td><td>${thStr}</td><td><small>${esc(r.reason||'')}</small></td><td><button class="btn-small btn-detail" data-rule="${esc(r.rule_id)}" data-type="${esc(r.check_type||'')}">详情</button></td></tr>`;
  }).join('') : '<tr><td colspan="9" style="text-align:center;color:var(--text-tertiary)">无符合条件的规则</td></tr>';
  $$('#semanticRows .btn-detail').forEach(b => b.addEventListener('click', () => openSemanticDrawer(b.dataset.rule, b.dataset.type, allResults)));
}
function openSemanticDrawer(rid, rtype, allResults) {
  const rule = (allResults||[]).find(r => r.rule_id===rid); if (!rule) return;
  const th = rule.threshold||{}; const ev = rule.evidence||[];
  const evHtml = ev.length ? ev.map(e => `<div class="evidence-block"><div class="meta"><span><b>页 ${e.page||'—'}</b></span></div><blockquote>${esc(e.quote||'')}</blockquote></div>`).join('') : '<p style="color:var(--text-tertiary)">无证据</p>';
  const sjHtml = rule.semantic_judgment ? `<div class="detail-section"><h4>语义判断指引</h4><p>${esc(rule.semantic_judgment)}</p></div>` : '';
  $('#semanticDrawerTitle').textContent = `${rule.rule_id} — ${rule.rule_name}`;
  $('#semanticDrawerBody').innerHTML = `<div class="detail-section"><h4>审查结果</h4><p><span class="status-chip status-${rule.status}">${RE_STATUS_CN[rule.status]||rule.status}</span></p><p>${esc(rule.reason||'')}</p></div><div class="detail-section"><h4>参数比对</h4><div style="display:grid;grid-template-columns:1fr 1fr;gap:8px"><div><b>实际值</b><br>${rule.actual_value!==null?esc(`${rule.actual_value}${th.unit||''}`):'—'}</div><div><b>阈值要求</b><br>${th.value!==undefined?esc(`${th.operator||''} ${th.value}${th.unit||''}`):'—'}</div></div></div>${sjHtml}<div class="detail-section"><h4>规范依据</h4><p><b>${esc(rule.code_ref?.standard||'')}</b></p><p style="color:var(--text-secondary)">${esc(rule.code_ref?.original_text||'')}</p></div><div class="detail-section"><h4>整改建议</h4><p>${esc(rule.remedy_suggestion||'')}</p></div><div class="detail-section"><h4>典型违规表现</h4><p>${esc(rule.typical_violation||'')}</p></div><div class="detail-section"><h4>证据</h4>${evHtml}</div>`;
  $('#semanticDetailPanel').classList.remove('hidden');
}

// ===== Calculation Review (计算校核) =====
function renderCalculation() {
  const calc = calcData;
  const items = preData?.consistency_review||[];
  const s = preData?.summary||{};
  // Combine calc engine results + consistency results
  const calcResults = calc?.results || [];
  const calcTotal = calc?.total_rules || 0;
  const calcCompliant = calc?.compliant || 0;
  const calcViolated = calc?.violated || 0;
  const calcUncertain = calc?.uncertain || 0;
  const consTotal = s.consistency_total ?? items.length;
  const consPass = s.consistency_pass ?? 0;
  const consIssue = s.consistency_issue ?? 0;

  $('#calcStats').innerHTML = [
    ['验算项', calcTotal], ['验算通过', calcCompliant], ['验算问题', calcViolated], ['无法判定', calcUncertain], ['参数不一致', consIssue]
  ].map(([l,v]) => `<div class="stat-card${l==='验算问题'&&v>0?' warn':''}"><div class="stat-title">${l}</div><div class="stat-value">${v}</div></div>`).join('');

  // Render calculation results table
  const calcRows = calcResults.length ? calcResults.map(r => {
    const ev = r.evidence || [];
    const evSnippet = ev.length ? ev[0].quote : '';
    return `<tr><td><b>${esc(r.rule_id)}</b></td><td>${esc(r.rule_name)}</td><td><span class="status-chip status-${r.status}">${RE_STATUS_CN[r.status]||r.status}</span></td><td><small>${esc(r.formula||'')}</small></td><td><small>${esc(evSnippet).substring(0,80)}</small></td><td>${esc(r.reason||'')}</td></tr>`;
  }).join('') : '<tr><td colspan="6" style="text-align:center;color:var(--text-tertiary)">暂无计算校核结果</td></tr>';

  // Also render consistency items
  const consRows = items.length ? items.map(i => `<tr><td>${esc(i.review_item_id)}</td><td>${esc(i.title)}</td><td><span class="status-chip status-${i.status}">${stTxt(i.status)}</span></td><td>${sideTxt(i.design_side)}</td><td>${sideTxt(i.calculation_side)}</td><td>${esc(i.conclusion||'')}</td></tr>`).join('') : '';

  $('#calcRows').innerHTML = calcRows + (consRows ? `<tr><td colspan="6" style="background:#fafafa;font-weight:600;padding:8px">参数一致性检查</td></tr>` + consRows : '');
}

// ===== Drawing =====
function renderDrawing() {
  const items = preData?.drawing_review||[]; const s = preData?.summary||{};
  $('#drawingStats').innerHTML = [['复核卡片',s.drawing_total??items.length],['需人工复核',s.drawing_review??items.length]].map(([l,v]) => `<div class="stat-card"><div class="stat-title">${l}</div><div class="stat-value">${v}</div></div>`).join('');
  $('#drawingCards').innerHTML = items.length ? items.map(i => `<div class="review-card"><div class="review-card-head"><div><b>${esc(i.review_item_id)} · ${esc(i.title)}</b></div><span class="status-chip status-${i.status}">${stTxt(i.status)}</span></div><p class="review-card-conclusion">${esc(i.conclusion||'')}</p></div>`).join('') : '<p style="color:var(--text-tertiary)">暂无结果</p>';
}

// ===== Manual =====
function renderManual() {
  const results = revData?.results||[]; const db = {}; decisions.forEach(d => db[d.rule_id]=d);
  const showAll = $('#showAllDecisions').checked;
  const items = results.map(r => ({ rule:r, decision: db[r.rule_id]||{human_decision:'pending'}, hasSaved: !!db[r.rule_id] }));
  const filtered = showAll ? items : items.filter(i => {
    const c = compData?.results?.find(c => c.rule_id===i.rule.rule_id);
    return isPriority(c, i.rule) || isQuick(c, i.rule) || (i.hasSaved && i.decision.human_decision==='pending');
  });
  const total = filtered.length; const done = filtered.filter(i => i.decision.human_decision!=='pending').length;
  $('#manualProgress').textContent = `进度：${done}/${total} 已确认`;
  if (!filtered.length) { $('#manualList').innerHTML = '<p style="text-align:center;padding:40px;color:var(--text-tertiary)">所有满足条件的规则均已完成复核。</p>'; return; }
  $('#manualList').innerHTML = filtered.map((item, idx) => {
    const r = item.rule; const d = item.decision; const isDone = d.human_decision !== 'pending';
    return `<div class="manual-item${isDone?' manual-done':''}" data-index="${idx}">
      <div class="manual-head"><b>${esc(r.rule_id)} ${esc(r.name)}</b><span class="status-chip status-${r.status}">${STATUS_CN[r.status]||r.status}</span></div>
      <div class="manual-body"><div class="field"><label>复核决定</label>
        <select data-rule="${esc(r.rule_id)}" class="manual-decision">
          ${['pending','confirmed_pass','confirmed_missing','unable_to_verify','false_positive','need_supplement'].map(v => `<option value="${v}" ${d.human_decision===v?'selected':''}>${HUMAN_CN[v]}</option>`).join('')}
        </select></div>
      <div class="field"><label>备注</label><textarea data-rule="${esc(r.rule_id)}" class="manual-note" maxlength="2000">${esc(d.note||'')}</textarea></div></div>
    </div>`;
  }).join('');
}
$('#showAllDecisions').addEventListener('change', renderManual);
$('#saveDecisions').addEventListener('click', saveAllDecisions);
$('#saveAndNext').addEventListener('click', async () => { await saveAllDecisions(); const results = revData?.results||[]; const db = {}; decisions.forEach(d => db[d.rule_id]=d); const items = results.map(r => ({rule:r,decision:db[r.rule_id]||{human_decision:'pending'}})); const filtered = $('#showAllDecisions').checked ? items : items.filter(i => { const c = compData?.results?.find(c=>c.rule_id===i.rule.rule_id); return isPriority(c,i.rule)||isQuick(c,i.rule); }); const ni = filtered.findIndex(i => i.decision.human_decision==='pending'); if (ni>=0) { manIdx=ni; renderManual(); } else { $('#decisionMessage').textContent='所有项目已完成复核'; } });
async function saveAllDecisions() {
  const sels = $$('#manualList .manual-decision'); const tas = $$('#manualList .manual-note');
  for (let i=0; i<sels.length; i++) { const v=sels[i].value, n=tas[i].value.trim(); if ((v==='confirmed_missing'||v==='false_positive'||v==='need_supplement')&&!n) { alert(`规则 ${sels[i].dataset.rule}：需填写备注`); tas[i].focus(); return; } }
  const decs = []; for (let i=0; i<sels.length; i++) { const rid=sels[i].dataset.rule; const r=revData?.results?.find(r=>r.rule_id===rid); decs.push({rule_id:rid,automatic_status:r?r.status:'UNCERTAIN',human_decision:sels[i].value,human_decision_label:HUMAN_CN[sels[i].value]||sels[i].value,note:tas[i].value.trim()}); }
  $('#saveDecisions').disabled = true;
  try { const r = await fetch(`/api/jobs/${curJob}/decisions`, {method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({decisions:decs})}); const d = await r.json(); if (!r.ok) throw new Error(d.detail||'保存失败'); decisions = d.decisions||[]; $('#decisionMessage').textContent = `✓ 已保存 ${d.saved_count} 条`; renderReviewTable($('#reviewFilter').value); renderManual(); renderOverview(); } catch(e) { $('#decisionMessage').textContent = '保存失败: '+e.message; }
  $('#saveDecisions').disabled = false;
}

// ===== Rule Library Management =====
let ruleLibraryData = null;

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
  // Populate standard filter
  const stds = [...new Set(rules.map(r => { const s=r.code_ref?.standard||''; const m=s.match(/(GB[\d\s]*\d+|JGJ[/T]*\s*\d+|住建部|建办质|建质)/); return m?m[0].replace(/\s/g,''):''; }).filter(Boolean))];
  const stdSel = $('#rlStandardFilter');
  if (stdSel.options.length <= 1) { stds.forEach(s => { const o=document.createElement('option'); o.value=s; o.textContent=s; stdSel.appendChild(o); }); }
  // Render table
  $('#ruleLibraryRows').innerHTML = rules.length ? rules.map(r => {
    const typeLabel = { deterministic:'确定性', semantic:'语义', calculation:'计算' }[r.check_type]||r.check_type;
    const sevClass = r.severity==='A-mandatory'?'orange':'default';
    const sevLabel = SEVERITY_CN[r.severity]||r.severity;
    const stdText = (r.code_ref?.standard||'').substring(0,15);
    const actions = r.status==='active'
      ? `<button class="btn-small btn-detail" onclick="openRuleLibraryDrawer('${esc(r.rule_id)}')">详情</button>`
      : `<button class="btn-small btn-detail" onclick="openRuleLibraryDrawer('${esc(r.rule_id)}')">详情</button>`;
    return `<tr><td><b>${esc(r.rule_id)}</b></td><td>${esc(r.rule_name)}</td><td><small>${esc(MODULE_CN[r.module]||r.module)}</small></td><td>${typeLabel}</td><td><span class="tag-${sevClass}">${sevLabel}</span></td><td><small>${esc(stdText)}</small></td><td>${r.status==='active'?'<span class="tag-green">启用</span>':'<span class="tag-default">停用</span>'}</td><td>${actions}</td></tr>`;
  }).join('') : '<tr><td colspan="8" style="text-align:center;color:var(--text-tertiary)">无符合条件的规则</td></tr>';
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
function isPriority(c, r) { return c?.review_priority==='priority_review' || (!c && (r.status==='MISSING'||r.status==='UNCERTAIN'||r.requires_human_review)); }
function isQuick(c, r) { return c?.review_priority==='quick_confirm' || Boolean(c?.comparison_status==='NOT_REQUESTED'&&r.status==='PASS'&&typeof r.confidence==='number'&&r.confidence>=0.8&&!r.requires_human_review&&!r.needs_semantic_review); }
function fmt(v) { return v ? new Date(v).toLocaleString('zh-CN',{hour12:false}) : '—'; }
function esc(v) { return String(v??'').replace(/[&<>"']/g, c => ({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#039;'})[c]); }
function vwu(i) { return !i||i.value===null||i.value===undefined ? (i?.status==='unknown'?'未识别':'需复核') : `${fmtv(i.value)}${i.unit||''}`; }
function fmtv(v) { return v === +v && v === (v|0) ? String(v) : String(v); }
function stTxt(s) { return {PASS:'支持通过',ISSUE:'发现问题',REVIEW:'需复核',NOT_APPLICABLE:'不适用'}[s]||s; }
function actTxt(a) { if (!a) return '未识别'; if (Array.isArray(a.items)) return esc(a.items.join('、')); if (a.value!==undefined&&a.value!==null) return esc(`${a.value}${a.unit||''}`); return esc(a.status||'未识别'); }
function sideTxt(s) { return !s||s.value===null||s.value===undefined ? '<span style="color:var(--text-tertiary)">未识别</span>' : `<b>${esc(fmtv(s.value))}</b>`; }
