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

### Web

Web 服务仅允许配置为 `127.0.0.1` 或 `localhost`，并校验 Host。页面由 Jinja2 服务端渲染；HTMX 2.0.10 与少量原生 JavaScript 均由 Python 包本地提供。胶囊上传受配置大小限制、同源检查和完整导入校验保护；相同 `capsule_id` 的不同字节不会覆盖现有归档。

## 事实一致性

CLI `capsules list/show` 和 Web 页面都从 `CapsuleSummary`、`CapsuleDetail` 与 `EvidenceChain` 读取数据。Web 视图模型只负责中文标签、时间格式和展示摘要，不创建新的状态或分析结论。后续 HTML 报告必须复用相同对象。

## 尚未实现的边界

模型 `live/replay/off` 适配器、根因候选、Patch 安全检查、人工 SHA-256 确认、受限 Docker 验证器和 HTML 对比报告属于后续阶段。当前 Web 会明确显示“未调用模型”“尚无修复建议”和“验证未开始”，不会用占位结果冒充已完成事实。
