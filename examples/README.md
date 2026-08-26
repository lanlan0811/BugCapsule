# BugCapsule 可导入示例

本目录提供一个最小、确定性、明确标注为仿真的 `.bugcapsule`，用于第一次浏览格式和验证导入链路。

| 文件 | 场景 | Capsule ID | 数据边界 |
| --- | --- | --- | --- |
| `connection-leak-simulated.bugcapsule` | Session 未关闭导致连接池耗尽 | `cap_eval_001` | 仿真 Trace、日志与源码，无生产数据 |

示例来自版本化数据集 `bugcapsule-simulated-root-cause-v1` 的 `BC-EVAL-001`。归档包含两个 Span、一条错误日志、Stack Trace、三行仿真源码、Git/环境摘要和脱敏报告。分析、Patch 与验证均为 `not_run`；人工标注答案不写入胶囊，也不能冒充模型结果。

## 1. 校验文件

```powershell
Get-FileHash -Algorithm SHA256 .\examples\connection-leak-simulated.bugcapsule
Get-Content .\examples\SHA256SUMS
```

期望 SHA-256：

```text
8a3f6438b98ebbcf14413eeb91d277b6e942a43a4df2c361808e62e9f0a46483
```

## 2. 导入浏览

```powershell
uv sync --frozen --group dev
uv run bugcapsule serve
```

打开本地 Web 后选择“导入胶囊”。导入器会重新验证扩展名、大小、ZIP 成员、路径、Schema、清单 SHA-256 和 Evidence 关系；仓库内文件也不绕过安全检查。

## 3. 确定性再生成

```powershell
uv run bugcapsule benchmark build --output .\benchmark-data
Get-FileHash -Algorithm SHA256 .\benchmark-data\capsules\cap_eval_001.bugcapsule
```

在数据集、Schema 和生成器未变化时，新文件应与示例逐字节一致。若有意更新，必须同时评审数据集标注哈希、示例归档、`SHA256SUMS`、[基准文档](../docs/benchmark.md)和相关测试。
