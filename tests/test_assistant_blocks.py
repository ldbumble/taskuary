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

    def test_resolving_a_report_that_chose_nothing_reads_what_it_always_read(self):
        """Every Assistant run now goes through resolve (reports.run_assistant and the dispatch), so
        the gate has to hold through it too - not only through the blocks=None path nobody takes."""
        s = A.store()
        cands = assistant.candidates(s, assistant.cfg(s))
        self.assertEqual(assistant.inputs(s, cands), assistant.inputs(s, cands, blocks=B.resolve(s, {'type': 'assistant'})))

    def test_every_default_on_block_appears_in_the_payload(self):
        s = A.store()
        text = assistant.inputs(s, [])
        for b in B.CATALOGUE:
            if not B.defaults(s, b)['on']: continue
            if not b.heading: continue                      # a producer renders under CANDIDATES, not its own head
            if not B.render(s, b, B.defaults(s, b))[0].strip(): continue   # a block with nothing to say has never printed an empty head
            head = b.heading.split('(')[0].split('{')[0].strip().rstrip(':')
            with self.subTest(block=b.id): self.assertIn(head, text, f'{b.id} is on by default and is not in the payload')


class ResolveTests(unittest.TestCase):
    """Three places hold a number - the declaration, the global setting, the report - and this is the
    order they win in. A fourth rule sits on top: what a report SAVED is the whole truth."""
    def test_no_config_is_the_declared_defaults(self):
        s = A.store()
        self.assertEqual(B.resolve(s, {'type': 'assistant'}),
                         {b.id: B.defaults(s, b) | ({'source_ids': None, 'inline': None} if b.id == 'system_checks' else {})
                          for b in B.CATALOGUE})

    def test_a_report_override_beats_the_setting_which_beats_the_declaration(self):
        s = A.store()
        self.assertEqual(B.resolve(s, {'type': 'assistant'})['gone_quiet']['days'], 3)
        s.set_setting('assistant_cold_days', '9', 'test')
        self.assertEqual(B.resolve(s, {'type': 'assistant'})['gone_quiet']['days'], 9)
        self.assertEqual(B.resolve(s, {'type': 'assistant', 'blocks': {'gone_quiet': {'days': 21}}})['gone_quiet']['days'], 21)

    def test_every_catalogue_id_is_in_the_answer(self):
        """Ruling J: a block missing from a saved choice resolves OFF, so a caller must never have to
        tell "the owner said no" from "this key was written before the block existed". resolve is the
        only supported producer of that dict, and it emits all sixteen whatever it was handed."""
        s, ids = A.store(), {b.id for b in B.CATALOGUE}
        for cfg in ({}, {'type': 'assistant'}, {'type': 'assistant', 'blocks': {}},
                    {'type': 'assistant', 'watch_source_ids': [4]},
                    {'type': 'assistant', 'blocks': {b.id: {'on': True} for b in B.CATALOGUE}},
                    {'type': 'assistant', 'blocks': {'nonesuch': {'on': True}}}):
            with self.subTest(cfg=cfg): self.assertEqual(set(B.resolve(s, cfg)), ids)

    def test_a_block_the_saved_choice_does_not_name_is_off(self):
        chosen = B.resolve(A.store(), {'type': 'assistant', 'blocks': {'open_work': {'on': True}}})
        self.assertTrue(chosen['open_work']['on'])
        self.assertFalse(chosen['threads']['on'])                 # shipped later ≠ switched on later

    def test_a_stored_key_the_block_never_declared_is_ignored(self):
        chosen = B.resolve(A.store(), {'type': 'assistant', 'blocks': {'open_work': {'on': True, 'cap': 3, 'source_ids': [9], 'days': 'x'}}})
        self.assertEqual(chosen['open_work']['cap'], 3)
        self.assertNotIn('source_ids', chosen['open_work'])
        self.assertNotIn('days', chosen['open_work'])

    def test_watch_sources_with_no_blocks_key_reads_no_taskuary_block(self):
        """Today an Assistant report with a source of its own is systems-only. A report saved before
        blocks existed must not silently start reading the owner's whole inbox."""
        chosen = B.resolve(A.store(), {'type': 'assistant', 'watch_source_ids': [4]})
        self.assertFalse(any(o['on'] for bid, o in chosen.items() if bid != 'system_checks'))
        self.assertFalse(B.reads_taskuary(chosen))

    def test_ticking_one_block_makes_it_no_longer_systems_only(self):
        chosen = B.resolve(A.store(), {'type': 'assistant', 'watch_source_ids': [4], 'blocks': {'open_work': {'on': True}}})
        self.assertTrue(chosen['open_work']['on'])
        self.assertTrue(B.reads_taskuary(chosen))
        self.assertEqual(chosen['system_checks']['source_ids'], [4])      # and its sources ride along

    def test_producers_follow_the_report_and_not_the_global_setting(self):
        s = A.store()
        chosen = B.resolve(s, {'type': 'assistant', 'blocks': {'gone_quiet': {'on': True, 'days': 11}}})
        c = B.producer_cfg(chosen, assistant.cfg(s))
        self.assertEqual(c['producers'], {'cold', 'idea'})      # `idea` is not a block: it is whether the model thinks at all
        self.assertEqual(c['cold_d'], 11)


