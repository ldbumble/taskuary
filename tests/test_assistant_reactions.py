"""Every kind of thing that ARRIVES, and every kind of thing the owner SAYS BACK - end to end.

The point is not that the words come out nicely: it is that something actually happened. Every case
here asserts the effect - a task created with the right kind, an agent dispatched (or deliberately
not), a review waiting, a message filed onto a chain, a lane in the pipe, a standing rule written, a
task closed, a session stopped, one arrival broken into two. The brain is a lambda throughout, so a
failure here is Taskuary's, never a model's.

Read it as a matrix:

    ARRIVALS   coding ask · reply-only question · fyi · a follow-up on an open task · a chat burst ·
               a second ask in one chat · a report that landed · a report that FAILED · an agent
               asking · an agent that finished · a meeting inside two hours · an auto-reply ·
               general (non-coding) work · a person's own task · an urgent sender · a muted family

    RESPONSES  next · done · later · tomorrow · reply (with the gist) · approve · not ours ·
               never again · that sender is noise · remember X · send it to the coder · I'll do it ·
               close the task · stop the agent · wrap it up · rerun the report · sweep them away ·
               split it in two · set something up · a correction · a question · a lookup
"""
import json, os, unittest
from datetime import datetime, timedelta
from unittest import mock

from fastapi.testclient import TestClient

from taskuary import concierge, funnel, general, ingest, server, terminal
from taskuary.store import MemoryStore


def ago(hours=0, minutes=0, days=0):
    return (datetime.now() - timedelta(hours=hours, minutes=minutes, days=days)).strftime('%Y-%m-%d %H:%M:%S')


def ahead(minutes=0):
    return (datetime.now() + timedelta(minutes=minutes)).strftime('%Y-%m-%d %H:%M:%S')


def store():
    s = MemoryStore()
    s.upsert_agent('coder', 'coding', 'cli', '{}')         # an install has one; without it a hand-off is refused
    for k in ('calendar_enabled', 'learn_enabled', 'auto_draft_enabled'): s.set_setting(k, '0', 't')
    s.set_setting('coder_auto_enabled', '1', 't')          # the funnel of record: work reaches an agent
    s.set_setting('team_domains', 'ours.com', 't')
    s.set_setting('owner_email', 'owner@ours.com', 't')
    funnel.invalidate(); funnel.forget_states(); funnel._SOURCES.update(at=0.0, by={})
    return s


def brain(intent='task', kind='coding', why='because', playbook=None):
    """Triage's answer, scripted."""
    def llm(system, user, **kw):
        out = {'intent': intent, 'why': why}
        if intent == 'task' and kind: out['kind'] = kind
        if playbook: out['playbook'] = playbook
        return json.dumps(out)
    return llm


def arrive(s, subject='Can you fix the export?', body='The nightly export drops inter-company rows.',
           who='Craig Neiswanger', email='craig@vendor.com', channel='email', conv=None, hours=1,
           llm=None, to=('owner@ours.com',), **kw):
    """One message through the front door, exactly as a connector delivers it."""
    msg = {'external_id': f'x:{subject}:{hours}:{channel}', 'channel': channel, 'conversation_id': conv or f'c:{subject}',
           'subject': subject, 'from_name': who, 'from_email': email, 'sent_at': ago(hours), 'body': body,
           'to': list(to), 'source_name': 'owner@ours.com', **kw}
    return ingest.ingest_message(s, msg, llm=llm if llm is not None else brain())


def pile(s, live=()):
    with mock.patch.object(terminal, 'live_sessions', return_value=list(live)):
        return funnel.build(s)['items']


def lanes(s, live=()):
    return [(i['kind'], i['lane']) for i in pile(s, live)]


def say(s, text, key=None, model='never asked', live=()):
    with mock.patch.object(terminal, 'live_sessions', return_value=list(live)):
        return concierge.say(s, text, key=key, llm=lambda *a, **k: model)


def surface(s, key=None, live=()):
    with mock.patch.object(terminal, 'live_sessions', return_value=list(live)):
        return concierge.surface(s, key, llm=lambda *a, **k: 'never asked')


def session(tid, **kw):
    base = {'taskId': tid, 'sid': f's{tid}', 'agent': 'coder', 'label': 'coder', 'started': ago(hours=1),
            'idle': 2, 'waiting': False, 'tail': ['reading…']}
    return [{**base, **kw}]


# ── what arrives, and where it lands ─────────────────────────────────────────────────────────
class ArrivalsTests(unittest.TestCase):
    def test_a_coding_ask_becomes_a_task_and_a_known_sender_reaches_an_agent(self):
        s = store()
        with mock.patch.object(ingest, '_spawn') as spawn:
            out = arrive(s, llm=brain('task', 'coding'))                # a stranger's first mail
        self.assertEqual(out['status'], 'created')
        t = s.get_task(out['task_id'])
        self.assertEqual((t['Kind'], t['Status']), ('coding', 'open'))
        self.assertFalse(spawn.called)                                  # …held on purpose: nobody has ever written to them
        self.assertIn('first message from', s.list_routes(out['task_id'])[-1]['Reason'])
        self.assertEqual(lanes(s), [('todo', 'asked')])                 # it waits on the owner instead
        # …and a colleague's ask does start one
        with mock.patch.object(ingest, '_spawn') as spawn:
            arrive(s, subject='Fix the payroll import', body='It crashes on every file.', who='Chana',
                   email='chana@ours.com', conv='c:payroll', hours=2, llm=brain('task', 'coding'))
        self.assertTrue(spawn.called, 'a known colleague is auto-worked')

    def test_a_question_becomes_a_reply_waiting_for_the_owners_yes(self):
        s = store()
        out = arrive(s, subject='Are you around Tuesday?', body='Quick call?', llm=brain('reply_only', None))
        t = s.get_task(out['task_id'])
        self.assertEqual(t['Kind'], 'reply')
        rv = s.pending_review(out['task_id'])
        self.assertIsNotNone(rv, 'a reply task always enters the review queue')
        self.assertEqual([(i['kind'], i['lane'], i['draft']) for i in pile(s)], [('review', 'approve', False)])

    def test_fyi_and_marketing_are_filed_but_stay_unread_until_the_owner_clears_them(self):
        s = store()
        promo = arrive(s, subject='Monthly newsletter', body='News from us', who='Marketing',
                       email='news@vendor.com', llm=brain('fyi', None, 'a newsletter'))
        self.assertEqual((promo['status'], promo['task_id']), ('filed', None))
        self.assertEqual([(i['kind'], i['category']) for i in pile(s)], [('fyi', 'promo')])
        person = arrive(s, subject='FYI - Rebecca is back Tuesday', body='Just so you know.', who='Chana',
                        email='chana@ours.com', conv='c:fyi', hours=2, llm=brain('fyi', None, 'telling you something'))
        self.assertEqual(person['status'], 'filed')
        self.assertEqual(lanes(s), [('fyi', 'fyi'), ('fyi', 'fyi')])    # both are unread; the category still ranks/explains them

        robot = arrive(s, subject='Backup completed', body='This is an automated notification.', who='System',
                       email='noreply@vendor.com', conv='c:robot', hours=0, llm=brain('fyi', None, 'system notice'))
        self.assertEqual(robot['status'], 'filed')
        self.assertEqual([i['category'] for i in pile(s)], ['info', 'promo', 'automated'])

    def test_an_assistant_timeline_post_is_unread_too(self):
        s = store()
        s.add_message({'ExternalId': 'assistant:1', 'ConversationId': 'assistant', 'Channel': 'assistant',
                       'SourceName': 'Assistant', 'Subject': 'Gabi sent a new requirement', 'FromName': 'Assistant',
                       'SentAt': ago(), 'BodyText': 'I would add this to the spec.', 'Status': 'feed'})
        self.assertEqual([(i['kind'], i['category'], i['title']) for i in pile(s)],
                         [('fyi', 'assistant', 'Gabi sent a new requirement')])

    def test_general_work_opens_a_conversation_and_starts_no_coder(self):
        s = store()
        with mock.patch.object(ingest, '_spawn') as spawn:
            out = arrive(s, subject='Which vendor should we pick?', body='Weigh these two quotes for me.',
                         llm=brain('task', 'general'))
        self.assertEqual(s.get_task(out['task_id'])['Kind'], 'general')
        self.assertFalse(spawn.called, 'general work is a conversation, not a checkout')

    def test_a_persons_own_task_lands_on_their_list_with_nobody_on_it(self):
        s = store()
        with mock.patch.object(ingest, '_spawn') as spawn:
            out = arrive(s, subject='Compliance training due 9/12', body='Please complete the course.',
                         who='HR', email='hr@ours.com', llm=brain('task', 'task'))
        self.assertEqual(s.get_task(out['task_id'])['Kind'], 'task')
        self.assertFalse(spawn.called)
        self.assertEqual(lanes(s), [('todo', 'asked')])

    def test_an_urgent_sender_jumps_the_queue(self):
        s = store()
        s.save_policy({'Name': 'boss', 'Kind': 'sender', 'Pattern': 'hindy@ours.com', 'Action': 'escalate',
                       'Reason': 'the CFO', 'SortOrder': 10, 'Active': 1}, 'o')
        with mock.patch.object(ingest, '_spawn'):
            arrive(s, subject='Board numbers', body='Need the deck fixed today.', who='Hindy', email='hindy@ours.com',
                   llm=brain('task', 'coding'))
        self.assertEqual(lanes(s), [('todo', 'time')])                  # 'coming up', ahead of ordinary asks

    def test_an_auto_reply_is_nobody_asking_anything(self):
        s = store()
        arrive(s, subject='Automatic reply: out of office', body='Back Monday.', who='Rebecca',
               email='rebecca@ours.com', llm=brain('fyi', None))
        self.assertEqual(pile(s), [])

    def test_a_report_that_landed_and_one_that_failed_read_differently(self):
        s = store()
        sid = s.save_source({'Channel': 'report', 'Address': 'Nightly export', 'Owner': 'o', 'Active': 1,
                             'ConfigJson': json.dumps({'type': 'agent', 'title': 'Nightly export'})}, 'o')
        s.add_report_run(sid, {'at': ago(1), 'type': 'agent', 'title': 'Nightly export', 'failed': 0})
        ok = s.add_message({'ExternalId': 'r-ok', 'Channel': 'report', 'SourceName': 'Nightly export',
                            'Subject': 'Nightly export - 0 errors', 'FromName': 'Nightly export', 'SentAt': ago(1),
                            'BodyText': 'all clear', 'Status': 'feed'})
        s.add_route(ok, None, 'feed', None, 'a report you set up', [], 'feed')
        got = {i['title']: i for i in pile(s)}
        self.assertFalse(got['Nightly export - 0 errors']['bad'])
        s.add_report_run(sid, {'at': ago(0), 'type': 'agent', 'title': 'Nightly export', 'failed': 1, 'error': 'timed out'})
        funnel._SOURCES.update(at=0.0, by={})
        bad = s.add_message({'ExternalId': 'r-bad', 'Channel': 'report', 'SourceName': 'Nightly export',
                             'Subject': 'Nightly export — FAILED', 'FromName': 'Nightly export', 'SentAt': ago(0),
                             'BodyText': 'error: timed out', 'Status': 'feed'})
        s.add_route(bad, None, 'feed', None, 'a report you set up', [], 'feed')
        funnel.invalidate()
        got = {i['title']: i for i in pile(s)}
        self.assertTrue(got['Nightly export — FAILED']['bad'])
        self.assertIn('the check failed', got['Nightly export — FAILED']['why'])

    def test_a_meeting_inside_two_hours_is_time_sensitive_and_interrupts(self):
        s = store()
        s.set_setting('calendar_enabled', '1', 't')
        ev = {'events': [{'subject': 'Payroll cutover', 'start': ahead(10), 'end': ahead(40), 'who': ['Chana'],
                          'all_day': False, 'where': 'Teams', 'id': 'ev1'}]}
        # funnel imports _agenda by name, so that is the one to stand in for
        with mock.patch.object(funnel, '_agenda', return_value=ev['events']):
            items = pile(s)
            self.assertEqual([(i['kind'], i['lane']) for i in items], [('meeting', 'time')])
            alerts = funnel.alerts(s, items)
        self.assertEqual([a['kind'] for a in alerts], ['meeting'])
        self.assertIn('starts in', alerts[0]['text'])

    def test_a_follow_up_on_an_open_task_is_judged_not_inherited(self):
        s = store()
        with mock.patch.object(ingest, '_spawn'):
            first = arrive(s, conv='c:pto', subject='PTO import', body='Please import the August PTO.',
                           who='Chana', email='chana@hrtgcs.com', hours=6, llm=brain('task', 'coding'))
        tid = first['task_id']
        s.add_message({'TaskId': tid, 'ExternalId': 'x:mine', 'ConversationId': 'c:pto', 'Channel': 'email',
                       'Subject': 'RE: PTO import', 'FromName': 'You', 'FromEmail': 'owner@ours.com',
                       'SentAt': ago(2), 'BodyText': 'Done - all 80 files posted.', 'Status': 'context'})
        thanks = ingest.ingest_message(s, {'external_id': 'x:ta', 'channel': 'email', 'conversation_id': 'c:pto',
                                           'subject': 'RE: PTO import', 'from_name': 'Chana', 'from_email': 'chana@hrtgcs.com',
                                           'sent_at': ago(0), 'body': 'Thank you!'},
                                          llm=brain('fyi', None, 'only says thanks'))
        self.assertEqual((thanks['status'], thanks['task_id']), ('filed', tid))
        self.assertEqual(s.get_message(thanks['message_id'])['Status'], 'filed')     # on the chain, off the pile
        self.assertEqual(lanes(s), [('wrapup', 'report')])                            # your reply went out: close it?

    def test_a_chat_burst_is_one_thought_and_a_new_ask_is_its_own_task(self):
        s = store()

        def line(body, mins, same=True):
            def llm(system, user, **kw):
                # the room reader answers same/why; triage answers intent/kind - one brain, two questions
                if 'SAME' in system: return json.dumps({'same': same, 'why': 'the reader says so'})
                return json.dumps({'intent': 'task', 'kind': 'coding', 'why': 'an ask'})
            return ingest.ingest_message(
                s, {'external_id': f'wa:{mins}', 'channel': 'whatsapp', 'conversation_id': 'wa:gabi',
                    'subject': 'WhatsApp with Gabi', 'from_name': 'Gabi', 'from_email': None,
                    'sent_at': ago(minutes=mins), 'body': body, 'source_name': 'Gabi'}, llm=llm)
        with mock.patch.object(ingest, '_spawn'):
            a = line('the dashboard agent is not running', 40)
            b = line('i mean the new one', 39)                       # seconds later: one thought, two messages
            c = line('also, can you add Copilot to my mail?', 5, same=False)
        self.assertEqual(a['status'], 'created')
        self.assertEqual(b['task_id'], a['task_id'])
        self.assertEqual(c['status'], 'created'); self.assertNotEqual(c['task_id'], a['task_id'])
        self.assertEqual(len(s.list_tasks()), 2)

    def test_an_agent_asking_blocks_and_an_agent_finishing_offers_its_report(self):
        s = store()
        with mock.patch.object(ingest, '_spawn'):
            out = arrive(s, llm=brain('task', 'coding'))
        tid = out['task_id']
        s.update_task(tid, {'Status': 'in_progress'}, 'router')
        dwell = mock.patch.object(funnel, 'DWELL', 0); dwell.start(); self.addCleanup(dwell.stop)
        with mock.patch.object(terminal, 'live_sessions', return_value=session(tid)):
            funnel.announce(s)                                         # working: remembered
            self.assertEqual(lanes(s, session(tid)), [('todo', 'working')])
        asking = session(tid, idle=200, waiting=True, tail=['Remove the old rows too? (y/n)'])
        with mock.patch.object(terminal, 'live_sessions', return_value=asking):
            ev = funnel.announce(s)
            self.assertEqual([e['kind'] for e in ev], ['asking'])
            self.assertEqual(lanes(s, asking), [('agent', 'blocked')])
            self.assertEqual(funnel.alerts(s, funnel.build(s)['items'])[0]['kind'], 'agent')
        s.add_comment(tid, 'coder', 'agent', 'CODER REPORT' + chr(10) + 'Summary: fixed the export and deployed.')
        s.update_task(tid, {'Status': 'done'}, 'coder')
        with mock.patch.object(terminal, 'live_sessions', return_value=[]):
            ev = funnel.announce(s)
        self.assertEqual([e['kind'] for e in ev], ['done'])
        self.assertIn('fixed the export', ev[0]['text'])
        self.assertIn('task is closed', ev[0]['text'])
        self.assertIsNone(ev[0]['card'])

    def test_a_family_the_owner_muted_never_comes_back(self):
        s = store()
        for n in range(2):
            out = arrive(s, subject=f'MFA Financial Report - .0{n}', body='from Intacct', who='Nechama Ozur',
                         email='nozur@hrtgcs.com', hours=n + 1, llm=brain('fyi', None))
            self.assertEqual(out['status'], 'filed')
        self.assertEqual(len(pile(s)), 2)
        funnel.remember_mute(s, {'sender': 'nozur@hrtgcs.com', 'words': ['mfa', 'financial'], 'why': 'the financials process'}, 'o')
        p = funnel.build(s)
        self.assertEqual((p['items'], p['muted']), ([], 2))
        # ...and the same sender asking something real still gets through
        with mock.patch.object(ingest, '_spawn'):
            arrive(s, subject='MFA Financial Report - can you re-run .02?', body='please re-run it',
                   who='Nechama Ozur', email='nozur@hrtgcs.com', hours=0, llm=brain('task', 'coding'))
        self.assertEqual([i['lane'] for i in pile(s)], ['asked'])


