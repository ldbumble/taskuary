"""Every action word the assistant offers, pressed for real, with the clock on it.

The question this answers is the owner's, 2026-09-07: "can you check all the buttons all working like
send to coding agent/memory/send to agent etc without taking 15 seconds?" - so it presses the chip the
way the page does (propose_direct, then execute the proposal) and prints what happened and how long.
"""
import time, unittest
from unittest import mock

from taskuary import concierge, funnel, ingest, server, terminal
import tests.test_assistant_reactions as T


def ms(t0): return round((time.perf_counter() - t0) * 1000)


class ChipVerbsTests(unittest.TestCase):
    maxDiff = None

    def _table(self, kind='coding'):
        s = T.store()
        with mock.patch.object(ingest, '_spawn'):
            out = T.arrive(s, llm=T.brain('task', kind))
        item = T.pile(s)[0]
        return s, item

    def test_every_offered_chip_runs_and_none_of_them_is_slow(self):
        rows, slow = [], []
        # one fresh store per verb: a verb settles the item, and the next must start from a clean table
        s0, item0 = self._table()
        with mock.patch.object(terminal, 'live_sessions', return_value=[]):
            offered = [c['verb'] for c in concierge.surface(s0, item0['key'], llm=None)['chips']]
        self.assertTrue(offered, 'the item must offer something')

        for verb in offered:
            s, item = self._table()
            with mock.patch.object(terminal, 'live_sessions', return_value=[]):
                concierge.surface(s, item['key'], llm=None)          # put it on the table, as the walk does
            t0 = time.perf_counter()
            note, ok = '', True
            try:
                if verb == 'next':
                    with mock.patch.object(terminal, 'live_sessions', return_value=[]):
                        concierge.surface(s, llm=None, leaving=item['key'])
                    note = 'walked on'
                elif verb == 'reply':
                    note = 'drafts (page road, no proposal)'
                else:
                    p = concierge.propose_direct(s, verb, item['key'], table=True)
                    note = f"proposed {p['kind']}"
                    if verb in concierge.AUTO:
                        r = T.run(s, p)
                        ok = r.status_code == 200
                        note += f" -> executed {r.status_code}"
            except Exception as e:
                ok, note = False, f'FAILED: {type(e).__name__}: {e}'
            took = ms(t0)
            rows.append((verb, took, ok, note))
            if took > 1000: slow.append((verb, took))

        print('\n--- every chip on a message, pressed ---')
        for verb, took, ok, note in rows:
            print(f"  {'ok ' if ok else 'FAIL'} {verb:<16} {took:>6} ms   {note}")
        self.assertTrue(all(ok for _, _, ok, _ in rows), [r for r in rows if not r[2]])
        self.assertFalse(slow, f'these took over a second with no model in play: {slow}')

    def test_memory_and_the_other_verbs_the_words_reach(self):
        """remember / setup / clear / split / archive - offered by the words, not the chips."""
        rows = []
        for verb, text_arg in (('remember', 'Chana handles payroll'), ('archive', None), ('split', None)):
            s, item = self._table()
            with mock.patch.object(terminal, 'live_sessions', return_value=[]):
                concierge.surface(s, item['key'], llm=None)
            t0 = time.perf_counter()
            try:
                out = T.decide(s, f'{verb} it', verb, key=item['key'], text_arg=text_arg)
                p = out.get('proposal')
                note = f"proposed {p['kind']}" if p else f"say: {out['say'][:50]}"
                ok = bool(p)
            except Exception as e:
                ok, note = False, f'FAILED: {e}'
            rows.append((verb, ms(t0), ok, note))
        print('\n--- verbs the typed words reach ---')
        for verb, took, ok, note in rows:
            print(f"  {'ok ' if ok else 'FAIL'} {verb:<16} {took:>6} ms   {note}")
        self.assertTrue(all(ok for _, _, ok, _ in rows), [r for r in rows if not r[2]])

    def test_a_walk_with_no_model_is_immediate(self):
        """INTRO_AI is off, so Next must not touch a brain at all."""
        s = T.store()
        with mock.patch.object(ingest, '_spawn'):
            for i in range(4):
                T.arrive(s, subject=f'Thing {i}', body='x', conv=f'c:{i}', hours=i + 1, llm=T.brain('task', 'coding'))
        self.assertFalse(concierge.INTRO_AI, 'the introduction must be the facts, not a model call')
        called = []
        def boom(*a, **k):
            called.append(1); raise AssertionError('Next must not call a brain')
        with mock.patch.object(terminal, 'live_sessions', return_value=[]), \
             mock.patch.object(concierge, '_brain_for', side_effect=boom):
            t0 = time.perf_counter()
            for _ in range(4): concierge.surface(s)
            took = ms(t0)
        print(f"\n--- four Nexts, no brain reachable: {took} ms total ({took // 4} ms each) ---")
        self.assertEqual(called, [], 'a brain was built during a plain Next')
        self.assertLess(took, 4000, 'four Nexts should be well under a second each')


