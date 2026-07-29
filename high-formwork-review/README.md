# 高支模专项施工方案智能审查系统

这是一个适合初学者阅读的最小 Python 项目。它读取 MinerU 已经保存到磁盘的解析结果，整理成统一文档，再检查高支模专项施工方案的 10 个必要部分。

当前版本支持命令行和本地 Web 演示：可调用 MinerU HTTP API，也可读取已有 raw 结果；
仍不使用数据库、大模型或任何旧项目模型。

## 文件和目录

```text
high-formwork-review/
├─ app/
│  ├─ __init__.py
│  ├─ models.py
│  ├─ mineru_parser.py
│  ├─ completeness_review.py
│  └─ main.py
├─ config/
│  └─ completeness_rules.json
├─ data/
│  ├─ input/
│  └─ output/
├─ tests/
│  ├─ test_parser.py
│  └─ test_review.py
├─ .env.example
├─ .gitignore
├─ requirements.txt
└─ README.md
```

- `app/models.py`：保存页面、block、章节、证据和审查结果等 8 个数据模型。
- `app/mineru_parser.py`：读取 MinerU JSON，生成 `MinerUDocument`。
- `app/completeness_review.py`：读取 10 条规则，输出 `PASS`、`MISSING` 或 `UNCERTAIN`。
- `app/main.py`：命令行入口，负责写出三个 JSON 和打印结果表。
- `config/completeness_rules.json`：规则别名、关键词、允许的内容类型和匹配数量。
- `data/input/`：可选的本地输入位置；程序也可直接读取其他目录。
- `data/output/`：建议的结果输出位置。
- `tests/test_parser.py`：解析器测试，fixture 在测试临时目录中动态创建。
- `tests/test_review.py`：完整性判定测试。
- `.env.example`：未来 MinerU API 的变量示例；第一版不会读取它。
- `requirements.txt`：测试依赖。

## 安装

需要 Python 3.10 或更高版本。以下命令在 PowerShell 中运行：

```powershell
cd D:\桌面\Competition\high-formwork-review
python -m venv .venv
.\.venv\Scripts\Activate.ps1
python -m pip install -r requirements.txt
```

如果 PowerShell 不允许激活脚本，也可以不激活，后续把 `python` 换成：

```powershell
.\.venv\Scripts\python.exe
```

## 输入是什么

`--raw-dir` 必须指向一个 MinerU raw 目录，其中至少要有：

- 一个 `*_content_list_v2.json`
- 一个 `layout.json`

图片通常放在同目录的 `images/` 中。`full.md` 和 `*_model.json` 可以存在，但第一版不读取它们。

## 如何运行

使用项目附带的输出目录：

```powershell
python -m app.main `
  --raw-dir "D:\桌面\Competition\mineru-test\output\run-001\raw" `
  --output-dir "D:\桌面\Competition\high-formwork-review\data\output"
```

路径中有空格时必须保留双引号。反引号表示 PowerShell 命令换行，也可以把整条命令写在一行。

## 输出是什么

程序在 `--output-dir` 中生成：

- `mineru_document.json`：规范化后的页、block、章节、原始指针和解析警告。
- `completeness_results.json`：10 条独立审查结果。
- `completeness_summary.json`：PASS、MISSING、UNCERTAIN 的数量及全部结果。

终端还会打印：

```text
规则编号 | 检查项 | 状态 | 页码 | 人工复核
```

## 如何看结果

- `PASS`：找到目标正文章节和足够的确认性证据。
- `UNCERTAIN`：找到线索，但可能只有目录、图片、空表格或解析不完整内容，需要人工查看证据页。
- `MISSING`：全文没有发现目标章节或相关内容，也没有相关解析风险。此时不会伪造页码，页码显示 `-`。
- `evidence`：命中证据，包含物理页码、印刷页码、章节路径、引用、bbox、图片/表格和源 JSON 指针。
- `requires_human_review`：为 `true` 时应人工复核。

## 如何运行测试

普通测试：

```powershell
python -m pytest -q
```

同时检查真实 MinerU 样本：

```powershell
$env:MINERU_SAMPLE_RAW_DIR = "D:\桌面\Competition\mineru-test\output\run-001\raw"
python -m pytest -q
Remove-Item Env:MINERU_SAMPLE_RAW_DIR
```

没有设置 `MINERU_SAMPLE_RAW_DIR` 时，真实样本测试会自动跳过，其他测试照常运行。

## 常见错误排查

