"""Shared by team-workflow and CodeStable; keep both copies identical."""
import importlib.util
from pathlib import Path
import sys
import tempfile
import textwrap
import unittest

ROOT = Path(__file__).resolve().parents[1]
spec = importlib.util.spec_from_file_location('lint_undefined_names', ROOT / 'scripts/lint_undefined_names.py')
lint = importlib.util.module_from_spec(spec)
spec.loader.exec_module(lint)


def names(source, **kwargs):
    findings, skipped = lint.check_source(textwrap.dedent(source), **kwargs)
    return [(row['name'], row['line']) for row in findings], skipped


class LintUndefinedNamesTests(unittest.TestCase):
    def test_valid_scoping_forms_have_no_findings(self):
        cases = {
            'closure': '''
                def outer():
                    value = 1
                    def inner():
                        return value
                    return inner
            ''',
            'comprehensions': '''
                rows = [1, 2]
                pairs = {k: v for k, v in zip(rows, rows)}
                def f(items):
                    return [x for x in items if x], sum(y for y in items), {z for z in items}
            ''',
            'global_nonlocal': '''
                def setup():
                    global CONFIG
                    CONFIG = 1
                def use():
                    return CONFIG
                def counter():
                    total = 0
                    def bump():
                        nonlocal total
                        total += 1
                    return bump
            ''',
            'except_as_and_with': '''
                import json
                def load(path):
                    try:
                        with open(path) as handle:
                            return json.load(handle)
                    except ValueError as exc:
                        return str(exc)
            ''',
            'match_capture': '''
                def kind(value):
                    match value:
                        case {'kind': name, **rest}:
                            return name, rest
                        case [first, *others]:
                            return first, others
                        case str() as text:
                            return text
                    return None
            ''',
            'walrus': '''
                def first(items):
                    if (found := next(iter(items), None)) is not None:
                        return found
                    return [last for item in items if (last := item)]
            ''',
            'super_and_class': '''
                class Base:
                    def run(self):
                        return 1
                class Child(Base):
                    def run(self):
                        return super().run() + len(__class__.__name__)
            ''',
            'lazy_imports_and_dunder': '''
                def later():
                    from pathlib import Path
                    import os.path
                    return Path(__file__), os.path.sep, __name__
            ''',
            'all_exports': '''
                from json import dumps
                def helper():
                    return dumps({})
                __all__ = ['helper', 'dumps']
            ''',
            'lambda_and_defaults': '''
                LIMIT = 3
                sort = lambda rows, key=LIMIT: sorted(rows, key=lambda row: row + key)
            ''',
        }
        for label, source in cases.items():
            with self.subTest(label):
                self.assertEqual(names(source), ([], None))

    def test_missing_import_is_reported_at_each_use(self):
        found, _ = names('''
            from json import dumps
            def gaps(path):
                value = read(path)
                return dumps(value), read(path)
        ''')
        self.assertEqual(found, [('read', 4), ('read', 5)])

    def test_class_attribute_is_not_visible_from_method(self):
        found, _ = names('''
            class Store:
                LIMIT = 3
                def size(self):
                    return LIMIT
        ''')
        self.assertEqual(found, [('LIMIT', 5)])

    def test_module_level_typo_and_all_entry(self):
        found, _ = names('''
            value = 1
            print(valeu)
            __all__ = ['value', 'missing']
        ''')
        self.assertEqual(found, [('valeu', 3), ('missing', 4)])

    def test_star_import_pragma_ignore_and_syntax(self):
        self.assertEqual(names('from os import *\nprint(path)\n')[1]['reason'], 'star-import')
        pragma = lint.SKIP_PRAGMA + '\nprint(nothing)\n'
        self.assertEqual(names(pragma)[1]['reason'], 'skip-file pragma')
        self.assertEqual(names('print(dynamic)\n', ignore=['dynamic']), ([], None))
        findings, _ = lint.check_source('def broken(:\n', 'x.py')
        self.assertEqual(findings[0]['kind'], 'syntax')

    def test_cli_exit_code_and_file_walk(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            (root / 'pkg').mkdir()
            (root / 'pkg/good.py').write_text('import os\nprint(os.sep)\n')
            (root / 'pkg/__pycache__').mkdir()
            (root / 'pkg/__pycache__/bad.py').write_text('print(missing)\n')
            self.assertEqual(lint.main([str(root / 'pkg')]), 0)
            (root / 'pkg/bad.py').write_text('print(missing)\n')
            self.assertEqual(lint.main([str(root / 'pkg')]), 1)
            result = lint.check([root / 'pkg'], root=root.resolve())
            self.assertEqual(result['files'], 2)
            self.assertEqual(result['findings'][0]['path'], 'pkg/bad.py')

    def test_repository_has_no_undefined_names(self):
        # CodeStable runtime sections are concatenated before use; lint the assembled runtime instead.
        paths = [path for path in lint.python_files(ROOT / name for name in ('scripts', 'skills', 'tests'))
                 if 'runtime_src' not in path.parts]
        result = lint.check(paths, root=ROOT)
        self.assertEqual(result['findings'], [], result['findings'])
        self.assertEqual(result['python'], sys.version.split()[0])


if __name__ == '__main__':
    unittest.main()
