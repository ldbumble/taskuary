"""One job, one task (the owner, 2026-09-25, triage step 1).

T1/T2 - a line on the thread of a CLOSED task goes back to that task: filed when it only says thanks, reopening it
when it needs the owner. T4 - triage is shown the open and recently closed work an arrival touches and may answer
that it IS one of them (same_as). T3 - Taskuary's own reports and ideas count as one sender for the exact repeat.
T5 - a message that reached its task before a later step failed is never judged again as new work."""
import json, unittest
from unittest import mock

from taskuary import ingest, triage
from taskuary.store import MemoryStore, task_ref
from tests import fake_embed


def brain(intent, same_as=None, title=None, seen=None, kind='task', **extra):
    """Triage, scripted: the verdict it gives, and whether it names a task this message is the same as."""
    def llm(system, user, **k):
        if seen is not None: seen.append({'sys': system, 'usr': user})
        out = {'intent': intent, 'why': 'scripted', 'title': title or 'Fix the nightly export', 'summary': 's'}
        if intent == 'task': out['kind'] = kind
        if same_as is not None: out['same_as'] = same_as
        return json.dumps({**out, **extra})
    return llm


def mail(s, ext, llm, conv, subject='Nightly export drops rows', body='The export drops inter-company rows again.',
         frm='erin@northwind.example', channel='email'):
    with mock.patch.object(ingest, '_spawn'):
        return ingest.ingest_message(s, {'external_id': ext, 'channel': channel, 'from_email': frm, 'from_name': 'Erin Blake',
                                         'conversation_id': conv, 'subject': subject, 'body': body,
                                         'sent_at': '2026-09-25 09:00:00'}, llm=llm)


