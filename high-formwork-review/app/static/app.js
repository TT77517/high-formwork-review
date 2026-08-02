/* ===== 高支模方案审查工作台 — 前端逻辑 ===== */
const $ = (s) => document.querySelector(s);
const $$ = (s) => document.querySelectorAll(s);

// ---- 常量 ----
const STAGE_NAMES = {
  waiting: '等待上传', uploaded: '已上传', mineru_parsing: 'MinerU 解析',
  document_parsing: '文档解析', completeness_review: '完整性审查',
  completed: '已完成', completed_with_warning: '已完成(有警告)', failed: '失败'
};
const STATUS_CN = { PASS: '已识别', MISSING: '疑似缺失', UNCERTAIN: '无法核验' };
const COMPARISON_STATUS_CN = {
  AGREEMENT: '一致',
  DISAGREEMENT: '不一致',
  NOT_REQUESTED: '未请求',
  DIFY_FAILED: '暂未完成',
  BOTH_UNCERTAIN: '均不确定'
};
const DIFY_SOURCE_CN = {
  not_requested: '增强复核：未请求',
  failed: '增强复核：暂未完成',
  cache: '增强复核：缓存结果',
  api: '增强复核：实时结果'
};
const HUMAN_DECISION_CN = {
  pending: '待复核', confirmed_pass: '确认已具备', confirmed_missing: '确认存在缺项',
  unable_to_verify: '暂无法核验', false_positive: '排除误报', need_supplement: '要求补充资料'
};

function comparisonStatus(comp) {
  return comp?.comparison_status || null;
}

function difyDisplayLabel(comp, hasComparison = true) {
  if (!hasComparison || !comp) return '增强复核：未请求';
  const source = comp.dify_result_source || (
    comparisonStatus(comp) === 'DIFY_FAILED' ? 'failed' : 'not_requested'
  );
  const sourceLabel = DIFY_SOURCE_CN[source] || DIFY_SOURCE_CN.not_requested;
  if (source === 'cache' || source === 'api') {
    const statusLabel = STATUS_CN[comp.dify_status] || '已返回';
    return `${sourceLabel} · ${statusLabel}`;
  }
  return sourceLabel;
}

function comparisonDisplayLabel(comp) {
  if (!comp) return '未请求';
  return COMPARISON_STATUS_CN[comparisonStatus(comp)] || '未请求';
}

function isPriorityReview(comp, rule) {
  if (comp?.review_priority === 'priority_review') return true;
  return !comp && (rule.status === 'MISSING' || rule.status === 'UNCERTAIN' || rule.requires_human_review);
}

function isQuickConfirm(comp, rule) {
  if (comp?.review_priority === 'quick_confirm') return true;
  return Boolean(
    comp?.comparison_status === 'NOT_REQUESTED' &&
    rule.status === 'PASS' &&
    typeof rule.confidence === 'number' &&
    rule.confidence >= 0.8 &&
    !rule.requires_human_review &&
    !rule.needs_semantic_review
  );
}

let currentJobId = null;
let reviewData = null;
let comparisonData = null;
let decisionsData = [];
let difyErrorData = null;
let documentMeta = null;
let pollTimer = null;
let currentManualIndex = 0;

// ---- 初始化 ----
$('#pdfFile').addEventListener('change', (e) => {
  $('#fileLabel').textContent = e.target.files[0]?.name || '选择不超过 50MB 的 PDF 文件';
});

$('#uploadForm').addEventListener('submit', async (e) => {
  e.preventDefault();
  const file = $('#pdfFile').files[0];
  if (!file) return;
  $('#uploadError').textContent = '';
  $('#submitButton').disabled = true;
  const form = new FormData();
  form.append('file', file);
  try {
    const res = await fetch('/api/jobs', { method: 'POST', body: form });
    const data = await res.json();
    if (!res.ok) throw new Error(data.detail || '上传失败');
    currentJobId = data.job_id;
    renderStatus(data);
    pollTimer = setInterval(pollStatus, 2000);
  } catch (err) {
    $('#uploadError').textContent = err.message;
    $('#submitButton').disabled = false;
  }
});

async function pollStatus() {
  try {
    const res = await fetch(`/api/jobs/${currentJobId}/status`);
    const data = await res.json();
    if (!res.ok) throw new Error(data.detail || '状态读取失败');
    renderStatus(data);
    const done = data.status === 'completed' || data.status === 'completed_with_warning';
    if (done) {
      clearInterval(pollTimer);
      await loadAllResults();
      $('#submitButton').disabled = false;
    } else if (data.status === 'failed') {
      clearInterval(pollTimer);
      $('#submitButton').disabled = false;
    }
  } catch (err) {
    clearInterval(pollTimer);
    $('#uploadError').textContent = err.message;
    $('#submitButton').disabled = false;
  }
}

