"""汇总一次 WWisnotOK MCP 实测：解析 runs/<run_id>/run.log 与 decision-traces/<id>/events.jsonl。

用法（用 WWisnotOK 自带的 Python，带 -I -B）：
    python.exe -I -B scripts/mcp_report.py [<运行目录>] [--trace <决策追踪目录>] [--out <输出目录>] [--loop-prefixes S,C,Z]

- <运行目录>：WWisnotOK run_task 生成的 <数据目录>/runs/<run_id>/（含 status.json、run.log、strategy-versions.json）。
- --trace：WWisnotOK set_decision_tracing 生成的 <数据目录>/decision-traces/<时间-编号>/（含 metadata.json、events.jsonl、summary.json）。
- 两者可任传其一或同时传入；--out 未指定时输出到主输入目录下的 report/。
- 输出：report.md、events.json；有 run.log 时同步复制一份归档为 report/run.log。
"""

import argparse
import json
import re
import shutil
import sys
from datetime import datetime
from pathlib import Path

# WWisnotOK TestRunner.cs 落盘格式：{Time:O} [{Level}] {Message}
WW_LINE_RE = re.compile(r'^(\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}(?:\.\d+)?(?:Z|[+-]\d{2}:\d{2})) \[(\w+)\] (.*)$')
# 角色循环轴行：支持中文角色名全角冒号（StrategyRuntime.WriteLog）和英文类名半角冒号
CHAR_RE = re.compile(r'^([^\s:：]+)[:：]\s*\[(\w+)\]\s+(.*)$')
ISSUE_RE = re.compile(
    r': fail\b|^fallback\b|^interrupt\b|clicked liberation but no effect|not in team while switching'
    r"|can't find next char|no_candidate_above_no_priority|not in combat|策略异常|连接已结束"
)


def parse_iso_ts(text):
    # .NET "O" 格式带 7 位小数秒，截到微秒以兼容所有 Python 3 版本
    normalized = re.sub(r'\.(\d{6})\d+', r'.\1', text).replace('Z', '+00:00')
    return datetime.fromisoformat(normalized).timestamp()


def parse_run_log(log_path):
    rows = []
    if not log_path or not log_path.is_file():
        return rows
    for raw in log_path.read_text(encoding='utf-8', errors='replace').splitlines():
        m = WW_LINE_RE.match(raw)
        if not m:
            if rows:
                rows[-1]['extra'].append(raw)
            continue
        ts = parse_iso_ts(m.group(1))
        rows.append({'ts': ts, 'iso': m.group(1), 'level': m.group(2).upper(), 'msg': m.group(3), 'extra': []})
    return rows


def classify_logs(rows):
    nodes, issues, casts = [], [], {}
    if not rows:
        return nodes, issues, casts
    t0 = rows[0]['ts']
    for r in rows:
        t = round(r['ts'] - t0, 3)
        m = CHAR_RE.match(r['msg'])
        if m:
            char, node, text = m.groups()
            if text.startswith('enter'):
                nodes.append({'t': t, 'iso': r['iso'], 'char': char, 'node': node, 'event': text})
            cm = re.match(r'(?:cast|retry) (\w+): (ok|fail)', text)
            if cm:
                casts.setdefault(f'{char} {cm.group(1)}', {'ok': 0, 'fail': 0})[cm.group(2)] += 1
        else:
            sep = '：' if '：' in r['msg'] else ':'
            head, found, body = r['msg'].partition(sep)
            char, node, text = (head.strip(), None, body.strip()) if found else ('WWisnotOK', None, r['msg'])
        if r['level'] in ('WARN', 'WARNING', 'ERROR', 'CRITICAL') or ISSUE_RE.search(text):
            issues.append({
                't': t, 'iso': r['iso'], 'level': r['level'],
                'char': char, 'node': node, 'text': text, 'extra': r['extra'][:6],
            })
    return nodes, issues, casts


