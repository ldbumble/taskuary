import unittest
import json
from datetime import datetime, timedelta
from unittest import mock

from taskuary import evening, reports
from taskuary.store import MemoryStore
from taskuary.testing import Factory


def _sent(s, rid, text):
    "His Send on review `rid`, gone as the provider confirms it (Factory.sent: on the record)."
    s.decide_review(rid, 'approved', text, 'owner'); Factory(s).sent(rid)


def _ago(hours):
    return (datetime.now() - timedelta(hours=hours)).strftime('%Y-%m-%d %H:%M:%S')


def _mail(store, external, subject, sender='person@example.com', hours=1, status='filed', body='Please review this.'):
    return store.add_message({'ExternalId': external, 'Channel': 'email', 'SourceName': 'owner@example.com',
                              'Subject': subject, 'FromName': sender.split('@')[0].title(), 'FromEmail': sender,
                              'SentAt': _ago(hours), 'BodyText': body, 'Status': status})


class EveningGatherTests(unittest.TestCase):
    def test_it_keeps_sent_invites_and_open_work_but_excludes_noise_and_old_mail(self):
        s = MemoryStore()
        s.set_setting('owner_email', 'owner@example.com', 'test')
        s.add_message({'ExternalId': 'sent', 'ConversationId': 'thread-1', 'Channel': 'email',
                       'SourceName': 'owner@example.com', 'Subject': 'Re: Budget', 'FromName': 'You',
                       'FromEmail': 'owner@example.com', 'SentAt': _ago(1), 'BodyText': 'Approved.',
                       'Status': 'context'})
        invite = _mail(s, 'invite', 'Invitation: Budget sync')
        s.add_route(invite, None, 'file', None, 'triage: fyi - a calendar invite - a meeting to be ready for', [], 'triage')
        s._exec('UPDATE message SET MailMetaJson=? WHERE MessageId=?', (json.dumps({'folder': 'inbox', 'invite': True}), invite))
        open_mid = _mail(s, 'open', 'Renewal decision')
        tid = s.create_task({'Title': 'Renewal decision', 'Kind': 'general', 'Priority': 'urgent'}, 'test')
        s._exec('UPDATE message SET TaskId=?, Status=? WHERE MessageId=?', (tid, 'routed', open_mid))
        flagged = _mail(s, 'flagged', 'Contract question')
        s._exec('UPDATE message SET MailMetaJson=? WHERE MessageId=?',
                (json.dumps({'folder': 'inbox', 'focus': 'other', 'flag': 'flagged'}), flagged))
        custom = _mail(s, 'custom', 'Filed vendor note')
        s._exec('UPDATE message SET MailMetaJson=? WHERE MessageId=?',
                (json.dumps({'folder': 'custom-folder-id', 'focus': 'focused'}), custom))
        promo = _mail(s, 'promo', 'September deals', 'marketing@vendor.example', body='Unsubscribe from this newsletter')
        s.add_route(promo, None, 'file', None, 'triage: fyi - a newsletter', [], 'triage', verdict={'intent': 'fyi', 'sender_class': 'bulk'})
        receipt = _mail(s, 'receipt', 'Payment receipt', 'billing@vendor.example', body='Your payment confirmation is attached.')
        s.add_route(receipt, None, 'file', None, 'triage: fyi - a receipt', [], 'triage', verdict={'intent': 'fyi', 'sender_class': 'automated'})
        # a PERSON writing about a payment is not a receipt: the word list that dropped "your payment" dropped this too
        overdue = _mail(s, 'overdue', 'Your payment is overdue - please call', 'gail@vendor.example', body='Your payment is overdue - please call me today.')
        s._exec('UPDATE message SET TaskId=?, Status=? WHERE MessageId=?',
                (s.create_task({'Title': 'Call about the overdue payment', 'Kind': 'task'}, 'test'), 'routed', overdue))
        _mail(s, 'old', 'Yesterday', hours=9)

        text = evening.gather(s, 8)
        self.assertIn('Re: Budget', text)
        self.assertIn('Invitation: Budget sync', text)
        self.assertIn('invite handled', text)
        self.assertIn('Renewal decision', text)
        self.assertIn('priority=urgent', text)
        self.assertIn('Contract question', text)
        self.assertIn('flagged=yes', text)
        self.assertIn('inbox_lane=other', text)
        self.assertNotIn('Filed vendor note', text)
        self.assertNotIn('September deals', text)
        self.assertNotIn('Payment receipt', text)
        self.assertIn('Your payment is overdue - please call', text)
        self.assertNotIn('Yesterday', text)

    def test_the_evening_report_uses_the_assistant_voice_contract(self):
        s = MemoryStore()
        s.create_task({'Title': 'Renewal decision', 'Kind': 'task'}, 'test')     # something to report on (an empty home is skipped)
        cfg = {'type': 'evening_inbox', 'hours': 8, 'ai_prompt': evening.PROMPT}
        seen = {}
        reports.render_report(s, cfg, llm=lambda system, user, **kw: seen.update(system=system, user=user) or 'brief')
        self.assertIn('END OF DAY BRIEF', seen['system'])
        self.assertIn('ACCOMPLISHED EVIDENCE', seen['user'])

    def test_a_stale_server_explains_that_the_new_report_type_needs_a_restart(self):
        s = MemoryStore()
        cfg = {'type': 'evening_inbox', 'hours': 8, 'ai_prompt': evening.PROMPT}
        with mock.patch.dict(reports.REGISTRY, {}, clear=True):
            with self.assertRaisesRegex(RuntimeError, "not available in this running Taskuary.*Restart Taskuary"):
                reports.render_report(s, cfg)


