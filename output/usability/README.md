# 首次使用者验收数据契约

本目录只保存匿名汇总，不保存逐人响应、自由文本或占位结果。研究流程见[首次使用者协议](../../docs/usability-study.md)。

## 1. 原始响应格式

在仓库外为每名参与者保存一个 JSON：

```json
{
  "participant_id": "P01",
  "operating_system": "windows_11",
  "start_to_healthy_seconds": 480,
  "doctor_failed_check_ids": [],
  "completed_task_ids": [1, 2, 3, 4, 5, 6, 7],
  "hint_count": 0,
  "blocking_step": null,
  "documentation_gap_codes": ["none"],
  "confidence_1_to_5": 4,
  "consent_to_publish_anonymized": true
}
```

允许的操作系统：`windows_10`、`windows_11`、`linux`。

文档缺口代码：`dependency_install`、`environment_file`、`docker_startup`、`fault_capture`、`evidence_navigation`、`patch_approval`、`verification_report`，或单独使用 `none`。

禁止添加姓名、账号、公司、联系方式、用户路径、密钥、设备标识和自由文本。未知字段会被拒绝。

## 2. 生成匿名汇总

```powershell
$ResponseDir = Read-Host '请输入仓库外的响应目录'
uv run python scripts/aggregate_usability_study.py `
  --input-dir $ResponseDir `
  --output output\usability\summary.json
```

工具要求 3–5 个唯一匿名编号和全部发布同意，并拒绝越界值、未知枚举和输入/输出目录重叠。输出只包含群组指标，不含 `participant_id` 或逐人数据，且默认不覆盖已有结果。

当前真实试用尚未执行，所以 `summary.json` 不存在；这正是预期状态。
