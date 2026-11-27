# 日志规范

本篇对应日志组规则 L-0 ～ L-11，外加工坊循环轴相关的 6-6 / 6-7。
写日志的流程和交付前自检见 [日志 Skill](../skills/logging/SKILL.md)，词表检查用 `scripts/check_logs.py`。

## 事实

| 事实 | 依据 |
|---|---|
| Python 侧 `Logger.get_logger(name)` 返回标准库 `logging.getLogger(name)`，经 `PipeLog` 发往 C# 宿主；角色日志由 C# 自动添加中文角色名前缀（`坎特蕾拉：<消息>`） | WWisnotOK `strategy_host/ok/__init__.py`、`strategy_host/worker.py:178-188`、`Strategies/StrategyRuntime.cs:154-160` |
| `run_task` 落盘的 `runs/<run_id>/run.log` 格式为 `2026-11-26T00:12:34.5678900+08:00 [INFO] 坎特蕾拉：<消息>`，带完整日期与高精度时间戳 | WWisnotOK `Services/TestRunner.cs:42` |
| Python 角色日志的 `INFO` / `DEBUG` 记入详情层文件，`WARNING` / `ERROR` 同步进入运行记录；默认日志级别为 `INFO` | WWisnotOK `Strategies/StrategyRuntime.cs:151-159`、`Services/AppStore.cs:51-52` |
| 切人选择、协奏证据、冷却采样和动作等待由 C# 决策追踪（`decision-traces/<时间-编号>/events.jsonl`）结构化记录 | WWisnotOK `Core/CombatDecisionTrace.cs`、`Core/DecisionOperations.cs` |

### 引擎与决策追踪已记录的项

角色代码不用重复这些记录（L-9）：

- 切人目标、切人原因、候选优先级、治疗锁定与切人冷却（`decision-traces` `switch_selected`）；
- 协奏读数来源与满协奏缓存（`decision-traces` `concerto`）；
- 技能点击、长等待与持续普攻起止耗时（`decision-traces` `action_started` / `action_ended`）；
- 脱战与角色阵亡异常（由 C# 战斗引擎记录并终止本轮）。

---

## L-1 级别

| 级别 | 用途 |
|---|---|
| `info` | 实机日志里要看到的一切：本篇的模板行 |
| `warning` | 兜底分支被触发（`fallback`） |
| `debug` | 高频细节，例如颜色占比、循环内状态。正式版看不到 |
| `error` | **角色代码不用**，留给框架报技能失败和脱战 |

## L-2 模板

```
[TAG] event[: ok|fail] [reason=code] [key=value ...]
```

模板分两层：

- **通用层**：所有角色代码都用，不带 `[TAG]`：`event[: ok|fail] [reason=code] [key=value ...]`。
- **工坊循环轴层**：只用于套用循环轴骨架（workshop.md）的代码，在通用层前加节点标签 `[F1]` / `[S2]`，即 mode 大写。

各部分的写法：

- `event`：取自下方的事件词表，用小写短语。
- `: ok` / `: fail`：只用于尝试类事件（cast、retry、switch）。`decide` / `fallback` 的冒号后写分支名，`wait` 的冒号后写等什么。
- `reason=`：取自 reason 词表（L-7）。fail 行分不出原因时省略，不新造码，也不为此额外读状态（L-8）；做判断时已经读到的值照常作为字段写上。
- `key=value`：取自字段词表（L-6）。
- 不写角色名，Logger 已经加了 `类名:` 前缀。

### 事件词表

