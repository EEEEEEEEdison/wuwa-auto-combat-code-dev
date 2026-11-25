"""Static self-check for a workshop axis team's hand-off chain (dev tool, not packed into the zip).

Compares the chain you designed (EXPECTED) with every literal
    self._force_switch_to(self._find_teammate('X'), 'mode')
written inside each class's perform_* methods. Run it before every repack.

Axis model:
- f modes = startup axis (once per fight).
- LOOP_PREFIXES (default ('s',), extend to e.g. ('s', 'c', 'z') for variant/end-of-fight axes)
  = loop/post-startup modes that form a closed graph.
- Exactly one startup->loop edge (STARTUP_END) joins them; every edge leaving a loop mode must go to
  a loop mode, and every loop mode must have both an in-edge and an out-edge (closed).

Usage: python verify_chain.py [team_dir]    (default: this script's directory)
Exit code: 0 = PASS, 1 = FAIL.

Replace FILES / EXPECTED / STARTUP_END / LOOP_PREFIXES / PENDING below with your team's chain.
After adding a new assertion, break one edge on purpose and confirm the exit code is 1.
"""
import ast
import pathlib
import sys

# Class names; each must live in <ClassName>.py inside team_dir.
FILES = ('Alpha', 'Beta', 'Gamma')

# Mode prefixes treated as loop/post-startup axis (e.g. ('s', 'c', 'z') when using variant/final axes).
LOOP_PREFIXES = ('s',)

# (source class, source mode, target class, target mode)
# Startup axis: Alpha f1 -> Beta f1 -> Gamma f1 -> Alpha f2 -> Gamma f2 -> Beta s1
# Loop axis:    Beta s1 -> Gamma s1 -> Alpha s1 -> Beta s1 (closed)
EXPECTED = [
    ('Alpha', 'f1', 'Beta', 'f1'),
    ('Beta', 'f1', 'Gamma', 'f1'),
    ('Gamma', 'f1', 'Alpha', 'f2'),
    ('Alpha', 'f2', 'Gamma', 'f2'),
    ('Gamma', 'f2', 'Beta', 's1'),
    ('Beta', 's1', 'Gamma', 's1'),
    ('Gamma', 's1', 'Alpha', 's1'),
    ('Alpha', 's1', 'Beta', 's1'),
]

# Endpoints whose perform_<mode> is not written yet: {('Class', 'mode'), ...}
PENDING = set()
# The single startup->loop edge that ends the startup axis.
STARTUP_END = ('Gamma', 'f2', 'Beta', 's1')

WIDTH = max(len(name) for name in FILES)


def _is_loop(mode):
    return bool(mode) and mode.startswith(LOOP_PREFIXES)


def _target_of(call):
    """Extract ('X', 'mode') from _force_switch_to(self._find_teammate('X'), 'mode')."""
    target = mode = None
    if call.args and isinstance(call.args[0], ast.Call) and call.args[0].args:
        arg0 = call.args[0].args[0]
        if isinstance(arg0, ast.Constant):
            target = arg0.value
    if len(call.args) > 1 and isinstance(call.args[1], ast.Constant):
        mode = call.args[1].value
    return target, mode


def scan(root):
    edges, methods = [], {}
    for name in FILES:
        tree = ast.parse((root / f'{name}.py').read_text(encoding='utf-8'))
        for cls in (n for n in ast.walk(tree) if isinstance(n, ast.ClassDef)):
            for fn in (f for f in cls.body if isinstance(f, ast.FunctionDef)):
                methods.setdefault(name, set()).add(fn.name)
                if not fn.name.startswith('perform_'):
                    continue
                for call in ast.walk(fn):
                    if (isinstance(call, ast.Call) and isinstance(call.func, ast.Attribute)
                            and call.func.attr == '_force_switch_to'):
                        target, mode = _target_of(call)
                        edges.append((name, fn.name[len('perform_'):], target, mode))
    return edges, methods


