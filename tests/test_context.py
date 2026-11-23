"""The coding agent's context file (context.py): what the hub knows about a task, written to Taskuary's
home and pointed at from the seed - history, past work, the thread. Offline; the
calendar is off and TASKUARY_HOME is the temp home conftest forces.
"""
import json, os, unittest
from unittest import mock
from datetime import datetime, timedelta
from pathlib import Path

from taskuary import context, terminal, wrapup
from taskuary.store import MemoryStore
from tests import fake_embed

ME, DANA = 'owner@ours.com', 'dana@vendor.com'
def _ago(days=0): return (datetime.now() - timedelta(days=days)).strftime('%Y-%m-%d %H:%M:%S')


def _store():
    s = MemoryStore()
    s.set_setting('calendar_enabled', '0', 't'); s.set_setting('coding_auto_enabled', '0', 't')
    return s


def _mail(s, frm, subject, body, days=3, tid=None, conv=None, status='routed'):
    return s.add_message({'TaskId': tid, 'ExternalId': f'x:{frm}:{subject}:{days}', 'ConversationId': conv, 'Channel': 'email', 'SourceName': ME,
                          'Subject': subject, 'FromName': frm.split('@')[0].title(), 'FromEmail': frm, 'SentAt': _ago(days), 'BodyText': body, 'Status': status})


def _closed(s, title, frm, report, days=20):
    tid = s.create_task({'Title': title, 'Kind': 'coding', 'Status': 'done'}, 't')
    _mail(s, frm, title, 'the original ask', days=days, tid=tid)
    s.add_comment(tid, 'agent', 'agent', f'{wrapup.REPORT}\n{report}')
    s._exec('UPDATE task SET ClosedAt=? WHERE TaskId=?', (_ago(days - 1), tid))
    return tid


class PastWorkTests(unittest.TestCase):
    def test_closed_tasks_from_the_same_sender_or_subject_come_back_with_their_reports(self):
        s = _store()
        a = _closed(s, 'Payroll import month wrong', DANA, 'Determination: the import used file date. Actions: routing.py now reads the payroll date.')
        b = _closed(s, 'Ledger export duplicates rows', 'lee@ours.com', 'Actions: dedupe on (id, period) in export.py')
        _closed(s, 'Printer on floor 3', 'sam@ours.com', 'Actions: nothing to do here')
        tid = s.create_task({'Title': 'Ledger export still duplicating', 'Kind': 'coding'}, 't')
        mid = _mail(s, DANA, 'Ledger export still duplicating', 'Same rows twice again.', days=0, tid=tid)
        # ...the same subject is the same MEANING (embeddings), never shared title words
        with fake_embed.meaning({'ledger rows': ['ledger export']}):
            rows = context.past_work(s, s.list_messages(tid), 'Ledger export still duplicating')
        self.assertEqual({r['tid']: r['why'] for r in rows}, {a: 'the same sender', b: 'the same subject'})
        self.assertIn('payroll date', next(r for r in rows if r['tid'] == a)['report'])
        text = context.render_past(rows)
        self.assertIn('TQ-%04d' % b, text); self.assertIn('dedupe on (id, period)', text)
        # ...and with no embedder, structure alone: the sender
        with fake_embed.no_embedder():
            self.assertEqual({r['tid']: r['why'] for r in context.past_work(s, s.list_messages(tid), 'Ledger export still duplicating')},
                             {a: 'the same sender'})

    def test_no_history_means_no_section_and_no_file(self):
        s = _store()
        tid = s.create_task({'Title': 'Brand new thing', 'Kind': 'coding'}, 't')
        self.assertEqual(context.past_work(s, [], 'Brand new thing'), [])
        # ...but who the owner is always rides (SOUL.md + JOB.md, the owner 2026-10-14), so the file is the background alone
        text = context.build(s, tid)
        self.assertNotIn('## Past work', text); self.assertIn('## About the owner', text)
        for name in ('soul', 'job'): s.save_doc(name, '', 't')
        self.assertEqual(context.build(s, tid), '')                      # nothing worth a file
        self.assertIsNone(context.write(s, tid))