# ── what the owner says back, and what actually happens ──────────────────────────────────────
class WrongThreadTests(unittest.TestCase):
    """A reply must join ITS OWN thread's task, or open a new one - never a third task that merely
    looks similar. It did: "RE: July 2026 Financials" landed on the PointClickCare task after the
    financials task closed, and the reply drafted for that task was about the financials (the owner,
    2026-09-03: "the reply was about another task? How does this happen. really bad????")."""

    def _two_tasks(self, s):
        with mock.patch.object(ingest, '_spawn'):
            fin = arrive(s, subject='July 2026 Financials', conv='c:fin', hours=6, who='Hindy Spiegel',
                         email='hindy@hrtgcs.com', body='Please send the July financial package to the VPO list.',
                         llm=brain('task', 'coding'))
            pcc = arrive(s, subject='PointClickCare custom data extract', conv='c:pcc', hours=5, who='Hindy Spiegel',
                         email='hindy@hrtgcs.com', body='Compass needs a sample of the PointClickCare AR extract we consume.',
                         llm=brain('task', 'coding'))
        return fin['task_id'], pcc['task_id']

    def _reply_on_the_financials_thread(self, s):
        return ingest.ingest_message(s, {'external_id': 'x:fin2', 'channel': 'email', 'conversation_id': 'c:fin',
                                         'subject': 'RE: July 2026 Financials', 'from_name': 'Hindy Spiegel',
                                         'from_email': 'hindy@hrtgcs.com', 'sent_at': ago(0),
                                         'body': 'The July financials bounced for Rene Gomez - his mailbox is full.',
                                         'to': ['owner@ours.com']}, llm=brain('task', 'coding'))

    def test_a_reply_after_its_task_closed_is_new_work_not_another_tasks_mail(self):
        s = store()
        fin, pcc = self._two_tasks(s)
        s.update_task(fin, {'Status': 'done'}, 'owner')                    # the owner closed it, as they had
        with mock.patch.object(ingest, '_spawn'):
            out = self._reply_on_the_financials_thread(s)
        self.assertEqual(out['status'], 'created')                          # new work, per the written rule
        self.assertNotIn(out['task_id'], (fin, pcc))
        self.assertNotIn('Rene Gomez', ' '.join(str(m.get('BodyText') or '') for m in s.list_messages(pcc)))

    def test_the_guard_itself_refuses_a_third_task_and_says_why(self):
        """What actually happened: route() scored the reply against the OPEN tasks and the
        PointClickCare one won on sender plus body similarity. The guard is what stops that."""
        s = store()
        fin, pcc = self._two_tasks(s)
        msg = {'conversation_id': 'c:fin', 'subject': 'RE: July 2026 Financials', 'channel': 'email',
               'from_email': 'hindy@hrtgcs.com', 'body': 'bounced for Rene Gomez'}
        attached = {'decision': 'attach', 'task_id': pcc, 'score': 0.61, 'reason': 'looked alike'}
        with_open = ingest.own_thread_only(s, msg, attached)
        self.assertEqual((with_open['decision'], with_open['task_id']), ('attach', fin))    # its own thread wins
        self.assertIn(f'TQ-{fin:04d}', with_open['reason'])
        s.update_task(fin, {'Status': 'done'}, 'owner')
        closed = ingest.own_thread_only(s, msg, attached)
        self.assertEqual((closed['decision'], closed['task_id']), ('create', None))         # …or nobody's
        self.assertIn('is closed', closed['reason'])
        # a message on ITS OWN task's thread is left exactly as routing decided
        same = {**msg, 'conversation_id': 'c:pcc'}
        self.assertEqual(ingest.own_thread_only(s, same, attached), attached)

    def test_a_reply_while_its_task_is_open_joins_that_one(self):
        s = store()
        fin, pcc = self._two_tasks(s)
        with mock.patch.object(ingest, '_spawn'):
            out = self._reply_on_the_financials_thread(s)
        self.assertEqual((out['status'], out['task_id']), ('attached', fin))

    def test_the_reply_a_task_drafts_is_written_from_that_tasks_own_thread(self):
        from taskuary import responder
        s = store()
        fin, pcc = self._two_tasks(s)
        s.update_task(fin, {'Status': 'done'}, 'owner')
        with mock.patch.object(ingest, '_spawn'):
            self._reply_on_the_financials_thread(s)
        seen = {}
        def llm(system, user, **kw):
            seen['user'] = user
            return 'Hindy, attached is the PointClickCare sample.'
        with mock.patch('taskuary.calendar.context_for', return_value=''):
            text = responder.draft_reply(s, pcc, llm=llm)
        self.assertIn('PointClickCare', seen['user'])
        self.assertNotIn('Rene Gomez', seen['user'])                        # the other thread is not in this draft's context
        self.assertIn('PointClickCare', text)

    def test_the_newest_session_is_what_was_done_when_an_agent_ran_twice(self):
        from taskuary import responder
        import pathlib, tempfile
        s = store()
        with mock.patch.object(ingest, '_spawn'):
            out = arrive(s, llm=brain('task', 'coding'))
        tid = out['task_id']
        s.add_comment(tid, 'coder', 'agent', 'CODER REPORT' + chr(10) + 'Summary: the second run corrected the first.')
        d = pathlib.Path(tempfile.mkdtemp())
        first, second = d / 'run1.md', d / 'run2.md'
        first.write_text('# run 1\n\n## Final agent response\n\nthe first answer, since corrected\n\n## Full session transcript\n', encoding='utf-8')
        second.write_text('# run 2\n\n## Final agent response\n\nthe corrected answer\n\n## Full session transcript\n', encoding='utf-8')
        for name, path in (('run1.md', first), ('run2.md', second)):
            s.add_task_artifact({'TaskId': tid, 'Name': name, 'Path': str(path), 'Kind': 'coding_session',
                                 'ContentType': 'text/markdown', 'Size': path.stat().st_size, 'CreatedBy': 'coder'})
        with mock.patch('taskuary.session_artifacts.confined', side_effect=lambda p: pathlib.Path(p) if p else None):
            got = responder.resolution_of(s, tid)
        self.assertIn('the corrected answer', got)
        self.assertNotIn('since corrected', got)