- “raw 目录不存在”：检查 `--raw-dir` 拼写，并给带空格的路径加双引号。
- “没有 `*_content_list_v2.json`”：确认传入的是 `raw` 目录，不是它的上一级。
- “存在多个 `*_content_list_v2.json`”：每次只在一个 MinerU 运行结果目录中执行。
- “缺少 `layout.json`”：确保 MinerU 结果复制完整。
- “JSON 格式错误”：文件可能未写完或被修改，请重新执行 MinerU。
- `ModuleNotFoundError: pytest`：重新运行 `python -m pip install -r requirements.txt`。
- 图片不存在警告：检查 `images/` 是否与 JSON 一起复制。程序仍会继续，但相关页面需要人工复核。
- 输出目录无法写入：换到当前用户有写入权限的位置。

## 实现说明

项目采用 Python `dataclasses` 和少量纯函数：

- `app/models.py`：定义 8 个指定的数据模型，并支持递归转换为可写入 JSON 的字典。
- `app/mineru_parser.py`：读取 MinerU 原始文件，构建页面、block、章节和文档模型。
- `app/completeness_review.py`：直接接收 `MinerUDocument`，执行配置中的 10 条完整性规则。
- `app/main.py`：处理命令行参数，串联解析与审查，写出 JSON 并打印摘要。
- `config/completeness_rules.json`：保存规则名称、别名、关键词、允许的 block/page 类型和最小匹配数。
- `tests/test_parser.py` 与 `tests/test_review.py`：分别验证解析和审查行为。

依赖方向为 `main → parser/reviewer → models`。解析器不执行审查，审查器不读取 MinerU 原始文件。

## MinerU 解析

- 自动定位唯一的 `*_content_list_v2.json`，并读取同目录的 `layout.json`。
- 顶层页数组下标加 1 得到物理页码；`layout.json` 提供页面宽高。
- 顶层 `paragraph` block 才作为普通正文。其内部的 `type="text"` 只用于提取字符串，不创建独立正文 block。
- `title` 保留 `content.level`，并使用标题层级栈构建章节路径。
- `table` 保留 `content.html`；`image`、`chart` 和表格图片保留 `content.image_source.path`。
- `page_number` 只提供印刷页码，不进入正文。
- 每个 block 保留 bbox、源文件名和形如 `/12/3` 的 `source_pointer`。
- 明确识别目录页；目录中的标题不创建正文 section，但原始 block 继续保留，以支持“仅目录命中”的判断。
- 页面类型支持 `text`、`table`、`drawing`、`organization_chart`、`mixed` 和 `unknown`。
- 正常正文或非空表格通常标记为 `complete`；只有图片、图表或空 HTML 表格时标记为 `partial` 并要求人工复核；没有任何可用内容时标记为 `unreadable`。
- 当前连续页存在空 HTML 表格且上一页存在非空 HTML 表格时，保守标记为 `table_continuation`。
- 所有判断基于内容结构，不写死真实 UUID 或物理页码。

## 完整性审查

每条规则依次查找正文 section、允许类型中的文字或结构证据、目录命中以及相关页面的解析风险：

- `PASS`：存在目标正文 section，并在解析完整页面上取得达到 `minimum_matches` 的确认性证据。
- `UNCERTAIN`：只有目录命中、图片或图表、空表格、证据不足，或者关键证据只位于解析不完整页面。
- `MISSING`：没有目标正文 section、没有相关证据，也不存在可能遮蔽该规则内容的相关解析风险。

`PASS` 和 `UNCERTAIN` 必须保存真实 `ReviewEvidence`。`MISSING` 不伪造证据或页码，其证据数组为空，终端页码显示 `-`，原因中明确说明全文检查未发现相关内容。

特殊规则：

- 相关施工图纸：明确图纸标题加图片可以 `PASS`；无 OCR 的 drawing/image 只能是 `UNCERTAIN`，不能直接判 `MISSING`。
- 计算书：只有目录命中时为 `UNCERTAIN`；正文计算章节配合公式、表格或计算关键词可以 `PASS`。
- 验收要求：普通“材料进场验收”不能独立构成 `PASS`，优先匹配支架、模板、搭设、程序、标准、人员和内容等专项验收词。
- 应急处置措施：匹配应急组织、职责、抢险领导小组、响应、事故报告和救援措施。
- 解析风险只影响可能相关的规则，不因无关页面为 `partial` 而降低全部规则状态。

### 错误处理与测试设计