# WHAT IS ALREADY KNOWN LEADS THE BRIEF (the owner, 2026-11-16: "It should know to look in [the app] without spending a bunch of tokens"). The live
# shape: a colleague nobody has written to before asks about one user's record in an internal app; the Hub holds notes on that app among
# better-voted ones on other things, closed tasks from OTHER senders settled the same kind of case in its repository, and semantic search is
# off. The agent was handed the best-voted notes on other things and no past task, and explored the databases for twelve minutes
PORTAL = {'portal': ['payroll portal', 'portal login', 'portal record'], 'close': ['month-end close', 'ledger close']}
def _known_world():
    s = _store()
    s.save_doc('soul', '## Repo map\n- **northwind/portal**: the internal web app staff sign in to\n- **northwind/ledger**: the finance backend\n', 't')
    from taskuary import handbook
    for i in range(4):          # better-voted notes about something else - what the old block handed every task
        p = handbook.post(s, f'Month-end close step {i} posts accruals first', 'Run the accrual job before the ledger close.', 'ledger', 'howto', 'agent')
        s.lore_vote(p['LoreId'], 2, 'owner')
    handbook.post(s, 'Payroll portal logins are created from the ledger db table pay_people',
                  'Payroll portal code lives in northwind/portal; the live data is the ledger db table pay_people, not the 2023 archive copy.',
                  'portal', 'system', 'agent')
    old = _closed(s, 'Blank payroll portal login for a new hire', 'gail@northwind.example', 'Cause: the hire had no job code in pay_people. Fixed the row.')
    s._exec('UPDATE task SET Tags=? WHERE TaskId=?', ('agent-repo:northwind/portal', old))
    _closed(s, 'Ledger close ran late', 'ray@northwind.example', 'Actions: moved the close job to 6am.')
    tid = s.create_task({'Title': 'Check incomplete payroll portal record for a new hire', 'Kind': 'coding',
                         'Summary': 'Paula asks why the new hire shows an incomplete payroll portal record'}, 't')
    _mail(s, 'paula@northwind.example', 'Portal help', 'The new hire still shows blank logins in the portal. Pls advise.', days=0, tid=tid)
    s._exec('UPDATE task SET OriginBase=? WHERE TaskId=?', ('owner', tid)); s.set_setting('owner_email', 'alex@northwind.example', 't')  # a colleague's ask
    return s, tid, old


