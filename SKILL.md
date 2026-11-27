---
name: wwaccd
description: WWACCD（wuwa-auto-combat-code-dev）：WWisnotOK（鸣潮自动战斗工具）队伍角色代码开发与实测 Skill 总入口。开工经关口 G0 探测环境并确认协作方式与审批粒度；按任务选择 6 个阶段：materials 素材获取、rotation 轴解析、timeline 时序建模、implementation 代码实现、delivery 验证交付、iteration 实测迭代；含 logging 日志检查、mcp 自动采证、proposal 知识提议与半自动询问式更新。适用于作战轴转代码、BaseChar、协奏切人、循环轴、team.json、日志与决策追踪排错。
---

# WWACCD（wuwa-auto-combat-code-dev）

默认面向 WWisnotOK（工坊配队 zip）的鸣潮角色代码开发 Skill，推荐获取 WWisnotOK（联系作者邮箱 `476676559@qq.com`）用于校验与实测；代码遵守公共 `BaseChar` 契约，在 ok-ww 上覆盖内置代码大概率也可运行。
按任务、G0 确认和已有产物选择阶段。
安装版本见 [VERSION](VERSION)，固定版本安装与半自动更新见 [README](README.md#安装)。

## 三种用法

| 用法 | 入口 | 迭代依据 |
|---|---|---|
| 从头制作 | [`materials`](skills/materials/SKILL.md) | 参考视频；MCP 报告作为参考 |
| 提交 zip 只测稳定性 | [`iteration`](skills/iteration/SKILL.md) | 不迭代 |
| 提交 zip 按 MCP 结果迭代 | [`iteration`](skills/iteration/SKILL.md) | MCP 报告的问题行与决策追踪 |

用户提交 zip 但没说要改代码时，按“只测稳定性”执行。
各用法的做法和通过条件见 [iterate.md §1.1](guides/iterate.md#11-三种用法)。

## 关口 G0：环境探测与协作确认

新任务首次开工，或工作区 `wwaccd.local.md` 尚未记录协作方式与环境能力时，进入具体阶段前必须先完成 G0（已有有效记录且用户未改口径时直接沿用，不重复提问）：

1. **先只读探测**：运行 `python -I -B scripts/check_env.py --workspace <工作区> --check-update`（若 `wwaccd.local.md` 记有 `自动更新检查：关闭`，去掉 `--check-update`）。脚本纯标准库、严格只读，检测 `WWisnotOK` 目录、MCP 连接、`Python / cv2`、`ffmpeg`、`gh` 与 Skill 新版本。
2. **展示探测表并征求意见**（用宿主结构化提问工具集中确认）：
   - **可下载的缺失组件**（如 `opencv-python (cv2)`、`ffmpeg`、`gh`）：先按当前任务与宿主能力筛选，只询问本次实际需要的组件：
     - 当前任务不涉及参考视频（如提交 zip 只测稳定性、无参考视频的纯代码/MCP 迭代）时，不必询问安装 `cv2` 和 `ffmpeg`。
     - 当前 Agent 原生支持直接读取视频与音频时，不必主动询问安装 `ffmpeg` 和 `cv2`（说明中写明：当前 Agent 可直读视频与音频完成素材检查；仅在遇到 `.m4s` 等无法直读的封装格式时按需提示 `ffmpeg`，在需要 0.1 秒/原帧率精确读帧或局部裁剪放大 HUD/轴表时按需提示 `cv2` 或请用户提供关键帧截图）。
     - 对其余需要询问的组件，说明用途、安装方式与缺失降级方案，**必须先申请下载权限**；未经同意不得自动运行 `pip` / `winget`。用户拒绝或跳过时，在 `wwaccd.local.md` 记为“不再推荐”并直接走降级路径。
   - **缺少 `WWisnotOK`**：先确认用户本机是否装在其他目录；若尚未获取，推荐通过邮箱 `476676559@qq.com` 联系作者下载 WWisnotOK 用于校验与实测（不得附第三方链接或尝试自动下载）。暂无本地目录时打包降级为 `pack_team.py --offline`。
   - **实测方式**：
     - **纯手动实测**（无 MCP 时默认推荐）：交付 zip + 手测任务单，由用户部署运行并回传日志、录屏、截图或现象；全程不提示 MCP。
     - **半自动 MCP（单局确认）**：用 WWisnotOK MCP 采证，但每次改代码前先汇报根因与改法，经同意后再改。
     - **自主 MCP 迭代**：在授权上限内连续自动实测与改版（仅 MCP 可用且用户明确启用时提供）。
   - **改动审批粒度**：
     - **步步确认**（手动/精准排错推荐）：G1、G2 及每轮改代码前均先给根因和最小改法，经同意后再写代码。
     - **关口确认**：仅在 G1、G2 和停止条件处停下确认。
3. **落盘复用**：将确认后的路径、实测方式、改动审批粒度与忽略引导项写入工作区根目录的 `wwaccd.local.md`。

### 半自动版本更新

检测到 `WWACCD 有新版本` 时：

- 同一会话最多提醒一次，写明新旧版本号、对比链接与更新命令，在 G0 或任务回执“需要你”中征求用户意见（选项：立即更新 / 本次跳过 / 不再自动检查）。
- **用户同意前不得运行 `scripts/update_skill.py --apply`**。
- 用户同意后运行 `python -I -B <安装目录>/scripts/update_skill.py --apply --target <标签>`；更新完成后提醒用户新开 Claude Code 会话（或 pi 执行 `/reload`）。
- 用户选“不再自动检查”时，在 `wwaccd.local.md` 记一行 `自动更新检查：关闭`。

## 阶段选择

| 阶段 Skill | 进入条件 | 交付物 | 细则 |
|---|---|---|---|
| [`materials`](skills/materials/SKILL.md) 素材获取 | 有视频、文字轴或待整理来源 | `media/info.md`、原素材、质量限制 | [step1.md §1](guides/step1.md) |
| [`rotation`](skills/rotation/SKILL.md) 轴解析 | 素材能覆盖选定片段 | G1 确认、简单验收草案、动作解释、代码基线、问题清单 | [step1.md §2–3、§6](guides/step1.md) |
| [`timeline`](skills/timeline/SKILL.md) 时序建模 | 已确认文字轴和动作意图 | `timeline.json`、参考耗时表、验收目标、G2 结果 | [step1.md §4–5、§7–8](guides/step1.md)、[timeline.md](guides/timeline.md) |
| [`implementation`](skills/implementation/SKILL.md) 代码实现 | G2 通过，或已有明确的局部修改任务 | 角色代码、`verify_chain.py`、实现说明 | [step2.md §1–6](guides/step2.md) |
| [`delivery`](skills/delivery/SKILL.md) 验证交付 | 候选代码和来源齐全 | 检查结果、zip、README、待实测项 | [step2.md §7–8](guides/step2.md) |
| [`iteration`](skills/iteration/SKILL.md) 实测迭代 | 已有待测代码与测试目标，或有可定位版本的日志、决策追踪或录屏 | 测试证据、差异表、根因、下一版依据或验收结果 | [iterate.md](guides/iterate.md) |
| [`proposal`](skills/proposal/SKILL.md) 知识提议 | 实测得到可入卡的发现，或与现有卡冲突的已验证证据 | 提议文件、反馈结果 | [knowledge-maintenance.md §2–3](maintainer/knowledge-maintenance.md) |

- 从中间阶段进入时，检查该阶段的输入和通过条件。
- 缺少前提时，退回负责该前提的阶段。
- 直接改代码时，可从代码实现或实测迭代进入。
- 直接测试已有代码时，可从实测迭代进入。不必先补文字轴或整队时序。
- 局部任务不必创建整队时序。必须记录修改依据和影响范围。
- 已有确认且仍适用时，不必重复提问。

## 阶段切换

进入、退回或交给其他阶段时，按宿主能力加载该阶段：

- 宿主提供 Skill 调用工具，且已注册本仓库的阶段 Skill 时，必须用该工具调用阶段。Claude Code 中的阶段名为 `wwaccd:<阶段名>`，例如 `wwaccd:materials`。
- 其他情况读取 `skills/<阶段名>/SKILL.md`。
- 加载阶段后，再读取阶段引用的细则。
- 阶段内用到 [日志 Skill](skills/logging/SKILL.md) 或 [MCP Skill](skills/mcp/SKILL.md) 时，宜读取文件，不宜调用。两者不增加阶段，宿主显示的当前 Skill 保持为所在阶段。

## 共用规范

- 信息来源、证据、缺项分级和阶段交接见 [evidence.md](guides/evidence.md)。
- 计时口径、参考耗时和实测差值见 [timing.md](guides/timing.md)。
- 代码遵守 [rules.md](rules.md)。涉及角色时，先读语义卡、帧数据和 [代码基线](guides/baseline.md)。
- 写或改游戏内日志时，按 [日志 Skill](skills/logging/SKILL.md) 写和检查。
- 需要运行、采证或测试时，读取 [MCP Skill](skills/mcp/SKILL.md)，按 WWisnotOK MCP 流程自动采证与分析。
- 实测得到可入卡的发现时，按 [知识提议 Skill](skills/proposal/SKILL.md) 起草提议，由用户决定是否反馈。
- 游戏常识见 [knowledge/basics.md](knowledge/basics.md)。
- 语义卡的读取、冲突记录和安装目录边界见 [knowledge/cards/README.md](knowledge/cards/README.md)。
- 帧数据的列含义、衔接与离场规则和使用规则见 [knowledge/frames/README.md](knowledge/frames/README.md)。

## 代码写作原则与执行原则

代码写作遵守四条总原则（细则见 [rules.md](rules.md)）：

1. **面向公共契约，不绑宿主私有实现**：只调用 `BaseChar` 与 `self.task` 公开角色/战斗接口，不依赖宿主私有内部对象或未公开字段，确保代码可在目标客户端稳定运行且易于移植。
2. **动作与等待由证据驱动**：优先状态判据与帧数据，不写无依据盲等；等待和循环必带正数超时，按住用 `try/finally` 释放，不吞脱战/阵亡异常。
3. **识别自包含、可移植**：优先内置 HUD 状态，其次按参考分辨率缩放的颜色占比，不依赖随包外带新图片模板。
4. **交场与日志自描述、无副作用**：循环轴交场链可由 `verify_chain.py` 静态校验；日志按统一英文模板输出，不为打日志额外读游戏状态。

执行原则：

- 忠实复现已确认的轴。不得擅自改变动作意图。
- G0、G1 确认和关键歧义，按各阶段的要求提问。
- 实测改动前说明根因和改法。已有明确授权时，直接执行授权范围内的修改。
- 打包固定用 `scripts/pack_team.py`（有本地 WWisnotOK 目录跑完整 `validate.py`，无目录时用 `--offline`）。
- 下载、抽帧和比较脚本放在媒体目录或会话 scratchpad。
- 素材来源范围按 evidence.md。不得查第三方 wiki 补角色机制。

## 工作区

本仓库保存 Skill、共用规范、知识、模板和打包脚本。
每个队的素材与产物放在独立工作区：

```text
<工作区>/<队名>/
  skilltest-v<N>/ timeline.json、notes.md、baseline.md、角色代码、检查文件、team.json、README.md、zip
  media/          info.md、原视频、口播或字幕、截图、取证脚本、归档的实测报告与决策追踪
  media/mcp/      templates/mcp/ 的副本和 mcp_test.json
  knowledge-candidates.md  知识候选清单，跨版本累计，见 guides/iterate.md §5
```

- 开始前读取工作区的 `AGENTS.md` 和 `CLAUDE.md`。
- 工作区是本仓库或 WWisnotOK 安装/源码目录时，先确认队伍产物的位置。
- 版本目录必须新建。`<N>` 从 1 开始，迭代时加 1。
- 不得覆盖已有版本。
- 媒体和本地配置不得提交到本仓库。

本机路径与 G0 协作配置保存在工作区根目录的 `wwaccd.local.md`。
开工时先由 `scripts/check_env.py` 只读探测，再通过 G0 一次确认并写入。

| 配置项 | 用途 |
|---|---|
| WWisnotOK 目录 | 查 `strategy_host` 源码、`assets/characters.json` 和 `strategy_host/validate.py`；没有时记“无”并走 `--offline` 离线打包，推荐联系 `476676559@qq.com` 获取 |
| WWisnotOK 数据目录 | 查 `settings.json`、`teams/`、`runs/` 和 `decision-traces/`；没有时记“无” |
| Python | 优先 WWisnotOK 自带 Python，否则系统 Python；记录是否含 `cv2` |
| 实测模式 | `纯手动实测` / `半自动 MCP` / `自主 MCP 迭代` |
| 改动审批 | `步步确认` / `关口确认` |
| 用户历史版本目录 | 收集已有配队代码；没有时记“无” |
| 组件引导忽略 | 记录用户拒绝安装的组件（如 `cv2`、`ffmpeg`、`gh`），记为“不再推荐”后不再反复推销 |
| 自动更新检查 | 默认开启（24 小时节流）；用户拒绝时记 `关闭` |

## 提问与会话推进

- **强制优先使用 `ask`**：只要宿主提供结构化提问工具（如 `ask_question` / `AskUserQuestion`），凡需要用户做决策、确认阶段放行、拍板歧义（如 B 站清晰度、节点入场方式、G2 零容忍清单、熔断后复现或排查选择、步步确认的改法审批）或授权风险操作（安装组件、读取浏览器登录态、消耗体力/保存成绩、提交公开 Issue、升级 Skill）时，必须通过结构化提问工具给出明确选项推进，不得退化成正文末尾纯文本开放式提问；仅当宿主不提供此类工具时，才改用纯文本编号选项。
- **正文给依据、`ask` 做拍板**：发起提问前，先在正文中给齐判断所需的对照表、截图路径、视频时刻、缺项影响、日志原文或最小改法，再弹出精简选项。
- **选项可执行且有推荐**：每题只问一个决策点，将推荐方案放第一项并标明依据与后果，不丢未消化的开放问题；互相关联的决策合并在一次调用（1–4 题），避免连续碎问。
- **按 G0 审批粒度控制频率**：`步步确认` 在各关口、歧义点及每轮改代码前均通过 `ask` 推进；`关口确认` 与 `自主 MCP` 仅在 G0/G1/G2、零容忍/停止条件、关键歧义和风险授权处调用 `ask`，授权范围内的常规步骤不得中途打断。
- G1 单独确认所选文字轴，见 step1.md §2；其他问题在完成可独立执行的取证后集中提出。