function renderStatus(data) {
  $('#taskFile').textContent = data.file_name || '—';
  $('#taskTime').textContent = formatTime(data.uploaded_at);
  $('#taskId').textContent = data.job_id || '—';
  $('#taskStage').textContent = `${data.stage} · ${STAGE_NAMES[data.stage] || data.stage}`;
  $('#progressBar').style.width = `${data.progress || 0}%`;
  $('#taskMessage').textContent = data.message || '';
  const badge = $('#statusBadge');
  const st = data.status;
  badge.textContent = STAGE_NAMES[st] || st;
  badge.className = `badge ${st === 'failed' ? 'failed' : st === 'completed' || st === 'completed_with_warning' ? 'completed' : 'running'}`;
  $('#jobIdBadge').textContent = (data.job_id || '—').slice(0, 8) + '…';
  if (data.status === 'completed' || data.status === 'completed_with_warning') {
    $('#uploadStage').textContent = '审查完成';
    $('#uploadStage').style.color = 'var(--green)';
  }
  if (data.error_stage) $('#uploadError').textContent = `失败阶段：${data.error_stage}。${data.message}`;
}

// ---- 标签页切换 ----
$$('#navTabs .nav-tab').forEach(btn => {
  btn.addEventListener('click', () => switchTab(btn.dataset.tab));
});

function switchTab(name) {
  $$('#navTabs .nav-tab').forEach(b => b.classList.remove('active'));
  $(`#navTabs .nav-tab[data-tab="${name}"]`).classList.add('active');
  $$('.tab-panel').forEach(p => p.classList.add('hidden'));
  const panel = $(`#tab-${name}`);
  if (panel) panel.classList.remove('hidden');
}

// ---- 加载全部结果 ----
async function loadAllResults() {
  try {
    const [docRes, reviewRes] = await Promise.all([
      fetch(`/api/jobs/${currentJobId}/document`),
      fetch(`/api/jobs/${currentJobId}/review`)
    ]);
    const docData = await docRes.json();
    reviewData = await reviewRes.json();
    if (!docRes.ok || !reviewRes.ok) throw new Error('结果加载失败');

    documentMeta = docData;
    decisionsData = reviewData.decisions || [];

    // 尝试加载对比数据
    try {
      const compRes = await fetch(`/api/jobs/${currentJobId}/comparison`);
      if (compRes.ok) comparisonData = await compRes.json();
    } catch (_) { comparisonData = null; }

    // 尝试加载 Dify 错误
    try {
      const errRes = await fetch(`/api/jobs/${currentJobId}/dify-error`);
      if (errRes.ok) difyErrorData = await errRes.json();
    } catch (_) { difyErrorData = null; }

    renderOverview();
    renderDocument();
    renderReview();
    renderManualReview();
    renderRecords();
  } catch (err) {
    console.error('加载结果失败:', err);
  }
}