class RecallTests(unittest.TestCase):
    def setUp(self): context._recalled.clear()

    def test_the_brief_leads_with_the_hub_notes_past_tasks_and_repository_this_task_is_about(self):
        s, tid, old = _known_world()
        calls = []
        with fake_embed.reads(PORTAL, calls): text = context.build(s, tid)
        self.assertIn(context.KNOWN_HEAD, text)
        known = text.split(context.KNOWN_HEAD, 1)[1].split('\n## ', 1)[0]
        self.assertIn('Likely repository: northwind/portal - earlier tasks on the same thing worked in it (TQ-%04d)' % old, known)
        self.assertIn('the ledger db table pay_people', known)                       # the Hub note, its body's gist with it
        self.assertIn('TQ-%04d Blank payroll portal login for a new hire' % old, known)
        self.assertIn('no job code in pay_people', known)                             # ...and how it ended
        self.assertNotIn('Month-end close', known); self.assertNotIn('Ledger close ran late', known)
        self.assertLess(text.index(context.KNOWN_HEAD), text.index('## About the owner'))     # read first, before the background
        self.assertEqual(len(calls), 1)                                               # one judgement for every list
        with fake_embed.reads(PORTAL, calls): context.build(s, tid); context.for_prompt(s, tid)
        self.assertEqual(len(calls), 1)                                               # ...made once per task, every turn reuses it

    def test_the_general_agent_reads_it_too_and_never_the_best_voted_notes_on_other_things(self):
        from taskuary import general
        s, tid, old = _known_world()
        with fake_embed.reads(PORTAL): user = general._prompt(s, tid)[1]
        self.assertIn('Already known about this', user); self.assertIn('northwind/portal', user); self.assertIn('pay_people', user)
        self.assertNotIn('Month-end close', user)

    def test_with_embeddings_the_same_picks_come_from_meaning(self):
        s, tid, old = _known_world()
        with fake_embed.meaning(PORTAL): rc = context.recall(s, tid)
        self.assertEqual(rc['past'], [old]); self.assertEqual(rc['repo'], 'northwind/portal')
        self.assertEqual([p['Title'] for p in rc['hub']], ['Payroll portal logins are created from the ledger db table pay_people'])

    def test_no_ai_and_no_embedder_recalls_nothing_rather_than_guessing(self):
        s, tid, old = _known_world()
        from taskuary import llm
        with fake_embed.no_embedder(), mock.patch.object(llm, 'build_llm', return_value=None): text = context.build(s, tid)
        self.assertNotIn(context.KNOWN_HEAD, text); self.assertNotIn('Month-end close', text)

    def test_the_judgement_starts_when_the_line_is_taken_and_the_turn_waits_on_that_one(self):
        """A FIRST TURN WAITED ON ITS OWN RECALL (speed round, 2026-11-18): the one light model call that reads the closed tasks' titles ran
        inside the turn, before the CLI was handed its prompt - ~3 s of ~4 on a store of a few hundred tasks. It starts as the owner's line
        is taken (general.warm); the turn's brief waits on that same judgement. Asserted on the order of what happened, never on time:
        the judgement was already under way when the turn asked for it, and the model was asked once."""
        import threading
        from taskuary import general, llm, terminal
        s, tid, old = _known_world()
        s._exec('UPDATE task SET Kind=? WHERE TaskId=?', ('general', tid))       # ...a chat, whose prompt reads the brief (context.for_prompt)
        context._recalled.clear(); context._judging.clear()                      # ...nothing judged before the line
        row = s.get_connector_by_type('openai')
        s.save_connector({'ConnectorId': row['ConnectorId'], 'Active': 1, 'Secret': 'sk-test', 'Name': 'Work model', 'ConfigJson': '{"model":"gpt-test"}'}, 'owner')
        ranked, asked, turn = [], [], threading.current_thread().name
        pick = fake_embed.reader(PORTAL)
        def rank(system, user, **k): ranked.append(threading.current_thread().name); return pick(system, user, **k)
        def build_llm(*a, job=None, **k): return rank if job == 'rank' else (lambda *a, **k: 'Pay_people has no job code for the hire.')
        real = context.recall
        def recall(*a, **k):
            asked.append(bool(getattr(context, '_judging', None)) or bool(context._recalled))   # under way (or made) as the turn asks?
            return real(*a, **k)
        with fake_embed.no_embedder(), mock.patch.object(llm, 'build_llm', build_llm), mock.patch.object(context, 'recall', recall), \
             mock.patch.dict(terminal.SESSIONS, {}, clear=True):
            general.take_line(s, tid, 'Why does the new hire still show blank logins?')
            user = general._prompt(s, tid)[1]
        self.assertTrue(asked, 'the turn read what is known about its task')
        self.assertTrue(asked[0], 'the turn asked for the judgement before anything had started it')
        self.assertEqual(len(ranked), 1, f'the titles were read {len(ranked)} times')
        self.assertNotEqual(ranked[0], turn, 'the judgement ran in the turn itself')
        self.assertIn('pay_people', user)                                           # ...and the brief carries its picks

    def test_the_judgements_kept_are_bounded(self):
        with mock.patch.object(context, 'RECALL_KEPT', 3):
            for i in range(5): context._keep(('s', i, 'about', ''), context.NOTHING, 60)
        self.assertEqual([k[1] for k in context._recalled], [2, 3, 4])

    def test_a_strangers_task_recalls_nothing(self):
        s, tid, old = _known_world()
        s._exec('UPDATE task SET OriginBase=? WHERE TaskId=?', ('stranger', tid))
        with fake_embed.reads(PORTAL): self.assertEqual(context.recall(s, tid), context.NOTHING)

    def test_the_coding_seed_names_the_likely_repository_among_its_hints(self):
        s, tid, old = _known_world()
        from taskuary import repochoice
        with fake_embed.reads(PORTAL): block = repochoice.block(s, tid, 'C:/scratch/TQ')
        self.assertIn('northwind/portal - earlier tasks on the same thing worked in it', block.split('What Taskuary knows', 1)[1])