def loop_stats(nodes, loop_prefixes):
    """启动轴到首个循环族节点为止；循环轮按首个循环族节点的再次进入切分（墙钟，含冻结）。"""
    prefixes = tuple(p.upper() for p in loop_prefixes)
    loop = [n for n in nodes if n['node'].upper().startswith(prefixes)]
    if not nodes or not loop:
        return {'loop_start': None, 'startup_s': None, 'rounds': []}
    first = (loop[0]['char'], loop[0]['node'])
    starts = [n['t'] for n in loop if (n['char'], n['node']) == first]
    return {
        'loop_start': f'{first[0]}.{first[1]}',
        'startup_s': round(loop[0]['t'] - nodes[0]['t'], 2),
        'rounds': [round(b - a, 2) for a, b in zip(starts, starts[1:])],
    }


def parse_decision_trace(trace_dir):
    if not trace_dir or not trace_dir.is_dir():
        return None
    meta = json.loads((trace_dir / 'metadata.json').read_text(encoding='utf-8')) if (trace_dir / 'metadata.json').is_file() else {}
    summary = json.loads((trace_dir / 'summary.json').read_text(encoding='utf-8')) if (trace_dir / 'summary.json').is_file() else {}
    events_path = trace_dir / 'events.jsonl'
    switches, slow_actions, frames, kind_counts = [], [], [], {}
    if events_path.is_file():
        for raw in events_path.read_text(encoding='utf-8', errors='replace').splitlines():
            if not raw.strip():
                continue
            ev = json.loads(raw)
            kind = ev.get('kind', 'unknown')
            kind_counts[kind] = kind_counts.get(kind, 0) + 1
            if ev.get('image_path'):
                frames.append({'seq': ev.get('sequence'), 'kind': kind, 'at': ev.get('at'), 'path': ev.get('image_path')})
            details = ev.get('details') or {}
            if kind == 'switch_selected':
                choice = details.get('choice') or {}
                ctx = details.get('context') or {}
                switches.append({
                    'seq': ev.get('sequence'), 'at': ev.get('at'),
                    'reason': choice.get('Reason') or choice.get('reason'),
                    'target_index': choice.get('Index', choice.get('index')),
                    'has_intro': ctx.get('HasIntro', ctx.get('has_intro')),
                })
            elif kind == 'action_ended':
                ms = details.get('milliseconds')
                if isinstance(ms, (int, float)) and ms >= 1500:
                    slow_actions.append({
                        'seq': ev.get('sequence'), 'at': ev.get('at'),
                        'name': details.get('name'), 'slot': details.get('slot'),
                        'strategy': details.get('strategy'), 'ms': round(ms, 1),
                    })
    return {
        'trace_id': meta.get('trace_id') or summary.get('Id') or trace_dir.name,
        'folder': str(trace_dir),
        'provenance': meta.get('provenance') or {},
        'summary': summary,
        'kind_counts': kind_counts,
        'switches': switches,
        'slow_actions': slow_actions,
        'frames': frames,
    }


