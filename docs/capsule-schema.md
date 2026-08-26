# BugCapsule 开放胶囊格式 0.1.0

`.bugcapsule` 是一个确定性 ZIP 交换产物。胶囊文件是权威数据，SQLite 仅作为可重建索引。所有 JSON 文件使用 UTF-8、排序键和紧凑分隔符编码，时间必须包含时区。

导出器使用固定 ZIP 时间戳、固定 Unix 文件权限、固定成员顺序和 `ZIP_STORED`，相同 manifest 与载荷必须产生逐字节相同的归档。写入通过同目录临时文件和原子替换完成。

## 目录结构

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
└── verification.json
```

除 `manifest.json` 外，每个实际存在的载荷文件都必须在 `manifest.files` 中出现，记录相对 POSIX 路径、SHA-256、小数制字节数和媒体类型。`manifest.json` 不对自身计算哈希，避免循环依赖。清单按路径升序排列，禁止重复项。

## 核心类型

- `CapsuleManifest`：Schema 版本、胶囊、服务、Trace、Git、环境、处理状态和文件完整性清单。
- `EvidenceItem`：Trace、Span、日志、Stack Trace、源码、Git、环境或测试证据。
- `RootCauseCandidate`：排名、置信度、未知项和证据引用。
- `PatchCandidate`：Patch ID、根因 ID、Diff 文件、SHA-256、修改范围和安全检查。
- `VerificationRun`：人工批准绑定、固定测试命令和修复前后结果。
- `RedactionFinding`：脱敏规则、位置、替换标记和命中数量。

## 标识符与证据引用

证据 ID 使用 `EV-` 加规范化内容 SHA-256 的前 12 位大写十六进制字符。ID 输入包括证据类型、来源、内容、Trace ID 和 Span ID，不包含采集时间或优先级，因此同一事实重复采集仍得到同一 ID。

模型输出中的每个 `evidence_ref` 必须存在于当前胶囊。未知引用使整个响应无效；模型适配器最多重试一次，不允许静默删除未知引用。

Root Cause ID 与 Patch ID 均由本地规范化内容派生，模型不能指定。Patch ID 绑定 Root Cause ID、canonical diff SHA-256 和有序修改文件清单；`candidate.json` 中的 SHA-256、修改范围和安全检查必须与 `candidate.diff` 的重新解析结果一致。

## 安全约束

- 归档路径只允许非空相对 POSIX 路径。
- 禁止绝对路径、盘符、反斜杠、`.` 和 `..` 路径段。
- Trace ID 固定为 32 位小写十六进制，Span ID 固定为 16 位。
- SHA-256 固定为 64 位小写十六进制。
- `schema_version` 当前只接受 `0.1.0`；不支持的版本必须显式拒绝。
- `explicitly_approved=true` 时，`approved_sha256` 必须逐字等于 `patch_sha256`。
- 导入限制文件数量、单文件大小、总解压大小和压缩比；拒绝重复成员、目录、加密成员、符号链接和未知压缩方法。
- 导入后必须逐项验证 manifest 的路径集合、文件大小和 SHA-256，缺失、多余或篡改载荷一律拒绝。
- Patch 只接受文本 Git unified diff；删除、重命名、复制、二进制、模式变化、测试/依赖/配置保护路径、无源码 Evidence 路径和工作区逃逸一律拒绝。

## 默认脱敏

所有证据必须在写入胶囊或发送给模型之前递归脱敏。字段名匹配 Authorization、Cookie、Token、密码、API Key 或连接串时替换整个值；其余字符串继续检测 Bearer 凭据、数据库 URL、邮箱、中国大陆手机号和常见 API Key 形式。

`redaction-report.json` 只记录规则 ID、JSON Pointer 位置、固定替换标记和命中数量，绝不记录原始匹配内容。Finding ID 从这些非敏感审计字段稳定派生。

正式验证逻辑以 [`src/bugcapsule/capsule/schema.py`](../src/bugcapsule/capsule/schema.py) 中的 Pydantic 模型为准。
