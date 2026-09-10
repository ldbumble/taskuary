"""Setting up a report or a workflow BY TALKING, after the chips took over the action words.

The strip over the composer carried a "Set something up" button and it is gone, so the roads left are
the welcome block (a fresh chat) and typing it. This checks the typed one still works end to end, that
it reaches the SAME handlers the Reports and Connections tabs use, and that nothing about the chip row
swallowed it. What compose.compose does internally is its own subsystem and its own tests; here it is
stood in for, because what is under test is the chat's wiring to it.
"""
import json, time, unittest
from unittest import mock

from taskuary import compose, concierge, ingest, server, terminal
import tests.test_assistant_reactions as T

SORTER = 'sort one set-up request'


def sorter(kind='report'):
    """Only the sort pass, scripted."""
    def llm(system, user, **kw):
        if SORTER in system:
            return json.dumps({'kind': kind, 'provider': None, 'why': 'a scheduled check'})
        return json.dumps({'questions': ['Which mailbox?']})
    return llm


class SetupInChatTests(unittest.TestCase):
    def test_asking_for_a_report_in_words_ends_in_a_confirmable_proposal(self):
        s = T.store()
        composed = {'config': {'type': 'sql', 'title': 'Overdue invoices', 'daily_at': '08:00',
                               'query': 'select 1'},
                    'explain': 'Runs each morning.', 'looked_at': ['ar.invoices']}
        with mock.patch.object(concierge, '_compose_llm', return_value=sorter()), \
             mock.patch.object(compose, 'compose', return_value=composed), \
             mock.patch.object(terminal, 'live_sessions', return_value=[]):
            t0 = time.perf_counter()
            out = T.say(s, 'set up a report of overdue invoices every morning',
                        model='I can do that.' + chr(10) + 'DECIDE: setup: a report of overdue invoices every morning')
            took = round((time.perf_counter() - t0) * 1000)
        p = out.get('proposal')
        self.assertIsNotNone(p, out.get('say'))
        self.assertEqual(p['kind'], 'report.create')
        self.assertIn('Nothing is saved', p['say'])          # it never creates on the words alone
        self.assertIn('I read ar.invoices', p['say'])        # ...and it says what it went and read
        print(chr(10) + f"  report from words -> {p['kind']} in {took} ms")

        # the confirmation goes down the Reports tab's own road (server: save_source)
        with mock.patch.object(compose, 'validate', return_value=(True, '')):
            r = T.run(s, p)
        self.assertEqual(r.status_code, 200, r.text[:300])
        made = [x for x in s.list_sources(active_only=False) if x.get('Channel') == 'report']
        self.assertTrue(any(str(x.get('Address') or '').lower() == 'overdue invoices' for x in made), made)
        print(f"  confirmed -> {r.status_code}; report rows now: {len(made)} | {r.json().get('link')}")

    def test_it_asks_before_it_builds_when_something_is_missing(self):
        s = T.store()
        with mock.patch.object(concierge, '_compose_llm', return_value=sorter()), \
             mock.patch.object(compose, 'compose', return_value={'questions': ['Which mailbox?']}), \
             mock.patch.object(terminal, 'live_sessions', return_value=[]):
            out = T.say(s, 'set up a daily digest', model='Sure.' + chr(10) + 'DECIDE: setup: a daily digest')
        self.assertIsNone(out.get('proposal'))
        self.assertIn('Before I put it together', out['say'])
        self.assertIn('Which mailbox?', out['say'])
        self.assertIn('Nothing is set up yet', out['say'])
        print(chr(10) + f"  missing detail -> {out['say'][:80]}")

    def test_work_that_needs_digging_opens_a_walkthrough_not_a_report(self):
        s = T.store()
        with mock.patch.object(concierge, '_compose_llm', return_value=sorter('investigate')), \
             mock.patch.object(terminal, 'live_sessions', return_value=[]):
            out = T.say(s, 'set up something that reconciles the portal against Intacct',
                        model='Right.' + chr(10) + 'DECIDE: setup: reconcile the portal against Intacct')
        say = out.get('say') or ''
        self.assertIn('digging', say.lower())
        self.assertEqual((out.get('proposal') or {}).get('kind'), 'task.setup')
        print(chr(10) + f"  needs digging -> {say[:90]}")

    def test_a_connection_is_proposed_inactive_and_never_carries_the_secret(self):
        s = T.store()
        with mock.patch.object(concierge, '_compose_llm', return_value=sorter('connection')), \
             mock.patch.object(terminal, 'live_sessions', return_value=[]):
            out = T.say(s, 'connect our Slack', model='Ok.' + chr(10) + 'DECIDE: setup: connect Slack')
        p = out.get('proposal') or {}
        blob = ((out.get('say') or '') + json.dumps(p)).lower()
        # a secret VALUE never rides a proposal (PW-196). The word "password" is allowed to appear -
        # the line that promises the secret goes on the card, not here, contains it.
        for leak in ('xoxb-', 'sk-', 'ghp_', 'bearer '):
            self.assertNotIn(leak, blob)
        self.assertIn('never goes here', blob)                # ...and it says so out loud
        if p: self.assertNotEqual(p.get('params', {}).get('active'), True)   # created off, always
        print(chr(10) + f"  connection -> {p.get('kind')} | {(out.get('say') or '')[:80]}")

    def test_the_way_in_still_exists_now_that_the_composer_strip_is_gone(self):
        """A fresh chat offers it as a button; after that it is typed. Both must still be there."""
        import io, os
        view = io.open(os.path.join('website', 'src', 'AssistantView.jsx'), encoding='utf-8').read()
        self.assertIn('Set up a report or workflow', view)     # the welcome block's own button
        self.assertIn('const setup = ()', view)                # ...and it still opens the SetupCard
        self.assertNotIn('tq-quick', view)                     # the strip over the composer is gone
        cards = io.open(os.path.join('website', 'src', 'assistantCards.jsx'), encoding='utf-8').read()
        self.assertIn('export function SetupCard', cards)
        self.assertIn('Open walkthrough', cards)               # the card still has its own road
        self.assertIn('setup', concierge.VERBS)                # and the words reach it

    def test_the_composer_gets_the_stream_so_twelve_seconds_are_not_silent(self):
        """compose reads the real schema and costs seconds (measured 11.8s on the owner's connectors).
        The work is honest; doing it behind three silent dots was not - build_llm always took a trace."""
        seen = {}
        def fake_build(store, *a, **kw): seen.update(kw); return lambda *x, **k: '{}'
        with mock.patch('taskuary.llm.build_llm', side_effect=fake_build):
            concierge._compose_llm(T.store(), trace='TRACE', cancel='CANCEL')
        self.assertEqual(seen.get('trace'), 'TRACE')
        self.assertEqual(seen.get('cancel'), 'CANCEL')


if __name__ == '__main__':
    unittest.main()