// ========== Tab 1: 任务概览 ==========
function renderOverview() {
  const summary = reviewData?.summary || {};
  const compSummary = comparisonData || {};
  const decisions = decisionsData;
  const diffCount = comparisonData ? comparisonData.disagreement_count : 0;
  const comparisonById = {};
  (comparisonData?.results || []).forEach(item => { comparisonById[item.rule_id] = item; });
  const priorityNeeded = (reviewData?.results || []).filter(rule => {
    const comp = comparisonById[rule.rule_id];
    const decision = decisions.find(item => item.rule_id === rule.rule_id);
    return isPriorityReview(comp, rule) &&
      (!decision || decision.human_decision === 'pending');
  }).length;
  const quickConfirmNeeded = (reviewData?.results || []).filter(rule => {
    const comp = comparisonById[rule.rule_id];
    const decision = decisions.find(item => item.rule_id === rule.rule_id);
    return isQuickConfirm(comp, rule) && (!decision || decision.human_decision === 'pending');
  }).length;
  const manualNeeded = priorityNeeded;
  const difyUnavailable = !comparisonData && !difyErrorData;
  const difyRequested = (comparisonData?.results || []).filter(item => item.requested_to_dify).length;
  const difyFailed = compSummary.dify_failed_count || 0;
  const difyNotRequested = compSummary.not_requested_count || 0;

  const cards = [
    { icon: '📄', title: '文档解析', value: documentMeta?.physical_page_count || '—', sub: `页 · ${documentMeta?.section_count || 0} 章节 · ${documentMeta?.block_count || 0} block` },
    { icon: '🔍', title: '本地预审', value: summary.total_rules || 10, sub: `已识别 ${summary.pass_count || 0} · 疑似缺失 ${summary.missing_count || 0} · 无法核验 ${summary.uncertain_count || 0}` },
    { icon: '🤖', title: 'Dify 审查', value: comparisonData ? compSummary.total_rules : '未启用', sub: difyErrorData ? 'Dify 调用失败，使用本地结果' : (comparisonData ? `一致 ${compSummary.agreement_count} · 不一致 ${compSummary.disagreement_count}` : '未配置 Dify 集成'), warn: !!difyErrorData || difyUnavailable },
    { icon: '✅', title: '待人工复核', value: manualNeeded || decisions.length || '—', sub: `${quickConfirmNeeded ? `快速确认 ${quickConfirmNeeded} 条 · ` : ''}已保存 ${decisions.filter(d => d.human_decision !== 'pending').length} 条复核记录`, warn: manualNeeded > 0 }
  ];

  if (comparisonData) {
    cards[2].value = difyRequested;
    if (difyErrorData) {
      cards[2].sub = `Dify 调用失败，使用本地结果 · 失败 ${difyFailed} · 未请求 ${difyNotRequested}`;
    }
  }

  if (difyUnavailable && !difyErrorData) {
    cards[2].sub = 'Dify 未启用，仅展示本地审查结果';
  }

  $('#overviewCards').innerHTML = cards.map(c =>
    `<div class="overview-card${c.warn ? ' card-warn' : ''}">
      <div class="card-icon">${c.icon}</div>
      <div class="card-title">${c.title}</div>
      <div class="card-value">${c.value}</div>
      <div class="card-sub">${c.sub}</div>
    </div>`).join('');

  // 优先处理事项
  const priorities = [];
  if (difyErrorData) priorities.push('Dify 审查调用失败，请检查 Dify 服务配置和网络连接');
  if (difyUnavailable && !difyErrorData) priorities.push('Dify 审查未启用，当前仅展示本地预审结果');
  if (summary.missing_count > 0) priorities.push(`${summary.missing_count} 条规则疑似存在缺项，请在"完整性检查"中逐项核实`);
  if (summary.uncertain_count > 0) priorities.push(`${summary.uncertain_count} 条规则无法自动核验，需要人工判断`);
  if (diffCount > 0) priorities.push(`${diffCount} 条规则本地与 Dify 结果不一致，请在"完整性检查"中对比确认`);
  if (manualNeeded === 0 && decisions.length > 0) priorities.push('所有规则已完成人工复核');
  if (!priorities.length) priorities.push('暂无明显待处理事项');

  const priorityBox = $('#priorityItems');
  priorityBox.classList.remove('hidden');
  $('#priorityList').innerHTML = priorities.map(p => `<li>${p}</li>`).join('');
}

// ========== Tab 2: 文档解析 ==========
function renderDocument() {
  const d = documentMeta;
  if (!d) return;

  const stats = [
    ['解析引擎', d.engine], ['总页数', d.physical_page_count],
    ['有效章节', d.section_count], ['Block 总数', d.block_count],
    ['文本块', d.text_block_count], ['表格', d.table_count],
    ['图片', d.image_count], ['公式', d.formula_count],
    ['完整页', d.complete_page_count], ['部分解析', d.partial_page_count],
    ['不可读', d.unreadable_page_count], ['需复核页', d.human_review_page_count]
  ];
  $('#documentStats').innerHTML = stats.map(([l, v]) =>
    `<div class="stat"><strong>${esc(v)}</strong><small>${esc(l)}</small></div>`).join('');

  // 技术统计（折叠）
  $('#techStatsContent').innerHTML = [
    { label: 'Text Block', value: d.text_block_count },
    { label: 'Table', value: d.table_count },
    { label: 'Image/Chart', value: d.image_count },
    { label: 'Formula', value: d.formula_count },
    { label: 'Complete Pages', value: d.complete_page_count },
    { label: 'Partial Pages', value: d.partial_page_count },
    { label: 'Unreadable Pages', value: d.unreadable_page_count },
  ].map(item => `<div class="fold-item"><strong>${item.value}</strong><small>${item.label}</small></div>`).join('');

  renderPageTable('all');
  renderSections();

  $('#pageFilter').onchange = function() { renderPageTable(this.value); };
}

function renderPageTable(filter) {
  const pages = documentMeta?.pages || [];
  const filtered = pages.filter(p => {
    if (filter === 'unreadable') return p.parse_status === 'unreadable';
    if (filter === 'partial') return p.parse_status === 'partial';
    if (filter === 'human-review') return p.requires_human_review;
    return true;
  });
  const rowClass = (p) => {
    if (p.parse_status === 'unreadable') return 'row-unreadable';
    if (p.parse_status === 'partial') return 'row-partial';
    return '';
  };
  $('#pageRows').innerHTML = filtered.map(p => `<tr class="${rowClass(p)}" data-page="${p.physical_page}">
    <td>${p.physical_page}</td><td>${esc(p.printed_page || '—')}</td>
    <td>${esc(p.page_type)}</td><td>${esc(p.parse_status)}</td>
    <td>${p.text_length}</td><td>${p.image_count}/${p.table_count}/${p.formula_count}</td>
    <td class="${p.requires_human_review ? 'review-yes' : ''}">${p.requires_human_review ? '需要' : '否'}</td>
  </tr>`).join('');
  $$('#pageRows tr').forEach(row => {
    row.addEventListener('click', () => openPageDrawer(Number(row.dataset.page)));
  });
}