class FileTests(unittest.TestCase):
    def test_the_file_carries_history_past_work_and_thread_and_the_seed_points_at_it(self):
        s = _store(); s.set_setting('owner_email', 'owner@vendor.com', 't')
        # a colleague's mail is the owner's own domain; an unvouched sender would be a stranger's, whose words ride in a file (tests/test_origin_seed.py)
        a = _closed(s, 'Payroll import month wrong', DANA, 'Actions: routing.py now reads the payroll date.')
        tid = s.create_task({'Title': 'Payroll import wrong again', 'Kind': 'coding'}, 't')
        _mail(s, DANA, 'Payroll imports', 'March file landed in April.', days=9, conv='c1', status='filed')
        m1 = _mail(s, DANA, 'Payroll import wrong again', 'It is doing it again for May.', days=1, tid=tid, conv='c2')
        s.add_message({'TaskId': tid, 'ExternalId': 'mine', 'ConversationId': 'c2', 'Channel': 'email', 'SourceName': ME, 'Subject': 'Re: Payroll import wrong again',
                       'FromName': 'You', 'FromEmail': ME, 'SentAt': _ago(0), 'BodyText': 'Looking now.', 'Status': 'context'})
        path = context.write(s, tid, repo='northwind/Census')
        self.assertTrue(path and Path(path).exists())
        self.assertEqual(Path(path).parent.name, 'context')
        self.assertTrue(Path(path).is_relative_to(Path(os.environ['TASKUARY_HOME'])))     # Taskuary's home, never a checkout
        text = Path(path).read_text(encoding='utf-8')
        for want in ('## What the hub knows', 'March file landed in April',
                     '## Past work', 'reads the payroll date', '## The whole thread', 'THE OWNER', 'Looking now.'):
            self.assertIn(want, text)
        seed = terminal.seed_text(s, tid, None, 'northwind/Census', 'C:/src/Census')
        self.assertIn(f'CONTEXT FILE: {path}', seed)
        # in PARAGRAPHS on the command line - a blank line between blocks, none inside one (2026-09-30: "(0 lines hidden)")
        self.assertIn('\n\n', seed); self.assertNotIn('\n', seed.replace('\n\n', ''))

    def test_the_switch_turns_the_file_off_and_the_seed_stays_as_it_was(self):
        s = _store()
        _closed(s, 'Payroll import month wrong', DANA, 'Actions: fixed.')
        tid = s.create_task({'Title': 'Payroll import wrong again', 'Kind': 'coding'}, 't')
        _mail(s, DANA, 'Payroll import wrong again', 'Again.', days=1, tid=tid)
        s.set_setting('agent_context_file', '0', 't')
        self.assertIsNone(context.write(s, tid))
        seed = terminal.seed_text(s, tid)
        self.assertNotIn('CONTEXT FILE', seed)