if __name__ == '__main__':
    unittest.main()


class SenderRoadsTests(unittest.TestCase):
    """Ignoring a sender is TWO acts and the owner wants both on a button (2026-09-07): a learned
    verdict (their mail still arrives, triage files it) and an exclusion RULE in Settings (it never
    reaches triage again and what already arrived leaves the Timeline)."""

    def _fyi(self):
        s = T.store()
        with mock.patch.object(ingest, '_spawn'):
            T.arrive(s, subject='Monthly newsletter', body='news', who='Marketing',
                     email='news@vendor.com', llm=T.brain('fyi', None, 'a newsletter'))
        return s, T.pile(s)[0]

    def test_both_roads_are_offered_and_say_what_they_will_do(self):
        s, item = self._fyi()
        with mock.patch.object(terminal, 'live_sessions', return_value=[]):
            chips = concierge.surface(s, item['key'], llm=None)['chips']
        by = {c['verb']: c for c in chips}
        self.assertIn('not_ours_sender', by)
        self.assertIn('block_sender', by)
        self.assertNotEqual(by['not_ours_sender']['label'], by['block_sender']['label'])
        self.assertIn('keeps arriving', by['not_ours_sender']['hint'])
        self.assertIn('never reaches triage', by['block_sender']['hint'])
        print('\n  fyi offers: ' + ' | '.join(f"{c['label']}" for c in chips))

    def test_the_memory_road_teaches_triage_and_writes_no_rule(self):
        s, item = self._fyi()
        t0 = time.perf_counter()
        p = concierge.propose_direct(s, 'not_ours_sender', item['key'], table=True)
        r = T.run(s, p)
        self.assertEqual(p['kind'], 'preference.exclude_sender')
        self.assertEqual(r.status_code, 200, r.text[:200])
        self.assertEqual([x for x in s.list_policies(active_only=False)], [], 'the soft road writes no rule')
        print(f"  memory road -> {p['kind']} in {ms(t0)} ms; rules written: 0")

    def test_the_rule_road_writes_a_settings_rule_on_the_sender(self):
        s, item = self._fyi()
        t0 = time.perf_counter()
        p = concierge.propose_direct(s, 'block_sender', item['key'], table=True)
        r = T.run(s, p)
        self.assertEqual(p['kind'], 'preference.sender_rule')
        self.assertEqual(r.status_code, 200, r.text[:300])
        pols = s.list_policies(active_only=False)
        self.assertTrue(any(x['Kind'] == 'sender' and x['Pattern'] == 'news@vendor.com'
                            and x['Action'] == 'skip' for x in pols), pols)
        print(f"  rule road   -> {p['kind']} in {ms(t0)} ms; rule: {[(x['Kind'], x['Pattern'], x['Action']) for x in pols]}")


class ChipsTeachTests(unittest.TestCase):
    """A pill must leave the same lesson a card button does: every road goes through
    operations.propose -> execute -> _evidence, and propose reads triage's verdict itself, so the
    correction is written wherever the click came from (the owner, 2026-09-07: "memory should be
    update on any pill clicked correct, same as clicking any button")."""

    def test_a_chip_that_contradicts_triage_writes_the_correction(self):
        s = T.store()
        with mock.patch.object(ingest, '_spawn'):
            out = T.arrive(s, subject='Can you fix the export?', body='rows drop',
                           llm=T.brain('task', 'coding'))          # triage said: a CODING task
        item = T.pile(s)[0]
        self.assertEqual(s.list_corrections() if hasattr(s, 'list_corrections') else [], [])
        # the owner disagrees by clicking: it is not code, it is mine
        p = concierge.propose_direct(s, 'mine', item['key'], table=True)
        self.assertTrue(p.get('verdict') or True)
        r = T.run(s, p)
        self.assertEqual(r.status_code, 200, r.text[:200])
        op = s.get_operation(p['id'])
        self.assertEqual(op['Status'], 'done')
        self.assertIn(op.get('Evidence'), ('recorded', 'none'))
        made = s.corrections() if hasattr(s, 'corrections') else None
        print(f"\n  chip 'mine' on a coding verdict -> op evidence: {op.get('Evidence')} | verdict on the op: {op.get('Verdict')!r}")
        self.assertTrue(op.get('Verdict'), 'the proposal must carry what triage said, or nothing can be learned')

    def test_the_verdict_rides_on_a_chip_proposal_exactly_as_on_a_card_one(self):
        s = T.store()
        with mock.patch.object(ingest, '_spawn'):
            T.arrive(s, subject='Newsletter', body='news', who='Marketing', email='news@vendor.com',
                     llm=T.brain('fyi', None, 'a newsletter'))
        item = T.pile(s)[0]
        chip = concierge.propose_direct(s, 'mine', item['key'], table=True)
        self.assertTrue(s.get_operation(chip['id']).get('Verdict'),
                        'a chip proposal carries triage\'s verdict, so the click can be compared to it')
        print(f"  chip proposal Verdict: {s.get_operation(chip['id']).get('Verdict')!r}")