- `test_parser.py` 在测试过程中动态创建最小 MinerU fixture，覆盖页码、标题层级、图片、表格、bbox、目录排除、图片页、空表格和跨页续表。
- `test_review.py` 直接构造 `MinerUDocument`，覆盖明确正文证据、仅目录命中、仅图纸图片、完整解析且无证据、材料验收误判保护以及无 OCR 图纸。
- 设置 `MINERU_SAMPLE_RAW_DIR` 时执行真实样本集成检查；未设置时自动跳过。
- 缺少输入文件、发现多个内容文件、JSON 无效或顶层结构错误时，程序给出中文错误并返回非零退出码。
- 单个 block 字段异常时尽量继续解析，并把问题写入 `warnings`。

## 安全说明

第一版不会读取 `.env`，也不会读取、打印或提交 MinerU Token。不要把真实 Token 写入 `.env.example`。

### Windows 系统代理

Windows 开启代理后 MinerU 无法使用时，保持：

```text
MINERU_USE_SYSTEM_PROXY=false
```

默认值为 `false`，MinerU 客户端不会读取 Windows 系统代理。只有设置为
`true`、`1`、`yes` 或 `on` 时才会启用系统代理。未来所有 MinerU HTTP
请求都必须复用 `MinerUClient.session`，不得直接调用 `requests.get/post/put`。

## Web 演示页面

Web 版用于本机比赛演示，保留原有命令行功能和 10 条完整性规则，不使用数据库、
登录系统、前端框架或大模型。

### 安装 Web 依赖

```powershell
cd D:\桌面\Competition\high-formwork-review
.\.venv\Scripts\python.exe -m pip install -r requirements.txt
```

`requirements.txt` 已包含 FastAPI、Jinja2、python-multipart 和 Uvicorn。

### 配置 `.env`

复制 `.env.example` 为 `.env`，填写 MinerU Token：

```text
MINERU_API_TOKEN=你的 MinerU Token
MINERU_API_BASE_URL=https://mineru.net
MINERU_USE_SYSTEM_PROXY=false
```

不要把 `.env`、Token、Authorization 请求头或 MinerU 临时签名 URL 提交到仓库。
Web 任务文件和 API 响应不会保存或返回这些敏感信息。

### 启动 Web

```powershell
.\.venv\Scripts\python.exe -m uvicorn app.web:app --reload
```

浏览器访问：

```text
http://127.0.0.1:8000
```

### 页面操作

1. 在“上传与任务”区域选择不超过 50MB 的 PDF，点击“开始解析并审查”。
2. 页面每 2 秒更新一次状态和进度。处理阶段依次为 `uploaded`、
   `mineru_parsing`、`document_parsing`、`completeness_review`、`completed`。
3. 完成后，在“文档解析 Agent”区域查看页数、章节、block、页面解析状态和风险页。
   点击页面可查看文本、title/paragraph/table/image/formula block、bbox、图片路径和
   `source_pointer`。
4. 在“完整性审查 Agent”区域展开 10 条规则，查看 PASS、MISSING、UNCERTAIN、
   命中章节、命中术语、子项和逐条证据。
5. 在“人工复核”区域选择“确认”“驳回”或“保持待复核”，填写备注并保存。
   结果写入 `data/web/jobs/{job_id}/decisions.json`。

### 三个模块的区别

- **MinerU**：底层多模态解析工具，负责把 PDF 转换为文本、表格、图片、公式和版面结果。
- **文档解析 Agent**：校验 MinerU 结果，构建章节树，分类页面并标记解析风险。
- **完整性审查 Agent**：在结构化文档上执行固定的 10 条规则，给出状态、原因和可追溯证据。

### 当前限制

- `BackgroundTasks` 仅用于当前单机演示版。服务重启后，正在运行的后台任务不可恢复。
- 暂不支持多实例部署，也没有可靠任务队列；不要把本版本当作生产任务系统。
- 不支持多用户、登录、数据库和任务权限隔离。
- 人工复核记录是本地 JSON 文件；同一任务同时写入时不提供数据库级并发控制。
- 页面只展示解析和审查所需字段，不直接返回整份 MinerU 原始 JSON。
- 当前只接受最大 50MB、扩展名为 `.pdf` 且文件头为 `%PDF-` 的文件。

### 演示建议

向老师演示时先说明三个模块的职责边界，再上传一份已验证的高支模方案：

