# BugCapsule 0.1 架构说明

本文描述 BugCapsule 的实际实现边界、权威数据源、关键数据流和安全不变量。目标不是画出理想化平台，而是让维护者能从文档直接定位代码、验证事实并判断一次变更是否破坏闭环。

## 1. 架构目标

BugCapsule 只解决一件事：把一次运行时故障变成可移交、可引用、可验证的工程证据。

系统遵守四条不变量：

1. `.bugcapsule` 是权威事实源，SQLite 只是可删除、可重建的索引；
2. 模型结论只能引用本次请求中存在的 `Evidence ID`；
3. Patch 不能直接修改主工作区，验证前必须绑定 Patch ID、SHA-256 和明确批准；
4. CLI、Web 与 HTML 报告读取同一个 `CapsuleDetail`，不维护第二套事实。

## 2. 系统上下文

```text
┌────────────────────────────── 运行时 ──────────────────────────────┐
│ FastAPI 订单服务 ─ SQLAlchemy ─ PostgreSQL                         │
│        │ HTTP / DB Span          │ 固定双连接池                     │
│        └──────── OpenTelemetry + Trace Context 日志 ───────────────┘
└───────────────────────────────┬────────────────────────────────────┘
                                │ 已脱敏 JSONL
                                ▼
┌──────────────────────────── 捕获与事实层 ──────────────────────────┐
│ CaptureService → Redactor → CapsuleArchive → CapsuleIndex          │
│                       .bugcapsule（权威）  SQLite（可重建）          │
└───────────────────────────────┬────────────────────────────────────┘
                                │ EvidenceChain
                                ▼
┌────────────────────────── 分析与修复建议层 ────────────────────────┐
│ deterministic request → live / replay / off → root causes          │
│ root cause + source evidence → Patch request → PatchSafetyValidator│
└───────────────────────────────┬────────────────────────────────────┘
                                │ 人工确认 Patch ID + SHA-256
                                ▼
┌────────────────────────────── 验证层 ──────────────────────────────┐
│ before 临时副本 ─┐                                                │
│                  ├→ 无网络、非 root、只读 Docker 回归 → 比较结果   │
│ after 临时副本  ─┘          │                                     │
│                              └→ verification/ + 自包含 HTML 报告   │
└────────────────────────────────────────────────────────────────────┘
```

## 3. 运行时与主演示

`src/bugcapsule/demo/` 实现可控订单服务。连接池由环境配置为 `pool_size=2`、`max_overflow=0` 和短超时；前两次 `/demo/leak` 在异常路径保留 Session，第三次请求无法获取连接并返回 `503 database_pool_exhausted`。`/demo/reset` 关闭注册表中保留的 Session，使场景可重复执行。

Compose 将 PostgreSQL 留在 `demo-internal` 内部网络。订单服务额外连接仅供宿主访问的 `demo-edge` 桥接网络，端口仍绑定 `127.0.0.1`；入口网络关闭 IP masquerade。HTTP 健康检查使用容器环境中的端口，`docker compose up --wait` 只有在 Uvicorn 实际响应后才完成。

OpenTelemetry FastAPI 与 SQLAlchemy instrumentation 记录 HTTP、数据库 Span 和异常。日志处理器写入相同 Trace Context，并在落盘前经过递归脱敏。命名卷只保存 `traces.jsonl`、`logs.jsonl` 和脱敏审计数据。

## 4. 捕获、脱敏与归档

`demo capture` 使用固定参数数组调用 `docker compose cp`，不拼接 shell 命令。控制器只接受配置中的服务名和绝对容器目录，随后执行以下检查：

- 本地目标必须位于配置的证据目录；
- 同步结果不能包含符号链接；
- JSONL 总字节数不能超过上限；
- 每行必须是 JSON 对象；
- 池耗尽记录必须包含合法的 32 位小写 Trace ID。

`CaptureService` 以 Trace ID 选择相关 Span 与日志，再加入 Stack Trace、允许根内源码窗口、Git、依赖锁摘要和环境摘要。所有字段在进入归档前脱敏，脱敏报告只保留规则、JSON Pointer、替换标记和计数，不保留秘密原文。

`CapsuleArchive` 以固定成员顺序、时间戳、权限和 `ZIP_STORED` 生成确定性归档。导入器在读取内容前限制成员数、单文件大小、总展开大小和压缩比，并拒绝路径穿越、目录、符号链接、加密成员、重复成员和未知压缩方法。

## 5. 证据关联与索引

`EvidenceCorrelator` 重新计算内容派生 Evidence ID，并验证 Trace/Span 关系。它输出：

- `priority_items`：按捕获优先级、证据类型、时间和 Evidence ID 稳定排序；
- `timeline`：按运行时间排列 HTTP Span、数据库 Span、日志、Stack Trace 和源码引用；
- `candidate_sources`：只根据 Stack Trace 与已捕获源码建立候选代码区域。