class SameAsTests(unittest.TestCase):
    def test_triage_is_shown_the_open_work_and_asked_whether_this_is_it(self):
        s = MemoryStore()
        first = mail(s, 'a', brain('task'), conv='c1')
        seen = []
        mail(s, 'b', brain('task', seen=seen), conv='c2')                     # a new thread, the same subject
        self.assertIn('same_as', seen[-1]['sys'])
        self.assertIn(f'"tid": {first["task_id"]}', seen[-1]['usr'])

    def test_same_as_an_open_task_joins_it_instead_of_a_second_task(self):
        s = MemoryStore()
        first = mail(s, 'a', brain('task'), conv='c1')
        again = mail(s, 'b', brain('task', same_as=first['task_id'], title='Export still drops rows'), conv='c2')
        self.assertEqual((again['status'], again['task_id']), ('routed', first['task_id']))
        self.assertEqual(len(s.list_tasks()), 1)
        self.assertIn('the same as', s.message_routes(again['message_id'])[-1]['Reason'])

    def test_one_pull_request_never_joins_another_ones_task(self):
        """The owner, 2026-09-28: two docs PRs from one contributor read alike, and triage filed #121 into #120's task.
        A pull request or an issue is its own job; a new push on the SAME one still joins its task."""
        # ...said to TRIAGE as a rule it applies, not enforced over its answer (2026-10-08): it is told, it answers null
        s = MemoryStore()
        seen = []
        first = mail(s, 'pr120', brain('task'), conv='gh:northwind/portal#120', channel='github', subject='northwind/portal#120 docs: fix the example')
        other = mail(s, 'pr121', brain('task', seen=seen), conv='gh:northwind/portal#121', channel='github',
                     subject='northwind/portal#121 docs: fill in the descriptions')
        self.assertIn('a different pull request or issue number', seen[-1]['sys'])    # a sign it is new (the guide, section 3)
        self.assertNotEqual(other['task_id'], first['task_id'])
        again = mail(s, 'pr120-push', brain('task', same_as=first['task_id']), conv='gh:northwind/portal#120', channel='github',
                     subject='northwind/portal#120 docs: fix the example')
        self.assertEqual(again['task_id'], first['task_id'])

    def test_same_as_a_closed_task_reopens_it_and_an_fyi_leaves_it_closed(self):
        s = MemoryStore()
        first = mail(s, 'a', brain('task'), conv='c1'); tid = first['task_id']
        s.update_task(tid, {'Status': 'done'}, 'owner')
        note = mail(s, 'b', brain('fyi', same_as=tid, title='Export report, same as before'), conv='c2')
        self.assertEqual((note['status'], note['task_id']), ('filed', tid))
        self.assertEqual(s.get_task(tid)['Status'], 'done')
        back = mail(s, 'c', brain('task', same_as=tid, title='The export fix did not hold'), conv='c3')
        self.assertEqual((back['status'], back['task_id']), ('routed', tid))
        self.assertEqual(s.get_task(tid)['Status'], 'open')
        self.assertEqual(len(s.list_tasks()), 1)

    def test_a_report_run_is_never_filed_away_on_yesterdays_closed_task(self):
        """A daily report shares one conversation, so triage saw yesterday's closed task and called today's run "the
        same", fyi - and filing it on a closed task put it nowhere: the morning report never showed (2026-10-01). A
        run judged fyi lands as its own row, where the report's Timeline line decides; an OPEN task still takes it."""
        s = MemoryStore()
        run = lambda ext, llm: mail(s, ext, llm, conv='report:7', channel='report', frm='', subject='Morning digest - 40 lines')
        first = run('report:7:mon', brain('task', title='Review the morning digest')); tid = first['task_id']
        s.update_task(tid, {'Status': 'done'}, 'owner')
        # the rule is TRIAGE's to apply (2026-10-08) - told, it answers null; code no longer unjoins its answer
        seen = []
        today = run('report:7:tue', brain('fyi', title='Morning digest', seen=seen))
        self.assertIn('a report run that needs nothing from the owner is better as its own quiet row than filed on a closed task', seen[-1]['sys'])
        self.assertEqual((today['status'], today['task_id']), ('filed', None), 'today\'s run vanished into the closed task')
        self.assertEqual(s.get_task(tid)['Status'], 'done')
        # ...and an OPEN task does not take it either (the owner, 2026-10-16: "if triage finds something that is already a task
        # that triage should not make it a task"): the run stays its own row and the task gets a note that the report names it
        s.update_task(tid, {'Status': 'open'}, 'owner')
        again = run('report:7:wed', brain('fyi', same_as=tid, title='Morning digest'))
        self.assertEqual((again['status'], again['task_id'], again['mentions']), ('feed', None, tid))

    def test_a_task_it_was_never_shown_joins_nothing(self):
        s = MemoryStore()
        first = mail(s, 'a', brain('task'), conv='c1')
        other = mail(s, 'b', brain('task', same_as=9999, title='Something else entirely'), conv='c2',
                     subject='Printer on floor 3', body='The printer is jammed.', frm='omar@northwind.example')
        self.assertEqual(other['status'], 'created'); self.assertNotEqual(other['task_id'], first['task_id'])


