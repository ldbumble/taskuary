"""Every context block the Assistant reads is a declaration, and the defaults are what it read
before there were declarations (the assistant-reads-Taskuary design, 2026-09-19)."""
import json, os, unittest
from unittest import mock
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
        s = A.store(); s.set_setting('calendar_enabled', '1', 't')
        assistant._AGENDA.clear()
        with mock.patch('taskuary.calendar.agenda', lambda store, days=2, start=None: {'events': []}) as _:
            with mock.patch('taskuary.assistant._read_agenda', wraps=assistant._read_agenda) as read:
                B.render(s, B.by_id('calendar'), {'on': True, 'days': 30})
                self.assertEqual(read.call_args[0][1], 30, 'the declared window never reached the Graph call')
        assistant._AGENDA.clear()


import tests.assistant_payload_fixture as F

GOLDEN = os.path.join(os.path.dirname(__file__), 'data', 'assistant_payload_golden.txt')


class DefaultsAreTodayTests(unittest.TestCase):
    """The one test that must never be relaxed: an Assistant report that has configured nothing
    reads exactly what it read before blocks existed."""
    def test_the_default_payload_is_the_one_from_before_blocks_existed(self):
        """THE gate. tests/data/assistant_payload_golden.txt was generated by running
        tests/assistant_payload_fixture.py at e5a34f53 - the last commit before assistantblocks - so
        this compares against bytes the registry had no hand in. Comparing inputs() with itself,
        which is what this test used to do, could never have gone red.

        To regenerate after a DELIBERATE payload change (and say so in the commit):
            python -m tests.assistant_payload_fixture tests/data/assistant_payload_golden.txt"""
        # normalise BOTH sides: .gitattributes pins the file to LF, and a checkout that ignored it
        # would otherwise fail this gate for a reason that has nothing to do with the payload
        want = F.normalise(open(GOLDEN, encoding='utf-8', newline='').read())
        self.assertEqual(F.normalise(F.payload()), want,
                         'the payload moved. If that was deliberate, regenerate the golden and say why in the commit.')

    def test_resolving_a_report_that_chose_nothing_reads_the_same_bytes(self):
        """Every Assistant run now goes through resolve (reports.run_assistant and the dispatch), so
        the gate has to hold through it too - not only through the blocks=None path nobody takes."""
        s = F.store()
        cands = assistant.candidates(s, assistant.cfg(s))
        # the clock is scrubbed from both: a minute boundary falling between the two calls must not
        # be what decides whether the gate is green
        self.assertEqual(F.normalise(assistant.inputs(s, cands)),
                         F.normalise(assistant.inputs(s, cands, blocks=B.resolve(s, {'type': 'assistant'}))))

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
        self.assertEqual(B.resolve(s, {'type': 'assistant'}), {b.id: B.defaults(s, b) for b in B.CATALOGUE})

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
                    {'type': 'assistant', 'blocks': {'nonesuch': {'on': True}}},
                    {'type': 'assistant', 'blocks': 'open_work'}, {'type': 'assistant', 'blocks': None}):
            with self.subTest(cfg=cfg): self.assertEqual(set(B.resolve(s, cfg)), ids)

    def test_a_block_the_saved_choice_does_not_name_is_off(self):
        chosen = B.resolve(A.store(), {'type': 'assistant', 'blocks': {'open_work': {'on': True}}})
        self.assertTrue(chosen['open_work']['on'])
        self.assertFalse(chosen['threads']['on'])                 # shipped later is not switched on later

    def test_a_malformed_choice_reads_nothing_rather_than_everything(self):
        """ConfigJson is free text on POST /api/sources and resolve() runs inside the scheduled
        dispatch, BEFORE assistant.run - so a bad value used to be an AttributeError that stopped the
        report posting at all, with nothing said. Every shape now fails toward spending nothing."""
        s = A.store()
        for bad in ('open_work', ['open_work'], 7, True):
            with self.subTest(blocks=bad):
                chosen = B.resolve(s, {'type': 'assistant', 'blocks': bad})
                self.assertEqual(set(chosen), {b.id for b in B.CATALOGUE})
                self.assertFalse(B.reads_taskuary(chosen))
        for bad in (True, None, 'yes', ['on'], 3):
            with self.subTest(open_work=bad):
                chosen = B.resolve(s, {'type': 'assistant', 'blocks': {'open_work': bad, 'threads': {'on': True}}})
                self.assertFalse(chosen['open_work']['on'], 'an unreadable block value must be off, not on')
                self.assertTrue(chosen['threads']['on'])          # ...and it does not poison the readable ones

    def test_a_null_blocks_means_no_choice_was_recorded(self):
        """DECIDED, so Task 3 does not discover it by shipping: `blocks: null` is ABSENT, not "a
        choice naming nothing". null is how every serialiser says "there is nothing here", so a
        panel that blanks the field must not silently switch a working report off. `{}` is the empty
        CHOICE - the owner opened the panel and ticked nothing - and that one IS all-off."""
        s = A.store()
        self.assertEqual(B.resolve(s, {'type': 'assistant', 'blocks': None}), B.resolve(s, {'type': 'assistant'}))
        self.assertTrue(B.reads_taskuary(B.resolve(s, {'type': 'assistant', 'blocks': None})))
        self.assertFalse(B.reads_taskuary(B.resolve(s, {'type': 'assistant', 'blocks': {}})))
        # ...and a null `blocks` on a report with sources still reads no Taskuary block, as an absent one does
        self.assertFalse(B.reads_taskuary(B.resolve(s, {'type': 'assistant', 'blocks': None, 'watch_source_ids': [4]})))

    def test_a_stored_key_the_block_never_declared_is_ignored(self):
        chosen = B.resolve(A.store(), {'type': 'assistant', 'blocks': {'open_work': {'on': True, 'cap': 3, 'source_ids': [9], 'days': 'x'}}})
        self.assertEqual(chosen['open_work']['cap'], 3)
        self.assertNotIn('source_ids', chosen['open_work'])
        self.assertNotIn('days', chosen['open_work'])

    def test_a_cap_of_zero_is_not_a_cap_of_twenty(self):
        """The builders read `o.get('cap') or 20`, so a stored 0 showed 0 on the card and used 20 in
        the payload. A cap floors at 1; reading none of a block is what the on switch is for."""
        s = A.store()
        chosen = B.resolve(s, {'type': 'assistant', 'blocks': {'open_work': {'on': True, 'cap': 0}}})
        self.assertEqual(chosen['open_work']['cap'], 1)
        for n in range(3): s.create_task({'Title': f'Task {n}', 'Kind': 'coding', 'Status': 'open'}, 'owner')
        self.assertEqual(next(r for r in B.weigh(s, chosen) if r['id'] == 'open_work')['rows'], 1)
        self.assertEqual(len(B.render(s, B.by_id('open_work'), chosen['open_work'])[0].split('\n')), 1)

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

    def test_producers_follow_the_report_and_not_the_global_setting(self):
        s = A.store()
        chosen = B.resolve(s, {'type': 'assistant', 'blocks': {'gone_quiet': {'on': True, 'days': 11}}})
        c = B.producer_cfg(chosen, assistant.cfg(s))
        self.assertEqual(c['producers'], {'cold', 'idea'})      # `idea` is not a block: it is whether the model thinks at all
        self.assertEqual(c['cold_d'], 11)

    def test_the_two_halves_of_followups_keep_their_own_window(self):
        """Ruling P. They used to share one number, so the card quoted the promised block's price at
        the waiting-on block's hours - wrong in both directions at once."""
        s = F.store()
        chosen = B.resolve(s, {'type': 'assistant', 'blocks': {'waiting_on': {'on': True, 'hours': 200},
                                                              'promised': {'on': True, 'hours': 1}}})
        c = assistant.cfg(s) | B.producer_cfg(chosen, assistant.cfg(s))
        self.assertEqual((c['followup_h'], c['promise_h']), (200, 1))
        cands = assistant.candidates(s, c)
        kinds = [x['kind'] for x in cands]
        # 200 hours of silence is longer than the fixture's ask has been quiet; one hour is not
        self.assertNotIn('followup', kinds); self.assertIn('promise', kinds)
        self.assertEqual(len(cands), len({x['key'] for x in cands}), 'a thread was counted twice')

    def test_one_window_is_still_one_pass(self):
        """At the shared default the payload's candidate ORDER must not move - two passes would list
        every ask before every promise, and the gate is on those bytes."""
        s = F.store(); c = assistant.cfg(s)
        self.assertEqual([x['key'] for x in assistant.candidates(s, c)],
                         [x['key'] for x in assistant.candidates(s, c | {'promise_h': c['followup_h']})])


