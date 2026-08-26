# BugCapsule 项目介绍 PDF

[`BugCapsule_0.1_项目介绍.pdf`](BugCapsule_0.1_项目介绍.pdf)是上海开源软件应用创新大赛中文项目说明，A4 共 8 页。内容冻结于 2026-08-26，覆盖问题、架构、连接池主演示、模型边界、Patch 安全、验证指标、开源治理和 Release 待办。

## 1. 已验证属性

| 属性 | 值 |
| --- | --- |
| SHA-256 | `a18a264574e8c67c9d807c2dbd7c0e7594a260f1a0a7ba394de0a46ff315f7bd` |
| 页数 | 8 |
| 页面 | A4 |
| PDF 版本 | 1.4 |
| 主动内容 | 无 JavaScript、无加密、无外部资源 |

[`SHA256SUMS`](SHA256SUMS)记录仓库产物摘要。生成器使用 ReportLab `invariant` 模式；相同输入、字体文件和工具版本可逐字节复现。不同系统选用不同离线字体时，布局目标保持一致，但嵌入字体和最终摘要可能不同。

## 2. 确定性生成

PDF 工具位于 `uv.lock` 的独立 `artifacts` 组，不进入生产依赖和发布 SBOM：

```powershell
uv run --isolated --frozen --no-dev --group artifacts `
  python scripts/build_project_pdf.py
Get-FileHash -Algorithm SHA256 .\output\pdf\BugCapsule_0.1_项目介绍.pdf
```

Windows 优先使用 Microsoft YaHei 与 Consolas；Linux 回退到 Noto Sans CJK 与 DejaVu Sans Mono。全程离线，不使用 CDN 或 Web Font。

## 3. 结构与视觉 QA

先检查页数、元数据、加密和主动内容，再用 Poppler 渲染全部页面：

```powershell
pdfinfo.exe .\output\pdf\BugCapsule_0.1_项目介绍.pdf
pdftoppm.exe -r 150 -png `
  .\output\pdf\BugCapsule_0.1_项目介绍.pdf `
  .\tmp\pdfs\project-intro\page
```

最终版完成两轮逐页检查，已修正中英混排缺字、指标换行和末页状态标记重叠；8 页未发现截断、重叠、黑块或不可读图表。
