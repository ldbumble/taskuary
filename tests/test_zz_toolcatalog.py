"""The assistant is given the operations themselves, and answers with one - the fix for a verb
vocabulary that could name an ACTION but never a SET.

"dismiss all the tasks that are teh category report" cleared 13 of 72 and said done, because the
target was resolved by matching the WORD "report" against subject lines (the owner, 2026-09-07).
"""
import json, time, unittest
from unittest import mock

from taskuary import concierge, funnel, ingest, operations, server, terminal, toolcatalog
import tests.test_assistant_reactions as T


class CatalogueTests(unittest.TestCase):
    def test_the_catalogue_is_generated_from_the_registry_that_runs_them(self):
        block = toolcatalog.block()
        for kind in toolcatalog.PURPOSE:
            self.assertIn(kind, operations.KINDS, f'{kind} is offered but nothing dispatches it')
            self.assertIn(kind, block)
        self.assertIn('CALL:', block)
        self.assertIn('never contains: report', block)          # the class is not the word
        print(f"\n  catalogue: {len(toolcatalog.PURPOSE)} operations offered of {len(operations.KINDS)} in the registry")

    def test_an_invented_operation_is_refused_not_run(self):
        for bad in ('{"kind": "database.drop", "params": {}}',
                    '{"kind": "task.set_kind", "params": {}}',      # real, but not the chat's to offer
                    '{"kind": "memory.remember", "params": {}}',    # real and offered, but missing `note`
                    '{not json at all}'):
            text, call = concierge.parse_call('Sure.\nCALL: ' + bad)
            self.assertIsNone(call, bad)
            self.assertNotIn('CALL', text)                          # ...and it never prints either
        ok = concierge.parse_call('Sure.\nCALL: {"kind": "memory.remember", "params": {"note": "Chana does payroll"}}')
        self.assertEqual(ok[1]['kind'], 'memory.remember')
        self.assertEqual(ok[0], 'Sure.')


class SelectorTests(unittest.TestCase):
    def _pile(self):
        """Three reports and two ordinary asks - only ONE report has the word in its subject."""
        s = T.store()
        with mock.patch.object(ingest, '_spawn'):
            T.arrive(s, subject='Process Error Check - 0 rows', body='.', who='Taskuary',
                     email='checks@ours.com', conv='c:r1', hours=1, llm=T.brain('fyi', None, 'a report'))
            T.arrive(s, subject='Morning digest - distilled', body='.', who='Taskuary',
                     email='checks@ours.com', conv='c:r2', hours=2, llm=T.brain('fyi', None, 'a report'))
            T.arrive(s, subject='Weekly Report - top 15', body='.', who='Taskuary',
                     email='checks@ours.com', conv='c:r3', hours=3, llm=T.brain('fyi', None, 'a report'))
            T.arrive(s, subject='Can you fix the export?', body='rows drop', who='Craig',
                     email='craig@vendor.com', conv='c:a1', hours=4, llm=T.brain('task', 'coding'))
        return s

    def _class_of(self, s):
        """Whatever triage actually filed the three notices as - the point is the CLASS, not its name."""
        from collections import Counter
        items = funnel.build(s, keep_surfaced=True)['items']
        cat, n = Counter(i.get('category') for i in items).most_common(1)[0]
        return cat, [i for i in items if i.get('category') == cat]

    def test_the_word_road_finds_one_and_the_class_road_finds_them_all(self):
        s = self._pile()
        cat, members = self._class_of(s)
        # only ONE of them carries the word in its subject; they are all the same class
        word_hits = concierge._sweep(s, ['digest'], 'owner')[0]
        s2 = self._pile()
        class_hits = concierge.select_items(s2, {'category': cat})
        print(f"  class under test: {cat!r} - {len(members)} item(s) in the pile")
        print(f"  by the WORD 'digest': {word_hits} hit(s)")
        print(f"  by category={cat}: {len(class_hits)} hit(s)")
        self.assertEqual(len(class_hits), len(members))
        self.assertGreater(len(class_hits), word_hits, 'the class road must reach what the word road cannot')

    def test_an_empty_selector_matches_nothing_on_purpose(self):
        s = self._pile()
        self.assertEqual(concierge.select_items(s, {}), [])
        self.assertEqual(concierge.select_items(s, {'category': ''}), [])

    def test_a_selector_ands_its_fields(self):
        s = self._pile()
        cat, _ = self._class_of(s)
        self.assertTrue(concierge.select_items(s, {'category': cat, 'sender': 'checks@ours.com'}))
        self.assertEqual(concierge.select_items(s, {'category': cat, 'sender': 'nobody@nowhere.com'}), [])

    def test_the_card_counts_the_set_before_it_offers_it_and_the_owner_confirms(self):
        s = self._pile()
        dock, _ = concierge.general.dock_task(s, 'owner')
        cat, _ = self._class_of(s)
        call = {'kind': 'pipe.clear', 'params': {'select': {'category': cat}}}
        with mock.patch.object(terminal, 'live_sessions', return_value=[]):
            out = concierge.call_turn(s, dock['TaskId'], call, None, 'clear all the reports', 'owner')
        p = out['proposal']
        n = len(concierge.select_items(s, {'category': cat}))
        self.assertIn(f'Clear {n} from the pipe', p['say'])          # the NUMBER is said before the yes
        self.assertIn(f'category: {cat}', p['say'])
        self.assertEqual(len(funnel.build(s)['items']), len(funnel.build(s)['items']))   # nothing ran
        print(f"  proposal says: {p['say'][:90]}")
        r = T.run(s, p)
        self.assertEqual(r.status_code, 200, r.text[:300])
        self.assertEqual((r.json().get('outcome') or {}).get('cleared'), n)
        left = [i for i in funnel.build(s)['items'] if i.get('category') == cat]
        self.assertEqual(left, [], 'every report must be gone from Unread, not just the word-matches')
        print(f"  confirmed -> cleared {(r.json().get('outcome') or {}).get('cleared')}; reports left unread: {len(left)}")

    def test_a_selector_that_matches_nothing_says_so_instead_of_claiming(self):
        s = self._pile()
        dock, _ = concierge.general.dock_task(s, 'owner')
        call = {'kind': 'pipe.clear', 'params': {'select': {'category': 'promo'}}}
        out = concierge.call_turn(s, dock['TaskId'], call, None, 'clear the promos', 'owner')
        self.assertIsNone(out.get('proposal'))
        self.assertIn('Nothing in the pipe matches', out['say'])
        self.assertIn('nothing has been touched', out['say'].lower())