该层不调用模型。它只陈述归档中已经存在的事实。

`CapsuleIndex` 保存胶囊 ID、Trace/Git 标识、处理状态、证据数量、脱敏计数、归档大小和 SHA-256。详情读取会重新计算归档摘要、重新导入并重建证据链；索引与归档不一致时显式报错，不静默使用旧记录。

## 6. 模型边界

`AnalysisService` 从已校验的 `EvidenceChain` 构造有字节上限的确定性请求。请求明确声明证据正文是不可信数据，只发送排序后的已脱敏片段，不发送整个仓库。

| 模式 | 行为 | 可陈述能力 |
| --- | --- | --- |
| `live` | 调用配置的 OpenAI-compatible Responses 或 Chat Completions API | 当前提供方与模型的实际结果 |
| `replay` | 按请求 SHA-256、provider、model 精确读取结构化记录 | 离线可重复管线，不代表模型泛化能力 |
| `off` | 不访问模型，不生成根因 | 确定性证据浏览 |

API Key 只从 `SecretStr` 环境配置进入授权头；Responses 请求关闭服务端存储。系统不持久化原始提示或原始响应，只在完全校验后保存结构化根因记录。模型不能指定 Root Cause ID；排名、字段边界、重复候选和 Evidence 引用均由本地验证，无效响应最多重试一次。

## 7. Evidence-bound Patch

`PatchGenerationService` 只接受已验证根因。模型可返回摘要、unified diff、Evidence 引用和非权威安全说明；以下内容全部由本地生成或重算：

- Patch ID；
- canonical diff SHA-256；
- 修改文件集合；
- 安全检查结果。

`PatchSafetyValidator` 拒绝 Markdown 围栏、二进制、删除、重命名、复制、模式变化、缺失 Hunk、重复路径、路径穿越、允许根外路径和保护文件。每个目标文件必须同时存在对应的 `SOURCE` Evidence，resolve 后不能逃离源码根，也不能是符号链接。

导入和详情读取会再次运行同一策略，不信任归档中自报的安全结论。

## 8. 人工批准与隔离验证

验证入口在任何 Docker 操作前比较当前胶囊中的完整 Patch ID、Patch SHA-256、用户提交的批准 SHA-256 和明确批准布尔值。Verification ID 由这些绑定内容派生。

验证器复制 before/after 两个临时工作区，只在 after 中先执行 `git apply --check` 再应用 diff。两个副本以只读挂载进入锁定验证镜像，容器配置包括：

- 非 root UID；
- `network=none`；
- `cap-drop=ALL`；
- `no-new-privileges`；
- 只读根文件系统和工作区；
- 独立临时 `/tmp`；
- CPU、内存、PID 和超时限制。

固定回归的成功条件是 before 非零退出、after 零退出且均未超时。原始输出再次脱敏，随后连同退出码、耗时和 SHA-256 写回 `verification/`。主工作区目标文件在执行前后做摘要对照。

## 9. CLI、Web 与报告

Typer CLI、Jinja2/HTMX Web 和 `HtmlReportService` 都读取 `CapsuleSummary`、`CapsuleDetail` 与 `EvidenceChain`。共享视图模型只做标签和格式化，不创建新状态。

Web 只允许 `127.0.0.1` 或 `localhost`，验证 Host 与写请求 Origin。HTMX 和 CSS 均本地提供，不依赖 CDN。上传同时受请求大小、ZIP 安全和胶囊完整性校验保护；相同 `capsule_id` 的不同字节不会覆盖已有归档。

HTML 报告只在分析、Patch 和完整 before/after 验证均存在时生成。模板自动转义不可信文本，内联 Design System CSS，不包含脚本、远程字体或图片，并以严格 CSP、`nosniff`、`no-store` 和附件响应交付。

## 10. 基准与发布

`benchmarking/dataset.json` 是 12 个仿真案例的版本化输入。生成器从标注确定性派生 Trace、Git、Evidence 和归档字节；评测器通过正式 `AnalysisService` 执行，并把失败案例保留在分母。Replay 与 Live 报告分别发布。

CI 在 Python 3.10–3.12 运行完整质量门禁；Docker 作业实测主演示以及修复前 20/20 失败、修复后 20/20 通过；供应链作业生成 wheel、sdist、CycloneDX SBOM、依赖审计和 SHA-256 清单。

## 11. 非目标与残余边界

0.1 不提供多租户、远程 Agent、IDE 插件、Kubernetes、向量数据库、生产 APM 或自动提交代码。Docker Engine 与宿主内核仍是信任基础；正则脱敏不能识别所有业务专有秘密；人工批准和固定回归不能替代完整代码审查。详细分析见[威胁模型](threat-model.md)。
