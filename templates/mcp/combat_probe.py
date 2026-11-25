"""WWisnotOK 定向战斗探测任务：由用户在游戏内备好战斗场景，运行有限时长的角色策略并记录结果。

通过 WWisnotOK MCP 的 run_task(file_path=<本文件绝对路径>, timeout_seconds=90, team=[...]) 运行。
参数优先读同目录 mcp_test.json 的 probe.duration_seconds（默认 30 秒）。
"""
import json
import time
from pathlib import Path

from ok import NotInCombatException


def _load_duration():
    cfg_path = Path(__file__).with_name('mcp_test.json')
    if cfg_path.is_file():
        cfg = json.loads(cfg_path.read_text(encoding='utf-8'))
        return float((cfg.get('probe') or {}).get('duration_seconds', 30))
    return 30.0


def run(task):
    duration = _load_duration()
    task.next_frame()
    in_team = task.in_team()
    chars = [type(c).__name__ if c else None for c in (getattr(task, 'chars', None) or [])]
    task.log_info(f'combat_probe start duration={duration:.1f}s in_team={in_team} chars={chars}')
    started = time.time()
    turns = 0
    stop_reason = 'duration_reached'
    while time.time() - started < duration:
        current = task.get_current_char(raise_exception=False)
        if current is None:
            stop_reason = 'no_current_char'
            break
        try:
            current.perform()
            turns += 1
        except NotInCombatException as exc:
            stop_reason = f'not_in_combat: {exc}'
            break
    elapsed = round(time.time() - started, 2)
    task.log_info(f'combat_probe end elapsed={elapsed}s turns={turns} reason={stop_reason}')
    return {'elapsed_s': elapsed, 'turns': turns, 'stop_reason': stop_reason, 'chars': chars}