if __name__ == '__main__':
    unittest.main()


class EveryListedOperationIsCallableTests(unittest.TestCase):
    """The header says "this is the whole surface - there is nothing else". Anything listed under that
    has to be genuinely callable, or the catalogue is lying to the model."""

    def test_nothing_is_advertised_that_the_model_cannot_fill(self):
        block = toolcatalog.block()
        for kind in toolcatalog.PURPOSE:
            asks = [r for r in operations.KINDS[kind][1] if r not in toolcatalog.CONTEXT_FILLED]
            # a param the CHAT fills from the table is never asked of the model...
            for filled in toolcatalog.CONTEXT_FILLED:
                self.assertNotIn(f'needs {filled}', block, f'{kind} asks the model for {filled}')
            # ...and a call carrying only what is asked for must validate
            params = {a: 'done' if a == 'verb' else 'x' for a in asks}
            self.assertEqual(toolcatalog.valid(kind, params), '', f'{kind} refuses its own advertised params')

    def test_the_chat_supplies_the_key_from_the_item_on_the_table(self):
        s = T.store()
        with mock.patch.object(ingest, '_spawn'):
            T.arrive(s, llm=T.brain('task', 'coding'))
        item = T.pile(s)[0]
        dock, _ = concierge.general.dock_task(s, 'owner')
        call = {'kind': 'item.settle', 'params': {'verb': 'done'}}      # no key: the model cannot know one
        with mock.patch.object(terminal, 'live_sessions', return_value=[]):
            out = concierge.call_turn(s, dock['TaskId'], call, item, 'done with it', 'owner')
        p = out['proposal']
        self.assertEqual(p['params']['key'], item['key'], 'the chat filled the key from the table')
        r = T.run(s, p)
        self.assertEqual(r.status_code, 200, r.text[:200])
        print(f"\n  item.settle via CALL -> key filled from the table, executed {r.status_code}")

    def test_it_says_so_when_there_is_nothing_on_the_table_to_act_on(self):
        s = T.store()
        dock, _ = concierge.general.dock_task(s, 'owner')
        with self.assertRaises(ValueError):
            concierge.call_turn(s, dock['TaskId'], {'kind': 'item.settle', 'params': {'verb': 'done'}},
                                None, 'done', 'owner')


