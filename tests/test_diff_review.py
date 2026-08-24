"""The look you take before anything is pushed. git does the diffing - we only ask it the
right three questions (what is committed and not pushed, what is changed and not committed,
and what is NEW, which `git diff` never mentions at all) and cut the answer into one entry
per file. Read-only by construction: `diff` and `status`, never
`add`, never `stash` - reviewing must not disturb what the agent is in the middle of.
"""
import os, subprocess, tempfile, unittest

from taskuary import proof
from taskuary.store import MemoryStore


def _run(cwd, *args): subprocess.run(['git', '-C', cwd, *args], capture_output=True, check=True)


def _repo() -> str:
    d = tempfile.mkdtemp()
    _run(d, 'init', '-q', '-b', 'main')
    _run(d, 'config', 'user.email', 'a@b.c'); _run(d, 'config', 'user.name', 'T')
    open(os.path.join(d, 'app.py'), 'w').write('def go():\n    return 1\n')
    _run(d, 'add', '-A'); _run(d, 'commit', '-qm', 'first')
    return d


class WorkingDiffTests(unittest.TestCase):
    def test_a_clean_checkout_has_nothing_to_review(self):
        self.assertEqual(proof.split_files(proof.working_diff(_repo())), [])

    def test_edits_and_brand_new_files_both_show(self):
        """The one that matters: `git diff` says NOTHING about a file the agent just created,
        so a review built on it alone silently omits every new file - the most important
        thing an agent does."""
        d = _repo()
        open(os.path.join(d, 'app.py'), 'w').write('def go():\n    return 2\n')
        os.makedirs(os.path.join(d, 'sub'))
        open(os.path.join(d, 'sub', 'new.py'), 'w').write('a\nb\nc\n')
        files = {f['path']: f for f in proof.split_files(proof.working_diff(d))}
        self.assertEqual(set(files), {'app.py', 'sub/new.py'})
        self.assertEqual((files['app.py']['added'], files['app.py']['removed']), (1, 1))
        self.assertEqual((files['sub/new.py']['added'], files['sub/new.py']['removed']), (3, 0))
        self.assertIn('+    return 2', files['app.py']['patch'])
        self.assertNotIn('return 2', files['sub/new.py']['patch'])   # each file keeps its OWN patch

    def test_staged_work_is_still_uncommitted_work(self):
        """`git diff` with no argument hides anything staged - and a push carries it. HEAD is
        what makes the question 'what would leave this machine', not 'what did you forget to
        add'."""
        d = _repo()
        open(os.path.join(d, 'app.py'), 'w').write('def go():\n    return 3\n')
        _run(d, 'add', '-A')
        self.assertEqual([f['path'] for f in proof.split_files(proof.working_diff(d))], ['app.py'])

    def test_reviewing_never_touches_the_tree(self):
        d = _repo()
        open(os.path.join(d, 'untracked.py'), 'w').write('x = 1\n')
        before = subprocess.run(['git', '-C', d, 'status', '--porcelain'], capture_output=True, text=True).stdout
        proof.working_diff(d)
        after = subprocess.run(['git', '-C', d, 'status', '--porcelain'], capture_output=True, text=True).stdout
        self.assertEqual(before, after)                 # nothing staged, nothing stashed
        head = subprocess.run(['git', '-C', d, 'rev-parse', 'HEAD'], capture_output=True, text=True).stdout
        self.assertTrue(head.strip())                   # and no commit was made

    def test_a_folder_that_is_not_a_checkout_is_not_an_error(self):
        self.assertEqual(proof.working_diff(tempfile.mkdtemp()), '')
        self.assertEqual(proof.working_diff('/no/such/place'), '')
        self.assertEqual(proof.working_diff(''), '')


class SplitTests(unittest.TestCase):
    def test_files_from_still_reports_what_it_always_did(self):
        """The proof card counts on this shape; splitting per file must not change it."""
        d = _repo()
        open(os.path.join(d, 'app.py'), 'w').write('def go():\n    return 9\n')
        self.assertEqual(proof.files_from(proof.working_diff(d)),
                         [{'path': 'app.py', 'added': 1, 'removed': 1}])

    def test_a_binary_change_says_so_instead_of_opening_onto_nothing(self):
        d = _repo()
        open(os.path.join(d, 'logo.png'), 'wb').write(b'\x89PNG\r\n\x1a\n' + bytes(range(256)))
        f = next(x for x in proof.split_files(proof.working_diff(d)) if x['path'] == 'logo.png')
        self.assertTrue(f['binary'])
        self.assertEqual((f['added'], f['removed']), (0, 0))