class WeighTests(unittest.TestCase):
    def test_weigh_prices_each_block(self):
        s = A.store()
        rows = B.weigh(s, B.resolve(s, {'type': 'assistant'}))
        self.assertEqual({r['id'] for r in rows}, {b.id for b in B.CATALOGUE})
        one = next(r for r in rows if r['id'] == 'gone_quiet')
        self.assertEqual(one['tables'], ['task', 'comment', 'message', 'run'])
        self.assertIsInstance(one['tokens'], int)
        self.assertTrue(next(r for r in rows if r['id'] == 'ooo')['sql'])      # a query block shows its statement
        self.assertIsNone(next(r for r in rows if r['id'] == 'threads')['sql'])   # a view shows none

    def test_a_block_switched_off_costs_nothing(self):
        s = A.store()
        rows = {r['id']: r for r in B.weigh(s, B.resolve(s, {'type': 'assistant', 'blocks': {'open_work': {'on': True}}}))}
        self.assertEqual((rows['threads']['on'], rows['threads']['tokens'], rows['threads']['rows']), (False, 0, 0))
        self.assertGreater(rows['open_work']['tokens'], 0)

    def test_weighing_never_reaches_the_calendar(self):
        """Ruling H. Pricing the calendar means a Graph token POST plus a calendarView per mailbox at
        20s each, and this list is what a settings card re-reads on every keystroke. So a live block
        is declared, not run: rows unknown, tokens nil, and the card says the cost is time."""
        from unittest import mock
        s = A.store(); s.set_setting('calendar_enabled', '1', 't')
        assistant._AGENDA.clear()
        with mock.patch('taskuary.assistant._read_agenda', side_effect=AssertionError('weigh fetched the calendar')):
            rows = {r['id']: r for r in B.weigh(s, B.resolve(s, {'type': 'assistant'}))}
        assistant._AGENDA.clear()
        for bid in ('calendar', 'meeting_prep', 'system_checks'):
            with self.subTest(block=bid):
                self.assertTrue(rows[bid]['live'], f'{bid} reaches a live connection and must say so')
                if rows[bid]['on']: self.assertIsNone(rows[bid]['rows']); self.assertEqual(rows[bid]['tokens'], 0)


class DoneThisWeekHeadTests(unittest.TestCase):
    """Ruling L: "DONE THIS WEEK" names its window in words. At the default that is the head the
    payload has always carried; widened, it would be a wrong statement about the lines under it."""
    def test_the_default_head_is_unchanged(self):
        b = B.by_id('done_this_week')
        self.assertEqual(B.headline(b, {'days': 7}), "DONE THIS WEEK (my own work, with the agent's summary)")

    def test_a_widened_window_is_named(self):
        b = B.by_id('done_this_week')
        self.assertEqual(B.headline(b, {'days': 30}), "DONE IN THE LAST 30 DAYS (my own work, with the agent's summary)")
        self.assertIn('TWO DAYS', B.headline(b, {'days': 2}))

    def test_no_other_heading_names_its_window_in_words(self):
        for b in B.CATALOGUE:
            if not (b.heading and b.window) or b.wide: continue
            with self.subTest(block=b.id):
                self.assertIn('{', b.heading, f'{b.id} has a window and no token in its head - declare a `wide` form')


class CardMatchesPayloadTests(unittest.TestCase):
    def test_the_card_names_the_blocks_the_payload_contains(self):
        """One resolution behind the card and the payload, or the card claims a read the run never
        made - the exact class of bug this feature exists to end. A block with nothing to say has
        never printed an empty head, so it is checked in the direction that can lie."""
        s = A.store()
        cfg = {'type': 'assistant', 'blocks': {'open_work': {'on': True}, 'gone_quiet': {'on': True, 'days': 14}}}
        chosen = B.resolve(s, cfg)
        payload = assistant.inputs(s, [], blocks=chosen)
        for row in B.weigh(s, chosen):
            b = B.by_id(row['id'])
            if not b.heading: continue                    # a producer renders under CANDIDATES, which weigh does not own
            head = b.heading.split('(')[0].split('{')[0].strip().rstrip(':')
            with self.subTest(block=row['id']):
                if not row['on']: self.assertNotIn(head, payload, f"the card says {row['id']} is off and the payload has it")
                elif row['tokens']: self.assertIn(head, payload, f"the card says {row['id']} is on and the payload has not got it")


class EndpointTests(unittest.TestCase):
    def test_the_route_prices_the_declared_defaults(self):
        from fastapi.testclient import TestClient
        from taskuary import server
        r = TestClient(server.app).get('/api/assistant/blocks')
        self.assertEqual(r.status_code, 200)
        d = r.json()
        self.assertEqual({x['id'] for x in d['data']}, {b.id for b in B.CATALOGUE})
        self.assertEqual(d['cost'], None)                          # the money line is Task 3's
        self.assertIsInstance(d['runs_per_day'], int)
        self.assertEqual(d['total_tokens'], sum(x['tokens'] for x in d['data'] if x['on']))


if __name__ == '__main__':
    unittest.main()