def _fmt(e):
    return f'{e[0]:{WIDTH}} {e[1]}  ->  {e[2]}.{e[3]}'


def main():
    root = pathlib.Path(sys.argv[1]) if len(sys.argv) > 1 else pathlib.Path(__file__).resolve().parent
    edges, methods = scan(root)
    ok = True
    loop_label = '/'.join(LOOP_PREFIXES)

    print('=== Hand-offs found in code ===')
    for e in edges:
        print(f'  {_fmt(e)}')

    print('=== Compared with EXPECTED ===')
    for exp in EXPECTED:
        hit = exp in edges
        ok &= hit
        print(f'  {"OK     " if hit else "MISSING"} {_fmt(exp)}')
    extra = [e for e in edges if e not in EXPECTED]
    for e in extra:
        print(f'  UNEXPECTED {_fmt(e)}')
    ok &= not extra

    print(f'=== Axis boundary: exactly one f->{loop_label} edge, {loop_label} modes form a closed loop ===')
    f2s = [e for e in edges if not _is_loop(e[1]) and _is_loop(e[3])]
    s2s = [e for e in edges if _is_loop(e[1])]
    loop = [e for e in EXPECTED if _is_loop(e[1])]
    if f2s == [STARTUP_END]:
        print(f'  OK  single f->{loop_label} edge {_fmt(STARTUP_END)} (startup end)')
    else:
        ok = False
        for e in f2s:
            print(f'  BAD f->{loop_label} edge {_fmt(e)} (expected only {_fmt(STARTUP_END)}); startup axis cut short?')
        if not f2s:
            print(f'  BAD no f->{loop_label} edge: the startup axis never reaches the loop axis')
    if sorted(s2s) == sorted(loop):
        print(f'  OK  {len(s2s)} edges leaving {loop_label} modes match EXPECTED')
    else:
        ok = False
        for e in sorted(set(s2s) - set(loop), key=str):
            print(f'  BAD extra edge leaving a {loop_label} mode {_fmt(e)}')
        for e in sorted(set(loop) - set(s2s), key=str):
            print(f'  BAD missing edge leaving a {loop_label} mode {_fmt(e)}')
    bad_loop_dst = [e for e in s2s if not _is_loop(e[3])]
    for e in bad_loop_dst:
        ok = False
        print(f'  BAD {loop_label} edge returns to non-loop mode {_fmt(e)}')
    # Closure: every mode entered by a loop edge must also leave by a loop edge, or the loop breaks there.
    srcs = {(e[0], e[1]) for e in loop}
    dsts = {(e[2], e[3]) for e in loop}
    if srcs == dsts:
        print(f'  OK  closed loop: {len(srcs)} {loop_label} modes, each entered and left')
    else:
        ok = False
        for n in sorted(dsts - srcs, key=str):
            print(f'  BAD {n[0]}.{n[1]} has a loop in-edge but no loop out-edge: the loop breaks here')
        for n in sorted(srcs - dsts, key=str):
            print(f'  BAD {n[0]}.{n[1]} has a loop out-edge but no loop in-edge: unreachable')

    print('=== Target perform_<mode> exists ===')
    for src, src_mode, target, mode in edges:
        hit = target in methods and f'perform_{mode}' in methods[target]
        pending = (target, mode) in PENDING
        ok &= hit or pending
        if hit:
            print(f'  OK      {target}.perform_{mode}')
        elif pending:
            print(f'  PENDING {target}.perform_{mode}')
        elif target is None or mode is None:
            print(f'  BAD     {src}.perform_{src_mode}: _force_switch_to is not the literal form')
        else:
            print(f'  BAD     {target}.perform_{mode} does not exist')

    print('\nHand-off chain check:', 'PASS' if ok else 'FAIL')
    return 0 if ok else 1


if __name__ == '__main__':
    sys.exit(main())