| 事件 | 用途 | 例 |
|---|---|---|
| `enter` | 进入本角色逻辑。带 `mode=`，同时用作与视频比对的时刻锚点 | `enter mode=intro` |
| `decide: <branch>` | 选了哪个分支，以及决定该分支的状态值 | `decide: liberate lib_ready=True con=1.000` |
| `cast E` / `cast R` / `cast echo` / `cast heavy` | 技能尝试与结果 | `cast R: fail reason=no_animation lib_ready=False in_team=True` |
| `retry E` / `retry R` / `retry echo` | 重试（5-3 的第 2 次尝试） | `retry R: ok attempt=2` |
| `send <技能>` | 只发键、没有可靠确认信号的技能，不写 ok/fail | `send E skill=vortex` |
| `attack` | 手写普攻循环结束时的汇总（L-4）。按组打时每组一行，带 `group`、`ended`。用 `continues_normal_attack` 等框架函数时不打：`decide` 行已经记录了分支，时长看时间戳差（L-5） | `attack attacks=12`、`attack group=2 ended=True` |
| `wait: <what>` | 上限 ≥2s 的条件等待开始前打，带 `timeout`（L-3） | `wait: con_full timeout=6.00` |
| `fallback: <what>` | 兜底分支被触发，用 **warning** 级别。早退分支也算兜底 | `fallback: switch_without_r` |
| `exit` | 离场：原因和下一个上场的人 | `exit reason=done next=Phrolova.f4` |
| `switch` | 角色代码自己发切人键时的结果，例如带着按住的左键切人 | `switch: ok next=Cantarella held=True switch_s=0.09` |
| `interrupt` | 角色代码自己识别到的中断：超时、交还框架等 | `interrupt reason=startup_in_progress` |
| `probe <对象>` | 取证行（L-11），字段不受 L-6 词表限制 | `probe icon icon=vortex inner=0.065` |

新事件要先加进本表再用（L-6 / L-7 同理）。

## L-3 必打时机

1. **`enter`**：每次进入本角色逻辑时打一条，带入场方式与实际变奏状态 `has_intro`。`mode` 按以下优先级取值：
   1. `forced`：被循环轴 `_force_switch_to` 指定入场；
   2. `intro`：`has_intro` 为真；
   3. `natural`：其余情况。

   循环轴的 `enter` 行必须同时输出 `has_intro=bool(self.has_intro)`（读已有内存属性，不触发额外读屏，符合 L-8），供日志与 MCP 零容忍监控直接核对入场方式。
2. **`decide`**：每个有分支的决策点，写选了哪支，以及决定该分支的状态值。
3. **`cast X: ok|fail`**：每次技能尝试的结果。失败时带 `reason` 和当时已有的关键状态。
4. **`fallback`**：兜底分支被触发时打。
5. **`exit`**：离场原因和下一个上场的人。如果不知道是谁（交给框架选），就写 `next=framework`。
6. **`interrupt`**：超时、把控制权交还框架等情况。
7. **`wait`**：等某个条件成立、上限 ≥2s 的等待（`wait_until`、手写轮询循环），开始前打一条，带 `timeout=<上限>`。代码卡住时，最后一行就是卡点。等待正常结束不另打行，结果写在后面的 `cast` / `decide` 行里。

注意：脱战和阵亡是异常，会直接穿过角色代码（5-6），角色代码不捕获这两种异常，也就打不了这类日志。框架会打。

## L-4 不打的时机

循环里每一帧、每一次点击都不打日志。只在两种时候打：

- 状态翻转时；
- 手写循环结束时打一条汇总，例如 `attack attacks=12`。框架普攻函数（`continues_normal_attack` 等）不返回点击次数，不打这一行。

`probe` 行同样只在状态翻转时打。

## L-5 耗时

- 一个动作内部、起止两个时刻都由代码自己量到的耗时，写成 `<名称>_s` 字段：真实时间 `time.time()` 之差，2 位小数。例如按键到出冷却数字写 `cd_s`。
- 跨动作的耗时不写，看两行的时间戳差（精确到毫秒）。
- 耗时字段必须是本次实测值。常量和配置值不得写成 `_s` 字段。
- 字段名和起止点取自 L-6 的耗时字段表。

## L-6 字段词表与格式

**格式**

| 类型 | 写法 |
|---|---|
| 布尔 | `True` / `False` |
| 比例 | 3 位小数，例如 `con=0.873` |
| 其他浮点 | 2 位小数 |
| 整数、字符串 | 原样 |

字段名用 snake_case，并且只用下面两张表里的名字。新字段先加进表再用。

**字段**

