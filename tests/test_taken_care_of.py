"""Taken care of: three moments where Taskuary used to go quiet, and now says what happened, that nothing is lost,
and what (if anything) is the owner's to do.

1. Microsoft signs the owner out. The token was still stored, so the card said "Signed in" while no mail had been
   read for hours. Now the card and the bell say "Microsoft signed you out at 2 pm", and the sign-in coming back is
   announced with real counts: "Back on. 3 came in, 1 needs you."
2. The brain goes down. The bell gave up after four hours, and one good answer cleared it while mail it had failed on
   was still unsorted. Now it stays up while anything is held, and says when it is back: "I'm back. All 3 sorted".
3. The retry gives up. It wrote a debug line and left the message among the things that need nothing. Now the message
   is on the owner's list with its Retry, and one line says how many and who from. And spent rows no longer fill the
   sweep's page ahead of newer ones.
"""
import json, re, unittest
from datetime import datetime, timedelta
from unittest import mock

from taskuary import channels, funnel, ingest, msauth, problems
from taskuary.processing_order import feed_band
from taskuary.processing_all import row_lane
from taskuary.store import MemoryStore


def ago(**kw): return (datetime.now() - timedelta(**kw)).strftime('%Y-%m-%d %H:%M:%S')


ME = 'alex@northwind.example'
LAPSE = f'{msauth.LAPSED} - sign in again on the Outlook card (AADSTS700082: the refresh token has expired)'
FYI = lambda *a, **k: '{"intent": "fyi", "why": "an automated notice"}'
TASK = lambda *a, **k: '{"intent": "task", "why": "she asks for a refund", "title": "Refund for a resident"}'
def boom(*a, **k): raise RuntimeError('azure_openai error 500')
def junk(*a, **k): return 'I am not sure what you mean'

# the words an office manager should never have to read (the voice rule)
BANNED = re.compile(r'\b(agent|AI|model|brain|triage|pipe|FYI|lane|sync|session|connector|API|token|device code|backlog|band|'
                    r'error|failed|retry|queue)\b', re.I)


def _mail(i, who='Erin Blake', addr='erin@northwind.example', sent=None, **kw):
    return {'external_id': f'graph:m{i}', 'channel': 'email', 'from_name': who, 'from_email': addr, 'conversation_id': f'conv{i}',
            'subject': f'Question {i}', 'body': 'Could you look at the invoice from Payworth?', 'sent_at': sent or ago(minutes=5),
            'source_name': ME, **kw}


def _outlook(s):
    c = s.get_connector_by_type('outlook')
    s.save_connector({'ConnectorId': c['ConnectorId'], 'Active': 1, 'Secret': 'refresh-token',
                      'ConfigJson': json.dumps({'auth': 'user', 'account': ME})}, 'o')
    s.save_source({'Channel': 'email', 'Address': ME, 'ConnectorId': c['ConnectorId'], 'Active': 1}, 'o')
    return s.get_connector(c['ConnectorId'])


def _lapse(s, c):
    """Mail was last read half an hour ago; then Microsoft refused the token."""
    s._exec('UPDATE connector SET LastSyncAt=? WHERE ConnectorId=?', (ago(minutes=30), c['ConnectorId']))
    s.touch_connector(c['ConnectorId'], LAPSE)
    problems.watch_mail(s, s.get_connector(c['ConnectorId']), LAPSE)