class SomeoneElsesAskTests(unittest.TestCase):
    """A stranger's pull request that closes the owner's issue shares every word of it, and triage joined the two -
    reopening the owner's finished task, its agent session and its old draft, now addressed to the stranger
    (2026-09-25). The judge is told who each task is from, and that another person's new thread is a new ask."""

    def test_triage_sees_the_task_is_someone_elses(self):
        s = MemoryStore()
        issue = mail(s, 'i', brain('task', title='Split long Discord replies'), conv='gh:northwind/ledger#53',
                     frm='alex@northwind.example', subject='Discord replies are cut off at 2,000 characters')
        s.update_task(issue['task_id'], {'Status': 'done'}, 'owner')
        seen = []
        with fake_embed.meaning({'discord': ['discord replies']}):          # the two are alike in meaning (a stand-in embedder)
            mail(s, 'p', brain('task', seen=seen), conv='gh:northwind/ledger#65', frm='ray@vendor.example',
                 subject='Send long Discord replies without truncation', body='Discord replies are cut off at 2,000 characters. Closes #53.')
        self.assertIn('"from": "someone else: alex@northwind.example - not this sender"', seen[-1]['usr'])
        self.assertIn("someone else's own ask on a similar subject", seen[-1]['sys'])

    def test_the_same_sender_again_is_told_so(self):
        s = MemoryStore()
        mail(s, 'a', brain('task'), conv='c1')
        seen = []
        mail(s, 'b', brain('task', seen=seen), conv='c2')
        self.assertIn('"from": "this sender"', seen[-1]['usr'])

    def test_their_pull_request_left_unjoined_is_a_task_of_its_own(self):
        s = MemoryStore()
        issue = mail(s, 'i', brain('task'), conv='gh:northwind/ledger#53', frm='alex@northwind.example')
        s.update_task(issue['task_id'], {'Status': 'done'}, 'owner')
        pr = mail(s, 'p', brain('task', title='Review the Discord chunking PR'), conv='gh:northwind/ledger#65', frm='ray@vendor.example')
        self.assertEqual(pr['status'], 'created'); self.assertNotEqual(pr['task_id'], issue['task_id'])
        self.assertEqual(s.get_task(issue['task_id'])['Status'], 'done')


class ChatReopensTests(unittest.TestCase):
    """A closed task comes back only with NEW work (the owner, 2026-10-15: "it should update the task description if something new
    was added to task, if not and it was just comment don't reopen this"). A colleague's "sure" to a meeting time the owner offered
    later in the same chat reopened the morning's closed timesheet task, because triage read it as a reply."""
    def setUp(self):
        self.s = MemoryStore()
        self.chat = lambda ext, body, llm: mail(self.s, ext, llm, conv='room-1', subject='', body=body, channel='teams')
        first = self.chat('t1', 'Can you send me the August statement?', brain('reply_only', title='Send Erin the August statement'))
        self.tid, self.mid1 = first['task_id'], first['message_id']
        self.s.update_task(self.tid, {'Status': 'done'}, 'owner')

    def joins(self, intent, title, summary='s'):
        tid, mid1 = self.tid, self.mid1
        return lambda system, user, **k: json.dumps({'intent': intent, 'why': 'scripted', 'title': title, 'summary': summary,
                                                       'relationship': 'answers', 'related_message_ids': [mid1], 'existing_task_id': tid,
                                                       'same_problem': True, **({'kind': 'task'} if intent == 'task' else {})})

    def test_a_reply_on_a_closed_ask_is_kept_on_it_and_it_stays_closed(self):
        back = self.chat('t2', 'sure, tomorrow morning works', self.joins('reply_only', 'Erin agrees to tomorrow morning'))
        self.assertEqual((back['status'], back['task_id']), ('filed', self.tid))
        t = self.s.get_task(self.tid)
        self.assertEqual((t['Status'], t['Title']), ('done', 'Send Erin the August statement'))
        self.assertIn('stays closed', self.s.message_routes(back['message_id'])[-1]['Reason'])
        self.assertFalse(self.s.pending_review(self.tid))                     # nothing drafted for a task that is not back

    def test_new_work_on_a_closed_ask_reopens_it_and_says_what_is_asked_now(self):
        back = self.chat('t2', 'and the September one too please', self.joins('task', 'Send Erin the September statement',
                                                                              'Erin also needs the September statement.'))
        self.assertEqual((back['status'], back['task_id']), ('attached', self.tid))
        t = self.s.get_task(self.tid)
        self.assertEqual((t['Status'], t['Title'], t['Summary']), ('open', 'Send Erin the September statement', 'and the September one too please'))   # his line's own words
        self.assertEqual(len(self.s.list_tasks()), 1)

    def test_a_same_as_reply_on_a_closed_task_stays_closed_too(self):
        r = mail(self.s, 'm2', brain('reply_only', same_as=self.tid, title='Erin asks if it went out'), conv='other')
        self.assertEqual((r['status'], r['task_id']), ('filed', self.tid))
        self.assertEqual(self.s.get_task(self.tid)['Status'], 'done')


