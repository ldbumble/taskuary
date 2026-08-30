"""The assistant on the Timeline (assistant.py): the half-hourly check that says what it noticed - the
reply you sent and never heard back on, the task gone quiet, its
own ideas - once each, with buttons. All offline: the model is a lambda, the calendar is off.
"""
import json, unittest
from datetime import datetime, timedelta
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
        self.assertEqual((row['Channel'], row['FromName'], row['Status']), ('assistant', 'Assistant', 'feed'))
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
        """The 'Assistant' report ships seeded like the Morning digest: hourly, on startup, its prompt the
        editable instruction. Deleting it (or switching it off) turns the post off - except for 'ask now'."""
        s = self._seed()
        src = assistant.source(s)
        self.assertEqual((src['Address'], src['cfg']['type'], src['cfg']['every_minutes'], src['Active']), ('Assistant', 'assistant', 30, 1))
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
        # a model that FAILS is not silence: the facts post in the hub's own words
        self.assertEqual(assistant.run(s, llm=mock.Mock(side_effect=RuntimeError('boom')), force=True)['said'], 1)


class ButtonTests(unittest.TestCase):
    def _posted(self):
        s = _store()
        mid = _mail(s, DANA, 'Q3 ledger', 'Here is the ledger.', days=6, conv='c1')
        _mine(s, 'Re: Q3 ledger', 'Could you send the reconciled version by Friday?', days=4, conv='c1')
        with mock.patch('taskuary.llm.build_llm', return_value=None):
            out = assistant.run(s, force=True)
        idea = s.list_ideas('open')[0]
        return s, mid, idea

    def test_follow_up_drafts_the_chase_into_review_and_closes_the_idea(self):
        s, mid, idea = self._posted()
        prompts = []
        def llm(system, user, **k):
            prompts.append((system, user)); return 'Hi Dana - any chance of the reconciled ledger this week? It unblocks the Q3 close.'
        out = assistant.act(s, idea['IdeaId'], 'followup', 'owner', llm=llm)
        rv = s.get_review(out['reviewId'])
        self.assertEqual((rv['Status'], rv['Kind'], rv['MessageId']), ('pending', 'draft', mid))
        self.assertIn('reconciled ledger', rv['DraftText'])
        self.assertIn('FOLLOW-UP', prompts[0][0])                          # the responder knew what kind of reply this is
        self.assertIn('WHY YOU ARE WRITING AGAIN', prompts[0][1])
        self.assertEqual(s.get_task(out['taskId'])['Kind'], 'reply')
        self.assertEqual(s.get_idea(idea['IdeaId'])['Status'], 'done')
        self.assertEqual(s.list_reviews('pending')[0]['ReviewId'], out['reviewId'])   # visible in the queue

    def test_make_it_a_task_opens_a_coding_task_and_dispatches_when_auto_is_on(self):
        s, mid, idea = self._posted()
        s.set_setting('coder_auto_enabled', '1', 't')
        with mock.patch('taskuary.ingest._spawn') as spawn:
            out = assistant.act(s, idea['IdeaId'], 'task')
        t = s.get_task(out['taskId'])
        self.assertEqual(t['Kind'], 'coding')
        self.assertEqual([getattr(c[0][0], '__name__', '') for c in spawn.call_args_list], ['_auto_code'])

    def test_dismiss_teaches_and_stays_dismissed_until_the_facts_change(self):
        s, mid, idea = self._posted()
        s.set_setting('learn_enabled', '1', 't')
        with mock.patch('taskuary.learn.learn_from') as learn:
            assistant.act(s, idea['IdeaId'], 'dismiss')
        self.assertIn('dismissed', learn.call_args[0][1])
        self.assertEqual(s.get_idea(idea['IdeaId'])['Status'], 'dismissed')
        with mock.patch('taskuary.llm.build_llm', return_value=None):
            self.assertEqual(assistant.run(s, force=True)['said'], 0)                # same silence: not said again
            _mine(s, 'Re: Q3 ledger', 'Dana - still need that file, could you send it?', days=2, conv='c1')
            self.assertEqual(assistant.run(s, force=True)['said'], 1)                # you wrote again: new facts, new line
        self.assertEqual(s.get_idea(idea['IdeaId'])['SaidCount'], 2)

    def test_snooze_sleeps_a_day_and_wakes(self):
        s, mid, idea = self._posted()
        out = assistant.act(s, idea['IdeaId'], 'snooze', days=1)
        self.assertEqual(s.get_idea(idea['IdeaId'])['Status'], 'snoozed')
        with mock.patch('taskuary.llm.build_llm', return_value=None):
            self.assertEqual(assistant.run(s, force=True)['said'], 0)
            s._exec('UPDATE idea SET SnoozeUntil=? WHERE IdeaId=?', (_ago(hours=1), idea['IdeaId']))
            self.assertEqual(assistant.run(s, force=True)['said'], 1)

    def test_a_note_with_no_message_behind_it_refuses_the_message_buttons(self):
        s = _store()
        row = s.upsert_idea({'key': 'idea:x', 'kind': 'idea', 'text': 'Book the sign-off.', 'action': {'type': 'note'}}, _ago())
        with self.assertRaises(ValueError): assistant.act(s, row['IdeaId'], 'followup')
        with self.assertRaises(ValueError): assistant.act(s, row['IdeaId'], 'task')
        with self.assertRaises(ValueError): assistant.act(s, row['IdeaId'], 'nonsense')


class ApiTests(unittest.TestCase):
    def test_the_endpoints_round_trip(self):
        from fastapi.testclient import TestClient
        from taskuary import server
        s = server.store
        s.set_setting('calendar_enabled', '0', 't'); s.set_setting('learn_enabled', '0', 't')
        _mail(s, DANA, 'API ledger', 'Here.', days=6, conv='api-c1')
        _mine(s, 'Re: API ledger', 'Could you send the reconciled version?', days=4, conv='api-c1')
        c = TestClient(server.app)
        sid = assistant.source(s)['SourceId']
        with mock.patch('taskuary.llm.build_llm', return_value=None):
            r = c.post(f'/api/sources/{sid}/run')                   # the Reports tab's "Run now" - the only manual trigger left
        self.assertEqual(r.status_code, 200); self.assertGreaterEqual(r.json()['said'], 1)
        mid = r.json()['message_id']
        self.assertEqual(c.get('/api/assistant/status').status_code, 404)   # the pinned card is gone (2026-08-30)
        ideas = c.get(f'/api/assistant/ideas?mid={mid}').json()['data']
        self.assertTrue(ideas and ideas[0]['status'] == 'open')
        self.assertEqual(len(s.list_ideas('open')), len(c.get('/api/assistant/ideas?status=open').json()['data']))
        r = c.post(f"/api/assistant/ideas/{ideas[0]['id']}/snooze", json={'days': 2})
        self.assertEqual(r.status_code, 200); self.assertEqual(r.json()['verb'], 'snooze')
        self.assertEqual(c.post(f"/api/assistant/ideas/{ideas[0]['id']}/nonsense").status_code, 422)


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