class TheDayAsItWasTests(unittest.TestCase):
    def test_the_brief_tells_the_day_his_agents_had_never_the_assistants_chat_nor_a_sent_thread_as_owed(self):
        """Round 3, 2026-11-22: two threads approved and sent stood as "focus for tomorrow", "Completed the Taskuary guide task" (the Assistant's
        own chat) stood as done, and the chart, sheet and Paula's email his agents made and sent were missing."""
        from taskuary import general
        s = MemoryStore()
        dock = s.create_task({'Title': 'Taskuary guide', 'Kind': 'general', 'Status': 'done', 'SourceRef': general.DOCK_TAG}, 'owner')
        s._exec('UPDATE task SET ClosedAt=? WHERE TaskId=?', (_ago(1), dock))
        tid = s.create_task({'Title': 'Monitor quote', 'Kind': 'reply', 'Status': 'open'}, 'router')
        first = _mail(s, 'q1', 'Monitor quote', 'ray@northwind.example', hours=3, status='routed'); s._exec('UPDATE message SET TaskId=? WHERE MessageId=?', (tid, first))
        second = _mail(s, 'q2', 'Re: Monitor quote', 'ray@northwind.example', hours=2, status='routed'); s._exec('UPDATE message SET TaskId=? WHERE MessageId=?', (tid, second))
        rv = s.add_review({'TaskId': tid, 'MessageId': second, 'Kind': 'draft_reply', 'Status': 'pending', 'DraftText': 'Approved - order them.'})
        _sent(s, rv, 'Approved - order them.')
        mail = s.add_review({'TaskId': tid, 'Kind': 'slot', 'Status': 'pending', 'Deliver': json.dumps({'to': ['paula@northwind.example']})})
        _sent(s, mail, 'Hi Paula')
        ev = evening.collect(s, 24)
        assert not [p for p in ev['priorities'] if 'Monitor quote' in p], ev['priorities']
        assert not [d for d in ev['done'] if 'Taskuary guide' in d], ev['done']
        assert any('paula@northwind.example' in a for a in ev['accomplished']), ev['accomplished']

    def test_a_correction_sent_as_new_emails_is_read_from_the_tasks_own_state_never_as_her_mail_unanswered(self):
        """Walk 6, the third walk running: Paula Vance wrote "headcount should be 214, not 212" on the board-pack task; its agent fixed the pack
        and sent the corrected copies as two new emails, ticked every to-do and said nothing was left - and the brief put "fix the headcount"
        under Tomorrow, because no reply sat on her very mail. What a task owes is the task's own facts; the brief only carries them."""
        from taskuary import general
        s = MemoryStore(); s.set_setting('owner_email', 'alex@northwind.example', 't')
        tid = s.create_task({'Title': 'Q3 board pack', 'Kind': 'general', 'Status': 'open'}, 'owner')
        her = _mail(s, 'p1', 'Headcount in the pack', 'paula@northwind.example', hours=2, status='routed', body='Headcount should be 214, not 212.')
        s._exec('UPDATE message SET TaskId=? WHERE MessageId=?', (tid, her))
        for who in ('erin@northwind.example', 'gail@northwind.example'):
            rv = s.add_review({'TaskId': tid, 'Kind': 'slot', 'Status': 'pending', 'Deliver': json.dumps({'to': [who], 'subject': 'Corrected Q3 board pack'})})
            _sent(s, rv, 'Corrected pack attached.')
        items = s.set_task_checklist(tid, ['Fix the headcount', 'Send the corrected pack'], 'agent')
        for i in items: s.tick_checklist_item(tid, i['id'], True, 'agent')
        s.add_comment(tid, 'agent', general.SUMMARY_TYPE, json.dumps({'did': 'Corrected the pack and sent it', 'on_you': [], 'nothing_left': True}))
        ev = evening.collect(s, 8)
        assert not [p for p in ev['priorities'] if 'Headcount' in p], ev['priorities']
        row = next(r for r in ev['on_tasks'] if 'Headcount' in r)
        for fact in ('sent today (2)', 'no input awaited from anyone'): assert fact in row, row
        assert any('no input awaited from anyone' in r for r in ev['open']), ev['open']

    def test_what_went_and_what_was_made_is_said_where_every_summary_reads_a_task_never_its_title(self):
        """Walk 14 (R1): the End-of-day report said "Tomorrow: send the 2026 vendor spend sheet" - sent at 2:26 - and "the Ask HN post first
        needs a Hacker News account" after its agent had made one and he had declined the post: each open task was told by the TITLE its agent
        gave it early on. The brief's line and the Advisor's open work (assistant._open, the digest's too) read the task's one state."""
        from taskuary import assistant, ledger
        s = MemoryStore()
        sheet = s.create_task({'Title': 'Send 2026 monthly vendor spend sheet', 'Kind': 'general', 'Status': 'open'}, 'owner')
        rv = s.add_review({'TaskId': sheet, 'Kind': 'draft', 'Status': 'pending',
                           'Deliver': json.dumps({'channel': 'email', 'to': ['erin@northwind.example'], 'subject': '2026 vendor spend sheet'})})
        _sent(s, rv, 'Hi Erin, the sheet is attached.')
        post = s.create_task({'Title': 'Ask HN post ready to submit', 'Kind': 'general', 'Status': 'open'}, 'owner')
        ledger.account(s, 'news.ycombinator.example', 'alexdoyle', 'made', task=post)
        card = s.add_review({'TaskId': post, 'Kind': 'action', 'Status': 'pending', 'Reason': 'post the Ask HN question',
                             'DraftText': json.dumps({'action': 'browser_act', 'what': 'post the Ask HN question'})})
        s.decide_review(card, 'rejected', None, 'owner')
        txt = assistant._open(s)
        line = lambda t: next(l for l in txt.splitlines() if f'TQ-{t:04d}' in l)
        self.assertIn('sent "2026 vendor spend sheet" to erin@northwind.example', line(sheet))
        self.assertIn('an account on news.ycombinator.example', line(post)); self.assertIn('he turned down: post the Ask HN question', line(post))
        self.assertIn('sent "2026 vendor spend sheet"', evening.owed(s, s.get_task(sheet), _ago(8)))

    def test_a_post_that_went_live_is_said_as_the_post_never_as_the_hold_it_waited_under(self):
        """Walk 19 (R1): the Chirp post was approved and published at 21:44; the End-of-day report said "Prepared your Chirp post and held it
        for your approval" and "Waiting for your press to publish the post" - the went-live line carried the held card's reason."""
        from taskuary import ledger, proposals
        s = MemoryStore()
        tid = s.create_task({'Title': 'Publish Chirp budget tip', 'Kind': 'general', 'Status': 'open'}, 'owner')
        p = {'action': 'browser_act', 'what': 'Publish your post on Chirp', 'why': 'it speaks for you to other people, so it waits for your press'}
        reason = f"held before it ran, {proposals.HELD_IN['browser_act']}: {p['what']} - {p['why']}"
        rv = s.add_review({'TaskId': tid, 'Kind': 'action', 'Status': 'pending', 'Reason': reason, 'DraftText': json.dumps(p)})
        s.decide_review(rv, 'approved', None, 'owner')
        self.assertTrue(ledger.went(s, rv, {'url': 'http://chirp.test/p/1'}))
        for line in (ledger.of_task(s, tid)[0], evening.owed(s, s.get_task(tid), _ago(8))):
            self.assertIn('went live: Publish your post on Chirp - http://chirp.test/p/1', line)
            self.assertNotIn('waits for your press', line); self.assertNotIn('held before', line)
        # ...and a row written before keeps the hold's reason in its record: it is said as the act all the same
        ledger.write(s, 'act', reason, '', 'went', 'rv0', tid, None, {'what': reason})
        self.assertFalse(any('waits for your press' in l for l in ledger.of_task(s, tid)))

    def test_what_he_did_is_newest_first_across_mail_and_acts_that_went_live(self):
        """Walk 20 (R1): the Chirp post went live after the night's mail went out, but every act was added after every mail - under a header
        that says newest first - and the brief, at most five items, left the post out though its row was there."""
        from taskuary import ledger
        s = MemoryStore()
        for i, h in enumerate((3, 2.5, 2, 1.5, 1.2, 1.1)):
            s.add_message({'ExternalId': f'out{i}', 'Channel': 'email', 'SourceName': 'alex@northwind.example', 'Direction': 'out', 'Status': 'context',
                           'Subject': f'Vendor follow-up {i}', 'FromEmail': 'alex@northwind.example', 'SentAt': _ago(h), 'BodyText': 'Sent.'})
        tid = s.create_task({'Title': 'Post the budget tip on Chirp', 'Kind': 'general', 'Status': 'open'}, 'owner')
        rv = s.add_review({'TaskId': tid, 'Kind': 'action', 'Status': 'approved', 'Reason': 'Publish your budget season tip on Chirp',
                           'DraftText': json.dumps({'action': 'browser_act'})})
        ledger.went(s, rv, {}, at=_ago(0.5))
        got = evening.collect(s, 8)['accomplished']
        self.assertIn('Publish your budget season tip on Chirp', got[0])
        self.assertEqual([l for l in got if 'Vendor follow-up' in l][0].count('Vendor follow-up 5'), 1, 'the mail newest first too')

    def test_a_card_he_declined_is_told_from_its_state_never_from_the_words_its_turn_wrote_before(self):
        """Walk 13: the agent's turn ended "the post goes out only when you press the card"; he declined the card, and the End-of-day report
        and the Assistant both still said it waited for his press - and the header read "agent waiting on you". What stands is the card's
        own state: he turned it down, nothing waits."""
        from taskuary import general, taskstate
        s = MemoryStore()
        tid = s.create_task({'Title': 'Ask HN post', 'Kind': 'general', 'Status': 'open'}, 'owner')
        s.add_comment(tid, 'assistant', general.ASSISTANT_TYPE, 'The post is set up.')
        s.add_comment(tid, 'agent', general.SUMMARY_TYPE, json.dumps({'did': 'Set up the post', 'nothing_left': False,
                                                                        'on_you': ['The post goes out only when you press the card']}))
        rv = s.add_review({'TaskId': tid, 'Kind': 'action', 'Status': 'pending', 'Reason': 'the agent proposes to post the Ask HN question',
                           'DraftText': json.dumps({'action': 'browser_act', 'what': 'post the Ask HN question'})})
        self.assertEqual(taskstate.turn_outcome(s, tid), 'blocked', 'while the card waits, the turn left it on him')
        s.decide_review(rv, 'rejected', None, 'owner')
        row = evening.owed(s, s.get_task(tid), _ago(8))
        self.assertNotIn('goes out only when you press', row)
        self.assertIn('he turned down: post the Ask HN question', row)
        self.assertEqual(taskstate.left_on_him(s, tid), [])
        self.assertEqual(taskstate.turn_outcome(s, tid), 'agentdone', 'the header no longer reads "agent waiting on you"')

    def test_a_step_the_agent_left_on_him_goes_with_the_card_it_names_never_kept_as_a_to_do(self):
        """Walk 15 (R1): the turn's `on_you` is also written to the task's to-dos (general -> store.set_on_you); he dismissed the Publish card,
        and the End-of-day report still read "to-dos left: Press the Publish card" beside "he turned down: Publish" - "still waiting on you".
        What is left on him is one reading (taskstate.left_on_him), and the to-dos say only the agent's own."""
        from taskuary import general, rulebook, taskstate
        s = MemoryStore()
        tid = s.create_task({'Title': 'Ask HN post', 'Kind': 'general', 'Status': 'open'}, 'owner')
        s.set_task_checklist(tid, ['Make the account'], 'agent')
        s.add_comment(tid, 'assistant', general.ASSISTANT_TYPE, 'The post is set up.')
        on = ['Press the Publish card to post the Ask HN']
        s.add_comment(tid, 'agent', general.SUMMARY_TYPE, json.dumps({'did': 'Set up the post', 'nothing_left': False, 'on_you': on}))
        s.set_on_you(tid, on, 'assistant')
        rv = s.add_review({'TaskId': tid, 'Kind': 'action', 'Status': 'pending', 'Reason': 'post the Ask HN question',
                           'DraftText': json.dumps({'action': 'browser_act', 'what': 'post the Ask HN question'})})
        self.assertIn('waiting for your input: post the Ask HN question', evening.owed(s, s.get_task(tid), _ago(8)))
        self.assertEqual(rulebook.agent_word(s, tid), 'on_you')
        s.decide_review(rv, 'rejected', None, 'owner')
        row = evening.owed(s, s.get_task(tid), _ago(8))
        self.assertNotIn('Press the Publish card', row)
        self.assertNotIn('to-dos left', row, 'an unticked to-do is no work left: the brief reads where the task stands (walk 17, K3)')
        self.assertIn('he turned down: post the Ask HN question', row)
        self.assertNotEqual(rulebook.agent_word(s, tid), 'on_you', 'nor the rail and header read it as on him')

    def test_where_it_stands_is_the_cards_and_the_wait_never_the_agents_title(self):
        """Walk 16: after Dismiss the brief was told "TQ-0003 Ask HN post, awaiting Submit - agent done" and trusted the title; and a task whose
        sent reply asked Erin something read "agent done" the moment it went."""
        from taskuary import asks, assistant, general
        s = MemoryStore(); s.set_setting('owner_email', 'alex@northwind.example', 't')
        tid = s.create_task({'Title': 'Ask HN post, awaiting Submit', 'Kind': 'general', 'Status': 'open',
                             'ThreadJson': json.dumps({'asking': 'Post an Ask HN question about the launch'})}, 'owner')
        s.add_comment(tid, 'assistant', general.ASSISTANT_TYPE, 'The post is set up.')
        s.add_comment(tid, 'agent', general.SUMMARY_TYPE, json.dumps({'did': 'Set up the post', 'nothing_left': False, 'on_you': []}))
        rv = s.add_review({'TaskId': tid, 'Kind': 'action', 'Status': 'pending', 'Reason': 'post the Ask HN question',
                           'DraftText': json.dumps({'action': 'browser_act', 'what': 'post the Ask HN question'})})
        s.decide_review(rv, 'rejected', None, 'owner')
        line = next(l for l in assistant._open(s).splitlines() if 'TQ-0001' in l)
        self.assertNotIn('awaiting Submit', line); self.assertIn('Post an Ask HN question', line)
        self.assertIn('no input awaited from anyone', line)
        # ...and a reply that asked a person something: waiting on her answer, never "agent done"
        m = s.add_message({'ExternalId': 'e1', 'ConversationId': 'th-1', 'Channel': 'email', 'Subject': 'Q4 vendor spend', 'FromName': 'Erin Blake',
                           'FromEmail': 'erin@northwind.example', 'SentAt': _ago(2), 'BodyText': 'Spendly is up 40%.', 'Status': 'routed', 'TaskId': tid})
        done = evening.owed(s, s.get_task(tid), _ago(8))
        self.assertIn('agent done', done, 'with nothing on him and nobody asked, its agent is done')
        asks._start_watch(s, tid, s.get_message(m))
        row = evening.owed(s, s.get_task(tid), _ago(8))
        self.assertIn("waiting for Erin's input: Erin Blake's answer", row); self.assertIn('Q4 vendor spend', row)
        self.assertNotIn('agent done', row)

    def test_the_brief_says_what_went_as_what_it_was_never_a_view_file_and_never_an_unanswered_close_as_handled(self):
        """Walk 5, 2026-11-22: "Sent availability slot to Gail" over the week's total, the show tool's view-...json as work done, and a task
        closed with its question to him unanswered told as "confirmed"."""
        from taskuary import general, session_artifacts
        s = MemoryStore()
        tid = s.create_task({'Title': 'Weekly hours', 'Kind': 'general', 'Status': 'open'}, 'owner')
        mail = s.add_review({'TaskId': tid, 'Kind': 'slot', 'Status': 'pending', 'Deliver': json.dumps({'to': ['gail@northwind.example'], 'subject': 'Weekly Timesheet Total'})})
        _sent(s, mail, 'Hi Gail')
        session_artifacts.view(s, tid, '{"title": "Hours"}')
        moved = s.create_task({'Title': 'Office move date', 'Kind': 'general', 'Status': 'open'}, 'owner')
        s.add_comment(moved, 'assistant', general.SUMMARY_TYPE, json.dumps({'did': 'Asked.'}))
        from taskuary import workerstate as ws
        ws.record(s, moved, 'sid1', 'input_needed', text='Is December 12 still the date?', source='api')
        from taskuary import concierge
        concierge.close_task(s, moved); s._exec('UPDATE task SET ClosedAt=? WHERE TaskId=?', (_ago(0), moved))
        ev = evening.collect(s, 24)
        sent = [a for a in ev['accomplished'] if 'state=sent' in a]
        assert sent and 'Weekly Timesheet Total' in sent[0] and 'slot' not in sent[0], sent
        assert not [a for a in ev['accomplished'] if 'view-' in a], ev['accomplished']
        assert any('Office move date' in d and 'unanswered' in d for d in ev['done']), ev['done']


