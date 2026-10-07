"""The assistant on the Timeline (assistant.py): the half-hourly check that says what it noticed - the
reply you sent and never heard back on, the task gone quiet, its
own ideas - once each, with actions and conversation. All offline: the model is a lambda, the calendar is off.
"""
import json, tempfile, unittest
from datetime import datetime, timedelta
from pathlib import Path
from unittest import mock

from taskuary import assistant, ingest
from taskuary.store import MemoryStore

ME, DANA = 'owner@ours.com', 'dana@vendor.com'
def _ago(days=0, hours=0): return (datetime.now() - timedelta(days=days, hours=hours)).strftime('%Y-%m-%d %H:%M:%S')


def _store():
    s = MemoryStore()
    s.set_setting('calendar_enabled', '0', 't')
    s.set_setting('coder_auto_enabled', '0', 't')
    s.set_setting('learn_enabled', '0', 't')
    return s


def _mail(s, frm, subject, body, days=3, conv=None, status='filed', tid=None, name=None, hours=0):
    return s.add_message({'TaskId': tid, 'ExternalId': f'x:{frm}:{subject}:{days}:{hours}', 'ConversationId': conv, 'Channel': 'email',
                          'SourceName': ME, 'Subject': subject, 'FromName': name or frm.split('@')[0].title(), 'FromEmail': frm,
                          'SentAt': _ago(days, hours), 'BodyText': body, 'Status': status})


def _mine(s, subject, body, days, conv, tid=None):
    """The owner's own reply on a thread - 'context' rows ride inside the chain."""
    return s.add_message({'TaskId': tid, 'ExternalId': f'mine:{conv}:{days}', 'ConversationId': conv, 'Channel': 'email', 'SourceName': ME,
                          'Subject': subject, 'FromName': 'You', 'FromEmail': ME, 'SentAt': _ago(days), 'BodyText': body, 'Status': 'context'})


class FollowupCandidateTests(unittest.TestCase):
    def test_a_chase_that_grew_is_said_even_when_the_model_lets_it_go_and_says_only_the_facts(self):
        # told "be useful, not busy", the model let a vendor's twelve days of silence go twice; the owner's ask was still open
        s = _store()
        _mail(s, DANA, 'SSO', 'Here are our settings.', days=13, conv='c1')
        _mine(s, 'Re: SSO', 'Has that been solved so employee ids are unique?', days=12, conv='c1')
        [c] = assistant.followups(s, hours=24)
        s.upsert_idea({'key': c['key'], 'kind': 'followup', 'text': 'said on day 2', 'sig': c['sig'].split('|')[0] + '|1', 'action': {}}, _ago(11))
        s.set_setting('assistant_producers', 'followup', 't')
        silent = lambda system, user, **k: json.dumps({'say': [], 'notes': 'nothing new'})
        out = assistant.run(s, llm=silent, force=True)
        self.assertEqual(out['said'], 1)
        body = s.get_message(out['message_id'])['BodyText']
        self.assertIn('No answer from Dana', body); self.assertNotIn('RAISED BEFORE', body); self.assertNotIn('say it again', body)

    def test_nobody_is_chased_behind_a_report_or_a_calendar_response(self):
        s = _store()
        _mail(s, 'calendar@ours.com', 'Accepted: AI Agents', 'Accepted', days=6, conv='c1')
        _mine(s, 'Re: AI Agents', 'Can you bring the numbers?', days=5, conv='c1')
        s.add_message({'ExternalId': 'r1', 'ConversationId': 'c2', 'Channel': 'report', 'SourceName': 'Automation ideas', 'Subject': 'Automation ideas',
                       'FromName': 'Automation ideas', 'FromEmail': '', 'SentAt': _ago(6), 'BodyText': 'Ideas.', 'Status': 'feed'})
        _mine(s, 'Re: Automation ideas', 'Could you add the T&E ones?', days=5, conv='c2')
        self.assertEqual(assistant.followups(s, hours=24), [])

    def test_an_open_follow_up_comes_back_as_the_silence_grows_but_a_dismissed_one_stays_down(self):
        # a vendor who never answered was raised on day 2 as the second line of a 6:56 post, then never again: the Sig was the
        # last word alone, and silence does not move it (2026-10-06)
        from datetime import datetime
        s = _store()
        _mail(s, DANA, 'SSO', 'Here are our settings.', days=13, conv='c1')
        _mine(s, 'Re: SSO', 'Has that been solved so employee ids are unique?', days=12, conv='c1')
        [now] = assistant.followups(s, hours=24)
        said_day2 = {'Key': now['key'], 'Status': 'open', 'Sig': now['sig'].split('|')[0] + '|1'}
        self.assertTrue(assistant.fresh({now['key']: said_day2}, now, datetime.now()))           # 12 days on: said again
        self.assertFalse(assistant.fresh({now['key']: {**said_day2, 'Sig': now['sig']}}, now, datetime.now()))  # same step: once
        for done in ('dismissed', 'done'):
            self.assertFalse(assistant.fresh({now['key']: {**said_day2, 'Status': done}}, now, datetime.now()), done)
        _mail(s, DANA, 'Re: SSO', 'Can you check the ids again?', days=0, hours=1, conv='c1')      # the thread itself moved
        self.assertEqual(assistant.followups(s, hours=24), [])

    def test_your_unanswered_ask_becomes_a_followup_but_a_thanks_does_not(self):
        s = _store()
        _mail(s, DANA, 'Q3 ledger', 'Here is the ledger.', days=6, conv='c1')
        _mine(s, 'Re: Q3 ledger', 'Thanks Dana - could you send the reconciled version by Friday?', days=4, conv='c1')
        _mail(s, 'lee@ours.com', 'Lunch', 'Lunch?', days=5, conv='c2')
        _mine(s, 'Re: Lunch', 'Thanks, see you there.', days=4, conv='c2')            # no ask in it - silence is fine
        _mail(s, 'sam@ours.com', 'Numbers', 'Can you check?', days=3, conv='c3')
        _mine(s, 'Re: Numbers', 'Could you resend the file?', days=2, conv='c3')
        _mail(s, 'sam@ours.com', 'Re: Numbers', 'Attached.', days=1, conv='c3')          # they answered - not a followup
        got = assistant.followups(s, hours=24)
        self.assertEqual([c['key'] for c in got], ['followup:c1'])
        self.assertIn('Dana', got[0]['text']); self.assertEqual(got[0]['action']['type'], 'followup')
        self.assertEqual(got[0]['action']['mid'], s.last_inbound_in('c1')['MessageId'])

    def test_too_recent_is_not_yet_a_followup(self):
        s = _store()
        _mail(s, DANA, 'Q3 ledger', 'Here.', days=1, conv='c1')
        _mine(s, 'Re: Q3 ledger', 'Could you resend?', days=0, conv='c1')
        self.assertEqual(assistant.followups(s, hours=24), [])
        self.assertEqual(len(assistant.followups(s, hours=0)), 1)


class ColdAndAheadTests(unittest.TestCase):
    def test_a_task_nothing_touched_for_days_goes_cold(self):
        s = _store()
        tid = s.create_task({'Title': 'Fix the export', 'Kind': 'coding', 'Status': 'open'}, 't')
        s._exec('UPDATE task SET CreatedAt=?, UpdatedAt=? WHERE TaskId=?', (_ago(5), _ago(5), tid))
        fresh = s.create_task({'Title': 'New one', 'Kind': 'coding', 'Status': 'open'}, 't')
        got = assistant.cold(s, days=3)
        self.assertEqual([c['key'] for c in got], [f'cold:TQ-{tid:04d}'])
        self.assertIn('sat quiet', got[0]['text'])
        s.add_comment(tid, 'coder', 'agent', 'working on it')            # activity today: no longer cold
        self.assertEqual(assistant.cold(s, days=3), [])