class ResponseTests(unittest.TestCase):
    def _asked(self, s=None, **kw):
        """A person's ask on the table, with its task."""
        s = s or store()
        with mock.patch.object(ingest, '_spawn'):
            out = arrive(s, llm=brain('task', 'coding'), **kw)
        item = pile(s)[0]
        return s, out['task_id'], out['message_id'], item

    def _drafted(self, s=None):
        """A reply drafted and waiting for a yes."""
        s = s or store()
        out = arrive(s, subject='Where is the June invoice?', body='Can you send it?', llm=brain('reply_only', None))
        rv = s.pending_review(out['task_id'])
        # a real draft, on the review: `set_review_draft` never existed, so this fixture spent months
        # testing approve against an EMPTY draft - which the app now refuses outright (2026-09-03)
        s.save_review_draft(rv['ReviewId'], 'Attached - sorry for the wait.')
        return s, out['task_id'], rv['ReviewId'], pile(s)[0]

    def test_next_moves_on_and_marks_the_one_shown_read(self):
        s, tid, mid, item = self._asked()
        out = say(s, 'next', key=item['key'])
        self.assertEqual(out['decision']['verb'], 'next')
        self.assertEqual(out['say'], 'Next.')
        surface(s, item['key'])                                        # showing it IS reading it
        self.assertTrue(funnel.next_item(s, item['key'])['surfaced'])

    def test_done_closes_the_task_behind_the_item(self):
        s, tid, mid, item = self._asked()
        self.assertEqual(say(s, 'done, i handled it', key=item['key'])['decision']['verb'], 'done')
        funnel.settle(s, item['key'], 'done', 'owner')
        self.assertEqual([i['key'] for i in pile(s)], [])

    def test_later_and_tomorrow_put_it_back_with_a_clock_on_it(self):
        s, tid, mid, item = self._asked()
        self.assertEqual(say(s, 'later', key=item['key'])['decision']['verb'], 'later')
        funnel.settle(s, item['key'], 'later', 'owner')
        self.assertEqual(pile(s), [])                                  # gone for now…
        st = s.funnel_states()[item['key']]
        self.assertEqual(st['Status'], 'later'); self.assertTrue(st['Until'])   # …and it comes back at its time
        s2, tid2, mid2, item2 = self._asked()
        self.assertEqual(say(s2, 'tomorrow', key=item2['key'])['decision']['verb'], 'skip')

    def test_reply_carries_the_gist_into_the_draft(self):
        s, tid, mid, item = self._asked()
        out = say(s, 'reply and tell them the export is fixed and shipping tonight', key=item['key'])
        self.assertEqual(out['decision']['verb'], 'reply')
        self.assertIn('export is fixed', out['decision']['text'])      # the page passes this as the instruction

    def test_approve_sends_the_drafted_reply_and_the_task_settles(self):
        from taskuary import verdicts
        s, tid, rid, item = self._drafted()
        out = say(s, 'approve', key=item['key'])
        self.assertEqual(out['decision']['verb'], 'approve')
        sent = {'ok': True, 'to': 'craig@vendor.com', 'subject': 'RE:', 'provider': 'test', 'channel': 'email'}
        with mock.patch('taskuary.outbound.reply_to_message', return_value=sent), \
             mock.patch.object(terminal, 'live_sessions', return_value=[]):
            verdicts.decide(s, s.get_review(rid), 'approve', 'Attached.', None, 'owner')
        self.assertIn(s.get_review(rid)['Status'], ('approved', 'edited'))   # 'edited' when the text was touched
        self.assertEqual(s.get_task(tid)['Status'], 'done')            # a sent reply closes its task
        self.assertIsNotNone(s.sent_reply(task_id=tid))

    def test_not_ours_files_it_and_never_again_writes_the_verdict_down(self):
        s, tid, mid, item = self._asked()
        self.assertEqual(say(s, "not my issue, let them sort it out", key=item['key'])['decision']['verb'], 'not_ours')
        s2, tid2, mid2, item2 = self._asked()
        self.assertEqual(say(s2, 'never again for this kind', key=item2['key'])['decision']['verb'], 'not_ours_remember')
        s3, tid3, mid3, item3 = self._asked()
        self.assertEqual(say(s3, 'that sender is junk, block them', key=item3['key'])['decision']['verb'], 'not_ours_sender')

    def test_remember_keeps_the_fact_in_the_owners_words(self):
        s, tid, mid, item = self._asked()
        out = say(s, 'remember that Hindy is the CFO and signs off on refunds', key=item['key'])
        # the row is written HERE, so the receipt is a fact and the page has nothing to carry out
        self.assertEqual(out['decision']['verb'], 'remembered')
        self.assertEqual(out['decision']['note'], 'Hindy is the CFO and signs off on refunds')
        self.assertIn('Hindy is the CFO and signs off on refunds', [m['Note'] for m in s.list_memories()])          # the row exists, not just the receipt
        self.assertIn('still on the table', out['say'])                               # ...and the walk did not move

    def test_send_it_to_the_coder_with_nothing_on_the_table_still_opens_a_task(self):
        s = store()
        with mock.patch.object(ingest, '_spawn') as spawn:
            out = say(s, 'look into why the bulk approve fix did not stick')
        self.assertEqual(out['decision']['verb'], 'created')
        t = s.get_task(out['decision']['taskId'])
        self.assertEqual(t['Kind'], 'coding'); self.assertTrue(spawn.called)
        self.assertIn('did not stick', t['Summary'])

    def test_mine_takes_it_off_the_agents_hands(self):
        s, tid, mid, item = self._asked()
        self.assertEqual(say(s, "i'll do it myself", key=item['key'])['decision']['verb'], 'mine')

    def test_close_the_task_closes_it_and_says_which(self):
        s, tid, mid, item = self._asked()
        out = say(s, 'close it', key=item['key'])
        self.assertEqual(out['decision'], {'verb': 'closed', 'taskId': tid, 'ref': f'TQ-{tid:04d}'})
        self.assertEqual(s.get_task(tid)['Status'], 'done')
        self.assertIn(f'TQ-{tid:04d} closed', out['say'])

    def test_stopping_the_agent_is_not_closing_the_task(self):
        s, tid, mid, item = self._asked()
        s.update_task(tid, {'Status': 'in_progress'}, 'router')
        live = session(tid)
        out = say(s, 'close the agent working', key=item['key'], live=live)
        self.assertEqual(out['decision']['verb'], 'stop_agent')
        self.assertEqual(out['decision']['taskId'], tid)
        self.assertFalse(out['decision']['wrap'])
        self.assertIn('task stays open', out['say'])
        self.assertNotEqual(s.get_task(tid)['Status'], 'done')         # the page ends the session; the task stands
        # a wrap writes the report FROM the transcript: with one, "wrap it up" wraps
        s.add_transcript(tid, 'sid1', 'ran the tests, fixed the filter', 'coder')
        out = say(s, "it's finished, wrap it up", key=item['key'], live=live)
        self.assertTrue(out['decision']['wrap'])

    def test_the_agent_that_is_named_is_the_one_stopped(self):
        s, tid, mid, item = self._asked()
        s2 = s
        with mock.patch.object(ingest, '_spawn'):
            other = arrive(s2, subject='Second job', body='and this too', conv='c:2', hours=2, llm=brain('task', 'coding'))
        both = session(tid) + session(other['task_id'])
        out = say(s2, f"stop the agent on TQ-{other['task_id']:04d}", key=item['key'], live=both)
        self.assertEqual(out['decision']['taskId'], other['task_id'])   # named wins over what is on the table

    def test_rerun_queues_the_report_again(self):
        s = store()
        sid = s.save_source({'Channel': 'report', 'Address': 'Nightly export', 'Owner': 'o', 'Active': 1,
                             'ConfigJson': json.dumps({'type': 'agent', 'title': 'Nightly export'})}, 'o')
        m = s.add_message({'ExternalId': 'r1', 'Channel': 'report', 'SourceName': 'Nightly export',
                           'Subject': 'Nightly export — FAILED', 'FromName': 'Nightly export', 'SentAt': ago(1),
                           'BodyText': 'error: timed out', 'Status': 'feed'})
        s.add_route(m, None, 'feed', None, 'a report you set up', [], 'feed')
        item = pile(s)[0]
        self.assertEqual(item['source_id'], sid)
        self.assertEqual(say(s, 'run it again', key=item['key'])['decision']['verb'], 'rerun')

    def test_a_sweep_clears_these_and_remembers_the_kind(self):
        s = store()
        for n in range(3):
            arrive(s, subject=f'MFA Financial Report - .0{n}', body='from Intacct', who='Nechama Ozur',
                   email='nozur@hrtgcs.com', hours=n + 1, llm=brain('fyi', None))
        keep = arrive(s, subject='RE: PointClickCare', body='please respond', who='Kishan',
                      email='kishan@vendor.com', hours=1, llm=brain('fyi', None))
        self.assertEqual(len(pile(s)), 4)
        out = say(s, "skip all the mfa financial reports, that is taken care of", key=pile(s)[0]['key'])
        self.assertEqual(out['decision']['cleared']['cleared'], 3)
        self.assertEqual([i['who'] for i in pile(s)], ['Kishan'])
        self.assertEqual([r['sender'] for r in funnel.mutes(s)], ['nozur@hrtgcs.com'])
        self.assertTrue(keep['message_id'])

    def test_split_breaks_one_arrival_into_two_jobs(self):
        s = store()
        with mock.patch.object(ingest, '_spawn'):
            out = arrive(s, subject='Two things', hours=1, llm=brain('task', 'coding'),
                         body=('Can you fix the nightly export? It drops inter-company rows.\\n\\n'
                               'Also, please add Priya to the payroll distribution list.'))
        tid = out['task_id']
        item = pile(s)[0]
        two = {'two': True, 'why': 'an export fix and a mailing-list change',
               'first': {'title': 'Fix the nightly export', 'summary': 'drops inter-company rows'},
               'second': {'title': 'Add Priya to the payroll distribution list', 'summary': 'mailing list'},
               'move_message_ids': []}
        with mock.patch('taskuary.reshape.propose_split', return_value=two):
            out = say(s, 'these are two different things, split it', key=item['key'])
        self.assertEqual(out['decision']['verb'], 'split')
        self.assertEqual(s.get_task(tid)['Title'], 'Fix the nightly export')
        new = s.get_task(out['decision']['taskId'])
        self.assertEqual((new['Title'], new['Kind']), ('Add Priya to the payroll distribution list', 'coding'))
        self.assertIn('Split', out['say'])
        self.assertEqual(len([t for t in s.list_tasks(active_only=True)]), 2)

    def test_set_something_up_opens_a_walk_through_not_a_build(self):
        s = store()
        with mock.patch.object(ingest, '_spawn') as spawn:
            out = say(s, 'set up the Zoho invoice integration so it drafts the monthly invoices')
        self.assertEqual(out['decision']['verb'], 'walkthrough')
        self.assertEqual(s.get_task(out['decision']['taskId'])['Kind'], 'general')
        self.assertFalse(spawn.called)                                  # nobody is sent into a repository

    def test_a_correction_is_taken_not_shrugged_off(self):
        s, tid, mid, item = self._asked()
        out = say(s, "that's not a fail, it says all clear?", key=item['key'],
                  model='Fair enough - the run says all clear.' + chr(10) + 'DECIDE: next')
        self.assertIsNone(out['decision'])
        self.assertIn('all clear', out['say'])

    def test_a_question_is_answered_and_decides_nothing(self):
        s, tid, mid, item = self._asked()
        out = say(s, 'what did they actually ask for?', key=item['key'], model='They want the export fixed.')
        self.assertIsNone(out['decision'])
        self.assertEqual(out['say'], 'They want the export fixed.')

    def test_naming_something_else_pulls_it_onto_the_table(self):
        s, tid, mid, item = self._asked()
        with mock.patch.object(ingest, '_spawn'):
            arrive(s, subject='Resident refund for Mrs Garnett', body='Please approve the refund.',
                   who='Rivka Mermelstein', email='rivka@ours.com', conv='c:refund', hours=2, llm=brain('task', 'coding'))
        out = say(s, 'what did Rivka send about the refund?', key=item['key'])
        self.assertIsNotNone(out.get('item'))
        self.assertIn('Rivka', f"{out['item'].get('who')} {out['say']}")

    def test_every_verb_the_contract_offers_is_one_the_code_can_carry_out(self):
        """The model may answer with any verb in the contract; each has to mean something here."""
        for verb in concierge.VERBS:
            if verb == 'none': continue
            self.assertTrue(verb in concierge.RECEIPTS or verb in ('clear', 'split', 'stop_agent', 'close', 'setting', 'forward'),
                            f'{verb} has no receipt and no branch')