class OwnChannelRepeatTests(unittest.TestCase):
    def test_the_advisor_and_a_report_on_one_event_make_one_task(self):
        s = MemoryStore()
        a = mail(s, 'r1', brain('task', title='Nightly export failed'), conv='report:1', channel='report', frm='',
                 subject='Process error check', body='The nightly export failed at 02:00.')
        # one task because TRIAGE says this idea IS that task - shown it as open work - not an exact-title check (2026-10-08)
        seen = []
        with fake_embed.meaning({'nightly export': ['nightly export']}):     # the run and the idea are alike in meaning (a stand-in embedder)
            b = mail(s, 'i1', brain('task', same_as=a['task_id'], title='Nightly export failed', seen=seen), conv='report:140:idea:export',
                     channel='assistant', frm='', subject='Idea', body='The nightly export failed - worth a look.')
        self.assertIn(f"TQ-{a['task_id']:04d}", seen[-1]['usr'])
        self.assertEqual(b['task_id'], a['task_id'])
        self.assertEqual(len(s.list_tasks()), 1)


class LaterStepFailedTests(unittest.TestCase):
    def test_a_message_that_reached_its_task_is_not_retriaged_when_a_later_step_breaks(self):
        s = MemoryStore()
        mid = s.add_message({'ExternalId': 'x1', 'Channel': 'email', 'FromEmail': 'erin@northwind.example', 'Subject': 'Fix the export',
                             'BodyText': 'please fix', 'ConversationId': 'c9', 'SentAt': '2026-09-25 09:00:00', 'Status': 'triaging'})
        tid = s.create_task({'Title': 'Fix the export', 'Kind': 'task', 'Status': 'open'}, 't')
        def boom(store, msg, **k):
            store.place_message(msg['_mid'], tid, 'routed')          # triaged onto its task...
            raise RuntimeError('agent start failed')                  # ...then a later step broke
        with mock.patch.object(ingest, 'ingest_message', side_effect=boom):
            ingest.drain(s)
        m = s.get_message(mid)
        self.assertEqual((m['Status'], m['TaskId']), ('routed', tid))
        self.assertTrue(any('a later step failed' in c['Body'] for c in s.list_comments(tid)))
        self.assertEqual(s.stranded_triage_failures(10), [])


class CoveredTests(unittest.TestCase):
    """A report's run that holds one new failure beside one an open task already has (the owner, 2026-11-15): triage is asked which open
    tasks hold a part of it, by the ids it was shown, and the run's own task is for the rest."""
    def test_triage_names_the_open_tasks_that_hold_a_part_and_only_ones_it_was_shown(self):
        s = MemoryStore()
        first = mail(s, 'a', brain('task', title='Investigate the Payworth export 403'), conv='c1', subject='Payworth export failed')
        seen = []
        run = mail(s, 'report:1:b', brain('task', title='Investigate the Trainly export 400', seen=seen, kind='general', covered=[first['task_id'], 999, 'x']),
                   conv='report:1', channel='report', subject='Process error check - 2 failures',
                   body='Trainly report export: HTTP 400\nPayworth user export: 2 of 81 sites failed, HTTP 403', frm=None)
        self.assertIn('**covered**', seen[-1]['sys']); self.assertIn('each is weighed by itself', seen[-1]['sys'])
        self.assertEqual(json.loads(s.message_routes(run['message_id'])[-1]['VerdictJson'])['covered'], [first['task_id']])
        self.assertEqual((run['status'], len(s.list_tasks())), ('created', 2))
        self.assertTrue(any(c['Body'].startswith('A report mentions this') or 'mentions this' in c['Body'] for c in s.list_comments(first['task_id'])))

    def test_the_one_it_is_is_not_also_a_part_of_it(self):
        s = MemoryStore()
        first = mail(s, 'a', brain('task'), conv='c1')
        again = mail(s, 'b', brain('task', same_as=first['task_id'], covered=[first['task_id']]), conv='c2')
        self.assertNotIn('covered', json.loads(s.message_routes(again['message_id'])[-1]['VerdictJson']))

