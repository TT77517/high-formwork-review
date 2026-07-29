const $ = (selector) => document.querySelector(selector);
const stageNames = {
  waiting: "等待上传", uploaded: "已上传", mineru_parsing: "MinerU 多模态解析",
  document_parsing: "文档解析 Agent", completeness_review: "完整性审查 Agent",
  completed: "已完成", failed: "失败"
};
let currentJobId = null;
let reviewData = null;
let pollTimer = null;

$("#pdfFile").addEventListener("change", (event) => {
  $("#fileLabel").textContent = event.target.files[0]?.name || "选择不超过 50MB 的 PDF 文件";
});

$("#uploadForm").addEventListener("submit", async (event) => {
  event.preventDefault();
  const file = $("#pdfFile").files[0];
  if (!file) return;
  $("#uploadError").textContent = "";
  $("#submitButton").disabled = true;
  const form = new FormData();
  form.append("file", file);
  try {
    const response = await fetch("/api/jobs", { method: "POST", body: form });
    const data = await response.json();
    if (!response.ok) throw new Error(data.detail || "上传失败");
    currentJobId = data.job_id;
    renderStatus(data);
    pollTimer = setInterval(pollStatus, 2000);
  } catch (error) {
    $("#uploadError").textContent = error.message;
    $("#submitButton").disabled = false;
  }
});

async function pollStatus() {
  try {
    const response = await fetch(`/api/jobs/${currentJobId}/status`);
    const data = await response.json();
    if (!response.ok) throw new Error(data.detail || "状态读取失败");
    renderStatus(data);
    if (data.status === "completed") {
      clearInterval(pollTimer);
      await loadResults();
      $("#submitButton").disabled = false;
    } else if (data.status === "failed") {
      clearInterval(pollTimer);
      $("#submitButton").disabled = false;
    }
  } catch (error) {
    clearInterval(pollTimer);
    $("#uploadError").textContent = error.message;
    $("#submitButton").disabled = false;
  }
}

function renderStatus(data) {
  $("#taskFile").textContent = data.file_name || "—";
  $("#taskTime").textContent = formatTime(data.uploaded_at);
  $("#taskId").textContent = data.job_id || "—";
  $("#taskStage").textContent = `${data.stage} · ${stageNames[data.stage] || data.stage}`;
  $("#progressBar").style.width = `${data.progress || 0}%`;
  $("#taskMessage").textContent = data.message || "";
  const badge = $("#statusBadge");
  badge.textContent = stageNames[data.status] || data.status;
  badge.className = `badge ${data.status === "failed" ? "failed" : data.status === "completed" ? "completed" : "running"}`;
  if (data.error_stage) $("#uploadError").textContent = `失败阶段：${data.error_stage}。${data.message}`;
}

async function loadResults() {
  const [documentResponse, reviewResponse] = await Promise.all([
    fetch(`/api/jobs/${currentJobId}/document`),
    fetch(`/api/jobs/${currentJobId}/review`)
  ]);
  const documentData = await documentResponse.json();
  reviewData = await reviewResponse.json();
  if (!documentResponse.ok || !reviewResponse.ok) throw new Error("结果加载失败");
  renderDocument(documentData);
  renderReview(reviewData);
  $("#documentPanel").classList.remove("hidden");
  $("#reviewPanel").classList.remove("hidden");
  $("#decisionPanel").classList.remove("hidden");
}

