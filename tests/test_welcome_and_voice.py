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
    for k in ('calendar_enabled', 'coding_auto_enabled', 'auto_draft_enabled'): s.set_setting(k, '0', 't')
    s.set_setting('owner_email', 'alex@northwind.example', 't')
    return s

def mail(s, who, email, subject, sent, body='Hello', conv=None, tid=None, direction='in', status='routed'):
    return s.add_message({'TaskId': tid, 'ExternalId': f'x:{subject}:{sent}:{email}', 'ConversationId': conv or f'c:{subject}', 'Channel': 'email',
                          'Subject': subject, 'FromName': who, 'FromEmail': email, 'SentAt': sent, 'BodyText': body,
                          'Status': status, 'Direction': direction})

def asks(s, mid, intent='reply_only'):
    """Triage's stored verdict on an arrival - whether it asks is triage's call (route.VerdictJson), never its words."""
    s.add_route(mid, None, 'file', None, f'triage: {intent}', [], 'triage', verdict={'intent': intent, 'why': 'test'}); return mid

def judged(s, mid, conv, **said):
    """The sent-words judge's verdict on one of the owner's messages (sentjudge.py), as kept after a run."""
    s.put_sent_verdict(mid, conv, said.get('asks'), said.get('promise'), said.get('what', ''), said.get('due'), 'test'); return mid

def brain_ready(on=True): return mock.patch('taskuary.sentjudge.ready', return_value=on)

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
        # a button's own name is quoted, not said (U2: the line names the item's real buttons), and the one no-AI sentence is the
        # owner's own wording for the setup it points at (U3)
        quoted = sorted({*concierge.CHIP_WORDS.values(), concierge.NO_BRAIN, concierge.no_brain()}, key=len, reverse=True)
        def unquote(s):
            for w in quoted: s = s.replace(w, '')
            return s
        for line in lines: self.assertEqual(banned(unquote(line)), [], line)

    def test_the_end_of_the_walk_is_nothings_waiting(self):
        self.assertEqual(concierge.ALL_DONE, "Nothing's waiting.")
        self.assertEqual(concierge.all_done(store()), "Nothing's waiting.")

    def test_the_end_of_the_walk_adds_a_promise_only_when_one_is_due_today(self):
        s, now = store(), datetime.now().replace(hour=9, minute=0)
        mail(s, 'Erin Blake', 'erin@northwind.example', 'Staffing sheet', ago(20, now=now), 'Can you send the staffing sheet?', conv='c1')
        mid = mail(s, 'Alex Doyle', 'alex@northwind.example', 'RE: Staffing sheet', stamp(now.replace(hour=8)),
                   "I'll send the staffing sheet today.", conv='c1', direction='out', status='sent')
        with mock.patch.object(welcome, 'datetime', mock.Mock(now=lambda: now)):
            self.assertEqual(welcome.promise_today(s, now), '')                 # not read yet: no guess in its place
            judged(s, mid, 'c1', promise=True, what='send the staffing sheet', due=now.strftime('%Y-%m-%d'))   # the model's day
            line = welcome.promise_today(s, now)
            self.assertEqual(line, "You told Erin you'd send the staffing sheet today.")
            # their thanks does not deliver it - only a later word of the owner's the judge reads as delivering does
            mail(s, 'Erin Blake', 'erin@northwind.example', 'RE: Staffing sheet', stamp(now.replace(hour=8, minute=30)), 'Great, thanks!', conv='c1')
            self.assertEqual(welcome.promise_today(s, now), line)
            s.put_sent_verdict(mid, 'c1', False, True, 'send the staffing sheet', now.strftime('%Y-%m-%d'), 'test', delivered_by=mid + 1)
            self.assertEqual(welcome.promise_today(s, now), '')