class PostTests(unittest.TestCase):
    def _seed(self):
        s = _store()
        _mail(s, DANA, 'Q3 ledger', 'Here is the ledger.', days=6, conv='c1')
        _mine(s, 'Re: Q3 ledger', 'Could you send the reconciled version by Friday?', days=4, conv='c1')
        return s

    def test_configured_report_views_are_pulled_live_without_filing_intermediate_rows(self):
        from taskuary import reports
        s = _store(); seen = {}
        reports.REGISTRY['_finance_watch'] = lambda cfg: ('3 payments today', 'total=125000\nnormal_daily=40000')
        try:
            watched = s.save_source({'Channel': 'report', 'Address': 'Intacct payments', 'Active': 0,
                                     'ConfigJson': json.dumps({'type': '_finance_watch', 'title': 'Intacct payments',
                                                               'ai_prompt': 'This report has its own summary prompt.'})}, 't')
            src = assistant.source(s); cfg = src['cfg'] | {'watch_source_ids': [watched]}
            s.save_source({'SourceId': src['SourceId'], 'ConfigJson': json.dumps(cfg)}, 't')
            s.set_setting('assistant_producers', 'followup', 't')  # selected views still request model judgement
            preview_head, preview = reports.run_assistant(
                reports.resolve_cfg(s, {'type': 'assistant', 'watch_source_ids': [watched]}))
            def llm(system, user, **kwargs):
                seen['user'] = user
                return json.dumps({'say': [{'key': 'idea:intacct-payment-spike',
                                            'text': 'Intacct payments are unusually high today.',
                                            'why': 'Intacct payments: 125000 versus a normal 40000.',
                                            'mid': None, 'task': None}], 'notes': ''})
            out = assistant.run(s, llm=llm, force=True)
        finally:
            reports.REGISTRY.pop('_finance_watch', None)
        self.assertEqual(out['said'], 1)
        self.assertIn('assistant would read', preview_head); self.assertIn('total=125000', preview)
        self.assertIn('CONFIGURED SYSTEM CHECKS', seen['user'])
        self.assertIn('Intacct payments (3 payments today)', seen['user'])
        self.assertIn('total=125000', seen['user'])
        self.assertNotIn('This report has its own summary prompt', seen['user'])
        self.assertIsNone(s.get_source(watched).get('LastPolledAt'))
        self.assertFalse(any(m.get('Channel') == 'report' for m in s.recent_messages(_ago(1), limit=20)))

    def test_the_assistant_reads_its_own_sources_without_a_saved_report_behind_them(self):
        """The owner (2026-08-31): asking the Assistant about another system must not require
        first saving a report or view for it."""
        from taskuary import reports
        s = _store(); seen = {}
        reports.REGISTRY['_beds'] = lambda cfg: (f"rows for {cfg['query']}", 'open_beds=4')
        try:
            own = [{'type': '_beds', 'label': 'Open beds', 'query': 'SELECT open FROM beds'}]
            src = assistant.source(s)
            s.save_source({'SourceId': src['SourceId'], 'ConfigJson': json.dumps(src['cfg'] | {'watch_sources': own})}, 't')
            s.set_setting('assistant_producers', 'followup', 't')
            _, preview = reports.run_assistant(reports.resolve_cfg(s, {'type': 'assistant', 'watch_sources': own}))
            def llm(system, user, **kwargs):
                seen['user'] = user
                return json.dumps({'say': [], 'notes': ''})
            assistant.run(s, llm=llm, force=True)
        finally:
            reports.REGISTRY.pop('_beds', None)
        for text in (preview, seen['user']):
            self.assertIn('=== Open beds (rows for SELECT open FROM beds) ===', text)
            self.assertIn('open_beds=4', text)
        # no standalone report was created to make that possible
        self.assertEqual([x for x in s.list_sources(active_only=False)
                          if json.loads(x['ConfigJson'] or '{}').get('type') == '_beds'], [])

    def test_a_source_backed_assistant_report_reads_only_its_own_sources(self):
        """A second Assistant report is an isolated monitor, not an alias for the seeded digest-like
        Assistant. Its SQL/data result is the complete fact set shown in Preview and handed to AI."""
        from taskuary import reports
        s = _store(); seen = {}
        _mail(s, DANA, 'Private mailbox distraction', 'This must not reach the SQL monitor.', days=0, conv='private')
        reports.REGISTRY['_backend_watch'] = lambda cfg: ('2 process rows', 'process=Import success=0\nprocess=Export success=1')
        try:
            sid = s.save_source({'Channel': 'report', 'Address': 'Backend monitor', 'Active': 1,
                                 'ConfigJson': json.dumps({'type': 'assistant', 'title': 'Backend monitor',
                                     'ai_prompt': 'Raise any process whose success is zero.',
                                     'watch_sources': [{'type': '_backend_watch', 'label': 'tranCodeRun last hour',
                                                        'query': 'SELECT * FROM tranCodeRun'}]})}, 't')
            src = s.get_source(sid)
            cfg_ = reports.resolve_cfg(s, json.loads(src['ConfigJson']))
            _head, preview = reports.run_assistant(cfg_)
            def llm(system, user, **kwargs):
                if 'user' not in seen: seen.update(system=system, user=user, kwargs=kwargs)   # the model pass, not the judge after it
                return json.dumps({'say': [{'key': 'idea:failed-import',
                    'text': 'Import has a failed run; I would inspect it now.', 'section': 'systems',
                    'why': 'tranCodeRun: process=Import success=0', 'mid': None, 'task': None}],
                    'notes': 'mailbox facts must never leak through notes'})
            out = reports.run_report_source(s, src, llm)
        finally:
            reports.REGISTRY.pop('_backend_watch', None)

        for text in (preview, seen['user'], out['inputs']):
            self.assertIn('CONFIGURED DATA SOURCES (the only facts available to this report)', text)
            self.assertIn('process=Import success=0', text)
            self.assertNotIn('WHAT PEOPLE SAID', text)
            self.assertNotIn('OPEN WORK', text)
            self.assertNotIn('Private mailbox distraction', text)
        self.assertIn("THE OWNER'S RULE FOR THIS MONITOR", seen['system'])
        self.assertIn('Raise any process whose success is zero', seen['system'])
        self.assertNotIn('images', seen['kwargs'])
        self.assertEqual((out['reviewed']['scope'], out['reviewed']['systems'], out['reviewed']['people']),
                         ('sources', 1, 0))
        self.assertEqual(s.get_message(out['message_id'])['SourceName'], 'Backend monitor')
        self.assertTrue(out['lines'][0]['key'].startswith(f'report:{sid}:idea:'))
        self.assertNotIn('mailbox facts', s.get_settings().get('assistant_notes', ''))

    def test_an_assistant_with_neither_kind_of_view_says_both_ways_to_add_one(self):
        s = _store()
        self.assertIn('add a data source', assistant.system_checks(s))
        self.assertEqual(assistant._inline([{'type': 'assistant'}, {'label': 'no type'}, 'nonsense']), [])

    def test_the_post_is_one_row_with_its_ideas_in_the_brief_and_never_repeats(self):
        s = self._seed()
        seen = []
        def llm(system, user, **k):
            seen.append(user)
            return json.dumps({'say': [{'key': 'followup:c1', 'text': "Dana owes you the reconciled ledger since Tuesday - I'd nudge.", 'mid': None},
                                       {'key': 'idea:ledger-close', 'text': 'Q3 close is a week out; I would book the sign-off now.', 'mid': None, 'task': None}]})
        out = assistant.run(s, llm=llm, force=True)
        self.assertEqual(out['said'], 2)
        row = s.get_message(out['message_id'])
        self.assertEqual((row['Channel'], row['FromName'], row['Status']), ('assistant', 'Advisor', 'feed'))
        ideas = json.loads(row['Brief'])['ideas']
        self.assertEqual([i['kind'] for i in ideas], ['followup', 'idea'])
        self.assertEqual(ideas[0]['action']['type'], 'followup')            # the candidate keeps its buttons
        self.assertIn('CANDIDATES:\n[followup:c1]', seen[0])
        # the feed wears it as its own category
        feed = s.feed(limit=10)
        self.assertEqual([r['Category'] for r in feed if r['Channel'] == 'assistant'], ['assistant'])
        # second run, same facts: the model is told what was said, and even if it echoes, nothing posts
        out2 = assistant.run(s, llm=llm, force=True)
        self.assertEqual(out2['said'], 0)
        self.assertIn('ALREADY SAID (never repeat):', seen[1]); self.assertIn('- (open) Dana owes you', seen[1])
        self.assertEqual(len([r for r in s.feed(limit=10) if r['Channel'] == 'assistant']), 1)

    def test_every_line_carries_its_why_and_the_post_says_what_it_reviewed(self):
        """The owner (2026-08-30): "we need more context like what it reviewed, why it brings up something,
        what is driving it". A candidate's why is the hub's facts plus the model's read; an idea's why is
        the model's own; the post records what it was built from and what it let go."""
        s = self._seed()
        _mail(s, 'lee@x.com', 'Invoice 88', 'Attached.', days=5, conv='c2')
        _mine(s, 'Re: Invoice 88', 'Can you confirm the PO number?', days=3, conv='c2')
        def llm(system, user, **k):
            self.assertIn('"why":', system)
            return json.dumps({'say': [{'key': 'followup:c1', 'text': "Dana owes you the ledger - I'd nudge.", 'why': 'four days is long for her', 'mid': None},
                                       {'key': 'idea:po-numbers', 'text': 'Two PO questions this week - I would keep a PO sheet.', 'why': 'mails on "Invoice 88" and "Q3 ledger" both circle a reference number', 'mid': None, 'task': None},
                                       {'key': 'idea:hunch', 'text': 'Something feels off with the close.', 'mid': None, 'task': None}]})
        out = assistant.run(s, llm=llm, force=True)
        row = s.get_message(out['message_id']); brief = json.loads(row['Brief'])
        ideas = brief['ideas']
        self.assertTrue(ideas[0]['why'].startswith('You wrote Dana on')); self.assertIn("The model's read: four days is long", ideas[0]['why'])
        self.assertEqual(ideas[1]['why'], 'mails on "Invoice 88" and "Q3 ledger" both circle a reference number')
        self.assertIn('gave no reason', ideas[2]['why'])
        self.assertNotIn('why', ideas[0]['action'])                          # rides in ActionJson, lifted out for the API
        rv = brief['reviewed']
        self.assertEqual(rv['candidates'], {'followup': 2}); self.assertTrue(rv['model'])
        self.assertEqual([c['key'] for c in rv['skipped']], ['followup:c2']); self.assertIn('Can you confirm the PO', rv['skipped'][0]['facts'])
        self.assertEqual(rv['said'], 0); self.assertTrue(all(isinstance(rv[k], int) for k in ('recent', 'week', 'open')))
        self.assertIn('    why: You wrote Dana', row['BodyText']); self.assertIn('Reviewed: 2 followup; let go: 1', row['BodyText'])
        self.assertEqual(out['reviewed'], rv)
        # nothing to say still reports what it read - the Reports tab's run result carries it
        self.assertEqual([c['key'] for c in assistant.run(s, llm=lambda *a, **k: '{"say": []}', force=True)['reviewed']['skipped']], ['followup:c2'])

    def test_no_model_still_posts_the_facts(self):
        s = self._seed()
        with mock.patch('taskuary.llm.build_llm', return_value=None):
            out = assistant.run(s, force=True)
        self.assertEqual(out['said'], 1)
        self.assertIn('No answer from Dana', s.get_message(out['message_id'])['BodyText'])

    def test_the_reports_tab_is_the_switch_the_clock_and_the_instruction(self):
        """The 'Advisor' report ships seeded like the Morning digest: hourly, on startup, its prompt the
        editable instruction. Deleting it (or switching it off) turns the post off - except for 'ask now'."""
        s = self._seed()
        src = assistant.source(s)
        self.assertEqual((src['Address'], src['cfg']['type'], src['cfg']['every_minutes'], src['Active']), ('Advisor', 'assistant', 30, 1))
        self.assertIn('What I promised', src['cfg']['ai_prompt'])
        seen = []
        def llm(system, user, **k): seen.append(system); return '{"say": []}'
        # a due run through the report machinery, with an edited instruction
        c = src['cfg'] | {'ai_prompt': 'Only chase vendors. Never mention meetings.'}
        s._exec('UPDATE source SET ConfigJson=? WHERE SourceId=?', (json.dumps(c), src['SourceId']))
        from taskuary.reports import run_report_source
        out = run_report_source(s, s.get_source(src['SourceId']), llm)
        self.assertTrue(out['ran']); self.assertIn('Only chase vendors', seen[0]); self.assertIn('At most 5 entries', seen[0])
        self.assertEqual([r for r in s.feed(limit=10) if r['Channel'] == 'report'], [])           # no report row - the assistant posts its own kind
        # switched off on the Reports tab: the scheduler's call does nothing, 'ask now' still answers
        s._exec('UPDATE source SET Active=0 WHERE SourceId=?', (src['SourceId'],))
        self.assertEqual(assistant.run(s, llm=llm), {'ran': False, 'said': 0})
        self.assertTrue(assistant.run(s, llm=llm, force=True)['ran'])
        self.assertFalse(assistant.source(s)['Active'])
        s.delete_source(src['SourceId'])
        self.assertIsNone(assistant.source(s))

    def test_lines_per_post_is_a_setting(self):
        s = self._seed()
        s.set_setting('assistant_max_lines', '2', 't')
        say = [{'key': f'idea:n{i}', 'text': f'idea number {i}', 'mid': None, 'task': None} for i in range(5)]
        out = assistant.run(s, llm=lambda *a, **k: json.dumps({'say': say}), force=True)
        self.assertEqual(out['said'], 2)

    def test_a_reply_sent_from_review_is_a_message_in_the_preview_and_blocks_a_false_nag(self):
        """The channel may not ingest our outbound copy before the next Assistant check.

        Review's successful send receipt still proves both that the message was answered and
        exactly what the owner said. The model gets that as the final message, and a claim that
        nobody replied is rejected even if the model overlooks it.
        """
        s = _store()
        tid = s.create_task({'Title': 'Give JD access', 'Kind': 'coding', 'Status': 'done'}, 't')
        mid = _mail(s, 'jd@ours.com', 'Access', 'Am I missing a permission?', days=0,
                    hours=2, conv='access-1', tid=tid, status='routed', name='JD')
        rid = s.add_review({'TaskId': tid, 'MessageId': mid, 'Kind': 'draft_reply',
                            'DraftText': 'Your access is fixed. Please retry.', 'Status': 'pending'})
        s.decide_review(rid, 'approved', 'Your access is fixed. Please retry.', 'owner')
        seen = {}
        def llm(system, user, **kwargs):
            seen['user'] = user
            return json.dumps({'say': [{'key': 'idea:reply-jd',
                                        'text': "Nobody told JD it was fixed. I'd reply and ask him to retry.",
                                        'why': 'the task is closed', 'mid': mid}]})
        out = assistant.run(s, llm=llm, force=True)
        self.assertIn('you ', seen['user'])
        self.assertIn('Your access is fixed. Please retry.', seen['user'])
        self.assertIn('[reply sent from Review]', seen['user'])
        self.assertEqual(out['said'], 0)
        self.assertEqual(s.list_ideas('open'), [])

    def test_a_promise_you_made_is_your_own_open_item_not_a_chase(self):
        s = _store()
        _mail(s, DANA, 'Contract', 'Can you send the signed copy?', days=4, conv='p1')
        _mine(s, 'Re: Contract', "Yes - I'll send it over by Friday.", days=3, conv='p1')
        got = assistant.followups(s, hours=24)
        self.assertEqual([c['kind'] for c in got], ['promise'])
        self.assertIn('You told Dana you would', got[0]['text']); self.assertEqual(got[0]['action']['type'], 'message')
        self.assertEqual(assistant.followups(s, hours=24, want=('followup',)), [])                # the producer is a switch

    def test_producers_are_switches(self):
        s = self._seed()
        s.set_setting('assistant_producers', 'prep,cold', 't')
        with mock.patch('taskuary.llm.build_llm', return_value=None):
            self.assertEqual(assistant.run(s, force=True)['said'], 0)          # followups are off, so nothing to say

    def test_a_model_that_answers_garbage_falls_back_to_the_facts(self):
        s = self._seed()
        # unreadable = the model chose silence; never a crash, and nothing enters the idea table
        self.assertEqual(assistant.run(s, llm=lambda *a, **k: 'I have no idea', force=True)['said'], 0)
        # a model that FAILS is not silence either: it is a failed run, posting nothing (R2, 2026-09-28)
        out = assistant.run(s, llm=mock.Mock(side_effect=RuntimeError('boom')), force=True)
        self.assertTrue(out['failed']); self.assertEqual(out['said'], 0); self.assertIn('boom', out['error'])


