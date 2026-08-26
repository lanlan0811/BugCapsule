# BugCapsule 最终提交材料清单

[`submission-manifest.json`](submission-manifest.json)是开发计划八类交付物的机器真源。文档、状态、现有证据和预期输出必须一致：未完成项保留阻塞原因，不创建空文件、不以估算结果冒充实测。

## 1. 八类交付物

| 类别 | 当前状态 |
| --- | --- |
| Gitee 主仓、GitHub 镜像与正式 Release | 部分验证 |
| 中英文文档 | 已验证 |
| 示例胶囊与 12 案例评测 | 已验证 |
| 8 页项目 PDF | 已验证 |
| 三分钟演示视频 | 外部待完成 |
| 断网回放演示 | 部分验证 |
| SBOM、许可与 Release 供应链附件 | 部分验证 |
| 评审证据索引 | 已验证 |

## 2. 日常结构校验

```powershell
uv run python scripts/validate_submission_manifest.py
```

该命令检查 Schema、八类唯一 ID、状态枚举、安全相对路径、已验证文件存在性和未完成项阻塞说明。

## 3. 正式发布门禁

代码冻结、外部材料就绪后，把 `release_commit` 写为冻结提交的完整 40 位小写 SHA，并执行：

```powershell
uv run python scripts/validate_submission_manifest.py --require-ready
```

严格模式要求八类交付物全部为 `verified`，所有 `expected_outputs` 真实存在且 `release_commit` 合法。GitHub 标签 Release 工作流执行同一门禁。

当前视频、三轮断网彩排、正式供应链附件和 `v0.1.0` 标签尚未完成，所以严格模式按设计失败；普通结构校验必须通过。
