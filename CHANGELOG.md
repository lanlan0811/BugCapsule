# 变更日志

本文件记录 BugCapsule 的重要变更。项目遵循[语义化版本](https://semver.org/lang/zh-CN/)，并在 `0.1.0` 起尽量采用“新增、变更、弃用、移除、修复、安全”分类。

## [未发布]

### 新增

- 建立 Apache-2.0 许可证与项目 NOTICE。
- 添加中英文 Issue 和 Pull Request 模板。
- 添加贡献指南、社区行为准则、安全策略与第三方声明。
- 添加 `0.1.0` 目标架构、开放 Capsule Schema、威胁模型和路线图。
- 添加中英文项目介绍占位文档。
- 建立 Python 3.10–3.12 项目骨架、环境变量配置与本地 FastAPI 健康检查。
- 添加 Typer CLI、确定性 `uv.lock`、单元测试、覆盖率门禁和多版本 CI。
- 添加 FastAPI 订单服务、PostgreSQL Compose 环境和可重置的连接池耗尽故障路径。
- 添加非 root、只读文件系统、最小 capabilities 的订单服务容器基线。
- 实现 `bugcapsule demo up|run|reset|down`，安全编排容器并校验固定故障状态序列。
- 实现开放胶囊 0.1.0 核心 Schema、内容派生 Evidence ID、路径约束和证据引用校验。
- 添加胶囊格式、安全不变量与标识符规则文档。
- 添加递归默认脱敏引擎与不保留秘密原文的审计报告。
- 添加确定性 `.bugcapsule` 导出、安全导入、完整性校验与 ZIP 攻击限制。
- 接入 OpenTelemetry FastAPI/SQLAlchemy Span 与携带 Trace Context 的已脱敏 JSONL 日志。
- 实现 `capture --trace-id`，关联 Span、日志、Stack Trace、源码窗口、Git、依赖和环境并导出胶囊。
- 添加确定性证据优先级、Trace/Span 因果时间线与候选源码区域关联。
- 添加以胶囊为事实源的可重建 SQLite 元数据索引及 `index`、`capsules` CLI 查询。
- 添加遵循 BugCapsule Design System 的 Jinja2 + HTMX 故障列表、胶囊详情、证据链和演示控制页面。
- 添加本地胶囊安全导入、原始归档导出、同源请求校验和本地固定版本 HTMX 资源。
- 添加 OpenAI-compatible Responses/Chat Completions 适配器和 `live/replay/off` 模型模式。
- 添加有输入预算的脱敏证据请求、严格根因 Schema、无效响应单次重试和本地 Evidence ID 强校验。
- 添加结构化精确回放、原子分析产物写回、`analyze` CLI 与 Web 根因候选展示。
- 添加 evidence-bound Patch 生成、Patch 专用精确回放和 `patch generate` CLI/Web 操作。
- 添加严格 unified diff 解析、允许根/保护路径、源码 Evidence 绑定、工作区逃逸检查及导入时二次安全校验。
- 添加 Patch ID/SHA-256/明确批准三重绑定、before/after 临时副本和固定命令验证状态机。
- 添加非 root、无网络、只读挂载和资源受限的 Docker 验证器，以及验证日志二次脱敏与完整性校验。
- 添加与 Web/CLI 共用事实源的自包含 HTML 前后对比报告、确定性报告 SHA-256 与安全下载头。
- 添加 12 个版本化人工标注仿真案例及可确定性生成 `.bugcapsule` 的 `benchmark build` 命令。
- 添加支持注释回放与真实 Live 模型的 `benchmark run`，实测 Top-1、引用有效率、证据覆盖及三段 P50/P95。
- 添加受限容器内 20 次修复前/后稳定性回归，并隔离全仓覆盖率参数对固定回归退出码的干扰。
- 添加只读 `doctor` 启动诊断与匿名化首次使用者验收协议。
- 完成英文快速开始、公开威胁模型、0.1 路线图及 GitHub Issue/PR 模板。
- 添加生产依赖 CycloneDX 1.6 SBOM、哈希锁定漏洞审计、wheel/sdist 完整性校验与 SHA-256 发布清单。
- 添加受完整 CI 门禁保护的标签 Release 工作流和供应链复现文档。
- 提交可直接导入、带 SHA-256 且由测试绑定到版本化标注的连接泄漏仿真示例胶囊。
- 添加覆盖四项评分权重、仓库路径、复现命令和诚实完成状态的机器可校验评审证据索引。
- 添加遵循 Design System 的 8 页中文项目介绍 PDF、确定性 ReportLab 生成器、锁定产物工具链、SHA-256 与逐页视觉 QA 记录。
- 添加 Docker 命名卷证据受控同步、最新池耗尽 Trace 选择及 CLI/Web 一键胶囊捕获闭环。
- 添加机器可校验的 10 镜头/180 秒演示计划、录制运行手册、断网兜底与诚实状态门禁。
- 添加覆盖八类最终材料的提交清单、预期输出校验与正式标签 Release 阻断门禁。

### 说明

- 当前仓库处于 `0.1.0` 阶段七开发，已具备从捕获到隔离验证、HTML 报告和可审计发布包的工程闭环。
- Docker 环境实机验收、外部可用性验收和正式 Release 尚未完成。

### 修复

- 修复 Linux CI 中 ANSI CLI 帮助断言与非 root 验证容器无法遍历 0700 patched 临时目录的问题。
- 修复只读订单容器启动时运行 `uv` 和命名卷目录缺少非 root 写权限导致的退出问题，并补充 Compose 失败诊断。

[未发布]: https://gitee.com/lan0811/bug-capsule/commits/master
