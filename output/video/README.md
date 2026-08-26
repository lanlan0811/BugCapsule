# 演示视频交付目录

本目录当前交付的是可机器校验的录制计划，不包含占位 MP4。

| 资产 | 状态 | 说明 |
| --- | --- | --- |
| `demo-shot-list.json` | 已验证 | 10 个连续镜头，严格覆盖 0–180 秒及开发计划中的十步路演 |
| [`demo-runbook.md`](../../docs/demo-runbook.md) | 已验证 | 录制、断网、彩排、失败兜底和诚实口径 |
| `rehearsal-summary.json` | 外部待完成 | 必须来自有 Docker 的比赛环境三次完整彩排 |
| `BugCapsule_0.1_三分钟演示.mp4` | 外部待完成 | 必须来自实际屏幕录制，不提交空文件 |

复核录制计划：

```powershell
uv run python scripts/validate_demo_plan.py
```

校验器会拒绝时间断点、重叠、非 180 秒结尾、重复镜头、缺失仓库证据、未知运行模式，以及在实际视频不存在时被错误标记为已验证的状态。

完成三次真实彩排后，按 [`demo-runbook.md`](../../docs/demo-runbook.md) 中的严格 JSON 字段写入 `rehearsal-summary.json`，再将冻结提交的完整 SHA 传给汇总门禁：

```powershell
uv run python scripts/validate_rehearsal_summary.py `
  --summary output/video/rehearsal-summary.json `
  --expected-commit <40位小写冻结提交SHA>
```

门禁要求三条唯一彩排记录全部在 180±5 秒内，故障序列均为 `500/500/503`，验证均为 before 非零、after 零，胶囊与报告使用完整 SHA-256，主工作区未改变，并至少有一轮明确使用断网模式。当前文件不存在，表示真实彩排尚未执行。