# ── the break test of 2026-09-03, one case per finding (docs/assistant-break-test-2026-09-03.md) ──
class WrongTargetTests(unittest.TestCase):
    """A. The verb acts on what the SENTENCE names, or on nothing at all - never on whatever card
    happens to be open. 'not ours, facilities handles the portal' filed the finished coding task on
    the table and deleted it, report, commit reference and drafted reply included."""

    def _two(self):
        """A drafted reply on the table; an outage from somebody else waiting behind it."""
        s = store()
        out = arrive(s, subject='Where is the June invoice?', body='Can you send it?', who='Kishan Patel',
                     email='kishan@vendor.com', conv='c:inv', hours=1, llm=brain('reply_only', None))
        rv = s.pending_review(out['task_id']); s.save_review_draft(rv['ReviewId'], 'Attached.')
        other = arrive(s, subject='Payroll portal is down', body='Nobody in Roanoke can clock in.', who='Miriam Schwartz',
                       email='miriam@ours.com', conv='c:outage', channel='teams', hours=0, llm=brain('task', 'general'))
        return s, out, rv['ReviewId'], other

    def test_a_verb_about_another_subject_is_carried_out_there_not_here(self):
        s, mine, rid, other = self._two()
        item = next(i for i in pile(s) if i.get('rid') == rid)
        with mock.patch.object(ingest, '_spawn'):
            out = say(s, 'not ours, this is the payroll portal outage - facilities handle that', key=item['key'])
        d = out['decision'] or {}
        self.assertEqual(d.get('verb'), 'not_ours')
        self.assertEqual((d.get('target') or {}).get('mid'), other['message_id'])     # THAT one, by its own ids
        self.assertIn('not the one on the table', out['say'])
        self.assertEqual(s.get_review(rid)['Status'], 'pending')                     # ...and this one is untouched
        self.assertEqual(s.get_task(mine['task_id'])['Status'], 'open')

    def test_a_verb_about_a_subject_we_cannot_find_asks_instead_of_acting(self):
        s, mine, rid, other = self._two()
        item = next(i for i in pile(s) if i.get('rid') == rid)
        out = say(s, 'not ours, the badge printer contract is legal’s', key=item['key'])
        self.assertIsNone(out['decision'])
        self.assertIn('nothing has been touched', out['say'])
        self.assertEqual(s.get_task(mine['task_id'])['Status'], 'open')

    def test_plain_words_still_act_on_the_thing_on_the_table(self):
        s, mine, rid, other = self._two()
        item = next(i for i in pile(s) if i.get('rid') == rid)
        for words in ('not ours', 'not my problem', "it's not my issue so let them sort it out", 'done, thanks'):
            out = say(s, words, key=item['key'])
            self.assertIsNotNone(out['decision'], words)                             # no false alarm on ordinary speech
            self.assertNotIn('target', out['decision'], words)

    def test_filing_a_message_whose_task_an_agent_worked_archives_it(self):
        s, tid, mid, item = ResponseTests()._asked()
        s.add_comment(tid, 'coder', 'agent', 'CODER REPORT\nFixed the filter; committed as abc123.')
        with mock.patch.object(server, 'store', s), mock.patch.object(terminal, 'live_sessions', return_value=[]):
            c = TestClient(server.app)
            r = c.post(f'/api/messages/{mid}/file', json={'learn': False}).json()
        self.assertFalse(r['taskDeleted']); self.assertTrue(r['taskArchived'])
        t = s.get_task(tid)
        self.assertEqual(t['Status'], 'done')                                        # closed, kept, report and all
        self.assertTrue(any('CODER REPORT' in (c['Body'] or '') for c in s.list_comments(tid)))


class ApproveOnceTests(unittest.TestCase):
    """A2/A3. Approving is sending: it happens once, and never with nothing to send."""

    def test_approving_an_empty_draft_sends_nothing_and_leaves_it_in_the_pipe(self):
        from taskuary import verdicts
        s = store()
        out = arrive(s, subject='Are you around Tuesday?', body='Quick call?', llm=brain('reply_only', None))
        rv = s.pending_review(out['task_id'])
        r = verdicts.decide(s, s.get_review(rv['ReviewId']), 'approve', None, None, 'owner')
        self.assertTrue(r.get('empty')); self.assertFalse(r['ok'])
        self.assertEqual(s.get_review(rv['ReviewId'])['Status'], 'pending')
        self.assertEqual(s.get_task(out['task_id'])['Status'], 'open')               # the task did NOT close
        item = next(i for i in pile(s) if i.get('rid') == rv['ReviewId'])
        said = say(s, 'approve', key=item['key'])
        self.assertIsNone(said['decision']); self.assertIn('nothing to approve', said['say'].lower())

    def test_approving_twice_sends_once(self):
        from taskuary import verdicts
        s, tid, rid, item = ResponseTests()._drafted()
        sent = {'ok': True, 'to': 'craig@vendor.com', 'subject': 'RE:', 'provider': 'test', 'channel': 'email'}
        with mock.patch('taskuary.outbound.reply_to_message', return_value=sent) as send, \
             mock.patch.object(terminal, 'live_sessions', return_value=[]):
            first = verdicts.decide(s, s.get_review(rid), 'approve', None, None, 'owner')
            second = verdicts.decide(s, s.get_review(rid), 'approve', None, None, 'owner')
        self.assertTrue(first['ok']); self.assertFalse(second['ok']); self.assertTrue(second.get('already'))
        self.assertEqual(send.call_count, 1)                                         # one mail, not two


class OneTruthPerTurnTests(unittest.TestCase):
    """B. The receipt is what happened. No verb is receipted that the card cannot carry out."""

    def test_a_verb_the_card_cannot_carry_is_refused_before_it_is_receipted(self):
        s, tid, mid, item = ResponseTests()._asked()                                  # an ask: no draft, no report
        for words, word in (('approve', 'approve'), ('rerun it', 'rerun'), ('tell the agent yes', 'answer')):
            out = say(s, words, key=item['key'])
            self.assertIsNone(out['decision'], words)
            self.assertIn('nothing to', out['say'].lower(), words)
            self.assertNotIn('Moving on', out['say'], words)

    def test_a_hand_off_with_no_agent_on_the_machine_says_so(self):
        s, tid, mid, item = ResponseTests()._asked()
        s._exec('DELETE FROM agent')
        out = say(s, 'send it to the coder', key=item['key'])
        self.assertIsNone(out['decision']); self.assertIn('not set up on this machine', out['say'])

    def test_remembering_writes_the_row_and_leaves_the_walk_where_it_was(self):
        s, tid, mid, item = ResponseTests()._asked()
        out = say(s, 'remember that Dovid handles the badge printers', key=item['key'])
        self.assertEqual(out['decision']['verb'], 'remembered')
        self.assertEqual([m['Note'] for m in s.list_memories()], ['Dovid handles the badge printers'])
        self.assertNotIn('Moving on', out['say'])
        self.assertEqual(funnel.next_item(s, item['key'])['key'], item['key'])        # still on the table

    def test_approve_and_remember_does_both(self):
        s, tid, rid, item = ResponseTests()._drafted()
        out = say(s, 'approve and remember that Kishan handles refunds', key=item['key'])
        self.assertEqual(out['decision']['verb'], 'approve')
        self.assertEqual([m['Note'] for m in s.list_memories()], ['Kishan handles refunds'])
        self.assertIn('remembered', out['say'].lower())


class WordsTheOwnerUsesTests(unittest.TestCase):
    """The phrases from the break test that meant the opposite of what they did."""

    def test_holding_something_open_is_never_a_verdict(self):
        for words in ("don't ignore this one", 'leave it open', 'leave it with the agent', "don't close it yet"):
            self.assertIsNone(concierge.decide_words(words), words)

    def test_telling_them_something_is_a_reply_not_a_filing(self):
        for words in ('let them know we will fix it by Friday', 'tell them to ignore it',
                      'reply: not ours, sorry', 'remember to reply to him'):
            self.assertEqual((concierge.decide_words(words) or {}).get('verb'), 'reply', words)

    def test_a_question_about_state_is_not_a_coding_job(self):
        self.assertIsNone(concierge.decide_words('can you check if the report ran?'))

    def test_the_verbs_the_owner_kept_using(self):
        for words, verb in (('skip it', 'skip_choice'), ('delete it', 'archive'), ('archive it', 'archive'),
                            ('snooze it', 'later'), ('remind me tomorrow', 'skip'),
                            ('make the reply shorter', 'redraft'), ('forward it to Chana', 'forward'),
                            ('ask Chana to handle it', 'forward'), ('tell the agent yes', 'answer_agent'),
                            ('answer the agent: yes remove them', 'answer_agent')):
            self.assertEqual((concierge.decide_words(words) or {}).get('verb'), verb, words)

    def test_skip_it_asks_once_or_forever_and_each_answer_has_a_distinct_verdict(self):
        s, tid, mid, item = ResponseTests()._asked()
        ask = say(s, 'skip it', key=item['key'])
        self.assertIsNone(ask['decision'])
        self.assertEqual(ask['options'], ['Just this once', 'Forever for this kind'])
        self.assertEqual(s.list_memories(), [])
        self.assertEqual(say(s, 'Just this once', key=item['key'])['decision']['verb'], 'not_ours')

        s2, tid2, mid2, item2 = ResponseTests()._asked()
        self.assertEqual(say(s2, 'Forever for this kind', key=item2['key'])['decision']['verb'],
                         'not_ours_remember')

    def test_yes_means_whatever_the_card_in_front_of_them_does(self):
        s, tid, rid, item = ResponseTests()._drafted()
        for words in ('yes', 'ok', 'go ahead', 'do it'):
            self.assertEqual(say(s, words, key=item['key'])['decision']['verb'], 'approve', words)
        s2, tid2, mid2, item2 = ResponseTests()._asked()
        live = session(tid2, idle=200, waiting=True, tail=['Remove the old rows too? (y/n)'])
        s2.update_task(tid2, {'Status': 'in_progress'}, 'router')
        agent = next(i for i in pile(s2, live) if i['kind'] == 'agent')
        for words in ('yes', 'yes remove them'):
            out = say(s2, words, key=agent['key'], live=live)
            self.assertEqual(out['decision']['verb'], 'answer_agent', words)
            self.assertIn('remove them' if 'remove' in words else 'yes', out['decision']['text'])

    def test_a_yes_with_nothing_to_say_yes_to_asks_rather_than_guesses(self):
        s, tid, mid, item = ResponseTests()._asked()
        out = say(s, 'yes', key=item['key'])
        self.assertIsNone(out['decision']); self.assertIn('Yes to what', out['say'])


