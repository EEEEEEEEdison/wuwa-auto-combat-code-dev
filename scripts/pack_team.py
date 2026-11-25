"""打包 WWisnotOK 工坊配队 zip，并用 WWisnotOK 自带的 strategy_host/validate.py 校验（或 --offline 离线静态校验）。

用法（带 -I -B）：
    完整校验（推荐，需本机 WWisnotOK 目录）：
        <WWisnotOK python.exe> -I -B pack_team.py <版本目录> <WWisnotOK 目录> [--src <代码目录>]
    离线校验（本机无 WWisnotOK 目录时降级使用）：
        python -I -B pack_team.py <版本目录> --offline [--src <代码目录>]

- team.json 取自版本目录。3 个角色 .py 默认也取自版本目录；项目要求先清洗代码时，用 --src 指向清洗结果。
- 完整校验：角色表取自 <WWisnotOK 目录>/assets/characters.json，并调用 strategy_host/validate.py 校验 AST、同名类、BaseChar 继承、模板名与构造安全。
- 离线校验：使用内置静态角色清单 + ZIP 结构 + AST 顶层类定义与 BaseChar 基类检查；不执行代码、不验证构造函数与模板名，结果须在 README 中标明限制。
- zip 写进版本目录，文件名 <类名>_<类名>_<类名>_<author>_<version>.zip，类名按 team 字段顺序。
- 同名 zip 已存在时不覆盖，退出码 2。校验不通过时删掉本次打的 zip，退出码 1。
"""

import argparse
import ast
import json
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
# 离线静态角色清单（同步自 WWisnotOK v0.4.7 assets/characters.json，共 58 个角色）
BUILTIN_CHAR_IDS = (
    'Aalto', 'Aemeath', 'Augusta', 'Baizhi', 'Brant', 'Calcharo', 'Camellya', 'Cantarella',
    'Carlotta', 'Cartethyia', 'Changli', 'Chisa', 'Chixia', 'Ciaccona', 'Danjin', 'Denia',
    'Douling', 'Encore', 'Galbrena', 'Hiyuki', 'Hsin', 'Iuno', 'Jianxin', 'JingRan',
    'Jinhsi', 'Jiyan', 'Lily', 'Lingyang', 'Linnai', 'Lucilla', 'Lucy', 'Luhesi',
    'Lumi', 'Lupa', 'Mornye', 'Mortefi', 'Phoebe', 'Phrolova', 'Qingxiao', 'Qiuyuan',
    'Rebecca', 'Roccia', 'Rover', 'Sanhua', 'ShoreKeeper', 'Suisui', 'Suoming', 'Taoqi',
    'Verina', 'Xiangliyao', 'Xigelika', 'YangYangSp', 'Yangyang', 'Yinlin', 'Youhu',
    'Yuanwu', 'Zani', 'Zhezhi',
)


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


def run_offline_ast_validate(codes):
    """无 WWisnotOK 目录时的离线静态检查：AST 编译、顶层同名类、显式继承 BaseChar。"""
    for name, code in codes.items():
        try:
            tree = ast.parse(code, filename=f'{name}.py')
            compile(tree, f'{name}.py', 'exec')
        except SyntaxError as exc:
            raise ValueError(f'{name}.py 语法错误：{exc}')
        cls_nodes = [n for n in tree.body if isinstance(n, ast.ClassDef) and n.name == name]
        if not cls_nodes:
            raise ValueError(f'{name}.py 顶层缺少 class {name}')
        bases = [ast.unparse(b) for b in cls_nodes[0].bases]
        if not any(b == 'BaseChar' or b.endswith('.BaseChar') for b in bases):
            raise ValueError(f'{name}.py 中 class {name} 未显式继承 BaseChar（当前基类：{bases}）')


def main():
    sys.stdout.reconfigure(encoding='utf-8')
    parser = argparse.ArgumentParser()
    parser.add_argument('version_dir')
    parser.add_argument('wwisnotok_dir', nargs='?')
    parser.add_argument('--offline', action='store_true', help='无 WWisnotOK 目录时改用内置角色表与 AST 静态校验')
    parser.add_argument('--src')
    args = parser.parse_args()
    if not args.offline and not args.wwisnotok_dir:
        parser.error('必须提供 <WWisnotOK 目录>，或在无本地目录时显式传 --offline')

    version_dir = Path(args.version_dir).resolve()
    src_dir = Path(args.src).resolve() if args.src else version_dir

    if args.offline:
        valid_ids = list(BUILTIN_CHAR_IDS)
        validate_path, py_exe = None, None
    else:
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
        if args.offline:
            run_offline_ast_validate(codes)
        else:
            run_validate(py_exe, validate_path, codes)
    except (ValueError, UnicodeDecodeError, json.JSONDecodeError) as e:
        print(f'FAIL: {e}')
        zip_path.unlink(missing_ok=True)
        return 1

    if args.offline:
        print(f'OK (offline): {zip_path}')
        print('note: 仅完成 ZIP 结构与 AST 静态检查，未运行 WWisnotOK strategy_host/validate.py（导入时由宿主做构造与模板校验）')
    else:
        print(f'OK: {zip_path}')
    print(f'members: {names}')
    print(f'team: {members}')
    return 0


if __name__ == '__main__':
    sys.exit(main())
