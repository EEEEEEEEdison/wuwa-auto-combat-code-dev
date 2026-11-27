"""WWisnotOK 定向战斗探测任务：由用户在游戏内备好战斗场景，运行有限时长的角色策略并记录结果。

通过 WWisnotOK MCP 的 run_task(file_path=<本文件绝对路径>, timeout_seconds=90, team=[...]) 运行。
参数优先读同目录 mcp_test.json 的 probe.duration_seconds（默认 30 秒）与 tolerances（零容忍熔断配置）。
"""
import json
import time
from pathlib import Path

from ok import NotInCombatException


def _load_config():
    cfg_path = Path(__file__).with_name('mcp_test.json')
    if cfg_path.is_file():
        return json.loads(cfg_path.read_text(encoding='utf-8'))
    return {}


def _check_entry_intro(expected_intro, cls_name, node, actual_intro):
    if not node:
        return None
    key = f'{cls_name}.{node}'.lower()
    if key not in expected_intro:
        return None
    expected = bool(expected_intro[key])
    if actual_intro != expected:
        return {
            'kind': 'entry_mismatch',
            'node': f'{cls_name}.{node}',
            'expected_intro': expected,
            'actual_intro': actual_intro,
        }
    return None


def run(task):
    cfg = _load_config()
    duration = float((cfg.get('probe') or {}).get('duration_seconds', 30))
    tol = cfg.get('tolerances') or {}
    fail_fast = bool(tol.get('fail_fast', True))
    expected_intro = {str(k).lower(): bool(v) for k, v in (tol.get('expected_intro') or {}).items()}

    task.next_frame()
    in_team = task.in_team()
    chars = [type(c).__name__ if c else None for c in (getattr(task, 'chars', None) or [])]
    task.log_info(f'combat_probe start duration={duration:.1f}s in_team={in_team} chars={chars} fail_fast={fail_fast}')
    started = time.time()
    turns = 0
    stop_reason = 'duration_reached'
    breach = None
    while time.time() - started < duration:
        current = task.get_current_char(raise_exception=False)
        if current is None:
            stop_reason = 'no_current_char'
            break
        cls_name = type(current).__name__
        actual_intro = bool(getattr(current, 'has_intro', False))
        planned_mode = getattr(current, '_entry_mode', None)
        if fail_fast and expected_intro and planned_mode:
            breach = _check_entry_intro(expected_intro, cls_name, planned_mode, actual_intro)
            if breach:
                stop_reason = (
                    f'tolerance_breach: entry_mismatch {breach["node"]} '
                    f'expected_intro={breach["expected_intro"]} actual_intro={breach["actual_intro"]}'
                )
                task.log_info(f'combat_probe {stop_reason}')
                break
        try:
            current.perform()
            turns += 1
        except NotInCombatException as exc:
            stop_reason = f'not_in_combat: {exc}'
            break
        if fail_fast and expected_intro and not planned_mode:
            executed_node = getattr(current, '_node', None)
            breach = _check_entry_intro(expected_intro, cls_name, executed_node, actual_intro)
            if breach:
                stop_reason = (
                    f'tolerance_breach: entry_mismatch {breach["node"]} '
                    f'expected_intro={breach["expected_intro"]} actual_intro={breach["actual_intro"]}'
                )
                task.log_info(f'combat_probe {stop_reason}')
                break
    elapsed = round(time.time() - started, 2)
    task.log_info(f'combat_probe end elapsed={elapsed}s turns={turns} reason={stop_reason}')
    return {'elapsed_s': elapsed, 'turns': turns, 'stop_reason': stop_reason, 'breach': breach, 'chars': chars}
