"""Taken care of: the goodbye, the morning and welcome back, "did I miss anything?", one sender folded into one item - and
the calm voice rule every line of it is held to (welcome.py, concierge.py, COUNSEL.md). Invented people only."""
import json, re, unittest
from datetime import datetime, timedelta
from pathlib import Path
from unittest import mock

from taskuary import concierge, counsel, desktop, funnel, general, lookups, toolcatalog, welcome
from taskuary.store import MemoryStore, task_ref

BANNED = ('agent', 'AI', 'model', 'brain', 'triage', 'pipe', 'FYI', 'lane', 'sync', 'session', 'connector', 'API', 'token',
          'device code', 'backlog', 'band', 'error', 'failed', 'retry', 'queue')
# the case-sensitive acronyms and the plain words, matched as words ("Payworth" never trips "pipe")
_BAN = re.compile(r'\b(' + '|'.join(re.escape(w) for w in BANNED if not w.isupper()) + r')s?\b', re.I)
_BAN_UP = re.compile(r'\b(' + '|'.join(w for w in BANNED if w.isupper()) + r')\b')
def banned(text):
    text = re.sub(r'#[\w-]+', '', text or '')                     # a page anchor is an address, not a word said
    return [m.group(0) for m in (*_BAN.finditer(text), *_BAN_UP.finditer(text))]

def stamp(d): return d.strftime('%Y-%m-%d %H:%M:%S')
def ago(hours=0, days=0, now=None): return stamp((now or datetime.now()) - timedelta(hours=hours, days=days))

def store():
    s = MemoryStore()
    for k in ('calendar_enabled', 'coder_auto_enabled', 'learn_enabled', 'auto_draft_enabled'): s.set_setting(k, '0', 't')
    s.set_setting('owner_email', 'alex@northwind.example', 't')
    return s

def mail(s, who, email, subject, sent, body='Hello', conv=None, tid=None, direction='in', status='routed'):
    return s.add_message({'TaskId': tid, 'ExternalId': f'x:{subject}:{sent}:{email}', 'ConversationId': conv or f'c:{subject}', 'Channel': 'email',
                          'Subject': subject, 'FromName': who, 'FromEmail': email, 'SentAt': sent, 'BodyText': body,
                          'Status': status, 'Direction': direction})

ITEMS = [{'key': 'msg:1', 'kind': 'asked', 'lane': 'asked', 'who': 'Erin Blake', 'title': 'Staffing sheet needed by noon'},
         {'key': 'msg:2', 'kind': 'review', 'lane': 'approve', 'who': 'Gail Moreno', 'title': 'Reply on the lease renewal'},
         {'key': 'msg:3', 'kind': 'todo', 'lane': 'yours', 'who': 'Paula Vance', 'title': 'Sign the vendor form'},
         {'key': 'msg:4', 'kind': 'fyi', 'lane': 'fyi', 'who': 'Payworth', 'title': 'Statement ready'}]


