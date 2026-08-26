# 最终提交材料清单

[`submission-manifest.json`](submission-manifest.json)逐项对应开发计划 7.2 的八类最终交付物。仓库内已验证项必须链接现有文件；部分完成和外部待完成项必须说明阻塞原因，不以空文件或估算结果冒充完成。

检查当前清单结构与证据路径：

```powershell
uv run python scripts/validate_submission_manifest.py
```

代码冻结并准备创建正式标签前执行严格门禁：

```powershell
uv run python scripts/validate_submission_manifest.py --require-ready
```

严格门禁要求全部八类交付物为 `verified`、所有预期输出真实存在，并且 `release_commit` 是完整 40 位小写 Git SHA。GitHub 标签 Release 工作流会执行同一检查；当前仍有视频、断网彩排、供应链 Release 附件和正式标签等外部事项，因此严格命令按设计返回失败。
