# 参赛评审证据索引

本页把大赛开发计划中的四个评分维度映射到仓库可复核事实。它不是宣传清单：`已验证` 只表示仓库内测试或本机命令已经完成；需要 Docker CI、独立参与者、模型提供方、远端镜像或正式标签的事项会保留为待完成。

机器可读版本位于 [`submission-evidence.json`](submission-evidence.json)，测试会校验四项权重合计 100%、状态枚举、相对路径安全性和每个证据文件是否存在。

## 状态口径

| 状态 | 含义 |
| --- | --- |
| 已验证 | 已由仓库测试、确定性命令或本机端到端流程复核 |
| 部分验证 | 单元/集成逻辑已验证，但指定外部运行环境尚未完成 |
| 外部待完成 | 依赖 Docker CI、首次使用者、Live 模型、远端同步或正式 Release，不能由开发者自测替代 |

## 技术创新（30%）

- 开放胶囊：[`capsule-schema.md`](capsule-schema.md)、`CapsuleManifest`、内容派生 Evidence ID、确定性 ZIP 与逐文件 SHA-256；仓库提供[可直接导入的仿真示例](../examples/README.md)。状态：已验证。
- 证据约束分析：根因引用必须来自本次模型输入，未知 Evidence ID 触发一次重试后明确失败；模型没有生成根因 ID 的权限。状态：已验证。
- Evidence-bound Patch：只接受 canonical unified diff，拒绝路径穿越、二进制、删除/重命名、保护路径和未被源码证据覆盖的文件。状态：已验证。
- 人工确认与隔离：Patch ID、完整 SHA-256、明确批准必须同时匹配；before/after 只进入临时副本和受限容器。状态：已验证。

最短复核命令：

```powershell
uv run pytest tests/capsule tests/analysis tests/patching tests/verification -o addopts=
```

## 场景落地（30%）

- FastAPI + PostgreSQL 使用 `pool_size=2`、`max_overflow=0`，前两次异常请求保留 Session，第三次稳定返回池耗尽；`demo capture` 受控同步命名卷证据并生成索引胶囊。逻辑、同步校验和状态机已验证；当前开发机缺少 Docker CLI，Compose 实机结果仍待 CI/外部环境确认。状态：部分验证。
- Trace、Span、日志、Stack Trace、源码、Git 和环境由同一 Trace Context 关联；SQLite 只是可重建索引，胶囊是事实源。状态：已验证。
- CLI、Jinja2/HTMX Web 与自包含 HTML 报告读取同一 `CapsuleDetail`，报告无外部脚本、字体或网络资源。状态：已验证。
- 12 案例仿真基准的注释回放实测 Top-1、引用有效率、Trace/日志/源码必需证据覆盖率均为 100%；该结果只证明确定性管线和评分器，不代表 Live 模型能力。状态：已验证。
- 修复前 20/20 失败、修复后 20/20 通过已写入受限 Docker CI；开发机尚未执行 Docker 实机。状态：外部待完成。

最短复核命令：

```powershell
uv run bugcapsule benchmark build --output .\benchmark-data
uv run bugcapsule benchmark run --mode replay --output .\benchmark-replay
uv run pytest
```

## 开源治理（20%）

- Apache-2.0 `LICENSE`、`NOTICE`、`THIRD_PARTY_NOTICES`、`SECURITY.md`、贡献指南和行为准则齐备。状态：已验证。
- [威胁模型](threat-model.md)明确资产、信任边界、攻击面、缓解措施和残余风险；脱敏报告不保存秘密原文。状态：已验证。
- [发布供应链](supply-chain.md)从纯生产环境生成 CycloneDX 1.6 SBOM，审计 47 个哈希冻结依赖，并校验 wheel、源码包和 SHA-256 清单。状态：已验证。
- 中文 README、英文快速开始、安全导向 Issue/PR 模板和公开路线图齐备。状态：已验证。
- [8 页项目介绍 PDF](../output/pdf/README.md)由锁定工具链确定性生成，附 SHA-256，并完成两轮逐页渲染 QA。状态：已验证。

## 长期发展（20%）

- 分层架构、版本化 Schema、模型适配协议、精确回放与公开路线图为后续扩展保留边界。状态：已验证。
- 3–5 名首次使用者试用必须按[可用性协议](usability-study.md)真实执行并发布匿名汇总；当前没有用开发者自测或估算填充结果。状态：外部待完成。
- Live 默认模型指标必须在实际提供方配置后单独发布，不能用注释回放替代。状态：外部待完成。
- GitHub 镜像同步、正式 `v0.1.0` 标签和 Gitee/GitHub Release 必须在全部发布门槛满足后完成。状态：外部待完成。

## 当前发布阻塞项

1. 在可用 Docker Engine 的环境确认 Compose 主场景、受限验证器和 20/20 前后回归；
2. 配置比赛采用的 Live 模型并独立发布 Live 指标；
3. 邀请 3–5 名首次使用者，按协议发布去标识汇总；
4. 完成 3–5 分钟演示视频和三分钟断网彩排；
5. 同步 GitHub 镜像并在代码冻结后创建同一提交的 `v0.1.0` Release。

阻塞项未清零前，仓库保持 `0.1.0` 开发状态，不创建正式标签。