class ButtonTests(unittest.TestCase):
    def _posted(self):
        s = _store()
        mid = _mail(s, DANA, 'Q3 ledger', 'Here is the ledger.', days=6, conv='c1')
        _mine(s, 'Re: Q3 ledger', 'Could you send the reconciled version by Friday?', days=4, conv='c1')
        with mock.patch('taskuary.llm.build_llm', return_value=None):
            out = assistant.run(s, force=True)
        idea = s.list_ideas('open')[0]
        return s, mid, idea

    def test_make_a_task_is_yours_and_starts_nothing(self):
        """C5 (the owner, 2026-09-27): Make a task is a task on your own list; Send to agent is the one that starts one."""
        s, mid, idea = self._posted()
        with mock.patch('taskuary.ingest._spawn') as spawn:
            out = assistant.act(s, idea['IdeaId'], 'task')
        t = s.get_task(out['taskId'])
        self.assertEqual((t['Kind'], t['Assignee']), ('task', 'owner'))
        spawn.assert_not_called()
        self.assertEqual(s.get_idea(idea['IdeaId'])['Status'], 'done')
        self.assertEqual(json.loads(s.get_idea(idea['IdeaId'])['ActionJson'])['tid'], out['taskId'])

    def test_send_to_agent_starts_the_agent_its_kind_names(self):
        s, mid, idea = self._posted()
        with mock.patch('taskuary.ingest._spawn') as spawn:
            out = assistant.act(s, idea['IdeaId'], 'agent')
        self.assertEqual(s.get_task(out['taskId'])['Kind'], 'general')             # coding is never the default
        self.assertEqual([getattr(c[0][0], '__name__', '') for c in spawn.call_args_list], ['_auto_general'])
        s2, _, idea2 = self._posted()
        s2.set_setting('coder_auto_enabled', '1', 't')
        s2.set_idea_action(idea2['IdeaId'], json.loads(idea2['ActionJson']) | {'kind': 'coding'})
        with mock.patch('taskuary.ingest._spawn') as spawn:
            out = assistant.act(s2, idea2['IdeaId'], 'agent')
        self.assertEqual(s2.get_task(out['taskId'])['Kind'], 'coding')
        self.assertEqual([getattr(c[0][0], '__name__', '') for c in spawn.call_args_list], ['_auto_code'])

    def test_make_a_task_reads_the_task_triage_already_opened(self):
        """I1: triage opened a task for the idea, and Make a task opened a second one beside it."""
        s, mid, idea = self._posted()
        tid = s.create_task({'Title': 'Chase the ledger', 'Kind': 'task', 'SourceRef': f"assistant:idea:{idea['IdeaId']}"}, 'assistant')
        n = len(s.list_tasks())
        with mock.patch('taskuary.ingest._spawn'):
            self.assertEqual(assistant.act(s, idea['IdeaId'], 'task')['taskId'], tid)
        self.assertEqual(len(s.list_tasks()), n)

    def test_an_idea_never_reopens_a_closed_task(self):
        """I7: the finished task keeps its history; the new work is a new task carrying the evidence."""
        s, mid, idea = self._posted()
        tid = s.create_task({'Title': 'Read this', 'Kind': 'general', 'Status': 'open'}, 'router')
        s.attach_message(mid, tid)
        s.update_task(tid, {'Status': 'done'}, 'owner')
        closed_at = s.get_task(tid)['ClosedAt']
        with mock.patch('taskuary.ingest._spawn') as spawn:
            out = assistant.act(s, idea['IdeaId'], 'agent')
        self.assertNotEqual(out['taskId'], tid)
        self.assertEqual((s.get_task(tid)['Status'], s.get_task(tid)['ClosedAt']), ('done', closed_at))
        task = s.get_task(out['taskId'])
        self.assertEqual((task['Kind'], task['Status'], task['SourceRef']), ('general', 'open', f"assistant:idea:{idea['IdeaId']}"))
        self.assertEqual([getattr(c[0][0], '__name__', '') for c in spawn.call_args_list], ['_auto_general'])

    def test_not_ours_teaches_nothing_and_stays_down_until_the_facts_change(self):
        """I10: Not ours only never repeats - the lesson it wrote went to a block no prompt reads."""
        s, mid, idea = self._posted()
        with mock.patch('taskuary.learn.learn_from') as learn:
            assistant.act(s, idea['IdeaId'], 'dismiss')
        learn.assert_not_called()
        self.assertEqual(s.get_idea(idea['IdeaId'])['Status'], 'dismissed')
        with mock.patch('taskuary.llm.build_llm', return_value=None):
            self.assertEqual(assistant.run(s, force=True)['said'], 0)                # same silence: not said again
            _mine(s, 'Re: Q3 ledger', 'Dana - still need that file, could you send it?', days=2, conv='c1')
            self.assertEqual(assistant.run(s, force=True)['said'], 1)                # you wrote again: new facts, new line
        self.assertEqual(s.get_idea(idea['IdeaId'])['SaidCount'], 2)

    def test_remind_me_sleeps_until_its_day_and_wakes(self):
        s, mid, idea = self._posted()
        out = assistant.act(s, idea['IdeaId'], 'snooze', until='2 weeks')
        self.assertTrue(out['until'].endswith('07:00:00')); self.assertTrue(out['when'])
        self.assertEqual(s.get_idea(idea['IdeaId'])['Status'], 'snoozed')
        # the post's line says which day it comes back, not "until its day"
        self.assertEqual(assistant._public(s.get_idea(idea['IdeaId']))['until'], out['until'])
        with mock.patch('taskuary.llm.build_llm', return_value=None):
            self.assertEqual(assistant.run(s, force=True)['said'], 0)
            s._exec('UPDATE idea SET SnoozeUntil=? WHERE IdeaId=?', (_ago(hours=1), idea['IdeaId']))
            self.assertEqual(assistant.run(s, force=True)['said'], 1)
        with self.assertRaises(ValueError): assistant.act(s, idea['IdeaId'], 'snooze', until='someday')

    def test_a_note_with_no_message_still_becomes_a_task(self):
        s = _store()
        row = s.upsert_idea({'key': 'idea:x', 'kind': 'idea', 'text': 'Book the sign-off.', 'action': {'type': 'note'}}, _ago())
        tid = assistant.act(s, row['IdeaId'], 'task')['taskId']
        self.assertEqual((s.get_task(tid)['Title'], s.get_task(tid)['SourceRef']), ('Book the sign-off.', f"assistant:idea:{row['IdeaId']}"))
        for gone in ('followup', 'discuss', 'nonsense'):
            with self.assertRaises(ValueError): assistant.act(s, row['IdeaId'], gone)

    def test_a_conversation_comes_before_a_pile_of_forwards_and_the_soul_goes_whole(self):
        """The chat where the owner and a colleague restarted a frozen app ("try now", "that worked") was cut from WHAT
        PEOPLE SAID by seven forwards from one sender, and the Advisor read "try now" alone (2026-09-25)."""
        s = _store()
        for n in range(7):
            _mail(s, 'paula@northwind.example', f'Refund form rejected - resident {n}', f'Forwarding batch {n}.', days=0, hours=n,
                  conv=f'fwd{n}', name='Paula Vance')
        _mail(s, 'ray@northwind.example', 'Portal help', 'try now', days=1, conv='chat', name='Ray Colton')
        _mine(s, 'Portal help', 'that worked, thanks - we have to find out why it freezes', 1, 'chat')
        txt, _ = assistant._people_context(s, 2)
        heads = [l for l in txt.splitlines() if l.startswith('- ')]
        self.assertIn('Ray Colton', heads[0]); self.assertIn('why it freezes', txt)         # the exchange leads, whole
        self.assertEqual(sum('Paula Vance [' in h for h in heads), 1)                      # one forward drawn in full...
        self.assertTrue(any(h.startswith('- Paula Vance: 6 more') for h in heads))          # ...the rest folded to one line
        s.save_doc('soul', '# SOUL\n' + 'x' * 3000 + '\n## Systems\nThe portal is the vendor app.', 'owner')
        seen = {}
        assistant.think(s, [], lambda system, user, **k: seen.update(system=system) or '{"say": []}')
        self.assertIn('The portal is the vendor app.', seen['system'])                     # past the old 1500-char cut

    def test_the_month_of_counts_is_read_once_a_week_and_only_a_real_run_starts_the_week(self):
        """Automation ideas, folded into the Advisor (the owner, 2026-09-25): its evidence rides in the Advisor's payload
        as the Automation card - once a week, because it is ~17k characters and the check runs every 30 minutes."""
        s = _store()
        for n in range(4):
            _mail(s, 'digest@vendor.example', f'Weekly numbers {n}', 'Numbers attached.', days=n, name='Vendor Digest')
        self.assertIn(assistant.AUTOMATION_HEAD, assistant.facts(s))                         # never read: due
        self.assertIn('[taskuary.automation]', assistant.PROMPT)                            # the prompt places it
        self.assertIsNone(s.get_settings().get('assistant_automation_read'))                # a preview starts nothing
        with mock.patch('taskuary.llm.build_llm', return_value=None):
            assistant.run(s, llm=lambda *a, **k: '{"say": []}', force=True)
        self.assertTrue(s.get_settings().get('assistant_automation_read'))                  # the check that read it did
        self.assertNotIn(assistant.AUTOMATION_HEAD, assistant.facts(s))                     # ...so the week is quiet
        s.set_setting('assistant_automation_read', _ago(days=8), 't')
        self.assertIn(assistant.AUTOMATION_HEAD, assistant.facts(s))                        # ...until it has passed

    def test_an_unedited_copy_of_the_last_shipped_prompt_is_healed_and_an_edited_one_is_kept(self):
        import hashlib, os
        from taskuary.store import SQLiteStore
        with tempfile.TemporaryDirectory(ignore_cleanup_errors=True) as d:        # Windows holds the sqlite file past close
            path = os.path.join(d, 'h.db'); s = SQLiteStore(path)
            adv = next(r for r in s.list_sources(active_only=False) if r['Address'] == 'Advisor')
            for text in ('the prompt as it shipped last week', 'the prompt as the owner rewrote it'):
                c = json.loads(adv['ConfigJson']) | {'ai_prompt': text}
                s._exec('UPDATE source SET ConfigJson=? WHERE SourceId=?', (json.dumps(c), adv['SourceId'])); s.cx.close()
                shipped = (hashlib.sha256(b'the prompt as it shipped last week').hexdigest(),)
                with mock.patch.object(assistant, 'OLD_PROMPT_SHA', shipped):
                    s = SQLiteStore(path)
                got = json.loads(next(r for r in s.list_sources(active_only=False) if r['Address'] == 'Advisor')['ConfigJson'])['ai_prompt']
                self.assertEqual(got, assistant.PROMPT if 'shipped' in text else text)
            s.cx.close()
        self.assertNotIn(hashlib.sha256(assistant.PROMPT.encode()).hexdigest(), assistant.OLD_PROMPT_SHA)

    def test_an_idea_about_work_just_handled_is_not_said(self):
        """"it should not make another advice if we just did it" (the owner, 2026-09-25): a loop fixed and closed yesterday
        came back as a fresh idea - and a fresh task - the next morning. For a week after a task closes, the Advisor's
        lines about it are dropped; a recurrence reaches the owner as its own mail, which triage puts back on the task."""
        s = _store()
        fixed = s.create_task({'Title': 'Vendor create loop', 'Kind': 'coding', 'Status': 'open'}, 'o')
        s.add_comment(fixed, 'coder', 'agent', 'The agent closed this itself: the name-keyed delete bug, fixed and deployed.')
        s.update_task(fixed, {'Status': 'done'}, 'coder')
        live = s.create_task({'Title': 'Budget tab missing', 'Kind': 'general', 'Status': 'open'}, 'o')
        mid = _mail(s, 'erin@northwind.example', 'Vendor create', 'Rejected again.', days=0, name='Erin')
        s._exec('UPDATE message SET TaskId=? WHERE MessageId=?', (fixed, mid))
        say = lambda *lines: json.dumps({'say': [dict(zip(('key', 'text', 'why', 'about', 'mid'), l)) for l in lines]})
        got = assistant.parse(s, say(('idea:loop-again', 'The vendor loop rejected a new vendor again.', 'mid 1', f'TQ-{fixed:04d}', None),
                                     ('idea:loop-mail', 'The rejection mail says the fix did not hold.', '', None, mid),
                                     ('idea:budget', f'TQ-{fixed:04d} is done, but TQ-{live:04d} still has no tab.', '', None, None)), [])
        self.assertEqual([g['key'] for g in got], ['idea:budget'])                 # the one about OPEN work stands
        self.assertEqual(got[0]['action']['tid'], live)
        self.assertIn('closed', assistant._done(s, 7)); self.assertIn('name-keyed delete bug', assistant._done(s, 7))
        s._exec('UPDATE task SET ClosedAt=? WHERE TaskId=?', (_ago(days=8), fixed))
        self.assertEqual(len(assistant.parse(s, say(('idea:loop-again', 'The loop is back.', '', f'TQ-{fixed:04d}', None)), [])), 1)

    def test_the_advisor_raises_new_ideas_and_never_edits_one(self):
        """"advisor can only send new ideas not edit an existing idea" (the owner, 2026-09-25): the model reworded the
        same key overnight, the new Sig read as new facts, and a read idea was rewritten and back on Next."""
        s = _store(); now = datetime.now()
        row = s.upsert_idea({'key': 'idea:alert', 'kind': 'idea', 'text': 'The alert group is refused, not a bug.', 'sig': 'a'}, _ago())
        state = {i['Key']: i for i in s.list_ideas()}
        self.assertFalse(assistant.fresh(state, {'key': 'idea:alert', 'sig': 'reworded'}, now))     # said, whatever the wording
        s.set_idea_status(row['IdeaId'], 'dismissed', 'owner')
        self.assertFalse(assistant.fresh({i['Key']: i for i in s.list_ideas()}, {'key': 'idea:alert', 'sig': 'b'}, now))
        self.assertTrue(assistant.fresh(state, {'key': 'idea:other', 'sig': 'a'}, now))           # a new key is news
        s.upsert_idea({'key': 'idea:alert', 'kind': 'idea', 'text': 'Reworded.', 'sig': 'b', 'action': {'type': 'note'}}, _ago())
        again = s.get_idea(row['IdeaId'])
        self.assertEqual((again['Text'], again['Sig']), ('The alert group is refused, not a bug.', 'a'))
        # ...and the model is shown the KEY of what it said, with when, so the same subject reuses it
        said = assistant._said(s)
        self.assertIn('[key idea:alert · said ', said); self.assertIn('2 times', said)
        s.set_idea_status(row['IdeaId'], 'done', 'owner')
        self.assertIn('idea:alert', assistant._said(s))                                          # acted on this week: still there
        s._exec('UPDATE idea SET DecidedAt=? WHERE IdeaId=?', (_ago(days=8), row['IdeaId']))
        self.assertNotIn('idea:alert', assistant._said(s))