| 字段 | 类型 | 含义（来源） |
|---|---|---|
| `mode` | str | 入场方式 `intro`、`natural`、`forced`；循环轴中是节点 mode |
| `has_intro` | bool | 本次上场是否带变奏入场（读已有属性 `self.has_intro`，不触发额外读屏，符合 L-8） |
| `next` | str | 下一个上场的人：类名，可以带 `.mode`；交给框架时写 `framework` |
| `con` | ratio | 协奏（`get_current_con()`，**只用判断时已读到的值**，见 L-8） |
| `con_full` | bool | `is_con_full()` |
| `res_ready` | bool | `resonance_available()` |
| `echo_ready` | bool | `echo_available()` |
| `lib_ready` | bool | `liberation_available()` |
| `res_pct` | ratio | `current_resonance()`，E 格白像素占比，不是能量进度 |
| `cd` | bool | 本行所述技能的 `has_cd(...)` |
| `in_team` | bool | `task.in_team()[0]`（演出中为 False） |
| `flying` | bool | `flying()` |
| `forte` | bool | 回路判断（`is_forte_full` 或角色专用变体）的结果 |
| `heavy` | bool | `heavy_click_forte` 的返回值是否为真：True = 2 秒内回路被消耗；False = 没按或按满 2 秒未消耗（两者都返回 None，分不开，fail 行因此不带 reason） |
| `attacks` | int | 本段普攻实际点击次数 |
| `attempt` | int | 第几次尝试（5-3） |
| `skill` | str | 同一个键能放出几种技能时，本行是哪一种。取值按图标起名，不用“强化”“终结”这类各处叫法不一的词，例如坎特蕾拉 E 的 `umbrella`（伞形）/ `vortex`（粉圈漩涡） |
| `round` | int | 循环轮次 |
| `group` | int | 按组打普攻时的第几组，从 1 开始；0 表示一组都没打 |
| `ended` | bool | 本组内认到状态结束，提前收手 |
| `sends` | int | 本次尝试实际发键次数 |
| `presses` | int | 按住类动作实际按下次数（含松开重按） |
| `press` | str | 按法：`hold`（按住）或 `tap`（点按） |
| `held` | bool | 带着按住的键切入或切出 |
| `timeout` | float | `wait` 行的等待上限，单位秒 |
| `note5` | bool | 弗洛洛五线谱第 5 个音符格亮着（工坊弗坎嘉 `is_note5_lit()`） |

**耗时字段**

起点都是本事件的起点：尝试类事件是第一次发键，`wait` 是开始等，`attack` 和 `decide` 是开始普攻。

| 字段 | 终点 |
|---|---|
| `ready_s` | 判到技能可用 |
| `cd_s` | 出冷却数字 |
| `done_s` | 认到其他完成信号，如进入目标状态 |
| `fire_s` | 认到出招 |
| `held_s` | 松开按住的键 |
| `switch_s` | 认到换人 |
| `wait_s` | 等待结束 |
| `attack_s` | 普攻结束，或判定出本行的分支 |

## L-7 reason 词表

| reason | 含义 |
|---|---|
| `done` | 正常完成（exit 用） |
| `not_ready` | 进入时技能、资源不满足 |
| `timeout` | 等确认信号超时，并且没有更具体的码可用（E / 声骸用 `icon_still_lit`，R 用 `no_animation`，按住用 `not_consumed`） |
| `no_animation` | 按了 R 但没确认到演出（`not in_team` 没出现） |
| `icon_still_lit` | 按键后图标仍亮着，没进 CD |
| `not_consumed` | 按住后回路没被消耗 |
| `out_of_combat` | 角色代码自己判断出已脱战（例如工坊 `skip_combat_check` 放手时） |
| `startup_in_progress` | 循环轴：启动轴进行中，却发生了自然入场，于是交还框架 |
| `unknown_mode` | 循环轴：`perform_<mode>` 不存在，于是交还框架 |
| `fast_switch` | `need_fast_perform()` 为真，跳过可选动作提前切人（3-4） |
| `teammate_missing` | 循环轴：`_find_teammate` 没找到目标，于是交给框架选人 |

## L-8 不为日志额外读状态

**严格版**：不为打日志额外读取任何状态，失败路径也不例外。需要的值在做判断时就存进变量，判断和日志共用同一个值。

```python
lib_ready = self.liberation_available()
con = self.get_current_con()
if lib_ready and con < 0.6:
    self.logger.info(f'decide: liberate lib_ready={lib_ready} con={con:.3f}')
```

两个坑：

- `get_current_con()` 会写入 `current_con`；读到 1 后 `current_con` 会一直是 1，直到下场，这会影响框架是否按变奏切人。
- `has_cd()` 会触发 OCR（每帧最多一次），有耗时。

