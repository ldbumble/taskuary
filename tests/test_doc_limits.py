"""How much of each document reaches the agent, said in the Docs editor (the owner, 2026-11-02: "it should not be hard coded in the
code but in coding.md ... and you can always extend the length of what goes into it. Also ... tell the user the max amount of
characters that go into the instructions, with a bar/percentage showing if you are over").

The subagent rule lives in CODING.md, every shipped document fits under the number its own prompt cuts with, GET /api/doc/{name}
returns that number, and an edited CODING.md takes the new section once."""
import json, tempfile, unittest
from pathlib import Path
from unittest import mock
from fastapi.testclient import TestClient

import taskuary
from taskuary import brief, doclimits, general, server, store as store_mod, terminal, triage
from taskuary.store import MemoryStore, SQLiteStore

T = Path(taskuary.__file__).parent / 'templates'
CODING = (T / 'coding.md').read_text(encoding='utf-8')


def _coding_task(s):
    tid = s.create_task({'Title': 'Fix the ledger export', 'Kind': 'coding', 'Status': 'open'}, 'o')
    s.set_task_checklist(tid, ['Fix the CSV header', 'Add a test for the totals row'], 'o')
    return tid


class SubagentRuleTests(unittest.TestCase):
    def test_coding_md_carries_the_rule_cli_neutral_and_short(self):
        raw = CODING.split('## Several to-dos at once', 1)[1].split('##', 1)[0]
        sec = ' '.join(raw.split())
        for s in ('do not depend on each other', 'its own subagent in parallel', "Claude Code's Agent tool", 'Codex or Gemini CLI subagents',
                  'the to-do, its id and what done means', 'tick it once it checks out', 'run the tests once at the end',
                  'depend on each other stay in order'):
            self.assertIn(s, sec, s)
        self.assertEqual(store_mod._FANOUT_NOW.strip(), ('## Several to-dos at once' + raw).strip())
        self.assertLess(len(sec), 500)   # the migration says what the template says

    def test_it_reaches_the_coding_seed_whole(self):
        s = MemoryStore(); s.upsert_agent('coding', 'coding', 'cli', json.dumps({'cmd': 'claude'}))
        seed = terminal.seed_text(s, _coding_task(s), cli='claude')
        self.assertIn('hand each to its own subagent in parallel', seed)
        self.assertIn(terminal.flatten_rules(s.doc('coding'))[-120:], seed)                # the end of CODING.md: nothing was cut
        self.assertNotIn('rules truncated here', seed)


class BudgetTests(unittest.TestCase):
    def test_every_shipped_document_fits_under_what_its_reader_takes(self):
        s = MemoryStore()
        for name in ('soul', 'job', 'style', 'counsel', 'agent', 'coding', 'researcher', 'analyst', 'assistant', 'ap'):
            lim = doclimits.limit(s, name) or doclimits.limit(s, 'coding')               # a shipped role is a profile document
            text = (T / f'{name}.md').read_text(encoding='utf-8')
            n = len(terminal.flatten_rules(text) if lim['flat'] else text)
            self.assertLess(n, lim['chars'] * .9, f'{name}: {n} of {lim["chars"]} - leave room for an edit')

    def test_one_number_per_document_and_the_prompts_cut_with_it(self):
        s = MemoryStore()
        self.assertEqual(doclimits.limit(s, 'coding')['chars'], terminal.DOC_CHARS)
        self.assertEqual(doclimits.limit(s, 'agent')['chars'], terminal.AGENT_CHARS)
        self.assertEqual(doclimits.limit(s, 'soul')['chars'], triage.SOUL_CHARS)
        self.assertIsNone(doclimits.limit(s, 'triage'))                                   # triage's whole system prompt: nothing cuts it
        self.assertEqual(doclimits.limit(s, 'counsel')['past'], doclimits.WHOLE)          # warned, never sliced (PW-258)
        self.assertEqual(doclimits.limit(s, 'coding')['past'], doclimits.CUT)
        self.assertGreater(terminal.DOC_CHARS, 6400)

    def test_a_general_worker_gets_agent_md_and_its_profile_whole(self):
        s = MemoryStore()
        s.save_doc('researcher', '# Researcher\n' + 'Read the sources first. ' * 250 + 'LAST LINE OF THE PROFILE.', 'owner')
        tid = s.create_task({'Title': 'Compare two vendors', 'Kind': 'general', 'Status': 'open', 'Assignee': 'agent:researcher'}, 'o')
        with mock.patch.object(general, 'assigned_role', return_value='researcher'):
            system = general._prompt(s, tid)[0]
        self.assertIn('LAST LINE OF THE PROFILE.', system)                                 # ~6,000 characters: cut at 4,000 before
        self.assertIn(brief.rules(s, 'agent', 10**9)[-80:], system)                        # AGENT.md's own end

    def test_the_seed_ceiling_leaves_room_on_a_windows_command_line(self):
        # CreateProcessW takes 32,767 UTF-16 units, NUL included; the exe, the flags and list2cmdline's escapes share it with the seed
        self.assertLessEqual(terminal.SEED_CEILING + 4000, 32767)
        self.assertLess(terminal.DOC_CHARS + terminal.AGENT_CHARS + terminal.BRIEF_CONTEXT, terminal.SEED_CEILING)


class ApiTests(unittest.TestCase):
    def test_the_docs_endpoint_returns_each_documents_limit(self):
        s = MemoryStore()
        with mock.patch.object(server, 'store', s):
            c = TestClient(server.app)
            got = {n: c.get(f'/api/doc/{n}').json()['limit'] for n in ('coding', 'agent', 'soul', 'job', 'style', 'learned', 'triage')}
        self.assertEqual(got['coding'], {'chars': terminal.DOC_CHARS, 'flat': True, 'reader': 'the agent', 'past': doclimits.CUT})
        self.assertEqual(got['agent']['chars'], terminal.AGENT_CHARS)
        self.assertEqual(got['soul']['chars'], triage.SOUL_CHARS); self.assertFalse(got['soul']['flat'])
        self.assertEqual(got['learned']['past'], doclimits.SECTIONS)
        self.assertIsNone(got['triage'])


class EditedCopyTests(unittest.TestCase):
    def setUp(self): self.path = Path(tempfile.mkdtemp()) / 'taskuary.db'

    def _reopen(self, body):
        s = SQLiteStore(str(self.path)); s.save_doc('coding', body, 'owner')
        s.cx.execute("DELETE FROM setting WHERE Name='coding_fans_out_todos'"); s.cx.commit()
        return SQLiteStore(str(self.path))

    def test_an_edited_copy_takes_the_section_once_lf_or_crlf(self):
        for nl in ('\n', '\r\n'):
            old = CODING.replace(store_mod._FANOUT_NOW, '').replace('## You may do alone', '## You may do alone\n- Our own line.').replace('\n', nl)
            self.assertNotIn('Several to-dos', old)
            got = self._reopen(old).get_doc('coding')
            self.assertEqual(got.count('## Several to-dos at once'), 1); self.assertIn('- Our own line.', got)
            if nl == '\r\n': self.assertNotIn('\n', got.replace('\r\n', ''))
            self.assertEqual(SQLiteStore(str(self.path)).get_doc('coding'), got)            # once: a second start adds nothing

    def test_a_copy_without_the_anchor_is_left_alone(self):
        self.assertNotIn('Several to-dos', self._reopen('# CODING.md\nOur own rules only.\n').get_doc('coding'))


if __name__ == '__main__':
    unittest.main()
