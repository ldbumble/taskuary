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
        # ...the wheel's help/ is docs/site/*.md copied in at publish (publish.yml); the exe carries docs/site itself, which lookups reads first
        if "('docs/site/*.md', 'docs/site')" in (ROOT / 'taskuary.spec').read_text(encoding='utf-8'): missing.discard('help')
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


class TheVideoConverterShipsTests(unittest.TestCase):
    def test_the_exe_collects_imageio_ffmpeg_with_its_binary(self):
        """A post's video is made an MP4 by the ffmpeg imageio-ffmpeg ships (linkedin.as_mp4). It is a runtime dependency
        of the wheel, but the exe only carries what the spec collects - and get_ffmpeg_exe() finds the binary as a data
        file of imageio_ffmpeg.binaries, which only collect_all (data files and submodules, as PyInstaller's own
        imageio_ffmpeg hook takes) brings along."""
        self.assertIn('imageio-ffmpeg', (ROOT / 'pyproject.toml').read_text(encoding='utf-8'))
        call = re.search(r'^datas, bins, hidden = _collect\((.+?)\)$', (ROOT / 'taskuary.spec').read_text(encoding='utf-8'), re.M)
        self.assertTrue(call, 'taskuary.spec no longer collects its packages in one _collect call')
        self.assertIn("'imageio_ffmpeg'", call.group(1))


class TheSpecStillParsesTests(unittest.TestCase):
    def test_the_spec_is_valid_python(self):
        ast.parse((ROOT / 'taskuary.spec').read_text(encoding='utf-8'))


class TheWebServerHasAFloorTests(unittest.TestCase):
    def test_starlette_and_fastapi_are_pinned_above_their_known_advisories(self):
        "Red team #3: starlette came in through fastapi with no floor of its own, so an old one with published advisories still installed."
        deps = re.findall(r'^\s*"([A-Za-z_-]+)>=([\d.]+)', (ROOT / 'pyproject.toml').read_text(encoding='utf-8'), re.M)
        floor = {n: tuple(int(x) for x in v.split('.')) for n, v in deps}
        self.assertGreaterEqual(floor.get('starlette', ()), (0, 49, 1))
        self.assertGreaterEqual(floor.get('fastapi', ()), (0, 115))


if __name__ == '__main__':
    unittest.main()
