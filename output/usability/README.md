# 首次使用者验收输出

本目录当前只包含结构化采集和匿名汇总说明，不包含虚构参与者或占位结果。完成 3–5 名未参与开发的志愿者试用后，在仓库外建立输入目录；每名参与者使用一个 JSON 文件，且只能包含下列字段：

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

允许的系统值为 `windows_10`、`windows_11`、`linux`。文档缺口代码为 `dependency_install`、`environment_file`、`docker_startup`、`fault_capture`、`evidence_navigation`、`patch_approval`、`verification_report` 或单独的 `none`。自由文本、姓名、账号、公司、路径、密钥、设备标识和联系方式不得进入 JSON。

生成只含汇总指标的结果：

```powershell
uv run python scripts/aggregate_usability_study.py `
  --input-dir C:\safe-local\bugcapsule-usability-responses `
  --output output\usability\summary.json
```

工具要求恰好 3–5 个唯一匿名编号、全部明确同意匿名发布，并拒绝未知字段。输出不包含参与者逐行记录或自由文本；原始响应继续保存在仓库外。当前尚未执行真实试用，因此 `summary.json` 不存在。
