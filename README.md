<p align="center"><img src="docs/assets/brand/bugcapsule-banner.svg" width="100%" alt="BugCapsule 项目横幅：运行时证据驱动的开源 AI 调试工具"></p>

<p align="center"><img src="docs/assets/brand/bugcapsule-app-icon.svg" width="112" height="112" alt="BugCapsule 应用图标"></p>

<h1 align="center">BugCapsule</h1>

<p align="center"><strong>把一次故障封装成可移交、可引用、可验证的证据胶囊。</strong></p>

<p align="center"><a href="README.en.md">English</a> · <a href="https://gitee.com/lan0811/bug-capsule">Gitee 主仓</a> · <a href="https://github.com/lanlan0811/BugCapsule">GitHub 镜像</a> · <a href="docs/submission-evidence.md">评审证据</a></p>

<p align="center"><code>0.1.0 开发中</code> <code>Apache-2.0</code> <code>Python 3.10–3.12</code> <code>本地优先</code> <code>无 CDN</code></p>

## 项目定位

BugCapsule 是一款以运行时证据为核心、能够验证修复结果的开源 AI 调试工具。它把 Trace、日志、Stack Trace、源码窗口、Git 状态、根因候选、Patch 和回归结果组织成可校验的 `.bugcapsule` 归档，让每个结论都能回到本次故障中的具体 `Evidence ID`。

它解决的不是“让模型直接改代码”，而是建立一条受约束的工程闭环：

![BugCapsule 从故障注入到隔离验证的证据约束流程](docs/assets/brand/bugcapsule-workflow.svg)

主演示聚焦一个真实、可重复的场景：FastAPI 订单服务因异常路径保留 SQLAlchemy Session，固定为 2 的 PostgreSQL 连接池在第三次请求稳定返回 `HTTP 503 / database_pool_exhausted`。

## 技术栈

所有图标均为仓库内 SVG，不依赖 CDN 或远程徽章服务。

<table align="center">
  <tr>
    <td align="center"><img src="docs/assets/tech/python.svg" width="64" alt="Python"><br><sub>Python 3.10–3.12</sub></td>
    <td align="center"><img src="docs/assets/tech/fastapi.svg" width="64" alt="FastAPI"><br><sub>FastAPI</sub></td>
    <td align="center"><img src="docs/assets/tech/postgresql.svg" width="64" alt="PostgreSQL"><br><sub>PostgreSQL</sub></td>
    <td align="center"><img src="docs/assets/tech/sqlalchemy.svg" width="64" alt="SQLAlchemy"><br><sub>SQLAlchemy 2</sub></td>
    <td align="center"><img src="docs/assets/tech/opentelemetry.svg" width="64" alt="OpenTelemetry"><br><sub>OpenTelemetry</sub></td>
  </tr>
  <tr>
    <td align="center"><img src="docs/assets/tech/docker.svg" width="64" alt="Docker"><br><sub>Docker Compose</sub></td>
    <td align="center"><img src="docs/assets/tech/pydantic.svg" width="64" alt="Pydantic"><br><sub>Pydantic</sub></td>
    <td align="center"><img src="docs/assets/tech/typer.svg" width="64" alt="Typer"><br><sub>Typer CLI</sub></td>
    <td align="center"><img src="docs/assets/tech/htmx.svg" width="64" alt="HTMX"><br><sub>Jinja2 + HTMX</sub></td>
    <td align="center"><img src="docs/assets/brand/bugcapsule-app-icon.svg" width="64" alt="BugCapsule"><br><sub>开放 Capsule</sub></td>
  </tr>
</table>

## 为什么是“证据胶囊”

| 传统 AI 修复风险 | BugCapsule 的确定性约束 |
| --- | --- |
| 根因描述无法回溯 | 每个根因候选只能引用本次模型输入中存在的 `Evidence ID` |
| 模型输出任意文件修改 | 只接受 canonical unified diff，并检查允许根、保护路径和源码证据绑定 |
| 用户确认后内容可能变化 | Patch ID、完整 SHA-256 与明确批准三重绑定 |
| Patch 直接污染工作区 | 只在临时 before/after 副本中应用，主仓文件执行前后做哈希对照 |
| 验证命令受模型控制 | 固定回归由项目配置，模型不能生成或覆盖命令 |
| 在线模型不可用就无法演示 | `live`、`replay`、`off` 三种模式边界明确，回放不会冒充实时推理 |