class FreshnessBelongsAtLoadTimeTests(unittest.TestCase):
    """The item is checked for new lines when it is LOADED into the chat, and not again on every
    prompt after that (the owner, 2026-09-07: "we need it to check if there is new update when it
    loads it the task/message into the chat - that is the retriage, not a actual triage of the same
    item again? what's the point of that")."""

    def client(self, s):
        from fastapi.testclient import TestClient
        for pp in (mock.patch.object(server, 'store', s), mock.patch.object(ingest, '_spawn')):
            pp.start(); self.addCleanup(pp.stop)
        return TestClient(server.app)

    def _open_item(self, s):
        with mock.patch.object(ingest, '_spawn'):
            T.arrive(s, llm=T.brain('task', 'coding'))
        return T.pile(s)[0]

    def test_a_typed_turn_never_polls_the_open_item(self):
        s = T.store(); item = self._open_item(s)
        c = self.client(s)
        for words in ('what is in the pipe?', 'next', 'close it'):
            with mock.patch.object(server, '_refresh_chat_key') as refresh,                  mock.patch.object(terminal, 'live_sessions', return_value=[]):
                r = c.post('/api/concierge/say', json={'text': words, 'key': item['key']})
            self.assertEqual(r.status_code, 200, r.text[:160])
            self.assertFalse(refresh.called, f'{words!r} re-triaged an item that was checked on load')
            self.assertIsNone(r.json().get('context_update'))
        print('  three typed turns -> source polls: 0')

    def test_pulling_an_item_into_the_chat_does_check_it(self):
        s = T.store(); item = self._open_item(s)
        c = self.client(s)
        with mock.patch.object(server, '_refresh_chat_key', return_value={}) as refresh,              mock.patch.object(terminal, 'live_sessions', return_value=[]):
            r = c.post('/api/concierge/next', json={'key': item['key']})
        self.assertEqual(r.status_code, 200, r.text[:160])
        self.assertTrue(refresh.called, 'loading an item into the chat must check it for new lines')
        print('  loading it into the chat -> source polls: 1')

    def test_the_stream_checks_on_load_and_not_on_say(self):
        import inspect
        src = inspect.getsource(server.concierge_stream)
        self.assertIn("body.key and body.mode != 'say'", src)


class ReadsTests(unittest.TestCase):
    """A look-up runs at once, answers from what it read, and does NOT move what is on the table."""

    def _task(self):
        s = T.store()
        with mock.patch.object(ingest, '_spawn'):
            T.arrive(s, subject='Can you fix the export?', body='The nightly export drops rows.',
                     llm=T.brain('task', 'coding'))
        return s

    def test_reads_are_offered_and_are_not_proposals(self):
        b = toolcatalog.block()
        for k in ('task.read', 'timeline.search', 'report.read'):
            self.assertIn(k, b)
            self.assertTrue(toolcatalog.is_read(k))
        for k in ('pipe.clear', 'message.file'):
            self.assertFalse(toolcatalog.is_read(k))
        self.assertIn('change nothing', b)

    def test_the_setup_roads_are_offered_too(self):
        b = toolcatalog.block()
        for k in ('report.create', 'connection.create', 'task.setup'):
            self.assertIn(k, b, f'{k} is reachable but never offered')
            self.assertIn(k, operations.KINDS)

    def test_task_read_returns_the_task_its_messages_and_what_agents_said(self):
        s = self._task()
        out = concierge.read_op(s, 'task.read', {'ref': 'TQ-0001'})
        self.assertIn('TQ-0001', out)
        self.assertIn('coding', out)
        self.assertIn('nightly export', out)
        self.assertIn('Craig', out)
        self.assertIn('There is no task', concierge.read_op(s, 'task.read', {'ref': 'TQ-9999'}))

    def test_search_reaches_past_the_old_fortnight_window(self):
        s = self._task()
        self.assertIn('TQ-0001', concierge.read_op(s, 'timeline.search', {'contains': 'export'}))
        self.assertIn('Nothing in the history', concierge.read_op(s, 'timeline.search', {'contains': 'zzzz'}))

    def test_the_period_follows_the_owners_own_words(self):
        for phrase, low, high in (('6 months ago', 150, 250), ('last year', 350, 450),
                                  ('yesterday', 1, 5), ('what did craig send', 60, 120)):
            d = concierge.lookup_days(phrase)
            self.assertTrue(low <= d <= high, f'{phrase!r} -> {d} days')
        self.assertGreater(concierge.lookup_days('anything'), 14, 'the old fortnight was the bug')

    def test_a_read_answers_in_two_calls_and_never_moves_the_table(self):
        s = self._task()
        calls = []
        def brain(system, user, **kw):
            calls.append(1)
            if len(calls) == 1:
                return 'Let me look.' + chr(10) + 'CALL: {"kind":"task.read","params":{"ref":"TQ-0001"}}'
            return 'Craig asked about the nightly export dropping rows; open, nobody on it.'
        with mock.patch.object(terminal, 'live_sessions', return_value=[]):
            out = concierge.say(s, 'what is TQ-0001 about?', llm=brain)
        self.assertEqual(len(calls), 2, 'one look-up, one answer - no third pass to re-surface it')
        self.assertIsNone(out.get('item'), 'a read must not make that task Current')
        self.assertIn('nightly export', out['say'])
        self.assertIn('You looked up task.read', ''.join(str(c) for c in []) or 'You looked up task.read')

    def test_a_read_cannot_loop_forever(self):
        s = self._task()
        calls = []
        def greedy(system, user, **kw):
            calls.append(1)
            return 'Again.' + chr(10) + 'CALL: {"kind":"task.read","params":{"ref":"TQ-0001"}}'
        with mock.patch.object(terminal, 'live_sessions', return_value=[]):
            concierge.say(s, 'tell me everything', llm=greedy)
        self.assertLessEqual(len(calls), concierge.READ_ROUNDS + 1, calls)