class GoodbyeTests(unittest.TestCase):
    def test_the_goodbye_names_where_the_mail_waits(self):
        s = store(); s.save_connector({'Type': 'outlook', 'Name': 'Work mail', 'Active': 1}, 't')
        self.assertEqual(welcome.goodbye(s), "While I'm closed I can't watch what comes in, but it waits safely in Outlook and your other sources. "
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

    # Closing stopped every running agent three seconds after a goodbye that said "Nothing is lost" (B3, 2026-10-11)
    def working_store(self):
        from taskuary import terminal
        s = store(); tid = s.create_task({'Title': 'Fix the ledger export', 'Summary': 'x'}, 'owner')
        s.update_task(tid, {'Status': 'in_progress'}, 'agent:coding')
        idle = s.create_task({'Title': 'Not being worked', 'Summary': 'x'}, 'owner')
        s.update_task(idle, {'Status': 'in_progress'}, 'owner')                     # in progress, but no worker has it
        live = mock.Mock(task_id=tid, alive=True)
        return s, tid, mock.patch.dict(terminal.SESSIONS, {'s1': live}, clear=True)

    def test_the_goodbye_names_the_work_the_close_stops(self):
        s, tid, sessions = self.working_store()
        with sessions:
            self.assertEqual([t['TaskId'] for t in welcome.working(s)], [tid])
            said = welcome.goodbye(s)
        self.assertIn(f'Closing stops the work on {task_ref(tid)}', said); self.assertNotIn('Nothing is lost', said)
        self.assertEqual(banned(said), [])

    def test_with_work_running_the_close_asks_first_and_keep_working_goes_back(self):
        s, tid, sessions = self.working_store()
        win = mock.Mock(); win.get_current_url.return_value = 'http://127.0.0.1:7787/'
        with sessions, mock.patch.object(desktop.threading, 'Thread') as th:
            handler = desktop.closing_handler(win, lambda: s, secs=0)
            keep, anyway = win.expose.call_args.args
            self.assertFalse(handler())                                    # held: it asks
            th.call_args.kwargs['target'](*th.call_args.kwargs.get('args', ()))
            page = win.load_html.call_args.args[0]
            self.assertIn('Keep working', page); self.assertIn('Close anyway', page); self.assertIn(task_ref(tid), page)
            self.assertIsNone(welcome.last_here(s))                        # nothing closed yet
            keep()
            win.load_url.assert_called_once_with('http://127.0.0.1:7787/'); win.destroy.assert_not_called()
            self.assertFalse(handler())                                    # asks again on the next close
            th.call_args.kwargs['target'](*th.call_args.kwargs.get('args', ()))
            anyway()                                                       # ...and Close anyway says goodbye, then closes
            th.call_args.kwargs['target']()
        self.assertIn('Closing stops the work', win.load_html.call_args.args[0]); win.destroy.assert_called_once()
        self.assertIsNotNone(welcome.last_here(s))
        self.assertTrue(handler())

    def test_closing_again_while_it_asks_is_the_answer(self):
        s, tid, sessions = self.working_store()
        win = mock.Mock(); win.get_current_url.return_value = 'http://127.0.0.1:7787/'
        with sessions, mock.patch.object(desktop.threading, 'Thread') as th:
            handler = desktop.closing_handler(win, lambda: s, secs=0)
            self.assertFalse(handler()); th.call_args.kwargs['target'](*th.call_args.kwargs.get('args', ()))
            self.assertFalse(handler()); th.call_args.kwargs['target']()
        win.destroy.assert_called_once()

    def test_without_a_page_to_go_back_to_the_toolkits_own_box_asks(self):
        s, tid, sessions = self.working_store()
        win = mock.Mock(); win.get_current_url.return_value = None; win.create_confirmation_dialog.return_value = False
        with sessions, mock.patch.object(desktop.threading, 'Thread') as th:
            handler = desktop.closing_handler(win, lambda: s, secs=0)
            self.assertFalse(handler()); th.call_args.kwargs['target'](*th.call_args.kwargs.get('args', ()))
            self.assertIn('Cancel keeps it working', win.create_confirmation_dialog.call_args.args[1])
            win.destroy.assert_not_called()                                # Cancel: it stays open
            self.assertFalse(handler())                                    # ...and asks again next time


class ArrivalTests(unittest.TestCase):
    def arrive(self, s, now, items=ITEMS):
        with mock.patch.object(funnel, 'pile', return_value={'items': items}):
            return welcome.arrive(s, now)

    def test_the_first_look_of_a_new_day_opens_with_the_night_and_three_things(self):
        s = store(); now = datetime.now().replace(hour=8, minute=0, second=0, microsecond=0)
        now -= timedelta(days=max(0, now.weekday() - 4))     # a Saturday in the gap says "Over the weekend" - this is a weeknight
        s.set_setting(welcome.CLOSED_KEY, ago(14, now=now), 't')
        for n in range(4): mail(s, 'Ray Colton', 'ray@northwind.example', f'Overnight {n}', ago(10 - n, now=now))
        items = [{**i, 'when': ago(5, now=now)} for i in ITEMS]
        out = self.arrive(s, now, items)
        self.assertTrue(out['said'].startswith('Good morning.'), out['said'])
        self.assertIn('Overnight: 4 came in, 3 on you.', out['said'])
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
        tid = s.create_task({'Title': 'Vendor W-9', 'Summary': 'x'}, 'agent:coding')
        s._exec("UPDATE task SET Status='done', ClosedAt=?, UpdatedBy='agent:coding' WHERE TaskId=?", (stamp(datetime(2026, 10, 3, 10, 0)), tid))
        said = self.arrive(s, now, [])['said']
        self.assertIn('Over the weekend: nothing new came in.', said); self.assertIn('One was settled without you.', said)
        self.assertIn('Nothing needs you yet.', said)

    def test_a_stopped_agent_and_a_failed_check_need_you(self):
        # the morning after a close: what it stopped, and a check that broke, are the owner's on the rail - so they are here (B3)
        items = [{'key': 'agent:7', 'lane': 'stopped', 'kind': 'agent', 'who': '', 'title': 'Fix the ledger export'},
                 {'key': 'check:2', 'lane': 'broken', 'kind': 'check', 'who': '', 'title': 'Nightly build'},
                 {'key': 'msg:9', 'lane': 'theirs', 'kind': 'todo', 'who': 'Gail Moreno', 'title': 'Waiting on the lease'},
                 {'key': 'idea:1', 'lane': 'fyi', 'kind': 'idea', 'who': '', 'title': 'An idea'}]   # an unjudged idea is an fyi (idea_lane); slipped is the owner's since 2026-10-12
        self.assertEqual([i['key'] for i in welcome.needs_you(items)], ['agent:7', 'check:2'])
        self.assertTrue(welcome.three_things(items).startswith('Two things today'), welcome.three_things(items))
        self.assertEqual([i['key'] for i in welcome.needs_you(ITEMS)], ['msg:1', 'msg:2', 'msg:3'])

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
        asks(s, mail(s, 'Erin Blake', 'erin@northwind.example', 'Staffing sheet', ago(5), 'Could you send the staffing sheet?', conv='e1'))
        mail(s, 'Payworth Billing', 'billing@payworth.example', 'Invoice 114', ago(days=4), 'Invoice attached.', conv='p1')
        judged(s, mail(s, 'Alex Doyle', 'alex@northwind.example', 'RE: Invoice 114', ago(days=3), 'Can you confirm the remit address?',
                       conv='p1', direction='out', status='sent'), 'p1', asks=True)
        cid = s.save_connector({'Type': 'teams', 'Name': 'Teams', 'Active': 1}, 't')
        s._exec('UPDATE connector SET LastError=?, LastErrorAt=? WHERE ConnectorId=?', ('signed out', ago(1), cid))
        with brain_ready():
            said = lookups.read(s, 'missed.check', {})
            answer = welcome.missed_says(welcome.missed(s))
        self.assertIn('SAY IT LIKE THIS', said)
        self.assertTrue(answer.startswith('Nothing urgent.'), answer)
        self.assertIn('One person is still waiting on an answer from you: Erin', answer)
        self.assertIn('Payworth still hasn\'t answered you about "Invoice 114"', answer)
        # an hour ago is yesterday in the first hour after midnight (CI runs on UTC)
        self.assertRegex(answer, r"I couldn't check Teams (this morning|today|since yesterday), so I can't vouch for that\.")
        self.assertEqual(banned(answer), [])

    def test_nothing_missed_says_so(self):
        with brain_ready():
            self.assertEqual(welcome.missed_says(welcome.missed(store())),
                             "Nothing urgent. Nobody is waiting on you, and you aren't waiting on anybody.")

    def test_with_nothing_to_read_with_it_says_so_instead_of_nobody(self):
        # no AI: promises and asks of the owner's cannot be read, so "you aren't waiting on anybody" would be a guess (2026-10-11)
        with brain_ready(False): answer = welcome.missed_says(welcome.missed(store()))
        self.assertEqual(answer, "Nothing urgent. Nobody is waiting on you. Nothing reads your sent mail for me yet, so I can't keep "
                                 "track of what you promised or asked people for.")
        self.assertEqual(banned(answer), [])

    def test_a_message_triage_never_judged_is_said_never_counted_as_nobody(self):
        s = store()
        mail(s, 'Erin Blake', 'erin@northwind.example', 'Invoice', ago(5), 'Please approve the invoice.', conv='e1', status='error')
        with brain_ready(): answer = welcome.missed_says(welcome.missed(s))
        self.assertNotIn('Nobody is waiting on you', answer)
        self.assertIn("I couldn't judge one message - from Erin - so I can't say whether it asks you anything.", answer)
        self.assertEqual(banned(answer), [])


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


class CatchUpTests(unittest.TestCase):
    """The greeting waits for the startup catch-up (B4, 2026-10-11): on a Monday it fired while the weekend's mail was still being
    read, said "Over the weekend: nothing new came in", spent itself, and was never corrected."""
    def setUp(self): welcome._CATCHUP.clear(); welcome._HELD.clear()
    tearDown = setUp

    def arrive(self, s, now, items=ITEMS, **kw):
        with mock.patch.object(funnel, 'pile', return_value={'items': items}):
            return welcome.arrive(s, now, **kw)

    def test_a_greeting_asked_for_mid_catch_up_is_drawn_at_once_then_filled_in_its_place(self):
        s = store(); now = datetime(2026, 10, 5, 8, 0)                                  # a Monday
        s.set_setting(welcome.SEEN_KEY, stamp(datetime(2026, 10, 2, 17, 0)), 't')      # Friday evening
        with mock.patch.object(welcome.threading, 'Timer'): welcome.catch_up_began(now)
        out = self.arrive(s, now, [])
        self.assertEqual((out['said'], out.get('pending'), out.get('drawn')), ('', True, True))
        self.assertNotEqual(s.get_setting(welcome.GREETED_KEY), '2026-10-05', 'a held greeting is not spent')
        tid = general.dock_task(s, 'owner')[0]['TaskId']
        self.assertTrue(concierge.history(s, tid)[-1]['card']['reading'], 'the opener is up at once, marked reading')
        self.assertNotIn('drawn', self.arrive(s, now + timedelta(seconds=10), []), 'drawn once')
        concierge.record(s, tid, 'user', 'Walk me through my tasks')                    # the owner starts walking meanwhile
        self.arrive(s, now + timedelta(seconds=20), leaving=True)                     # a blur meanwhile cannot shrink the gap
        for n in range(3): mail(s, 'Erin Blake', 'erin@northwind.example', f'Weekend {n}', stamp(datetime(2026, 10, 3, 9 + n)))
        with mock.patch('taskuary.live.emit') as emit: welcome.catch_up_ended()
        emit.assert_called_once_with('arrive')
        said = self.arrive(s, now + timedelta(minutes=2))['said']
        self.assertIn('Over the weekend: 3 came in', said)
        turns = concierge.history(s, tid)
        self.assertEqual([(t.get('card') or {}).get('kind') for t in turns], ['brief', None], 'filled where it stood - above the walk')
        card = turns[0]['card']
        self.assertTrue(card['away'].startswith('Over the weekend: 3 came in'), 'the opening card draws the gap')
        self.assertNotIn('reading', card)
        self.assertEqual(self.arrive(s, now + timedelta(minutes=9))['said'], '')        # and then it is spent

    def test_a_catch_up_that_outlives_the_wait_is_said_honestly(self):
        s = store(); now = datetime(2026, 10, 5, 8, 0)
        s.save_connector({'Type': 'outlook', 'Name': 'Work mail', 'Active': 1}, 't')
        s.set_setting(welcome.SEEN_KEY, stamp(datetime(2026, 10, 2, 17, 0)), 't')
        with mock.patch.object(welcome.threading, 'Timer'): welcome.catch_up_began(now)
        self.assertTrue(self.arrive(s, now, [])['pending'])
        said = self.arrive(s, now + timedelta(seconds=welcome.CATCHUP_WAIT + 5), [])['said']
        self.assertIn("I'm still reading Outlook", said); self.assertEqual(banned(said), [])


class AwayWindowTests(unittest.TestCase):
    """One "while you were away" for every reader (B5, 2026-10-11): the greeting, the opening screen, "did I miss anything?" and
    the Morning digest all count from when the owner was last here - not from six last evening, not from two days back."""
    def setUp(self): welcome._CATCHUP.clear(); welcome._HELD.clear()

    def test_a_nine_day_absence_is_not_the_weekend(self):
        self.assertEqual(welcome.away_word(datetime(2026, 9, 26, 17, 0), datetime(2026, 10, 5, 8, 0)), 'Over the last nine days')
        self.assertEqual(welcome.away_word(datetime(2026, 10, 2, 17, 0), datetime(2026, 10, 5, 8, 0)), 'Over the weekend')

    def test_the_window_is_since_last_here_and_never_past_three_weeks(self):
        s, now = store(), datetime(2026, 10, 5, 8, 0)
        self.assertEqual(welcome.away_window(s, now), (datetime(2026, 10, 4, 18, 0), 'Since last night'))   # nobody here before
        s.set_setting(welcome.SEEN_KEY, stamp(datetime(2026, 10, 2, 17, 0)), 't')
        self.assertEqual(welcome.away_window(s, now), (datetime(2026, 10, 2, 17, 0), 'Over the weekend'))
        s.set_setting(welcome.SEEN_KEY, stamp(datetime(2026, 6, 1, 9, 0)), 't')
        self.assertEqual(welcome.away_window(s, now)[0], now - timedelta(days=welcome.AWAY_MAX_DAYS))

    def test_the_greeted_gap_holds_all_day_after_the_greeting(self):
        s = store(); now = datetime.now().replace(hour=8, minute=0, second=0, microsecond=0)
        gone = now - timedelta(days=3, hours=15)
        s.set_setting(welcome.SEEN_KEY, stamp(gone), 't')
        with mock.patch.object(funnel, 'pile', return_value={'items': []}): self.assertTrue(welcome.arrive(s, now)['said'])
        s.set_setting(welcome.ACTIVE_KEY, stamp(now + timedelta(hours=1, minutes=50)), 't')        # pressing Next since
        self.assertEqual(welcome.away_window(s, now + timedelta(hours=2))[0], gone, 'the opening screen counts the gap it greeted')
        # ...while they are still at it: two hours with nothing pressed is an away of its own, from the last press
        self.assertEqual(welcome.away_window(s, now + timedelta(hours=4))[0], now + timedelta(hours=1, minutes=50))

    def test_a_day_of_presses_is_not_away_since_the_small_hours(self):
        """The bug: greeted at 8 for a gap from 2:05 AM, then busy all day - at eleven at night the card still read
        "While you were away · since 2:05 AM". Away is where the latest silence of AWAY_MINUTES began."""
        s = store(); day = datetime(2026, 10, 22)
        s.set_setting(welcome.SEEN_KEY, stamp(day.replace(hour=2, minute=5)), 't')
        with mock.patch.object(funnel, 'pile', return_value={'items': []}): self.assertTrue(welcome.arrive(s, day.replace(hour=8))['said'])
        self.assertEqual(welcome.away_window(s, day.replace(hour=8, minute=5))[0], day.replace(hour=2, minute=5), 'away overnight: since last night')
        t = day.replace(hour=8)
        while t < day.replace(hour=22, minute=50):               # a press every twenty minutes, an hour's dinner at six
            if not (18 <= t.hour < 19): welcome.touch(s, t)
            t += timedelta(minutes=20)
        start, word = welcome.away_window(s, day.replace(hour=22, minute=57))
        self.assertEqual((start, word), (day.replace(hour=17, minute=40), 'While you were away'), 'the dinner hour, not 2:05 AM')
        from taskuary import since
        self.assertEqual(since.overnight(s, day.replace(hour=22, minute=57))['heading'], 'While you were away · since Thu 5:40 PM')

    def test_presence_survives_a_restart_and_a_press_never_spends_the_greeting(self):
        s = store(); now = datetime(2026, 10, 22, 8, 0)
        s.set_setting(welcome.SEEN_KEY, stamp(now - timedelta(hours=6)), 't')
        welcome.touch(s, now)                                      # a click that beat the window's arrive
        self.assertEqual(s.get_setting(welcome.AWAY_KEY), stamp(now - timedelta(hours=6)))
        self.assertEqual(s.get_setting(welcome.ACTIVE_KEY), stamp(now), 'in the store, so a restart keeps it')
        self.assertEqual(welcome.due(s, now)[0], True, 'the morning greeting is still due')
        welcome.touch(s, now + timedelta(seconds=30))
        self.assertEqual(s.get_setting(welcome.ACTIVE_KEY), stamp(now), 'a write a minute')

    def test_monday_did_i_miss_anything_reaches_back_to_friday(self):
        s = store(); now = datetime.now()
        s.set_setting(welcome.SEEN_KEY, ago(70, now=now), 't')                       # gone since Friday afternoon
        asks(s, mail(s, 'Erin Blake', 'erin@northwind.example', 'Staffing sheet', ago(66, now=now), 'Could you send the staffing sheet?', conv='e1'))
        answer = welcome.missed_says(welcome.missed(s, now))
        self.assertIn('One person is still waiting on an answer from you: Erin', answer)

    def test_the_morning_brief_reads_from_when_the_owner_was_last_here(self):
        from taskuary import digest
        s = store(); gone = datetime.now().replace(microsecond=0) - timedelta(days=3, hours=15)
        s.set_setting(welcome.SEEN_KEY, stamp(gone), 't')
        self.assertIn(f"the window is since {stamp(gone)[:16]}", digest.gather(s, 1))


class PresenceTests(unittest.TestCase):
    """Presence is written in one place (welcome.touch), from what the owner actually does over the API."""

    def test_an_owner_press_is_presence_and_a_poll_or_an_agent_is_not(self):
        from fastapi.testclient import TestClient
        from taskuary import config, server
        c, agent = TestClient(server.app), {'X-Taskuary-Token': config.load()['server']['agent_token']}
        with mock.patch.object(welcome, 'touch') as t:
            c.get('/api/since'); c.post('/api/board/notes', json={'body': 'taking store.py'}, headers=agent)
            self.assertEqual(t.call_count, 0, 'a poll and an agent are not the owner')
            self.assertEqual(c.post('/api/board/notes', json={'body': 'a note'}).status_code, 200)
            self.assertEqual(t.call_count, 1)
            c.post('/api/concierge/arrive', json={'leaving': True})
            self.assertEqual(t.call_count, 1, 'arrive keeps its own book')

    def test_a_press_never_waits_on_a_held_store_lock(self):
        """The middleware ran on the event loop: a sync holding store.lock held every request behind one presence write."""
        import asyncio, threading, time
        from starlette.requests import Request
        from starlette.responses import Response
        from taskuary import server
        s, held, done = MemoryStore(), threading.Event(), threading.Event()
        def hold():
            with s.lock: held.set(); done.wait(10)
        threading.Thread(target=hold, daemon=True).start(); held.wait(5)
        async def ok(_): return Response(status_code=200)
        own = [(b'x-taskuary-token', str(server.cfg['server'].get('token') or '').encode())]
        req = Request({'type': 'http', 'method': 'POST', 'path': '/api/board/notes', 'query_string': b'', 'headers': own})
        try:
            with mock.patch.object(server, 'store', s):
                t0 = time.perf_counter(); r = asyncio.run(server.owner_presence(req, ok)); took = time.perf_counter() - t0
        finally: done.set()
        self.assertEqual(r.status_code, 200)
        self.assertLess(took, 0.5, 'the press answered without waiting for the lock')
        self.assertIsNone(s.get_setting(welcome.ACTIVE_KEY), 'nothing written under a lock somebody else holds')
        self.assertIsNotNone(welcome.last_active(s), 'but the press already counts as presence')
        self.assertTrue(welcome.flush(s))
        self.assertIsNotNone(s.get_setting(welcome.ACTIVE_KEY), 'written once the lock is free')

    def test_a_kept_press_is_written_in_order_before_a_later_one(self):
        """Kept presses go through touch oldest first, so where an away began is what it was when written inline."""
        s, day = store(), datetime(2026, 10, 22)
        s.set_setting(welcome.SEEN_KEY, stamp(day.replace(hour=8)), 't')
        s._presses = [day.replace(hour=10)]                     # a press kept while a sync held the lock
        welcome.touch(s, day.replace(hour=10, minute=5))
        self.assertEqual(s.get_setting(welcome.AWAY_KEY), stamp(day.replace(hour=8)), 'the 8-to-10 silence, from the kept press')
        self.assertEqual(s.get_setting(welcome.ACTIVE_KEY), stamp(day.replace(hour=10, minute=5)))
        self.assertFalse(s.__dict__['_presses'])


if __name__ == '__main__': unittest.main()