class NewestFirstTests(unittest.TestCase):
    """A reopened coding task's context file kept the thread's FIRST mails and cut the ones after them - the very ones it was
    reopened for - while the resume seed said "3 new messages, read them in this file" (the owner, 2026-10-14)."""
    def test_a_long_thread_keeps_what_came_after_the_last_run_and_marks_it(self):
        s = MemoryStore()
        tid = s.create_task({'Title': 'Budget tab still missing', 'Kind': 'coding'}, 't')
        def mail(n, sent, reached):
            mid = s.add_message({'TaskId': tid, 'ExternalId': f'b{n}', 'ConversationId': 'cb', 'Channel': 'email', 'Subject': 'Budget tab',
                                 'FromName': f'Sender {n}', 'FromEmail': f's{n}@northwind.example', 'SentAt': sent,
                                 'BodyText': f'Mail {n}. ' + 'detail ' * 200, 'Status': 'routed'})
            s.cx.execute('UPDATE message SET CreatedAt=? WHERE MessageId=?', (reached, mid))
        for n in range(1, 13): mail(n, f'2026-10-{n:02d} 09:00:00', f'2026-10-{n:02d} 09:05:00')
        s.add_transcript(tid, 'sid-1', 'worked it', agent='coding', ext_id='ext-1')
        s.cx.execute("UPDATE transcript SET CreatedAt='2026-10-10 12:00:00' WHERE TaskId=?", (tid,))
        mail(13, '2026-10-09 18:00:00', '2026-10-13 08:00:00')                 # sent before the run, read in after it: still news
        s.cx.commit()
        text = context.build(s, tid)
        self.assertIn('newest first;', text); self.assertIn('older not shown', text)
        order = [int(n) for n in __import__('re').findall(r'^--- (?:\[NEW since your last run\] )?Sender (\d+) ·', text, __import__('re').M)]
        self.assertEqual(order[:4], [13, 12, 11, 10], 'newest first, by when it reached the thread')
        self.assertNotIn(1, order, 'the oldest are what the cap drops')
        for n in (11, 12, 13): self.assertIn(f'--- [NEW since your last run] Sender {n} ·', text)
        self.assertNotIn('[NEW since your last run] Sender 10 ·', text)
        self.assertIn('NEW SINCE YOUR LAST RUN: 3 messages', terminal.resume_seed('', s, tid), 'the seed counts the ones the file marks')


class SameRunTests(unittest.TestCase):
    """Two monitors reported one failed run an hour apart; the second opened a task "after the prior one was closed" because the
    closed one - made from the first monitor's idea, on another thread - was never shown to triage (TQ-1088/1089, 2026-10-14)."""
    def test_a_closed_task_carrying_the_same_run_id_is_shown_first(self):
        s = MemoryStore()
        first = s.create_task({'Title': 'Investigate ledger sync auth failures', 'Kind': 'coding'}, 't')
        s.add_message({'TaskId': first, 'ExternalId': 'i1', 'ConversationId': 'report:9:idea:ledger', 'Channel': 'assistant',
                       'Subject': 'Advisor idea', 'BodyText': 'Ledger Sync runId 4400917 failed with HTTP 401.', 'Status': 'routed'})
        for n in range(3):                                     # the report's own older tasks, which used to take every seat
            t = s.create_task({'Title': f'Ledger sync timeout {n}', 'Kind': 'coding'}, 't')
            s.add_message({'TaskId': t, 'ExternalId': f'r{n}', 'ConversationId': 'report:4', 'Channel': 'report',
                           'Subject': 'Process Error Check', 'BodyText': 'Ledger Sync timed out.', 'Status': 'routed'})
            s.update_task(t, {'Status': 'done'}, 't')
        s.update_task(first, {'Status': 'done'}, 't')
        body = 'Error summary:\n' + 'Ledger Sync timed out. ' * 60 + '\nLedger Sync failed: runId 4400917 - 3 company failures, HTTP 401'
        msg = {'channel': 'report', 'conversation_id': 'report:4', 'subject': 'Process Error Check - Error summary:', 'body': body}
        rows = context.recent_closures(s, msg)
        self.assertEqual(rows[0]['tid'], first)
        self.assertEqual(rows[0]['why'], 'the same run or record (4400917)')

    def test_no_shared_id_changes_nothing(self):
        self.assertEqual(context.ids_of('a run at 2026-10-14 16:18:39, 7 failures, code 401'), set())
        self.assertEqual(context.ids_of('runId 1001769 and ticket #3856864'), {'1001769', '3856864'})


ALEX, ERIN, GAIL = 'alex@northwind.example', 'erin@northwind.example', 'gail@northwind.example'

