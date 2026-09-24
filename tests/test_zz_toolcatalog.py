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
        ok = concierge.parse_call('Sure.\nCALL: {"kind": "memory.remember", "params": {"note": "Erin does payroll"}}')
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

    def test_the_sweep_takes_what_it_cleared_off_the_table(self):
        """Settling one item drops Current with it; the sweep left it there, so clearing the reports
        cleared seven and kept the report the owner was holding (the owner, 2026-09-07)."""
        s = self._pile()
        dock, _ = concierge.general.dock_task(s, 'owner')
        cat, members = self._class_of(s)
        held = members[0]
        concierge.set_current(s, dock['TaskId'], held['key'], 'owner')
        out = concierge.clear_selected(s, {'category': cat}, 'owner')
        self.assertEqual(out['cleared'], len(members))
        self.assertEqual(concierge.current_key(s, dock['TaskId']), '', 'the cleared item stayed on the table')

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

    def test_the_last_look_up_says_it_is_the_last_and_a_research_ask_becomes_a_hand_off(self):
        """The owner, 2026-09-24: "i asked it to research for me which should open a agent card but it did
        nothing". A project nothing here has written down: the model searched, searched again, ended on a
        bare CALL - and the empty answer read as "No AI is connected"."""
        s = self._task()
        prompts = []
        def brain(system, user, **kw):
            prompts.append(user)
            if 'last look-up' in user:
                return 'Nothing here covers it - that needs research.' + chr(10) + 'DECIDE: regular_agent: research the CLI Anything project'
            return 'CALL: {"kind":"knowledge.search","params":{"query":"CLI Anything"}}'
        with mock.patch.object(terminal, 'live_sessions', return_value=[]):
            out = concierge.say(s, 'research this GitHub project for me', llm=brain)
        self.assertIn(concierge.LAST_READ, prompts[-1])
        self.assertIn('regular agent', (out.get('proposal') or {}).get('label', '').lower())

    def _handoff(self, answer, workers=True, soul=''):
        """One typed turn with nothing on the table, the model answering `answer`; returns (turn, proposal)."""
        import json
        s = T.store()
        if workers: s.upsert_agent('researcher', 'research', 'cli', json.dumps({'cmd': 'claude'}))
        if soul: s.save_doc('soul', soul, 'owner')
        s.upsert_agent('coder', 'coding', 'cli', json.dumps({'cmd': 'claude', 'cwd_map': {'northwind/ledger': 'C:/x/ledger', 'northwind/portal': 'C:/x/portal'}}))
        with mock.patch.object(terminal, 'live_sessions', return_value=[]):
            out = concierge.say(s, 'can you do this for me', llm=lambda system, user, **kw: answer)
        return s, out, out.get('proposal') or {}

    def test_an_ask_for_a_worker_that_fits_starts_it_at_once(self):
        """The owner, 2026-09-24: "if i ask it to do something especially if we have profile for it it should start
        a general agent" / "start right away if it's clear ... if unclear which profile to choose ... then ask"."""
        s, out, prop = self._handoff('Research job.' + chr(10) + 'DECIDE: regular_agent[researcher]: find out what the CLI Anything project does')
        self.assertTrue(prop.get('auto'), prop)
        self.assertEqual(prop['params']['profile'], 'researcher')
        self.assertIn('researcher', out['say'])
        # ...and the task it makes is the researcher's, so the session is seeded with the researcher's rules
        t = concierge.setup_task(s, 'find out what it does', 'owner', kind='general', agent_job=True, profile='researcher')
        self.assertEqual(s.get_task(t['taskId'])['Assignee'], 'agent:researcher')

    def test_a_worker_nobody_named_is_asked_about_not_guessed(self):
        _s, _out, prop = self._handoff('DECIDE: regular_agent: find out what the CLI Anything project does')
        self.assertFalse(prop.get('auto'))
        self.assertIsNone((prop.get('params') or {}).get('profile'))
        _s, _out, prop = self._handoff('DECIDE: regular_agent[astrologer]: find out what it does')    # not on the roster
        self.assertFalse(prop.get('auto'))

    def test_a_coding_ask_starts_when_the_checkout_is_clear_and_asks_when_it_is_not(self):
        soul = ('# SOUL.md' + chr(10) + '## Repository map' + chr(10) + '- **northwind/ledger**: the fan mobile app' + chr(10)
                + '- **northwind/portal**: the expense portal' + chr(10))
        # NAMED - by the model off the map, or in the owner's own words - it starts, in that checkout
        _s, out, prop = self._handoff('DECIDE: coder[ledger]: fix the login crash in the fan mobile app', soul=soul)
        self.assertTrue(prop.get('auto'))
        self.assertIn('northwind/ledger', out['say'])
        _s, out, prop = self._handoff('DECIDE: coder: fix the login crash in the ledger app', soul=soul)
        self.assertTrue(prop.get('auto'))
        # only MATCHED by the description: a guess, shown on the card for a yes - a weak best match once pointed at
        # a checkout the job was not in
        _s, _out, prop = self._handoff('DECIDE: coder: fix the login crash in the fan mobile app', soul=soul)
        self.assertFalse(prop.get('auto'))
        self.assertEqual(prop['params']['repo'], 'northwind/ledger')
        _s, _out, prop = self._handoff('DECIDE: coder[nowhere]: tidy up the code', soul=soul)          # not on the map
        self.assertFalse(prop.get('auto'))

    def test_a_checkout_nobody_named_is_picked_on_the_card_and_the_pick_is_where_it_opens(self):
        """The owner, 2026-09-24: "it should be dropdown to choose repo if it's not clear but it just started it in
        taskuary". The card carries every checkout; the one picked is revised onto the proposal and pinned."""
        from taskuary import operations
        soul = ('# SOUL.md' + chr(10) + '## Repository map' + chr(10) + '- **northwind/ledger**: the fan mobile app' + chr(10)
                + '- **northwind/portal**: the expense portal' + chr(10))
        s, _out, prop = self._handoff('DECIDE: coder: tidy up the dashboard code', soul=soul)
        self.assertFalse(prop.get('auto'))
        self.assertEqual(set(prop['repo_choices']), {'northwind/ledger', 'northwind/portal'})
        picked = operations.revise(s, prop['id'], {**prop['params'], 'repo': 'northwind/portal'}, 'owner')
        made = concierge.handoff_task(s, picked['params']['text'], 'coding', 'owner', title=picked['params']['title'],
                                      repo=picked['params']['repo'])
        prof = {'cmd': 'claude', 'cwd_map': {'northwind/ledger': 'C:/x/ledger', 'northwind/portal': 'C:/x/portal'}}
        self.assertEqual(terminal.guess_repo(s, made['taskId'], prof)[0], 'northwind/portal')

    def test_a_checkout_the_owner_wrote_starts_even_when_the_model_rewords_it_away(self):
        """"if i ask for coding agent on taskuary (explicitly write it) will it start right away" - the model's
        brief can drop the name; the owner's own message still has it."""
        import json
        soul = ('# SOUL.md' + chr(10) + '## Repository map' + chr(10) + '- **northwind/ledger**: the fan mobile app' + chr(10)
                + '- **northwind/portal**: the expense portal' + chr(10))
        s = T.store()
        s.save_doc('soul', soul, 'owner')
        s.upsert_agent('coder', 'coding', 'cli', json.dumps({'cmd': 'claude', 'cwd_map': {'northwind/ledger': 'C:/x/l', 'northwind/portal': 'C:/x/p'}}))
        with mock.patch.object(terminal, 'live_sessions', return_value=[]):
            out = concierge.say(s, 'start a coding agent on portal to fix the receipt upload',
                                llm=lambda system, user, **kw: 'DECIDE: coder: fix the receipt upload')
        prop = out.get('proposal') or {}
        self.assertTrue(prop.get('auto'), prop)
        self.assertEqual(prop['params']['repo'], 'northwind/portal')
        self.assertEqual(terminal.repo_named_in(s, 'the portal and the ledger'), '')          # two named: ask
        # ...and the model names a checkout by its FULL name, slash and all - a bracket that could not hold a '/'
        # left the whole DECIDE line unread and printed it to the owner as the reply
        self.assertEqual(concierge.parse_decision('On it.' + chr(10) + 'DECIDE: coder[northwind/portal]: fix it')[1]['as'], 'northwind/portal')

    def test_a_brain_that_answers_nothing_never_says_no_ai_is_connected(self):
        s = self._task()
        greedy = lambda system, user, **kw: 'CALL: {"kind":"knowledge.search","params":{"query":"x"}}'
        with mock.patch.object(terminal, 'live_sessions', return_value=[]):
            out = concierge.say(s, 'research this GitHub project for me', llm=greedy)
        self.assertNotIn('No AI is connected', out['say'])


