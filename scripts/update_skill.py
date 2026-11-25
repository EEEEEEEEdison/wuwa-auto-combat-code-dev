"""WWACCD 半自动询问式更新脚本：只读检查新版本，或在用户明确同意后安全切换标签。

用法（纯标准库，带 -I -B）：
    检查新版本（只读，24 小时节流缓存保存在系统临时目录，不写入安装目录）：
        python -I -B scripts/update_skill.py --check [--force] [--json]
    执行更新（必须在用户明确同意后运行）：
        python -I -B scripts/update_skill.py --apply [--target v1.2.0]

安全边界：
- 检查失败、断网或超时静默返回 status=offline，不阻塞开发。
- --apply 前必须确认安装目录为干净 Git 仓库且当前不在本地开发分支（HEAD 须为 detached tag）；
  工作树有未提交改动、处于开发分支或非 Git 目录时一律拒绝覆盖，给出明确提示。
"""

import argparse
import json
import os
import re
import subprocess
import sys
import tempfile
import time
import urllib.request
from pathlib import Path

REPO = 'EEEEEEEEdison/wuwa-auto-combat-code-dev'
TAGS_API = f'https://api.github.com/repos/{REPO}/tags?per_page=20'
SEMVER_RE = re.compile(r'^v?(\d+)\.(\d+)\.(\d+)$')
CACHE_TTL_S = 86400
CACHE_FILE = Path(tempfile.gettempdir()) / 'wwaccd-update-check-cache.json'


def skill_root():
    return Path(__file__).resolve().parent.parent


def parse_semver(tag):
    m = SEMVER_RE.match((tag or '').strip())
    return tuple(int(g) for g in m.groups()) if m else None


def read_local_version(root):
    vf = root / 'VERSION'
    return vf.read_text(encoding='utf-8').strip() if vf.is_file() else '0.0.0'


def fetch_latest_tag_git(root, timeout=5.0):
    if not (root / '.git').exists():
        return None
    r = subprocess.run(
        ['git', '-C', str(root), 'ls-remote', '--tags', '--refs', 'origin'],
        capture_output=True, text=True, encoding='utf-8', errors='replace', timeout=timeout,
    )
    if r.returncode != 0:
        return None
    parsed = []
    for line in r.stdout.splitlines():
        parts = line.split()
        if len(parts) < 2 or not parts[1].startswith('refs/tags/'):
            continue
        name = parts[1][len('refs/tags/'):]
        ver = parse_semver(name)
        if ver:
            parsed.append((ver, name if name.startswith('v') else f'v{name}'))
    if not parsed:
        return None
    parsed.sort(key=lambda x: x[0], reverse=True)
    return parsed[0][1]


def fetch_latest_tag_api(timeout=4.0):
    req = urllib.request.Request(
        TAGS_API,
        headers={'User-Agent': 'WWACCD-UpdateCheck/1.0', 'Accept': 'application/vnd.github+json'},
    )
    with urllib.request.urlopen(req, timeout=timeout) as resp:
        items = json.loads(resp.read().decode('utf-8'))
    parsed = []
    for item in items:
        name = item.get('name', '')
        ver = parse_semver(name)
        if ver:
            parsed.append((ver, name if name.startswith('v') else f'v{name}'))
    if not parsed:
        return None
    parsed.sort(key=lambda x: x[0], reverse=True)
    return parsed[0][1]


def get_latest_tag(root, force=False, timeout=5.0):
    now = time.time()
    if not force and CACHE_FILE.is_file():
        try:
            cache = json.loads(CACHE_FILE.read_text(encoding='utf-8'))
            if now - cache.get('checked_at', 0) < CACHE_TTL_S and cache.get('repo') == REPO and cache.get('latest_tag'):
                return cache.get('latest_tag'), True
        except Exception:
            pass
    latest = None
    try:
        latest = fetch_latest_tag_git(root, timeout=timeout)
    except Exception:
        latest = None
    if not latest:
        try:
            latest = fetch_latest_tag_api(timeout=timeout)
        except Exception:
            latest = None
    if not latest:
        return None, False
    try:
        CACHE_FILE.write_text(
            json.dumps({'repo': REPO, 'checked_at': now, 'latest_tag': latest}, ensure_ascii=False),
            encoding='utf-8',
        )
    except OSError:
        pass
    return latest, False


def inspect_install(root):
    if not (root / '.git').exists():
        return {'kind': 'non_git', 'dirty': None, 'branch': None}
    branch = subprocess.run(
        ['git', '-C', str(root), 'symbolic-ref', '--quiet', '--short', 'HEAD'],
        capture_output=True, text=True, encoding='utf-8', errors='replace',
    )
    dirty_proc = subprocess.run(
        ['git', '-C', str(root), 'status', '--porcelain', '--untracked-files=all'],
        capture_output=True, text=True, encoding='utf-8', errors='replace',
    )
    dirty_lines = [line for line in dirty_proc.stdout.splitlines() if line.strip()]
    if branch.returncode == 0 and branch.stdout.strip():
        return {'kind': 'dev_branch', 'branch': branch.stdout.strip(), 'dirty': bool(dirty_lines), 'dirty_files': dirty_lines}
    return {'kind': 'tag_install', 'branch': None, 'dirty': bool(dirty_lines), 'dirty_files': dirty_lines}