class FirstScheduleTests(unittest.TestCase):
    def test_a_first_run_ritual_waits_until_its_daily_time(self):
        future_time = datetime.now() + timedelta(minutes=2)
        if future_time.day != datetime.now().day:
            self.skipTest('too close to midnight')
        self.assertFalse(reports.is_due({'daily_at': future_time.strftime('%H:%M'),
                                         'first_run_at_schedule': True}, None))

    def test_the_existing_immediate_first_run_default_is_unchanged(self):
        self.assertTrue(reports.is_due({'daily_at': '23:59'}, None))


if __name__ == '__main__':
    unittest.main()


class StaleConnectorErrorTests(unittest.TestCase):
    """Issue #270: "the report ran without Outlook mail, although Outlook was listed among the connectors". An evening report owed at
    startup ran before Outlook's first poll of the session, and last session's stored error named Outlook unreadable."""
    def test_an_error_from_before_this_run_is_not_a_connection_that_cannot_be_read(self):
        from taskuary import channels
        old = (datetime.strptime(channels.BOOT, '%Y-%m-%d %H:%M:%S') - timedelta(hours=3)).strftime('%Y-%m-%d %H:%M:%S')
        now = (datetime.strptime(channels.BOOT, '%Y-%m-%d %H:%M:%S') + timedelta(seconds=5)).strftime('%Y-%m-%d %H:%M:%S')
        jobs = [({'ConnectorId': 1, 'Type': 'outlook', 'Name': 'Outlook mail', 'Active': 1, 'LastError': 'connection reset', 'LastErrorAt': old}, None),
                ({'ConnectorId': 2, 'Type': 'gmail', 'Name': 'Gmail', 'Active': 1, 'LastError': 'connection reset', 'LastErrorAt': now}, None)]
        with mock.patch.object(channels, '_poll_jobs', return_value=jobs):
            got = {x['label']: x['ok'] for x in evening.sources(MemoryStore())}
        self.assertEqual(got, {'Outlook mail': True, 'Gmail': False})


