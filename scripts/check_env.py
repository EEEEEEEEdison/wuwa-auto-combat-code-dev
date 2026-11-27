"""只读探测本机开发环境能力，供 WWACCD 关口 G0 向用户汇总现状并征求意见。

用法：
    python -I -B scripts/check_env.py [--workspace <工作区目录>] [--wwisnotok <WWisnotOK 目录>] [--check-update] [--json]

特点：
- 仅使用 Python 标准库，任何 Python 3 均可运行。
- 严格只读：不修改文件、不下载安装任何组件、不启动游戏或 WWisnotOK。
- 检查项：wwaccd.local.md、WWisnotOK 目录与 MCP、Python 与 cv2、ffmpeg、gh 登录状态，以及可选的新版本检查。
"""

import argparse
import json
import os
import re
import shutil
import socket
import subprocess
import sys
from pathlib import Path
from urllib.parse import urlparse

GH_DEFAULT = Path(os.environ.get('ProgramFiles', r'C:\Program Files')) / 'GitHub CLI' / 'gh.exe'


def parse_local_config(workspace):
    cfg_path = Path(workspace).resolve() / 'wwaccd.local.md'
    result = {'path': str(cfg_path), 'exists': cfg_path.is_file(), 'entries': {}}
    if not cfg_path.is_file():
        return result
    text = cfg_path.read_text(encoding='utf-8-sig', errors='replace')
    for line in text.splitlines():
        s = line.strip()
        if s.startswith('|') and s.endswith('|') and not re.match(r'^\|\s*-+', s):
            parts = [p.strip().strip('`') for p in s.strip('|').split('|')]
            if len(parts) >= 2 and parts[0] not in ('项', '配置项'):
                result['entries'][parts[0]] = parts[1]
        elif '：' in s or ':' in s:
            sep = '：' if '：' in s else ':'
            k, v = s.split(sep, 1)
            k, v = k.lstrip('-* ').strip(), v.strip().strip('`')
            if k and v and len(k) <= 24:
                result['entries'][k] = v
    return result


def is_valid_wwisnotok_dir(path):
    p = Path(path)
    return (p / 'assets' / 'characters.json').is_file() and (p / 'strategy_host' / 'validate.py').is_file()


def is_valid_okww_working(path):
    p = Path(path)
    return (p / 'src' / 'char' / 'BaseChar.py').is_file() and (p / 'src' / 'char' / 'CharFactory.py').is_file()


def find_wwisnotok_dir(explicit, local_entries, workspace):
    candidates = []
    if explicit:
        candidates.append(Path(explicit))
    for k, v in local_entries.items():
        if 'WWisnotOK' in k and '数据' not in k and v and v != '无':
            candidates.append(Path(v.split('（')[0].strip()))
    ws = Path(workspace).resolve()
    candidates += [
        ws / 'WWisnotOK',
        ws.parent / 'WWisnotOK',
        Path(os.environ.get('LOCALAPPDATA', '')) / 'Programs' / 'WWisnotOK',
        Path(os.environ.get('ProgramFiles', '')) / 'WWisnotOK',
    ]
    seen = set()
    for cand in candidates:
        try:
            resolved = cand.resolve()
        except OSError:
            continue
        if resolved in seen:
            continue
        seen.add(resolved)
        if is_valid_wwisnotok_dir(resolved):
            return str(resolved)
    return None


def find_okww_working(explicit, local_entries, workspace):
    candidates = []
    if explicit:
        candidates.append(Path(explicit))
    for k, v in local_entries.items():
        if 'ok-ww' in k.lower() and v and v != '无':
            candidates.append(Path(v.split('（')[0].strip()))
    ws = Path(workspace).resolve()
    candidates += [
        ws / 'ok-ww' / 'data' / 'apps' / 'ok-ww' / 'working',
        ws.parent / 'ok-ww' / 'data' / 'apps' / 'ok-ww' / 'working',
        ws.parent / 'ok-ww',
    ]
    seen = set()
    for cand in candidates:
        try:
            resolved = cand.resolve()
        except OSError:
            continue
        if resolved in seen:
            continue
        seen.add(resolved)
        if is_valid_okww_working(resolved):
            return str(resolved)
    return None


def _read_json_path(json_file):
    try:
        if not json_file.is_file():
            return None
        data = json.loads(json_file.read_text(encoding='utf-8-sig'))
        val = (data.get('path') or '').strip()
        return str(Path(val).resolve()) if val else None
    except Exception:
        return None