class WeighTests(unittest.TestCase):
    def test_weigh_prices_each_block(self):
        s = F.store()
        rows = B.weigh(s, B.resolve(s, {'type': 'assistant'}))
        self.assertEqual({r['id'] for r in rows}, {b.id for b in B.CATALOGUE})
        one = next(r for r in rows if r['id'] == 'gone_quiet')
        self.assertEqual(one['tables'], ['task', 'comment', 'message', 'run'])
        self.assertEqual((one['rows'], one['tokens'] > 0), (1, True))      # the fixture's nine-day-old task
        self.assertTrue(next(r for r in rows if r['id'] == 'ooo')['sql'])          # a query block shows its statement
        self.assertIsNone(next(r for r in rows if r['id'] == 'threads')['sql'])    # a view shows none

    def test_a_block_switched_off_costs_nothing(self):
        s = F.store()
        rows = {r['id']: r for r in B.weigh(s, B.resolve(s, {'type': 'assistant', 'blocks': {'open_work': {'on': True}}}))}
        self.assertEqual((rows['threads']['on'], rows['threads']['tokens'], rows['threads']['rows']), (False, 0, 0))
        self.assertGreater(rows['open_work']['tokens'], 0)

    def test_a_producer_is_priced_at_what_the_run_would_still_say(self):
        """The run drops a candidate it has already said (fresh), so a card that counts the raw
        producer over-counts every day after the first."""
        s = F.store()
        chosen = B.resolve(s, {'type': 'assistant'})
        before = next(r for r in B.weigh(s, chosen) if r['id'] == 'gone_quiet')
        raw = assistant.cold(s, chosen['gone_quiet']['days'])
        s.upsert_idea(raw[0] | {'action': {}}, '2026-09-19 08:00:00')       # said, with these very facts
        after = next(r for r in B.weigh(s, chosen) if r['id'] == 'gone_quiet')
        self.assertEqual((before['rows'], after['rows']), (1, 0))

    def test_the_knowledge_base_is_priced_against_the_candidates(self):
        """Ruling Q. weigh() used to hand knowledge.block an empty string, which always returns '',
        so the one block that can reach BLOCK_BUDGET always priced at nil."""
        s, seen = F.store(), []
        with mock.patch('taskuary.knowledge.block', side_effect=lambda store, text, *a, **k: (seen.append(text), 'x' * 800)[1]):
            row = next(r for r in B.weigh(s, B.resolve(s, {'type': 'assistant'})) if r['id'] == 'knowledge')
        self.assertTrue(seen and seen[0].strip(), 'the knowledge block was priced against no facts at all')
        self.assertIn('Reconcile the Q3 ledger', seen[0])       # the candidates' own words, as build_inputs passes them
        self.assertGreater(row['tokens'], 100)

    def test_weighing_never_reaches_the_calendar(self):
        """Ruling H. Pricing the calendar means a Graph token POST plus a calendarView per mailbox at
        20s each, and this list is what a settings card re-reads on every keystroke. So a live block
        is declared, not run: rows unknown, tokens nil, and the card says the cost is time."""
        s = F.store(); s.set_setting('calendar_enabled', '1', 't')
        assistant._AGENDA.clear()
        live = [b.id for b in B.CATALOGUE if b.live]
        self.assertEqual(sorted(live), ['calendar', 'meeting_prep', 'system_checks'])
        chosen = B.resolve(s, {'type': 'assistant', 'blocks': {bid: {'on': True} for bid in live}})
        with mock.patch('taskuary.assistant._read_agenda', side_effect=AssertionError('weigh fetched the calendar')):
            rows = {r['id']: r for r in B.weigh(s, chosen)}
        assistant._AGENDA.clear()
        for bid in live:
            with self.subTest(block=bid):
                self.assertTrue(rows[bid]['on'], 'this guard is void if the block is not even on')
                self.assertTrue(rows[bid]['live']); self.assertIsNone(rows[bid]['rows']); self.assertEqual(rows[bid]['tokens'], 0)

    def test_an_identical_choice_is_not_priced_twice(self):
        """Ruling R: one GET renders most of an Assistant payload, and the card asks as the owner
        types."""
        s = F.store(); chosen = B.resolve(s, {'type': 'assistant'})
        B._WEIGHED.clear(); self.addCleanup(B._WEIGHED.clear)
        first = B.weighed(s, chosen)
        with mock.patch('taskuary.assistantblocks.weigh', side_effect=AssertionError('priced again')):
            self.assertEqual(B.weighed(s, chosen), first)
        with mock.patch('taskuary.assistantblocks.weigh', return_value=[]) as w:
            B.weighed(s, chosen, ttl=0); B.weighed(s, chosen, ttl=0)
            self.assertEqual(w.call_count, 2, 'ttl=0 must always read fresh')

    def test_the_cache_hands_out_a_deep_copy_and_never_answers_for_another_store(self):
        """Three latent bugs in one entry: a caller editing a row (or a row's `tables`) would have
        edited the cache; the key held id(store), which Python reuses the moment a store is
        collected; and a strong reference kept every store it ever priced alive."""
        import gc, weakref
        s = F.store(); chosen = B.resolve(s, {'type': 'assistant'})
        B._WEIGHED.clear(); self.addCleanup(B._WEIGHED.clear)
        B.weighed(s, chosen)                                   # fills the entry
        hit = B.weighed(s, chosen)                             # ...and this one is served FROM it
        hit[0]['tokens'] = 999_999; hit[0]['tables'].append('nonsense')
        again = B.weighed(s, chosen)
        self.assertNotEqual(again[0]['tokens'], 999_999, 'a caller edited the cache')
        self.assertNotIn('nonsense', again[0]['tables'], 'the copy was shallow: the nested lists are shared')
        # a second store standing where the first one's id used to be must be priced, not answered for
        key = next(iter(B._WEIGHED))
        s2 = F.store()
        B._WEIGHED[key] = (B._WEIGHED[key][0], [{'id': 'stale'}], weakref.ref(s2))
        self.assertNotEqual([r['id'] for r in B.weighed(s, chosen)], ['stale'])

    def test_the_cache_does_not_keep_a_store_alive(self):
        import gc, weakref
        B._WEIGHED.clear(); self.addCleanup(B._WEIGHED.clear)
        s = F.store(); dead = weakref.ref(s)
        B.weighed(s, B.resolve(s, {'type': 'assistant'}))
        del s; gc.collect()
        self.assertIsNone(dead(), 'the price cache pinned a whole store (and its SQLite connection)')

    def test_the_note_is_priced_for_the_report_that_asked(self):
        """weigh() stamped no `report`, so every card priced the SEEDED Assistant's note - a number
        for a note that report has not got. Both sides go through assistantblocks.stamp now."""
        s = F.store()
        s.set_setting('assistant_notes:77', 'x' * 600, 'test')
        chosen = B.resolve(s, {'type': 'assistant', 'blocks': {'notes': {'on': True}}})
        seeded = next(r for r in B.weigh(s, chosen) if r['id'] == 'notes')
        theirs = next(r for r in B.weigh(s, chosen, report_id=77) if r['id'] == 'notes')
        self.assertGreater(theirs['tokens'], seeded['tokens'] + 100)
        payload = assistant.inputs(s, [], blocks=chosen, report_id=77)
        section = payload[payload.index('\n\nYOUR NOTES FROM YOUR LAST CHECK'):]   # the notes block is the last one
        self.assertEqual(theirs['tokens'], len(section) // 4, 'the card priced a note the payload has not got')


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
    def test_every_priced_block_is_priced_at_what_the_payload_carries(self):
        """On/off alone let a block be priced from the WRONG report's data and say nothing: weigh()
        stamped no `report`, so the card quoted the seeded Assistant's note for every report that
        asked. So slice the payload at the heads the card itself printed and compare the SIZE of
        each section with the tokens the card charged for it."""
        s = F.store()
        s.set_setting('assistant_notes:77', 'a note of its own, and a much longer one at that. ' * 8, 'test')
        chosen = B.resolve(s, {'type': 'assistant'})
        rows = B.weigh(s, chosen, report_id=77)
        payload = assistant.inputs(s, B._candidates(s, chosen), blocks=chosen, report_id=77)
        # EVERY on block with a head cuts the payload, priced or not: a `live` one is charged 0 on
        # purpose and still takes up room, so leaving it out would fold its section into its
        # neighbour's and make every comparison after it meaningless
        cuts = [(r, payload.index(r['heading'].split('(')[0].strip()))
                for r in rows if r['on'] and r['heading'] and r['heading'].split('(')[0].strip() in payload]
        self.assertEqual([i for _, i in cuts], sorted(i for _, i in cuts), 'the card lists the blocks out of payload order')
        self.assertTrue([r for r, _ in cuts if r['tokens']], 'nothing was priced - this test would pass on an empty store')
        for n, (r, i) in enumerate(cuts):
            if not r['tokens']: continue                       # a live block: charged nil by declaration
            end = cuts[n + 1][1] if n + 1 < len(cuts) else len(payload)
            # the head's own '\n\n' lead-in sits before `i`, and _price counts it for a `whole`
            # block and not for the others - two tokens of slack, against sections of tens
            with self.subTest(block=r['id']):
                self.assertAlmostEqual(r['tokens'], len(payload[i:end].rstrip()) // 4, delta=2,
                                       msg=f"{r['id']} was priced from data the payload has not got")

    def test_the_card_names_the_blocks_the_payload_contains(self):
        """One resolution behind the card and the payload, or the card claims a read the run never
        made - the exact class of bug this feature exists to end. Both are built from the SAME
        candidate list here, because the knowledge base is priced against those very facts."""
        s = F.store()
        cfg = {'type': 'assistant', 'blocks': {'open_work': {'on': True}, 'knowledge': {'on': True},
                                               'gone_quiet': {'on': True, 'days': 14}, 'threads': {'on': True, 'days': 2}}}
        chosen = B.resolve(s, cfg)
        payload = assistant.inputs(s, B._candidates(s, chosen), blocks=chosen)
        for row in B.weigh(s, chosen):
            b = B.by_id(row['id'])
            if not b.heading: continue                    # a producer renders under CANDIDATES, which weigh does not own
            head = b.heading.split('(')[0].split('{')[0].strip().rstrip(':')
            with self.subTest(block=row['id']):
                if not row['on']: self.assertNotIn(head, payload, f"the card says {row['id']} is off and the payload has it")
                elif row['rows'] or row['tokens']: self.assertIn(head, payload, f"the card prices {row['id']} and the payload has not got it")

    def test_a_priced_knowledge_base_is_really_in_the_payload(self):
        """The case a `tokens` guard skips: knowledge renders '' when nothing matches, so it could be
        priced and absent at once without anything noticing."""
        s = F.store()
        chosen = B.resolve(s, {'type': 'assistant', 'blocks': {'knowledge': {'on': True}, 'gone_quiet': {'on': True}}})
        with mock.patch('taskuary.knowledge.block', side_effect=lambda store, text, *a, **k: 'FROM THE KNOWLEDGE BASE\n- a passage'):
            row = next(r for r in B.weigh(s, chosen) if r['id'] == 'knowledge')
            payload = assistant.inputs(s, B._candidates(s, chosen), blocks=chosen)
        self.assertGreater(row['tokens'], 0)
        self.assertIn('FROM THE KNOWLEDGE BASE', payload)


class IdentityTests(unittest.TestCase):
    """Ruling M: identity is the report, data scope is the blocks. They were one flag, which worked
    only while "has sources of its own" and "is its own monitor" were the same sentence."""
    def test_a_monitor_that_also_reads_taskuary_keeps_its_own_name_and_namespace(self):
        from taskuary import reports
        s = F.store()
        sid = s.save_source({'Channel': 'report', 'Address': 'watch@report', 'Active': 1, 'ConfigJson': json.dumps(
            {'title': 'Ledger watch', 'type': 'assistant', 'watch_sources': [{'kind': 'sql', 'query': 'select 1'}],
             'blocks': {'open_work': {'on': True}}})}, 't')
        reports.run_report_source(s, s.get_source(sid), lambda *a, **k: json.dumps(
            {'say': [{'key': 'idea:ledger', 'text': 'The ledger job looks stuck.', 'why': 'two runs failed'}]}))
        ideas = {i['Key'] for i in s.list_ideas()}
        self.assertIn(f'report:{sid}:idea:ledger', ideas, f'a monitor lost its namespace: {sorted(ideas)}')
        posts = [m for m in s.recent_messages('2000-01-01', limit=80) if str(m.get('ConversationId') or '') == f'assistant:{sid}']
        self.assertTrue(posts, 'the post left its own thread for the shared `assistant` one')
        self.assertEqual(posts[0]['FromName'], 'Ledger watch')

    def test_the_apps_own_assistant_is_still_the_assistant_thread(self):
        s = F.store()
        src = assistant.seeded_source(s)
        self.assertEqual(src['Owner'], 'template')
        self.assertFalse(assistant.own_identity(s, src['SourceId']), 'the seeded Assistant must keep the `assistant` thread')
        self.assertFalse(assistant.own_identity(s, None))
        self.assertTrue(assistant.own_identity(s, int(src['SourceId']) + 999))

    def test_deleting_the_seeded_row_does_not_hand_its_thread_to_another_report(self):
        """Deleting the seeded Assistant is the documented off switch (store.py). Anchored on
        `source()` - the FIRST assistant-typed report - the owner's own Assistant report inherited
        the exception the moment that row went, taking the shared thread and the shared idea
        namespace with it: exactly the collision own_identity exists to prevent."""
        from taskuary import reports
        s = F.store()
        mine = s.save_source({'Channel': 'report', 'Address': 'mine@report', 'Active': 1, 'ConfigJson': json.dumps(
            {'title': 'My assistant', 'type': 'assistant', 'blocks': {'open_work': {'on': True}}})}, 'owner')
        s.delete_source(assistant.seeded_source(s)['SourceId'])
        self.assertIsNone(assistant.seeded_source(s))
        self.assertEqual(assistant.source(s)['SourceId'], mine)       # source() now names the owner's report...
        self.assertTrue(assistant.own_identity(s, mine))              # ...and identity does not follow it
        reports.run_report_source(s, s.get_source(mine), lambda *a, **k: json.dumps(
            {'say': [{'key': 'idea:stuck', 'text': 'Something looks stuck.', 'why': 'nothing moved'}]}))
        self.assertIn(f'report:{mine}:idea:stuck', {i['Key'] for i in s.list_ideas()})
        posts = [m for m in s.recent_messages('2000-01-01', limit=80) if str(m.get('ConversationId') or '') == f'assistant:{mine}']
        self.assertTrue(posts and posts[0]['FromName'] == 'My assistant')


class OwnerIsProvenanceTests(unittest.TestCase):
    """Ruling X. `POST /api/sources` set Owner on every save, and Owner is in SOURCE_COLS, so an
    ordinary Reports-tab save - or the on/off Switch, which posts {SourceId, Active} - took the row
    over. The seeded Assistant stopped being seeded on the owner's commonest action, which moved its
    posts off the Timeline's `assistant` thread and re-namespaced its ideas.

    Through the API, not store.save_source: the route is where the overwrite lived."""
    def _api(self):
        from taskuary import server
        s = F.store()
        p = mock.patch.object(server, 'store', s); p.start(); self.addCleanup(p.stop)
        return s, server

    def test_an_ordinary_save_and_the_active_toggle_leave_the_seeded_row_seeded(self):
        s, server = self._api()
        sid = assistant.seeded_source(s)['SourceId']
        cfg = json.loads(s.get_source(sid)['ConfigJson'])
        before = (assistant.own_identity(s, sid), assistant.notes_key(s, sid))
        self.assertEqual(before, (False, 'assistant_notes'))
        server.save_source(server.SourceBody(SourceId=sid, Channel='report', Address='Assistant', Active=True,
                                             ConfigJson=json.dumps({**cfg, 'every_minutes': 45})))   # the Save button
        server.save_source(server.SourceBody(SourceId=sid, Active=False))                            # the on/off Switch
        server.save_source(server.SourceBody(SourceId=sid, Active=True))
        self.assertEqual(s.get_source(sid)['Owner'], 'template', 'an edit reassigned the row')
        self.assertEqual(assistant.seeded_source(s)['SourceId'], sid)
        self.assertEqual((assistant.own_identity(s, sid), assistant.notes_key(s, sid)), before)
        self.assertEqual(json.loads(s.get_source(sid)['ConfigJson'])['every_minutes'], 45)   # ...and the edit still landed

    def test_the_seeded_assistant_still_posts_on_the_shared_thread_after_a_save(self):
        from taskuary import reports
        s, server = self._api()
        sid = assistant.seeded_source(s)['SourceId']
        server.save_source(server.SourceBody(SourceId=sid, Active=False))
        server.save_source(server.SourceBody(SourceId=sid, Active=True))
        reports.run_report_source(s, s.get_source(sid), lambda *a, **k: json.dumps(
            {'say': [{'key': 'idea:ledger', 'text': 'The ledger looks stuck.', 'why': 'nothing moved'}]}))
        self.assertIn('idea:ledger', {i['Key'] for i in s.list_ideas()})                 # not report:<sid>:idea:ledger
        posts = [m for m in s.recent_messages('2000-01-01', limit=80) if str(m.get('FromName') or '') == 'Assistant']
        self.assertTrue(posts and posts[0]['ConversationId'] == 'assistant', 'the Assistant left its own Timeline thread')

    def test_a_discovered_chats_name_survives_the_toggle_too(self):
        """Owner is provenance for more than the seeded rows: the Telegram poller writes
        "discovered: <title>" there and ConnectorsView prints it. One toggle used to erase it."""
        s, server = self._api()
        sid = s.save_source({'Channel': 'telegram', 'Address': '-100123', 'Active': 1,
                             'Owner': 'discovered: Ops room'}, 'telegram-poll')
        server.save_source(server.SourceBody(SourceId=sid, Active=False))
        self.assertEqual(s.get_source(sid)['Owner'], 'discovered: Ops room')

    def test_a_new_source_is_still_owned_by_whoever_made_it(self):
        s, server = self._api()
        out = server.save_source(server.SourceBody(Channel='report', Address='new@report', Active=True,
                                                   ConfigJson=json.dumps({'title': 'New', 'type': 'rest'})))
        self.assertEqual(s.get_source(out['sourceId'])['Owner'], server.ACTOR)


class NotesAreOneChecksOwnTests(unittest.TestCase):
    """Ruling W: the note is a check's private memory of its own last run. One global key meant a
    second Assistant report read the first's note and then overwrote it."""
    def test_each_report_writes_and_reads_its_own_note(self):
        from taskuary import reports
        s = F.store()
        mine = s.save_source({'Channel': 'report', 'Address': 'mine@report', 'Active': 1, 'ConfigJson': json.dumps(
            {'title': 'My assistant', 'type': 'assistant', 'blocks': {'open_work': {'on': True}}})}, 'owner')
        reports.run_report_source(s, s.get_source(mine), lambda *a, **k: json.dumps(
            {'say': [], 'notes': 'the importer run is the one to watch'}))
        settings = s.get_settings()
        self.assertIn('the importer', settings[f'assistant_notes:{mine}'])
        self.assertEqual(settings.get('assistant_notes'), F.store().get_settings().get('assistant_notes'),
                         "a report overwrote the app Assistant's note")
        # ...and each one READS its own: the seeded note must not leak into this report's payload
        chosen = B.resolve(s, {'type': 'assistant', 'blocks': {'notes': {'on': True}}})
        self.assertIn('the importer', assistant.inputs(s, [], blocks=chosen, report_id=mine))
        self.assertNotIn('the importer', assistant.inputs(s, [], blocks=chosen))
        self.assertIn('Dana still owes the ledger', assistant.inputs(s, [], blocks=chosen))   # the seeded one's, unmoved

    def test_the_seeded_assistant_keeps_the_bare_key(self):
        s = F.store()
        self.assertEqual(assistant.notes_key(s, None), 'assistant_notes')
        self.assertEqual(assistant.notes_key(s, assistant.seeded_source(s)['SourceId']), 'assistant_notes')
        self.assertEqual(assistant.notes_key(s, 4242), 'assistant_notes:4242')


class ReadsNothingTests(unittest.TestCase):
    """Ruling N: every block off and no source either is a report that reads nothing. It runs on a
    clock, so it would have gone on doing that for ever, quietly."""
    def test_a_report_that_reads_nothing_says_so_and_posts_nothing(self):
        from taskuary import reports
        s = F.store()
        sid = s.save_source({'Channel': 'report', 'Address': 'empty@report', 'Active': 1, 'ConfigJson': json.dumps(
            {'title': 'Empty watch', 'type': 'assistant', 'blocks': {}})}, 't')
        out = reports.run_report_source(s, s.get_source(sid), lambda *a, **k: '{"say": [{"key": "idea:x", "text": "anything"}]}')
        self.assertEqual(out['said'], 0)
        self.assertIsNone(out['message_id'])
        self.assertIn('reads nothing', out['summary'])
        self.assertIn('reads nothing', reports.last_runs(s)[sid]['summary'])   # on the Reports tab, not only in a log
        self.assertFalse([i for i in s.list_ideas() if i['Key'].endswith('idea:x')])


class EndpointTests(unittest.TestCase):
    def _client(self):
        from fastapi.testclient import TestClient
        from taskuary import server
        B._WEIGHED.clear(); self.addCleanup(B._WEIGHED.clear)
        return TestClient(server.app), server.store

    def _source(self, store, cfg):
        """The route reads the SHARED test store, so anything written here outlives the test - two
        poll-lane tests count the sources in it. Every row is taken back out."""
        sid = store.save_source({'Channel': 'report', 'Address': f"{cfg['title']}@report", 'Active': 1,
                                 'ConfigJson': json.dumps(cfg)}, 't')
        self.addCleanup(store.delete_source, sid)
        return sid

    def test_the_route_prices_the_declared_defaults(self):
        c, store = self._client()
        d = c.get('/api/assistant/blocks').json()
        self.assertEqual({x['id'] for x in d['data']}, {b.id for b in B.CATALOGUE})
        self.assertEqual(d['cost'], None)                          # the money line is Task 3's
        self.assertIsInstance(d['runs_per_day'], float)
        self.assertTrue(d['reads_taskuary'])
        self.assertEqual([u['id'] for u in d['unpriced']], [b.id for b in B.CATALOGUE if b.live])

    def test_a_reports_own_choice_is_what_is_priced(self):
        c, store = self._client()
        sid = self._source(store, {'title': 'One block', 'type': 'assistant', 'once_per_week': True,
                                   'cron': '0 6 * * 1', 'blocks': {'open_work': {'on': True}}})
        d = c.get(f'/api/assistant/blocks?source_id={sid}').json()
        self.assertEqual({x['id'] for x in d['data'] if x['on']}, {'open_work', 'system_checks'})
        self.assertEqual(d['total_tokens'], next(x['tokens'] for x in d['data'] if x['id'] == 'open_work'))
        self.assertAlmostEqual(d['runs_per_day'], round(1 / 7, 3))          # a weekly brief is not a daily one
        self.assertTrue(d['reads_taskuary'])

    def test_the_route_prices_the_note_of_the_report_it_was_asked_about(self):
        """The route has to hand weigh() the report, or the card quotes the seeded Assistant's note
        for every report that asks - a number for a note that report has not got."""
        c, store = self._client()
        sid = self._source(store, {'title': 'Note watch', 'type': 'assistant', 'blocks': {'notes': {'on': True}}})
        store.set_setting(f'assistant_notes:{sid}', 'a note of its own, and a long one. ' * 20, 'test')
        self.addCleanup(store.set_setting, f'assistant_notes:{sid}', '', 'test')
        mine = next(x for x in c.get(f'/api/assistant/blocks?source_id={sid}').json()['data'] if x['id'] == 'notes')
        seeded = next(x for x in c.get('/api/assistant/blocks').json()['data'] if x['id'] == 'notes')
        self.assertGreater(mine['tokens'], seeded['tokens'] + 100, 'the card priced the wrong report\'s note')

    def test_a_systems_only_report_says_what_is_unpriced_rather_than_just_nil(self):
        """A monitor reading a live SQL view totals 0 tokens, which is true and useless on its own -
        it is the report that costs the most. The card needs the words, so the route names them."""
        c, store = self._client()
        sid = self._source(store, {'title': 'SQL watch', 'type': 'assistant',
                                   'watch_sources': [{'kind': 'sql', 'query': 'select 1'}]})
        d = c.get(f'/api/assistant/blocks?source_id={sid}').json()
        self.assertEqual({x['id'] for x in d['data'] if x['on']}, {'system_checks'})
        self.assertEqual(d['total_tokens'], 0)
        self.assertFalse(d['reads_taskuary'])
        self.assertEqual([u['label'] for u in d['unpriced']], ['Configured systems'])

    def test_a_source_that_is_not_an_assistant_report_is_not_answered_with_the_defaults(self):
        c, store = self._client()
        self.assertEqual(c.get('/api/assistant/blocks?source_id=999999').status_code, 404)
        sid = self._source(store, {'title': 'AR', 'type': 'mssql'})
        self.assertEqual(c.get(f'/api/assistant/blocks?source_id={sid}').status_code, 404)


class RunsPerDayTests(unittest.TestCase):
    def test_a_clock_is_counted_over_the_week_it_runs_in(self):
        from taskuary.reports import runs_per_day
        self.assertEqual(runs_per_day({'every_minutes': 30}), 48)
        self.assertEqual(runs_per_day({'daily_at': '08:00'}), 1)
        self.assertEqual(runs_per_day({'cron': '0 6 * * 1-5'}), round(5 / 7, 3))
        self.assertEqual(runs_per_day({'cron': '0 6 * * *'}), 1)
        self.assertEqual(runs_per_day({'daily_at': '08:00', 'once_per_week': True}), round(1 / 7, 3))
        self.assertEqual(runs_per_day({'on_startup': True, 'once_per_day': True}), 1)
        self.assertEqual(runs_per_day({}), 0)
        self.assertEqual(runs_per_day({'cron': 'nonsense'}), 0)


if __name__ == '__main__':
    unittest.main()
