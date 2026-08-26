# BugCapsule 三分钟主演示运行手册

本手册是比赛录制与现场路演的操作真源。机器可读时间线位于 [`demo-shot-list.json`](../output/video/demo-shot-list.json)，严格覆盖 0–180 秒。所有画面必须来自同一冻结提交，不用占位文件、旧胶囊或测试夹具冒充现场结果。

## 1. 口径与红线

- 故障、证据同步、胶囊捕获和隔离验证来自实际 Docker 运行；
- 分析与 Patch 固定使用 `replay`，画面显示“replay · 结构化离线回放”；
- Replay 证明管线和评分器可重复，不代表 Live 模型能力；
- Live 指标仅在独立 `benchmark-live/evaluation.json` 完成后陈述；
- 断网兜底必须绑定冻结提交并通过完整彩排；
- 屏幕不得出现 `.env`、密钥、Authorization、Cookie、真实业务数据、用户目录或系统通知。

## 2. 冻结前准备

在录制用 Windows 10/11 与 Docker Desktop 环境执行：

先为录制中使用的同一胶囊生成分析和 Patch 的精确 Replay 记录。`.env` 中必须填写 Live 提供方、模型名和本机密钥；以下两个 Live 请求都成功后，再把 `BUGCAPSULE_MODEL_MODE` 改为 `replay`，但保持 `BUGCAPSULE_MODEL_PROVIDER`、`BUGCAPSULE_MODEL_NAME` 与 `BUGCAPSULE_REPLAY_DIR` 不变。新捕获的胶囊不会复用其他胶囊或基准案例的 Replay 记录。

```powershell
Copy-Item .env.example .env
# 仅在本机编辑 .env，不录屏、不提交。
uv sync --frozen --group dev
uv run ruff check .
uv run ruff format --check .
uv run mypy
uv run pytest
uv run bugcapsule doctor
uv run bugcapsule demo up
uv run bugcapsule demo run
uv run bugcapsule demo capture
uv run bugcapsule analyze <本轮胶囊ID> --mode live
uv run bugcapsule patch generate <本轮胶囊ID> --mode live
# 在 .env 中切换到 BUGCAPSULE_MODEL_MODE=replay 后验证精确命中：
uv run bugcapsule analyze <本轮胶囊ID> --mode replay
uv run bugcapsule patch generate <本轮胶囊ID> --mode replay
uv run bugcapsule demo reset
uv run bugcapsule benchmark build --output .\benchmark-data
uv run bugcapsule benchmark run --mode replay --output .\benchmark-replay
```

只有以下条件同时满足才可冻结提交：`doctor.ready=true`、完整质量门禁通过、故障序列为 `500 → 500 → 503`、新胶囊可导入、Replay 请求精确命中、验证为 before 失败/after 通过，且主工作区目标文件摘要未变化。

录制规格固定为 1920×1080、30 fps、浏览器 100% 缩放。关闭通知、输入法浮窗、密码管理器提示和包含个人信息的任务栏区域。

## 3. 180 秒镜头表

| 时间 | 操作 | 必须可见的证明 |
| --- | --- | --- |
| 00:00–00:12 | 展示健康状态与正常订单 | HTTP 201、pool ready、Trace Context |
| 00:12–00:28 | 连续触发两次泄漏 | HTTP 500 → 500、leaked sessions = 2 |
| 00:28–00:42 | 定格第三次请求 | HTTP 503、`database_pool_exhausted` |
| 00:42–00:56 | 同步证据并捕获胶囊 | 32 位 Trace ID、胶囊详情入口 |
| 00:56–01:18 | 展开因果时间线 | Trace、日志、源码 Evidence ID |
| 01:18–01:40 | 运行 Replay 分析 | replay 标识、根因与有效引用 |
| 01:40–02:00 | 生成并检查 Patch | canonical diff、允许路径、源码绑定 |
| 02:00–02:12 | 核对并批准 | 完整 Patch ID、64 位 SHA-256、明确批准 |
| 02:12–02:42 | 执行隔离验证 | before failed、after passed、workspace unchanged |
| 02:42–03:00 | 打开报告和评测摘要 | 自包含 HTML、12 案例、Replay/Live 边界 |

镜头动作、逐句口播、模式和仓库证据以 JSON 为准：

```powershell
uv run python scripts/validate_demo_plan.py
```

## 4. 现场运行顺序

1. 开场前确认 Compose 健康，Web 停在 `/demo`，模型模式为 `replay`；
2. 从正常请求开始，严格按镜头表执行，不跳过故障状态；
3. 捕获后只打开本轮新生成的胶囊；
4. Replay 摘要不匹配时中止，不临时切换 Live；
5. 批准前完整展示 Patch ID 和 SHA-256；
6. 验证后展示 before/after、容器限制与主仓不变；
7. 最后打开同一胶囊生成的自包含报告。

## 5. 断网与失败兜底

网络中断不影响 Compose 内部网络、结构化回放、本地 Web 或自包含报告。若现场实时操作异常，只能切换到同一冻结提交、同一轮彩排生成并已核对 SHA-256 的胶囊与报告，并明确说明“这是同一流程的已验证离线产物”。

最终 MP4 仅在完成 SHA-256 校验和断网全程播放后作为最后兜底。现场环境异常时先说明原因，再播放视频；视频仍须保留 Docker 实机证据、Replay 标识和指标边界。

## 6. 三轮彩排门禁

正式录制前连续完成三轮完整彩排，其中至少一轮断网。使用 `scripts/validate_rehearsal_summary.py` 定义的严格字段记录冻结提交、系统与 Docker 版本、带时区时间、时长、网络模式、故障序列、胶囊/报告 SHA-256、before/after 退出码、主工作区不变和断网播放结果。禁止自由文本操作者备注。

```powershell
uv run python scripts/validate_rehearsal_summary.py `
  --summary output/video/rehearsal-summary.json `
  --expected-commit <40位小写冻结提交SHA>
```

三轮都必须满足：175–185 秒、故障与批准绑定一致、before 非零、after 为零、主仓未变、屏幕无敏感数据，并至少一轮完成断网回放。最终剪辑严格为 180 秒。当前 `rehearsal-summary.json` 与 MP4 均为外部待完成；真实执行前不要创建空文件。