function renderDocument(data) {
  const stats = [
    ["解析引擎", data.engine], ["总页数", data.physical_page_count],
    ["有效章节", data.section_count], ["block", data.block_count],
    ["文本块", data.text_block_count], ["表格", data.table_count],
    ["图片", data.image_count], ["公式", data.formula_count],
    ["complete 页", data.complete_page_count], ["partial 页", data.partial_page_count],
    ["unreadable 页", data.unreadable_page_count], ["人工复核页", data.human_review_page_count]
  ];
  $("#documentStats").innerHTML = stats.map(([label, value]) =>
    `<div class="stat"><strong>${escapeHtml(value)}</strong><small>${escapeHtml(label)}</small></div>`).join("");
  $("#sectionRows").innerHTML = data.sections.map(section => `<tr>
    <td>${escapeHtml(section.title)}</td><td>${section.level}</td>
    <td>${section.physical_page_start}–${section.physical_page_end}</td>
    <td>${escapeHtml((section.path || []).join(" / "))}</td></tr>`).join("");
  $("#pageRows").innerHTML = data.pages.map(page => `<tr data-page="${page.physical_page}">
    <td>${page.physical_page}</td><td>${escapeHtml(page.printed_page || "—")}</td>
    <td>${escapeHtml(page.page_type)}</td><td>${escapeHtml(page.parse_status)}</td>
    <td>${page.text_length}</td><td>${page.image_count}/${page.table_count}/${page.formula_count}</td>
    <td class="${page.requires_human_review ? "review-yes" : ""}">${page.requires_human_review ? "需要" : "否"}</td></tr>`).join("");
  document.querySelectorAll("#pageRows tr").forEach(row =>
    row.addEventListener("click", () => loadPage(Number(row.dataset.page))));
}

async function loadPage(pageNumber) {
  const response = await fetch(`/api/jobs/${currentJobId}/document/pages/${pageNumber}`);
  const page = await response.json();
  if (!response.ok) return;
  const warnings = page.warnings?.length ? `<p class="review-yes">警告：${escapeHtml(page.warnings.join("；"))}</p>` : "";
  $("#pageDetail").classList.remove("empty");
  $("#pageDetail").innerHTML = `<h3>第 ${page.physical_page} 页详情</h3>${warnings}
    <div class="page-text">${escapeHtml(page.text || "本页无可用文本")}</div>
    <div>${page.blocks.map(renderBlock).join("")}</div>`;
}

function renderBlock(block) {
  const image = block.image_path
    ? `<img src="/api/jobs/${currentJobId}/asset?path=${encodeURIComponent(block.image_path)}" alt="解析图片">` : "";
  const table = block.table_html
    ? `<details><summary>查看 table_html</summary><pre>${escapeHtml(block.table_html)}</pre></details>` : "";
  return `<article class="block"><div class="block-head"><b>${escapeHtml(block.block_type)}</b>
    <span>${escapeHtml(block.block_id)}</span><span>source: ${escapeHtml(block.source_pointer || "—")}</span></div>
    <pre>${escapeHtml(block.text || "无文本")}</pre>
    <small>bbox: ${escapeHtml(JSON.stringify(block.bbox || null))}</small>${image}${table}</article>`;
}

function renderReview(data) {
  const summary = data.summary;
  $("#reviewStats").innerHTML = [
    ["规则总数", summary.total_rules], ["PASS", summary.pass_count],
    ["MISSING", summary.missing_count], ["UNCERTAIN", summary.uncertain_count]
  ].map(([label, value]) => `<div class="stat"><strong>${value}</strong><small>${label}</small></div>`).join("");
  $("#ruleList").innerHTML = data.results.map(rule => `<details class="rule">
    <summary><b>${escapeHtml(rule.rule_id)}</b><span>${escapeHtml(rule.name)}</span>
      <span class="status-chip status-${rule.status}">${rule.status}</span>
      <span>${rule.requires_human_review ? "需人工复核" : "自动判断"}</span></summary>
    <div class="rule-body"><p><strong>判断原因：</strong>${escapeHtml(rule.reason)}</p>
      <div class="meta-grid">
        <div><b>命中章节</b><br>${(rule.matched_sections || []).map(s => `${escapeHtml(s.title)}（${s.physical_page_start}-${s.physical_page_end}页）`).join("<br>") || "无"}</div>
        <div><b>命中术语</b><br>${escapeHtml((rule.matched_terms || []).join("、") || "无")}</div>
        <div><b>命中子项</b><br>${(rule.matched_subitems || []).map(s => `${s.satisfied ? "✓" : "○"} ${escapeHtml(s.name)}：${escapeHtml((s.matched_terms || []).join("、") || "无")}`).join("<br>") || "无"}</div>
        <div><b>证据页码</b><br>${escapeHtml((rule.physical_pages || []).join("、") || "无")}</div>
      </div>
      <h3>证据详情</h3>${(rule.evidence || []).map(renderEvidence).join("") || "<p>无证据（MISSING 不制造页码或证据）。</p>"}
    </div></details>`).join("");
  renderDecisions(data.results, data.decisions || []);
}