function renderSections() {
  const sections = documentMeta?.sections || [];
  $('#sectionList').innerHTML = sections.map(s =>
    `<span class="toc-item level-${s.level}" data-page="${s.physical_page_start}">
      ${esc(s.title)} <small>${s.physical_page_start}-${s.physical_page_end}</small>
    </span>`).join('');
  $$('#sectionList .toc-item').forEach(item => {
    item.addEventListener('click', () => {
      const page = Number(item.dataset.page);
      openPageDrawer(page);
      // 高亮并滚动到对应页面行
      $$('#pageRows tr').forEach(r => r.classList.remove('page-highlight'));
      const row = $(`#pageRows tr[data-page="${page}"]`);
      if (row) { row.classList.add('page-highlight'); row.scrollIntoView({ behavior: 'smooth', block: 'center' }); }
    });
  });
}

async function openPageDrawer(pageNumber) {
  try {
    const res = await fetch(`/api/jobs/${currentJobId}/document/pages/${pageNumber}`);
    const page = await res.json();
    if (!res.ok) return;
    const warnings = page.warnings?.length
      ? `<p class="review-yes">⚠ 解析警告：${esc(page.warnings.join('；'))}</p>` : '';
    const blocks = (page.blocks || []).map(b => {
      const img = b.image_path
        ? `<img src="/api/jobs/${currentJobId}/asset?path=${encodeURIComponent(b.image_path)}" alt="解析图片">` : '';
      const tbl = b.table_html
        ? `<details><summary>查看 table_html</summary><div class="table-html">${b.table_html}</div></details>` : '';
      return `<div class="evidence-block"><div class="meta">
        <span><b>${esc(b.block_type)}</b></span>
        <span>${esc(b.block_id)}</span>
        <span>source: ${esc(b.source_pointer || '—')}</span>
      </div>
      <blockquote>${esc(b.text || '无文本')}</blockquote>
      <small>bbox: ${esc(JSON.stringify(b.bbox || null))}</small>${img}${tbl}</div>`;
    }).join('');

    $('#drawerTitle').textContent = `第 ${page.physical_page} 页详情`;
    $('#drawerBody').innerHTML = `${warnings}
      <div class="page-text">${esc(page.text || '本页无可用文本')}</div>
      <h4 style="margin-top:14px">Block 列表</h4>${blocks}`;
    $('#pageDetailPanel').classList.remove('hidden');
  } catch (_) {}
}

$('#drawerClose').addEventListener('click', () => {
  $('#pageDetailPanel').classList.add('hidden');
});
$('#pageDetailPanel').addEventListener('click', (e) => {
  if (e.target === $('#pageDetailPanel')) $('#pageDetailPanel').classList.add('hidden');
});

// ========== Tab 3: 完整性检查 ==========
function renderReview() {
  const results = reviewData?.results || [];
  const decisionsById = {};
  decisionsData.forEach(d => { decisionsById[d.rule_id] = d; });

  // Dify 警告
  if (difyErrorData) {
    $('#difyWarning').textContent = `⚠ Dify 审查失败：${difyErrorData.message || '未知错误'}，仅展示本地结果`;
    $('#difyWarning').classList.remove('hidden');
  } else if (!comparisonData) {
    $('#difyWarning').textContent = 'ℹ Dify 审查未启用，仅展示本地预审结果';
    $('#difyWarning').classList.remove('hidden');
  } else {
    $('#difyWarning').classList.add('hidden');
  }

  renderReviewTable('all');

  $('#reviewFilter').onchange = function() { renderReviewTable(this.value); };

  // 抽屉关闭事件
  const reviewDrawer = $('#reviewDetailPanel');
  reviewDrawer.querySelector('.drawer-close').addEventListener('click', () => {
    reviewDrawer.classList.add('hidden');
  });
  reviewDrawer.addEventListener('click', (e) => {
    if (e.target === reviewDrawer) reviewDrawer.classList.add('hidden');
  });
}

