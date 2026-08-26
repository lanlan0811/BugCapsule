# 变更日志

本文件记录 BugCapsule 的用户可见变化。项目遵循[语义化版本](https://semver.org/lang/zh-CN/)；`0.1.0` 正式标签尚未创建，以下内容均属于未发布版本。

## [未发布]

### 新增

- 建立 Python 3.10–3.12 工程、冻结 `uv.lock`、Typer CLI、FastAPI Web、SQLite 索引和多版本 CI。
- 实现 FastAPI + PostgreSQL 固定双连接池主演示，稳定复现 `500 → 500 → 503` 泄漏耗尽并支持 reset。
- 实现 OpenTelemetry Trace/Span、Trace Context 日志、Stack Trace、源码窗口、Git、依赖与环境捕获。
- 定义开放 `.bugcapsule` 0.1.0 Schema、内容派生 Evidence ID、确定性 ZIP、逐文件 SHA-256 和安全导入限制。
- 添加递归默认脱敏、无秘密原文审计、证据优先级、因果时间线和候选源码关联。
- 提供 `live`、`replay`、`off` 分析模式，严格校验结构、输入预算、Evidence 引用和精确回放身份。
- 实现 Evidence-bound Patch：canonical unified diff、允许根、保护路径、源码 Evidence 绑定和安全二次校验。
- 实现 Patch ID、完整 SHA-256、明确批准三重绑定，以及无网络、非 root、只读、资源受限的 Docker before/after 验证。
- 生成与 CLI/Web 同源的自包含 HTML 对比报告，无脚本、无外链并带严格交付安全头。
- 提供 12 个版本化仿真案例、确定性胶囊生成、Replay/Live 独立评测和三段 P50/P95 指标。
- 在 Docker CI 中完成主演示实测和修复前 20/20 失败、修复后 20/20 通过的隔离回归。
- 添加 `doctor` 诊断、3–5 名首次使用者匿名验收协议、180 秒镜头表和三轮 Windows 彩排门禁。
- 添加 Apache-2.0 治理文件、CycloneDX 1.6 SBOM、哈希依赖审计、wheel/sdist 完整性检查和标签 Release 门禁。
- 提供可导入仿真示例胶囊、8 页中文项目 PDF、评审证据索引和八类最终提交材料清单。
- 新增本地 SVG 品牌系统：BugCapsule 专属横幅、应用图标和九枚技术栈图标。

### 变更

- 新增中英双语商业使用与再分发声明，明确 Apache-2.0 允许商用和闭源衍生作品，同时列出分发时的许可证、修改标记、归属与 NOTICE 义务。
- 明确 BugCapsule 项目作品、初始开发者与维护者的版权归属，并在中英文 README 同步版权声明。
- 将项目定位中的纯文本闭环替换为仓库内 Mermaid 风格 SVG 流程图，展示故障注入、证据胶囊、Evidence-bound Patch、人工批准和隔离验证。
- 重写中英文 README；横幅置于应用图标上方，并以本地 SVG 展示技术栈、架构边界、快速开始和已验证指标。
- 重写架构、Capsule Schema、威胁模型、基准、供应链、路线图、治理和参赛交付文档，统一事实来源、状态口径与复核命令。
- Gitee 作为主仓和协作入口，GitHub 作为同步镜像与 CI/Release 展示面。

### 修复

- 修复 Linux CI 中 ANSI CLI 帮助断言和非 root 验证容器无法遍历临时目录的问题。
- 修复只读订单容器运行 `uv`、命名卷目录缺少非 root 写权限和 Compose 失败诊断问题。
- 修复 Compose 仅等待容器 running、未等待 Uvicorn HTTP 就绪造成的首请求竞态。
- 修复服务只连内部网络时宿主 `localhost` 端口不可达；PostgreSQL 继续留在内部网络。
- 为主演示耗尽断言保留容器状态、服务日志和原始退出码，便于远端复核。

### 安全

- 胶囊导入拒绝路径穿越、符号链接、重复/未知成员、加密成员、异常压缩比和超限内容。
- 模型输出不能控制本地标识、命令、路径策略或批准；未知 Evidence 引用最多重试一次后失败。
- Patch 不直接应用主工作区，验证前后核对目标摘要，容器不挂载 Docker Socket 或宿主秘密。
- Web 仅允许 loopback，执行 Trusted Host 与写请求 Origin 校验；HTML 报告自动转义且不加载外部资源。

### 发布状态

- 已验证：完整代码闭环、195 项测试门禁、12 案例 Replay 评测、Docker CI 稳定性回归、PDF 和供应链生成链路。
- 外部待完成：比赛 Live 模型评测、3–5 名独立首次使用者、Windows 三轮录制彩排、最终 MP4 与正式 `v0.1.0` Release。
- 未完成项不会用占位文件或估算数据标记为完成。

[未发布]: https://gitee.com/lan0811/bug-capsule/commits/master
