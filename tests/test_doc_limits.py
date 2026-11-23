"""How much of each document reaches the model that reads it, said in the Docs editor (the owner, 2026-11-02: "tell the user the max
amount of characters that go into the instructions, with a bar/percentage showing if you are over").

Every shipped document fits under the number its own reader cuts with, and GET /api/doc/{name} returns that number."""
import unittest
from pathlib import Path
from unittest import mock
from fastapi.testclient import TestClient

import taskuary
from taskuary import doclimits, server, terminal, triage
from taskuary.store import MemoryStore

T = Path(taskuary.__file__).parent / 'templates'


class BudgetTests(unittest.TestCase):
    def test_every_shipped_document_fits_under_what_its_reader_takes(self):
        s = MemoryStore()
        for name in ('soul', 'job', 'style', 'counsel'):
            lim, n = doclimits.limit(s, name), len((T / f'{name}.md').read_text(encoding='utf-8'))
            self.assertLess(n, lim['chars'] * .9, f'{name}: {n} of {lim["chars"]} - leave room for an edit')

    def test_one_number_per_document_and_the_prompts_cut_with_it(self):
        s = MemoryStore()
        self.assertEqual(doclimits.limit(s, 'soul')['chars'], triage.SOUL_CHARS)
        self.assertIsNone(doclimits.limit(s, 'triage'))                                   # triage's whole system prompt: nothing cuts it
        self.assertEqual(doclimits.limit(s, 'counsel')['past'], doclimits.WHOLE)          # warned, never sliced (PW-258)
        for gone in ('agent', 'coding'): self.assertIsNone(doclimits.limit(s, gone))      # no agent reads them (2026-11-23)

    def test_agents_md_is_kept_short_and_the_shipped_text_fits(self):
        """AGENTS.md (the owner, 2026-11-23) is a few general sentences, never a rulebook: the meter caps it where the agents' reader cuts it."""
        from taskuary import selfclose
        s = MemoryStore(); lim = doclimits.limit(s, 'agents')
        self.assertEqual((lim['chars'], lim['flat'], lim['past']), (selfclose.AGENTS_CHARS, True, doclimits.CUT))
        self.assertLessEqual(lim['chars'], 1000)
        self.assertLess(len(selfclose.ONE_SENTENCE), lim['chars'] * .9)

    def test_the_seed_ceiling_leaves_room_on_a_windows_command_line(self):
        # CreateProcessW takes 32,767 UTF-16 units, NUL included; the exe, the flags and list2cmdline's escapes share it with the seed
        self.assertLessEqual(terminal.SEED_CEILING + 4000, 32767)
        self.assertLess(terminal.DOC_CHARS + terminal.BRIEF_CONTEXT, terminal.SEED_CEILING)


class ApiTests(unittest.TestCase):
    def test_the_docs_endpoint_returns_each_documents_limit(self):
        s = MemoryStore()
        with mock.patch.object(server, 'store', s):
            c = TestClient(server.app)
            got = {n: c.get(f'/api/doc/{n}').json()['limit'] for n in ('soul', 'job', 'style', 'learned', 'triage')}
        self.assertEqual(got['soul']['chars'], triage.SOUL_CHARS); self.assertFalse(got['soul']['flat'])
        self.assertEqual(got['learned']['past'], doclimits.SECTIONS)
        self.assertIsNone(got['triage'])


if __name__ == '__main__':
    unittest.main()