class AgentEndingsTests(unittest.TestCase):
    """A5. Closing a task ends the agent on it; 'done' on a parked agent ends both."""

    def _parked(self):
        s, tid, mid, item = ResponseTests()._asked()
        s.update_task(tid, {'Status': 'in_progress'}, 'router')
        live = session(tid, idle=200, waiting=True, tail=['Remove the old rows too? (y/n)'])
        return s, tid, live, next(i for i in pile(s, live) if i['kind'] == 'agent')

    def test_close_it_from_the_chat_stops_the_session_too(self):
        s, tid, live, item = self._parked()
        with mock.patch.object(terminal, 'session_for') as found, mock.patch.object(terminal, 'close') as closed:
            found.return_value = mock.Mock(sid='s1', alive=True)
            out = say(s, 'close it', key=item['key'], live=live)
        self.assertEqual(out['decision']['verb'], 'closed')
        self.assertEqual(s.get_task(tid)['Status'], 'done')
        closed.assert_called_once_with('s1')

    def test_done_on_a_parked_agent_closes_the_task_and_the_session(self):
        s, tid, live, item = self._parked()
        with mock.patch.object(terminal, 'session_for') as found, mock.patch.object(terminal, 'close') as closed:
            found.return_value = mock.Mock(sid='s1', alive=True)
            out = say(s, 'done', key=item['key'], live=live)
        self.assertEqual(out['decision']['verb'], 'closed')
        self.assertEqual(s.get_task(tid)['Status'], 'done'); closed.assert_called_once_with('s1')

    def test_wrap_it_up_with_nothing_to_wrap_says_so(self):
        s, tid, live, item = self._parked()
        out = say(s, 'wrap it up', key=item['key'], live=live)
        self.assertFalse(out['decision']['wrap'])                                     # the page would 422 on a wrap
        self.assertIn('nothing to wrap', out['say'])


class WalkFromWordsTests(unittest.TestCase):
    """C. The walk starts and continues from TYPED words, not only from buttons - and it never
    claims to be somewhere it is not."""

    def _three(self):
        s = store()
        with mock.patch.object(ingest, '_spawn'):
            arrive(s, subject='Fix the export', body='Rows drop.', conv='c:b', hours=3, llm=brain('task', 'coding'))
            arrive(s, subject='FYI - Rebecca is back', body='Just so you know.', who='Chana', email='chana@ours.com',
                   conv='c:c', hours=2, llm=brain('fyi', None))
            arrive(s, subject='FYI - lunch moved', body='Thursday now.', who='Chana', email='chana@ours.com',
                   conv='c:d', hours=2, llm=brain('fyi', None))
        return s

    def test_next_and_done_with_nothing_on_the_table_bring_the_next_thing_up(self):
        for words in ('next', 'done', 'walk me through my tasks', "what's next"):
            s = self._three()
            out = say(s, words, key=None)
            self.assertIsNotNone(out.get('item'), words)                      # something came out of the pipe
            self.assertIsNone(out.get('decision'), words)

    def test_start_with_the_mail_walks_only_the_mail(self):
        s = self._three()
        out = say(s, 'start with the mail', key=None)
        self.assertTrue(out['item']['mid'])

    def test_a_verb_with_nothing_on_the_table_says_so_instead_of_claiming(self):
        s = self._three()
        for words in ('close it', 'approve', 'rerun it'):
            out = say(s, words, key=None)
            self.assertIsNone(out.get('decision'), words)
            self.assertIn('Nothing is on the table', out['say'], words)

    def test_words_land_on_the_fyi_batch_the_way_buttons_do(self):
        s = self._three()
        with mock.patch.object(terminal, 'live_sessions', return_value=[]):
            first = concierge.surface(s, llm=None)                            # the coding ask
            card = concierge.surface(s, llm=None)                             # ...then the FYI handful
        self.assertTrue(card['item']['key'].startswith('fyis:'))
        self.assertEqual((card['item']['kind'], len(card['item']['items'])), ('fyis', 2))
        for words, verb in (('next', 'next'), ('done', 'done')):
            out = say(s, words, key=card['item']['key'])
            self.assertEqual((out.get('decision') or {}).get('verb'), verb, words)

    def test_a_new_chat_brings_a_waiting_agent_back(self):
        s, tid, mid, item = ResponseTests()._asked()
        s.update_task(tid, {'Status': 'in_progress'}, 'router')
        live = session(tid, idle=200, waiting=True, tail=['Remove the old rows too? (y/n)'])
        agent = next(i for i in pile(s, live) if i['kind'] == 'agent')
        funnel.settle(s, agent['key'], 'surfaced', 'owner')                   # shown in yesterday's chat
        with mock.patch.object(terminal, 'live_sessions', return_value=live):
            self.assertNotEqual((funnel.next_item(s) or {}).get('key'), agent['key'])
            funnel.reset_walk(s)                                              # ...a new chat
            self.assertEqual(funnel.next_item(s)['key'], agent['key'])        # the thing that blocks work comes first

    def test_the_voice_never_says_it_cannot_see_the_queue(self):
        s, tid, mid, item = ResponseTests()._asked()
        for excuse in ("I understand the role, but I don't have the queue data to walk you through.",
                       "I'm in Claude Code, so I don't have access to the systems Taskuary would need.",
                       'As an AI, I cannot access your pipe.'):
            self.assertFalse(concierge.in_character(excuse), excuse)
            out = say(s, 'what is this one again?', key=item['key'], model=excuse)
            self.assertNotIn('Claude Code', out['say']); self.assertNotIn('queue data', out['say'])
            self.assertIn(item['title'][:12], out['say'])                     # the facts, instead


class PipeTruthTests(unittest.TestCase):
    """D. What the pipe says is what is: one row per conversation, no ghost agents, and nothing in
    it that says of itself that it could not run."""

    def test_a_chat_opener_waits_for_the_ask_it_opens(self):
        s = store()
        with mock.patch.object(ingest, '_spawn'):
            hey = arrive(s, subject='', body='hey', who='Yosef Adler', email='', channel='whatsapp',
                         conv='w:yosef', hours=0, external_id='w:1', llm=brain('reply_only', None))
        self.assertIsNone(hey['task_id'])                                  # no task, no drafted "Hey - what's up?"
        self.assertEqual(hey['status'], 'filed')
        self.assertEqual(s.list_reviews('pending'), [])
        with mock.patch.object(ingest, '_spawn'):
            ask = arrive(s, subject='', body='did the invoice for Oak Ridge go out?', who='Yosef Adler', email='',
                         channel='whatsapp', conv='w:yosef', hours=0, external_id='w:2', llm=brain('reply_only', None))
        self.assertTrue(ask['task_id'])                                    # the ASK is the task
        self.assertIn('Oak Ridge', s.get_task(ask['task_id'])['Title'] + s.get_task(ask['task_id'])['Summary'])

    def test_a_pending_draft_speaks_for_its_whole_thread(self):
        s = store()
        out = arrive(s, subject='Nightly export drops rows', body='Can you fix it?', who='Chana Klein',
                     email='chana@ours.com', conv='c:export', hours=5, llm=brain('reply_only', None))
        rv = s.pending_review(out['task_id']); s.save_review_draft(rv['ReviewId'], 'Fixed and pushed.')
        arrive(s, subject='RE: Nightly export drops rows', body='Also keep two decimals.', who='Chana Klein',
               email='chana@ours.com', conv='c:export', hours=1, llm=brain('fyi', None))
        rows = [i for i in pile(s) if i.get('cid') == 'c:export']
        self.assertEqual([i['kind'] for i in rows], ['review'])            # one row, and it is the draft
        self.assertEqual(rows[0]['more'], 1)                               # ...which says how much it stands for

    def test_a_stopped_agent_gives_the_task_back(self):
        s, tid, mid, item = ResponseTests()._asked()
        s.update_task(tid, {'Status': 'in_progress'}, 'router')
        c = TestClient(server.app)
        live = mock.Mock(sid='s1', alive=True, label='coder', agent='coder', task_id=tid)
        with mock.patch.object(server, 'store', s), mock.patch.object(server.hub_term, 'session_for', return_value=live), \
             mock.patch.object(server.hub_term, 'close', return_value=True):
            c.post(f'/api/tasks/{tid}/agent/stop')
        with mock.patch.object(terminal, 'live_sessions', return_value=[]):
            keys = [(i['key'], i['lane']) for i in funnel.build(s)['items']]
        self.assertTrue(any(k == f'msg:{mid}' and lane != 'working' for k, lane in keys), keys)

    def test_a_run_row_nobody_touched_is_not_an_agent_at_work(self):
        s, tid, mid, item = ResponseTests()._asked()
        rid = s.start_run(tid, 'coder', 'fix it', 'owner')
        with mock.patch.object(terminal, 'live_sessions', return_value=[]):
            self.assertIn(tid, funnel.working_tids(s))                     # fresh: an agent really is on it
            s._exec('UPDATE run SET StartedAt=?, UpdatedAt=? WHERE RunId=?', (ago(hours=3), ago(hours=3), rid))
            self.assertNotIn(tid, funnel.working_tids(s))                  # three hours untouched: a corpse

    def test_a_report_that_could_not_summarise_stays_off_the_pipe(self):
        from taskuary.reports import NO_BRAIN
        s = store()
        m = s.add_message({'ExternalId': 'r:1', 'Channel': 'report', 'SourceName': 'Nightly export',
                           'Subject': 'Nightly export — 12 rows', 'FromName': 'Nightly export', 'SentAt': ago(1),
                           'BodyText': f'{NO_BRAIN} - raw data below)\n\nrow, row, row', 'Status': 'feed'})
        s.add_route(m, None, 'feed', None, 'a report you set up', [], 'feed')
        funnel.invalidate()
        self.assertEqual([i for i in pile(s) if i['kind'] == 'report'], [])
        self.assertTrue(s.get_message(m))                                  # still on the Timeline

    def test_a_sweep_that_names_a_lane_writes_a_lane_rule(self):
        s = store()
        arrive(s, subject='FYI - Rebecca is back', body='Just so you know.', who='Chana Klein',
               email='chana@ours.com', conv='c:f1', hours=2, llm=brain('fyi', None))
        out = concierge.clear_matching(s, 'skip all the fyi from Chana, I do not need those')
        self.assertEqual(out['cleared'], 1)
        rule = funnel.mutes(s)[0]
        self.assertEqual((rule.get('sender'), rule.get('lane'), rule.get('words')), ('chana@ours.com', 'fyi', []))
        # ...and it means every fyi from her, not the mails with 'fyi' in the subject
        self.assertTrue(funnel.muted(rule, {'email': 'chana@ours.com', 'lane': 'fyi', 'title': 'lunch on Thursday'}))
        self.assertFalse(funnel.muted(rule, {'email': 'chana@ours.com', 'lane': 'asked', 'title': 'fyi about the audit'}))