## 十分钟快速开始

### 1. 准备环境

- Windows 10/11、Linux 或 macOS；
- Python 3.10–3.12；
- [uv](https://docs.astral.sh/uv/)；
- Docker Desktop 或 Docker Engine + Compose v2（主演示与隔离验证需要）。

### 2. 安装与诊断

```powershell
Copy-Item .env.example .env
uv sync --frozen --group dev
uv run bugcapsule --version
uv run bugcapsule doctor
```

配置只从 `.env` 或 `BUGCAPSULE_*` 环境变量读取；`.env` 已被 Git 忽略。字段说明见 [`.env.example`](.env.example)。`doctor` 是只读诊断，不创建目录、不启动容器，也不输出密钥原文。

### 3. 启动 Web

```powershell
uv run bugcapsule serve
```

打开 `http://127.0.0.1:8765`。健康检查为 `GET /healthz`，OpenAPI 文档为 `/api/docs`。服务默认只监听本机回环地址。

### 4. 运行 PostgreSQL 主场景

```powershell
uv run bugcapsule demo up
uv run bugcapsule demo run
uv run bugcapsule demo capture
uv run bugcapsule demo reset
uv run bugcapsule demo down
```

`demo run` 断言固定的 `500 → 500 → 503` 序列；`demo capture` 从命名卷受控同步脱敏 JSONL，校验大小、格式和 Trace ID 后生成胶囊。Web 的“同步并捕获”使用同一控制器。

## 从证据到验证

### 捕获与查询

```powershell
uv run bugcapsule capture --trace-id <32位Trace-ID>
uv run bugcapsule index rebuild
uv run bugcapsule capsules list --query demo-order-api
uv run bugcapsule capsules show <capsule-id>
```

胶囊文件是权威事实源；SQLite 只保存可重建元数据索引。导入时会重新验证 Schema、ZIP 安全边界和逐文件 SHA-256。

### 根因与 Patch

```powershell
uv run bugcapsule analyze <capsule-id> --mode replay
uv run bugcapsule patch generate <capsule-id> --mode replay
```

启用 `live` 前，在 `.env` 配置 OpenAI-compatible 提供方：

```dotenv
BUGCAPSULE_MODEL_MODE=live
BUGCAPSULE_MODEL_API_STYLE=responses
BUGCAPSULE_MODEL_BASE_URL=https://api.openai.com/v1
BUGCAPSULE_MODEL_API_KEY=replace-with-your-key
BUGCAPSULE_MODEL_NAME=replace-with-model-name
```

模型只接收经过脱敏、排序和字节预算限制的证据包。响应必须通过严格 Schema；未知证据引用只重试一次，随后返回可解释错误。

### 人工批准与隔离回归

```powershell
uv run bugcapsule verify <capsule-id> `
  --patch-id <patch-id> `
  --approved-sha256 <完整64位SHA-256> `
  --approve

uv run bugcapsule report <capsule-id> --output .\verification-report.html
```

验证容器使用非 root 用户、无网络、只读挂载、`cap-drop=ALL`、`no-new-privileges` 以及 CPU、内存、PID、临时目录和超时限制。报告是自包含 HTML，不加载远程脚本、字体或图片，可断网审阅和打印。

## 开放 `.bugcapsule` 格式

`.bugcapsule` 是确定性 ZIP 交换格式，Schema 从 `0.1.0` 开始。归档包含清单、Trace/日志/源码证据、脱敏报告，以及按执行状态写入的分析、Patch 和验证产物。`manifest.json` 为每个成员记录 SHA-256；Evidence ID 由规范化内容派生。

详细字段、完整性规则和兼容策略见 [Capsule Schema](docs/capsule-schema.md)。仓库提供一个[可直接导入的仿真胶囊](examples/README.md)。

## 已验证证据

| 项目 | 当前可复核事实 |
| --- | --- |
| 自动化测试 | 本机 195 项通过，分支覆盖率 90.82% |
| Python 兼容性 | GitHub CI 在 Python 3.10、3.11、3.12 全部通过 |
| Docker 主场景 | CI 实测 HTTP 就绪、`500/500/503`、池耗尽标识与 reset |
| 修复稳定性 | 受限容器内修复前 20/20 失败，修复后 20/20 通过 |
| 仿真评测 | 12/12 注释回放；Top-1、引用有效率、必需证据覆盖率均为 100% |
| 供应链 | 生产 SBOM 48 个组件，审计 47 个哈希冻结依赖，零已知漏洞 |
| 提交材料 | 8 页项目 PDF、180 秒镜头表、提交清单和 Release 阻断门禁已生成 |

注释回放指标只证明确定性管线和评分器，不代表 Live 模型能力。完整证据及 CI 运行链接见[参赛评审证据索引](docs/submission-evidence.md)。

## 安全边界

- 默认脱敏 Authorization、Cookie、Token、连接串、邮箱、手机号和常见密钥格式；
- 不持久化原始提示、原始模型响应或秘密原文；
- 导入限制成员数量、单文件大小、总解压大小、压缩比、路径和成员类型；
- Patch 拒绝路径穿越、二进制、删除、重命名、复制、模式变化和保护文件修改；
- 验证器不挂载 Docker Socket、宿主密钥、用户目录或可写主仓；
- 安全问题请按 [SECURITY.md](SECURITY.md) 私下报告，不要先公开 Issue。

完整资产、信任边界、攻击面和残余风险见[威胁模型](docs/threat-model.md)。

## 项目结构

```text
src/bugcapsule/          主程序：胶囊、索引、分析、Patch、验证、Web
verification_tests/     只读固定回归与修复夹具
tests/                  单元、集成、契约和安全测试
docs/                   架构、Schema、威胁模型、评测与交付文档
examples/               可复核的仿真胶囊
output/                 PDF、视频计划、试用和提交材料
.design_library/        BugCapsule Design System
```

## 文档导航

| 主题 | 文档 |
| --- | --- |
| 系统设计 | [架构](docs/architecture.md) · [Capsule Schema](docs/capsule-schema.md) · [威胁模型](docs/threat-model.md) |
| 验证与评测 | [基准数据集](docs/benchmark.md) · [可用性验收](docs/usability-study.md) · [路线图](docs/roadmap.md) |
| 发布与提交 | [供应链](docs/supply-chain.md) · [评审证据](docs/submission-evidence.md) · [最终材料清单](output/submission/README.md) |
| 演示资产 | [示例胶囊](examples/README.md) · [录制手册](docs/demo-runbook.md) · [项目 PDF](output/pdf/README.md) |
| 社区治理 | [贡献指南](CONTRIBUTING.md) · [安全策略](SECURITY.md) · [行为准则](CODE_OF_CONDUCT.md) · [变更记录](CHANGELOG.md) |

## 当前状态

BugCapsule 仍处于 `0.1.0` 开发状态。Linux Docker CI、开源治理、PDF 和可重复演示计划已完成；以下结果必须来自真实外部执行，仓库不会用占位文件或估算值冒充：

1. 比赛默认 Live 模型的独立量化评测；
2. 3–5 名首次使用者的匿名汇总；
3. Windows Docker 三次录制彩排与最终 MP4；
4. 全部门槛清零后的 `v0.1.0` 双平台 Release。

## 贡献与许可

Gitee 是主仓、Issue 和贡献入口；GitHub 是同步镜像。提交前请阅读 [CONTRIBUTING.md](CONTRIBUTING.md)，并运行完整质量门禁。

项目作品版权归属：Copyright © 2026 **lan0811 与 BugCapsule contributors**。初始开发者与维护者为 **lan0811**。

BugCapsule 原创源代码、文档与视觉资产基于 [Apache License 2.0](LICENSE) 开源；第三方组件版权与许可见 [THIRD_PARTY_NOTICES](THIRD_PARTY_NOTICES) 和 [NOTICE](NOTICE)。
