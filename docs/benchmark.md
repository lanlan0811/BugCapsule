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