def find_data_dir(local_entries, ww_dir):
    """按 WWisnotOK DataLocation.cs 规则定位实际数据目录。"""
    candidates = []
    env_dir = os.environ.get('WWISNOTOK_DATA_DIR')
    if env_dir:
        candidates.append(('env', Path(env_dir)))
    for k, v in local_entries.items():
        if '数据目录' in k and v and v != '无':
            candidates.append(('local_config', Path(v.split('（')[0].strip())))
    if ww_dir:
        ptr = _read_json_path(Path(ww_dir) / 'data-location.json')
        if ptr:
            candidates.append(('data-location.json', Path(ptr)))
    if os.environ.get('LOCALAPPDATA'):
        last = _read_json_path(Path(os.environ['LOCALAPPDATA']) / 'WWisnotOK' / 'last-data.json')
        if last:
            candidates.append(('last-data.json', Path(last)))
    if ww_dir:
        candidates.append(('default', Path(ww_dir) / 'data'))
    seen = set()
    for source, cand in candidates:
        try:
            resolved = cand.resolve()
        except OSError:
            continue
        if resolved in seen:
            continue
        seen.add(resolved)
        if (resolved / 'settings.json').is_file() or (source in ('env', 'data-location.json', 'last-data.json') and resolved.is_dir()):
            return {'path': str(resolved), 'source': source}
    return {'path': None, 'source': None}


def probe_mcp(local_entries, ww_dir, data_dir=None):
    candidates = []
    env_dir = os.environ.get('WWISNOTOK_DATA_DIR')
    if env_dir:
        candidates.append(Path(env_dir) / 'mcp' / 'connection.json')
    if os.environ.get('LOCALAPPDATA'):
        candidates.append(Path(os.environ['LOCALAPPDATA']) / 'WWisnotOK' / 'mcp' / 'connection.json')
    if data_dir:
        candidates.append(Path(data_dir) / 'mcp' / 'connection.json')
    for k, v in local_entries.items():
        if '数据目录' in k and v and v != '无':
            candidates.append(Path(v.split('（')[0].strip()) / 'mcp' / 'connection.json')
    if ww_dir:
        candidates.append(Path(ww_dir) / 'data' / 'mcp' / 'connection.json')

    for p in candidates:
        if not p.is_file():
            continue
        try:
            data = json.loads(p.read_text(encoding='utf-8'))
            url = data.get('url', '')
            parsed = urlparse(url)
            host = parsed.hostname or '127.0.0.1'
            port = parsed.port or 8766
            reachable = False
            with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as sock:
                sock.settimeout(0.5)
                reachable = sock.connect_ex((host, port)) == 0
            return {
                'status': 'reachable' if reachable else 'stale_connection_file',
                'connection_file': str(p),
                'url': url,
                'pid': data.get('pid'),
                'reachable': reachable,
            }
        except Exception as exc:
            return {'status': 'invalid_connection_file', 'connection_file': str(p), 'error': str(exc), 'reachable': False}
    return {'status': 'not_running', 'connection_file': None, 'url': None, 'pid': None, 'reachable': False}


def probe_python_cv2(ww_dir, okww_dir):
    py_candidates = []
    if ww_dir:
        ww_py = Path(ww_dir) / 'runtime' / 'python' / 'python.exe'
        if ww_py.is_file():
            py_candidates.append(('wwisnotok', str(ww_py)))
    if okww_dir:
        ok_py = Path(okww_dir).parent / 'python' / 'python.exe'
        if ok_py.is_file():
            py_candidates.append(('ok-ww', str(ok_py)))
    py_candidates.append(('current', sys.executable))
    which_py = shutil.which('python')
    if which_py and os.path.abspath(which_py) != os.path.abspath(sys.executable):
        py_candidates.append(('system', which_py))

    best = None
    for source, exe in py_candidates:
        try:
            r = subprocess.run(
                [exe, '-I', '-B', '-c', 'import sys; print(sys.version.split()[0]); import cv2; print(cv2.__version__)'],
                capture_output=True, text=True, timeout=6,
            )
            lines = [x.strip() for x in r.stdout.splitlines() if x.strip()]
            info = {
                'source': source,
                'path': exe,
                'version': lines[0] if lines else None,
                'cv2': lines[1] if r.returncode == 0 and len(lines) >= 2 else None,
            }
            if info['cv2']:
                return info
            if best is None:
                best = info
        except Exception:
            continue
    return best or {'source': None, 'path': None, 'version': None, 'cv2': None}


def probe_gh():
    gh = shutil.which('gh') or (str(GH_DEFAULT) if GH_DEFAULT.is_file() else None)
    if not gh:
        return {'status': 'not_installed', 'path': None}
    try:
        r = subprocess.run([gh, 'auth', 'status', '--hostname', 'github.com'], capture_output=True, timeout=5)
        return {'status': 'logged_in' if r.returncode == 0 else 'not_logged_in', 'path': gh}
    except Exception:
        return {'status': 'unknown', 'path': gh}


def probe_skill_update():
    upd_script = Path(__file__).with_name('update_skill.py')
    if not upd_script.is_file():
        return None
    try:
        r = subprocess.run(
            [sys.executable, '-I', '-B', str(upd_script), '--check', '--json'],
            capture_output=True, text=True, encoding='utf-8', timeout=8,
        )
        return json.loads(r.stdout) if r.returncode == 0 and r.stdout.strip() else None
    except Exception:
        return None


