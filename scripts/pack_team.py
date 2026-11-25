"""打包 WWisnotOK 工坊配队 zip，并用 WWisnotOK 自带的 strategy_host/validate.py 校验。

用法（用 WWisnotOK 自带的 Python，带 -I -B）：
    python.exe -I -B pack_team.py <版本目录> <WWisnotOK 目录> [--src <代码目录>]

- team.json 取自版本目录。3 个角色 .py 默认也取自版本目录；项目要求先清洗代码时，用 --src 指向清洗结果。
- 角色表取自 <WWisnotOK 目录>/assets/characters.json，显示名映射与 WWisnotOK Core/Contracts.cs 保持一致。
- 按 TeamStore.cs 规则检查 zip：平铺无子目录、单文件 <= 2 MB、总包 <= 20 MB、恰好含 team.json 与 3 个角色 .py。
- 调用 <WWisnotOK 目录>/strategy_host/validate.py 在独立进程校验 AST、同名类、BaseChar 继承与构造安全。
- zip 写进版本目录，文件名 <类名>_<类名>_<类名>_<author>_<version>.zip，类名按 team 字段顺序。
- 同名 zip 已存在时不覆盖，退出码 2。校验不通过时删掉本次打的 zip，退出码 1。
"""

import argparse
import json
import os
import re
import subprocess
import sys
import zipfile
from pathlib import Path

FIELDS = ('name', 'description', 'author', 'version', 'team')
MAX_FILE_BYTES = 2_000_000
MAX_ARCHIVE_BYTES = 20_000_000
# 与 WWisnotOK src/WWisnotOK/Core/Contracts.cs Names.Aliases 保持一致
DISPLAY_ALIASES = {
    'Douling': 'Buling',
    'Xigelika': 'Sigrika',
    'Linnai': 'Lynae',
    'Luhesi': 'Luuk Herssen',
    'Xiangliyao': 'Xiangli Yao',
    'ShoreKeeper': 'Shorekeeper',
    'Rover': 'Rover',
    'YangYangSp': 'Yangyang: Xuanling',
}


def safe(value):
    return re.sub(r'[<>:"/\\|?*\s]+', '_', value).strip(' .')


def display_name(char_id):
    return DISPLAY_ALIASES.get(char_id, char_id)


def resolve_wwisnotok_paths(app_dir):
    root = Path(app_dir).resolve()
    chars_path = root / 'assets' / 'characters.json'
    validate_path = root / 'strategy_host' / 'validate.py'
    python_path = root / 'runtime' / 'python' / 'python.exe'
    if not chars_path.is_file():
        raise FileNotFoundError(f'找不到角色表：{chars_path}')
    if not validate_path.is_file():
        raise FileNotFoundError(f'找不到校验脚本：{validate_path}')
    py = str(python_path) if python_path.is_file() else sys.executable
    return chars_path, validate_path, py


def inspect_archive(zip_path, valid_ids):
    if zip_path.stat().st_size > MAX_ARCHIVE_BYTES:
        raise ValueError(f'队伍压缩包超过 {MAX_ARCHIVE_BYTES} 字节')
    class_by_display = {display_name(cid): cid for cid in valid_ids}
    with zipfile.ZipFile(zip_path, 'r') as z:
        infos = z.infolist()
        names = [i.filename for i in infos]
        if any('/' in n or '\\' in n for n in names):
            raise ValueError('压缩包必须平铺，不能包含子目录')
        if len({n.casefold() for n in names}) != len(names):
            raise ValueError('压缩包包含重复文件名')
        for info in infos:
            if info.file_size > MAX_FILE_BYTES:
                raise ValueError(f'文件过大（超过 {MAX_FILE_BYTES} 字节）：{info.filename}')
        if 'team.json' not in names:
            raise ValueError('压缩包缺少 team.json')
        manifest = json.loads(z.read('team.json').decode('utf-8'))
        if not isinstance(manifest, dict):
            raise ValueError('team.json 格式无效')
        for field in FIELDS:
            if not isinstance(manifest.get(field), str) or not manifest[field].strip():
                raise ValueError(f'team.json 缺少非空字段 {field}')
        displays = [n.strip() for n in manifest['team'].split(',') if n.strip()]
        if len(displays) != 3:
            raise ValueError(f'team 字段必须包含 3 个角色，实际：{displays}')
        if displays != sorted(displays, key=str.casefold):
            raise ValueError(f'team 字段必须按英文显示名不区分大小写字母序排列：{displays}')
        members = []
        for disp in displays:
            cid = class_by_display.get(disp)
            if cid is None:
                raise ValueError(f'未知角色显示名：{disp}')
            members.append(cid)
        if len(set(members)) != 3:
            raise ValueError(f'队伍必须包含 3 个不同角色：{members}')
        expected = {'team.json', *(f'{m}.py' for m in members)}
        if set(names) != expected:
            raise ValueError(f'压缩包内容须恰好为 {sorted(expected)}，实际：{sorted(names)}')
        codes = {}
        for m in members:
            raw = z.read(f'{m}.py').decode('utf-8')
            codes[m] = raw.replace('\r\n', '\n').replace('\r', '\n')
    return manifest, members, codes, names