class ApiTests(unittest.TestCase):
    def test_a_historical_false_reply_nag_is_returned_as_answered(self):
        from fastapi.testclient import TestClient
        from taskuary import server
        s = _store()
        tid = s.create_task({'Title': 'Fix access', 'Kind': 'coding', 'Status': 'done'}, 't')
        mid = _mail(s, 'jd@ours.com', 'Access', 'Can I try again?', days=0,
                    conv='api-access', tid=tid, status='routed', name='JD')
        rid = s.add_review({'TaskId': tid, 'MessageId': mid, 'Kind': 'draft_reply',
                            'DraftText': 'Fixed — please try again.', 'Status': 'pending'})
        s.decide_review(rid, 'approved', 'Fixed — please try again.', 'owner')
        s.upsert_idea({'key': 'idea:false-reply-nag', 'kind': 'idea',
                       'text': "Nobody replied to JD. I'd answer now.",
                       'action': {'type': 'message', 'mid': mid}}, _ago())
        with mock.patch.object(server, 'store', s):
            row = TestClient(server.app).get('/api/assistant/ideas?status=open').json()['data'][0]
        self.assertEqual(row['answered']['text'], 'Fixed — please try again.')
        self.assertTrue(row['answered']['at'])

    def test_the_endpoints_round_trip(self):
        from fastapi.testclient import TestClient
        from taskuary import server
        s = server.store
        s.set_setting('calendar_enabled', '0', 't'); s.set_setting('learn_enabled', '0', 't')
        _mail(s, DANA, 'API ledger', 'Here.', days=6, conv='api-c1')
        _mine(s, 'Re: API ledger', 'Could you send the reconciled version?', days=4, conv='api-c1')
        c = TestClient(server.app)
        sid = assistant.source(s)['SourceId']
        from taskuary import reports
        with mock.patch('taskuary.llm.build_llm', return_value=None):
            r = reports.run_one(s, s.get_source(sid), None, 'manual')   # Run now's road (server._rerun_report)
        self.assertGreaterEqual(r['said'], 1)
        mid = r['message_id']
        self.assertEqual(c.get('/api/assistant/status').status_code, 404)   # the pinned card is gone (2026-08-30)
        ideas = c.get(f'/api/assistant/ideas?mid={mid}').json()['data']
        self.assertTrue(ideas and ideas[0]['status'] == 'open')
        self.assertEqual(len(s.list_ideas('open')), len(c.get('/api/assistant/ideas?status=open').json()['data']))
        r = c.post(f"/api/assistant/ideas/{ideas[0]['id']}/snooze", json={'until': 'tomorrow'})
        self.assertEqual(r.status_code, 200); self.assertEqual(r.json()['verb'], 'snooze'); self.assertTrue(r.json()['when'])
        # the words that are gone are refused, not quietly run: a follow-up and a discussion are a task's agent's now
        for gone in ('nonsense', 'followup', 'discuss'):
            self.assertEqual(c.post(f"/api/assistant/ideas/{ideas[0]['id']}/{gone}").status_code, 422)