def main():
    sys.stdout.reconfigure(encoding='utf-8')
    ap = argparse.ArgumentParser()
    ap.add_argument('run_dir', nargs='?', type=Path)
    ap.add_argument('--trace', type=Path, help='WWisnotOK decision-traces/<时间-编号> 目录')
    ap.add_argument('--out', type=Path, help='报告输出目录（默认 <输入目录>/report）')
    ap.add_argument('--loop-prefixes', default='S', help='循环族节点前缀，逗号分隔，默认 S（可扩展为 S,C,Z）')
    args = ap.parse_args()

    if not args.run_dir and not args.trace:
        ap.error('至少需要提供 <运行目录> 或 --trace <决策追踪目录>')

    run_dir = args.run_dir.resolve() if args.run_dir else None
    trace_dir = args.trace.resolve() if args.trace else None
    base_dir = run_dir or trace_dir
    out_dir = args.out.resolve() if args.out else (base_dir / 'report')
    out_dir.mkdir(parents=True, exist_ok=True)

    status = json.loads((run_dir / 'status.json').read_text(encoding='utf-8')) if run_dir and (run_dir / 'status.json').is_file() else {}
    versions = json.loads((run_dir / 'strategy-versions.json').read_text(encoding='utf-8')) if run_dir and (run_dir / 'strategy-versions.json').is_file() else {}
    log_path = (run_dir / 'run.log') if run_dir else None
    rows = parse_run_log(log_path)
    nodes, issues, casts = classify_logs(rows)
    loop_prefixes = [p.strip() for p in args.loop_prefixes.split(',') if p.strip()] or ['S']
    stats = loop_stats(nodes, loop_prefixes)
    trace = parse_decision_trace(trace_dir)

    if log_path and log_path.is_file() and (out_dir / 'run.log').resolve() != log_path.resolve():
        shutil.copy2(log_path, out_dir / 'run.log')

    run_id = status.get('RunId') or status.get('run_id') or (run_dir.name if run_dir else trace['trace_id'])
    state = status.get('State') or status.get('state') or ('trace_only' if trace else 'unknown')
    error = status.get('Error') or status.get('error')

    imported_hashes = {k: v[:16] for k, v in versions.items() if ('\\' in k or '/' in k)}
    if not imported_hashes and trace:
        imp = (trace.get('provenance') or {}).get('imported_strategies') or {}
        imported_hashes = {k: v[:16] for k, v in imp.items()}

    events = {
        'run_id': run_id,
        'state': state,
        'error': error,
        'run_dir': str(run_dir) if run_dir else None,
        'imported_sha256_16': imported_hashes,
        'loop': stats,
        'casts': casts,
        'issues': issues,
        'nodes': nodes,
        'decision_trace': trace,
    }
    (out_dir / 'events.json').write_text(json.dumps(events, ensure_ascii=False, indent=1), encoding='utf-8')

    lines = [
        f'# WWisnotOK 实测报告：{run_id}',
        '',
        f'- 状态：{state}；错误：{error or "无"}',
        f'- 导入策略 sha256(前16位)：{imported_hashes or "无（仅内置或未提供）"}',
        f'- 日志行数：{len(rows)}；节点：{len(nodes)} 个；问题行：{len(issues)} 条',
        f'- 启动轴：{stats["startup_s"]} 秒；循环起点：{stats["loop_start"]}；各轮墙钟：{stats["rounds"]}',
    ]
    if trace:
        tsum = trace['summary']
        lines += [
            f'- 决策追踪：`{trace["trace_id"]}`，事件分布：{trace["kind_counts"]}，'
            f'切人 {len(trace["switches"])} 次，关键帧 {len(trace["frames"])} 张，'
            f'丢弃事件 {tsum.get("dropped_disk_events", 0)}，跳过帧 {tsum.get("skipped_frames", 0)}',
        ]
    lines += ['', '## 技能结果', '']
    lines += [f'- {k}: ok {v["ok"]} / fail {v["fail"]}' for k, v in sorted(casts.items())] or ['- 无技能统计行']
    lines += ['', '## 问题行（t 从首行日志起算）', '']
    lines += [
        f'- t={i["t"]:.2f}s [{i["level"]}] {i["char"]}' + (f'[{i["node"]}]' if i['node'] else '') + f' {i["text"]}'
        for i in issues
    ] or ['- 无问题行']
    if trace and trace['switches']:
        lines += ['', '## 切人决策摘要（decision-traces）', '']
        lines += [
            f'- #{s["seq"]} {s["at"]} target_slot={s["target_index"]} has_intro={s["has_intro"]} reason={s["reason"]}'
            for s in trace['switches']
        ]
    if trace and trace['slow_actions']:
        lines += ['', '## 长耗时动作（>= 1500 ms）', '']
        lines += [
            f'- #{a["seq"]} slot={a["slot"]} {a["strategy"]}.{a["name"]} {a["ms"]} ms'
            for a in trace['slow_actions']
        ]
    if trace and trace['frames']:
        lines += ['', '## 决策关键帧', '']
        lines += [f'- #{f["seq"]} {f["kind"]} → `{f["path"]}`' for f in trace['frames'][:30]]

    report_text = '\n'.join(lines) + '\n'
    (out_dir / 'report.md').write_text(report_text, encoding='utf-8')
    print(report_text)
    print(f'report: {out_dir}')


if __name__ == '__main__':
    main()