class WhatCameInTests(unittest.TestCase):
    """What is on file about each message and no read of a task carried (the stress run, 2026-11-10): whom it went to, the addresses
    behind its words, and - where a task's messages did not all come as one thread - what triage called each and the road it came by."""
    def setUp(self):
        s = self.s = _store()
        s.set_setting('owner_email', ALEX, 't')
        self.tid = s.create_task({'Title': 'Approve the renewal', 'Kind': 'general', 'OriginBase': 'owner'}, 't')

    def mail(self, n, body, subject='Renewal', conv='c-renewal', to=(ALEX,), cc=(), links=None, frm=ERIN, channel='email'):
        return self.s.add_message({'TaskId': self.tid, 'ExternalId': f'w{n}', 'ConversationId': conv, 'Channel': channel, 'SourceName': ALEX, 'Subject': subject,
                                   'FromName': frm.split('@')[0].title(), 'FromEmail': frm, 'SentAt': f'2026-11-0{n} 09:00:00', 'BodyText': body, 'Status': 'routed',
                                   'RecipientsJson': json.dumps({'to': list(to), 'cc': list(cc)}) if to or cc else None,
                                   'MailMetaJson': json.dumps({'links': links}) if links else None})

    def test_a_plain_thread_to_the_owner_alone_adds_nothing(self):
        self.mail(1, 'Can you approve the renewal?'); self.mail(2, 'Any news on this?', subject='RE: Renewal')
        self.assertEqual(context.came_in(self.s, self.tid), '')
        self.assertNotIn(context.CAME_HEAD, context.build(self.s, self.tid))

    def test_the_address_behind_a_word_and_who_else_it_went_to_reach_both_reads(self):
        wrapped = 'https://eur01.safelinks.protection.outlook.com/?url=https%3A%2F%2Fportal.vendor.example%2Fapprove%3Fid%3D88&data=05'
        mid = self.mail(1, 'Please approve the renewal here before Friday.', to=(GAIL,), cc=(ALEX, 'ray@northwind.example'),
                        links=[['here', wrapped], ['Unsubscribe', 'https://t.vendor.example/u/1']])
        self.mail(2, 'Thanks all.', subject='RE: Renewal')
        for text in (context.build(self.s, self.tid), context.for_prompt(self.s, self.tid)):
            self.assertIn(f'[m{mid}] Erin · 2026-11-01 09:00:00 · email · "Renewal"', text)
            self.assertIn(f'to: {GAIL} · cc: {ALEX}, ray@northwind.example', text)                      # the owner was only copied
            self.assertIn('"here" -> https://portal.vendor.example/approve?id=88', text)                # the mail system's wrapper is not the link
            self.assertNotIn('triage called it', text)                                                  # one thread: nothing to tell apart
        self.assertEqual(context.came_in(self.s, self.tid).count(chr(10) + '[m'), 1, 'the second mail lost nothing, so it is not listed')

    def test_a_subject_with_no_body_under_it_is_listed(self):
        mid = self.mail(1, '', subject='Call me re: the Payworth contract')
        self.assertIn(f'[m{mid}] Erin · 2026-11-01 09:00:00 · email · "Call me re: the Payworth contract"', context.came_in(self.s, self.tid))

    def test_a_long_thread_keeps_the_newest_and_says_what_it_left_out(self):
        for n in range(1, 10): self.mail(n, 'See the link.', links=[['the sheet', f'https://portal.vendor.example/{n}/' + 'x' * 400]])
        text = context.came_in(self.s, self.tid)
        self.assertLess(len(text), context.CAME_CHARS + 400)
        self.assertIn('https://portal.vendor.example/9/', text); self.assertNotIn('https://portal.vendor.example/1/', text)
        self.assertRegex(text, r'\d older not listed')