class NotesToSelf(unittest.TestCase):
    """A check ends with a note to the next one, and the next one reads it - even when the check
    itself posted nothing. Twenty-minute checks that each start from zero would research the same
    silence three times an hour."""
    def test_note_survives_a_quiet_check_and_reaches_the_next(self):
        s = _store(); seen = []
        def llm(system, user, **k):
            seen.append(user)
            return json.dumps({'say': [], 'notes': 'Dana answers on Tuesdays - the SOW thread is not a chase before then'})
        out = assistant.run(s, llm=llm, force=True)
        self.assertEqual(out['said'], 0)                                            # nothing on the Timeline...
        self.assertIn('Tuesdays', s.get_settings().get('assistant_notes', ''))         # ...but the note is kept
        self.assertIn('Tuesdays', out['reviewed']['notes'])
        self.assertIn('(none yet', seen[0])                                         # the first check had none to read
        assistant.run(s, llm=llm, force=True)
        self.assertIn('Tuesdays', seen[1])                                          # the second one does
        self.assertIn('rewrite them', seen[1])

    def test_an_empty_note_keeps_the_last_one(self):
        s = _store()
        assistant.run(s, llm=lambda *a, **k: '{"say": [], "notes": "renewal is on the 15th"}', force=True)
        assistant.run(s, llm=lambda *a, **k: '{"say": []}', force=True)
        self.assertIn('15th', s.get_settings().get('assistant_notes', ''))