function renderEvidence(item) {
  const image = item.image_path
    ? `<img src="/api/jobs/${currentJobId}/asset?path=${encodeURIComponent(item.image_path)}" alt="证据图片">` : "";
  const table = item.table_html
    ? `<details><summary>查看 table_html</summary><pre>${escapeHtml(item.table_html)}</pre></details>` : "";
  return `<article class="evidence"><b>物理页 ${item.physical_page}</b> · ${escapeHtml(item.block_type)}
    · ${escapeHtml((item.section_path || []).join(" / ") || "无章节")}
    <blockquote>${escapeHtml(item.quote || item.description || "无文字证据")}</blockquote>
    <small>说明：${escapeHtml(item.description || "—")}<br>page_type：${escapeHtml(item.page_type || "见页面详情")}
    · parse_status：${escapeHtml(item.parse_status || "见页面详情")}<br>
    bbox：${escapeHtml(JSON.stringify(item.bbox || null))} · source_pointer：${escapeHtml(item.source_pointer || "—")}
    · whether_from_toc：${item.whether_from_toc ? "是" : "否"}
    · 证据需复核：${item.requires_human_review ? "是" : "否"}<br>
    image_path：${escapeHtml(item.image_path || "无")}</small>${image}${table}</article>`;
}

function renderDecisions(results, saved) {
  const savedByRule = Object.fromEntries(saved.map(item => [item.rule_id, item]));
  $("#decisionList").innerHTML = results.map(rule => {
    const old = savedByRule[rule.rule_id] || {};
    return `<div class="decision" data-rule="${escapeHtml(rule.rule_id)}" data-status="${rule.status}">
      <b>${escapeHtml(rule.rule_id)}</b><span>${escapeHtml(rule.name)} · <span class="status-chip status-${rule.status}">${rule.status}</span></span>
      <select aria-label="${escapeHtml(rule.rule_id)} 人工决定">
        <option value="pending" ${old.human_decision === "pending" ? "selected" : ""}>保持待复核</option>
        <option value="confirmed" ${old.human_decision === "confirmed" ? "selected" : ""}>确认</option>
        <option value="rejected" ${old.human_decision === "rejected" ? "selected" : ""}>驳回</option>
      </select>
      <textarea maxlength="2000" placeholder="填写复核备注">${escapeHtml(old.note || "")}</textarea></div>`;
  }).join("");
}

$("#saveDecisions").addEventListener("click", async () => {
  const decisions = [...document.querySelectorAll(".decision")].map(row => ({
    rule_id: row.dataset.rule,
    automatic_status: row.dataset.status,
    human_decision: row.querySelector("select").value,
    note: row.querySelector("textarea").value
  }));
  $("#saveDecisions").disabled = true;
  const response = await fetch(`/api/jobs/${currentJobId}/decisions`, {
    method: "POST", headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ decisions })
  });
  const data = await response.json();
  $("#decisionMessage").textContent = response.ok ? `已保存 ${data.saved_count} 条复核记录` : (data.detail || "保存失败");
  $("#saveDecisions").disabled = false;
});

function formatTime(value) {
  if (!value) return "—";
  return new Date(value).toLocaleString("zh-CN", { hour12: false });
}
function escapeHtml(value) {
  return String(value ?? "").replace(/[&<>"']/g, char => ({
    "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#039;"
  })[char]);
}
