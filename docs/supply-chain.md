# 发布供应链与 SBOM

BugCapsule 的 CI 从提交的 `uv.lock` 构建发布证据。供应链任务与正式标签 Release 使用同一组冻结版本、输入和完整性校验；任何依赖审计、SBOM 结构或产物命名检查失败都会阻止交付。

## 发布包内容

| 文件 | 作用 | 生成依据 |
| --- | --- | --- |
| `bugcapsule-<version>-py3-none-any.whl` | Python wheel | 当前 Git 提交与 `pyproject.toml` |
| `bugcapsule-<version>.tar.gz` | 源代码包 | 当前 Git 提交与构建清单 |
| `bugcapsule.cdx.json` | CycloneDX 1.6 JSON SBOM | 仅安装冻结生产依赖的 `.venv` |
| `dependency-audit.json` | 已知漏洞逐依赖审计结果 | 哈希锁定的生产依赖快照与 PyPI Advisory Database |
| `release-requirements.txt` | 可审计的生产依赖与制品哈希 | `uv.lock`，排除开发组与本项目 editable 项 |
| `SHA256SUMS` | 上述五类文件的 SHA-256 | 按文件名排序后生成 |

CI 使用 `uv 0.8.13`；`cyclonedx-bom 7.3.1`、`pip-audit 2.10.1` 及其传递依赖全部记录在 `uv.lock` 的独立 `supply-chain` 组。工具在隔离环境中运行，不会进入被盘点的生产环境。升级时必须连同锁文件、本地复现、文档和审计结果一起评审。

## 本地复现

以下 PowerShell 命令与 CI 的生产依赖边界一致。执行后可用 `uv sync --frozen --group dev` 恢复开发依赖。

```powershell
$SupplyChainDir = Join-Path $PWD "supply-chain"

uv sync --frozen --no-dev
uv build
New-Item -ItemType Directory -Path $SupplyChainDir -Force | Out-Null
uv export --frozen --no-dev --no-emit-project --format requirements.txt `
  --output-file (Join-Path $SupplyChainDir "release-requirements.txt")
uv run --isolated --frozen --no-dev --group supply-chain pip-audit `
  --require-hashes `
  --requirement (Join-Path $SupplyChainDir "release-requirements.txt") `
  --format json `
  --output (Join-Path $SupplyChainDir "dependency-audit.json") `
  --progress-spinner off
uv run --isolated --frozen --no-dev --group supply-chain cyclonedx-py environment `
  --pyproject pyproject.toml `
  --spec-version 1.6 `
  --output-format JSON `
  --output-file (Join-Path $SupplyChainDir "bugcapsule.cdx.json") `
  .venv
.venv\Scripts\python.exe -m scripts.release_integrity `
  --dist-dir dist `
  --sbom (Join-Path $SupplyChainDir "bugcapsule.cdx.json") `
  --audit (Join-Path $SupplyChainDir "dependency-audit.json") `
  --requirements (Join-Path $SupplyChainDir "release-requirements.txt") `
  --checksums (Join-Path $SupplyChainDir "SHA256SUMS")
```

校验器要求恰好存在一个 wheel 和一个源码包，二者文件名及内部 Core Metadata 的项目名/版本都必须一致；读取源码包元数据时不会解压文件，并限制元数据大小。SBOM 必须是 CycloneDX 1.6、根组件必须匹配当前项目且至少包含一个依赖；审计结果必须覆盖非空依赖集合且已知漏洞数为零；依赖快照必须包含 SHA-256 哈希且不能包含 editable 项。校验和采用原子替换写入，避免留下半写文件。

## CI 与正式 Release

- `CI / supply-chain` 在主分支和 Pull Request 上生成临时证据包，保留 14 天，便于评审下载检查。
- 推送 `v*` 标签，或在 GitHub 工作流界面以一个已存在标签作为运行引用时，Release 工作流会先复用完整 CI；标签必须精确等于 `v<pyproject version>`，并指向检出的提交。手动从分支运行会因标签检查失败而停止。
- 只有所有门禁通过后，GitHub 镜像才创建 Release 并上传完整供应链包。Gitee 主仓 Release 使用同一批已校验文件，不重新生成另一套内容。
- `SHA256SUMS` 不包含自身。下载后应使用平台自带的 SHA-256 工具逐项核对，再安装 wheel 或解压源码包。

## 安全边界

`pip-audit` 只报告其数据源中已公开、能映射到所解析 Python 包版本的漏洞。零结果不代表不存在未知漏洞，也不能替代源码审计、容器镜像扫描、秘密扫描或运行时防护。SBOM 是依赖清单与追溯证据，不是安全认证。网络或漏洞服务不可用时任务必须失败，不能用空报告替代。