class LastRunRecord(unittest.TestCase):
    """A quiet check posts nothing - the Reports tab still shows what it read and why it stayed quiet."""
    def test_a_quiet_assistant_run_leaves_its_record_on_the_source(self):
        from taskuary import reports
        s = _store()
        src = next(x for x in s.list_sources(active_only=False) if json.loads(x['ConfigJson'] or '{}').get('type') == 'assistant')
        reports.run_report_source(s, src, lambda *a, **k: '{"say": [], "notes": "nothing new; Dana answers Tuesdays"}')
        rec = reports.last_runs(s)[src['SourceId']]
        self.assertEqual((rec['type'], rec['said'], rec['failed']), ('assistant', 0, False))
        self.assertIn('Tuesdays', rec['reviewed']['notes'])
        self.assertIn('ALREADY SAID', rec['inputs'])                     # the exact text the model saw

    def test_every_run_joins_the_history_with_what_it_read_and_why_it_said_it(self):
        """The owner (2026-08-30): "a history of runs on the Reports tab... to see what it processed and why
        it created certain things". Quiet runs and posting runs alike; the list is light, one run is whole."""
        from taskuary import reports
        s = _store()
        _mail(s, DANA, 'Q3 ledger', 'Here is the ledger.', days=6, conv='c1')
        _mine(s, 'Re: Q3 ledger', 'Could you send the reconciled version by Friday?', days=4, conv='c1')
        src = next(x for x in s.list_sources(active_only=False) if json.loads(x['ConfigJson'] or '{}').get('type') == 'assistant')
        reports.run_report_source(s, src, lambda *a, **k: '{"say": [], "notes": "quiet"}')
        reports.run_report_source(s, src, lambda *a, **k: json.dumps({'say': [{'key': 'followup:c1', 'text': "Dana owes you the ledger - I'd nudge.", 'why': 'four days is long for her'}]}))
        runs = s.report_runs(src['SourceId'])
        self.assertEqual([(r['said'], r['failed'], r['type']) for r in runs], [(1, False, 'assistant'), (0, False, 'assistant')])   # newest first
        self.assertNotIn('inputs', runs[0]); self.assertGreater(runs[0]['inputChars'], 100)                                # the list is light
        self.assertEqual(runs[0]['lines'][0]['kind'], 'followup'); self.assertIn("The model's read: four days", runs[0]['lines'][0]['why'])
        whole = s.get_report_run(runs[0]['runId'])
        self.assertIn('ALREADY SAID', whole['inputs']); self.assertEqual(whole['reviewed']['candidates'], {'followup': 1})
        self.assertEqual(whole['messageId'], s.get_message(whole['messageId'])['MessageId'])
        self.assertIsNone(s.get_report_run(99999))
        # a failed run is kept too, with its error
        bad = s.save_source({'Channel': 'report', 'Address': 'Broken', 'Active': 1, 'ConfigJson': json.dumps({'type': 'digest', 'title': 'Broken'})}, 't')
        with mock.patch('taskuary.reports.render_report', side_effect=RuntimeError('no brain')):
            reports.run_report_source(s, s.get_source(bad), None)
        self.assertEqual(s.report_runs(bad)[0]['failed'], True)
        # the history is capped per report
        with mock.patch.object(type(s), 'REPORT_RUNS_KEPT', 3):
            for _ in range(4): reports.run_report_source(s, src, lambda *a, **k: '{"say": []}')
        self.assertEqual(len(s.report_runs(src['SourceId'])), 3)

    def test_the_history_endpoints(self):
        from fastapi.testclient import TestClient
        from taskuary import server, reports
        s = server.store
        s.set_setting('calendar_enabled', '0', 't')
        src = assistant.source(s)
        reports.run_report_source(s, src, lambda *a, **k: '{"say": [], "notes": "nothing"}')
        c = TestClient(server.app)
        runs = c.get(f"/api/reports/{src['SourceId']}/runs").json()['data']
        self.assertTrue(runs); self.assertNotIn('inputs', runs[0])
        one = c.get(f"/api/reports/runs/{runs[0]['runId']}").json()
        self.assertIn('ALREADY SAID', one['inputs']); self.assertEqual(one['runId'], runs[0]['runId'])
        self.assertEqual(c.get('/api/reports/runs/99999').status_code, 404)
        self.assertEqual(c.get('/api/reports/99999/runs').status_code, 404)