class AgentsStartAndFinishTests(unittest.TestCase):
    """E. An agent Taskuary starts must not park on a question the owner already answered, and what
    it IS asking must reach the card."""

    def test_the_checkout_is_trusted_before_claude_opens_it(self):
        import json as _json, tempfile
        home, cwd = tempfile.mkdtemp(), tempfile.mkdtemp()
        self.assertTrue(terminal.pretrust(cwd, r'C:\bin\claude.cmd --model sonnet', home=home))
        got = _json.load(open(os.path.join(home, '.claude.json'), encoding='utf-8'))['projects'][cwd]
        self.assertTrue(got['hasTrustDialogAccepted'] and got['hasClaudeMdExternalIncludesApproved'])
        self.assertFalse(terminal.pretrust(cwd, 'claude', home=home))       # already answered: nothing written
        self.assertFalse(terminal.pretrust(cwd, 'codex', home=home))        # only claude asks these

    def test_pretrust_keeps_everything_else_in_the_file(self):
        import json as _json, tempfile
        home, cwd = tempfile.mkdtemp(), tempfile.mkdtemp()
        p = os.path.join(home, '.claude.json')
        open(p, 'w', encoding='utf-8').write(_json.dumps({'userID': 'abc', 'projects': {'/other': {'allowedTools': ['Bash']}}}))
        terminal.pretrust(cwd, 'claude', home=home)
        got = _json.load(open(p, encoding='utf-8'))
        self.assertEqual(got['userID'], 'abc')
        self.assertEqual(got['projects']['/other'], {'allowedTools': ['Bash']})

    def test_the_cards_question_is_the_screen_not_the_theme_bar(self):
        chrome = ['─────────────', '  Catppuccin Mocha  Dracula  Nord', '? for shortcuts', 'auto-accept edits on']
        real = 'Remove the old rows too? (y/n)'
        with mock.patch.object(terminal, 'screen', return_value={'lines': [real] + chrome}):
            self.assertEqual(terminal.asking_lines('s1', 4), [real])

    def test_a_walkthrough_the_owner_just_opened_does_not_raise_its_own_hand(self):
        s = store()
        made = concierge.setup_task(s, 'set up a weekly refunds report', 'owner')
        tid = made['taskId']
        s.update_task(tid, {'Status': 'in_progress'}, 'router')
        live = session(tid, idle=200, waiting=True, started=ago(minutes=2),
                       tail=['What should it cover? (1) refunds (2) everything'])
        self.assertEqual([i for i in pile(s, live) if i['kind'] == 'agent'], [])     # they are IN it
        live[0]['started'] = ago(hours=2)                                            # ...but not any more
        self.assertEqual([i['key'] for i in pile(s, live) if i['kind'] == 'agent'], [f'agent:{tid}'])

    def test_the_coder_brief_has_one_rule_about_finishing(self):
        doc = open(os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
                                'taskuary', 'templates', 'coder.md'), encoding='utf-8').read()
        closing = doc.split('## Closing out', 1)[1].split('##', 1)[0]
        self.assertIn('taskuary --done', closing)                        # it says to say so...
        self.assertNotIn('do not write a wrap-up', closing)              # ...and no longer says not to
        self.assertNotIn('clicks **Done**', closing)


# ── the order things come out in, and the verdicts that never become work ────────────────────
class WalkOrderTests(unittest.TestCase):
    """The pipe's whole claim is that the NEXT thing is the right thing. One pile with something in
    every lane, walked to the end."""

    def _everything(self, s):
        # an agent parked on a question (blocked), a draft for a yes (approve), a person's ask (asked),
        # a report that landed (report) and a colleague's fyi (fyi)
        with mock.patch.object(ingest, '_spawn'):
            agent = arrive(s, subject='Fix the export', conv='c:agent', hours=8, who='Chana', email='chana@ours.com',
                           body='The export drops rows.', llm=brain('task', 'coding'))
            asked = arrive(s, subject='Refund for Mrs Garnett', conv='c:ask', hours=4, who='Rivka', email='rivka@ours.com',
                           body='Please approve the refund.', llm=brain('task', 'coding'))
        s.update_task(agent['task_id'], {'Status': 'in_progress'}, 'router')
        draft = arrive(s, subject='Where is the June invoice?', conv='c:draft', hours=6, who='Kishan',
                       email='kishan@vendor.com', body='Can you send it?', llm=brain('reply_only', None))
        rep = s.add_message({'ExternalId': 'r1', 'Channel': 'report', 'SourceName': 'Nightly export',
                             'Subject': 'Nightly export - 0 errors', 'FromName': 'Nightly export',
                             'SentAt': ago(3), 'BodyText': 'all clear', 'Status': 'feed'})
        s.add_route(rep, None, 'feed', None, 'a report you set up', [], 'feed')
        arrive(s, subject='FYI - Rebecca is back Tuesday', conv='c:fyi', hours=2, who='Chana', email='chana@ours.com',
               body='Just so you know.', llm=brain('fyi', None))
        return agent['task_id'], draft['task_id'], asked['task_id']

    def test_the_mouth_gives_them_up_in_the_order_a_sharp_assistant_would_raise_them(self):
        s = store()
        agent, draft, asked = self._everything(s)
        parked = session(agent, idle=200, waiting=True, tail=['Drop the old rows? (y/n)'])
        with mock.patch.object(terminal, 'live_sessions', return_value=parked):
            self.assertEqual([i['lane'] for i in funnel.build(s)['items']],
                             ['blocked', 'approve', 'asked', 'report', 'fyi'])
            # …and one at a time out of the mouth, in that order, each one read as it is shown
            seen = []
            for _ in range(5):
                out = concierge.surface(s, llm=lambda *a, **k: 'never asked')
                if not out.get('item'): break
                seen.append(out['item']['lane'])
                funnel.settle(s, out['item']['key'], 'done', 'owner')
        self.assertEqual(seen, ['blocked', 'approve', 'asked', 'report', 'fyi'])

    def test_start_with_what_came_in_walks_only_what_a_person_sent(self):
        s = store()
        agent, draft, asked = self._everything(s)
        with mock.patch.object(terminal, 'live_sessions', return_value=[]):
            came = []
            for _ in range(6):
                item = funnel.next_item(s, only='mail')
                if not item: break
                came.append((item['kind'], item['channel'] or 'email'))
                funnel.settle(s, item['key'], 'done', 'owner')
        self.assertTrue(came, 'the mail-first walk finds the mail')
        self.assertTrue(all(ch != 'report' for _, ch in came), came)      # never a scheduled report
        self.assertIn('review', [k for k, _ in came])                     # …and it does include a draft for a yes


class NeverWorkTests(unittest.TestCase):
    def test_a_brain_that_fails_files_the_message_and_says_so(self):
        s = store()
        def broken(system, user, **kw): raise RuntimeError('connector 500')
        out = arrive(s, llm=broken)
        self.assertEqual((out['status'], out['task_id']), ('filed', None))
        self.assertIn('AI triage failed', s.message_routes(out['message_id'])[-1]['Reason'])
        self.assertIn('connector 500', s.get_settings().get('triage_last_error') or '')
        # A failed classifier must not invent work, but the arrival is still unread information.
        # Filing/category is not a read receipt: it remains in the shared All/Unread inventory as
        # an FYI explaining the connector failure until the owner reads or handles it.
        items = pile(s)
        self.assertEqual([(i['kind'], i['lane'], i.get('tid')) for i in items], [('fyi', 'fyi', None)])
        self.assertIn('AI triage failed', items[0]['why'])

    def test_a_brain_that_answers_nonsense_files_it_rather_than_guessing(self):
        s = store()
        out = arrive(s, llm=lambda *a, **k: 'I think this is probably a task?')
        self.assertEqual((out['status'], out['task_id']), ('filed', None))
        reason = s.message_routes(out['message_id'])[-1]['Reason']
        self.assertIn('could not read as a verdict', reason)

    def test_a_thread_the_owner_already_ruled_on_never_comes_back_as_work(self):
        s = store()
        with mock.patch.object(ingest, '_spawn'):
            first = arrive(s, subject='Resident refund - Mrs Garnett', conv='c:refund', hours=6,
                           who='Rivka', email='rivka@ours.com', body='Please approve.', llm=brain('task', 'coding'))
        c = TestClient(server.app)
        with mock.patch.object(server, 'store', s), mock.patch.dict(terminal.SESSIONS, {}, clear=True):
            c.post(f"/api/messages/{first['message_id']}/file", json={'learn': True})
        again = ingest.ingest_message(s, {'external_id': 'x:again', 'channel': 'email', 'conversation_id': 'c:refund',
                                          'subject': 'RE: Resident refund - Mrs Garnett', 'from_name': 'Rivka',
                                          'from_email': 'rivka@ours.com', 'sent_at': ago(0),
                                          'body': 'Any update on the approval?'}, llm=brain('task', 'coding'))
        self.assertEqual((again['status'], again['task_id']), ('filed', None))
        reason = s.message_routes(again['message_id'])[-1]['Reason']
        self.assertIn('already ruled', reason)

    def test_a_playbook_instance_is_tagged_so_the_agent_works_it_that_way(self):
        s = store()
        from taskuary import playbooks
        menu = '- pto-import: PTO import' + chr(10) + '  when: PTO files arrive'
        with mock.patch.object(playbooks, 'menu', return_value=menu), mock.patch.object(ingest, '_spawn'):
            out = arrive(s, subject='August PTO files', body='Attached - please import.', who='Chana',
                         email='chana@ours.com', llm=brain('task', 'coding', playbook='pto-import'))
        t = s.get_task(out['task_id'])
        self.assertEqual(t['Kind'], 'coding')
        self.assertIn('pto-import', str(t['Tags'] or ''), 'the playbook rides on the task, so the session is seeded from it')