function renderReviewTable(filter) {
  const results = reviewData?.results || [];
  const compById = {};
  if (comparisonData?.results) {
    comparisonData.results.forEach(r => { compById[r.rule_id] = r; });
  }
  const decisionsById = {};
  decisionsData.forEach(d => { decisionsById[d.rule_id] = d; });

  const filtered = results.filter(r => {
    const comp = compById[r.rule_id] || {};
    const dec = decisionsById[r.rule_id];
    const needsReview = (comp.manual_review) || r.status === 'MISSING' || r.status === 'UNCERTAIN' || r.requires_human_review || (dec && dec.human_decision === 'pending');
    if (filter === 'manual-review') return needsReview;
    if (filter === 'disagree') return comp?.comparison_status === 'DISAGREEMENT';
    if (filter === 'MISSING') return r.status === 'MISSING';
    if (filter === 'UNCERTAIN') return r.status === 'UNCERTAIN';
    return true;
  });

  $('#reviewRows').innerHTML = filtered.map(r => {
    const comp = compById[r.rule_id] || {};
    const dec = decisionsById[r.rule_id];
    const localLabel = STATUS_CN[r.status] || r.status;
    const difyStatus = comp.dify_status;
    const difyLabel = difyDisplayLabel(comp, Boolean(comparisonData));
    const comparisonLabel = comparisonDisplayLabel(comp);
    const comparisonClass = comp.comparison_status === 'AGREEMENT' || comp.comparison_status === 'BOTH_UNCERTAIN'
      ? 'agreement-consistent'
      : comp.comparison_status === 'DISAGREEMENT' ? 'agreement-inconsistent' : '';
    const humanLabel = dec && dec.human_decision !== 'pending'
      ? HUMAN_DECISION_CN[dec.human_decision] || dec.human_decision
      : comp.review_priority === 'quick_confirm' ? '快速确认' : '待复核';
    const humanClass = dec && dec.human_decision !== 'pending'
      ? 'human-confirmed'
      : comp.review_priority === 'quick_confirm' ? 'review-priority' : 'review-yes';

    return `<tr>
      <td><b>${esc(r.rule_id)}</b></td>
      <td>${esc(r.name)}</td>
      <td><span class="status-chip status-${r.status}">${localLabel}</span></td>
      <td><span class="status-chip status-${difyStatus || 'uncertain'}">${esc(difyLabel)}</span></td>
      <td class="${comparisonClass}">${comparisonLabel}</td>
      <td class="${humanClass}">${humanLabel}</td>
      <td><button class="btn-small btn-detail" data-rule="${esc(r.rule_id)}">详情</button></td>
    </tr>`;
  }).join('');

  $$('#reviewRows .btn-detail').forEach(btn => {
    btn.addEventListener('click', () => openReviewDrawer(btn.dataset.rule));
  });
}