def main():
    sys.stdout.reconfigure(encoding='utf-8')
    ap = argparse.ArgumentParser()
    ap.add_argument('--workspace', default='.')
    ap.add_argument('--wwisnotok', default=None)
    ap.add_argument('--check-update', action='store_true', help='顺带只读检查 WWACCD 是否有新版本（24 小时节流缓存）')
    ap.add_argument('--json', action='store_true')
    args = ap.parse_args()

    local_cfg = parse_local_config(args.workspace)
    ww_dir = find_wwisnotok_dir(args.wwisnotok, local_cfg['entries'], args.workspace)
    data_info = find_data_dir(local_cfg['entries'], ww_dir)
    mcp = probe_mcp(local_cfg['entries'], ww_dir, data_info['path'])
    py_info = probe_python_cv2(ww_dir, None)
    ffmpeg = shutil.which('ffmpeg')
    gh = probe_gh()
    update_info = probe_skill_update() if args.check_update else None

    report = {
        'workspace': str(Path(args.workspace).resolve()),
        'local_config': local_cfg,
        'wwisnotok': {
            'found': bool(ww_dir), 'dir': ww_dir,
            'data_dir': data_info['path'], 'data_dir_source': data_info['source'],
            'contact_email': '476676559@qq.com',
        },
        'mcp': mcp,
        'python': py_info,
        'ffmpeg': {'found': bool(ffmpeg), 'path': ffmpeg},
        'gh': gh,
        'skill_update': update_info,
        'recommended_test_mode': 'semi_auto_mcp' if mcp['reachable'] else 'manual',
    }

    if args.json:
        print(json.dumps(report, ensure_ascii=False, indent=2))
        return 0

    print('# 本机环境只读探测结果（G0）')
    print()
    print('| 组件 | 当前状态 | 路径 / 详情 | 缺失影响与获取方式 |')
    print('|---|---|---|---|')
    ww_state = '已找到' if ww_dir else '未找到'
    ww_note = '支持工坊 zip（validate.py）、内置基线与可选 MCP' if ww_dir else '推荐获取 WWisnotOK 用于验证（联系作者邮箱 476676559@qq.com）；暂无本地目录时可走 --offline 打包'
    print(f'| WWisnotOK（推荐） | {ww_state} | `{ww_dir or "无"}` | {ww_note} |')
    data_state = f'已定位（{data_info["source"]}）' if data_info['path'] else '未找到'
    print(f'| WWisnotOK 数据目录 | {data_state} | `{data_info["path"] or "无"}` | 存放 settings.json、teams/、runs/ 与 decision-traces/ |')

    mcp_map = {'reachable': '已连通', 'stale_connection_file': '连接文件存在但端口未监听', 'not_running': '未运行', 'invalid_connection_file': '连接文件异常'}
    mcp_note = '支持半自动或自主 MCP 实测' if mcp['reachable'] else '推荐先走纯手动实测，或开启 WWisnotOK --mcp 后再启用 MCP'
    print(f'| WWisnotOK MCP | {mcp_map.get(mcp["status"], mcp["status"])} | `{mcp["url"] or "无"}` | {mcp_note} |')

    py_state = f'Python {py_info["version"]} + cv2 {py_info["cv2"]}' if py_info.get('cv2') else (f'Python {py_info["version"]}（缺 cv2）' if py_info.get('version') else '未找到')
    py_note = '支持自动抽帧与画面比对' if py_info.get('cv2') else '无法自动抽帧；若当前 Agent 支持直读视频可先跳过，仅在帧级精确测时或 HUD 裁剪放大时按需申请安装 opencv-python 或请用户提供关键帧截图'
    print(f'| Python / cv2 | {py_state} | `{py_info.get("path") or "无"}` | {py_note} |')

    ff_state = '已安装' if ffmpeg else '未安装'
    ff_note = '支持本地音轨提取与转码' if ffmpeg else '可选；若当前 Agent 支持直读视频/音频则无需安装（仅封装不兼容时按需提示），否则依赖字幕或用户转述；如需安装须先申请权限'
    print(f'| ffmpeg（可选） | {ff_state} | `{ffmpeg or "无"}` | {ff_note} |')

    gh_map = {'logged_in': '已登录', 'not_logged_in': '已安装未登录', 'not_installed': '未安装', 'unknown': '状态未知'}
    gh_note = '支持自动提交知识提议 Issue' if gh['status'] == 'logged_in' else '可选；知识提议可改用浏览器预填页或邮件附件'
    print(f'| gh（可选） | {gh_map.get(gh["status"], gh["status"])} | `{gh.get("path") or "无"}` | {gh_note} |')
    print()
    print(f'- 本地配置文件：`{local_cfg["path"]}`（{"已存在" if local_cfg["exists"] else "尚未创建"}）')
    print(f'- 默认推荐实测模式：{"半自动 MCP（可切换纯手动/自主）" if mcp["reachable"] else "纯手动实测"}')
    if update_info and update_info.get('has_update'):
        print(f'- WWACCD 有新版本：v{update_info["local_version"]} → {update_info["latest_tag"]}（对比：{update_info["compare_url"]}）')
        print(f'  更新命令：{update_info["update_command"]}')
    return 0


if __name__ == '__main__':
    sys.exit(main())