def do_check(root, force=False, timeout=5.0, as_json=False):
    local_ver = read_local_version(root)
    local_tuple = parse_semver(local_ver) or (0, 0, 0)
    latest_tag, from_cache = get_latest_tag(root, force=force, timeout=timeout)
    install = inspect_install(root)

    if not latest_tag:
        payload = {
            'status': 'offline', 'local_version': local_ver, 'latest_tag': None,
            'has_update': False, 'from_cache': from_cache, 'install': install,
        }
    else:
        latest_tuple = parse_semver(latest_tag) or (0, 0, 0)
        has_update = latest_tuple > local_tuple
        payload = {
            'status': 'update_available' if has_update else 'up_to_date',
            'local_version': local_ver,
            'latest_tag': latest_tag,
            'has_update': has_update,
            'from_cache': from_cache,
            'compare_url': f'https://github.com/{REPO}/compare/v{local_ver}...{latest_tag}',
            'release_url': f'https://github.com/{REPO}/releases/tag/{latest_tag}',
            'update_command': f'python -I -B "{root / "scripts" / "update_skill.py"}" --apply --target {latest_tag}',
            'install': install,
        }

    if as_json:
        print(json.dumps(payload, ensure_ascii=False, indent=2))
        return 0

    if payload['status'] == 'update_available':
        print(f'WWACCD 有新版本：v{local_ver} → {latest_tag}')
        print(f'对比链接：{payload["compare_url"]}')
        print(f'更新命令：{payload["update_command"]}')
        print('提示：用户同意前不得运行更新命令；更新后需新开会话（或 pi 执行 /reload）。')
    elif payload['status'] == 'up_to_date':
        print(f'WWACCD 已是最新版本（v{local_ver}）')
    else:
        print(f'WWACCD 版本检查跳过（当前 v{local_ver}，网络不可达或超时）')
    return 0


def do_apply(root, target_tag=None):
    install = inspect_install(root)
    if install['kind'] == 'non_git':
        print(f'REFUSE: {root} 不是 Git 仓库，无法自动切换标签。请先移走旧目录，再用 git clone --branch <标签> 重装。')
        return 2
    if install['kind'] == 'dev_branch':
        print(f'REFUSE: 当前位于本地开发分支 {install["branch"]}，不强切 detached HEAD。请手动 git pull --ff-only 或保留开发状态。')
        return 2
    if install['dirty']:
        print('REFUSE: 安装目录存在未提交改动，拒绝覆盖：')
        for line in install['dirty_files'][:20]:
            print('  ' + line)
        return 2

    if not target_tag:
        latest_tag, _ = get_latest_tag(root, force=True, timeout=8.0)
        if not latest_tag:
            print('FAIL: 无法获取远端最新标签，请检查网络或显式传 --target v<版本号>。')
            return 1
        target_tag = latest_tag
    if not parse_semver(target_tag):
        print(f'FAIL: 非法版本号标签：{target_tag}')
        return 1
    if not target_tag.startswith('v'):
        target_tag = 'v' + target_tag

    old_ver = read_local_version(root)
    r1 = subprocess.run(
        ['git', '-C', str(root), 'fetch', 'origin', 'tag', target_tag, '--no-tags'],
        capture_output=True, text=True, encoding='utf-8', errors='replace',
    )
    if r1.returncode != 0:
        print(f'FAIL: git fetch 失败：{(r1.stderr or r1.stdout).strip()}')
        return 1
    r2 = subprocess.run(
        ['git', '-C', str(root), 'switch', '--detach', target_tag],
        capture_output=True, text=True, encoding='utf-8', errors='replace',
    )
    if r2.returncode != 0:
        print(f'FAIL: git switch 失败：{(r2.stderr or r2.stdout).strip()}')
        return 1

    head = subprocess.check_output(['git', '-C', str(root), 'rev-parse', 'HEAD'], text=True).strip()
    tag_commit = subprocess.check_output(
        ['git', '-C', str(root), 'rev-parse', f'refs/tags/{target_tag}^{{commit}}'], text=True,
    ).strip()
    new_ver = read_local_version(root)
    if head != tag_commit or f'v{new_ver}' != target_tag:
        print(f'FAIL: 切换后核对不一致（HEAD={head[:8]}, tag={tag_commit[:8]}, VERSION={new_ver}）')
        return 1
    print(f'OK: WWACCD 已更新 v{old_ver} → {target_tag}（{head[:8]}）')
    print('请新开 Claude Code 会话（或在 pi 运行 /reload）使新版生效。')
    return 0


def main():
    sys.stdout.reconfigure(encoding='utf-8')
    ap = argparse.ArgumentParser()
    group = ap.add_mutually_exclusive_group(required=True)
    group.add_argument('--check', action='store_true', help='只读检查是否有新版本')
    group.add_argument('--apply', action='store_true', help='经用户同意后切换安装目录到目标标签')
    ap.add_argument('--target', default=None, help='目标版本标签，如 v1.2.0（仅 --apply 使用）')
    ap.add_argument('--force', action='store_true', help='忽略 24 小时缓存强制检查')
    ap.add_argument('--timeout', type=float, default=5.0, help='网络请求超时秒数，默认 5.0')
    ap.add_argument('--json', action='store_true')
    args = ap.parse_args()

    root = skill_root()
    if args.check:
        return do_check(root, force=args.force, timeout=args.timeout, as_json=args.json)
    return do_apply(root, target_tag=args.target)


if __name__ == '__main__':
    sys.exit(main())