function openReviewDrawer(ruleId) {
  const results = reviewData?.results || [];
  const rule = results.find(r => r.rule_id === ruleId);
  if (!rule) return;

  const compById = {};
  if (comparisonData?.results) {
    comparisonData.results.forEach(r => { compById[r.rule_id] = r; });
  }
  const comp = compById[ruleId] || {};

  const decisionsById = {};
  decisionsData.forEach(d => { decisionsById[d.rule_id] = d; });
  const saved = decisionsById[ruleId] || {};

  const localLabel = STATUS_CN[rule.status] || rule.status;
  const difyStatus = comp.dify_status;
  const difyLabel = difyDisplayLabel(comp, Boolean(comparisonData));
  const diffReason = comp.difference_reason || (comparisonData ? comparisonDisplayLabel(comp) : 'Dify 未启用');

  // 证据列表
  const evidenceHtml = (rule.evidence || []).length === 0
    ? '<p style="color:var(--muted)">无直接证据（MISSING 不制造页码或证据）</p>'
    : (rule.evidence || []).map(ev => {
        const img = ev.image_path
          ? `<img src="/api/jobs/${currentJobId}/asset?path=${encodeURIComponent(ev.image_path)}" alt="证据图片">` : '';
        const tbl = ev.table_html
          ? `<details><summary>查看 table_html</summary><div class="table-html">${ev.table_html}</div></details>` : '';
        return `<div class="evidence-block">
          <div class="meta">
            <span><b>物理页 ${ev.physical_page}</b></span>
            <span>印刷页 ${esc(ev.printed_page || '—')}</span>
            <span>${esc(ev.block_type)}</span>
            <span>章节: ${esc((ev.section_path || []).join(' / ') || '无')}</span>
          </div>
          <blockquote>${esc(ev.quote || ev.description || '无文字证据')}</blockquote>
          <small>来源: ${esc(ev.source_pointer || '—')} · bbox: ${esc(JSON.stringify(ev.bbox || null))} · 目录页: ${ev.whether_from_toc ? '是' : '否'}</small>
          ${img}${tbl}
        </div>`;
      }).join('');

  // 匹配信息
  const matchedSections = (rule.matched_sections || []).map(s =>
    `${esc(s.title)}（${s.physical_page_start}-${s.physical_page_end}页）`).join('<br>') || '无';
  const matchedTerms = (rule.matched_terms || []).join('、') || '无';
  const matchedSubitems = (rule.matched_subitems || []).map(s =>
    `${s.satisfied ? '✓' : '○'} ${esc(s.name)}：${esc((s.matched_terms || []).join('、') || '无')}`).join('<br>') || '无';
  const pages = (rule.physical_pages || []).join('、') || '无';

  $('#reviewDrawerTitle').textContent = `${rule.rule_id} — ${rule.name}`;
  $('#reviewDrawerBody').innerHTML = `
    <div class="detail-section">
      <h4>检查要求</h4>
      <p>${esc(rule.reason)}</p>
      <p>判断结果：<span class="status-chip status-${rule.status}">${localLabel}</span>
      ${rule.requires_human_review ? ' <span class="review-yes">需人工复核</span>' : ''}</p>
    </div>
    <div class="detail-section">
      <h4>本地预审结果</h4>
      <p>状态：<span class="status-chip status-${rule.status}">${localLabel}</span></p>
      <p>原因：${esc(rule.reason)}</p>
    </div>
    <div class="detail-section">
      <h4>Dify 审查结果</h4>
      <p>状态：<span class="status-chip status-${difyStatus || 'uncertain'}">${difyLabel}</span></p>
      <p>对比：${esc(diffReason)}</p>
    </div>
    <div class="detail-section">
      <h4>对比原因</h4>
      <p>${esc(diffReason)}</p>
    </div>
    <div class="detail-section">
      <h4>匹配信息</h4>
      <div style="display:grid;grid-template-columns:1fr 1fr;gap:8px">
        <div><b>命中章节</b><br>${matchedSections}</div>
        <div><b>命中术语</b><br>${matchedTerms}</div>
        <div><b>命中子项</b><br>${matchedSubitems}</div>
        <div><b>证据页码</b><br>${pages}</div>
      </div>
    </div>
    <div class="detail-section">
      <h4>原文证据</h4>
      ${evidenceHtml}
    </div>
    <div class="detail-section">
      <h4>人工复核</h4>
      <div class="manual-body">
        <div class="field">
          <label>复核决定</label>
          <select data-rule="${esc(ruleId)}" class="drawer-decision">
            <option value="pending" ${saved.human_decision === 'pending' || !saved.human_decision ? 'selected' : ''}>待复核</option>
            <option value="confirmed_pass" ${saved.human_decision === 'confirmed_pass' ? 'selected' : ''}>确认已具备</option>
            <option value="confirmed_missing" ${saved.human_decision === 'confirmed_missing' ? 'selected' : ''}>确认存在缺项</option>
            <option value="unable_to_verify" ${saved.human_decision === 'unable_to_verify' ? 'selected' : ''}>暂无法核验</option>
            <option value="false_positive" ${saved.human_decision === 'false_positive' ? 'selected' : ''}>排除误报</option>
            <option value="need_supplement" ${saved.human_decision === 'need_supplement' ? 'selected' : ''}>要求补充资料</option>
          </select>
        </div>
        <div class="field full-width">
          <label>复核备注</label>
          <textarea data-rule="${esc(ruleId)}" class="drawer-note" maxlength="2000" placeholder="调整结果或排除误报时必须填写备注">${esc(saved.note || '')}</textarea>
        </div>
        <div class="field full-width">
          <button class="btn-small" style="background:var(--blue);color:#fff;padding:6px 14px" id="drawerSaveBtn">保存此条</button>
        </div>
      </div>
    </div>`;

  $('#drawerSaveBtn').addEventListener('click', () => saveSingleDecision(ruleId));
  $('#reviewDetailPanel').classList.remove('hidden');
}

async function saveSingleDecision(ruleId) {
  const select = $(`#reviewDetailPanel select[data-rule="${ruleId}"]`);
  const textarea = $(`#reviewDetailPanel textarea[data-rule="${ruleId}"]`);
  const decision = select.value;
  const note = textarea.value.trim();

  if ((decision === 'confirmed_missing' || decision === 'false_positive' || decision === 'need_supplement') && !note) {
    alert('调整结果或排除误报时必须填写复核备注');
    return;
  }

  const result = reviewData?.results?.find(r => r.rule_id === ruleId);
  const payload = {
    decisions: [{
      rule_id: ruleId,
      automatic_status: result ? result.status : 'UNCERTAIN',
      human_decision: decision,
      human_decision_label: HUMAN_DECISION_CN[decision] || decision,
      note: note
    }]
  };

  try {
    const res = await fetch(`/api/jobs/${currentJobId}/decisions`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(payload)
    });
    const data = await res.json();
    if (!res.ok) throw new Error(data.detail || '保存失败');
    decisionsData = data.decisions || [];
    renderReviewTable($('#reviewFilter').value);
    renderManualReview();
    renderOverview();
  } catch (err) {
    alert('保存失败: ' + err.message);
  }
}

