# 项目介绍 PDF

`BugCapsule_0.1_项目介绍.pdf` 是上海开源软件应用创新大赛的中文 A4 项目介绍，共 8 页。内容快照日期为 2026-08-26，覆盖问题定义、闭环架构、数据库连接池主演示、模型边界、Patch 安全、实测指标、开源治理与正式 Release 待办。

## 完整性

```text
SHA-256  a18a264574e8c67c9d807c2dbd7c0e7594a260f1a0a7ba394de0a46ff315f7bd
Pages    8
Format   A4 / PDF 1.4 / no JavaScript / no encryption
```

仓库中的 `SHA256SUMS` 记录最终提交文件的摘要。PDF 采用 ReportLab `invariant` 模式；相同字体文件、工具版本和输入可逐字节重复生成。不同操作系统选用不同离线字体时，文字与版式保持一致，但嵌入字体字节和最终 SHA-256 可能不同。

## 确定性生成

PDF 工具及其传递依赖位于 `uv.lock` 的独立 `artifacts` 组，不进入生产环境或发布 SBOM：

```powershell
uv run --isolated --frozen --no-dev --group artifacts `
  python scripts/build_project_pdf.py
Get-FileHash -Algorithm SHA256 .\output\pdf\BugCapsule_0.1_项目介绍.pdf
```

Windows 构建优先使用 Microsoft YaHei 与 Consolas；Linux 构建回退到 Noto Sans CJK 与 DejaVu Sans Mono。字体完全离线，不加载 CDN 或 Web Font。

## 视觉与结构 QA

最终文件必须先用 `pypdf` 或 `pdfinfo` 检查元数据、页数、加密与脚本状态，再使用 Poppler 将全部页面渲染为 PNG 逐页检查：

```powershell
pdfinfo.exe .\output\pdf\BugCapsule_0.1_项目介绍.pdf
pdftoppm.exe -r 150 -png `
  .\output\pdf\BugCapsule_0.1_项目介绍.pdf `
  .\tmp\pdfs\project-intro\page
```

本次已完成两轮全页渲染。第二轮修正了中英混排字体缺字、Python 版本指标换行和末页待办徽标重叠；最终 8 页没有发现截断、重叠、黑块或不可读图表。
