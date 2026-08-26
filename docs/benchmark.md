# 仿真基准数据集

BugCapsule 随 Python 包发布 `bugcapsule-simulated-root-cause-v1`。数据集由 12 个明确标注为仿真的案例组成，平均覆盖三类故障：

- 连接泄漏：Session、异常路径、事务和流式响应未释放连接；
- 数据库不可达：连接拒绝、DNS、TLS 与端口配置；
- 慢查询：缺少索引、复合索引、N+1 与排序溢写。

每个案例包含稳定 Case/Capsule ID、故障输入、期望根因、可公开复核的关键词组以及根因必须覆盖的 Evidence 类型。源文件位于 `src/bugcapsule/benchmarking/dataset.json`，由严格 Pydantic Schema 校验：案例数不得少于 12，每类不得少于 4，Case ID、Capsule ID 和必需 Evidence 类型不得重复。

## 确定性生成

```powershell
uv run bugcapsule benchmark build --output .\benchmark-data
```

命令生成 `annotations.json` 和 `capsules/*.bugcapsule`。Trace/Span ID、Git SHA、时间戳、Evidence ID、ZIP 元数据和载荷顺序均由版本化输入确定；相同版本在不同目录生成完全相同的归档字节。输出已存在时默认拒绝覆盖，只有显式 `--force` 才会替换同名基准文件。

`annotations.json` 的 SHA-256 会写入命令结果，后续评测报告必须携带该值，确保指标与确切标注版本绑定。仿真回放指标不能表述为真实生产数据或在线模型泛化能力；Live 评测必须另外记录提供方、模型和运行时间。

## 量化评测

```powershell
# 无网络的注释回放：验证完整分析链、引用和计时口径
uv run bugcapsule benchmark run --mode replay --output .\benchmark-replay

# 使用 .env 中的默认 OpenAI-compatible 提供方和模型
uv run bugcapsule benchmark run --mode live --output .\benchmark-live
```

`evaluation.json` 逐案例记录完成状态、Top-1 匹配、引用数量、有效引用、必需 Evidence 类型覆盖，以及确定性处理、模型或回放边界、完整分析三段实测耗时。聚合区使用 nearest-rank 方法报告 P50/P95，并报告 Top-1 准确率、引用有效率和必需证据覆盖率。

`replay` 的提供方固定标记为 `bugcapsule-annotated-replay`，结论来自公开注释，只能证明离线管线和评分方法可重复。`live` 才测量所配置模型，报告会保留实际 provider、model、开始/完成时间；模型调用失败的案例计入总样本并按 Top-1 未命中处理，不从分母中删除。

## 已复现实测

2026-08-26 在 Windows 10、Python 3.12.13 上对标注 SHA-256 `f6e603ca74bef5e6d563281b62141ba904ff78af3fd3f6bde2bed21ead9da01b` 执行一次 `replay`：

| 指标 | 实测值 |
| --- | ---: |
| 完成案例 | 12 / 12 |
| Top-1 注释匹配率 | 100% |
| Evidence 引用有效率 | 100% |
| 必需 Trace/日志/源码覆盖率 | 100% |
| 确定性处理 P50 / P95 | 79.290 / 109.752 ms |
| 注释回放读取 P50 / P95 | 0.751 / 4.458 ms |
| 完整分析 P50 / P95 | 80.016 / 110.323 ms |

这是一次机器相关的实际测量值，不是性能承诺。运行 `benchmark run` 会保留全部 12 条逐案例结果和测量时间；Live 默认模型结果将在配置比赛使用的提供方后单独发布，不能用上表替代。
