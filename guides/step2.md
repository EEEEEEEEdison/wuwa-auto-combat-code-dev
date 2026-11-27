# 步骤 2：实现、验证与交付

整队生成的前提是 [G2](timeline.md#3-关口-g2) 通过。
局部修改的输入见 [代码实现 Skill](../skills/implementation/SKILL.md)。
代码遵守 [rules.md](../rules.md)。
骨架见 [workshop.md](../references/workshop.md)，日志见 [logging.md](../references/logging.md)。
API 查 [basechar-api.md](../references/basechar-api.md) 和 [task-api.md](../references/task-api.md)。

## 1 目标代码形式

- 工坊循环轴使用 3 个直接继承 `BaseChar` 的类。
- f/s 节点按 rules.md 第 6 组组织。
- 共用协议和日志 helper 按 workshop.md 保持一致。
- 优先调用框架函数，新增实现按 rules.md 的决策阶梯判断。
- 不引入 DSL（自定义领域语言）。

## 2 节点映射

一个节点对应薄包装 `perform_<f或s><序号>()` 和动作体 `_action_<名字>(tag, nxt)`。
动作完全相同时，可共用动作体。
薄包装最后一行固定为：

```python
self._force_switch_to(self._find_teammate('<下一个类名>'), '<下个节点模式>')
```

分发器、`_entry_mode`、`_startup_done`、`reset_state` 按骨架实现。
节点注释标出轴原文、视频区间和时序节点编号。
动作体落实前置、触发、完成、取消和依赖判据。
不得只按记号顺序拼接函数。

## 3 记号与判据到代码

以下列出技能与按键、触发等待和切人涉及的全部公开函数及其行为边界（签名与坑点详见 [basechar-api.md](../references/basechar-api.md) 和 [task-api.md](../references/task-api.md)）。Agent 按模型已确认的按法、触发条件、完成信号和副作用自行选用最匹配的函数，不设固定优先级约束。

### 技能与按键可用函数

| 类别 | 可用函数 | 行为、副作用与适用场景 |
|---|---|---|
| E 共鸣技能 | `click_resonance(time_out=<正数>, has_animation=..., send_click=..., click_f=...)` | 循环发 E（`send_click=True` 会交替点普攻）直到进 CD 或超时，首次发键记 `last_res`，返回 `(clicked, duration, animated)`；不进冷却的多段/强化 E 用它会一直按到超时 |
| E 共鸣技能 | `send_resonance_key(post_sleep=0, down_time=0.01)` | 按配置键单发一次 E，不等确认、不记时间戳；需计时时在确认后调 `record_resonance_use()` |
| E 共鸣技能 | `self.task.wait_until(<完成条件>, post_action=self.send_resonance_key, time_out=<正数>)` | 反复发 E 且不插普攻，直到指定条件（如进 CD 或图标变化）成立 |
| E / R / Q 长按 | `self.task.send_key(self.get_*_key(), down_time=<秒>)` | 按配置键阻塞式固定时长长按（期间不抓帧、不做战斗检查、不能中途松开） |
| E / R / Q 长按 | `self.task.send_key_down(key)` / `send_key_up(key)` | 非阻塞按住与松开，按住期间可 `wait_until` 观察画面按条件松开；必须放进 `try/finally` 释放 |
| R 共鸣解放 | `click_liberation(con_less_than=-1, send_click=False, wait_if_cd_ready=0.1, animation_min_duration=0, click_f=True)` | 发 R 后 0.4 秒内等 `not in_team()` 确认演出，演出结束记冻结与 `last_liberation`；无动画或演出延迟 >0.4 秒返回 `False`；后接按秒动作时可设 `click_f=False` |
| R 共鸣解放 | `send_liberation_key(after_sleep=0, down_time=0.01)` | 按配置键单发一次 R，不等演出、不记时间戳；适合无动画 R、延迟演出 R 或自定义确认条件，确认后按需调 `record_liberation_use()` |
| Q 声骸技能 | `click_echo(time_out=0)` | 单发模式：就绪时发一次并记 `last_echo`；进入时不可用会退入循环并立即超时返回 `False` |
| Q 声骸技能 | `click_echo(duration=..., time_out=<正数>)` | 循环模式：每 0.1 秒发 Q 直到进 CD 或按满 `duration`；超时一律返回 `False`（即使已按出） |
| Q 声骸技能 | `send_echo_key(after_sleep=0, down_time=0.01)` | 按配置键单发一次 Q，不等确认、不记时间戳；确认后按需调 `record_echo_use()` |
| A 普攻 | `self.click()` / `self.normal_attack()` / `self.click_with_interval(interval=0.1)` | 单次普攻点击（`normal_attack` 先做战斗检查；`click_with_interval` 适合做 `wait_until` 的 `post_action`） |
| A 普攻 | `continues_normal_attack(duration, interval=0.1, after_sleep=0, click_resonance_if_ready_and_return=False, until_con_full=False)` | 按真实时间持续普攻，内置 `sleep` 与战斗检查；开启 `click_resonance_if_ready_and_return` 时内部无参调 `click_resonance`（上限 15 秒） |
| A 普攻 | `continues_click_until(condition, time_out, interval=0.1)` | 持续普攻直到 `condition()` 成立或超时（带 `check_combat`），命中返回 `True`、超时返回 `False` |
| Z 重击 | `heavy_click_forte(check_fun=...)` | 条件为真时按住左键直到 `not check_fun()` 或 2 秒超时后松开（默认用 `is_forte_full`，自定义判断须显式传入） |
| Z 重击 | `heavy_attack(duration=0.6)` | 固定时长按住左键（异常中断时中间 `sleep` 可能跳过 `mouse_up`） |
| Z 重击 | `self.task.mouse_down()` / `self.task.mouse_up()` | 手写按住左键，配合 `sleep` 或 `wait_until` 按任意时长/条件松开；必须放进 `try/finally` 释放 |
| 闪避 | `self.task.send_key(self.task.key_config.get('Dodge Key'))` / `continues_right_click(duration, interval=0.1, direction_key=None)` | 单次闪避或持续右键闪避（`continues_right_click` 不做战斗检查） |
| 跳跃 / 通用键 / 锁敌 | `self.task.jump()` / `continues_click(key, duration, interval=0.1)` / `self.task.middle_click_relative(x, y, ...)` | 按配置键跳跃；持续发任意配置键（不做战斗检查）；中键锁定目标 |

### 触发、状态判断与等待可用函数

| 类别 | 可用函数 | 行为与边界 |
|---|---|---|
| 条件等待 | `self.task.wait_until(condition, time_out=<正数>, pre_action=..., post_action=..., settle_time=...)` | 每轮抓新帧并判 `condition`；`time_out` 超过 1 秒传 `pre_action=self.check_combat`；防单帧闪烁传 `settle_time` |
| 定时等待 / 抓帧 | `self.sleep(sec, check_combat=True)` / `self.task.next_frame()` | `sleep` 按真实时间等待并做战斗检查（不得使用 `time.sleep()`）；手写轮询循环每轮须调 `sleep` 或 `next_frame()` |
| 入场/落地等待 | `self.wait_down(click=True)` / `self.wait_intro(time_out=1.2, click=True)` | `wait_down` 等入场动作结束或落地；`wait_intro` 在 `has_intro` 为真时等 E 或 R 可用 |
| 计时与演出冻结 | `self.time_elapsed_accounting_for_freeze(anchor, intro_motion_freeze=False)`、`add_freeze_duration(start, duration=-1.0, freeze_time=0.1)`、`self.task.in_liberation`、`time.time() - start` | 扣冻结的游戏内时长用前者，手写演出等待后用 `add_freeze_duration` 记账并成对置位/复位 `in_liberation`；循环真实时间上限用 `time.time() - start` |
| 技能与资源判断 | `resonance_available()`、`echo_available()`、`liberation_available()`、`extra_action_available()`、`available(box, check_color=True, check_cd=True)`、`current_resonance()` / `current_echo()` / `current_liberation()`、`has_cd(box)`、`is_con_full()`、`get_current_con()`、`is_forte_full()` / `is_mouse_forte_full()` / `is_e_forte_full()`、`self.task.in_team()`、`self.flying()` / `flying_based_on_resonance()`、`has_long_action()` / `has_long_action2()` / `has_short_action()`、`check_outro()`、`is_first_engage()` | `resonance_available`/`echo_available` 只看 CD 数字，判图标亮需配 `current_*() > 0`；`get_current_con()` 会写入粘滞缓存 `current_con`，只判满槽用 `is_con_full()` |

- `ready` 触发：满足可用判据即执行，不加保险等待。
- `state` 触发：等明确的状态变化后执行。
- `delay` 触发：使用模型规定的锚点和时钟，不从日志 `ok` 擅自改算。
- `immediate` 触发：前置条件满足后直接执行。
- `timing: condition` 不得改成固定时长。
- 多段及强化 E/R 按语义卡确认目标段；不进冷却的段不得循环按到出现冷却。
- 手写按住操作必须放进 `try/finally`，在 `finally` 中松开（rules.md 5-4）；技能键位走配置，不得写死。

### 切人可用函数与约束

| 可用函数 | 行为、副作用与适用场景 |
|---|---|
| `self._force_switch_to(self._find_teammate('<类名>'), '<mode>')` | 工坊循环轴强切：设置目标 `_entry_mode` 与 `_force_switch_me` 后在 `try/finally` 中调 `switch_next_char()`；`verify_chain.py` 靠字面量扫描该行 |
| `self.switch_next_char(free_intro=False, target_low_con=False)` | 战斗中切人；仅机制允许不满协奏出延奏（如今汐）时传 `free_intro=True`；无候选人时仅普攻 0.2 秒返回；`in_team()` 为假（演出中）调用会报脱战 |
| `get_switch_priority(current_char, has_intro, target_low_con)` | 普通队伍在目标角色上覆写以决定切人优先级；不在场时调用，只读时间戳、已存状态与 `*_available()` |
| `need_fast_perform()` | 检查是否有非在场队友不带 intro 即返回 `MUST`，放在可跳过动作前决定是否提前切人 |
| `wait_switch()` | 在目标角色上覆写以延后被切入；必须自带超时且只读时间戳和已存状态 |
| `self.wait_switch_cd()` | 距本次上场不足 1 秒时普攻补足剩余时间（`normal_attack_until_can_switch()` 为忙等反例，不宜使用） |
| `self.task._target_has_switch_cd(target)` | 配合 `wait_until` 等待目标切人冷却结束再切（rules.md 3-12） |
| `self.f_break(check_f_on_switch=..., force=...)` | 控制切人前/后或节点内是否触发击破演出（rules.md 3-9、3-10） |
| `self.switch_other_char()` | 仅在 `on_combat_end` 中使用，战斗中不得调用 |

- 原轴要求变奏时，按已确认的协奏和结束判据离场。
- 只有 `allow_fill: true` 才能额外补协奏。
- 原轴要求普通切人时，完成最后动作即切，不加补资源动作。
- `↓` 只表示原轴的延奏意图，不能独立决定补满策略。
- 特殊机制和目标切人冷却按模型与 rules.md 3-7、3-12 处理。
- 证据不足时退回建模，不得默认补满。

## 4 时限与未就绪

参考耗时、按住时长和超时保护分别确定。
不得统一使用“视频时长 × 1.5、至少 1 秒”。
每个等待必须记录条件、正数时限、依据和超时处理。
时限宜参考已核实的动作范围、框架语义和实测波动。
条件成立后即继续，不得等满保护时限。
游戏持续时间与真实循环上限按 rules.md 2-5 区分。
超过 1 秒的等待，加 `pre_action=self.check_combat`。

技能未就绪时，先核对 `precondition` 和 `trigger`。
只有模型允许补资源时，才能一边普攻一边等。
超时后按 `wait.on_timeout` 处理，并记录 fallback。
跳过、重试和离场不得自动采用统一策略。
关键处理没有依据时，退回 G2。
战斗结束、角色死亡异常不捕获，交给框架处理。

## 5 日志与实现交接

按 logging.md、骨架和 [日志 Skill](../skills/logging/SKILL.md) 记录：

- 节点 `enter`、`exit`；
- 技能 `cast X: ok|fail`，没有确认信号的发键写 `send X`；
- 分支 `decide`；
- 兜底 `fallback`；
- 上限 ≥2s 的条件等待前打 `wait`。

核对日志与实际事件的关系。
不得用 `ok` 直接替代所有生效时刻。
整队骨架日志处理遵守 rules.md 6-6、6-7。
局部修改保留已有诊断字段，按动作阶段适配。
实现选择、借用来源及待测项写入 `notes.md`。
参考耗时保留在 timeline，不复制成无来源常量。

## 6 verify_chain

复制 [verify_chain.py](../templates/verify_chain.py) 到版本目录。
按模型填 `FILES`、`EXPECTED`、`STARTUP_END`。
运行并确认通过。
在临时副本中改错一条边，确认报错。
最终候选必须恢复正确边并再次通过。

检查只覆盖静态交场链。
这项检查不能证明协奏、技能效果或耗时符合。

## 7 自检清单

适用项必须通过后才能交付。
局部任务不适用的项目，记录原因。

- [ ] 只做本次角色文件的内存语法检查：`python -I -B -c "import ast, sys; [ast.parse(open(p, encoding='utf-8-sig').read(), p) for p in sys.argv[1:]]" <文件...>`（不落盘 `__pycache__`）。
- [ ] 交场链正常通过，变异时确实失败，最终候选再次通过。
- [ ] `self.X()`、`self.task.X()` 均能在源码或本文件定义中定位。
- [ ] 每个动作的触发、完成和切人处理与模型一致。
- [ ] 普通切人没有被补协奏或保险等待改成变奏。
- [ ] 没有把参考总时长直接作为等待时长。
- [ ] 依赖、延迟锚点和时钟与模型一致。
- [ ] 无写死按键，无 `time.sleep`。
- [ ] `wait_until` 与 `click_resonance` 有正数时限。
- [ ] 手写循环有真实时间上限，每轮调用 `sleep` 或 `next_frame`。
- [ ] 不吞战斗异常；日志 helper 按规则处理自身异常。
- [ ] 3 个文件的共用协议与日志 helper 逐字一致。
- [ ] 节点日志齐全；fallback 用 warning；日志不额外读状态。
- [ ] `scripts/check_logs.py` 报 0 条问题，或剩下的问题已在 README 写明原因。
- [ ] 待测项均有预期、验证办法和失败处理。

## 8 打包交付

1. 从已有确认读取 `name`、`description`、`author`、`version`。缺少时集中提问。
2. 在新的 `<队名>/skilltest-v<N>/` 放置 3 个角色文件、`verify_chain.py` 和 `team.json`。
3. 写 README，列出交场链、轴与视频节点对应、参考耗时入口、试验假设和未实测项。
4. 写 `notes.md`，记录来源、实现选择及实际检查结果。
5. 用配置的 Python 执行 `scripts/pack_team.py <版本目录> <WWisnotOK 目录>`；G0 确认本机无 `WWisnotOK` 目录时，改用 `scripts/pack_team.py <版本目录> --offline`，并在 README 标明“离线静态校验，未运行 `strategy_host/validate.py`”。
6. 核对 zip 与声明的打包源逐字节一致。
7. 若 G0 选定**纯手动实测**，交付时必须附一张不超过 3 行的**本轮手测任务单**：
   - 本版改了哪 1 个变量或目标；
   - 进游戏重点观察哪 1–2 个节点或时刻；
   - 若失败，优先带回哪几样最小证据（例如日志片段 + 指定节点的 1 张截图）。
8. 交付 zip 路径、检查结果、手测任务单（手动模式）及待实测项，进入 [iterate.md](iterate.md)。

`team.json.team` 用逗号分隔的英文显示名，按不区分大小写的字母序排列。
角色表与显示名以 `<WWisnotOK 目录>/assets/characters.json` 和 `Core/Contracts.cs` 的 `Names.Aliases` 为准（漂泊者类名为 `Rover`）。
`description` 必须写“一号位<中文名>”标明开场角色，如“一号位坎特蕾拉”。

项目要求清洗时，先生成清洗后的 3 个 `.py`。
使用 `--src <清洗结果目录>`，并把该目录记为实际打包源。
字节一致检查针对实际打包源；清洗前后的行为另行核对。

zip 平铺 `team.json` 和 3 个角色文件。
文件名为 `<类名>_<类名>_<类名>_<author>_<version>.zip`。
`pack_team.py` 调用 WWisnotOK `strategy_host/validate.py` 输出 `OK` 才通过。
`REFUSE` 表示同名包已存在，必须使用新版本号。
`FAIL` 时按报错修正，再运行同一打包脚本。
不得另写打包脚本。

交付 README 的出处引用原视频、文字轴和本案 timeline。
迭代证据的路径与分析记录写入 notes，见 iterate.md §4。
