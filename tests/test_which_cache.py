"""Where a CLI is, asked once - and still the answer shutil.which would give now (perf report 2.7, 2026-10-19).

Every setup, first-run, agents and CLI request scanned PATH for every AI CLI: ~13,300 stats a request, a second or more
behind a bare spinner. The owner's rule for the fix: "not how it works, just working faster". So each test here pins
an answer to the uncached one: a CLI that appears, one that goes away, a PATH that changes, a mock that stands in."""
import os, shutil, tempfile, unittest
from pathlib import Path
from unittest import mock

from taskuary import cliinstall, clis, pathcache

EXE = 'nwtool.exe' if os.name == 'nt' else 'nwtool'


class WhichCacheTests(unittest.TestCase):
    def setUp(self):
        self.a, self.b = tempfile.mkdtemp(), tempfile.mkdtemp()
        env = mock.patch.dict(os.environ, {'PATH': os.pathsep.join([self.a, self.b])}); env.start(); self.addCleanup(env.stop)
        ttl = mock.patch.object(pathcache, 'SIG_TTL', 0); ttl.start(); self.addCleanup(ttl.stop)   # every look re-reads the mtimes
        self.n, real = [0], shutil.which
        def counting(*a, **k): self.n[0] += 1; return real(*a, **k)
        p = mock.patch.object(pathcache, '_scan', counting); p.start(); self.addCleanup(p.stop)
        pathcache.forget()

    def put(self, d, name=EXE):
        f = Path(d) / name; f.write_text('#!/bin/sh\ntrue\n'); f.chmod(0o755); return f

    def test_a_second_look_does_not_scan_again(self):
        self.put(self.b)
        first = pathcache.which('nwtool')
        self.assertEqual(Path(first).resolve(), (Path(self.b) / EXE).resolve())
        for _ in range(5): self.assertEqual(pathcache.which('nwtool'), first)
        self.assertEqual(self.n[0], 1)

    def test_a_cli_installed_after_the_first_look_is_found(self):
        self.assertIsNone(pathcache.which('nwtool'))
        self.put(self.b)
        self.assertEqual(Path(pathcache.which('nwtool')).resolve(), (Path(self.b) / EXE).resolve())

    def test_a_copy_earlier_on_path_wins_as_it_would_uncached(self):
        self.put(self.b); pathcache.which('nwtool')
        self.put(self.a)
        self.assertEqual(Path(pathcache.which('nwtool')).resolve(), (Path(self.a) / EXE).resolve())

    def test_a_removed_cli_is_gone(self):
        f = self.put(self.b); self.assertTrue(pathcache.which('nwtool'))
        f.unlink()
        self.assertIsNone(pathcache.which('nwtool'))

    def test_a_changed_path_is_its_own_question(self):
        self.put(self.b); self.assertTrue(pathcache.which('nwtool'))
        with mock.patch.dict(os.environ, {'PATH': self.a}): self.assertIsNone(pathcache.which('nwtool'))
        self.assertIsNone(pathcache.which('nwtool', path=self.a))
        self.assertTrue(pathcache.which('nwtool', path=self.b))

    def test_forget_scans_again(self):
        pathcache.which('nwtool'); pathcache.forget(); pathcache.which('nwtool')
        self.assertEqual(self.n[0], 2)

    def test_a_mock_of_which_is_asked_never_the_cache(self):
        self.put(self.b); self.assertTrue(pathcache.which('nwtool'))
        with mock.patch.object(shutil, 'which', return_value=None): self.assertIsNone(pathcache.which('nwtool'))
        with mock.patch.object(shutil, 'which', side_effect=lambda c, path=None: '/x/' + c): self.assertEqual(pathcache.which('nwtool'), '/x/nwtool')
        answers = iter(['/x/one', None])     # a stateful double is asked every time, as it was before the cache
        with mock.patch.object(shutil, 'which', side_effect=lambda c, **k: next(answers)):
            self.assertEqual(pathcache.which('nwtool'), '/x/one'); self.assertIsNone(pathcache.which('nwtool'))
        self.assertEqual(self.n[0], 1, 'the doubles were asked, never the real scan')

    def test_no_answer_outlives_max_age(self):
        pathcache.which('nwtool')
        with mock.patch.object(pathcache, 'MAX_AGE', 0): pathcache.which('nwtool')
        self.assertEqual(self.n[0], 2)

    def test_a_mode_or_explicit_path_is_its_own_question(self):
        self.put(self.b); pathcache.which('nwtool'); pathcache.which('nwtool', path=self.b); pathcache.which('nwtool', mode=os.F_OK)
        self.assertEqual(self.n[0], 3)
        self.assertEqual(pathcache.which('nwtool', mode=os.F_OK), shutil.which('nwtool', mode=os.F_OK))

    def test_a_directory_in_the_name_is_never_remembered(self):
        f = self.put(self.b); self.assertEqual(pathcache.which(str(f)), shutil.which(str(f))); pathcache.which(str(f))
        self.assertEqual(self.n[0], 2)

    def test_detection_says_what_uncached_detection_says(self):
        self.put(self.b, 'claude.cmd' if os.name == 'nt' else 'claude')
        with mock.patch.object(cliinstall, 'npm', return_value=''): want = clis.detect(None)
        with mock.patch.object(cliinstall, 'npm', return_value=''):
            self.assertEqual(clis.detect(None), want)
            n = self.n[0]; self.assertEqual(clis.detect(None), want)
        self.assertEqual(self.n[0], n, 'a third detect over an unchanged PATH scans nothing')

    def test_an_install_phase_change_forgets(self):
        pathcache.which('nwtool'); cliinstall._set('installing', 'claude'); pathcache.which('nwtool')
        self.assertEqual(self.n[0], 2)
        cliinstall.reset()

    def test_a_dir_put_on_path_is_searched(self):
        c = tempfile.mkdtemp(); self.put(c); self.assertIsNone(pathcache.which('nwtool'))
        with mock.patch.object(cliinstall, 'persist_windows'), mock.patch.object(cliinstall, 'persist_posix'): cliinstall.ensure_on_path(c)
        self.assertEqual(Path(pathcache.which('nwtool')).resolve(), (Path(c) / EXE).resolve())


class SharedSignatureTests(unittest.TestCase):
    def test_a_burst_reads_the_directories_once(self):
        d = tempfile.mkdtemp(); pathcache.forget()
        with mock.patch.dict(os.environ, {'PATH': d}), mock.patch.object(pathcache, '_mtime', wraps=pathcache._mtime) as m:
            for c in ('nwa', 'nwb', 'nwc', 'nwa', 'nwb'): pathcache.which(c)
        self.assertEqual(m.call_count, 2 if os.name == 'nt' else 1)      # the dir (and on Windows the cwd), once


if __name__ == '__main__':
    unittest.main()
