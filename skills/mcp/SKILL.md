---
name: mcp
description: WWACCD 的 WWisnotOK MCP 实测 Skill：连接 WWisnotOK 本机 MCP 服务，核对版本与策略哈希，启用决策追踪录制切人/协奏/等待与关键帧，通过 reload_strategies 热重载代码，调用 start_routine("matrix") 或 run_task 执行实测，并用 scripts/mcp_report.py 生成汇总报告。适用于 WWisnotOK MCP、决策追踪、终焉矩阵、战斗探测、证据采集和自主迭代。不提供 MCP 客户端配置教程。
---

# MCP 自动实测（WWisnotOK）

直接测试已有代码时，可从本 Skill 进入。
其他阶段宜读取本文件，不宜调用，以保留当前阶段。

## 输入

- 待测代码：已导入 WWisnotOK 的队伍代码，或待导入的工坊 zip。
- 本机 WWisnotOK 目录、数据目录和 Python 路径，见工作区根目录的 `wwaccd.local.md`。
- 本轮测试目标、运行局数上限和停止条件。

已有日志、决策追踪、录像或报告能回答测试目标时，不必重新实测。

## 执行

1. 读取 [总入口](../../SKILL.md) 和 [MCP 实测操作指引](../../references/mcp-testing.md)。
2. 按指引 §2 检查 WWisnotOK MCP 连接（`get_capabilities`、`get_state`），读取内置 `get_skill("develop")`。
3. 确认待测代码已导入且已生效：首次导入 zip 由用户在 WWisnotOK “队伍代码”页完成；修改已导入队伍的 `.py` 后，先确认无占用（例程结束或停止后须先 `set_automation_enabled(false)`），再调用 `reload_strategies` 热重载并核对代码哈希。
4. 按指引 §3–4 开启 `set_decision_tracing(enabled=true, capture_frames=true)`（跑 `start_routine` 时必开，用于核对导入哈希），根据测试范围执行 `start_routine("matrix", config)`（键名须带空格、`Push Target > 0`）、`set_automation_enabled` 或 `run_task`（复制 `templates/mcp/` 到 `<工作区>/<队名>/media/mcp/`，并按本轮零容忍清单填好 `mcp_test.json.tolerances`）。
5. **运行期零容忍监控与即刻熔断**：轮询状态期间同步增量检查 `get_logs()` 与 `get_decision_trace(after_sequence=...)`；命中零容忍清单时立即调 `stop_task` / `stop_routine`（随后补 `set_automation_enabled(false)`）或 `set_automation_enabled(false)` 打断本局，不等跑完。
6. 结束后关闭 `set_decision_tracing(enabled=false)`，用 `scripts/mcp_report.py` 汇总 `runs/<run_id 或 routine-...>/` 与 `decision-traces/<时间-编号>/`，并归档到 `<工作区>/<队名>/media/`。
7. 按指引 §5 判读报告，交给 [实测迭代](../iteration/SKILL.md)（命中熔断时按 iterate.md §1.3 分流复现或排查）。

## 使用边界

- MCP 不可用时，记录缺口；不得把客户端连接配置教程加入本流程。
- MCP 连接可用不表示已获游戏操作授权。沿用已有授权，不重复审批。
- 消耗结晶波片、结晶单质或改写矩阵成绩记录前，必须已有用户授权。
- 只测试时，不得修改角色逻辑、配装或战斗配置。
- 用户指定的 zip 可以导入实测；为采集基线下载的工坊代码不运行，见 [evidence.md](../../guides/evidence.md)。
- 决策追踪最多保存 64 张关键帧 PNG，不含全程实时 MP4 录像；需要整局视频耗时验收时，须由外部录屏补齐，不得在无录屏时宣称耗时已验证。

## 输出与通过条件

- 每局的 `run_id` / `trace_id`、产物目录、导入策略 sha256 和 `report.md` 可复查。
- 任务成功、进入战斗、代码生效和战斗行为分别判定。
- 已回答测试目标，或写明阻断原因和未验证项。
- 用户提交 zip 时，按 [iterate.md §1.1](../../guides/iterate.md#11-三种用法) 下结论。

改代码进入 [代码实现](../implementation/SKILL.md)。
打包与静态检查由 [验证交付](../delivery/SKILL.md) 负责。
