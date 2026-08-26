# 三分钟主演示运行手册

本手册是录制与现场路演的操作真源，时间线由 [`demo-shot-list.json`](../output/video/demo-shot-list.json) 机器校验。目标成片严格为 180 秒；比赛允许 3–5 分钟，但不以冗长等待占用评审时间。

## 演示口径

- 故障注入、Trace/日志捕获、胶囊生成与隔离验证必须来自实际 Docker 运行，画面不得用测试夹具冒充实机结果。
- 模型分析和 Patch 生成在正式录制中采用 `replay`，画面始终保留“replay · 结构化离线回放”状态；它证明可重复管线，不代表 Live 模型指标。
- Live 模型评测只在单独的 `benchmark-live` 报告中陈述，未完成时不口播模型准确率。
- 断网兜底只使用同一提交完成彩排后冻结的胶囊、HTML 报告和评测报告，不以旧材料替代当前发布证据。
- 屏幕中不得出现 `.env`、API Key、Authorization、Cookie、真实业务数据、用户目录或通知弹窗。

## 录制前一次性准备

在用于比赛的全新 Windows + Docker Desktop 环境执行：

```powershell
Copy-Item .env.example .env
# 仅在本地编辑 .env 中的演示密码和模型配置，不录屏、不提交。
uv sync --frozen --group dev
uv run bugcapsule doctor
uv run pytest
uv run bugcapsule demo up
uv run bugcapsule demo run
uv run bugcapsule demo capture
uv run bugcapsule demo reset
uv run bugcapsule benchmark build --output .\benchmark-data
uv run bugcapsule benchmark run --mode replay --output .\benchmark-replay
```

只有 `doctor.ready=true`、全量测试通过、故障序列为 `500 → 500 → 503` 且捕获后的胶囊可以打开时，才进入录制。录像使用 1920×1080、30 fps、浏览器 100% 缩放；系统通知、输入法浮窗与任务栏敏感信息全部关闭。

## 180 秒操作时间线

| 时间 | 操作 | 必须入镜的证明 |
| --- | --- | --- |
| 00:00–00:12 | 正常订单与 Trace | HTTP 201、连接池 ready、Trace Context |
| 00:12–00:28 | 点击“触发故障” | HTTP 500 → 500 |
| 00:28–00:42 | 定格第三次请求 | HTTP 503、`database_pool_exhausted` |
| 00:42–00:56 | 点击“同步并捕获”并打开胶囊 | 32 位 Trace ID、胶囊详情链接 |
| 00:56–01:18 | 展开证据时间线 | Trace、日志、源码 Evidence ID |
| 01:18–01:40 | 运行 replay 分析 | replay 徽标、根因引用 |
| 01:40–02:00 | 生成并检查 Patch | canonical Diff、路径策略、源码绑定 |
| 02:00–02:12 | 核对并批准 | Patch ID、完整 SHA-256、明确批准 |
| 02:12–02:42 | 运行隔离验证 | before failed、after passed、主仓未变 |
| 02:42–03:00 | 打开 HTML 报告与指标 | 自包含报告、12 案例、Replay/Live 边界 |

镜头切换、鼠标位置、口播逐句文本与仓库证据路径以 JSON 镜头表为准。校验命令：

```powershell
uv run python scripts/validate_demo_plan.py
```

## 现场模式

### 主路径：实际运行 + 结构化回放

开场前保持 Compose 服务健康、BugCapsule Web 位于 `/demo`、模型模式为 `replay`。正式操作从正常请求开始，故障与验证均实际执行；模型部分使用与本次胶囊请求摘要完全匹配的结构化回放记录。任何摘要不匹配都应中止，不临时切换成 Live。

### 断网路径：已彩排产物

网络中断不影响 Compose 内部网络、模型回放、自包含报告或本地 Web。若现场机器运行异常，切换到同一冻结提交在完整彩排后保存的胶囊与 HTML 报告，并明确口播“这是刚才同一流程的已验证离线产物”。不得把仿真示例的未运行状态说成 Docker 实测。

### 完全失败路径：视频回放

只有最终 MP4 已完成 SHA-256 校验且能在断网播放器中从头播放，才允许作为最后兜底。播放前一句说明现场环境异常；视频本身仍须保留 Docker 实机证明、replay 状态和指标边界。

## 彩排记录与通过门槛

正式录制前连续完成三次计时彩排。每次生成一条去敏记录，最终汇总写入尚未创建的 `output/video/rehearsal-summary.json`。严格字段由 `scripts/validate_rehearsal_summary.py` 定义：提交 SHA、Windows 与 Docker/Compose 版本、带时区起止时间、实际时长、联网/断网模式、Replay 披露、故障序列、胶囊/报告 SHA-256、before/after 退出码、主工作区不变、断网回放结果、枚举化观察代码和失败检查点。禁止自由文本操作者备注，避免路径、账号或设备信息进入仓库。

三次均通过后执行：

```powershell
uv run python scripts/validate_rehearsal_summary.py `
  --summary output/video/rehearsal-summary.json `
  --expected-commit <40位小写冻结提交SHA>
```

三次均满足以下条件才可将视频状态改为已验证：

1. 总时长在 175–185 秒内，最终剪辑精确为 180 秒；
2. 实际故障序列、胶囊完整性、Patch 批准绑定和 before/after 结果全部一致；
3. 主仓目标文件前后 SHA-256 不变；
4. 全程无密钥、真实数据、个人通知或未声明的 Live 模型口径；
5. MP4 断网完整播放，音频可辨，关键标识在 1080p 下可读。

当前开发机缺少 Docker CLI，且尚无正式屏幕录制，因此彩排汇总与 MP4 均保持“外部待完成”，不得创建空文件或伪造摘要。
