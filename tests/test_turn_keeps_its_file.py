"""Each turn keeps the file as it made it (the owner, 2026-11-07: "same file with revisions"). An agent rewrote one comparison in place over
three turns, and the first turn - whose words were about three tools - drew the newest table, four tools cheapest first, under them: an earlier
turn rewritten. The turn that writes a file keeps its version, a copy when it is small and only its name when it is large ("changed later");
the newest turn and the file itself are the latest."""
import json, os, tempfile, time, unittest
from pathlib import Path
from unittest import mock

from fastapi.testclient import TestClient

from taskuary import general, outputs, server
from taskuary.store import MemoryStore


class TurnKeepsItsFile(unittest.TestCase):
    def setUp(self):
        home = tempfile.TemporaryDirectory(); self.addCleanup(home.cleanup)
        p = mock.patch.dict(os.environ, {'TASKUARY_HOME': home.name}); p.start(); self.addCleanup(p.stop)
        self.s = MemoryStore()
        self.tid = self.s.create_task({'Title': 'Compare expense tools for Northwind', 'Kind': 'general'}, 'o')
        self.ses = general.GeneralSession(self.s, self.tid)
        self.ses.pick, self.ses.provider, self.ses.model = 'cli:claude', 'Claude Code', ''
        p = mock.patch('taskuary.hooks.judge_ended', lambda *a, **k: None); p.start(); self.addCleanup(p.stop)

    def turn(self, ask, writes):
        "One turn whose agent writes `writes` {name: text} into the task's outputs folder, as a CLI with hands does."
        def brain(system, user, **k):
            for name, text in writes.items():
                (f := outputs.folder(self.tid) / name).parent.mkdir(parents=True, exist_ok=True); f.write_text(text, encoding='utf-8')
            return f'Done - see `{next(iter(writes))}`.'
        with mock.patch.object(general.llm_mod, 'build_llm', return_value=brain): self.ses.send_prompt(ask)
        time.sleep(0.02)
        return max(c['CommentId'] for c in self.s.list_comments(self.tid) if c['ActorType'] == general.ASSISTANT_TYPE)

    def payload(self):
        with mock.patch.object(server, 'store', self.s): return server._assistant_payload(self.tid)

    def test_an_earlier_turn_keeps_the_version_it_made(self):
        one = self.turn('Compare three tools.', {'tools.md': '| Spendly | Expensify | Zoho |'})
        self.assertEqual(self.payload()['turnOutputs'], [])                       # nothing changed it since: the file IS turn 1's
        two = self.turn('Add one, cheapest first.', {'tools.md': '| Ramp | Expensify | Fyle | Spendly |'})
        got = self.payload()
        then = [v for v in got['turnOutputs'] if v['path'] == 'tools.md']
        self.assertEqual([v['turn'] for v in then], [f'comment-{one}'])           # turn 1 has its own...
        self.assertEqual([o['after'] for o in got['outputs'] if o['path'] == 'tools.md'], [f'comment-{two}'])   # ...the newest turn the file
        with mock.patch.object(server, 'store', self.s):
            c = TestClient(server.app)
            self.assertIn('Zoho', c.get(then[0]['url']).text)                     # turn 1's copy, as it left it
            self.assertIn('Ramp', c.get(f'/api/task-outputs/{self.tid}/tools.md').text)
            self.assertEqual(c.get(f'/api/task-outputs/{self.tid}/tools.md?turn=999').status_code, 404)   # a turn that kept none: no file

    def test_a_large_file_is_only_named_and_reads_changed_later(self):
        with mock.patch.object(outputs, 'TURN_COPY_MAX', 10):
            one = self.turn('Build the workbook.', {'book.csv': 'a,b\n' * 20})
            self.turn('Add a column.', {'book.csv': 'a,b,c\n' * 20})
        self.assertFalse(outputs.turn_folder(self.tid, one).exists())                # no copy of a big file...
        v, = self.payload()['turnOutputs']
        self.assertEqual((v['turn'], v['later']), (f'comment-{one}', True))           # ...its name, "changed later"
        self.assertNotIn('?turn=', v['url'])

    def test_a_turn_that_wrote_nothing_keeps_nothing(self):
        self.turn('Write it.', {'tools.md': 'v1'})
        with mock.patch.object(general.llm_mod, 'build_llm', return_value=lambda *a, **k: 'Nothing to change.'): self.ses.send_prompt('Looks good?')
        self.assertEqual(len(list(outputs.turns_folder(self.tid).glob('*.json'))), 1)


if __name__ == '__main__':
    unittest.main()