if __name__ == '__main__':
    unittest.main()


class RetitleTests(unittest.TestCase):
    """The owner, 2026-10-15: a chat kept joining one task and its title stayed the first message's ("asks to come over today")
    after the talk moved on. A real ask joined to the task brings triage's title and summary for it."""
    def test_an_ask_refined_on_a_chat_task_renames_it_and_keeps_the_old_name_in_a_note(self):
        """Only when the task's OWN ask moved (refines) since 2026-10-28 - a separate subject is its own task now."""
        s = MemoryStore()
        first = mail(s, 'a', brain('task', title='Erin asks to come over today'), conv='c1', channel='whatsapp')
        tid = first['task_id']
        mail(s, 'b', brain('task', same_as=tid, refines=True, same_problem=True, title='Erin asks to come over tomorrow instead'), conv='c1', channel='whatsapp',
             body='Actually make it tomorrow')
        t = s.get_task(tid)
        self.assertEqual(t['Title'], 'Erin asks to come over tomorrow instead')
        self.assertTrue(any('Now about: Erin asks to come over tomorrow instead (was: Erin asks to come over today)' in (c.get('Body') or '')
                            for c in s.list_comments(tid)))

    def test_a_line_that_only_joins_keeps_the_title(self):
        s = MemoryStore()
        tid = mail(s, 'a', brain('task', title='Erin asks to come over today'), conv='c1', channel='whatsapp')['task_id']
        mail(s, 'b', brain('task', same_as=tid, title='Erin asks for parking details'), conv='c1', channel='whatsapp', body='where do I park?')
        self.assertEqual(s.get_task(tid)['Title'], 'Erin asks to come over today')
        self.assertFalse(any('Now about' in (c.get('Body') or '') for c in s.list_comments(tid)))

    def test_a_task_the_owner_wrote_and_a_mere_fyi_keep_their_title(self):
        s = MemoryStore()
        tid = s.create_task({'Title': 'My own job', 'Summary': 'mine', 'Kind': 'task', 'Source': 'manual'}, 'owner')
        mail(s, 'b', brain('task', same_as=tid, title='Something else'), conv='c9', channel='whatsapp')
        self.assertEqual(s.get_task(tid)['Title'], 'My own job')                    # not made by this channel
        first = mail(s, 'c', brain('task', title='The first ask'), conv='c2', channel='whatsapp')
        mail(s, 'd', brain('fyi', same_as=first['task_id'], title='Thanks'), conv='c2', channel='whatsapp')
        self.assertEqual(s.get_task(first['task_id'])['Title'], 'The first ask')     # an fyi adds nothing to rename for


class EmailThreadRetitleTests(unittest.TestCase):
    """The owner, 2026-10-15: a CFO's new ask ("can you export and send the status to the VPOs") arrived on the thread of a task
    closed two days before; it was judged a task and reopened that task - under its old title, so it read as the finished thread
    and was closed again unseen. An email thread stays one task, and the task says what is asked NOW."""
    def test_a_new_ask_on_a_closed_tasks_thread_reopens_it_under_the_new_title(self):
        s = MemoryStore()
        first = mail(s, 'a', brain('task', title='Advise on the missing budget facilities'), conv='t1', subject='Missing Budget')
        tid = first['task_id']
        s.update_task(tid, {'Status': 'done'}, 't')
        mail(s, 'b', brain('task', title='Export the budget status and send it to the VPOs'), conv='t1', subject='RE: Missing Budget',
             body='Can you export and send the status to the VPOs.')
        t = s.get_task(tid)
        self.assertEqual((t['Status'], t['Title']), ('open', 'Export the budget status and send it to the VPOs'))
        self.assertTrue(any('Now about: Export the budget status and send it to the VPOs (was: Advise on the missing budget facilities)'
                            in (c.get('Body') or '') for c in s.list_comments(tid)))

    def test_a_thanks_on_the_thread_keeps_the_title(self):
        s = MemoryStore()
        tid = mail(s, 'a', brain('task', title='Advise on the missing budget facilities'), conv='t1', subject='Missing Budget')['task_id']
        mail(s, 'b', brain('fyi', title='Erin says thanks'), conv='t1', subject='RE: Missing Budget', body='Thanks!')
        self.assertEqual(s.get_task(tid)['Title'], 'Advise on the missing budget facilities')