class SourceMarkTests(unittest.TestCase):
    """The owner, 2026-11-02, of '[Outlook mail] - RE: ...' and '[WhatsApp] - (no subject) - ...': "these should be emojis?" """
    def test_a_row_carries_its_source_mark_and_a_chat_is_named_not_no_subject(self):
        s = MemoryStore()
        mid = _mail(s, 'm1', 'RE: Budgets dashboard fix', 'erin@northwind.example')
        s._exec('UPDATE message SET TaskId=? WHERE MessageId=?', (s.create_task({'Title': 'Budgets fix', 'Kind': 'task'}, 'test'), mid))
        cid = s.add_message({'ExternalId': 'w1', 'Channel': 'whatsapp', 'SourceName': 'Ops crew', 'Subject': '', 'FromName': 'Gail Moreno',
                             'FromEmail': '', 'SentAt': _ago(1), 'BodyText': 'Can you look at the rota?', 'Status': 'filed'})
        s._exec('UPDATE message SET TaskId=? WHERE MessageId=?', (s.create_task({'Title': 'Rota', 'Kind': 'task'}, 'test'), cid))
        text = evening.gather(s, 8)
        self.assertNotIn('(no subject)', text)
        self.assertIn('src=✉️', text)
        self.assertIn('sender=Gail Moreno | src=\U0001f4ac | subject=Ops crew', text)
        self.assertIn('src=\U0001f4cc', text)

    def test_the_prompt_asks_for_the_mark_never_a_bracketed_label(self):
        from taskuary.channels import ch_icon
        self.assertNotIn('[Who or where]', evening.PROMPT)
        self.assertIn('src mark', evening.PROMPT)
        self.assertIn('[Who or where]', evening.OLD_PROMPTS[0])       # the stock one before it migrates (store.py)
        self.assertEqual((ch_icon('email'), ch_icon('teams'), ch_icon('nothing-known')), ('✉️', '\U0001f465', '\U0001f517'))