class VoiceTests(unittest.TestCase):
    """COUNSEL's calm rule, where the model learns it and where code speaks for itself."""
    def test_counsel_carries_the_rule_under_its_marker_and_the_brief_reads_it(self):
        t = (Path(counsel.__file__).parent / 'templates' / 'counsel.md').read_text(encoding='utf-8')
        self.assertIn(counsel.CALM_MARKER, t)
        for said in ('calmer than before they read it', "I've got it", 'device code', "nothing goes out until you say so"): self.assertIn(said, t)
        self.assertLessEqual(len(t), counsel.BUDGET)
        st = MemoryStore(); counsel.migrate(st)
        self.assertIn('calmer than before', counsel.for_brief(st)); self.assertIn('calmer than before', counsel.for_worker(st))

    def test_the_last_stock_release_is_replaced_and_an_owner_copy_gains_the_rule_once(self):
        old = (Path(counsel.__file__).parent / 'templates' / 'history' / 'counsel-0.3.7.10.md').read_text(encoding='utf-8')
        st = MemoryStore(); st.save_doc('counsel', old, 'owner')
        self.assertEqual(counsel.migrate(st), 'replaced'); self.assertIn(counsel.CALM_MARKER, st.get_doc('counsel'))
        mine = old.replace('## My goal', "## My goal\n- Alex's own goal.", 1)
        st = MemoryStore(); st.save_doc('counsel', mine, 'owner')
        self.assertEqual(counsel.migrate(st), 'appended')
        after = st.get_doc('counsel')
        self.assertIn("- Alex's own goal.", after); self.assertEqual(after.count(counsel.CALM_MARKER), 1)
        self.assertLess(after.index('## Voice'), after.index(counsel.CALM_MARKER))
        self.assertEqual(counsel.migrate(st), 'unchanged')

    def test_an_owner_copy_without_a_voice_heading_gets_one_at_the_end(self):
        st = MemoryStore(); st.save_doc('counsel', '# Mine\n\n## My goal\n- Finish.\n', 'owner')
        counsel.migrate(st)
        after = st.get_doc('counsel')
        self.assertIn('## Voice\n' + counsel.CALM_MARKER, after); self.assertIn('- Finish.', after)

    def test_the_lines_code_speaks_use_none_of_the_banned_words(self):
        lines = [v for k, v in concierge.RECEIPTS.items()] + [concierge.ALL_DONE, welcome.goodbye(store())]
        lines += [concierge.brain_trouble(Exception(e)) for e in ("maximum context length", '429 rate limit', '401 invalid key',
                                                                   'connection timed out', 'something odd')]
        lines += [concierge.fallback(None, False, ITEMS), concierge.fallback(None, False, ITEMS, brain=True), concierge.waiting_line(ITEMS)]
        lines += [concierge.fallback({**i, 'mid': n, 'channel': 'email', 'why': 'a notice'}, True) for n, i in enumerate(ITEMS, 1)]
        lines += [concierge.fallback({'kind': 'report', 'title': 'Weekly AR', 'bad': True, 'when': ago(1)}, False)]
        for line in lines: self.assertEqual(banned(line), [], line)

    def test_the_end_of_the_walk_is_nothings_waiting(self):
        self.assertEqual(concierge.ALL_DONE, "Nothing's waiting.")
        self.assertEqual(concierge.all_done(store()), "Nothing's waiting.")

    def test_the_end_of_the_walk_adds_a_promise_only_when_one_is_due_today(self):
        s, now = store(), datetime.now().replace(hour=9, minute=0)
        mail(s, 'Erin Blake', 'erin@northwind.example', 'Staffing sheet', ago(20, now=now), 'Can you send the staffing sheet?', conv='c1')
        mail(s, 'Alex Doyle', 'alex@northwind.example', 'RE: Staffing sheet', stamp(now.replace(hour=8)),
             "I'll send the staffing sheet today.", conv='c1', direction='out', status='sent')
        with mock.patch.object(welcome, 'datetime', mock.Mock(now=lambda: now)):
            line = welcome.promise_today(s, now)
        self.assertEqual(line, "You told Erin you'd send the staffing sheet today.")


class GoodbyeTests(unittest.TestCase):
    def test_the_goodbye_names_where_the_mail_waits(self):
        s = store(); s.save_connector({'Type': 'outlook', 'Name': 'Work mail', 'Active': 1}, 't')
        self.assertEqual(welcome.goodbye(s), "While I'm closed I can't watch your mail, but it waits safely in Outlook. "
                                             "I'll catch up the moment you open me.")
        self.assertIn("can't watch for anything new", welcome.goodbye(store()))

    def test_closing_writes_down_when(self):
        s = store(); now = datetime(2026, 10, 5, 18, 30)
        welcome.closing(s, now)
        self.assertEqual(welcome.last_here(s), now.replace(microsecond=0))

    def test_the_window_shows_the_goodbye_then_closes_itself(self):
        s, win = store(), mock.Mock()
        handler = desktop.closing_handler(win, lambda: s, secs=0)
        with mock.patch.object(desktop.threading, 'Thread') as th:
            self.assertFalse(handler())                                    # held for the goodbye
            th.call_args.kwargs['target']()
        self.assertIn("While I&#x27;m closed", win.load_html.call_args.args[0]); win.destroy.assert_called_once()
        self.assertTrue(handler())                                         # the second close goes straight through
        self.assertTrue(desktop.closing_handler(mock.Mock(), lambda: None)())   # nothing booted: nothing to say