class ReviewTests(unittest.TestCase):
    def test_the_live_sessions_cwd_wins_over_any_tag(self):
        """Where the agent is actually typing beats what a tag claims - the tag can be stale
        or absent, the pty cannot."""
        d = _repo()
        open(os.path.join(d, 'app.py'), 'w').write('def go():\n    return 4\n')
        s = MemoryStore()
        tid = s.create_task({'Title': 'work', 'Kind': 'coding', 'Tags': 'repo:someone/elsewhere'}, 'o')
        from unittest import mock
        with mock.patch('taskuary.terminal.for_task', return_value={'cwd': d, 'alive': True}):
            out = proof.review(s, tid)
        self.assertEqual(out['cwd'], d)
        self.assertEqual([f['path'] for f in out['files']], ['app.py'])
        self.assertEqual((out['added'], out['removed']), (1, 1))
        self.assertEqual(out['branch'], 'main')

    def test_no_checkout_says_what_to_do_rather_than_failing(self):
        s = MemoryStore()
        tid = s.create_task({'Title': 'work', 'Kind': 'coding'}, 'o')
        from unittest import mock
        with mock.patch('taskuary.terminal.for_task', return_value=None):
            out = proof.review(s, tid)
        self.assertEqual(out['files'], [])
        self.assertIn('start a session', out['why'])

    def test_a_huge_patch_is_listed_but_not_rendered(self):
        d = _repo()
        open(os.path.join(d, 'bundle.js'), 'w').write('x\n' * 200_000)
        s = MemoryStore()
        tid = s.create_task({'Title': 'work'}, 'o')
        from unittest import mock
        with mock.patch('taskuary.terminal.for_task', return_value={'cwd': d, 'alive': True}):
            f = next(x for x in proof.review(s, tid)['files'] if x['path'] == 'bundle.js')
        self.assertTrue(f['truncated'])
        self.assertEqual(f['patch'], '')
        self.assertEqual(f['added'], 200_000)          # the COUNT still tells you what happened




class PushBaseTests(unittest.TestCase):
    """"What a push would carry" has to mean it. CODER.md tells agents to commit locally and
    stop, so the finished state of a task is a CLEAN working tree with commits waiting - and
    a reviewer measuring against HEAD called that "nothing changed"."""

    def _tracked(self):
        """A repo with an upstream, the way a real checkout has one."""
        origin = _repo()
        _run(origin, 'config', 'receive.denyCurrentBranch', 'ignore')
        d = tempfile.mkdtemp()
        subprocess.run(['git', 'clone', '-q', origin, d], capture_output=True, check=True)
        _run(d, 'config', 'user.email', 'a@b.c'); _run(d, 'config', 'user.name', 'T')
        return d

    def test_a_committed_but_unpushed_change_is_still_a_change(self):
        d = self._tracked()
        open(os.path.join(d, 'app.py'), 'w').write('def go():\n    return 42\n')
        _run(d, 'commit', '-aqm', 'fix it')
        base, ahead, up = proof.push_base(d)
        self.assertEqual(ahead, 1)
        self.assertTrue(up.endswith('main'))
        files = proof.split_files(proof.working_diff(d))
        self.assertEqual([f['path'] for f in files], ['app.py'])   # HEAD said nothing at all
        self.assertIn('+    return 42', files[0]['patch'])

    def test_committed_and_uncommitted_arrive_together(self):
        d = self._tracked()
        open(os.path.join(d, 'app.py'), 'w').write('def go():\n    return 42\n')
        _run(d, 'commit', '-aqm', 'fix it')
        open(os.path.join(d, 'notes.txt'), 'w').write('still working\n')      # untracked
        open(os.path.join(d, 'app.py'), 'a').write('# and one more edit\n')   # uncommitted
        paths = {f['path'] for f in proof.split_files(proof.working_diff(d))}
        self.assertEqual(paths, {'app.py', 'notes.txt'})

    def test_a_pushed_checkout_shows_nothing_to_push(self):
        d = self._tracked()
        open(os.path.join(d, 'app.py'), 'w').write('def go():\n    return 42\n')
        _run(d, 'commit', '-aqm', 'fix it')
        _run(d, 'push', '-q')
        self.assertEqual(proof.push_base(d)[1], 0)
        self.assertEqual(proof.split_files(proof.working_diff(d)), [])

    def test_a_checkout_with_nowhere_to_push_falls_back_to_HEAD(self):
        """A plain `git init` has no upstream; the reviewer still has to work."""
        d = _repo()
        base, ahead, up = proof.push_base(d)
        self.assertEqual((base, ahead, up), ('HEAD', 0, ''))
        open(os.path.join(d, 'app.py'), 'w').write('changed\n')
        self.assertEqual([f['path'] for f in proof.split_files(proof.working_diff(d))], ['app.py'])

    def test_the_review_reports_how_far_ahead_it_is(self):
        from unittest import mock
        d = self._tracked()
        open(os.path.join(d, 'app.py'), 'w').write('one\n'); _run(d, 'commit', '-aqm', 'a')
        open(os.path.join(d, 'app.py'), 'w').write('two\n'); _run(d, 'commit', '-aqm', 'b')
        s = MemoryStore()
        tid = s.create_task({'Title': 'work', 'Kind': 'coding'}, 'o')
        with mock.patch('taskuary.terminal.for_task', return_value={'cwd': d, 'alive': True}):
            out = proof.review(s, tid)
        self.assertEqual(out['ahead'], 2)
        self.assertTrue(out['upstream'].endswith('main'))


if __name__ == '__main__':
    unittest.main()