**反例**：日志行里写 `con=self.get_current_con()`、`cd=self.has_cd('liberation')`。这是为了打日志而读状态，会改变行为。

## L-9 框架日志怎么处理

| 写法 | 处理 |
|---|---|
| 普通队伍代码（无固定交场链） | 直接使用 `self.logger` 或 `_trace`（`tag=None`），不重复打引擎已有记录 |
| 循环轴队伍代码 | 轴角色的 `self.logger` 按实例包一层 `_InfoAsDebug`（info 降为 debug，warning/error 原样），节点日志通过 `_raw_logger` 经 `_trace` 输出；切人与协奏看 WWisnotOK 决策追踪（见 workshop.md） |

## L-10 两种写法

### 直接内联写法（普通队伍代码）

```python
self.logger.info(f'enter mode={"intro" if self.has_intro else "natural"}')
self.logger.info(f'cast R: fail reason=no_animation lib_ready={lib_ready} in_team={in_team}')
self.logger.warning('fallback: heavy_instead_of_e')
```

### `_trace` helper 写法（循环轴推荐）

可以用 `_trace` helper。下面是英文参考实现：

- 不分轴的代码 `tag` 传 `None`；
- helper 用 try/except 吞掉**自己的**异常（5-6 唯一的例外）；
- 写出时走 `_raw_logger`（循环轴骨架会把 `self.logger` 包成 info 降级版，见 workshop.md）；
- 非轴角色没有 `_raw_logger`，直接用 `self.logger`。

```python
_RATIO_FIELDS = ('con', 'res_pct')


def _fmt_value(key, v):
    if isinstance(v, float):
        return f'{v:.3f}' if key in _RATIO_FIELDS else f'{v:.2f}'
    return str(v)


class Example(BaseChar):
    def _trace(self, tag, event, ok=None, reason=None, **data):
        """Write one template line: [TAG] event[: ok|fail] [reason=code] [key=value ...]."""
        try:
            line = f'[{tag.upper()}] {event}' if tag else event
            if ok is not None:
                line += ': ok' if ok else ': fail'
            if reason:
                line += f' reason={reason}'
            for key, value in data.items():
                line += f' {key}={_fmt_value(key, value)}'
            getattr(self, '_raw_logger', self.logger).info(line)
        except Exception:
            pass
```

用法：

```python
self._trace('f1', 'enter', mode='forced', has_intro=bool(self.has_intro))
self._trace('f1', 'cast R', ok=False, reason='no_animation', lib_ready=lib_ready, in_team=in_team)
self._trace('f1', 'exit', reason='done', next='Phrolova.f1')
self._trace(None, 'decide: liberate', lib_ready=True)
```

`fallback` 要打 warning。`_trace` 只打 info，所以 `fallback` 直接写：

```python
getattr(self, '_raw_logger', self.logger).warning('[F1] fallback: switch_without_r')
```

### 实机效果示例（循环轴 `runs/<run_id>/run.log`）

```text
2026-11-26T00:12:34.1200000+08:00 [INFO] 坎特蕾拉：[F1] enter mode=forced has_intro=False
2026-11-26T00:12:34.5800000+08:00 [INFO] 坎特蕾拉：[F1] cast E: ok
2026-11-26T00:12:35.9100000+08:00 [INFO] 坎特蕾拉：[F1] cast R: fail reason=no_animation lib_ready=False in_team=True
2026-11-26T00:12:35.9150000+08:00 [WARNING] 坎特蕾拉：[F1] fallback: switch_without_r
2026-11-26T00:12:35.9200000+08:00 [INFO] 坎特蕾拉：[F1] exit reason=done next=Phrolova.f1
2026-11-26T00:12:36.2100000+08:00 [INFO] 弗洛洛：[F1] enter mode=forced has_intro=True
```

## L-11 取证行（probe）

- 为查某个问题临时加的行，例如图标逐帧读数、截图落盘，统一用 `probe <对象>` 事件、info 级，实测日志里能看到。
- 字段可以自定，不受 L-6 词表限制；格式仍按 L-6。
- 截图路径写相对工作区或数据目录的路径，不写绝对路径。
- 交付 README 必须列出本版开着的 probe 行和各自要回答的问题。
- 问题查清后的下一版必须删掉对应的 probe 行。