// ========== Tab 4: 人工复核 ==========
function renderManualReview() {
  const results = reviewData?.results || [];
  const decisionsById = {};
  decisionsData.forEach(d => { decisionsById[d.rule_id] = d; });

  const showAll = $('#showAllDecisions').checked;

  const items = results.map(r => {
    const dec = decisionsById[r.rule_id];
    return {
      rule: r,
      decision: dec || { human_decision: 'pending', note: '' },
      hasSavedDecision: Boolean(dec)
    };
  });

  const filtered = showAll ? items : items.filter(item => {
    const comp = comparisonData?.results?.find(c => c.rule_id === item.rule.rule_id);
    return isPriorityReview(comp, item.rule) ||
      isQuickConfirm(comp, item.rule) ||
      (item.hasSavedDecision && item.decision.human_decision === 'pending');
  });

  const total = filtered.length;
  const done = filtered.filter(item => item.decision.human_decision !== 'pending').length;
  $('#manualProgress').textContent = `进度：${done}/${total} 已确认`;

  if (filtered.length === 0) {
    $('#manualList').innerHTML = '<p style="color:var(--muted);text-align:center;padding:40px">所有满足条件的规则均已完成复核。</p>';
    return;
  }

  $('#manualList').innerHTML = filtered.map((item, idx) => {
    const r = item.rule;
    const d = item.decision;
    const isDone = d.human_decision !== 'pending';
    const localLabel = STATUS_CN[r.status] || r.status;
    const comp = comparisonData?.results?.find(c => c.rule_id === r.rule_id);
    const difyLabel = difyDisplayLabel(comp, Boolean(comparisonData));
    const agreeLabel = comp ? comparisonDisplayLabel(comp) : '未请求';
    const priorityLabel = isPriorityReview(comp, r) ? '优先复核' : isQuickConfirm(comp, r) ? '快速确认' : '';
    const comparisonClass = comp?.comparison_status === 'AGREEMENT' || comp?.comparison_status === 'BOTH_UNCERTAIN'
      ? 'agreement-consistent'
      : comp?.comparison_status === 'DISAGREEMENT' ? 'agreement-inconsistent' : '';

    return `<div class="manual-item${isDone ? ' manual-done' : ''}" data-index="${idx}">
      <div class="manual-head">
        <span class="rule-label">${esc(r.rule_id)} ${esc(r.name)}</span>
        <span class="status-chip status-${r.status}">本地: ${localLabel}</span>
        ${comp ? `<span class="status-chip status-${comp.dify_status || 'uncertain'}">${esc(difyLabel)}</span>` : '<span class="status-chip status-uncertain">增强复核：未请求</span>'}
        ${comp ? `<span class="${comparisonClass}">${agreeLabel}</span>` : ''}
        ${priorityLabel ? `<span class="review-priority">${priorityLabel}</span>` : ''}
        ${isDone ? `<span class="human-confirmed">${HUMAN_DECISION_CN[d.human_decision] || d.human_decision}</span>` : '<span class="review-yes">待复核</span>'}
      </div>
      <div class="manual-body">
        <div class="field">
          <label>复核决定</label>
          <select data-rule="${esc(r.rule_id)}" class="manual-decision">
            <option value="pending" ${d.human_decision === 'pending' ? 'selected' : ''}>待复核</option>
            <option value="confirmed_pass" ${d.human_decision === 'confirmed_pass' ? 'selected' : ''}>确认已具备</option>
            <option value="confirmed_missing" ${d.human_decision === 'confirmed_missing' ? 'selected' : ''}>确认存在缺项</option>
            <option value="unable_to_verify" ${d.human_decision === 'unable_to_verify' ? 'selected' : ''}>暂无法核验</option>
            <option value="false_positive" ${d.human_decision === 'false_positive' ? 'selected' : ''}>排除误报</option>
            <option value="need_supplement" ${d.human_decision === 'need_supplement' ? 'selected' : ''}>要求补充资料</option>
          </select>
        </div>
        <div class="field">
          <label>复核备注${d.human_decision !== 'pending' && !d.note && (d.human_decision === 'confirmed_missing' || d.human_decision === 'false_positive') ? ' <span class="review-yes">*必填</span>' : ''}</label>
          <textarea data-rule="${esc(r.rule_id)}" class="manual-note" maxlength="2000" placeholder="填写复核依据或备注">${esc(d.note || '')}</textarea>
        </div>
      </div>
    </div>`;
  }).join('');

  // 滚动到当前项
  setTimeout(() => {
    const target = $(`.manual-item[data-index="${currentManualIndex}"]`);
    if (target) target.scrollIntoView({ behavior: 'smooth', block: 'center' });
  }, 100);
}

$('#showAllDecisions').addEventListener('change', () => {
  renderManualReview();
});

$('#saveDecisions').addEventListener('click', saveAllDecisions);

