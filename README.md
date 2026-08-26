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

## 数据库连接池故障演示

先复制环境模板并替换其中的本地演示密码，然后启动 PostgreSQL 与订单服务：

```powershell
Copy-Item .env.example .env
docker compose up --build --detach
curl.exe http://127.0.0.1:8766/healthz
```

订单服务的 SQLAlchemy 连接池默认固定为 `pool_size=2`、`max_overflow=0`。连续执行三次故障请求：

```powershell
curl.exe -X POST http://127.0.0.1:8766/demo/leak
curl.exe -X POST http://127.0.0.1:8766/demo/leak
curl.exe -X POST http://127.0.0.1:8766/demo/leak
```

前两次请求在注入的异常路径中保留数据库 Session，第三次返回 `503` 与 `database_pool_exhausted`。可查询并重置确定性状态：

```powershell
curl.exe http://127.0.0.1:8766/demo/status
curl.exe -X POST http://127.0.0.1:8766/demo/reset
docker compose down
```

所有端口只映射到宿主机 `127.0.0.1`。订单容器以非 root 用户、只读根文件系统、移除 Linux capabilities 且启用 `no-new-privileges` 运行。

## 质量检查

```powershell
uv run ruff check .
uv run ruff format --check .
uv run mypy
uv run pytest
```

依赖解析结果提交在 `uv.lock`；CI 在 Python 3.10、3.11 和 3.12 上使用冻结锁文件执行同一组检查。

## 项目原则

- 证据优先：模型结论必须引用胶囊内已存在的 `evidence_id`。
- 人工确认：验证请求必须同时包含 Patch ID、Patch SHA-256 和明确批准标记。
- 安全隔离：Patch 只进入受限临时副本，不修改主仓库。
- 离线可演示：Web 使用 Jinja2 + HTMX，不依赖 CDN 或前端构建服务。
- 可访问表达：状态由文字、形态和 SVG 符号共同表达，不单独依赖颜色。

## 文档与治理

- [英文简介](README.en.md)
- [贡献指南](CONTRIBUTING.md)
- [安全策略](SECURITY.md)
- [行为准则](CODE_OF_CONDUCT.md)
- [变更记录](CHANGELOG.md)

本项目基于 [Apache License 2.0](LICENSE) 开源。