class TwoMattersOnOneTaskTests(unittest.TestCase):
    """A task is one matter only as far as each road onto it was right. The roads are on file (route.Reason, the verdict, each message's
    own triage title); the agent working the task saw one flat list of bodies. Arrivals go through the real ingest, the model is a stub."""
    def setUp(self):
        s = self.s = _store()
        s.set_setting('owner_email', ALEX, 't')

    def come(self, msgs, script):
        from taskuary import ingest
        n = [0]
        def llm(system, user, **k):
            x = script[min(n[0], len(script) - 1)]; n[0] += 1
            return json.dumps({'intent': 'task', 'kind': 'task', 'why': 'scripted', 'summary': 'scripted', **x})
        llm.takes_want = True
        with mock.patch.object(ingest, '_spawn'): return [ingest.ingest_message(self.s, m, llm=llm) for m in msgs]

    def chat(self, n, body):
        return {'external_id': f'w{n}', 'channel': 'whatsapp', 'from_email': 'erin@wa.example', 'from_name': 'Erin Blake', 'conversation_id': 'wa:erin',
                'subject': 'Erin Blake', 'body': body, 'sent_at': f'2026-11-09 1{n}:00:00', 'source_name': 'Erin Blake', 'mail_meta': {'dm': True}}

    def mailed(self, n, body, subject, conv, frm=ERIN, name='Erin Blake'):
        return {'external_id': f'e{n}', 'channel': 'email', 'from_email': frm, 'from_name': name, 'conversation_id': conv, 'subject': subject,
                'body': body, 'sent_at': f'2026-11-09 1{n}:00:00', 'to': [ALEX], 'cc': []}

    def test_a_one_to_one_line_joined_because_triage_was_unsure_says_so(self):
        a, b = self.come([self.chat(1, 'the portal is down, it says 502'), self.chat(2, 'btw did payroll go out for Marcus?')],
                         [{'relationship': 'new', 'title': 'Portal is down'}, {'relationship': 'uncertain', 'title': 'Did payroll go out for Marcus'}])
        self.assertEqual((b['status'], b['task_id']), ('attached', a['task_id']), 'the widest door: unsure joins in a one-to-one chat')
        rows = context.joins(self.s, a['task_id'])
        self.assertEqual([(r['mid'], r['title'], r['joined'], r['doubt']) for r in rows],
                         [(a['message_id'], 'Portal is down', False, False), (b['message_id'], 'Did payroll go out for Marcus', True, True)])
        text = context.build(self.s, a['task_id'], general=True)
        self.assertIn('2 messages from 1 thread or chat, 1 of them joined with nothing sure it continues the task', text)
        self.assertIn(f"[m{b['message_id']}] Erin Blake", text)
        self.assertIn('triage called it "Did payroll go out for Marcus" · joined this task: unsure whether it continues', text)
        self.assertIn('triage called it "Portal is down" · opened this task', text)

    def test_two_threads_on_one_task_are_told_apart(self):
        a, b = self.come([self.mailed(1, 'Please approve PO-5512.', 'PO-5512', 'c-po'),
                          self.mailed(2, 'A reminder about the Trainly renewal quote.', 'Trainly renewal', 'c-trainly', GAIL, 'Gail Moreno')],
                         [{'title': 'Approve PO-5512'}, {'title': 'Trainly renewal quote', 'same_as': 1}])
        self.assertEqual((b['status'], b['task_id']), ('routed', a['task_id']))
        text = context.came_in(self.s, a['task_id'])
        self.assertIn('2 messages from 2 threads or chats - each line ends', text)
        self.assertIn(f"[m{b['message_id']}] Gail Moreno · 2026-11-09 12:00:00 · email · \"Trainly renewal\"", text)
        self.assertRegex(text, r'triage called it "Trainly renewal quote" · joined this task: triage: .*the same as TQ-0001, joined to it')
        # ...and the coding read's thread names each message by the same id
        self.assertIn(f"· email · m{b['message_id']}\n", context.build(self.s, a['task_id']))

    def test_a_thread_whose_subject_moved_on_is_two_threads(self):
        a, b = self.come([self.mailed(1, 'Please approve PO-5512.', 'PO-5512', 'c-po'),
                          self.mailed(2, 'Separately - can you set up a laptop for the new starter?', 'Laptop for the new starter', 'c-po')],
                         [{'title': 'Approve PO-5512'}, {'title': 'Set up a laptop for the new starter'}])
        self.assertEqual((b['status'], b['task_id']), ('attached', a['task_id']), 'its own thread: joined unless triage says new_job')
        text = context.came_in(self.s, a['task_id'])
        self.assertIn('2 messages from 2 threads or chats', text)
        self.assertIn('triage called it "Set up a laptop for the new starter" · joined this task: attached: same conversation thread', text)
