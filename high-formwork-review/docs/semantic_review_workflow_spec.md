# 规范语义审查 Workflow 规格（Dify 建台用）

> 本文档给在 Dify 控制台创建"规范语义审查"Workflow 的人（或 Agent）。
> 系统侧代码（`app/services/semantic_dify.py`）已按本规格实现，建好后填入
> `DIFY_SEMANTIC_API_KEY` 并设 `SEMANTIC_REVIEW_MODE=dify` 即可联调。

## 1. 应用类型

**Workflow**（非 Chatflow）。以 blocking 模式调用 `POST /v1/workflows/run`。

## 2. 开始节点 —— 输入变量（4 个，全部必填）

| 变量名 | 类型 | 说明 |
|--------|------|------|
| `task_id` | 文本（短） | 批次追踪号，如 `semantic-batch-3-a1b2c3d4` |
| `rules_json` | 段落（长文本） | 本批规则定义 JSON 数组（≤8 条），字段见 §3 |
| `evidence_json` | 段落（长文本） | 与规则一一对应的方案证据文本 JSON 数组 |
| `expected_rule_count` | 数字 | 本批规则条数，用于校验输出完整性 |

## 3. rules_json / evidence_json 结构

```json
// rules_json
[
  {
    "rule_id": "1.9",
    "rule_name": "方案编制单位",
    "check_content": "专项施工方案应由施工单位组织编制",
    "semantic_judgment": "编制主体必须是施工单位，不得为分包或咨询机构",
    "standard": "住建部37号令-第十一条",
    "original_text": "专项施工方案应由施工单位组织编制...",
    "severity": "A-mandatory"
  }
]

// evidence_json（rule_id 与上面对应）
[
  { "rule_id": "1.9", "evidence_text": "……从方案中召回的相关章节文本，最长6000字……" }
]
```

## 4. LLM 节点 —— Prompt

模型要求：**指令遵循强、稳定输出 JSON** 的模型（实例里已有的额度模型即可）。
温度建议 ≤0.3。

### 系统提示词（原样粘贴）

```
你是高支模专项施工方案审查专家，负责对照规范条款逐条审查方案内容。

审查原则：
1. 只依据提供的"方案证据"判断，禁止使用证据以外的信息，禁止脑补。
2. 判定为 COMPLIANT 或 VIOLATED 时，evidence_quote 必须是证据文本中逐字存在的原句片段；找不到可引用的原句就只能判 UNCERTAIN。
3. 证据不足以支撑明确结论时，判 UNCERTAIN，宁可保守，不许猜测。
4. 规范原文（original_text）是判定标准，方案证据是被审对象，不要颠倒。
5. 对每条输入规则都必须输出一条结果，rule_id 原样带回，不得遗漏、不得重复、不得新增。

状态定义：
- COMPLIANT：证据表明方案满足规范要求
- VIOLATED：证据表明方案与规范要求冲突
- UNCERTAIN：证据缺失、含糊或不足以判定

输出格式：只输出一个 JSON 数组，不要任何解释、前后缀或 markdown 围栏：
[
  {
    "rule_id": "1.9",
    "status": "COMPLIANT|VIOLATED|UNCERTAIN",
    "reason": "50字以内的判定理由，说明依据了证据中的什么内容",
    "evidence_quote": "证据原文逐字引用（≤120字）；UNCERTAIN 可为空字符串",
    "confidence": "high|medium|low"
  }
]
```

### 用户提示词（Dify 变量引用）

```
任务编号：{{#1735000000000.task_id#}}
本批规则数量：{{#1735000000000.expected_rule_count#}}

【规则定义】
{{#1735000000000.rules_json#}}

【方案证据】
{{#1735000000000.evidence_json#}}

请对每条规则输出审查结果（JSON 数组）。
```

> 注：`{{#1735000000000.变量名#}}` 中的节点 ID 以实际控制台"开始"节点 ID 为准，
> 在 LLM 节点里直接插入变量即可，不必手抄。

## 5. 结束节点 —— 输出变量

| 变量名 | 类型 | 取值 |
|--------|------|------|
| `result_json` | 文本 | LLM 节点的输出文本（系统侧会解析 JSON 并剥离可能的围栏） |

## 6. 系统侧校验（已实现，建台者了解即可）

- `rule_id` 集合必须与请求批次完全一致（多/少/重复 → 整批拒绝并降级本地）
- `status` 仅接受 COMPLIANT / VIOLATED / UNCERTAIN
- VIOLATED / COMPLIANT 的 `evidence_quote` 会展示给复核人，务必保证逐字可查

## 7. 验收清单

建好 Workflow 后，用下面最小请求自测（替换 YOUR_KEY）：

```bash
curl -X POST https://api.dify.ai/v1/workflows/run \
  -H "Authorization: Bearer YOUR_KEY" -H "Content-Type: application/json" \
  -d '{
    "inputs": {
      "task_id": "smoke-test-1",
      "rules_json": "[{\"rule_id\":\"T-1\",\"rule_name\":\"测试规则\",\"check_content\":\"方案应包含工程概况\",\"semantic_judgment\":\"证据中出现工程概况描述即合规\",\"standard\":\"测试\",\"original_text\":\"方案应包含工程概况\",\"severity\":\"A-mandatory\"}]",
      "evidence_json": "[{\"rule_id\":\"T-1\",\"evidence_text\":\"一、工程概况：本项目为教学楼，支模高度13.88米。\"}]",
      "expected_rule_count": 1
    },
    "response_mode": "blocking",
    "user": "smoke-test"
  }'
```

期望返回 `data.outputs.result_json` 内含 `rule_id: "T-1"`、`status: "COMPLIANT"` 的
JSON 数组。通过后把新应用的 API Key 交给系统侧填入 `.env`。
