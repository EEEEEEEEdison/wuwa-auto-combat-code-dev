# WWisnotOK MCP 实测指引

本指引让 Agent 通过 WWisnotOK 本机 MCP 服务执行代码核对、决策追踪、定向战斗探测或终焉矩阵实测，并用 `scripts/mcp_report.py` 汇总证据。
如需获取 WWisnotOK，请通过邮箱 `476676559@qq.com` 联系作者；不使用 MCP 时请按 G0 走纯手动实测流程。

## 1 前提

| 项 | 要求 |
|---|---|
| WWisnotOK | 已安装或已构建（基线 `v0.4.7`），以 `WWisnotOK.exe --mcp`（或设置中开启 MCP）启动 |
| 权限 | 游戏以管理员身份运行时，WWisnotOK 也必须以管理员身份运行 |
| 宿主 | 已连接 WWisnotOK 本机 MCP（默认端口 `8766`，连接描述在 `%LOCALAPPDATA%\WWisnotOK\mcp\connection.json`，设了 `WWISNOTOK_DATA_DIR` 时在该目录的 `mcp\connection.json`） |
| 游戏 | 简体中文、16:9 画面、分辨率不低于 1280×720，窗口不得最小化 |
| 本机路径 | 工作区 `wwaccd.local.md` 记录 WWisnotOK 目录、数据目录与内置 Python（`runtime/python/python.exe`） |

GUI 和 MCP 共用同一个执行权：自动战斗、测试（`run_task`）、日常任务（`start_routine`）和策略重载（`reload_strategies`）不能同时运行。
客户端连接配置教程不在本指引范围内；WWisnotOK 官方接口细节以 `<WWisnotOK 目录>/docs/develop.md` 为准。

## 2 连接检查与内置指引

1. 调用 `get_capabilities()`，确认 `application` 为 `WWisnotOK`，记录应用版本和策略数量。
2. 调用 `get_state()`，查看游戏采集连接、画面状态、当前队伍、执行权归属和前台状态。
3. 调用 `get_skill(skill_id="develop")`，核对当前版本的 MCP 契约与测试脚本写法。

`screenshot()` 报错不表示 MCP 断开，连通性以 `get_capabilities()` 和 `get_state()` 为准。

## 3 导入代码与热重载

WWisnotOK 每支队伍支持内置代码（槽位 0）和 6 个导入位（槽位 1–6，位于 `<数据目录>/teams/<TeamKey>/imports/1..6/`）。

当前边界：`McpHost` 尚未提供独立的 `import_team` MCP 工具。

- **首次导入新 zip**：请用户在 WWisnotOK 的“队伍代码”页签点击导入并切换到对应导入位。
- **修改已导入队伍的 `.py` 后复测**：在确认无任务占用执行权后调用 `reload_strategies()` 热重载；若有语法或导入错误，引擎会保留旧类并返回报错。
- **核对代码生效**：每次 `run_task` 写入 `runs/<run_id>/strategy-versions.json`，每次决策追踪写入 `decision-traces/<时间-编号>/metadata.json`（含 `provenance.imported_strategies` 的 SHA-256）。核对其中对应 `<类名>.py` 的哈希前 16 位与本次候选包一致，不相等说明新代码未生效。

## 4 实测与采证方式

按测试目标选用以下三种方式之一；执行前按需把 `templates/mcp/` 副本放到 `<工作区>/<队名>/media/mcp/`：

| 模板 / 接口 | 用途 | 是否发送输入 | 主要产物 |
|---|---|---|---|
| `templates/mcp/capture_probe.py`（经 `run_task`） | 只读检查画面分辨率、`in_team()` 和当前加载的角色类 | 否 | `runs/<run_id>/run.log`、`result.json`、`strategy-versions.json`、`last-frame.png` |
| `templates/mcp/combat_probe.py`（经 `run_task`） | 用户在游戏内备好战斗场景，跑限定时长（默认 30 秒）的策略循环 | 是 | 同上；配合 `set_decision_tracing` 产出 `events.jsonl` 与关键帧 PNG |
| `start_routine("matrix", config)` | 调用 WWisnotOK 内置终焉矩阵例程（支持 `RunMode: "Push"` 奇点扩张凹分） | 是 | 例程日志、进度与决策追踪目录 |

### 标准采证流程

1. 调用 `get_state()` 确认无占用，可选跑一次 `capture_probe.py` 确认画面和队伍识别正常。
2. 调用 `set_decision_tracing(enabled=true, capture_frames=true)` 开启决策追踪。
   - 追踪会异步写入 `<数据目录>/decision-traces/<时间-编号>/`（最多 50,000 条事件、64 张关键帧 PNG，不阻塞战斗）。
   - 记录返回的 `folder` / `trace_id`。
