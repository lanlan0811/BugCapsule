# BugCapsule

BugCapsule 是一款以运行时证据为核心、能够验证修复结果的开源 AI 调试工具。它把 Trace、日志、源码、Git 变更和测试结果组织成可校验的故障胶囊，使根因分析与修复建议都能回溯到具体证据。

> 当前版本：`0.1.0`（开发中）
>
> 主演示场景：FastAPI + PostgreSQL 数据库连接池耗尽
>
> 主仓库与 Issue：Gitee

## 核心闭环

```text
故障注入 → Trace / Log / 代码证据 → 故障胶囊
        → AI 根因与补丁 → 人工确认
        → 隔离回归 → 前后对比报告
```

BugCapsule 不会让模型直接修改主演示仓库。模型只提出带证据引用的 unified diff；补丁必须通过路径、安全和 SHA-256 确认检查，随后才能在隔离临时副本中验证。

## 开发环境

- Windows 10/11、Linux 或 macOS
- Python 3.10–3.12
- [uv](https://docs.astral.sh/uv/)
- Docker Desktop 或 Docker Engine（主演示场景需要）

## 本地安装

```powershell
Copy-Item .env.example .env
uv sync --frozen --all-groups
uv run bugcapsule --version
```

环境配置只从 `.env` 或 `BUGCAPSULE_*` 环境变量读取。`.env` 不进入 Git；可提交的字段说明位于 [`.env.example`](.env.example)。

## 启动本地服务

```powershell
uv run bugcapsule serve
```

默认地址为 `http://127.0.0.1:8765`，健康检查为 `GET /healthz`，OpenAPI 文档为 `/api/docs`。监听地址被限制为本机回环地址。

Web 界面提供故障列表、胶囊详情、证据链时间线和演示控制。页面使用 Jinja2 服务端渲染与本地固定版本 HTMX，不加载 CDN、外部字体或外部脚本：

```text
http://127.0.0.1:8765/capsules
http://127.0.0.1:8765/demo
```

可在顶栏导入经过大小、ZIP 安全、清单校验和证据关联校验的 `.bugcapsule`；同一 `capsule_id` 的不同内容不会覆盖已有文件。详情页可导出与索引对应的原始归档。

## 数据库连接池故障演示

先复制环境模板并替换其中的本地演示密码，然后启动 PostgreSQL 与订单服务：

```powershell
Copy-Item .env.example .env
uv run bugcapsule demo up
```

订单服务的 SQLAlchemy 连接池默认固定为 `pool_size=2`、`max_overflow=0`。运行一次完整、可重复的故障注入：

```powershell
uv run bugcapsule demo run
```

前两次请求在注入的异常路径中保留数据库 Session，第三次返回 `503` 与 `database_pool_exhausted`。可查询并重置确定性状态：

```powershell
curl.exe http://127.0.0.1:8766/demo/status
uv run bugcapsule demo reset
uv run bugcapsule demo down
```

所有端口只映射到宿主机 `127.0.0.1`。订单容器以非 root 用户、只读根文件系统、移除 Linux capabilities 且启用 `no-new-privileges` 运行。

### 运行时证据

订单服务默认启用 OpenTelemetry FastAPI 与 SQLAlchemy instrumentation。Trace 和标准日志在落盘前经过同一套脱敏规则，并分别写入：

```text
.bugcapsule-data/demo/traces.jsonl
.bugcapsule-data/demo/logs.jsonl
.bugcapsule-data/demo/redaction-findings.jsonl
```

每条故障日志携带与 HTTP/数据库 Span 一致的 `trace_id` 和 `span_id`。Docker 模式使用 `demo-telemetry-data` 命名卷保存这些证据。

从故障日志中取得 32 位 Trace ID 后，可生成开放胶囊：

```powershell
uv run bugcapsule capture --trace-id <trace-id>
```

输出位于 `.bugcapsule-data/capsules/`。捕获器只读取 `BUGCAPSULE_SOURCE_INCLUDE_ROOT` 指定目录中的源码窗口；归档包含 Span、日志、Stack Trace、相对源码片段、Git、依赖锁摘要、环境摘要和合并后的脱敏报告。

### 证据链与本地索引

`capture` 成功后会同步更新仅含元数据的 SQLite 索引。胶囊文件始终是事实源；索引可随时从已校验归档重建，损坏归档会被排除并在结果中明确列出：

```powershell
uv run bugcapsule index rebuild
uv run bugcapsule capsules list --query demo-order-api
uv run bugcapsule capsules show <capsule-id>
```

详情命令以确定性 JSON 输出胶囊清单、按优先级排列的证据和因果时间线。时间线通过 Trace ID、Span ID 与父 Span 关系关联 HTTP/数据库 Span、错误日志、Stack Trace 和候选源码区域，不依赖模型推断。

### 证据约束的模型分析

BugCapsule 支持三种显式模型模式：`live` 调用 OpenAI-compatible 接口，`replay` 按完整请求 SHA-256 读取本地录制结果，`off` 不发起网络请求。默认是 `off`。启用模型前在 `.env` 中配置：

```dotenv
BUGCAPSULE_MODEL_MODE=live
BUGCAPSULE_MODEL_API_STYLE=responses
BUGCAPSULE_MODEL_BASE_URL=https://api.openai.com/v1
BUGCAPSULE_MODEL_API_KEY=replace-with-your-key
BUGCAPSULE_MODEL_NAME=replace-with-model-name
```

也可将 `BUGCAPSULE_MODEL_API_STYLE` 设为 `chat_completions` 以适配相应兼容服务。运行分析：

```powershell
uv run bugcapsule analyze <capsule-id>
uv run bugcapsule analyze <capsule-id> --mode replay
```

模型输入只包含胶囊中已脱敏、按优先级选择且受字节上限约束的证据。响应必须通过严格 JSON Schema，并且每个根因候选引用的 Evidence ID 必须存在于本次请求；格式或引用无效时只重试一次。根因 ID 由本地根据内容生成，模型无权指定。验证后的结果写入 `analysis/root-causes.json`，回放目录只保留结构化结果，不保存原始提示或原始响应。

根因分析完成后，可生成只存入胶囊、不会应用到当前仓库的 Patch：

```powershell
uv run bugcapsule patch generate <capsule-id>
uv run bugcapsule patch generate <capsule-id> --root-cause-id <root-cause-id> --mode replay
```

模型只能提出 unified diff，Patch ID、SHA-256、修改文件清单和安全结论全部由本地生成。解析器拒绝 Markdown 围栏、二进制内容、删除、重命名、复制、模式变化、非规范 Hunk、路径穿越和重复文件；修改路径还必须同时位于 `BUGCAPSULE_PATCH_ALLOWED_ROOTS`、不匹配 `BUGCAPSULE_PATCH_PROTECTED_PATHS`、对应胶囊中的源码 Evidence，并且解析后不逃离 `BUGCAPSULE_SOURCE_ROOT`。测试、依赖锁和项目配置默认属于保护路径。

人工核对页面或 CLI 输出的完整 Patch ID 与 SHA-256 后，才可启动隔离验证：

```powershell
uv run bugcapsule verify <capsule-id> `
  --patch-id <patch-id> `
  --approved-sha256 <完整-64-位-sha256> `
  --approve
```

三项批准值必须同时匹配胶囊当前 Patch，失败时不会准备镜像或执行命令。验证器复制两个临时工作区，只把 Patch 应用于 after 副本；两个副本都以只读 bind mount 进入非 root Docker 容器，容器无网络、无 capabilities、启用 `no-new-privileges` 并限制 CPU、内存、PID、临时目录和超时。验证命令来自 `BUGCAPSULE_VERIFICATION_COMMAND`，不接受模型提供的命令。修复前后原始输出经过脱敏后连同退出码、耗时和 SHA-256 写回胶囊，主源码文件会在验证前后做哈希对照。

验证完成后，可从详情页下载自包含 HTML 报告，或通过 CLI 写入指定位置：

```powershell
uv run bugcapsule report <capsule-id> --output .\verification-report.html
```

报告只从重新校验后的 `CapsuleDetail` 生成，包含证据链、根因候选、canonical unified diff、安全检查、批准绑定、修复前后脱敏输出及归档完整性。它不加载外部脚本、样式、字体或图片，可断网查看和打印；默认拒绝覆盖现有文件，确需覆盖时显式传入 `--force`。

## 仿真基准数据集

构建随包发布的 12 个带人工标注胶囊：

```powershell
uv run bugcapsule benchmark build --output .\benchmark-data
uv run bugcapsule benchmark run --mode replay --output .\benchmark-replay
```

数据集平均覆盖连接泄漏、数据库不可达和慢查询，生成结果包含标注文件 SHA-256，且所有案例明确标记为仿真数据。评测输出逐案例事实及 Top-1、引用有效率、证据覆盖率和三段 P50/P95；`--mode live` 才代表当前配置模型，注释回放不会冒充在线模型能力。格式、评分口径和复现约束见[基准数据集文档](docs/benchmark.md)。

## 质量检查

```powershell
uv run ruff check .
uv run ruff format --check .
uv run mypy
uv run pytest
```

依赖解析结果提交在 `uv.lock`；CI 在 Python 3.10、3.11 和 3.12 上使用冻结锁文件执行同一组检查。

## 项目原则

- 证据优先：模型结论必须引用本次模型输入中已存在的 `evidence_id`。
- 人工确认：验证请求必须同时包含 Patch ID、Patch SHA-256 和明确批准标记。
- 安全隔离：Patch 只进入受限临时副本，不修改主仓库。
- 离线可演示：Web 使用 Jinja2 + HTMX，不依赖 CDN 或前端构建服务。
- 可访问表达：状态由文字、形态和 SVG 符号共同表达，不单独依赖颜色。

## 文档与治理

- [英文简介](README.en.md)
- [贡献指南](CONTRIBUTING.md)
- [安全策略](SECURITY.md)
- [基准数据集](docs/benchmark.md)
- [行为准则](CODE_OF_CONDUCT.md)
- [变更记录](CHANGELOG.md)

本项目基于 [Apache License 2.0](LICENSE) 开源。
