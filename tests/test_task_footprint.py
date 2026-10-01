"""A task's drawer shows ITS changes in a checkout other tasks share (proof.touched_by).

The shape (2026-10-01): two tasks in one checkout. Another task's unpushed fix changed two transforms and a test file; this
task changed that same test file and a script, uncommitted - the script already dirty when its session reopened. The drawer
showed the other task's commit as "1 commit of its own" with its two transforms, and not the script at all."""
import os, subprocess, tempfile, unittest
from types import SimpleNamespace
from unittest import mock

from taskuary import proof, terminal as term
from taskuary.store import MemoryStore, task_ref


def git(cwd, *a): return subprocess.run(['git', *a], cwd=cwd, capture_output=True, text=True, check=True).stdout


class FootprintTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory(); root = self.tmp.name
        bare, self.co = os.path.join(root, 'origin.git'), os.path.join(root, 'co')
        git(root, 'init', '-q', '--bare', bare); git(root, 'clone', '-q', bare, self.co)
        for k, v in (('user.name', 'Alex Doyle'), ('user.email', 'alex@northwind.example')): git(self.co, 'config', k, v)
        for f in ('src/a.py', 'src/b.py', 'tests/test_smoke.py', 'scripts/run.py'): self.write(f, 'x = 1\n')
        git(self.co, 'add', '-A'); git(self.co, 'commit', '-qm', 'start'); git(self.co, 'push', '-q', '-u', 'origin', 'HEAD')
        # the OTHER task's fix, committed, not pushed
        for f in ('src/a.py', 'src/b.py', 'tests/test_smoke.py'): self.write(f, 'x = 2\n')
        git(self.co, 'commit', '-qam', 'fix(a,b): a disable reaches an existing account')
        # this task's work, uncommitted
        for f in ('scripts/run.py', 'tests/test_smoke.py'): self.write(f, 'x = 3\n')
        self.s = MemoryStore()
        self.tid = self.s.create_task({'Title': 'Stop the vendor-create mails', 'Kind': 'coding', 'Status': 'open'}, 'owner')
        self._sessions = dict(term.SESSIONS); term.SESSIONS.clear()

    def tearDown(self):
        term.SESSIONS.clear(); term.SESSIONS.update(self._sessions); self.tmp.cleanup()

    def write(self, rel, text):
        p = os.path.join(self.co, rel); os.makedirs(os.path.dirname(p), exist_ok=True)
        with open(p, 'w', encoding='utf-8') as f: f.write(text)

    def session(self, files, edited):
        term.SESSIONS['s1'] = SimpleNamespace(task_id=self.tid, cwd=self.co, files=lambda: files,
                                             witness=SimpleNamespace(files={os.path.join(self.co, *e.split('/')): {'n': 1} for e in edited}))

    def test_another_tasks_commit_is_not_its_own_and_its_own_edit_is_there(self):
        # scripts/run.py was dirty when the session reopened, so dirty-now-minus-dirty-at-open misses it; the agent's edits name it
        self.session(files=['tests/test_smoke.py'], edited=['scripts/run.py', 'tests/test_smoke.py'])
        paths, commits, known = proof.touched_by(self.s, self.tid, self.co)
        self.assertTrue(known)
        self.assertEqual(commits, [], 'one shared file does not make another task\'s commit its own')
        self.assertEqual(sorted(paths), ['scripts/run.py', 'tests/test_smoke.py'])

    def test_a_commit_that_names_the_task_or_holds_only_its_files_is_its_own(self):
        self.write('scripts/run.py', 'x = 4\n'); git(self.co, 'commit', '-qm', f'{task_ref(self.tid)}: only mail on a failed request', '--', 'scripts/run.py')
        self.session(files=[], edited=['scripts/run.py'])
        paths, commits, _ = proof.touched_by(self.s, self.tid, self.co)
        self.assertEqual([c['subject'][:7] for c in commits], [task_ref(self.tid)])
        self.assertNotIn('src/a.py', paths)

    def test_a_path_outside_the_checkout_is_not_the_tasks(self):
        self.assertEqual(proof._rel(self.co, os.path.join(self.tmp.name, 'elsewhere.py')), '')
        self.assertEqual(proof._rel(self.co, os.path.join(self.co, 'scripts', 'run.py')), 'scripts/run.py')


if __name__ == '__main__':
    unittest.main()