class TellingItInAdvanceTests(unittest.TestCase):
    """"If you tell it something, how does it know to ignore it?" (the owner, 2026-09-03). Said with
    nothing of that kind in the pipe, the instruction used to be written NOWHERE - the sweep needed
    something to clear. Now the words alone write the rule."""

    def _history(self, s):
        for n in range(2):
            arrive(s, subject=f'MFA Financial Report - .0{n} P&L', body='from Intacct', who='Nechama Ozur',
                   email='nozur@hrtgcs.com', hours=n + 1, llm=brain('fyi', None))
        for i in pile(s): funnel.settle(s, i['key'], 'done', 'owner')      # read already; the pipe is clear
        funnel.invalidate()

    def test_the_words_alone_write_the_rule_and_the_next_batch_never_enters(self):
        s = store()
        self._history(s)
        self.assertEqual(pile(s), [])
        out = say(s, 'nechama emails about mfa financials reports should not show up anymore')
        self.assertEqual(out['decision']['verb'], 'clear')
        self.assertEqual(out['decision']['cleared']['cleared'], 0)          # nothing to clear…
        self.assertTrue(out['decision']['cleared']['ahead'])                 # …so it was noted instead
        self.assertEqual([(r['sender'], r['words']) for r in funnel.mutes(s)],
                         [('nozur@hrtgcs.com', ['nechama', 'mfa', 'financials'])])
        self.assertIn('it is noted', out['say']); self.assertIn('stay on the Timeline', out['say'])
        # …and it is visible as a memory too, so the owner can see and undo it
        notes = [n for n in s.list_memories(active_only=True) if (n['ScopeKey'] or '') == 'nozur@hrtgcs.com']
        self.assertTrue(notes and 'should not show up' in notes[0]['Note'])
        arrive(s, subject='MFA Financial Report - .098 P&L Detail ALF', body='from Intacct',
               who='Nechama Ozur', email='nozur@hrtgcs.com', hours=0, llm=brain('fyi', None))
        funnel.invalidate()
        p = funnel.build(s)
        self.assertEqual((p['items'], p['muted']), ([], 1))

    def test_a_real_ask_from_a_muted_sender_still_reaches_the_owner(self):
        s = store()
        self._history(s)
        say(s, 'nechama emails about mfa financials reports should not show up anymore')
        with mock.patch.object(ingest, '_spawn'):
            arrive(s, subject='MFA Financial Report - can you re-run .02 for me?', body='please re-run it',
                   who='Nechama Ozur', email='nozur@hrtgcs.com', conv='c:rerun', hours=0, llm=brain('task', 'coding'))
        funnel.invalidate()
        self.assertEqual([i['lane'] for i in pile(s)], ['asked'])           # a rule only reaches the quiet lanes

    def test_the_rule_is_the_owners_to_take_off_again(self):
        s = store()
        self._history(s)
        say(s, 'nechama emails about mfa financials reports should not show up anymore')
        c = TestClient(server.app)
        with mock.patch.object(server, 'store', s), mock.patch.dict(terminal.SESSIONS, {}, clear=True):
            listed = c.get('/api/funnel/mutes').json()['data']
            self.assertEqual(len(listed), 1)
            self.assertEqual(c.delete('/api/funnel/mutes/0').status_code, 200)
        self.assertEqual(funnel.mutes(s), [])
        arrive(s, subject='MFA Financial Report - .099 P&L', body='from Intacct', who='Nechama Ozur',
               email='nozur@hrtgcs.com', hours=0, llm=brain('fyi', None))
        funnel.invalidate()
        self.assertEqual([i['who'] for i in pile(s)], ['Nechama Ozur'])     # back, because they said so


class WhichCheckoutTests(unittest.TestCase):
    """An agent in the wrong checkout is the worst thing that can happen quietly, and it happened
    twice: "the assistant sent the coding agent the wrong repo again... It was issue with the github
    trending report but it says fannapp???" (the owner, 2026-09-03). Two leaks, two rules."""

    PROFILE = {'cmd': 'claude', 'cwd': 'C:/Users/x/Documents/FanApp',
               'cwd_map': {'mfaVita/FanApp': 'C:/Users/x/Documents/FanApp',
                           'mfaVita/TopE': 'C:/Users/x/Documents/TopE',
                           'ldbumble/taskuary': 'C:/Users/x/Documents/taskhub'}}
    SOUL = ('# SOUL.md' + chr(10) + '## Repository map' + chr(10)
            + '- **mfaVita/FanApp**: the fan mobile app' + chr(10)
            + '- **mfaVita/TopE**: the expense portal' + chr(10)
            + '- **ldbumble/taskuary**: this assistant, its connectors and its reports' + chr(10))

    def _report_task(self, s):
        s.save_doc('soul', self.SOUL, 'owner')
        tid = s.create_task({'Title': 'GitHub Trending Top 15 Morning Report - coder ran a prompt', 'Kind': 'coding',
                             'Status': 'open', 'Source': 'report'}, 'o')
        s.add_message({'TaskId': tid, 'ExternalId': 'r1', 'Channel': 'report', 'SourceName': 'GitHub Trending',
                       'Subject': 'GitHub Trending Top 15 Morning Report — FAILED', 'FromName': 'GitHub Trending',
                       'SentAt': ago(1), 'BodyText': 'error: claude exit 1: timed out after 300s', 'Status': 'feed'})
        return tid

    def test_our_own_report_goes_to_our_own_checkout(self):
        s = store()
        tid = self._report_task(s)
        repo, why = terminal.guess_repo(s, tid, self.PROFILE)
        self.assertEqual(repo, 'ldbumble/taskuary')
        self.assertIn('own', why)

    def test_a_task_that_matches_nothing_refuses_rather_than_opening_the_default_folder(self):
        s = store()
        s.save_doc('soul', self.SOUL, 'owner')
        tid = s.create_task({'Title': 'Henkin Medicaid overpayment', 'Kind': 'coding', 'Status': 'open'}, 'o')
        s.add_message({'TaskId': tid, 'ExternalId': 'm1', 'Channel': 'email', 'Subject': 'Henkin Medicaid overpayment',
                       'FromName': 'Rivka', 'FromEmail': 'rivka@ours.com', 'SentAt': ago(1),
                       'BodyText': 'The county says Mrs Henkin was overpaid; please sort out the refund with them.',
                       'Status': 'routed'})
        repo, why = terminal.guess_repo(s, tid, self.PROFILE)
        self.assertIsNone(repo, f'nothing here names a checkout (why={why})')
        s.upsert_agent('coder', 'coding', 'cli', json.dumps(self.PROFILE))
        with self.assertRaises(ValueError) as caught:
            terminal.open_session(s, 'coder', tid, None, None)
        self.assertIn('could not tell which checkout', str(caught.exception))
        self.assertIn('Pick the repository', str(caught.exception))
        self.assertNotIn('FanApp', str(caught.exception).split('would put an agent in')[0])

    def test_a_repo_the_owner_tagged_always_wins(self):
        s = store()
        tid = self._report_task(s)
        s.update_task(tid, {'Tags': 'repo:mfaVita/TopE'}, 'owner')
        repo, why = terminal.guess_repo(s, tid, self.PROFILE)
        self.assertEqual((repo, why), ('mfaVita/TopE', 'tagged on the task'))


class SettingProposalTests(unittest.TestCase):
    """A standing instruction that belongs in a SWITCH is written there - but never on the
    assistant's own say-so (the owner, 2026-09-03: "yes do it that way ask user if it can change
    setttings")."""

    def test_a_switch_the_owner_names_is_proposed_and_nothing_changes_until_they_approve(self):
        from taskuary import proposals, verdicts
        s = store()
        s.save_connector({'Type': 'github', 'Name': 'GitHub', 'Secret': 'x', 'Active': 1,
                          'ConfigJson': json.dumps({'use_as_tracker': True})}, 'o')
        out = say(s, 'turn PRs into timeline items not tasks')
        self.assertEqual(out['decision']['verb'], 'setting')
        rid = out['decision']['reviewId']
        rv = s.get_review(rid)
        self.assertEqual((rv['Kind'], rv['Status']), ('action', 'pending'))
        self.assertIn('you asked for this setting', rv['Reason'])
        self.assertIn('put it in front of you rather than touching it', out['say'])
        self.assertTrue(json.loads(s.get_connector_by_type('github')['ConfigJson'])['use_as_tracker'],
                        'nothing changed on the proposal alone')
        # …and it waits in the pipe, so it cannot scroll away
        self.assertEqual([(i['kind'], i['lane']) for i in pile(s)], [('action', 'approve')])
        with mock.patch.object(terminal, 'live_sessions', return_value=[]):
            res = verdicts.decide(s, s.get_review(rid), 'approve', None, None, 'owner')
        self.assertEqual(res['status'], 'approved')
        self.assertFalse(json.loads(s.get_connector_by_type('github')['ConfigJson'])['use_as_tracker'])
        self.assertEqual(s.get_settings().get('agent_issues_enabled'), '0')

    def test_a_number_the_owner_says_out_loud_is_the_value(self):
        s = store()
        out = say(s, 'check the mail every 5 minutes')
        self.assertEqual(out['decision']['changes'], [{'name': 'poll_minutes', 'value': '5'}])
        self.assertNotEqual(s.get_settings().get('poll_minutes'), '5', 'still theirs to approve')

    def test_only_the_allow_listed_switches_can_ever_be_named(self):
        from taskuary import proposals
        s = store()
        for bad in ('agent_push_enabled', 'github_replies_ok', 'owner_email', 'agent_token'):
            ok, why = proposals.validate(s, {'action': 'settings', 'changes': [{'name': bad, 'value': '1'}]})
            self.assertFalse(ok, bad)
            self.assertIn('not a switch a proposal may touch', why)
        ok, why = proposals.validate(s, {'action': 'settings', 'changes': [{'name': 'poll_minutes', 'value': 'soon'}]})
        self.assertFalse(ok); self.assertIn('whole number', why)
        ok, _ = proposals.validate(s, {'action': 'settings', 'changes': [{'name': 'coder_auto_enabled', 'value': False}]})
        self.assertTrue(ok)

    def test_the_assistant_never_writes_a_setting_itself(self):
        """Whatever the words, the only road to a written setting is proposals.execute behind an
        approval - so the chat path must not touch the store."""
        s = store()
        before = dict(s.get_settings())
        for words in ('stop auto-starting the coder', 'never read my calendar', 'the pipe should hold at most 15'):
            say(s, words)
        after = dict(s.get_settings())
        self.assertEqual({k: v for k, v in after.items() if k in ('coder_auto_enabled', 'calendar_enabled', 'funnel_max')},
                         {k: v for k, v in before.items() if k in ('coder_auto_enabled', 'calendar_enabled', 'funnel_max')})
        self.assertEqual(len([r for r in s.list_reviews('pending') if r['Kind'] == 'action']), 3)