3. 运行目标测试：
   - **定向战斗测试**：由用户备好战斗场景后，用 `run_task(file_path=<combat_probe.py 绝对路径>, timeout_seconds=90, team=[...])` 启动，轮询 `get_run_status(run_id)` 至终态，再用 `get_run_artifacts(run_id)` 取产物路径。
   - **已有自动战斗观察**：用 `set_automation_enabled(enabled=true)` 开启后，可用 `get_state()`、`get_logs()`、`get_decision_trace()` 增量观察，结束后关闭。
   - **终焉矩阵测试**：向用户确认 `matrix_routine` 参数（槽位、预设、增益、目标与是否保留成绩）后，调用 `start_routine(task="matrix", config=...)`，轮询 `routine_status()` 至结束。
4. 调用 `set_decision_tracing(enabled=false)` 结束记录并等待后台落盘完成。
5. 运行报告脚本汇总并归档到工作区媒体目录：

```text
<WWisnotOK python.exe> -I -B scripts/mcp_report.py [<runs/<run_id> 目录>] [--trace <decision-traces/<编号> 目录>] [--out <工作区>/<队名>/media/mcp_reports/<编号>]
```

说明：若团队使用带变轴/末轮的循环前缀（如 `S,C,Z`），追加 `--loop-prefixes S,C,Z`。

## 5 结果判读

`scripts/mcp_report.py` 输出 `report.md`、`events.json`（及归档的 `run.log`），按以下顺序判读：

1. **运行状态**：`status.json` 的 `State == "succeeded"` 仅说明测试任务未抛异常，不代表战斗轴通过。
2. **代码版本**：核对 `imported_sha256_16` 与本次交付 zip 内 `.py` 的 SHA-256 前 16 位是否一致。
3. **证据完整性**：检查 `decision_trace.summary` 的 `dropped_disk_events` 和 `skipped_frames`；若事件有丢弃，必须标明该次决策证据不完整。
4. **问题行与切人核对**：
   - 先看 `report.md` 的“问题行”（`fail`、`fallback`、`interrupt`、`WARN`/`ERROR`、`no_candidate_above_no_priority`）；
   - 再对照“切人决策摘要”（`switch_selected` 的 `target_index`、`has_intro`、`reason`）与“长耗时动作”（`action_ended >= 1500 ms`）；
   - 结合 `decision-traces` 保存的关键帧 PNG 定位首处偏离。
5. **录像与计时边界**：WWisnotOK 当前未内置全程实时 MP4 录像。需要逐节点视频耗时验收（`iterate.md §3`）时，必须同步录制外部视频（如 OBS），再按相同起止事件做视频对比；缺少整局录屏时必须写明“耗时未验证”。

## 6 故障与处理

| 现象 | 原因 | 处理 |
|---|---|---|
| `connection.json` 不存在或连不上 `127.0.0.1:8766` | WWisnotOK 未开启 MCP 或已重启换了端口/令牌 | 启动 `WWisnotOK.exe --mcp` 并重新读取 `connection.json` |
| 工具报执行权被占用 | 自动战斗、例程或上一个 `run_task` 尚未结束 | 先 `stop_task` / `stop_routine` / `set_automation_enabled(false)`，等状态归闲 |
| `reload_strategies` 失败 | 导入的 `.py` 存在语法、导入或继承错误 | 按返回的错误信息修正，先跑 `scripts/pack_team.py` 校验再重载 |
| 画面采集失败或 `frame.json` 为 `unavailable` | 游戏窗口最小化，或 WWisnotOK 权限低于管理员运行的游戏 | 恢复游戏窗口；以管理员身份重启 WWisnotOK |
| 导入哈希与候选 zip 不一致 | 未在 WWisnotOK 切换到新导入位，或未调用 `reload_strategies` | 在“队伍代码”页确认激活槽位并重载 |

同一步骤连续失败 2 次时，必须停止并向用户报告，不得换方法反复重试。

## 7 验证状态

- 本指引与 `templates/mcp/`、`scripts/mcp_report.py` 已按 WWisnotOK `v0.4.7` 源码接口核对并完成离线模拟验证。
- 实机端到端回归（`capture_probe.py`、`combat_probe.py`、`start_routine("matrix")` + `set_decision_tracing`）尚未在本版完成真机记录，首次真机实测后在此补记验证结果。
