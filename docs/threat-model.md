# BugCapsule 威胁模型

本模型覆盖本地单用户、比赛演示和离线评审场景。它不把模型、导入胶囊、日志或 Patch 当作可信输入，也不把容器化等同于绝对隔离。

## 1. 范围与安全目标

安全目标：

1. 主源码、Git 工作区和人工批准意图不被模型或导入文件篡改；
2. API Key、运行日志中的秘密和个人数据不进入胶囊、模型请求或报告；
3. 胶囊、分析、Patch 与验证结果可检测篡改；
4. Patch 只在受限临时副本中验证；
5. Replay、仿真数据和外部待完成结果不被表述为 Live 或生产事实。

非目标：多用户认证、远程部署、生产 Agent、宿主内核加固和模型提供方合规认证。

## 2. 受保护资产

- 宿主源码、Git 元数据和回归测试；
- `.env`、模型 API Key、数据库凭据；
- Trace、日志、Stack Trace 和源码中的秘密/PII；
- `.bugcapsule` 完整性和 Evidence 引用关系；
- Patch ID、SHA-256 与用户批准；
- Docker Engine、验证镜像和固定命令；
- 基准标注、评测结果和提交材料状态。

## 3. 信任边界

```text
运行服务 ──不可信遥测──> 捕获/脱敏器
外部文件 ──不可信 ZIP──> 胶囊导入器
胶囊证据 ──已脱敏数据──> 模型提供方
模型响应 ──不可信结构──> Schema / Evidence / Patch 校验器
用户输入 ──批准绑定────> 验证服务
宿主源码 ──临时副本────> 受限 Docker 容器
胶囊详情 ──转义渲染────> HTML 报告
```

受信控制面是本地配置、确定性校验器、锁定回归和用户对完整摘要的明确批准；这些输入仍需格式与范围检查。

## 4. 威胁、控制与验证证据

| 威胁 | 主要控制 | 失败策略 | 证据 |
| --- | --- | --- | --- |
| ZIP Slip、绝对路径、额外载荷 | POSIX 路径约束；成员集合、大小、SHA-256、压缩比和总量校验 | 拒绝整个导入 | `tests/capsule/test_archive.py` |
| 符号链接与工作区逃逸 | 导入拒绝链接；源码与 Patch 目标 resolve 后必须位于允许根 | 拒绝捕获、Patch 或验证 | `tests/patching/test_safety.py` |
| 提示注入 | 请求将证据标为不可信；严格输出 Schema；模型不能指定本地 ID | 最多重试一次 | `tests/analysis/test_service.py` |
| 伪造 Evidence 引用 | 本地保存实际输入集合并逐项校验 | 未知引用不持久化 | `tests/analysis/test_service.py` |
| 恶意 Patch 修改测试/依赖 | canonical diff；允许根、保护路径、源码 Evidence 三重约束 | 不生成安全 Patch | `tests/patching/test_safety.py` |
| 批准后替换 Patch | Patch ID、Patch SHA-256、批准 SHA-256、Verification ID 内容绑定 | Docker 启动前拒绝 | `tests/verification/test_service.py` |
| 验证命令注入 | 命令和命令 ID 只来自配置并使用 argv 执行 | 配置无效时失败 | `src/bugcapsule/verification/service.py` |
| 容器访问公网或宿主秘密 | 非 root、只读、`network=none`、无 capabilities、无 Docker Socket、资源限制 | 记录验证失败 | `tests/verification/test_docker.py` |
| 秘密或 PII 外泄 | 捕获前、模型前、验证输出三次脱敏；报告不存原文 | 替换为固定标记 | `tests/capsule/test_redaction.py` |
| HTML 主动内容/外带 | Jinja 自动转义；无脚本/外链；严格 CSP、`nosniff`、附件下载 | 未完成闭环不生成 | `tests/reporting/test_service.py` |
| 本地跨站写操作 | loopback 绑定、Trusted Host、Origin 检查 | 返回 403 | `tests/test_web.py` |
| 基准或提交状态误导 | `simulated_data=true`；Live/Replay 分栏；失败保留分母；机器清单状态门禁 | 未就绪时拒绝 Release | `tests/test_submission_manifest.py` |

## 5. 数据最小化

模型请求只包含完成脱敏、按优先级选择且受字节上限约束的证据。系统不持久化原始提示或原始提供方响应。SQLite 只保存列表元数据；日志、Stack Trace、源码正文留在完整性受保护的归档中。

Live 模式会把已脱敏证据发送给用户配置的 OpenAI-compatible 提供方。提供方的数据保留、地域和训练策略不由 BugCapsule 控制，启用前必须由使用者评估。

## 6. 隔离假设

验证器依赖 Docker Engine、宿主内核和锁定镜像正确实施命名空间、只读挂载和资源限制。它显著缩小 Patch 的执行权限，但不能抵御 Docker/内核漏洞。比赛环境必须更新系统与 Docker，并避免在高价值宿主上验证不可信代码。

## 7. 残余风险

- 正则脱敏无法识别所有业务专有密钥和间接身份信息；共享前仍需人工复核；
- 允许修改的业务源码可能包含逻辑型恶意行为，固定回归不覆盖全部语义；
- 本地 loopback 服务仍信任当前操作系统账户；
- 依赖漏洞审计只覆盖已公开且能映射到包版本的公告；
- 仿真数据不能代表真实生产分布，12 案例 Replay 不能替代 Live 模型评测；
- 0.1 没有多租户授权、集中审计或远程 Agent 边界。

## 8. 安全报告

发现漏洞时请遵循 [`SECURITY.md`](../SECURITY.md) 私下报告。不要在公开 Issue、日志或附件中提交真实密钥、生产胶囊、个人数据或可直接利用的细节。