1. 在任务进度中指出 MinerU、文档解析 Agent、完整性审查 Agent 的阶段切换。
2. 展示解析统计，重点打开一个 `partial` 页面，说明页面分类、警告和
   `requires_human_review` 如何避免错误自动判断。
3. 展开一条 PASS 规则，从规则原因依次展示命中章节、物理页码、证据原文、bbox 和
   `source_pointer`，说明证据可以回溯到 MinerU block。
4. 展开 UNCERTAIN 规则，说明系统不会把不完整证据误判为 MISSING。
5. 在人工复核区填写备注并保存，展示 `decisions.json` 是演示版的人机协同闭环。

## 审查结果质量核验规格

以下内容记录解析与审查核心的质量核验规格；Web 演示层只复用这些结果，不改变规则逻辑。
项目仍不使用数据库、大模型、Word 或 Excel。

### 章节构建

section 候选只允许来自顶层 MinerU `title` block。本阶段不把 paragraph 提升为 section。

以下候选不创建 section，但原始 block 继续保留：

- 已识别目录页中的 title，以及带连续点线和末尾页码的目录式文本。
- `1、`、`(1)`、`（1）`、`1)`、`8）、` 等普通列表或步骤编号。
- 以“图 1：”“表 2：”“附图 3：”“附件 4：”等形式开头的说明文字。
- 去掉编号后少于两个有效字符，或只有数字、标点、公式符号的极短文本。
- 同一页中相邻出现且标准化后完全相同的重复标题；只保留第一条。

`page_number`、table/image/formula 内部文本和表格单元格不会成为 section。`MinerUBlock.title_level` 保留 MinerU 原值；`MinerUSection.level` 继续使用 MinerU level，并仅以明确数字标题层级作保守补充。被排除的 title 不会中断父章节范围。审查器只使用 `document.sections` 中已接受的标题更新章节路径。

### 必要子项与 PASS 阈值

章节标题本身不算内容子项。子项必须由目标正文 section 内的非目录证据满足：

- HF-COMP-001：至少 3/4，且“高支模部位或主要参数”必选。
- HF-COMP-002：至少 2/3，覆盖图纸/施工组织设计、规范标准、法律法规。
- HF-COMP-003：至少 2/4，覆盖进度、材料、设备、劳动力。
- HF-COMP-004：至少 2/4，覆盖技术参数、工艺流程、搭设/安装、拆除。
- HF-COMP-005：至少 2/4，覆盖组织保障、技术保障、监测监控、危险源/防护。
- HF-COMP-006：至少 2/4，覆盖管理人员、安全人员、特种作业人员、岗位职责。
- HF-COMP-007：至少 2/7；材料进场验收不计入支架、模板、搭设、程序、标准、内容、人员等专项验收子项。
- HF-COMP-008：至少 3/6，覆盖应急组织、职责、响应、事故报告、抢险救援、应急物资。
- HF-COMP-009：必须有正文计算章节，并至少命中公式、计算表格或明确计算内容中的一类。
- HF-COMP-010：相关正文标题和可关联图片同时存在才可以 PASS。

PASS 必须命中正文 section、在非 unreadable 页面上达到必要子项阈值、满足必选项，并保存至少一条可追溯证据。只有标题、只有目录、子项不足或只有无关联图片时为 UNCERTAIN。达到阈值的证据主要来自 partial 页面时转为 UNCERTAIN。图纸规则仅在 partial 原因是图片无 OCR 且标题与图片关联明确时允许 PASS；关联不足仍为 UNCERTAIN。

### 证据核验报告

每次命令行审查后，在输出目录生成 `completeness_evidence_check.md`。报告总览包含章节数和三种状态数量；每条规则包含：

- rule_id、name、status、reason
- matched_sections、physical_pages、printed_pages
- matched_terms、matched_subitems
- evidence block type、quote 或 description
- image_path、table_html 是否存在
- page_type、parse_status、whether_from_toc
- requires_human_review

每条 PASS 明确写明已满足的必要子项、达到的数量和判定原因。无数据字段写“无”，不制造页码或证据。报告使用与 JSON 审查结果完全相同的内部判定明细。

### 验证

在现有测试文件中增加章节过滤、title_level 保留、标题单独命中、子项阈值、partial/unreadable 降级、图纸无 OCR 保护和 Markdown 字段测试。原有测试必须继续通过，并重新运行真实 87 页样本。完成后对比章节数量、审查汇总、逐规则状态和 PASS 主要证据，并输出修改后前 50 个章节供人工核验。
