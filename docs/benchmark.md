# BugCapsule 仿真基准与量化评测

基准用于回答两个不同问题：确定性分析管线是否可重复，以及所选 Live 模型在固定标注上的表现如何。两类结果必须分开发布。

## 1. 数据集

随包发布的数据集名为 `bugcapsule-simulated-root-cause-v1`，包含 12 个明确标记 `simulated_data=true` 的案例：

| 故障类 | 数量 | 覆盖示例 |
| --- | ---: | --- |
| connection leak | 4 | Session、异常路径、事务、流式响应未释放 |
| database unreachable | 4 | 连接拒绝、DNS、TLS、端口配置 |
| slow query | 4 | 缺少索引、复合索引、N+1、排序溢写 |

源文件为 [`src/bugcapsule/benchmarking/dataset.json`](../src/bugcapsule/benchmarking/dataset.json)。Pydantic Schema 要求至少 12 案例、每类至少 4 个、Case/Capsule ID 唯一、必需 Evidence 类型不重复。

每个案例包含稳定 ID、仿真故障输入、人工期望根因、可公开复核的关键词组和根因必须覆盖的 Evidence 类型。它不是生产事故数据，也不代表真实流量分布。

## 2. 确定性构建

```powershell
uv run bugcapsule benchmark build --output .\benchmark-data
```

输出：

```text
benchmark-data/
├── annotations.json
└── capsules/
    └── *.bugcapsule
```

Trace/Span ID、Git SHA、时间戳、Evidence ID、ZIP 元数据和成员顺序均从版本化输入派生。相同提交在不同目录生成相同归档字节。已存在输出默认拒绝覆盖；只有显式 `--force` 才替换。

`annotations.json` 的 SHA-256 写入评测报告，使任何指标都绑定到确切标注版本。

## 3. Replay 评测

```powershell
uv run bugcapsule benchmark run --mode replay --output .\benchmark-replay
```

Replay 使用公开注释构造结构化响应，再通过正式 `AnalysisService`、Schema、Evidence 引用、胶囊写回和索引更新执行全部案例。它验证管线与计分器，不测量模型泛化能力。

提供方固定记录为 `bugcapsule-annotated-replay`，模型标识为 `root-cause-v1`。

## 4. Live 评测

在 `.env` 配置比赛采用的 OpenAI-compatible provider 与 model 后运行：

```powershell
uv run bugcapsule benchmark run --mode live --output .\benchmark-live
```

Live 报告必须保留 provider、model、开始/完成时间、标注 SHA-256 和全部 12 个逐案例结果。调用失败仍计入分母，按 Top-1 未命中处理，不能删除失败案例后重新计算。

## 5. 指标定义

| 指标 | 定义 |
| --- | --- |
| completed count | 完成严格结构化分析的案例数 / 12 |
| Top-1 accuracy | 排名第一根因是否覆盖全部人工关键词组 |
| citation validity | 有效 Evidence 引用数 / 总引用数 |
| required evidence coverage | 覆盖案例规定 Evidence 类型的案例数 / 12 |
| deterministic latency | 总分析耗时减去 provider/replay 边界耗时 |
| model or replay latency | 仅 provider 或 Replay Store 边界耗时 |
| total latency | 请求构造、边界调用、校验、归档写回与索引更新总耗时 |

P50/P95 使用 nearest-rank 方法。延迟是当前机器与当次运行的观测值，不是服务等级承诺。

## 6. 已复现 Replay 结果

环境：Windows 10、Python 3.12.13；标注 SHA-256：`f6e603ca74bef5e6d563281b62141ba904ff78af3fd3f6bde2bed21ead9da01b`。

| 指标 | 实测值 |
| --- | ---: |
| 完成案例 | 12 / 12 |
| Top-1 注释匹配率 | 100% |
| Evidence 引用有效率 | 100% |
| 必需 Trace/日志/源码覆盖率 | 100% |
| 确定性处理 P50 / P95 | 79.290 / 109.752 ms |
| Replay 读取 P50 / P95 | 0.751 / 4.458 ms |
| 完整分析 P50 / P95 | 80.016 / 110.323 ms |

这些数字只证明当次注释回放结果。比赛默认 Live 模型尚未配置并独立发布，因此 README、PDF 和路演不得把上表称为模型准确率。

## 7. 复核

```powershell
uv run pytest tests/benchmarking -o addopts=
uv run bugcapsule benchmark build --output .\benchmark-data
uv run bugcapsule benchmark run --mode replay --output .\benchmark-replay
```

评审者应核对 `evaluation.json` 中的 `mode`、provider、model、标注摘要、逐案例失败和聚合指标，而不是只阅读百分比截图。
