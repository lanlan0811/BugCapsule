# BugCapsule 开放胶囊格式 0.1.0

`.bugcapsule` 是 BugCapsule 的权威交换产物：一个确定性、可完整校验、默认脱敏的 ZIP 归档。本文是格式说明；可执行约束以 [`src/bugcapsule/capsule/schema.py`](../src/bugcapsule/capsule/schema.py) 和 [`archive.py`](../src/bugcapsule/capsule/archive.py) 为准。

## 1. 编码与确定性

- JSON 使用 UTF-8、排序键和紧凑分隔符；
- 时间必须包含时区；
- 路径使用相对 POSIX 格式；
- ZIP 成员按路径排序；
- ZIP 时间戳、Unix 权限和压缩方式固定；
- 当前导出使用 `ZIP_STORED`；
- 写入通过同目录临时文件和原子替换完成。

相同清单与载荷必须生成逐字节相同的归档。

## 2. 目录结构

```text
<capsule-id>.bugcapsule
├── manifest.json
├── evidence/
│   ├── traces.jsonl
│   ├── logs.jsonl
│   └── source-snippets.json
├── redaction-report.json
├── analysis/
│   └── root-causes.json
├── patches/
│   ├── candidate.json
│   └── candidate.diff
└── verification/
    ├── result.json
    ├── before.log
    ├── after.log
    └── redaction-report.json
```

分析、Patch 和验证目录只在对应阶段成功写入后存在。未执行阶段通过 `manifest.processing` 表达，不创建空文件。

## 3. `manifest.json`

`CapsuleManifest` 包含：

| 区域 | 内容 |
| --- | --- |
| identity | `schema_version`、`capsule_id`、创建时间、仿真标记 |
| service | 服务名与入口点 |
| trace | Trace ID、根 Span、开始/结束时间 |
| git | 提交 SHA、分支和 dirty 状态 |
| environment | Python、平台与依赖锁摘要 |
| processing | 捕获、分析、Patch、验证状态及关联 ID |
| files | 每个实际载荷的路径、媒体类型、字节数和 SHA-256 |

`manifest.json` 不对自身计算哈希，避免自引用循环。`manifest.files` 必须与归档中的非清单成员一一对应，按路径升序且不得重复。

## 4. 核心模型

- `EvidenceItem`：Trace、Span、日志、Stack Trace、源码、Git、环境或测试事实；
- `RootCauseCandidate`：本地 ID、排名、假设、置信度、未知项和证据引用；
- `PatchCandidate`：Patch ID、Root Cause ID、diff 路径、摘要、SHA-256、修改范围和安全检查；
- `VerificationRun`：批准绑定、固定命令身份、before/after 结果和最终状态；
- `RedactionFinding`：规则 ID、JSON Pointer、替换标记和计数。

## 5. 标识符

| 标识 | 格式 | 生成方 |
| --- | --- | --- |
| Trace ID | 32 位小写十六进制 | OpenTelemetry |
| Span ID | 16 位小写十六进制 | OpenTelemetry |
| SHA-256 | 64 位小写十六进制 | 本地确定性代码 |
| Evidence ID | `EV-` + 规范内容 SHA-256 前 12 位大写十六进制 | 本地确定性代码 |
| Root Cause ID | 规范化根因内容派生 | 本地确定性代码 |
| Patch ID | Root Cause ID、diff SHA-256 和有序文件集合派生 | 本地确定性代码 |
| Verification ID | Patch 绑定与固定命令身份派生 | 本地确定性代码 |

Evidence ID 输入包含证据类型、来源、规范化内容、Trace ID 和 Span ID，不包含采集时间或显示优先级。同一事实重复捕获仍得到相同 ID。

模型无权指定 Root Cause、Patch 或 Verification ID。任何模型 `evidence_ref` 都必须存在于本次请求的证据集合；未知引用使整个响应无效。

## 6. 完整性校验

导入时按以下顺序失败关闭：

1. 检查 ZIP 总体限制和成员类型；
2. 验证成员路径和重复项；
3. 解析 `manifest.json` 并验证 `schema_version`；
4. 比较实际成员集合与 `manifest.files`；
5. 逐文件验证字节数和 SHA-256；
6. 解析证据并重新计算 Evidence ID；
7. 验证 Trace/Span 父子引用；
8. 若存在分析、Patch 或验证产物，重新验证对应引用和绑定。

缺失、多余、篡改、越界或不一致载荷均拒绝整个导入，不返回部分胶囊。

## 7. ZIP 安全规则

- 只允许非空相对 POSIX 路径；
- 禁止绝对路径、盘符、反斜杠、`.`、`..` 和空路径段；
- 禁止目录、符号链接、加密成员、重复成员和未知压缩方法；
- 限制成员数量、单文件展开大小、总展开大小和压缩比；
- 读取源码包或归档元数据时不执行载荷内容。

具体上限来自 `.env` / `BUGCAPSULE_*` 配置，不在文档中复制第二套常量。

## 8. Patch 与验证绑定

`candidate.diff` 只能是文本 Git unified diff。导入器重新解析并拒绝删除、重命名、复制、二进制、文件模式变化、无 Hunk、重复目标、路径逃逸、保护路径和缺少源码 Evidence 的目标。

`candidate.json` 的 SHA-256、文件集合和安全检查必须与重新解析的 diff 一致。验证结果必须绑定当前 Patch ID 和 SHA-256；`passed` 只在 before 非零、after 为零且二者均未超时时成立。before/after 日志摘要、固定命令 ID 和清单状态必须互相一致。

## 9. 默认脱敏

证据在写入归档或发送给模型之前递归脱敏：

- 敏感字段名：Authorization、Cookie、Token、Password、API Key、连接串；
- 字符串模式：Bearer 凭据、数据库 URL、邮箱、中国大陆手机号和常见 API Key。

`redaction-report.json` 不保存匹配原文，只保存规则、位置、固定替换标记和数量。Finding ID 从这些非敏感字段派生。

## 10. 版本兼容

当前实现只接受 `0.1.0`。读取器对未知版本显式拒绝，不以宽松解析猜测兼容。未来版本如增加可选字段，必须同时提供迁移说明、正反例测试与版本化读取策略；破坏性变化提升主版本。

## 11. 派生产物

HTML 对比报告不是归档载荷，不加入 `manifest.files`。报告每次从完整校验后的 `CapsuleDetail` 确定性渲染并计算独立 SHA-256；其中展示的归档摘要始终指向生成它的 `.bugcapsule` 字节。