class SignedOut(unittest.TestCase):
    def setUp(self): self.s = MemoryStore(); self.c = _outlook(self.s)

    def test_a_lapsed_sign_in_is_said_out_loud_with_the_way_back(self):
        _lapse(self.s, self.c)
        p = {x['key']: x for x in problems.collect(self.s)}[f"connector:{self.c['ConnectorId']}"]
        self.assertTrue(p['title'].startswith('Microsoft signed you out at '), p['title'])
        self.assertEqual(p['detail'], "I can't see your mail, so I can't watch for answers. Sign in here and I'll catch up.")
        self.assertEqual((p['fix'], p['where'], p['connector']), ('Sign in', 'Connections', str(self.c['ConnectorId'])))

    def test_the_card_no_longer_says_signed_in(self):
        from fastapi.testclient import TestClient
        from taskuary import server
        _lapse(self.s, self.c)
        prev, server.store = server.store, self.s
        try: rows = TestClient(server.app).get('/api/connectors').json()['data']
        finally: server.store = prev
        mine = next(r for r in rows if r['ConnectorId'] == self.c['ConnectorId'])
        self.assertTrue(mine['SignedOut'])
        self.assertFalse(any(r['SignedOut'] for r in rows if r['ConnectorId'] != self.c['ConnectorId']))

    def test_it_stays_up_for_as_long_as_it_is_true(self):
        """Four hours of nobody reading the mail is not yesterday's news."""
        _lapse(self.s, self.c)
        self.s.set_setting(f"{problems.AWAY}{self.c['ConnectorId']}", json.dumps({'at': ago(hours=9)}), 't')
        self.s._exec('UPDATE connector SET LastErrorAt=? WHERE ConnectorId=?', (ago(hours=9), self.c['ConnectorId']))
        self.assertIn(f"connector:{self.c['ConnectorId']}", {p['key'] for p in problems.collect(self.s)})

    def test_the_rail_says_it_the_same_way(self):
        _lapse(self.s, self.c)
        row = next(r for r in funnel.broken_connections(self.s) if r['key'] == f"conn:{self.c['ConnectorId']}")
        self.assertTrue(row['title'].startswith('Microsoft signed you out'))

    def test_only_microsoft_refusing_the_token_is_a_lapse(self):
        """A 503 from their sign-in service is their bad minute; sending the owner to sign in again would be wrong."""
        def answer(code):
            r = mock.Mock(status_code=code, headers={'content-type': 'application/json'}, text='')
            r.json.return_value = {'error': 'invalid_grant', 'error_description': 'AADSTS700082: expired'}
            return r
        for code, lapsed in ((400, True), (401, True), (503, False), (429, False)):
            with mock.patch('taskuary.msauth.requests.post', return_value=answer(code)):
                with self.assertRaises(RuntimeError) as e: msauth.refresh({'client_id': 'x'}, 'rt')
            self.assertEqual(msauth.lapsed(str(e.exception)), lapsed, code)

    def test_coming_back_is_announced_with_what_came_in(self):
        _lapse(self.s, self.c)
        ingest.ingest_message(self.s, _mail(1), llm=TASK)
        ingest.ingest_message(self.s, _mail(2, 'Payworth', 'billing@vendor.example'), llm=FYI)
        ingest.ingest_message(self.s, _mail(3, 'Trainly', 'news@vendor.example'), llm=FYI)
        self.assertEqual(problems.news(self.s), [], 'nothing to announce while it is still out')
        self.s.touch_connector(self.c['ConnectorId'])
        problems.watch_mail(self.s, self.c, None)
        n = {x['key']: x for x in problems.news(self.s)}[f"back:mail:{self.c['ConnectorId']}"]
        self.assertEqual(n['title'], 'Back on. 3 came in, 1 needs you.')
        self.assertNotIn(f"connector:{self.c['ConnectorId']}", {p['key'] for p in problems.collect(self.s)})
        problems.dismiss(self.s, n['key'])                       # read once, gone
        self.assertEqual(problems.news(self.s), [])

    def test_the_poll_itself_keeps_the_story(self):
        """Wired where the poll writes the card's state: a lapse marks the moment, the next clean poll closes it."""
        with mock.patch('taskuary.channels.graph_token', side_effect=RuntimeError(LAPSE)):
            channels._poll_one(self.s, self.c, False, 0, None, False)
        self.assertTrue(problems.away_since(self.s, self.c['ConnectorId']))
        self.s.save_source({**next(x for x in self.s.list_sources() if x['Address'] == ME), 'Active': 0}, 'o')
        with mock.patch('taskuary.channels.graph_token', return_value='tok'):
            channels._poll_one(self.s, self.c, False, 0, None, False)
        self.assertEqual(problems.away_since(self.s, self.c['ConnectorId']), '')
        self.assertIn(f"back:mail:{self.c['ConnectorId']}", {x['key'] for x in problems.news(self.s)})


