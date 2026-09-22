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

    def test_lanes_json_by_name_because_it_is_read_at_import(self):
        """Named on its own: every module that touches a lane pulls it in before the app can answer
        anything, so its absence is not a degraded feature - it is a dead install."""
        self.assertIn('lanes.json', spec_data())
        self.assertIn('lanes.json', wheel_data())

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