# ── the buttons the assistant points at: every one of them, through the API ──────────────────
class ApiActionsTests(unittest.TestCase):
    """The assistant never acts itself - it says what happens and the card's button does it. So each
    of those doors is opened here exactly as the page opens it, and the effect is checked."""

    def client(self, s):
        patches = [mock.patch.object(server, 'store', s), mock.patch.dict(terminal.SESSIONS, {}, clear=True),
                   mock.patch.object(ingest, '_spawn')]
        for pp in patches: pp.start(); self.addCleanup(pp.stop)
        return TestClient(server.app)

    def _ask(self, s, **kw):
        with mock.patch.object(ingest, '_spawn'):
            return arrive(s, llm=brain('task', 'coding'), **kw)

    def test_not_ours_files_the_message_and_the_sender_verdict_is_written_down(self):
        s = store(); out = self._ask(s); c = self.client(s)
        self.assertEqual(c.post(f"/api/messages/{out['message_id']}/file", json={'learn': False}).status_code, 200)
        self.assertEqual(s.get_message(out['message_id'])['Status'], 'ignored')   # the owner's own verdict on the thread
        self.assertEqual(s.list_memories(active_only=True), [])                    # this once teaches nothing
        gone = s.get_task(out['task_id'])                                         # a task that existed only for
        self.assertTrue(gone is None or gone['Status'] in ('dropped', 'done'), gone)   # this mail is removed with it
        self.assertEqual(pile(s), [])                                             # and off the pile
        two = self._ask(s, subject='Another refund', conv='c:two', hours=2)
        r = c.post(f"/api/messages/{two['message_id']}/not-mine", json={'scope': 'sender'})
        self.assertEqual(r.status_code, 200)
        notes = s.list_memories(active_only=True)
        self.assertTrue(notes, 'the verdict is remembered, not just applied once')
        self.assertTrue(any('craig@vendor.com' in (n['ScopeKey'] or '').lower() or 'refund' in (n['Note'] or '').lower()
                            for n in notes), [dict(n) for n in notes])
        self.assertIn(s.get_message(two['message_id'])['Status'], ('ignored', 'filed'))

    def test_dispatch_hands_the_mail_to_a_coding_agent_with_the_owners_words(self):
        s = store(); out = self._ask(s); c = self.client(s)
        s.upsert_agent('coder', 'coding', 'cli', '{"cmd": "claude"}')
        with mock.patch.object(server, 'start_session', return_value={'sid': 's1', 'agent': 'coder'}) as start:
            r = c.post(f"/api/messages/{out['message_id']}/dispatch",
                       json={'agent': 'coder', 'instruction': 'find out why it drops inter-company rows'})
        self.assertEqual(r.status_code, 200, r.text)
        self.assertTrue(start.called)
        tid, agent, instruction = start.call_args[0][1], start.call_args[0][2], start.call_args[0][4]
        self.assertEqual((tid, agent), (out['task_id'], 'coder'))
        self.assertIn('inter-company', instruction)                     # the owner's words reach the session
        self.assertEqual(s.get_task(tid)['Kind'], 'coding')

    def test_mine_takes_the_agent_off_it_and_keeps_the_task(self):
        s = store(); out = self._ask(s); c = self.client(s)
        r = c.post(f"/api/messages/{out['message_id']}/mine", json={'kind': 'task'})
        self.assertEqual(r.status_code, 200)
        t = s.get_task(out['task_id'])
        self.assertEqual((t['Status'], t['Assignee']), (t['Status'], 'owner'))    # theirs now, nobody sent at it
        self.assertNotIn('agent:', str(t['Assignee']))

    def test_answering_an_agent_queues_the_words_for_it(self):
        s = store(); out = self._ask(s); c = self.client(s)
        from taskuary import waitroom
        with mock.patch.object(waitroom, 'deliver', return_value={'delivered': 0}):
            r = c.post(f"/api/tasks/{out['task_id']}/waitroom", json={'text': 'yes, drop the old rows'})
        self.assertEqual(r.status_code, 200, r.text)
        queued = c.get(f"/api/tasks/{out['task_id']}/waitroom").json()
        self.assertTrue(any('drop the old rows' in str(x) for x in queued.get('data', [])))

    def test_a_draft_can_be_redrafted_dismissed_or_sent(self):
        s = store()
        out = arrive(s, subject='Where is the June invoice?', body='Can you send it?', llm=brain('reply_only', None))
        rid = s.pending_review(out['task_id'])['ReviewId']
        c = self.client(s)
        with mock.patch('taskuary.responder.draft_reply', return_value='Attached - sorry for the wait.'):
            r = c.post(f'/api/reviews/{rid}/draft')
        self.assertEqual(r.status_code, 200)
        self.assertIn('Attached', s.get_review(rid)['DraftText'])
        r = c.post(f'/api/reviews/{rid}/decide', json={'verb': 'no_reply', 'final_text': None, 'note': 'nothing to say'})
        self.assertEqual(r.status_code, 200)
        self.assertNotEqual(s.get_review(rid)['Status'], 'pending')        # dismissed: nothing goes out
        self.assertIsNone(s.pending_review(out['task_id']))

    def test_an_agents_proposed_action_runs_only_on_the_owners_yes(self):
        s = store(); out = self._ask(s); c = self.client(s)
        rid = s.add_review({'TaskId': out['task_id'], 'MessageId': out['message_id'], 'Kind': 'action',
                            'Status': 'pending',
                            'DraftText': json.dumps({'action': 'write_playbook', 'slug': 'pto-import',
                                                     'text': '# PTO import' + chr(10) + 'steps', 'why': 'it repeats'}),
                            'Reason': 'the agent proposes a playbook'})
        funnel.invalidate()
        self.assertEqual([(i['kind'], i['lane']) for i in pile(s)], [('action', 'approve')])
        with mock.patch('taskuary.proposals.execute', return_value={'wrote': 'pto-import'}) as ran:
            r = c.post(f'/api/reviews/{rid}/decide', json={'verb': 'approve', 'final_text': None, 'note': None})
        self.assertEqual(r.status_code, 200, r.text)
        self.assertTrue(ran.called, 'the approval is what runs it - never the proposal itself')
        self.assertEqual(s.get_review(rid)['Status'], 'approved')
        # …and a dismissal runs nothing at all
        rid2 = s.add_review({'TaskId': out['task_id'], 'MessageId': out['message_id'], 'Kind': 'action',
                             'Status': 'pending', 'DraftText': json.dumps({'action': 'write_playbook', 'slug': 'x', 'text': '#x'}),
                             'Reason': 'another proposal'})
        with mock.patch('taskuary.proposals.execute') as never:
            c.post(f'/api/reviews/{rid2}/decide', json={'verb': 'reject', 'final_text': None, 'note': 'no'})
        self.assertFalse(never.called)
        self.assertTrue(any('nothing was done' in (x['Body'] or '') for x in s.list_comments(out['task_id'])))

    def test_splitting_a_second_ask_out_of_one_thread_gives_it_its_own_task(self):
        s = store(); out = self._ask(s); c = self.client(s)
        second = s.add_message({'TaskId': out['task_id'], 'ExternalId': 'x:second', 'ConversationId': 'c:Can you fix the export?',
                                'Channel': 'email', 'Subject': 'Can you fix the export?', 'FromName': 'Craig Neiswanger',
                                'FromEmail': 'craig@vendor.com', 'SentAt': ago(0), 'Status': 'routed',
                                'BodyText': 'Also, please add Priya to the payroll distribution list.'})
        r = c.post(f'/api/messages/{second}/split', json={'kind': 'coding'})
        self.assertEqual(r.status_code, 200)
        new = r.json()['taskId']
        self.assertNotEqual(new, out['task_id'])
        self.assertEqual(s.get_message(second)['TaskId'], new)             # the ask moved, the thread stayed
        self.assertTrue(any('Split' in (x['Body'] or '') for x in s.list_comments(out['task_id'])))

    def test_a_report_can_be_rerun_from_the_chat_and_the_run_is_recorded(self):
        s = store()
        sid = s.save_source({'Channel': 'report', 'Address': 'Nightly export', 'Owner': 'o', 'Active': 1,
                             'ConfigJson': json.dumps({'type': 'agent', 'title': 'Nightly export'})}, 'o')
        c = self.client(s)
        with mock.patch.object(server, 'run_report_source') as run:      # queued on a thread, so wait for it
            r = c.post(f'/api/reports/{sid}/rerun')
            for _ in range(50):
                if run.called: break
                import time; time.sleep(0.02)
        self.assertEqual(r.status_code, 200, r.text)
        self.assertEqual(r.json()['title'], 'Nightly export')            # …and it says which report it queued
        self.assertTrue(run.called, 'the report actually ran')

    def test_stopping_an_agent_ends_the_session_and_leaves_the_task_open(self):
        s = store(); out = self._ask(s); c = self.client(s)
        tid = out['task_id']
        s.update_task(tid, {'Status': 'in_progress'}, 'router')
        live = mock.Mock(sid='s1', alive=True, label='coder', agent='coder', task_id=tid)
        with mock.patch.object(server.hub_term, 'session_for', return_value=live), \
             mock.patch.object(server.hub_term, 'close', return_value=True) as close:
            r = c.post(f'/api/tasks/{tid}/agent/stop')
        self.assertEqual(r.status_code, 200, r.text)
        self.assertTrue(close.called and r.json()['stopped'])
        # the task is NOT closed - stopping an agent is not finishing the work - but it is no longer
        # being worked either: 'in_progress' with no session held it in the pipe's working lane for
        # ever, saying "agent working, nothing for you" (the 2026-09-03 break test)
        self.assertEqual(s.get_task(tid)['Status'], 'open')
        self.assertNotIn(tid, funnel.working_tids(s))
        self.assertTrue(any('Stopped the coder session' in (x['Body'] or '') for x in s.list_comments(tid)))

    def test_wrapping_up_files_the_report_and_closes_the_task(self):
        s = store(); out = self._ask(s); c = self.client(s)
        tid = out['task_id']
        # wrapping up needs a transcript to turn into the report - that IS the ending
        s.add_transcript(tid, 's1', 'coder: fixed the export and deployed.', 'coder', 'C:/repo')
        with mock.patch('taskuary.responder.draft_for_review', return_value='Fixed - shipping tonight.'):
            r = c.post(f'/api/tasks/{tid}/wrap', json={'close': True})
        self.assertEqual(r.status_code, 200, r.text)
        t = s.get_task(tid)
        self.assertIn(t['Status'], ('done', 'waiting'))                      # closed, or waiting on the reply it drafted
        self.assertTrue(any(str(x['Body'] or '').startswith('CODER REPORT') for x in s.list_comments(tid)),
                        'the transcript became the report on THIS task')

    def test_the_pile_says_when_the_item_on_the_table_is_gone(self):
        """A sent reply leaves the pile - and the page holding that key has to be told, or it keeps
        drawing "reply pending" over a draft that already went (the owner, 2026-09-03)."""
        s = store()
        out = arrive(s, subject='Where is the June invoice?', body='Can you send it?', llm=brain('reply_only', None))
        rid = s.pending_review(out['task_id'])['ReviewId']
        key = f'review:{rid}'
        c = self.client(s)
        got = c.get('/api/funnel/pile', params={'current': key}).json()
        self.assertEqual((got['current'] or {}).get('key'), key)             # still a thing
        sent = {'ok': True, 'to': 'craig@vendor.com', 'subject': 'RE:', 'provider': 'test', 'channel': 'email'}
        from taskuary import verdicts
        with mock.patch('taskuary.outbound.reply_to_message', return_value=sent), \
             mock.patch.object(terminal, 'live_sessions', return_value=[]):
            verdicts.decide(s, s.get_review(rid), 'approve', 'Attached.', None, 'owner')
        funnel.invalidate()
        gone = c.get('/api/funnel/pile', params={'current': key}).json()
        self.assertIsNone(gone['current'], 'the page is told the table is clear')
        self.assertEqual(gone['items'], [])

    def test_a_closed_agent_cannot_become_a_current_funnel_card(self):
        s = store(); out = self._ask(s)
        tid = out['task_id']
        s.add_comment(tid, 'coder', 'agent', 'CODER REPORT' + chr(10) + 'Summary: the export is fixed and shipping tonight.')
        s.update_task(tid, {'Status': 'done'}, 'coder')
        with mock.patch.object(terminal, 'live_sessions', return_value=[]):
            self.assertEqual(funnel.build(s)['items'], [])
        c = self.client(s)
        got = c.get('/api/funnel/pile', params={'force': True, 'current': f'done:{tid}'}).json()
        self.assertIsNone(got['current'])

    def test_a_task_closed_from_the_chat_is_closed_on_the_board_too(self):
        s = store(); out = self._ask(s)
        item = pile(s)[0]
        say(s, 'close it', key=item['key'])
        c = self.client(s)
        got = c.get(f"/api/tasks/{out['task_id']}").json()['task']
        self.assertEqual(got['Status'], 'done')                            # one record, both doors


if __name__ == '__main__':
    unittest.main()
