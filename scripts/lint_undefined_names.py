#!/usr/bin/env python3
"""Report names that are read but never bound, using the compiler's own scope tables.

Shared byte-for-byte by team-workflow and CodeStable; keep both copies identical.
Standard library only, Python 3.10+. No flow analysis: use-before-assignment is out of scope.
"""
import argparse
import ast
import builtins
import json
from pathlib import Path
import symtable
import sys

LINT_VERSION = '1.0.0'
SKIP_PRAGMA = '# lint-undefined-names: skip-file'
MODULE_NAMES = {'__file__', '__name__', '__doc__', '__package__', '__spec__', '__loader__', '__builtins__',
                '__annotations__', '__path__', '__debug__', '__cached__', '__dict__'}
CLASS_NAMES = {'__class__', '__module__', '__qualname__'}
SCOPES = (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef, ast.Lambda)


def tables(top):
    yield top
    for child in top.get_children():
        yield from tables(child)


def star_import(tree):
    return any(isinstance(node, ast.ImportFrom) and any(alias.name == '*' for alias in node.names)
               for node in ast.walk(tree))


def module_bindings(top, every):
    defined = set(dir(builtins)) | MODULE_NAMES | CLASS_NAMES
    for symbol in top.get_symbols():
        if symbol.is_assigned() or symbol.is_imported() or symbol.is_namespace() or symbol.is_declared_global():
            defined.add(symbol.get_name())
    for table in every[1:]:
        for symbol in table.get_symbols():
            if symbol.is_declared_global() and (symbol.is_assigned() or symbol.is_imported() or symbol.is_namespace()):
                defined.add(symbol.get_name())
    return defined


def scope_node(tree, table):
    if table.get_type() == 'module':
        return tree
    for node in ast.walk(tree):
        if isinstance(node, SCOPES) and node.lineno == table.get_lineno():
            if isinstance(node, ast.Lambda) or node.name == table.get_name():
                return node
    return tree


def occurrences(node, name):
    found = [n for n in ast.walk(node) if isinstance(n, ast.Name) and n.id == name
             and isinstance(n.ctx, (ast.Load, ast.Del))]
    return sorted(found, key=lambda n: (n.lineno, n.col_offset))


def unbound(table, defined):
    for symbol in table.get_symbols():
        name = symbol.get_name()
        if name.startswith('.') or not symbol.is_referenced() or name in defined:
            continue
        if table.get_type() == 'module':
            if not (symbol.is_assigned() or symbol.is_imported() or symbol.is_namespace()):
                yield name
        elif symbol.is_global():
            yield name


def check_source(text, path='<source>', ignore=()):
    if any(line.strip() == SKIP_PRAGMA for line in text.splitlines()):
        return [], {'path': path, 'reason': 'skip-file pragma'}
    try:
        tree = ast.parse(text, path)
    except SyntaxError as exc:
        return [{'path': path, 'line': exc.lineno or 0, 'col': exc.offset or 0, 'name': '',
                 'scope': '', 'kind': 'syntax'}], None
    if star_import(tree):
        return [], {'path': path, 'reason': 'star-import'}
    top = symtable.symtable(text, path, 'exec')
    every = list(tables(top))
    defined = module_bindings(top, every) | set(ignore)
    findings, seen = [], set()
    for table in every:
        node = scope_node(tree, table)
        for name in sorted(unbound(table, defined)):
            spots = occurrences(node, name) or [node]
            for spot in spots:
                key = (getattr(spot, 'lineno', 0), getattr(spot, 'col_offset', 0), name)
                if key in seen:
                    continue
                seen.add(key)
                findings.append({'path': path, 'line': key[0], 'col': key[1], 'name': name,
                                 'scope': table.get_name(), 'kind': 'undefined-name'})
    for node in tree.body:
        targets = node.targets if isinstance(node, ast.Assign) else []
        if any(isinstance(t, ast.Name) and t.id == '__all__' for t in targets) and isinstance(node.value, (ast.List, ast.Tuple)):
            for item in node.value.elts:
                if isinstance(item, ast.Constant) and isinstance(item.value, str) and item.value not in defined:
                    findings.append({'path': path, 'line': item.lineno, 'col': item.col_offset, 'name': item.value,
                                     'scope': 'top', 'kind': 'undefined-in-__all__'})
    return sorted(findings, key=lambda f: (f['line'], f['col'], f['name'])), None


def python_files(paths):
    for raw in paths:
        path = Path(raw)
        if path.is_file():
            yield path
        elif path.is_dir():
            yield from sorted(p for p in path.rglob('*.py') if '__pycache__' not in p.parts)


def check(paths, ignore=(), root=None):
    findings, skipped, count = [], [], 0
    for path in python_files(paths):
        count += 1
        label = path.resolve().relative_to(root).as_posix() if root else path.as_posix()
        found, skip = check_source(path.read_text(encoding='utf-8'), label, ignore)
        findings.extend(found)
        if skip:
            skipped.append(skip)
    return {'ok': not findings, 'lint_version': LINT_VERSION, 'python': sys.version.split()[0],
            'files': count, 'findings': findings, 'skipped': skipped}


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument('paths', nargs='+')
    parser.add_argument('--ignore', action='append', default=[], help='name to treat as defined (repeatable)')
    parser.add_argument('--json', action='store_true')
    args = parser.parse_args(argv)
    result = check(args.paths, args.ignore)
    if args.json:
        print(json.dumps(result, indent=2, ensure_ascii=False))
    else:
        for row in result['findings']:
            print(f"{row['path']}:{row['line']}:{row['col']}: {row['kind']} {row['name']!r} in {row['scope']}")
        print(f"{result['files']} files, {len(result['findings'])} findings, {len(result['skipped'])} skipped")
    return 0 if result['ok'] else 1


if __name__ == '__main__':
    sys.exit(main())