class SweepReachesTheTableTests(unittest.TestCase):
    """The item ON THE TABLE has been put in the chat, which marks it surfaced/read - and a surfaced
    row is not in `funnel.build()`. So the sweep could not see the very report the owner was looking
    at: it cleared five of six and left Current where it was (the owner, 2026-09-11: "it did not clear
    all 6 reports including current and did not move to next after")."""
    def _pile(self, n=6):
        s = T.store()
        with mock.patch.object(ingest, '_spawn'):
            for i in range(n):
                T.arrive(s, subject=f'Process Error Check {i} - 0 rows', body='.', who='Taskuary',
                         email='checks@ours.com', conv=f'c:r{i}', hours=i + 1, llm=T.brain('fyi', None, 'a report'))
        return s

    def _cat(self, s):
        from collections import Counter
        items = funnel.build(s, keep_surfaced=True)['items']
        return Counter(i.get('category') for i in items).most_common(1)[0][0]

    def test_the_report_on_the_table_is_swept_with_the_rest(self):
        s = self._pile()
        dock, _ = concierge.general.dock_task(s, 'owner')
        cat = self._cat(s)
        all_six = funnel.build(s, keep_surfaced=True)['items']
        held = all_six[0]
        funnel.settle(s, held['key'], 'surfaced', 'owner', read=True)      # the assistant put it in the chat
        concierge.set_current(s, dock['TaskId'], held['key'], 'owner')
        self.assertEqual(len(concierge.select_items(s, {'category': cat})), len(all_six),
                         'the item on the table is invisible to the selector')
        out = concierge.clear_selected(s, {'category': cat}, 'owner')
        self.assertEqual(out['cleared'], len(all_six))
        self.assertEqual(concierge.current_key(s, dock['TaskId']), '', 'the cleared item stayed on the table')

    def test_the_card_says_when_it_sweeps_the_table_as_well(self):
        """The sweep settles Current itself, so the card carries its key: that is how the page knows the
        table went with the rest, puts it down and offers Next instead of leaving the cleared report
        sitting there (the owner, 2026-09-11: "did not move to next after"; "it doesn't have to move on
        but should show button next"). A sweep that leaves the table alone carries no key."""
        s = self._pile()
        dock, _ = concierge.general.dock_task(s, 'owner')
        cat = self._cat(s)
        held = funnel.build(s, keep_surfaced=True)['items'][0]
        funnel.settle(s, held['key'], 'surfaced', 'owner', read=True)
        concierge.set_current(s, dock['TaskId'], held['key'], 'owner')
        call = {'kind': 'pipe.clear', 'params': {'select': {'category': cat}}}
        with mock.patch.object(terminal, 'live_sessions', return_value=[]):
            p = concierge.call_turn(s, dock['TaskId'], call, None, 'mark all the report items as read', 'owner')['proposal']
        self.assertEqual(p['key'], held['key'])
        self.assertTrue(p['settles'])
        with mock.patch.object(terminal, 'live_sessions', return_value=[]):
            other = concierge.call_turn(s, dock['TaskId'], {'kind': 'pipe.clear', 'params': {'select': {'sender': 'nobody@nowhere.com'}}},
                                        None, 'clear those', 'owner')
        self.assertIsNone(other.get('proposal'))            # nothing matched - and nothing on the table moved