class WhatItReadsTests(unittest.TestCase):
    """The owner (2026-08-30): iterate on the data it brings in until it says something useful and surprising.
    Handed subjects and counts, the model wrote 'no content given'; so the check reads the words, the
    auto-replies, the calendar, and the machines' schedules and causes."""
    def _chat(self, s, who, body, days=0, hours=0, status='filed', mine=False):
        return s.add_message({'ExternalId': f'chat:{who}:{body[:20]}:{days}:{hours}', 'ConversationId': 'chat1', 'Channel': 'teams', 'SourceName': 'Teams',
                              'Subject': f'Teams chat with {who}', 'FromName': 'You' if mine else who, 'FromEmail': ME if mine else f'{who.split()[0].lower()}@ours.com',
                              'SentAt': _ago(days, hours), 'BodyText': body, 'Status': 'context' if mine else status})

    def test_out_of_office_rides_on_the_followup_instead_of_a_chase(self):
        s = _store()
        _mail(s, DANA, 'Q3 ledger', 'Here is the ledger.', days=6, conv='c1')
        _mine(s, 'Re: Q3 ledger', 'Could you send the reconciled version by Friday?', days=4, conv='c1')
        _mail(s, DANA, 'Automatic reply: Q3 ledger', 'I am out of the office until Monday September 7th with no access to email.', days=3, conv='c9')
        self.assertEqual(assistant.ooo(s), {DANA: f'out until Monday September 7th (auto-reply {assistant._when(_ago(3))[:10]})'})
        got = assistant.followups(s, hours=24)
        self.assertEqual(len(got), 1)
        self.assertIn('they are out until Monday September 7th', got[0]['text']); self.assertIn("I'd wait", got[0]['text'])
        self.assertIn('BUT Dana is out until Monday September 7th', got[0]['facts'])
        self.assertTrue(got[0]['sig'].split('|')[0].endswith(':away'))         # the facts changed: a dismissed chase may be said again as a wait
        self.assertIn('OUT OF OFFICE (from their auto-replies):\n- ' + DANA, assistant.inputs(s, got))

    def test_what_people_said_carries_the_words_and_marks_yours(self):
        s = _store()
        self._chat(s, 'Priya Shah', 'Rina said the server was updating? Did she understand wrong?', hours=5)
        self._chat(s, 'Priya Shah', 'Also, can you please fill out the performance review? It is almost my hire date.', hours=4)
        self._chat(s, 'Priya Shah', 'Looking now - the review goes out today.', hours=3, mine=True)
        self._chat(s, 'Priya Shah', 'She said that every day from 4 - 5:00 it does not work', hours=2)
        _mail(s, 'noreply@robots.com', 'Vendor Create', 'This is an automated message. A vendor was created.', days=0, conv='r1')
        s.add_message({'ExternalId': 'rep:1', 'ConversationId': 'rep', 'Channel': 'report', 'SourceName': 'Morning digest', 'Subject': 'Morning digest — today',
                       'FromName': 'Morning digest', 'SentAt': _ago(0, 1), 'BodyText': 'By the tags...', 'Status': 'feed'})
        txt = assistant._people(s)
        self.assertIn('- Priya Shah [teams] re "Teams chat with Priya Shah" - 3 new, last word THEIRS', txt)
        self.assertIn('"Also, can you please fill out the performance review?', txt)
        self.assertIn('    you ', txt); self.assertIn('the review goes out today', txt)   # the owner's own line, marked
        self.assertNotIn('Vendor Create', txt); self.assertNotIn('Morning digest', txt)  # robots and reports are not people
        self.assertEqual(assistant._people(_store()), '(no person wrote in the last two days)')
        inp = assistant.inputs(s, [])
        for head in ('NOW: ', 'WHAT PEOPLE SAID', 'OUT OF OFFICE', 'CALENDAR (the next two days):\n(nothing on the calendar for two days - calendar off)', 'ARRIVED IN THE LAST TWO DAYS'):
            self.assertIn(head, inp)
        self.assertIn('CANDIDATES (new since the last post):', assistant.facts(s))     # the Reports tab's Preview is the same text

    def test_arrivals_carry_the_reports_schedule_and_the_failures_cause(self):
        s = _store()
        s._exec("INSERT INTO source (Channel, Address, Owner, Active, ConfigJson) VALUES ('report', 'Nightly', 't', 1, ?)",
                (json.dumps({'type': 'digest', 'title': 'Nightly', 'daily_at': '08:00', 'on_startup': True}),))
        for i in range(3):
            s.add_message({'ExternalId': f'n:{i}', 'ConversationId': f'n{i}', 'Channel': 'report', 'SourceName': 'Nightly', 'Subject': 'Nightly — FAILED', 'FromName': 'Nightly',
                           'SentAt': _ago(0, i + 1), 'BodyText': 'Report error: Login timeout expired (0)', 'Status': 'feed'})
        _mail(s, 'notifications@github.com', '[o/r] Run failed: ci - master (abc1234)', 'ci: Some jobs were not successful\n\nci / build-web Succeeded in 27 seconds\n\n'
              'ci / test (ubuntu-latest, 3.12) Failed in 49 seconds\n1\nci / test (windows-latest, 3.10) Failed in 3 minutes\n', days=0, conv='g1', status='ignored', name='Alex')
        txt = assistant._recent(s)
        self.assertIn('x3 [report] Nightly: "Nightly — FAILED"', txt)
        self.assertIn('[schedule: daily at 08:00 + on app start] -> "Report error: Login timeout expired (0)"', txt)
        self.assertIn('-> failed: test (ubuntu-latest, 3.12), test (windows-latest, 3.10)', txt)
        self.assertEqual(assistant._schedules(s)['Nightly'], 'daily at 08:00 + on app start')

    def test_arrivals_say_when_a_report_last_ran_even_when_it_posted_nothing(self):
        # A routed report whose judge held the run back files NO message, so the newest mid read as
        # its last firing: a 140-minute timer looked stalled two runs after it fired on time (TQ-0685).
        from taskuary.reports import LAST_RUN
        s = _store()
        s._exec("INSERT INTO source (Channel, Address, Owner, Active, ConfigJson) VALUES ('report', 'Error check', 't', 1, ?)",
                (json.dumps({'type': 'mssql', 'title': 'Error check', 'every_minutes': 140}),))
        sid = s._one("SELECT SourceId FROM source WHERE Address='Error check'")['SourceId']
        s.add_message({'ExternalId': 'e:1', 'ConversationId': 'e', 'Channel': 'report', 'SourceName': 'Error check', 'Subject': 'Error check - 3 rows',
                       'FromName': 'Error check', 'SentAt': _ago(0, 5), 'BodyText': 'three errors', 'Status': 'feed'})
        s.set_setting(f'{LAST_RUN}{sid}', json.dumps({'at': _ago(0, 0), 'message_id': None, 'said': 0, 'failed': False}), 'report')
        txt = assistant._recent(s)
        self.assertIn(f'[schedule: every 140 minutes; last ran {assistant._when(_ago(0, 0))}, nothing to report so nothing was filed]', txt)
        s.set_setting(f'{LAST_RUN}{sid}', json.dumps({'at': _ago(0, 0), 'message_id': 9793, 'said': 1, 'failed': False}), 'report')
        self.assertIn('; last ran ', assistant._schedules(s)['Error check']); self.assertIn(', posted mid 9793]', assistant._recent(s))
        s.set_setting(f'{LAST_RUN}{sid}', json.dumps({'at': _ago(0, 0), 'message_id': 9799, 'failed': True, 'error': 'Login timeout'}), 'report')
        self.assertIn(', failed]', assistant._recent(s))

    def test_arrivals_carry_the_email_body_not_just_the_subject(self):
        s = _store()
        _mail(s, 'notifications@github.com', 'Devarajan invited you to acme-hiring-screener',
              'Devarajan invited you to collaborate on acme-hiring-screener. The repository screens '
              'applicants for a multi-factor authentication engineering role. You can accept or decline the invitation.',
              days=0, conv='invite', status='ignored', name='Devarajan')
        txt = assistant._recent(s)
        self.assertIn('Devarajan invited you to acme-hiring-screener', txt)
        self.assertIn('-> says: "Devarajan invited you to collaborate', txt)
        self.assertIn('screens applicants for a multi-factor authentication engineering role', txt)
        self.assertNotIn('acme-hiring-screener', assistant._people(s))       # automated mail only reaches the rolled-up arrivals block
        self.assertIn('screens applicants for a multi-factor authentication engineering role', assistant.inputs(s, []))

    def test_two_checks_at_once_post_one_row(self):
        """2026-08-29 23:59:02: two clocks fired in the same second and the same followup posted twice."""
        import threading, time
        s = _store()
        _mail(s, DANA, 'Q3 ledger', 'Here is the ledger.', days=6, conv='c1')
        _mine(s, 'Re: Q3 ledger', 'Could you send the reconciled version by Friday?', days=4, conv='c1')
        def llm(system, user, **k):
            time.sleep(0.2); return json.dumps({'say': [{'key': 'followup:c1', 'text': "Dana owes you the ledger - I'd nudge.", 'mid': None}]})
        outs = []
        ts = [threading.Thread(target=lambda: outs.append(assistant.run(s, llm=llm, force=True))) for _ in range(2)]
        for t in ts: t.start()
        for t in ts: t.join()
        self.assertEqual(sorted(o['said'] for o in outs), [0, 1])
        self.assertEqual(len([r for r in s.feed(limit=10) if r['Channel'] == 'assistant']), 1)

    def test_the_rows_line_is_cut_at_a_word_and_the_post_counts_the_threads_it_read(self):
        s = _store()
        self._chat(s, 'Priya Shah', 'can you please fill out the performance review?', hours=4)
        long = "I would go into Monday's Target Meeting with Priya's note that exporting freezes the app every afternoon at four"
        out = assistant.run(s, llm=lambda *a, **k: json.dumps({'say': [{'key': 'idea:a', 'text': long, 'mid': None}, {'key': 'idea:b', 'text': 'Second.', 'mid': None}]}), force=True)
        row = s.get_message(out['message_id'])
        self.assertEqual(row['Subject'], long[:90].rsplit(' ', 1)[0] + '… (+1 more)')
        self.assertEqual(out['reviewed']['people'], 1); self.assertIn('1 thread(s) of what people said', row['BodyText'])

    def test_a_line_naming_a_task_carries_its_tid_and_the_model_pass_is_not_swallowed(self):
        """parse() resolves "TQ-0001" to the task so the pipe can tell an agent already has the work
        - and it reads the store to do that. For a day it was never handed one, and the NameError
        died inside _run's broad `except Exception`, so every post fell back to the bare facts with
        only a warning to show for it (the owner, 2026-09-04: "the model pass failed, posting the
        facts alone - name 'store' is not defined"). Asserting `model` is what catches that."""
        s = _store()
        tid = s.create_task({'Title': 'July financials', 'Kind': 'coding', 'Status': 'in_progress'}, 't')
        self._chat(s, 'Priya Shah', 'can you please fill out the performance review?', hours=4)
        out = assistant.run(s, force=True, llm=lambda *a, **k: json.dumps(
            {'say': [{'key': 'idea:a', 'text': f'TQ-{tid:04d} July financials has not moved since Tuesday.', 'mid': None}]}))
        self.assertTrue(out['reviewed']['model'])                                  # the pass ran; it did not fall back
        self.assertEqual([l['action'].get('tid') for l in out['lines']], [tid])
