# BugCapsule 0.1 路线图与发布门槛

路线图以开发计划为范围依据，以仓库、测试和 CI 事实为完成依据。状态只使用“已完成、进行中、外部待完成”，不以计划日期或占位文件替代验收。

## 1. 里程碑状态

| 阶段 | 交付目标 | 当前状态 | 主要证据 |
| --- | --- | --- | --- |
| 1 | Python/CI 骨架、PostgreSQL 故障与 Docker 基线 | 已完成 | `pyproject.toml`、`compose.yml`、CI |
| 2 | OpenTelemetry、默认脱敏、开放胶囊导入导出 | 已完成 | `capsule/`、Schema、安全测试 |
| 3 | 证据关联、SQLite 索引、CLI 与 Web | 已完成 | `index.py`、Jinja2/HTMX 页面 |
| 4 | OpenAI-compatible 分析与 Evidence-bound Patch | 已完成 | `analysis/`、`patching/` |
| 5 | SHA-256 批准、隔离前后回归、自包含报告 | 已完成 | `verification/`、`reporting/` |
| 6 | 12 案例评测、20 次稳定性、启动诊断、外部试用 | 进行中 | Replay 与 Docker CI 已完成；3–5 人试用和 Live 评测待完成 |
| 7 | 治理、SBOM、双语文档、提交清单与 Release | 进行中 | 治理和供应链已自动化；正式 Release 待完成 |
| 8 | 冻结回归、PDF、Windows 彩排与最终视频 | 进行中 | PDF 和 180 秒录制包已完成；彩排与 MP4 待完成 |

## 2. 已闭合的工程门槛

- Python 3.10、3.11、3.12 冻结依赖质量门禁；
- Linux Docker 主场景 HTTP 就绪、`500/500/503` 与 reset；
- 受限容器内修复前 20/20 失败、修复后 20/20 通过；
- 197 项本机测试与 90.82% 分支覆盖率；
- 12 个版本化仿真案例与 Replay 评测；
- CycloneDX 1.6 SBOM、哈希锁定依赖审计、wheel/sdist 和 SHA-256 清单；
- 中英文 README、架构、Schema、威胁模型和治理文件；
- 8 页项目 PDF、180 秒镜头表、彩排门禁和八类提交清单；
- Gitee 主仓与 GitHub 镜像 `master` 同步。

## 3. `v0.1.0` 外部待完成门槛

| 门槛 | 完成证据 | 当前状态 |
| --- | --- | --- |
| Live 模型评测 | 独立 `benchmark-live/evaluation.json`，含 provider、model、标注哈希和完整 12 案例 | 外部待完成 |
| 首次使用者 | 3–5 名未参与开发者的 `output/usability/summary.json` | 外部待完成 |
| Windows 录制彩排 | 绑定冻结提交的三轮 `rehearsal-summary.json`，至少一次断网 | 外部待完成 |
| 最终视频 | 实际 3–5 分钟 MP4，完成哈希和断网兜底复核 | 外部待完成 |
| 正式 Release | Gitee/GitHub 同一提交的 `v0.1.0`，附供应链包与校验和 | 外部待完成 |

## 4. 冻结规则

代码冻结后只允许修复阻塞发布、安全或可复现性的缺陷；不升级依赖、不增加场景、不改变 Schema。每次冻结期变更必须重新执行完整测试、Docker CI、提交清单和受影响的录制彩排。

发布前运行：

```powershell
uv run ruff check .
uv run ruff format --check .
uv run mypy
uv run pytest
uv run python scripts/validate_demo_plan.py
uv run python scripts/validate_submission_manifest.py --require-ready
```

最后一条在任何外部交付缺失、状态未验证或 `release_commit` 未冻结时必须失败。

## 5. 0.2 以后

0.1 完成后再评估新的故障类型、跨语言采集、IDE 集成或远程 Agent。任何扩展都必须保留开放胶囊、Evidence 引用、人工批准和隔离验证四个核心边界；未经 0.1 真实用户与 Live 评测验证，不提前扩大范围。
