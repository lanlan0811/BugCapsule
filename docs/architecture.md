# BugCapsule 0.1 架构

## 目标

BugCapsule 将运行时故障证据保存为可移植、可校验、默认脱敏的 `.bugcapsule`，再从同一归档向 CLI、Web 和后续 HTML 报告提供事实。模型分析、Patch 建议和验证结果不能绕过证据引用或人工确认边界。

## 当前组件

```text
FastAPI 演示服务 + PostgreSQL
        │ OpenTelemetry Span / Trace Context 日志
        ▼
本地已脱敏 JSONL 证据流
        │ bugcapsule capture --trace-id
        ▼
.bugcapsule（权威事实源）
        │ 完整性与证据关联校验
        ├──────────────┐
        ▼              ▼
SQLite 元数据索引    EvidenceChain
        │              │
        └──────┬───────┘
               ▼
   live / replay / off 模型分析
               │ 严格 Schema + Evidence ID 校验
               ▼
       CLI JSON / Jinja2 + HTMX Web
```

### 运行时证据

主演示服务通过 OpenTelemetry FastAPI 与 SQLAlchemy instrumentation 记录 HTTP 和数据库 Span。标准日志在写入前注入当前 `trace_id`、`span_id`，并与 Span 使用同一脱敏器。证据仅写入配置的本地数据目录。

### 故障胶囊

胶囊是采用确定性成员顺序、时间戳和权限写出的 ZIP_STORED 归档。`manifest.json` 记录 Schema 版本、服务、Trace、Git、环境及每个 payload 的大小、媒体类型和 SHA-256。导入器在读取内容前限制文件数、单文件大小、总展开大小与压缩比，并拒绝绝对路径、路径穿越、目录、符号链接、加密成员、重复成员和未知压缩方式。

### 证据关联

`EvidenceCorrelator` 重新验证每个内容派生 Evidence ID，并拒绝重复 ID、跨 Trace 引用、重复 Span、未知 Span 和未知父 Span。它输出两个确定性视图：

- 优先级视图：按已捕获优先级、证据类型、时间和 Evidence ID 排序；
- 因果时间线：按运行时间排列，并通过父 Span、日志 Span、Stack Trace 和源码引用建立关系。

这一层不调用模型，因此只陈述已捕获的传播路径和候选源码区域。

### SQLite 索引

SQLite 只保存可重建的列表元数据，例如胶囊 ID、状态、Trace/Git 标识、证据数量、脱敏命中数、归档大小和归档 SHA-256。日志正文、Stack Trace 与源码正文不进入数据库。详情读取时会重新计算归档 SHA-256、重新导入胶囊并重建证据链；归档变化会产生显式陈旧索引错误。

### 模型分析

`AnalysisService` 从已校验的 `EvidenceChain` 构造确定性、有字节上限的模型输入。胶囊内容被明确标为不可信数据；只发送已完成脱敏的排序证据，不读取或发送整个仓库。请求摘要绑定提供方、模型、API 风格、指令、输入和输出 Schema。

适配器支持 OpenAI-compatible Responses API 与 Chat Completions 两种请求形式。Responses 请求关闭服务端存储；API Key 只从 `SecretStr` 环境配置进入授权头，错误信息不包含响应正文或密钥。模型必须返回严格结构化根因候选，不能提供 Root Cause ID。确定性代码会校验连续排名、字段边界、重复候选及每个 Evidence ID；格式或引用错误只重试一次，随后返回安全错误。

`live` 只在响应完全有效后保存结构化回放记录；`replay` 必须命中相同请求 SHA-256、提供方和模型；`off` 不访问模型或索引。分析产物作为 `analysis/root-causes.json` 原子写回胶囊并更新清单 SHA-256，详情读取时会再次校验证据引用。原始提示和原始模型响应都不持久化。

### Patch 安全层

`PatchGenerationService` 选择已验证的根因候选并构造独立的有界请求。模型响应只包含摘要、unified diff、Evidence ID 和非权威安全备注；Patch ID、Diff SHA-256、修改文件清单和安全检查清单均由确定性代码生成。无效结构、证据引用或 Diff 最多重试一次，只有完全有效的结构化响应才会写入 Patch 回放。