class Thinking(unittest.TestCase):
    def setUp(self): self.s = MemoryStore()

    def failed(self, n, sent=None):
        return [ingest.ingest_message(self.s, _mail(i, sent=sent), llm=boom)['message_id'] for i in range(n)]

    def test_while_down_it_says_mail_is_held(self):
        self.failed(3)
        p = {x['key']: x for x in problems.collect(self.s)}['triage']
        self.assertEqual(p['title'], "I'm having trouble thinking for a few minutes")
        self.assertIn("Mail is still coming in and I'm holding all of it.", p['detail'])
        self.assertIn('3 are waiting', p['detail'])
        self.assertIn('500', p['error'], 'the raw cause is kept for whoever needs it, off the line she reads')

    def test_it_does_not_age_out_while_anything_is_held(self):
        self.failed(2)
        self.s.set_setting('triage_last_error_at', ago(hours=problems.STALE_HOURS + 3), 't')
        self.s.set_setting(problems.THINKING, json.dumps({'at': ago(hours=problems.STALE_HOURS + 3)}), 't')
        self.assertIn('triage', {p['key'] for p in problems.collect(self.s)})

    def test_one_good_answer_does_not_clear_it_while_others_are_stuck(self):
        self.failed(3)
        ingest.ingest_message(self.s, _mail(9), llm=FYI)          # the brain answered once
        self.assertEqual(self.s.get_setting('triage_last_error'), '')
        p = {x['key']: x for x in problems.collect(self.s)}['triage']
        self.assertEqual(p['title'], "I'm catching up")
        self.assertIn('3 messages I was holding', p['detail'])

    def test_it_says_when_it_is_back_with_real_counts(self):
        self.failed(3)
        problems.collect(self.s)                                    # the outage is noticed
        answers = iter([TASK, FYI, FYI])
        self.assertEqual(ingest.retry_failed_triage(self.s, lambda *a, **k: next(answers)(*a, **k)), 3)
        self.assertNotIn('triage', {p['key'] for p in problems.collect(self.s)})
        n = {x['key']: x for x in problems.news(self.s)}['back:thinking']
        self.assertEqual(n['title'], "I'm back. All 3 sorted, 1 needs you.")

    def test_the_timeline_caption_gets_the_same_words(self):
        from fastapi.testclient import TestClient
        from taskuary import server
        self.failed(1)
        prev, server.store = server.store, self.s
        try: st = TestClient(server.app).get('/api/ingest/status').json()
        finally: server.store = prev
        self.assertTrue(st['thinking'].startswith("I'm having trouble thinking for a few minutes. Mail is still coming in"))

    def test_a_no_ai_install_is_not_an_outage(self):
        ingest.ingest_message(self.s, _mail(1), llm=None)            # "awaiting AI triage": nothing failed
        self.assertNotIn('triage', {p['key'] for p in problems.collect(self.s)})


