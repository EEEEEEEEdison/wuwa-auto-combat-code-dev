# 自实现套路

只有内置函数确实不够用时才读本篇。
在 WWisnotOK 队伍代码中可以直接使用这些套路；交付说明里要标出自实现的部分。

**基线**：WWisnotOK `v0.4.7`（`strategy_host/src/char/BaseChar.py`、`strategy_host/bridge.py`、`src/WWisnotOK/Core/`）。API 详情见 basechar-api.md 和 task-api.md。

## 目录

1. [实现顺序（5-1）](#1-实现顺序)
2. [时间推算谓词（5-2）](#2-时间推算谓词)
3. [发送 → 确认 → 记录（5-3）](#3-发送--确认--记录)
4. [手写演出等待（上游写法）](#4-手写演出等待)
5. [按住（5-4）](#5-按住)
6. [自定义区域识别（5-5）](#6-自定义区域识别)
7. [状态存储与清理（3-8 / 4-4）](#7-状态存储与清理)
8. [异常（5-6）](#8-异常)
9. [常量与注释（5-7）](#9-常量与注释)
10. [按日志和视频迭代（5-8）](#10-按日志和视频迭代)

---

## 1. 实现顺序

没有合适的内置函数时，按下面顺序选实现方式（5-1）：

1. **内置 HUD 识别**：`*_available()`、`current_*()`、`task.in_team()`、`is_forte_full` / `is_mouse_forte_full` / `is_e_forte_full`、`is_con_full` / `get_current_con`。
2. **自定义区域识别**：颜色占比，或复用 WWisnotOK 已有模板名。见第 6 节。
3. **时间戳推算**：用来推算识别不到的游戏内状态，例如 buff 剩余、窗口期、技能段数。见第 2 节。

各方式的取舍：

| 方式 | 优点 | 缺点 |
|---|---|---|
| 识别 | 反映真实状态，不累积误差 | — |
| 时间推算 | 成本低 | 动画被打断、卡肉时会漂移 |

## 2. 时间推算谓词

规则 5-2：

- 写成按游戏含义命名的小谓词方法；
- 方法内容 = **已确认的时间戳** + **扣冻结的经过时间** + **时长常量**；
- 时间戳只在动作确认成功后记录。如果确认前就记，技能没放出来也会被当成放了。

```python
class Example(BaseChar):
    LIBERATION_DURATION = 12  # 大招强化状态持续时间

    def still_in_liberation(self):
        return self.time_elapsed_accounting_for_freeze(self.last_liberation) < self.LIBERATION_DURATION
```

- `last_liberation` 初值是 `-1`，此时 `time_elapsed_accounting_for_freeze` 返回 10000，所以谓词天然为 False。
- 上游同类写法：`Brant.py:44`（12 秒）、`Lupa.py:77`、`Encore.py:14`、`Xiangliyao.py:26`。
- 起点按含义选（2-6），不另建和 `last_*` 同义的变量。

谓词可以在 `get_switch_priority` 里用（3-3 允许读时间戳），例如 `Brant.py:112`：`if self.still_in_liberation(): return SwitchPriority.MUST`。

## 3. 发送 → 确认 → 记录

适用于“按一次，确认生效”。如果要“一直按到进 CD”，用 1-6 的 `wait_until(..., post_action=self.send_*_key)`。

规则 5-3：

1. 发送；
2. 用 `wait_until` 等确认信号；
3. 确认成功才 `record_*_use()`。

最多尝试 2 次。失败时打日志并返回 False。

**标准确认信号**：

| 动作 | 确认信号 | 备注 |
|---|---|---|
| E | `not self.resonance_available()` | 进了 CD |
| R | `not self.task.in_team()[0]` | 进入演出 |
| 回到可操作 | `self.task.in_team()[0]`，加 `settle_time=0.1` | 演出结束；过滤单帧 |
| 声骸 | `not self.echo_available()` | 进了 CD |

**模板**：

```python
def cast_resonance_confirmed(self):
    if not self.resonance_available():
        self.logger.info('cast E: fail reason=not_ready')
        return False
    for attempt in range(2):
        # If E already shows CD here, the first press landed after its window: confirm it, don't press again.
        if attempt == 0 or self.resonance_available():
            self.send_resonance_key()
        if self.task.wait_until(lambda: not self.resonance_available(), time_out=0.5):
            self.record_resonance_use()
            self.logger.info(f'{"cast E" if attempt == 0 else "retry E"}: ok attempt={attempt + 1}')
            return True
    self.logger.info('retry E: fail reason=icon_still_lit attempt=2')
    return False
```

**上游原型**：`Rover.py:131-147` 的 `short_electric_skill`：

```python
def short_electric_skill(self):
    # 强化E能在普通E冷却期间触发，不能用普通冷却拦截。
    for attempt in range(2):
        if not self.electric_skill_ready():
            return False
        start = time.time()
        self.send_resonance_key(down_time=0.05)
        # 回路在尾段消耗；过滤瞬间变暗，同时保留必要的动作保护。
        consumed = bool(self.task.wait_until(
            lambda: self.time_elapsed_accounting_for_freeze(start) >= 1.5
                    and not self.is_forte_full() and not self.is_e_forte_full(),
            time_out=2.6, settle_time=0.2, pre_action=self.check_combat))
        if consumed:
            self.record_resonance_use()
            return True
        self.logger.info(f'rover: electric enhanced resonance attempt {attempt + 1} not confirmed')
    return False
```

这个原型同时用到了：

- 2-3：会闪的识别加 `settle_time`；
- 2-4：超过 1 秒的等待传 `pre_action=self.check_combat`；
- 1-3 / 5-2：确认后才记录。

## 4. 手写演出等待

以下是事实，不是新规则。`click_liberation` 不合适时，上游手写演出等待的写法是：

1. 发键；
2. 确认进入演出（`not in_team()[0]`）；
3. 置 `task.in_liberation = True`，让演出期间不会因为看不到目标而判脱战；
4. 等 `in_team()[0]`；
5. 复位 `in_liberation`；
6. `add_freeze_duration(start, 演出时长)`；
7. `record_liberation_use()`。

例子：

- `Augusta.py:71-86`（按住 R 的“威仪”）；
- `Hiyuki.py:160-177`（`hold_liberation`）；
- `Jinhsi.py:44-72`。

```python
def wait_liberation_end(self, start):
    self.task.in_liberation = True
    self.task.wait_until(lambda: self.task.in_team()[0], time_out=7, settle_time=0.1)
    self.task.in_liberation = False
    self.add_freeze_duration(start, time.time() - start)
    self.record_liberation_use()
```

**注意**：

- 手写等待没有 `click_liberation` 那层 7 秒保护（演出超过 7 秒它会 `raise_not_in_combat`）。
- `in_liberation` 为 True 期间 `check_combat` 永远通过，所以 `wait_until` 必须自带上限。
- 脱战时框架的 `reset_to_false` 会把 `in_liberation` 复位。

## 5. 按住

规则：

- **5-4**：手写的 `mouse_down` / `send_key_down` 必须放进 try/finally，在 finally 里松开。脱战异常会直接穿过角色代码往上抛，没有 finally 的话按键会一直按着不松。
- **4-2**：能用 `heavy_click_forte(check_fun)` 的，仍然优先用它。

```python
def hold_heavy_until(self, check_fun, time_out):
    self.task.mouse_down()
    try:
        return self.task.wait_until(check_fun, time_out=time_out, pre_action=self.check_combat)
    finally:
        self.task.mouse_up()
```

```python
def hold_resonance(self, duration):
    self.task.send_key_down(self.get_resonance_key())
    try:
        self.sleep(duration)
    finally:
        self.task.send_key_up(self.get_resonance_key())
```

上游例子：`Hsin.py:79-87`、`Lucilla.py:125-130`、`Lucilla.py:147-151`。

注意：框架自带的 `heavy_attack(duration)` 和 `heavy_click_forte` 内部都**没有** try/finally。`heavy_attack` 里的 `sleep` 抛出脱战异常时，`mouse_up` 不会执行。这是框架现状。

## 6. 自定义区域识别

规则 5-5 的自由度很高，有两条路。

### 6a 颜色占比（两种模式都能用）

```python
def is_forte_full_example_bar(self):
    box = self.task.box_of_screen_scaled(3840, 2160, 2251, 1993, 2311, 2016, name='example_bar', hcenter=True)
    percent = self.task.calculate_color_percentage(forte_white_color, box)
    self.logger.debug(f'example_bar percent={percent:.3f}')
    return percent > 0.08
```

**坐标**

- `box_of_screen_scaled` 的前两个参数是**量坐标时用的截图分辨率**，框架会换算到当前分辨率；
- 上游用过 3840×2160、5120×2880、2560×1440；
- 坐标写成左上 `(x, y)` 加右下 `(to_x, to_y)`；
- HUD 底部技能栏一带要加 `hcenter=True`，否则超宽屏会偏。

**颜色**

- 优先复用框架已有的颜色：`forte_white_color`（`from src.char.BaseChar import forte_white_color`）、`text_white_color`（`from src import text_white_color`）；
- 新颜色写成 `{'r': (lo, hi), 'g': (lo, hi), 'b': (lo, hi)}`。

**阈值**

- 比例打 `debug`。L-1 规定高频细节用 debug；L-6 规定比例保留 3 位小数；
- 阈值来自实测，按 5-7 写成类常量并配简明备注。

**命名**（4-1）

- 替代通用回路判断时，覆写 `is_forte_full`；
- 另起名字时，写成 `is_forte_full_<char>_<what>`，并显式传给调用方，例如 `heavy_click_forte(check_fun=self.is_forte_full_example_bar)`。

**上游例子**：

- `Cantarella.py:70-73`：覆写 `is_forte_full`，5120×2880 坐标，阈值 0.06；
- `Linnai.py:113-116`；
- `Phoebe.py:133`、`Phoebe.py:177`。

**只对在场角色有效**（4-4）：HUD 上显示的永远是在场角色的状态。

### 6b 复用已有模板（不可随 zip 携带新图片）

工坊 zip 只能包含 `team.json` 和 3 个 `.py` 文件（WWisnotOK `TeamStore` 强制校验），**带不了新图片**。因此自定义识别只能用 6a 颜色占比，或复用 WWisnotOK `assets/templates/` 中已存在的模板名：

- 代码里用 `self.task.find_one(Labels.xxx, threshold=0.7)` 或 `self.task.find_one('xxx', ...)`；
- `strategy_host/validate.py` 会在打包校验时检查 `get_feature_by_name` / `get_box_by_name` 引用的模板是否存在于 `assets/templates/`，不得凭空编造模板名。

## 7. 状态存储与清理

| 状态生命周期 | 在哪里清 | 规则 |
|---|---|---|
| 本次上场有效（本次已放几段 E、本次是否放过 R） | 覆写 `switch_out(con_full)`，先调 `super().switch_out(con_full)` | 3-8 |
| 本场战斗有效（开场标记、阶段、计数） | 覆写 `reset_state()`，先调 `super().reset_state()` | 3-8 |
| 跨场（事实） | 框架时间戳 `last_res` / `last_liberation` / `last_echo` / `last_switch_time` 不会被 `reset_state` 清。工坊类直接继承 `BaseChar` 时例外：每场开战都会重建实例，见 workshop.md 第 1 节 | — |

另外两条要求：

- `__init__` 里的初值要和 `reset_state` 一致（3-8）；
- 离场角色的资源（回路格数、协奏）只能用**在场时存下的值**或时间戳推算（4-4）。

```python
def __init__(self, *args, **kwargs):
    super().__init__(*args, **kwargs)
    self.e_count = 0          # 本次上场
    self.opener_done = False  # 本场战斗

def switch_out(self, con_full=False):
    super().switch_out(con_full)
    self.e_count = 0

def reset_state(self):
    super().reset_state()
    self.opener_done = False
```

上游例子：

- `Hiyuki.py:32-35`、`Encore.py:17-19`：在 `switch_out` 里清；
- 13 个角色覆写了 `reset_state`。

## 8. 异常

规则 5-6：角色代码里不写 `try/except` 吞异常。

- `NotInCombatException`、`CharDeadException` 要一直抛到 `AutoCombatTask.run`，由它结束战斗循环，并调用 `combat_end()`。
- 吞掉脱战异常的后果：脱战后脚本还会继续按技能。
- `try/finally`（不带 except）不受此限制，第 5 节的按住就要用它。
- 唯一允许 `except Exception: pass` 的地方，是日志 helper 吞掉自己的格式化异常（logging.md 的 `_trace`）。

## 9. 常量与注释

从日志或视频量出来的时长和阈值（5-7）：写成类常量，并配简明备注说明游戏机制或实测来源，例如 `R_ANIMATION = 1.8  # 视频实测 R 演出 1.8s`。

## 10. 按日志和视频迭代

规则 5-8：

1. 在日志里定位：哪个节点（`enter` 行）、`cast X: ok|fail`、`reason=`。
2. 用 `enter` 行对齐视频，再用时间戳差找到对应时刻，确认根因。日志里不写耗时（L-5）。
3. 根因确认后再改，一次只改一个变量。
4. 原因不明时不加兜底分支。兜底会把真正的问题盖住。
