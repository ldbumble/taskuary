"""Every context block the Assistant reads is a declaration, and the defaults are what it read
before there were declarations (the assistant-reads-Taskuary design, 2026-09-19)."""
import unittest
from taskuary import assistantblocks as B
import tests.test_appfacts as A


class CatalogueTests(unittest.TestCase):
    def test_every_block_says_what_it_reads(self):
        self.assertGreaterEqual(len(B.CATALOGUE), 16)
        seen = set()
        for b in B.CATALOGUE:
            self.assertNotIn(b.id, seen, f'{b.id} declared twice'); seen.add(b.id)
            self.assertTrue(b.label, f'{b.id} has no label')
            self.assertEqual(bool(b.heading), not b.proposes, f'{b.id}: a context block needs a heading, a producer must not have one')
            self.assertIn(b.kind, ('query', 'view'), f'{b.id} is neither a query nor a view')
            self.assertTrue(b.tables, f'{b.id} names no table')
            self.assertTrue(callable(b.build), f'{b.id} has no builder')
            if b.kind == 'query': self.assertTrue(b.sql, f'{b.id} is a query with no SQL to show')

    def test_a_query_blocks_sql_runs(self):
        """b.build, NOT B.render: render swallows the exception and hands back a sentence, so a
        test that went through it would pass with every builder broken."""
        s = A.store()
        for b in B.CATALOGUE:
            if b.kind != 'query' or not b.sql: continue
            with self.subTest(block=b.id):
                text, mids = b.build(s, B.defaults(s, b))
                self.assertIsInstance(text, str); self.assertIsInstance(mids, list)

    def test_a_query_blocks_sql_is_the_statement_the_store_runs(self):
        """What `kind='query'` promises: the card prints the statement the database receives. So
        listen to the store while the block builds and find the declaration in what it was asked -
        a SELECT nobody runs is the same lie as a window that binds nothing."""
        s, asked = A.store(), []
        rows = s._rows
        s._rows = lambda q, p=(): (asked.append(' '.join(str(q).split())), rows(q, p))[1]
        for b in B.CATALOGUE:
            if b.kind != 'query': continue
            with self.subTest(block=b.id):
                o = B.defaults(s, b); asked.clear(); b.build(s, o)
                self.assertIn(' '.join(b.sql.split()), asked, f'{b.id} declares SQL its builder never runs')

    def test_by_id_finds_and_misses(self):
        self.assertEqual(B.by_id('gone_quiet').label, 'Work gone quiet')
        self.assertIsNone(B.by_id('nope'))


from taskuary import assistant


class WhatIsDeclaredBindsTests(unittest.TestCase):
    """A window or a cap the owner can see and the payload ignores is the lie this registry exists
    to end. Each declared number is pulled here, and the text has to move with it - in the body as
    well as in the head, because the empty-state lines said "two days" in their own words."""
    def test_the_caps_cut_the_rows(self):
        s = A.store()
        for n in range(3):
            s.create_task({'Title': f'Task {n}', 'Kind': 'coding', 'Status': 'open'}, 'owner')
            s.upsert_idea({'key': f'idea:{n}', 'kind': 'idea', 'text': f'Thought {n}.', 'action': {}}, '2026-09-19 08:00:00')
        self.assertEqual(len(B.render(s, B.by_id('open_work'), {'on': True, 'cap': 2})[0].split('\n')), 2)
        self.assertEqual(len(B.render(s, B.by_id('already_said'), {'on': True, 'cap': 1})[0].split('\n')), 1)

    def test_a_window_reaches_the_body_and_not_only_the_head(self):
        s = A.store(); s.set_setting('calendar_enabled', '0', 't')
        self.assertIn('the last 30 days', assistant._recent(s, days=30))
        self.assertIn('for 30 days', assistant._calendar(s, days=30))
        self.assertIn('the last two days', assistant._recent(s, days=2))          # today's words, unchanged
        self.assertIn('for two days', assistant._calendar(s, days=2))

    def test_the_calendar_window_reaches_the_calendar(self):
        from unittest import mock
        s = A.store(); s.set_setting('calendar_enabled', '1', 't')
        assistant._AGENDA.clear()
        with mock.patch('taskuary.calendar.agenda', lambda store, days=2, start=None: {'events': []}) as _:
            with mock.patch('taskuary.assistant._read_agenda', wraps=assistant._read_agenda) as read:
                B.render(s, B.by_id('calendar'), {'on': True, 'days': 30})
                self.assertEqual(read.call_args[0][1], 30, 'the declared window never reached the Graph call')
        assistant._AGENDA.clear()


class DefaultsAreTodayTests(unittest.TestCase):
    """The one test that must never be relaxed: an Assistant report that has configured nothing
    reads exactly what it read before blocks existed."""
    def test_the_default_payload_is_unchanged(self):
        s = A.store()
        cands = assistant.candidates(s, assistant.cfg(s))
        self.assertEqual(assistant.inputs(s, cands), assistant.inputs(s, cands, blocks=None))

    def test_every_default_on_block_appears_in_the_payload(self):
        s = A.store()
        text = assistant.inputs(s, [])
        for b in B.CATALOGUE:
            if not B.defaults(s, b)['on']: continue
            if not b.heading: continue                      # a producer renders under CANDIDATES, not its own head
            if not B.render(s, b, B.defaults(s, b))[0].strip(): continue   # a block with nothing to say has never printed an empty head
            head = b.heading.split('(')[0].split('{')[0].strip().rstrip(':')
            with self.subTest(block=b.id): self.assertIn(head, text, f'{b.id} is on by default and is not in the payload')


if __name__ == '__main__':
    unittest.main()
