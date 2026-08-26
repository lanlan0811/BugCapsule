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

### 说明

- 当前仓库处于 `0.1.0` 阶段一开发，已具备可运行的本地服务骨架。
- Docker 环境实机验收、SBOM、示例胶囊和正式 Release 尚未完成。

[未发布]: https://gitee.com/lan0811/bug-capsule/commits/master