class GivenUp(unittest.TestCase):
    def setUp(self): self.s = MemoryStore()

    def spent(self, i, who='Erin Blake', addr='erin@northwind.example', sent=None):
        """Unusable answers while the brain is otherwise fine - failing for its own reasons."""
        mid = ingest.ingest_message(self.s, _mail(i, who, addr, sent=sent), llm=junk)['message_id']
        for _ in range(ingest.RETRY_TRIES):
            self.s.add_route(mid, None, 'file', None, 'AI triage returned an answer it could not read as a verdict - retry available',
                             [], 'triage', parse_error='not json')
        return mid

    def test_spent_rows_do_not_fill_the_sweeps_page(self):
        """25 spent rows at the head used to be the whole LIMIT - nothing newer was ever retried again."""
        for i in range(ingest.RETRY_SWEEP + 5): self.spent(i)
        fresh = ingest.ingest_message(self.s, _mail(99), llm=boom)['message_id']
        got = self.s.stranded_triage_failures(ingest.RETRY_SWEEP, since=ago(hours=24), tries=ingest.RETRY_TRIES)
        self.assertEqual([r['MessageId'] for r in got], [fresh])

    def test_a_row_the_retry_gave_up_on_is_on_her_list_with_its_retry(self):
        mid = self.spent(1)
        self.s.set_setting('triage_last_error', '', 't')
        ingest.retry_failed_triage(self.s, FYI)
        m = self.s.get_message(mid)
        self.assertEqual(m['Status'], 'error', 'still unjudged - nothing was started for it')
        row = next(r for r in self.s.feed(ids=[mid]))
        self.assertEqual((feed_band(row), row_lane(row)), (2, 'unjudged'))
        self.assertTrue(row['NeedsYou'] or feed_band(row) == 2)
        item = next(i for i in funnel.from_feed(self.s, [row], canonical=True) if i['key'] == f'msg:{mid}')
        self.assertEqual(funnel._band(item), 2, 'the pile agrees: your task, not the quiet band')
        self.assertEqual(ingest.retry_failed_triage(self.s, FYI), 0, 'the sweep does not pick it up again')
        self.assertTrue(self.s.claim_retriage(mid), 'and her Retry still works')

    def test_she_is_told_how_many_and_who_from(self):
        self.spent(1); self.spent(2, 'Payworth', 'billing@vendor.example'); self.spent(3)
        self.s.set_setting('triage_last_error', '', 't')
        ingest.retry_failed_triage(self.s, FYI)
        n = {x['key']: x for x in problems.news(self.s)}['held']
        self.assertEqual(n['title'], "I couldn't make sense of 3 messages, so I put them on your list to be safe.")
        self.assertEqual(n['detail'], "Here's who they are from: Erin Blake, Payworth.")

    def test_an_outage_is_not_a_reason_to_give_up(self):
        mid = self.spent(1)
        self.s.set_setting('triage_last_error', 'azure_openai error 500', 't')
        ingest.retry_failed_triage(self.s, boom)
        self.assertNotEqual(self.s.message_routes(mid)[-1]['Decision'], 'held')

    def test_sliding_out_of_the_window_is_a_stop_too_but_history_stays_put(self):
        recent = ingest.ingest_message(self.s, _mail(1, sent=ago(hours=30)), llm=boom)['message_id']
        old = ingest.ingest_message(self.s, _mail(2, sent=ago(days=9)), llm=boom)['message_id']
        ingest.retry_failed_triage(self.s, boom)
        self.assertEqual(self.s.message_routes(recent)[-1]['Decision'], 'held')
        self.assertNotEqual(self.s.message_routes(old)[-1]['Decision'], 'held', 'a fortnight of history is not dumped on her')

    def test_retry_all_still_reaches_what_was_handed_over(self):
        mid = self.spent(1)
        self.s.set_setting('triage_last_error', '', 't')
        ingest.retry_failed_triage(self.s, FYI)
        self.assertIn(mid, [r['MessageId'] for r in self.s.stranded_triage_failures(500)])
        self.assertEqual(ingest.retry_failed_triage(self.s, FYI, limit=500, hours=0, tries=0), 1)
        self.assertEqual(self.s.get_message(mid)['Status'], 'filed')


class Voice(unittest.TestCase):
    def test_none_of_these_lines_uses_a_word_she_should_not_have_to_read(self):
        s = MemoryStore(); c = _outlook(s)
        _lapse(s, c)
        ingest.ingest_message(s, _mail(1, sent=ago(hours=30)), llm=boom)
        ingest.ingest_message(s, _mail(2), llm=boom)
        ingest.retry_failed_triage(s, boom)
        said = [p for p in problems.collect(s) if p.get('kind') in ('signed_out', 'thinking')]
        s.touch_connector(c['ConnectorId']); problems.watch_mail(s, c, None)
        ingest.retry_failed_triage(s, FYI)
        said += problems.news(s)
        self.assertGreaterEqual(len(said), 4)
        for p in said:
            for line in (p['title'], p['detail'], p['fix']):
                self.assertIsNone(BANNED.search(line), line)
        self.assertIsNone(BANNED.search(ingest.HELD_REASON), 'the row says it plainly too')


if __name__ == '__main__':
    unittest.main()