def run_validate(python_exe, validate_path, codes):
    # -I 模式忽略 PYTHONUTF8/PYTHONIOENCODING，用 ensure_ascii=True 避免 Windows 代码页破坏中文注释
    proc = subprocess.run(
        [python_exe, '-I', '-B', str(validate_path)],
        input=json.dumps(codes, ensure_ascii=True),
        capture_output=True,
        text=True,
        encoding='utf-8',
    )
    if proc.returncode != 0:
        detail = (proc.stderr or proc.stdout).strip() or f'exit {proc.returncode}'
        raise ValueError(f'strategy_host/validate.py 校验失败：{detail}')


def main():
    sys.stdout.reconfigure(encoding='utf-8')
    parser = argparse.ArgumentParser()
    parser.add_argument('version_dir')
    parser.add_argument('wwisnotok_dir')
    parser.add_argument('--src')
    args = parser.parse_args()
    version_dir = Path(args.version_dir).resolve()
    src_dir = Path(args.src).resolve() if args.src else version_dir

    try:
        chars_path, validate_path, py_exe = resolve_wwisnotok_paths(args.wwisnotok_dir)
    except FileNotFoundError as e:
        print(f'FAIL: {e}')
        return 1

    valid_ids = [c['id'] for c in json.loads(chars_path.read_text(encoding='utf-8'))]
    class_by_display = {display_name(cid): cid for cid in valid_ids}

    manifest_path = version_dir / 'team.json'
    if not manifest_path.is_file():
        print(f'FAIL: 找不到 {manifest_path}')
        return 1
    manifest = json.loads(manifest_path.read_text(encoding='utf-8'))
    missing = [k for k in FIELDS if not isinstance(manifest.get(k), str) or not manifest[k].strip()]
    if missing:
        print(f'FAIL: team.json 缺少字段 {missing}')
        return 1

    displays = [n.strip() for n in manifest['team'].split(',') if n.strip()]
    unknown = [d for d in displays if d not in class_by_display]
    if unknown:
        print(f'FAIL: team.json 含未知角色显示名 {unknown}')
        return 1
    class_names = [class_by_display[d] for d in displays]
    sources = [src_dir / f'{c}.py' for c in class_names]
    absent = [str(p) for p in sources if not p.is_file()]
    if absent:
        print(f'FAIL: 找不到角色代码 {absent}')
        return 1

    zip_name = '_'.join(class_names + [safe(manifest['author']), safe(manifest['version'])]) + '.zip'
    zip_path = version_dir / zip_name
    if zip_path.exists():
        print(f'REFUSE: {zip_path} 已存在，不覆盖；请换版本号')
        return 2

    with zipfile.ZipFile(zip_path, 'x', compression=zipfile.ZIP_DEFLATED) as z:
        z.write(manifest_path, 'team.json')
        for c, p in zip(class_names, sources):
            z.write(p, f'{c}.py')

    try:
        _, members, codes, names = inspect_archive(zip_path, valid_ids)
        run_validate(py_exe, validate_path, codes)
    except (ValueError, UnicodeDecodeError, json.JSONDecodeError) as e:
        print(f'FAIL: {e}')
        zip_path.unlink(missing_ok=True)
        return 1

    print(f'OK: {zip_path}')
    print(f'members: {names}')
    print(f'team: {members}')
    return 0


if __name__ == '__main__':
    sys.exit(main())
