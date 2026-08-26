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

## 结构化匿名记录

原始响应必须存放在仓库外，每名参与者一个 JSON 文件，并严格采用 [`output/usability/README.md`](../output/usability/README.md) 定义的字段、枚举和取值范围。只使用 `P01` 形式的匿名编号；不采集自由文本、姓名、账号、公司、设备标识、路径、密钥或联系方式。主持人的观察笔记不得复制进响应 JSON。

参与者完成后，在仓库根目录运行：

```powershell
uv run python scripts/aggregate_usability_study.py `
  --input-dir C:\safe-local\bugcapsule-usability-responses `
  --output output\usability\summary.json
```

汇总器只接受 3–5 个唯一匿名编号、明确同意匿名发布且字段完全匹配的记录；未知字段、自由文本变体、重复值和越界值都会被拒绝。输出路径必须位于原始响应目录之外，默认拒绝覆盖已有结果。发布的 `summary.json` 只包含中位启动时间、任务完成率、常见失败检查/步骤、文档缺口计数、信心与提示数汇总，不包含参与者逐行数据。

首次真实试用前不得创建占位 `summary.json`。试用完成后，由维护者人工核对汇总与主持人去标识笔记，只把汇总及已修正文档提交到仓库；不同意发布的参与者记录不得作为输入。