def asked(intent, asks, title, summary='s', **kw):
    """Triage, scripted, with its own word on whether the line still waits on the owner."""
    return lambda system, user, **k: json.dumps({'intent': intent, 'why': 'scripted', 'title': title, 'summary': summary, 'asks_owner': asks, **kw})


class QuestionReopensTests(unittest.TestCase):
    """The owner, 2026-10-25: "new message came in but it did not reopen task?" A finance task was closed after the owner explained a
    ledger pull to two colleagues; a day later one asked on the same thread what the accounts differ by. Triage read it reply_only, the
    2026-10-15 rule kept every reply_only on the closed task, and a direct question sat on a DONE card with no draft. Triage's own
    asks_owner now tells a question to the owner from a "sure" or a thanks - only the first brings the task back."""
    def setUp(self):
        self.s = MemoryStore()
        self.tid = mail(self.s, 'a', brain('task', title='Investigate the missing ledger accounts'), conv='gl', subject='Missing GL accounts')['task_id']
        self.s.update_task(self.tid, {'Status': 'done'}, 'owner')

    def again(self, llm, body):
        return mail(self.s, 'b', llm, conv='gl', subject='RE: Missing GL accounts', body=body)

    def test_a_question_on_a_closed_email_task_reopens_it_retitles_it_and_drafts(self):
        back = self.again(asked('reply_only', True, 'Erin asks what separates the 4100 accounts', 'Erin Blake wants the difference explained.'),
                          'Can you explain the difference between the 4100 accounts? Is the text after the comma a class?')
        self.assertEqual((back['status'], back['task_id']), ('attached', self.tid))
        t = self.s.get_task(self.tid)
        self.assertEqual((t['Status'], t['Title'], t['Summary']), ('open', 'Erin asks what separates the 4100 accounts',
                                                                   'Can you explain the difference between the 4100 accounts? Is the text after the comma a class?'))
        self.assertEqual(self.s.pending_review(self.tid, kind='draft')['MessageId'], back['message_id'])
        self.assertTrue(any(c['Body'].startswith('Reopened - Erin Blake has a question for you') for c in self.s.list_comments(self.tid)))

    def test_a_thanks_on_a_closed_email_task_stays_filed_and_closed(self):
        back = self.again(asked('reply_only', False, 'Erin thanks Alex for the explanation'), 'Thanks, that makes sense.')
        self.assertEqual((back['status'], back['task_id']), ('filed', self.tid))
        self.assertEqual((self.s.get_task(self.tid)['Status'], self.s.get_task(self.tid)['Title']), ('done', 'Investigate the missing ledger accounts'))
        self.assertFalse(self.s.pending_review(self.tid))

    def test_a_reply_only_without_the_bit_stays_closed_as_before(self):
        back = self.again(brain('reply_only', title='Erin replies'), 'ok')                # an older brain that never answers asks_owner
        self.assertEqual((back['status'], self.s.get_task(self.tid)['Status']), ('filed', 'done'))

    def test_a_question_the_same_as_a_closed_task_reopens_it_too(self):
        r = mail(self.s, 'c', asked('reply_only', True, 'Erin asks which accounts', same_as=self.tid), conv='other')
        self.assertEqual((r['status'], r['task_id'], self.s.get_task(self.tid)['Status']), ('routed', self.tid, 'open'))
        self.assertTrue(self.s.pending_review(self.tid, kind='draft'))


