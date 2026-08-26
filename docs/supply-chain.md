# BugCapsule 发布供应链与 SBOM

本页定义从 `uv.lock` 到 Release 附件的可复现链路。目标是让评审者知道每个文件由什么输入生成、由什么规则校验，以及“零已知漏洞”不能证明什么。

## 1. 输入与工具边界

- 项目元数据：`pyproject.toml`；
- 依赖解析：提交的 `uv.lock`；
- 构建工具：`uv 0.8.13`；
- SBOM：`cyclonedx-bom 7.3.1`；
- 漏洞审计：`pip-audit 2.10.1`；
- 完整性校验：`scripts/release_integrity.py`。

供应链工具位于独立 `supply-chain` 依赖组，在隔离环境运行，不进入被盘点的生产环境。升级任一工具时必须同时评审锁文件、生成格式、本地复现和 CI。

## 2. 交付文件

| 文件 | 证明内容 | 校验规则 |
| --- | --- | --- |
| `bugcapsule-<version>-py3-none-any.whl` | 可安装 Python 包 | 文件名、Core Metadata 名称/版本与项目一致 |
| `bugcapsule-<version>.tar.gz` | 源码发布包 | 文件名与包内 Core Metadata 一致 |
| `release-requirements.txt` | 生产依赖及制品哈希 | 非空、无 editable、每项含 SHA-256 |
| `bugcapsule.cdx.json` | CycloneDX 1.6 生产 SBOM | 根组件匹配项目，至少包含一个依赖 |
| `dependency-audit.json` | 已公开依赖漏洞结果 | 覆盖非空依赖集合，已知漏洞数为零 |
| `SHA256SUMS` | 上述文件字节完整性 | 按文件名排序；不包含自身 |

本地已复现事实：SBOM 48 个生产组件，审计 47 个哈希冻结依赖，数据源当次返回零已知漏洞。

## 3. PowerShell 复现

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

命令完成后可用 `uv sync --frozen --group dev` 恢复开发环境。

## 4. 完整性校验器

`release_integrity` 不解压源码包到磁盘；它直接读取受大小限制的元数据。校验流程包括：

1. 要求 dist 中恰好一个 wheel 和一个 sdist；
2. 比较文件名、wheel Metadata 和 sdist PKG-INFO；
3. 校验 SBOM 格式、版本、根组件和依赖集合；
4. 校验审计结果结构与漏洞数；
5. 校验 requirements 的哈希和非 editable 边界；
6. 对全部交付文件生成稳定排序的 `SHA256SUMS`；
7. 通过临时文件和原子替换写入清单。

任何结构、身份、版本、哈希或漏洞门禁失败都以非零退出，不生成可发布结论。

## 5. CI 与 Release

- `CI / supply-chain` 在 `master` 和 Pull Request 构建临时证据包，保留 14 天；
- Release 工作流先复用完整 CI，再运行提交材料 `--require-ready` 门禁；
- 标签必须精确等于 `v<pyproject version>` 并指向检出提交；
- GitHub 生成一次附件，Gitee 使用同一批已校验字节，不重新构建第二套产物；
- 下载者应先用平台 SHA-256 工具核对，再安装或解压。

## 6. 安全解释

`pip-audit` 只能报告数据源中已公开且能映射到解析包版本的漏洞。零结果不代表不存在未知漏洞，也不替代源码审计、容器基础镜像扫描、秘密扫描或运行时防护。SBOM 是依赖清单与追溯证据，不是认证。网络或漏洞服务不可用时任务必须失败，不能用空报告占位。