class ArrivalTests(unittest.TestCase):
    def arrive(self, s, now, items=ITEMS):
        with mock.patch.object(funnel, 'pile', return_value={'items': items}):
            return welcome.arrive(s, now)

    def test_the_first_look_of_a_new_day_opens_with_the_night_and_three_things(self):
        s = store(); now = datetime.now().replace(hour=8, minute=0, second=0, microsecond=0)
        s.set_setting(welcome.CLOSED_KEY, ago(14, now=now), 't')
        for n in range(4): mail(s, 'Ray Colton', 'ray@northwind.example', f'Overnight {n}', ago(10 - n, now=now))
        items = [{**i, 'when': ago(5, now=now)} for i in ITEMS]
        out = self.arrive(s, now, items)
        self.assertTrue(out['said'].startswith('Good morning.'), out['said'])
        self.assertIn('Overnight: 4 came in, 3 need you.', out['said'])
        self.assertIn("Three things today, Erin's first: Staffing sheet needed by noon. Then Gail and Paula.", out['said'])
        self.assertIn("I'm holding the rest.", out['said'])
        self.assertEqual(banned(out['said']), [])
        turns = concierge.history(s, general.dock_task(s, 'owner')[0]['TaskId'])
        self.assertEqual(turns[-1]['text'], out['said']); self.assertEqual(turns[-1]['card']['kind'], 'brief')
        self.assertEqual(self.arrive(s, now + timedelta(minutes=5))['said'], '')        # once a day

    def test_a_fresh_install_and_a_second_look_the_same_morning_say_nothing(self):
        s = store(); now = datetime.now().replace(hour=9, minute=0)
        self.assertEqual(self.arrive(s, now)['said'], '')                               # nobody to welcome back yet
        self.assertEqual(self.arrive(s, now + timedelta(hours=1))['said'], '')          # same morning

    def test_back_after_sixteen_hours_the_same_day_is_welcome_back(self):
        s = store(); now = datetime.now().replace(hour=23, minute=0, second=0, microsecond=0)
        s.set_setting(welcome.SEEN_KEY, ago(17, now=now), 't'); s.set_setting(welcome.GREETED_KEY, now.strftime('%Y-%m-%d'), 't')
        said = self.arrive(s, now)['said']
        self.assertTrue(said.startswith('Welcome back.'), said); self.assertIn('While you were away: nothing new came in.', said)

    def test_after_a_weekend_it_says_what_was_settled_without_you(self):
        s = store(); now = datetime(2026, 10, 5, 8, 0)                                  # a Monday
        s.set_setting(welcome.SEEN_KEY, stamp(datetime(2026, 10, 2, 17, 0)), 't')      # Friday evening
        tid = s.create_task({'Title': 'Vendor W-9', 'Summary': 'x'}, 'agent:coder')
        s._exec("UPDATE task SET Status='done', ClosedAt=?, UpdatedBy='agent:coder' WHERE TaskId=?", (stamp(datetime(2026, 10, 3, 10, 0)), tid))
        said = self.arrive(s, now, [])['said']
        self.assertIn('Over the weekend: nothing new came in.', said); self.assertIn('One was settled without you.', said)
        self.assertIn('Nothing needs you yet.', said)

    def test_the_phone_hears_it_once_on_its_first_message_and_never_after_the_desk(self):
        s = store(); now = datetime.now().replace(hour=8, minute=0)
        s.set_setting(welcome.SEEN_KEY, ago(15, now=now), 't')
        with mock.patch.object(funnel, 'pile', return_value={'items': ITEMS}):
            first = welcome.phone_lead(s, now)
            again = welcome.phone_lead(s, now + timedelta(minutes=2))
        self.assertTrue(first.startswith('Good morning.')); self.assertEqual(again, '')
        self.assertEqual(self.arrive(s, now + timedelta(minutes=3))['said'], '')         # the desk does not say it twice

    def test_leaving_only_notes_the_time(self):
        s = store(); now = datetime.now().replace(hour=8, minute=0)
        s.set_setting(welcome.SEEN_KEY, ago(15, now=now), 't')
        self.assertEqual(welcome.arrive(s, now, leaving=True)['said'], '')
        self.assertEqual(welcome.last_here(s), now.replace(microsecond=0))


