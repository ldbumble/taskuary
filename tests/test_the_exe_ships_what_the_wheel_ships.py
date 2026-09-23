"""The exe and the wheel are the same program, or neither of them is trustworthy.

taskuary.spec listed three data directories; [tool.setuptools.package-data] listed five things.
`lanes.json` was in the wheel and not in the exe - and workerstate reads it AT IMPORT, with funnel
importing workerstate - so on a machine running the packaged app the Timeline, the Assistant,
/api/setup, /api/problems and every scheduled report answered 500 for ever, while the same version
installed with pip was perfect (a second machine's log, 2026-09-22).

The two lists cannot be kept in step by remembering, so this asks them.
"""
import ast
import re
from fnmatch import fnmatch
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def wheel_data() -> set:
    """The package-data globs pyproject ships, as the top-level file or directory each names."""
    line = re.search(r'^taskuary = \[(.+?)\]', (ROOT / 'pyproject.toml').read_text(encoding='utf-8'), re.M)
    assert line, 'pyproject no longer lists taskuary package-data'
    return {g.strip().strip('"').split('/')[0] for g in line.group(1).split(',') if g.strip()}


def spec_data() -> set:
    """What taskuary.spec puts in the bundle, by source path's last element."""
    spec = (ROOT / 'taskuary.spec').read_text(encoding='utf-8')
    body = re.search(r'datas=\[(.+?)\],\n\s+binaries=', spec, re.S)
    assert body, 'taskuary.spec no longer passes a datas list'
    return {m.split('/')[-1] for m in re.findall(r"\('taskuary/([^']+)'", body.group(1))}


class TheExeShipsWhatTheWheelShipsTests(unittest.TestCase):
    def test_every_data_file_in_the_wheel_is_in_the_exe(self):
        missing = {d for d in wheel_data() if d not in spec_data()}
        self.assertFalse(missing, f'the wheel ships {sorted(missing)} and taskuary.spec does not - '
                                  'an exe without them is a different program')

    def test_every_json_beside_the_code_is_in_both(self):
        """Asked of the FILES, not the list: lanes.json is read at import (workerstate), and so is
        triage_kind_rules.json (store) - a list that named lanes.json and nothing else shipped a
        container that died on the second (2026-09-23). A file in the tree that neither glob
        catches is a dead install, not a degraded feature."""
        files = sorted(f.name for f in (ROOT / 'taskuary').glob('*.json'))
        self.assertIn('lanes.json', files)
        for name in files:
            self.assertTrue(any(fnmatch(name, g) for g in wheel_data()), f'pyproject does not ship {name}')
            self.assertTrue(any(fnmatch(name, g) for g in spec_data()), f'taskuary.spec does not ship {name}')

    def test_the_file_the_import_actually_reads_is_where_both_of_them_put_it(self):
        self.assertTrue((ROOT / 'taskuary' / 'lanes.json').is_file())
        src = (ROOT / 'taskuary' / 'workerstate.py').read_text(encoding='utf-8')
        self.assertIn("Path(__file__).parent / 'lanes.json'", src,
                      'if this read moves, both packaging lists have to follow it')


class TheSpecStillParsesTests(unittest.TestCase):
    def test_the_spec_is_valid_python(self):
        ast.parse((ROOT / 'taskuary.spec').read_text(encoding='utf-8'))


if __name__ == '__main__':
    unittest.main()