class QuestionWhileClosingTests(unittest.TestCase):
    """Mark done on a live agent closes BEHIND the press (writeup.start, close=True): the write-up runs for seconds and the task closes
    when it ends. A question to the owner that arrived in between landed on a task still open - nothing to reopen - and the close then
    shut it over that question, its draft put down unsent: a mail owed an answer on a closed task, and nothing lit. A mail on a task
    that is closing lands once the close has (the close every road waits on, writeup.wait_for), so the reopen rule reads it."""
    def test_a_question_that_lands_while_mark_done_writes_up_reopens_the_task(self):
        import threading, time
        from taskuary import writeup
        s = MemoryStore()
        tid = mail(s, 'a', brain('task', title='Investigate the missing ledger accounts'), conv='gl', subject='Missing GL accounts')['task_id']
        done = threading.Event()
        with writeup._LOCK: writeup._JOBS[tid] = done
        writeup._begin(tid, 'report', True)                    # Mark done pressed: the write-up runs, the close comes when it ends
        def write_up():
            time.sleep(0.3); s.update_task(tid, {'Status': 'done'}, 'owner'); done.set()
        th = threading.Thread(target=write_up); th.start()
        try:
            back = mail(s, 'b', asked('reply_only', True, 'Erin asks what separates the 4100 accounts'), conv='gl',
                        subject='RE: Missing GL accounts', body='Can you explain the difference between the 4100 accounts?')
        finally:
            th.join(); writeup._JOBS.pop(tid, None); writeup._STATE.pop(tid, None)
        self.assertEqual(back['task_id'], tid)
        self.assertEqual(s.get_task(tid)['Status'], 'open', 'the question was closed under the write-up')
        self.assertTrue(any(c['Body'].startswith('Reopened - Erin Blake has a question for you') for c in s.list_comments(tid)))


class ChatQuestionReopensTests(ChatReopensTests):
    """The chat side of the same rule (2026-10-25): a "sure" stays filed, a question put to the owner brings the task back."""
    def joins(self, intent, title, summary='s', asks=None):
        f = super().joins(intent, title, summary)
        return lambda system, user, **k: json.dumps({**json.loads(f(system, user)), **({} if asks is None else {'asks_owner': asks})})

    def test_a_sure_judged_as_asking_nothing_stays_closed(self):
        back = self.chat('t3', 'sure', self.joins('reply_only', 'Erin agrees', asks=False))
        self.assertEqual((back['status'], self.s.get_task(self.tid)['Status']), ('filed', 'done'))

    def test_a_question_to_the_owner_in_the_chat_reopens_it_and_drafts(self):
        back = self.chat('t3', 'which account did the August one go to?', self.joins('reply_only', 'Erin asks which account the statement used',
                                                                                     'Erin Blake wants to know the account.', asks=True))
        self.assertEqual((back['status'], back['task_id']), ('attached', self.tid))
        t = self.s.get_task(self.tid)
        self.assertEqual((t['Status'], t['Title']), ('open', 'Erin asks which account the statement used'))
        self.assertTrue(self.s.pending_review(self.tid, kind='draft'))


class AsksOwnerVerdictTests(unittest.TestCase):
    def test_triage_is_asked_whether_the_line_waits_on_the_owner_and_its_answer_is_kept(self):
        self.assertIn('asks_owner', triage.verdict_schema()['schema']['properties'])
        self.assertIn('**asks_owner**', triage.SHIPPED)
        out = triage.classify_intent({'from_email': 'erin@northwind.example', 'subject': 'Q', 'body': 'which file?'},
                                     llm=asked('reply_only', True, 'Erin asks which file'))
        self.assertIs(out['asks_owner'], True)


