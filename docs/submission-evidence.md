# 上海开源软件应用创新大赛评审证据索引

本页将四项评分维度映射到可复核仓库证据。机器版本 [`submission-evidence.json`](submission-evidence.json)会校验权重合计 100%、状态、路径与命令。这里的“已验证”只表示代码、测试、确定性产物或远端 Docker CI 已有证据，不把 Replay、仿真数据或待录制材料描述成外部实测。

## 1. 状态定义

| 状态 | 判定标准 |
| --- | --- |
| 已验证 | 仓库测试、确定性命令、本地端到端或可定位 CI 已完成 |
| 部分验证 | 核心实现已验证，但指定外部环境或最终附件未完成 |
| 外部待完成 | 需要 Live 提供方、独立参与者、Windows 录制或正式 Release |

## 2. 技术创新（30%）

| 能力 | 可复核证据 | 状态 |
| --- | --- | --- |
| 开放胶囊 | [Schema](capsule-schema.md)、确定性归档、内容派生 Evidence ID、逐成员 SHA-256、[可导入示例](../examples/README.md) | 已验证 |
| 证据约束分析 | 严格根因 Schema、实际请求 Evidence 集合、未知引用拒绝、模型无权指定本地 ID | 已验证 |
| Evidence-bound Patch | canonical diff、允许根、保护路径、源码 Evidence 绑定、导入后二次校验 | 已验证 |
| 人工批准与隔离 | Patch ID + SHA-256 + 明确批准，before/after 临时副本和受限容器 | 已验证 |

```powershell
uv run pytest tests/capsule tests/analysis tests/patching tests/verification -o addopts=
```

## 3. 场景落地（30%）

| 结果 | 可复核证据 | 状态 |
| --- | --- | --- |
| 固定双连接池故障 | Compose、订单服务、控制器与 Docker CI 实测 `500/500/503` 和 reset | 已验证 |
| 一键证据捕获 | 命名卷受控同步、JSONL/Trace 校验、Trace 到源码因果链 | 已验证 |
| 统一事实呈现 | CLI、Jinja2/HTMX Web、自包含 HTML 共用 `CapsuleDetail` | 已验证 |
| 版本化评测 | 12 个仿真案例；Replay Top-1、引用有效率、必需证据覆盖均为 100% | 已验证，非 Live |
| 修复稳定性 | 受限 Docker 中 before 20/20 失败、after 20/20 通过 | 已验证 |

Docker 事实可在 GitHub Actions `CI / demo-integration` 复核；本地最短路径：

```powershell
uv run bugcapsule demo up
uv run bugcapsule demo run
uv run bugcapsule demo capture
uv run bugcapsule benchmark build --output .\benchmark-data
uv run bugcapsule benchmark run --mode replay --output .\benchmark-replay
```

## 4. 开源治理（20%）

- Apache-2.0 `LICENSE`、`NOTICE`、第三方声明、贡献指南、行为准则和私密安全披露齐备；
- [威胁模型](threat-model.md)覆盖资产、信任边界、控制证据、数据最小化和残余风险；
- [供应链流程](supply-chain.md)生成 CycloneDX 1.6 SBOM、47 个哈希冻结依赖审计、wheel/sdist 与校验和；
- 中英文 README、Issue/PR 模板和[公开路线图](roadmap.md)可直接用于协作；
- [8 页项目 PDF](../output/pdf/README.md)由锁定工具链生成并完成逐页渲染 QA；
- [180 秒录制包](../output/video/README.md)已有镜头、口播、证据和门禁，Windows 彩排与最终 MP4 尚待完成；
- [最终提交清单](../output/submission/README.md)覆盖八类材料，未完成项必须附阻塞原因。

## 5. 长期发展（20%）

- 分层架构、版本化 Schema、OpenAI-compatible 双 API 与 `live/replay/off` 为后续演进提供稳定边界；
- [3–5 名首次使用者协议](usability-study.md)及匿名汇总工具已经验证，已完成一份代操作试运行并据此修正文档与数据契约，正式独立样本仍为外部待完成；
- 比赛默认 Live 模型必须单独执行 12 案例评测，不得用 Replay 替代；
- Gitee `master` 与 GitHub 镜像同步，正式 `v0.1.0` 需在全部 Release 门槛通过后创建。

## 6. 当前发布阻塞项

1. 选定比赛 Live 模型并生成独立 Live 评测；
2. 邀请 3–5 名独立首次使用者并发布匿名汇总；
3. 在 Windows Docker 环境完成三轮彩排、至少一次断网验收和最终 MP4；
4. 冻结同一提交，创建 `v0.1.0` 标签并发布完整供应链附件。

阻塞项未清零前项目保持预发布状态，不创建空附件或伪造完成记录。