$('#saveAndNext').addEventListener('click', async () => {
  await saveAllDecisions();
  // 找到第一个待复核项
  const results = reviewData?.results || [];
  const decisionsById = {};
  decisionsData.forEach(d => { decisionsById[d.rule_id] = d; });
  const showAll = $('#showAllDecisions').checked;
  const items = results.map(r => ({
    rule: r,
    decision: decisionsById[r.rule_id] || { human_decision: 'pending' },
    hasSavedDecision: Boolean(decisionsById[r.rule_id])
  }));
  const filtered = showAll ? items : items.filter(item => {
    const comp = comparisonData?.results?.find(c => c.rule_id === item.rule.rule_id);
    return isPriorityReview(comp, item.rule) ||
      isQuickConfirm(comp, item.rule) ||
      (item.hasSavedDecision && item.decision.human_decision === 'pending');
  });
  const nextIdx = filtered.findIndex(item => item.decision.human_decision === 'pending');
  if (nextIdx >= 0) {
    currentManualIndex = nextIdx;
    renderManualReview();
  } else {
    $('#decisionMessage').textContent = '所有项目已完成复核';
 }
});

async function saveAllDecisions() {
  const selects = $$('#manualList .manual-decision');
  const textareas = $$('#manualList .manual-note');

  // 验证必填
  for (let i = 0; i < selects.length; i++) {
    const val = selects[i].value;
    const note = textareas[i].value.trim();
    if ((val === 'confirmed_missing' || val === 'false_positive' || val === 'need_supplement') && !note) {
      alert(`规则 ${selects[i].dataset.rule}：调整结果或排除误报时必须填写复核备注`);
      textareas[i].focus();
      return;
    }
  }

  const decisions = [];
  for (let i = 0; i < selects.length; i++) {
    const ruleId = selects[i].dataset.rule;
    const result = reviewData?.results?.find(r => r.rule_id === ruleId);
    decisions.push({
      rule_id: ruleId,
      automatic_status: result ? result.status : 'UNCERTAIN',
      human_decision: selects[i].value,
      human_decision_label: HUMAN_DECISION_CN[selects[i].value] || selects[i].value,
      note: textareas[i].value.trim()
    });
  }

  $('#saveDecisions').disabled = true;
  try {
    const res = await fetch(`/api/jobs/${currentJobId}/decisions`, {
      method: 'POST', headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ decisions })
    });
    const data = await res.json();
    if (!res.ok) throw new Error(data.detail || '保存失败');
    decisionsData = data.decisions || [];
    $('#decisionMessage').textContent = `✓ 已保存 ${data.saved_count} 条复核记录`;
    renderReviewTable($('#reviewFilter').value);
    renderManualReview();
    renderOverview();
  } catch (err) {
    $('#decisionMessage').textContent = '保存失败: ' + err.message;
  }
  $('#saveDecisions').disabled = false;
}

// ========== Tab 5: 审查记录 ==========
function renderRecords() {
  // 时间线
  try {
    const statusRes = fetch(`/api/jobs/${currentJobId}/status`);
    const timelineRes = fetch(`/api/jobs/${currentJobId}/timeline`);
    Promise.all([statusRes, timelineRes]).then(([sr, tr]) => {
      if (!sr.ok || !tr.ok) return;
      sr.json().then(statusData => {
        tr.json().then(timelineData => {
          const events = timelineData.events || [];
          $('#timeline').innerHTML = events.map(ev => {
            let cls = 'timeline-item';
            if (ev.stage === 'completed' || ev.stage === 'completed_with_warning') cls += ' tl-active';
            if (ev.stage === 'failed' || ev.error) cls += ' tl-error';
            return `<div class="${cls}">
              <span class="tl-time">${formatTime(ev.time)}</span>
              <span class="tl-desc">${esc(ev.description)}</span>
            </div>`;
          }).join('');
        });
      });
    }).catch(() => {});
  } catch (_) {}

  // 输出文件
  try {
    fetch(`/api/jobs/${currentJobId}/files`).then(res => {
      if (!res.ok) return;
      res.json().then(data => {
        const files = data.files || [];
        $('#outputFiles').innerHTML = files.map(f => {
          const extra = f.downloadable
            ? ` <a href="/api/jobs/${currentJobId}/download/${encodeURIComponent(f.name)}" download>下载</a>`
            : '';
          return `<div class="output-file">
            <div><span class="file-name">${esc(f.name)}</span><br><span class="file-desc">${esc(f.description)}</span></div>
            <span class="file-size">${esc(f.size || '—')}</span>${extra}
          </div>`;
        }).join('');
      });
    }).catch(() => {});
  } catch (_) {}
}

// ========== 工具函数 ==========
function formatTime(value) {
  if (!value) return '—';
  return new Date(value).toLocaleString('zh-CN', { hour12: false });
}

function esc(value) {
  return String(value ?? '').replace(/[&<>"']/g, c => ({
    '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#039;'
  })[c]);
}