class ReopenedQuestionOnTheRailTests(unittest.TestCase):
    def test_the_reopened_task_is_back_on_the_rail_where_the_line_that_reopened_it_arrived(self):
        """2026-10-25: the closed task had nothing on the rail. Back, it ARRIVES again with the line that reopened it - at the bottom,
        newest - not at its creation: a two-month-old task reopened this morning read "68d" on the table (the owner, 2026-10-28)."""
        from datetime import datetime, timedelta
        from taskuary import funnel
        def ago(h): return (datetime.now() - timedelta(hours=h)).strftime('%Y-%m-%d %H:%M:%S')
        def m(ext, llm, conv, h, body='The export drops rows.'):
            with mock.patch.object(ingest, '_spawn'):
                return ingest.ingest_message(s, {'external_id': ext, 'channel': 'email', 'from_email': 'erin@northwind.example', 'from_name': 'Erin Blake',
                                                 'conversation_id': conv, 'subject': 'Ledger', 'body': body, 'sent_at': ago(h)}, llm=llm)['task_id']
        s = MemoryStore()
        a, b, c = m('a', brain('task', title='Older'), 'c1', 3), m('b', brain('task', title='Ledger accounts'), 'c2', 2), m('c', brain('task', title='Newer'), 'c3', 1)
        s.update_task(b, {'Status': 'done'}, 'owner')
        rail = lambda: [r.get('tid') for r in sorted(funnel.build(s)['items'], key=funnel.order_key)]
        self.assertEqual(rail(), [a, c])
        m('d', asked('reply_only', True, 'Erin asks what separates the accounts'), 'c2', 0, 'Can you explain the difference?')
        self.assertEqual(rail(), [a, c, b])


class OneFailureOneRowFiledTests(unittest.TestCase):
    """THE OWNER, 2026-11-16 ("one failure is one row"): a system's failure mail, each run on its own thread, stood on the rail three times -
    triage filed each as fyi and read each as "failed again". It is shown the sender's notices filed with no task, names the one this repeats
    (same_notice), and the repeat lands on that notice's thread, which the rail folds into one row."""
    def test_three_failure_mails_are_one_row(self):
        from datetime import datetime
        from taskuary import processing_unread as pu
        s, seen = MemoryStore(), []
        def llm(system, user, **k):
            u = json.loads(user); seen.append((system, u))
            shown = u.get('filed_notices') or []
            return json.dumps({'intent': 'fyi', 'why': 'an automated failure notice', 'title': 'Nightly ledger export failed', 'summary': 's',
                               'same_notice': shown[-1]['mid'] if shown and 'ledger export' in u['body'] else None})
        def alert(ext, conv, body):
            with mock.patch.object(ingest, '_spawn'):
                return ingest.ingest_message(s, {'external_id': ext, 'channel': 'email', 'from_email': 'alerts@vendor.example', 'from_name': 'Ledger Alerts',
                    'conversation_id': conv, 'subject': '[Ledger export] Nightly job FAILED', 'body': body,
                    'sent_at': datetime.now().strftime('%Y-%m-%d %H:%M:%S')}, llm=llm)
        got = [alert(f'f{i}', f'fail-{i}', f'The nightly ledger export failed at 0{i}:00 UTC. Run id: {1000 + i}.') for i in (1, 2, 3)]
        self.assertTrue(all(g['status'] == 'filed' for g in got), got)
        self.assertNotIn('filed_notices', seen[0][1])
        self.assertEqual([n['mid'] for n in seen[1][1]['filed_notices']], [got[0]['message_id']])
        self.assertIn('**same_notice**', seen[1][0])
        convs = {s.get_message(g['message_id'])['ConversationId'] for g in got}
        self.assertEqual(convs, {'fail-1'}, 'the repeats land on the first notice\'s thread')
        # ...a different notice from the same sender stays its own row
        other = alert('f9', 'quota-1', 'Your storage quota is 90% full.')
        self.assertEqual(s.get_message(other['message_id'])['ConversationId'], 'quota-1')
        cards = [{'lane': 'fyi', 'kind': 'fyi', 'tid': None, 'cid': s.get_message(g['message_id'])['ConversationId'], 'channel': 'email',
                  'key': f"m{g['message_id']}", 'mid': g['message_id'], 'last_at': ''} for g in got + [other]]
        self.assertEqual(len(pu.fold_fyi_threads(cards)), 2)
