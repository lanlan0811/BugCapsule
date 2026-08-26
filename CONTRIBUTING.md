# 为 BugCapsule 做贡献

BugCapsule 接受缺陷修复、测试、文档、安全加固和范围明确的功能贡献。0.1 阶段的核心约束是：胶囊是事实源，分析必须引用 Evidence，Patch 必须经过确定性安全校验，执行前必须人工批准并进入隔离验证。

## 1. 协作入口

Gitee 是主仓库及 Issue、Pull Request 的唯一入口：

- 仓库：<https://gitee.com/lan0811/bug-capsule>
- Issues：<https://gitee.com/lan0811/bug-capsule/issues>
- Pull Requests：<https://gitee.com/lan0811/bug-capsule/pulls>

GitHub 仅作同步镜像。安全漏洞不要提交公开 Issue，请按 [安全策略](SECURITY.md) 私密报告。

## 2. 开发环境

支持 Python 3.10–3.12；主演示和 Patch 验证还需要 Docker Desktop/WSL2 或兼容 Docker Engine。Windows 使用 PowerShell，敏感配置只写入未跟踪的 `.env`。

```powershell
git clone https://gitee.com/lan0811/bug-capsule.git
Set-Location bug-capsule
Copy-Item .env.example .env
uv sync --frozen --group dev
uv run bugcapsule doctor
```

不要修改锁文件来绕过安装失败。依赖确需变更时，必须说明原因、最小化范围，并同步评审 SBOM 和第三方许可影响。

## 3. 选择改动范围

先搜索现有 Issue。下列变更必须在实现前讨论：

- Capsule Schema、Evidence ID 或归档兼容性；
- 公开 CLI、Web 路由或配置变量；
- 脱敏、安全策略、保护路径或验证隔离；
- 运行时/开发依赖、容器和 CI；
- 超出 0.1 路线图的产品能力。

一个 Pull Request 只解决一个清晰问题。建议分支命名为 `feat/<topic>`、`fix/<topic>`、`docs/<topic>`、`test/<topic>` 或 `refactor/<topic>`。

## 4. 实现不变量

- 不硬编码凭据、端口、模型或机器路径；配置放入环境变量，并更新 `.env.example`。
- 不在源码、测试夹具、胶囊、截图或日志中提交真实秘密和个人数据。
- 不使用模型输出决定命令、允许路径、ID、摘要或批准结果。
- 不让 Patch 修改测试、依赖锁、Docker、CI 或允许根外文件。
- 新增证据字段时同步更新 Schema、脱敏规则、威胁模型和正反测试。
- UI 图标使用仓库内 SVG，不使用 emoji、CDN、远程字体或运行时外链资源。
- 公开格式保持向后兼容；不可兼容变更必须升级版本并提供迁移说明。

## 5. 质量门禁

提交前运行完整门禁：

```powershell
uv run ruff check .
uv run ruff format --check .
uv run mypy
uv run pytest
```

涉及 Docker 主演示时，额外执行：

```powershell
uv run bugcapsule demo up
uv run bugcapsule demo run
uv run bugcapsule demo capture
uv run bugcapsule demo reset
uv run bugcapsule demo down
```

测试应覆盖成功、拒绝和边界路径。安全相关更改至少包含可证明控制有效的负例；文档或产物变更要检查相对链接、SHA-256、机器清单和渲染结果。

## 6. 提交 Pull Request

PR 描述必须包含动机、改动边界、风险和实际验证结果，并关联 Issue。提交前确认：

- 工作区无调试残留、秘密、真实业务数据或未声明第三方资产；
- 测试与文档和代码一起更新；
- `CHANGELOG.md` 记录用户可见变化；
- 生成式 AI 辅助内容已由贡献者逐项审查，来源和许可证清晰；
- 作者有权按 Apache-2.0 贡献代码、文档、测试和素材。

除非另有书面声明，被项目接受的有意贡献依照 [Apache License 2.0](LICENSE) 第 5 节授权，不附加额外条款。
