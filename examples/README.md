# BugCapsule 示例胶囊

本目录提供一个可以直接导入 BugCapsule Web 的最小示例：

| 文件 | 场景 | 数据性质 | Capsule ID |
| --- | --- | --- | --- |
| `connection-leak-simulated.bugcapsule` | 数据库 Session 未关闭，连接未归还并最终耗尽连接池 | 明确标注的仿真数据 | `cap_eval_001` |

该文件来自随包发布的 `bugcapsule-simulated-root-cause-v1` 数据集案例 `BC-EVAL-001`，不含真实生产日志、用户数据、密钥或专有源码。它包含两个 Trace/Span 事件、一条错误日志、Stack Trace、三行仿真源码、Git/环境摘要和脱敏报告；分析与验证状态均为 `not_run`，不能把人工标注答案冒充模型输出。

## 校验与导入

先核对仓库记录的 SHA-256：

```powershell
Get-FileHash -Algorithm SHA256 .\examples\connection-leak-simulated.bugcapsule
Get-Content .\examples\SHA256SUMS
```

期望摘要为 `8a3f6438b98ebbcf14413eeb91d277b6e942a43a4df2c361808e62e9f0a46483`。随后启动本地服务，在顶栏选择“导入胶囊”：

```powershell
uv sync --frozen --group dev
uv run bugcapsule serve
```

导入器会重新执行扩展名、大小、ZIP 成员、路径、Schema、清单 SHA-256 和证据关联校验；不要因为文件来自仓库而绕过这些检查。

## 确定性再生成

以下命令会从包内版本化标注生成全部 12 个案例：

```powershell
uv run bugcapsule benchmark build --output .\benchmark-data
Get-FileHash -Algorithm SHA256 .\benchmark-data\capsules\cap_eval_001.bugcapsule
```

未修改数据集、Schema 或生成器时，`cap_eval_001.bugcapsule` 应与本目录示例逐字节一致。若有意更新数据集，必须同时评审标注 SHA-256、示例文件、`SHA256SUMS`、基准文档和相关测试；不能只替换二进制文件。
