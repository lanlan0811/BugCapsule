# BugCapsule 首次使用者可用性验收协议

本研究验证第一次接触项目的人能否仅依靠公开文档完成核心闭环。参与者必须是 3–5 名未参与 BugCapsule 开发的志愿者；开发者自测、估算或虚构记录不能替代真实结果。

## 1. 研究目标

- 首次安装到 Web 健康检查的中位时间不超过 10 分钟；
- 参与者能复现 `500 → 500 → 503` 并说明一个 Evidence 引用；
- 参与者能辨认 Replay/Live 边界，核对 Patch 摘要并完成隔离验证；
- 识别 README、环境配置、Docker、捕获、导航、批准和报告中的文档缺口。

## 2. 参与与隐私

参与前说明任务、记录字段和发布范围，并取得匿名汇总同意。只使用 `P01` 形式编号；不采集姓名、账号、公司、联系方式、设备标识、用户路径、密钥、生产日志或自由文本。原始响应保存在仓库外，只提交聚合后的 `summary.json`。

不同意匿名发布的记录不得进入汇总。参与者可随时停止，不影响其任何权益。

正式样本必须由参与者本人执行所有项目命令和界面操作，记录为 `execution_mode: participant_operated`。AI 助手、主持人或其他人代为输入、运行或点击的会话只能记录为 `assistant_operated` 试运行，用于改进产品和文档，不计入 3–5 名正式样本；汇总器会拒绝此类记录。

## 3. 首次使用任务

1. 在全新 Windows 10/11 或 Linux 环境克隆仓库；
2. 只阅读 README，安装 Python、uv 和 Docker；
3. 复制 `.env.example`，运行 `uv run bugcapsule doctor`；
4. 启动主演示，复现连接池耗尽；
5. 捕获胶囊，在 Web 中找到 Trace、日志和源码证据；
6. 用 Replay 生成根因与 Patch，核对完整 SHA-256；
7. 明确批准并运行隔离验证，下载 HTML 报告；
8. 执行 reset，确认场景可以再次运行。

计时从开始阅读 README 到 Web 健康检查成功。参与者首次卡住时主持人保持观察；持续 3 分钟后才可给最小提示，并增加 `hint_count`、记录对应 `blocking_step`。提示只能指出应重读的 README 小节或任务目标，不能替参与者操作。

## 4. 记录与汇总

每名参与者使用一个严格 JSON 文件，字段与枚举见 [`output/usability/README.md`](../output/usability/README.md)。主持人的去标识观察笔记单独保存在仓库外，不复制进 JSON。

```powershell
$ResponseDir = Read-Host '请输入仓库外的响应目录'
uv run python scripts/aggregate_usability_study.py `
  --input-dir $ResponseDir `
  --output output\usability\summary.json
```

macOS / Linux：

```bash
read -r -p '请输入仓库外的响应目录: ' response_dir
uv run python scripts/aggregate_usability_study.py \
  --input-dir "$response_dir" \
  --output output/usability/summary.json
```

汇总器拒绝未知字段、自由文本、重复参与者、越界值、未同意记录、非参与者本人操作记录和非 3–5 人输入。输出只保留群组规模、系统分布、中位启动时间、任务完成率、失败检查、阻塞步骤、文档缺口、信心和提示数，不包含逐人记录。

## 5. 验收与改进

维护者在提交汇总前核对：输入均有同意、输出不含个体标识、结果与原始结构化记录一致。对高频文档缺口先修正文档，再邀请至少一名新参与者复核受影响步骤；原有结果不回填、不覆盖。

达到 3–5 份有效 `participant_operated` 记录前不得创建占位 `summary.json`。当前已有试运行反馈，但正式独立样本仍为外部待完成。
