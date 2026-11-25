"""WWisnotOK 只读状态探测任务：抓帧、核对队伍识别与已加载角色类，不发送任何游戏输入。

通过 WWisnotOK MCP 的 run_task(file_path=<本文件绝对路径>, timeout_seconds=30) 运行。
"""


def run(task):
    task.next_frame()
    frame = task.frame
    in_team = task.in_team()
    chars = []
    for char in getattr(task, 'chars', None) or []:
        if char is None:
            chars.append(None)
            continue
        chars.append({
            'index': getattr(char, 'index', None),
            'class': type(char).__name__,
            'module': type(char).__module__,
            'role': str(getattr(char, 'char_type', '')),
            'is_current': bool(getattr(char, 'is_current_char', False)),
        })
    shape = list(frame.shape) if frame is not None else None
    task.log_info(f'capture_probe shape={shape} in_team={in_team} chars={[c["class"] if c else None for c in chars]}')
    return {'shape': shape, 'in_team': list(in_team) if isinstance(in_team, tuple) else in_team, 'chars': chars}
