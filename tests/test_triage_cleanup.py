"""Triage steps 3 and 4 (the owner, 2026-09-25): what was stuck or lost, the settings that did nothing, and the
small things - each pinned with the behaviour the owner chose."""
import json, unittest
from unittest import mock

from taskuary import assistant, ingest, policy, senders
from taskuary.store import MemoryStore


def verdict(intent, **more):
    def llm(system, user, **k):
        return json.dumps({'intent': intent, 'why': 'scripted', 'title': more.pop('title', 'Fix the export'), 'summary': 's',
                           **({'kind': 'task'} if intent == 'task' else {}), **more})
    return llm


def mail(s, ext, llm, conv='c1', frm='erin@northwind.example', body='Please fix the export.', channel='email', **extra):
    with mock.patch.object(ingest, '_spawn'):
        return ingest.ingest_message(s, {'external_id': ext, 'channel': channel, 'from_email': frm, 'from_name': 'Erin Blake',
                                         'conversation_id': conv, 'subject': 'Export', 'body': body,
                                         'sent_at': '2026-09-25 09:00:00', **extra}, llm=llm)


class StuckAndLostTests(unittest.TestCase):
    def test_a_line_still_waiting_for_triage_is_never_pulled_onto_a_task_unjudged(self):
        s = MemoryStore()
        waiting = s.add_message({'ExternalId': 'w', 'Channel': 'teams', 'ConversationId': 'room', 'FromEmail': 'erin@northwind.example',
                                 'BodyText': 'and the totals', 'SentAt': '2026-09-25 08:59:00', 'Status': 'triaging'})
        out = mail(s, 'a', verdict('task', related_message_ids=[waiting]), conv='room', channel='teams')
        m = s.get_message(waiting)
        self.assertEqual((m['Status'], m['TaskId']), ('triaging', None))
        self.assertTrue(out['task_id'])

    def test_an_idea_whose_triage_failed_is_retried_on_the_next_run(self):
        s = MemoryStore()
        s.upsert_idea({'key': 'idea:x', 'kind': 'idea', 'text': 'The export failed twice.', 'sig': 'a',
                       'action': {'triage': {'error': 'HTTP 500', 'sig': 'a'}}}, '2026-09-25 08:00:00')
        with mock.patch('taskuary.llm.build_llm', return_value=lambda *a, **k: '{"intent": "fyi", "why": "known"}'):
            self.assertEqual(assistant.retry_stuck_ideas(s), 1)
        t = json.loads(s.list_ideas()[0]['ActionJson'])['triage']
        self.assertEqual((t.get('intent'), t.get('error')), ('fyi', None))


class RulesTests(unittest.TestCase):
    def test_a_rule_can_only_skip_ignore_or_escalate(self):
        self.assertEqual(policy.PRECEDENCE, ('skip', 'ignore', 'escalate'))
        self.assertEqual(policy.evaluate({'from_email': 'x@y.example'}, [])['action'], 'none')
        draft_rule = {'Name': 'd', 'Kind': 'sender', 'Pattern': 'x@y.example', 'Action': 'draft', 'Reason': 'r', 'Active': 1}
        self.assertEqual(policy.evaluate({'from_email': 'x@y.example'}, [draft_rule])['action'], 'none')

    def test_escalate_marks_urgent_the_task_a_follow_up_lands_on(self):
        s = MemoryStore()
        first = mail(s, 'a', verdict('task'))
        s.save_policy({'Name': 'boss', 'Kind': 'sender', 'Pattern': 'erin@northwind.example', 'Action': 'escalate',
                       'Reason': 'always urgent', 'SortOrder': 1, 'Active': 1}, 'owner')
        mail(s, 'b', verdict('task'), body='Any update?')
        self.assertEqual(s.get_task(first['task_id'])['Priority'], 'urgent')

    def test_there_is_no_auto_draft_or_default_action_setting(self):
        from taskuary import settings_schema
        self.assertNotIn('auto_draft_enabled', settings_schema.knobs())
        self.assertNotIn('default_action', settings_schema.knobs())


class SmallThingsTests(unittest.TestCase):
    def test_the_owners_own_reply_is_outgoing(self):
        from taskuary import channels
        s = MemoryStore()
        channels.ingest_own_message(s, {'external_id': 'me1', 'channel': 'email', 'conversation_id': 'c9', 'subject': 'Re: x',
                                        'from_email': 'alex@northwind.example', 'body': 'Done.'}, 'your reply')
        self.assertEqual(s._one("SELECT Direction FROM message WHERE ExternalId='me1'")['Direction'], 'out')

    def test_a_question_on_a_coding_task_pings_and_carries_its_own_title(self):
        s = MemoryStore()
        first = mail(s, 'a', verdict('task', kind='coding'))
        with mock.patch.object(ingest, '_notify_new') as ping:
            mail(s, 'b', verdict('reply_only', title='Asks when the fix ships'), body='When will it ship?')
        self.assertTrue(ping.called)
        self.assertEqual(ping.call_args[0][4], 'a question for you')
        row = s._one("SELECT TriageTitle FROM message WHERE ExternalId='b'")
        self.assertEqual(row['TriageTitle'], 'Asks when the fix ships')
        self.assertTrue(first['task_id'])

    def test_taskuarys_own_report_is_named_for_what_it_is(self):
        self.assertEqual(senders.known(MemoryStore(), {'channel': 'report'}), (True, "Taskuary's own report"))

    def test_an_invite_is_still_an_invite_when_judged_later(self):
        s = MemoryStore()
        mid = s.add_message({'ExternalId': 'inv', 'Channel': 'email', 'Subject': 'Updated invitation: sync', 'FromEmail': 'erin@northwind.example',
                             'BodyText': 'moved to 3pm', 'Status': 'triaging', 'MailMetaJson': json.dumps({'invite': True})})
        self.assertTrue(ingest._from_row(s.get_message(mid), s).get('invite'))


if __name__ == '__main__':
    unittest.main()
