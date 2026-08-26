# BugCapsule 演示视频交付

本目录当前交付机器可校验的录制方案，不包含占位 MP4。

| 资产 | 状态 | 验证含义 |
| --- | --- | --- |
| `demo-shot-list.json` | 已验证 | 10 个连续镜头严格覆盖 0–180 秒 |
| [`demo-runbook.md`](../../docs/demo-runbook.md) | 已验证 | 录制、口径、断网、彩排与失败兜底 |
| `rehearsal-summary.json` | 外部待完成 | 三轮真实 Windows Docker 彩排，至少一轮断网 |
| `BugCapsule_0.1_三分钟演示.mp4` | 外部待完成 | 实际 1080p 屏幕录制与 SHA-256，不创建空文件 |

## 1. 校验录制方案

```powershell
uv run python scripts/validate_demo_plan.py
```

校验器拒绝时间断点、重叠、非 180 秒结尾、重复镜头、缺失证据路径、未知模式，以及视频不存在却标记为已验证的状态。

## 2. 验收三轮彩排

真实彩排完成后，按[运行手册](../../docs/demo-runbook.md)生成严格 `rehearsal-summary.json`：

```powershell
uv run python scripts/validate_rehearsal_summary.py `
  --summary output/video/rehearsal-summary.json `
  --expected-commit <40位小写冻结提交SHA>
```

门禁要求三条唯一记录均在 175–185 秒、故障序列均为 `500/500/503`、before 非零、after 为零、胶囊与报告使用完整 SHA-256、主工作区未变化，并至少一轮断网。

## 3. 最终 MP4

最终剪辑严格 180 秒、1920×1080、30 fps。交付前必须完成音画检查、关键 ID 可读性检查、敏感信息复核、断网从头播放和 SHA-256 记录，再将清单状态由 `external_pending` 改为 `verified`。