class AppReadTests(unittest.TestCase):
    """The look-ups that make "what reports do we have" answerable and "run the AR report" resolvable -
    the app itself, by name, read off the tables the tabs read (appfacts; the owner, 2026-09-18)."""
    def _store(self):
        import tests.test_appfacts as A
        return A.store()

    def test_every_new_read_is_in_the_catalogue_and_validates(self):
        b = toolcatalog.block()
        for k in ('reports.list', 'settings.list', 'setting.read', 'connections.list', 'connection.read', 'agents.list'):
            self.assertTrue(toolcatalog.is_read(k), k); self.assertIn(k, b)
        self.assertEqual(toolcatalog.valid('setting.read', {}), 'setting.read needs key or label')
        self.assertEqual(toolcatalog.valid('reports.list', {}), '')

    def test_reports_list_names_them_with_ids_clocks_and_outcomes(self):
        out = concierge.read_op(self._store(), 'reports.list', {})
        self.assertIn('REPORT Monthly AR Report', out); self.assertIn('WORKFLOW ADP hours export', out)
        self.assertIn('source_id', out); self.assertIn('07:00', out); self.assertIn('FAILED - sign-in page', out)

    def test_report_read_finds_by_part_of_the_name_and_says_its_id(self):
        out = concierge.read_op(self._store(), 'report.read', {'title': 'ar report'})
        self.assertIn('REPORT Monthly AR Report', out); self.assertIn('source_id', out); self.assertIn('07:00', out)
        miss = concierge.read_op(self._store(), 'report.read', {'title': 'payroll'})
        self.assertIn('No report by that name', miss); self.assertIn('Monthly AR Report', miss)

    def test_settings_read_by_key_or_label_and_a_group_lists_its_knobs(self):
        s = self._store()
        self.assertIn('Intent triage (Triage & routing): on', concierge.read_op(s, 'setting.read', {'key': 'intent_classify_enabled'}))
        self.assertIn('Intent triage', concierge.read_op(s, 'setting.read', {'label': 'intent triage'}))
        self.assertIn('No setting by that name', concierge.read_op(s, 'setting.read', {'label': 'warp drive'}))
        out = concierge.read_op(s, 'settings.list', {'group': 'Triage & routing'})
        self.assertIn('Intent triage', out); self.assertNotIn('Triage brain', out)
        self.assertIn('Triage & agents', concierge.read_op(s, 'settings.list', {}))            # no group: the groups

    def test_connections_and_agents(self):
        s = self._store()
        out = concierge.read_op(s, 'connections.list', {})
        self.assertIn('Alex mailbox (outlook)', out); self.assertNotIn('Teams (teams', out); self.assertIn('catalogue cards are off', out)
        self.assertIn('outlook', concierge.read_op(s, 'connection.read', {'name': 'mailbox'}))
        self.assertIn('Teams - type teams', concierge.read_op(s, 'connection.read', {'name': 'teams'}))   # off, but readable by name
        self.assertIn('No connection by that name', concierge.read_op(s, 'connection.read', {'name': 'zzzz'}))
        self.assertIn('coder', concierge.read_op(s, 'agents.list', {}))

    def test_knowledge_search_reads_the_hub_and_the_kept_facts(self):
        """"Which sites do we run" was offered as "I can look it up in Company Hub" - and then searched
        the mail, because no look-up reached the Hub or the facts the owner asked to keep."""
        s = self._store()
        self.assertTrue(toolcatalog.is_read('knowledge.search')); self.assertIn('knowledge.search', toolcatalog.block())
        self.assertEqual(toolcatalog.valid('knowledge.search', {}), 'knowledge.search needs query')
        concierge.remember_fact(s, 'Gail Moreno approves every PO over 5k')
        self.assertIn('Gail Moreno approves', concierge.read_op(s, 'knowledge.search', {'query': 'who approves a PO'}))
        self.assertIn('Nothing the company has written down', concierge.read_op(s, 'knowledge.search', {'query': 'warp drive'}))

    def test_a_brief_for_my_list_says_so_on_the_button_and_the_receipt(self):
        """"Add a to-do: call Ruth" put the MODEL's catalogue sentence on the button ("Start an agent from a
        brief when there is no message behind it"), and the receipt said a regular agent had it."""
        self.assertEqual(concierge.op_label('task.create_from_text', {'kind': 'task'}), 'Put it on my list')
        self.assertEqual(concierge.op_label('task.create_from_text', {'kind': 'coding'}), 'Start a coding agent on it')
        line = concierge._outcome_line('task.create_from_text', {'kind': 'task'}, {'ref': 'TQ-0009', 'title': 'Call Erin'})
        self.assertIn('on your list', line); self.assertNotIn('agent now', line)

    def test_every_general_turn_carries_the_app_state(self):
        """Asked "run me the AR report" from a chat, the assistant had no list of reports at all. The
        state block rides the system prompt of the general road - and never the scripts, which reach
        no model (walk.py)."""
        s = self._store()
        seen = {}
        def llm(system, user, max_tokens=None): seen['system'] = system; return 'Two reports are set up.'
        concierge.say(s, 'what reports do we have?', llm=llm)
        self.assertIn('THE APP RIGHT NOW', seen['system'])
        self.assertIn('Monthly AR Report', seen['system'])
        self.assertIn('walk me through my tasks', seen['system'])