class MissedTests(unittest.TestCase):
    def test_did_i_miss_anything_is_a_look_up_with_the_answer_written_out(self):
        self.assertEqual(toolcatalog.valid('missed.check', {}), ''); self.assertIn('missed.check', lookups.READ)
        s = store()
        mail(s, 'Erin Blake', 'erin@northwind.example', 'Staffing sheet', ago(5), 'Could you send the staffing sheet?', conv='e1')
        mail(s, 'Payworth Billing', 'billing@payworth.example', 'Invoice 114', ago(days=4), 'Invoice attached.', conv='p1')
        mail(s, 'Alex Doyle', 'alex@northwind.example', 'RE: Invoice 114', ago(days=3), 'Can you confirm the remit address?',
             conv='p1', direction='out', status='sent')
        cid = s.save_connector({'Type': 'teams', 'Name': 'Teams', 'Active': 1}, 't')
        s._exec('UPDATE connector SET LastError=?, LastErrorAt=? WHERE ConnectorId=?', ('signed out', ago(1), cid))
        said = lookups.read(s, 'missed.check', {})
        self.assertIn('SAY IT LIKE THIS', said)
        answer = welcome.missed_says(welcome.missed(s))
        self.assertTrue(answer.startswith('Nothing urgent.'), answer)
        self.assertIn('One person is still waiting on an answer from you: Erin', answer)
        self.assertIn('Payworth still hasn\'t answered you about "Invoice 114"', answer)
        self.assertRegex(answer, r"I couldn't check Teams (this morning|today), so I can't vouch for that\.")
        self.assertEqual(banned(answer), [])

    def test_nothing_missed_says_so(self):
        self.assertEqual(welcome.missed_says(welcome.missed(store())),
                         "Nothing urgent. Nobody is waiting on you, and you aren't waiting on anybody.")


class RepeatsTests(unittest.TestCase):
    def test_one_sender_folded_onto_one_task_is_said_once_with_what_they_need_now(self):
        s = store()
        tid = s.create_task({'Title': 'Invoice 114 needs a W-9', 'Summary': 'Payworth needs a W-9 before paying invoice 114.'}, 'triage')
        ref = task_ref(tid)
        for n in range(5):
            mid = mail(s, 'Payworth Billing', 'billing@payworth.example', 'Invoice 114', ago(days=5 - n), f'Reminder {n}', conv=f'p{n}', tid=tid)
            if n: s.add_route(mid, tid, 'attach', 1.0, f'triage: asked - the same as {ref}, joined to it', [], 'triage',
                              verdict={'intent': 'asked', 'summary': 'All they need is the signed W-9. Nothing else is missing.'})
        got = concierge.repeats(s, tid)
        self.assertEqual(got['n'], 5)
        self.assertEqual(got['line'], 'Payworth Billing wrote five times about the same thing - every one is kept here. '
                                      'All they need now: All they need is the signed W-9.')

    def test_a_single_message_or_a_plain_conversation_is_not_a_repeat(self):
        s = store()
        tid = s.create_task({'Title': 'Lease', 'Summary': 'Gail asks about the lease.'}, 'triage')
        mail(s, 'Gail Moreno', 'gail@northwind.example', 'Lease', ago(3), 'Question', tid=tid)
        mail(s, 'Gail Moreno', 'gail@northwind.example', 'RE: Lease', ago(1), 'And another', tid=tid, conv='c:Lease')
        self.assertIsNone(concierge.repeats(s, tid))

    def test_the_task_page_carries_it(self):
        from fastapi.testclient import TestClient
        from taskuary import server
        s = store()
        tid = s.create_task({'Title': 'Invoice', 'Summary': 'They need the signed W-9.'}, 'triage')
        for n in range(2):
            mid = mail(s, 'Payworth Billing', 'billing@payworth.example', 'Invoice', ago(days=2 - n), f'R{n}', conv=f'q{n}', tid=tid)
            if n: s.add_route(mid, tid, 'attach', 1.0, f'triage: fyi, the same as {task_ref(tid)} - nothing new', [], 'triage')
        with mock.patch.object(server, 'store', s):
            got = TestClient(server.app).get(f'/api/tasks/{tid}').json()['repeats']
        self.assertEqual(got['line'], 'Payworth Billing wrote twice about the same thing - every one is kept here. All they need now: They need the signed W-9.')


if __name__ == '__main__': unittest.main()
