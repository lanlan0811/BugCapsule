# 首次使用者可用性验收

本协议用于 3-5 名未参与开发的志愿者。它不预填结果，也不以开发者自测代替真实参与者反馈。

## 任务

1. 在全新 Windows 10/11 或 Linux 环境中克隆仓库；
2. 只阅读 README，安装 Python、uv 与 Docker；
3. 复制 `.env.example`，运行 `uv run bugcapsule doctor`；
4. 启动主演示并稳定复现连接池耗尽；
5. 打开 Web 证据链，说明一个根因引用；
6. 在 replay 模式生成 Patch、核对 SHA-256、运行隔离验证并下载 HTML 报告；
7. 执行 `demo reset`，确认环境可再次运行。

计时从开始阅读 README 到 Web 健康检查成功；目标中位数不超过 10 分钟。主持人只记录观察，不在参与者首次卡住时立即提示；超过 3 分钟的阻塞可给予最小提示并单独记录。

## 匿名记录模板

| 字段 | 记录方式 |
| --- | --- |
| participant_id | `P01` 等匿名编号 |
| operating_system | 系统与版本，不记录设备序列号 |
| start_to_healthy_seconds | 实测秒数 |
| doctor_failed_check_ids | 失败检查 ID，使用分号分隔 |
| task_completion_rate | 完成任务数 / 7 |
| hints_given | 提示数量与最小内容摘要 |
| blocking_step | 首个无法独立完成的步骤，无则留空 |
| documentation_gap | 参与者指出的文档缺口 |
| confidence_1_to_5 | 主观完成信心 |
| consent_to_publish_anonymized | `yes` 或 `no` |

发布汇总时只报告中位启动时间、任务完成率、常见失败步骤、已修正文档和未解决问题。参与者自由文本必须去除姓名、账号、公司、路径和密钥；未同意匿名发布的数据不进入仓库。