`PatchSafetyValidator` 仅接受规范 Git unified diff。它拒绝二进制内容、Markdown 围栏、删除/重命名/复制、文件模式变化、含糊文件头、无 Hunk、路径穿越、重复修改、允许根之外路径和保护路径。每个目标还必须对应胶囊中的 `SOURCE` Evidence，解析后的本地目标必须留在配置的源码工作区且不能是符号链接。导入与详情读取会重新执行同一安全策略，不信任胶囊中自报的 `safety_checks`。

通过校验的 `patches/candidate.diff` 和 `patches/candidate.json` 原子写回胶囊。当前阶段只展示和导出 Patch，不应用工作区，也不执行任何模型提供的命令。

### 人工批准与隔离验证

验证入口同时要求完整 Patch ID、完整 Patch SHA-256 和明确批准布尔值。三者在任何 Docker 或临时副本操作前与胶囊当前 Patch 比对；`Verification ID` 由批准绑定内容派生。验证命令及命令 ID 只来自环境配置，模型输出不能影响它们。

验证器从配置的源码根建立 before/after 两份临时副本，拒绝副本中的符号链接，只在 after 中通过 `git apply --check` 后应用 canonical diff。主源码中的目标文件在验证前后做 SHA-256 对照。Docker 执行器使用专用锁定依赖镜像、非 root 用户、只读根和工作区、`network=none`、`cap-drop=ALL`、`no-new-privileges`、临时 `/tmp` 以及 CPU/内存/PID/超时限制。

固定回归应在 before 失败、after 成功；其他组合明确记录为失败。两个容器的原始输出先经过默认脱敏，再与退出码、耗时、超时标记和输出 SHA-256 写入 `verification/`。胶囊导入和详情读取会重新验证批准绑定、日志哈希、命令 ID 与清单状态。

### Web

Web 服务仅允许配置为 `127.0.0.1` 或 `localhost`，并校验 Host。页面由 Jinja2 服务端渲染；HTMX 2.0.10 与少量原生 JavaScript 均由 Python 包本地提供。胶囊上传受配置大小限制、同源检查和完整导入校验保护；相同 `capsule_id` 的不同字节不会覆盖现有归档。

### HTML 对比报告

`HtmlReportService` 只接受包含分析、Patch 和完整 before/after 验证结果的 `CapsuleDetail`。报告模板与 Web 页面复用同一证据视图模型和时间格式，不单独维护事实副本；渲染过程不读取当前工作区，也不再次调用模型。输出字节确定性生成并计算交付 SHA-256。

HTML 内联 Design System 样式与 SVG 标志，不包含外部资源或脚本，并同时设置严格 CSP、`nosniff` 和 `no-store` 交付头。Jinja 自动转义覆盖模型文本、日志和证据内容。CLI 默认拒绝覆盖已有报告，Web 以附件形式下载同一组确定性字节。

### 版本化基准数据集

`benchmarking/dataset.json` 是人工标注的权威输入，Schema 强制至少 12 个案例，并要求连接泄漏、数据库不可达和慢查询各不少于 4 个。`BenchmarkDatasetBuilder` 仅从该输入派生时间、Trace/Span、Git 与 Evidence 标识，生成可逐项导入校验且跨目录字节一致的胶囊。标注文件与生成结果保持独立，后续指标通过标注 SHA-256 绑定具体数据版本。

## 事实一致性

CLI `capsules list/show`、Web 页面和 HTML 报告都从 `CapsuleSummary`、`CapsuleDetail` 与 `EvidenceChain` 读取数据。共享视图模型只负责中文标签、时间格式和展示摘要，不创建新的状态或分析结论。

## 尚未实现的边界

模型分析、Patch 或验证未运行时，Web 仍会明确显示对应的未开始状态，报告端点返回未就绪错误，不会用占位结果冒充已完成事实。量化评测与可用性研究属于后续阶段。
