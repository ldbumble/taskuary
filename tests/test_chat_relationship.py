"""Chat grouping is one verdict, same room, same calendar day (PW-031 to PW-035).

A chat room shares one conversation id, and a separate classifier (triage.same_ask) used to
decide whether a new line belonged to the task the room already had open - after the router had
already joined it on the room id alone. Now the single triage call also answers `relationship`
(new, continues, answers, uncertain) with `related_message_ids` and an optional
`existing_task_id`, chosen only among the lines of the SAME room on the SAME local calendar date
as the message's own timestamp - a prior day is new whatever it resembles, a task id cannot smuggle
an older ask back in, and `uncertain` never joins. Two facts still decide without a model: a line
typed seconds after the last, and an answer arriving while an agent is live on the task. Mail
threads and tracker items are untouched: their identity does not reset at midnight.
"""
import json, unittest
from unittest import mock

from taskuary import ingest, triage
from taskuary.ingest import ingest_message
from taskuary.store import MemoryStore

CONV = 'whatsapp:120363@g.us'
TODAY, YESTERDAY = '2026-09-06', '2026-09-05'


def line(s, body, at, llm, ext=None, name='Gabi', conv=CONV, channel='whatsapp'):
    return ingest_message(s, {'external_id': ext or f'{channel}:{conv}:{at}', 'channel': channel, 'subject': f'Chat with {name}',
                              'body': body, 'from_name': name, 'from_email': None, 'conversation_id': conv,
                              'sent_at': at, 'source_name': name}, llm=llm)


def verdict(intent='task', kind='general', relationship='new', related=(), task=None, seen=None):
    """The ONE brain call the funnel makes per chat line: intent, kind and relationship together."""
    def llm(system, user, **kw):
        if seen is not None: seen.append({'system': system, 'user': json.loads(user)})
        j = {'intent': intent, 'why': 'an ask', 'relationship': relationship, 'related_message_ids': list(related)}
        if kind and intent == 'task': j['kind'] = kind
        if task is not None: j['existing_task_id'] = task
        return json.dumps(j)
    return llm


class OneVerdictTests(unittest.TestCase):
    def setUp(self):
        self.s = MemoryStore()
        self.first = line(self.s, 'the agent isnt working on my dashboard', f'{TODAY} 09:00:00', verdict())
        self.assertEqual(self.first['status'], 'created')

    def test_the_verdict_sees_the_rooms_same_day_lines_and_nothing_else_is_asked(self):
        seen = []
        line(self.s, 'still broken by the way', f'{TODAY} 10:00:00', verdict(relationship='continues', related=[self.first['message_id']], seen=seen))
        self.assertEqual(len(seen), 1, 'one call decides intent, kind and relationship')
        cands = seen[0]['user']['same_day_lines']
        self.assertEqual([c['id'] for c in cands], [self.first['message_id']])
        self.assertIn('dashboard', cands[0]['text']); self.assertEqual(cands[0]['task_id'], self.first['task_id'])
        self.assertIn('relationship', seen[0]['system'])
        self.assertNotIn('is NEW part of the ask already open', seen[0]['system'])   # the separate classifier is gone

    def test_continues_joins_the_related_lines_task(self):
        out = line(self.s, 'still broken by the way', f'{TODAY} 10:00:00', verdict(relationship='continues', related=[self.first['message_id']]))
        self.assertEqual((out['status'], out['task_id']), ('attached', self.first['task_id']))
        self.assertIn('continues', self.s.message_routes(out['message_id'])[-1]['Reason'])

    def test_a_different_ask_in_the_same_room_gets_its_own_task(self):
        out = line(self.s, 'Also, copilot did this in my email. would be nice to have', f'{TODAY} 10:30:00', verdict(relationship='new'))
        self.assertEqual(out['status'], 'created'); self.assertNotEqual(out['task_id'], self.first['task_id'])
        self.assertEqual(len(self.s.list_tasks()), 2)

    def test_a_third_line_joins_the_ask_it_continues_not_the_rooms_first(self):
        second = line(self.s, 'Also, the badge printer is down', f'{TODAY} 10:30:00', verdict(relationship='new'))
        out = line(self.s, 'the printer on floor 2 I mean', f'{TODAY} 11:00:00', verdict(relationship='continues', related=[second['message_id']]))
        self.assertEqual((out['status'], out['task_id']), ('attached', second['task_id']))

    def test_uncertain_never_joins(self):
        out = line(self.s, 'hmm', f'{TODAY} 10:30:00', verdict(relationship='uncertain', related=[self.first['message_id']]))
        self.assertNotEqual(out['task_id'], self.first['task_id'])
        self.assertIn('uncertain', self.s.message_routes(out['message_id'])[-1]['Reason'])

    def test_answers_to_a_line_without_a_task_pulls_that_line_in(self):
        """Related lines need not belong to a task yet: the fyi that opened the subject joins the task the answer opens."""
        fyi = line(self.s, 'fyi the printer on floor 2 is down', f'{TODAY} 10:30:00', verdict(intent='fyi', kind=None))
        self.assertIsNone(fyi['task_id'])
        out = line(self.s, 'can you get someone to fix it today?', f'{TODAY} 10:35:00', verdict(relationship='continues', related=[fyi['message_id']]))
        self.assertEqual(out['status'], 'created')
        self.assertEqual(self.s.get_message(fyi['message_id'])['TaskId'], out['task_id'])

    def test_invalid_and_cross_room_ids_are_ignored(self):
        other = line(self.s, 'unrelated room ask', f'{TODAY} 09:30:00', verdict(), conv='whatsapp:999@g.us')
        out = line(self.s, 'and this?', f'{TODAY} 10:30:00', verdict(relationship='continues', related=[other['message_id'], 424242]))
        self.assertEqual(out['status'], 'created'); self.assertNotIn(out['task_id'], (self.first['task_id'], other['task_id']))
        out2 = line(self.s, 'or this?', f'{TODAY} 10:40:00', verdict(relationship='continues', task=other['task_id']))
        self.assertNotEqual(out2['task_id'], other['task_id'])                         # a task id cannot bypass the room


class SameDayTests(unittest.TestCase):
    def test_yesterdays_lines_are_not_candidates_and_cannot_be_joined(self):
        s = MemoryStore(); seen = []
        old = line(s, 'the agent isnt working on my dashboard', f'{YESTERDAY} 23:00:00', verdict())
        out = line(s, 'still broken', f'{TODAY} 09:00:00', verdict(relationship='continues', related=[old['message_id']], seen=seen))
        self.assertEqual(seen[0]['user'].get('same_day_lines', []), [])
        self.assertEqual(out['status'], 'created'); self.assertNotEqual(out['task_id'], old['task_id'])

    def test_midnight_is_the_boundary(self):
        s = MemoryStore()
        late = line(s, 'can you look at the export tonight?', f'{YESTERDAY} 23:59:00', verdict())
        out = line(s, 'it just failed again', f'{TODAY} 00:01:00', verdict(relationship='continues', related=[late['message_id']]))
        self.assertNotEqual(out['task_id'], late['task_id'])

    def test_a_delayed_sync_uses_the_message_date_not_the_processing_date(self):
        s = MemoryStore()
        first = line(s, 'can you look at the export?', f'{YESTERDAY} 14:00:00', verdict())
        out = line(s, 'it failed at 3pm too', f'{YESTERDAY} 15:00:00', verdict(relationship='continues', related=[first['message_id']]))
        self.assertEqual((out['status'], out['task_id']), ('attached', first['task_id']))

    def test_an_old_task_in_the_room_is_never_joined_on_the_room_id_alone(self):
        s = MemoryStore()
        old = line(s, 'the agent isnt working on my dashboard', '2026-08-20 09:00:00', verdict())
        s.set_setting('intent_classify_enabled', '0', 'owner')
        out = line(s, 'Also, a completely different thing', f'{TODAY} 09:00:00', None)
        self.assertNotEqual(out['task_id'], old['task_id'])


class FactsStillDecideTests(unittest.TestCase):
    def setUp(self):
        self.s = MemoryStore()
        self.first = line(self.s, 'the agent isnt working on my dashboard', f'{TODAY} 16:35:00', verdict())

    def test_a_line_typed_seconds_later_is_the_same_thought(self):
        seen = []
        out = line(self.s, 'i mean the new one', f'{TODAY} 16:35:40', verdict(relationship='new', seen=seen))
        self.assertEqual((out['status'], out['task_id']), ('attached', self.first['task_id'])); self.assertEqual(seen, [])

    def test_an_answer_to_a_live_agent_is_never_split_off(self):
        seen = []
        rid = self.s.start_run(self.first['task_id'], 'coder', 'have a look', 'owner'); self.s.update_run(rid, {'Status': 'running'})
        out = line(self.s, 'yes, the production one', f'{TODAY} 17:10:00', verdict(relationship='new', seen=seen))
        self.assertEqual((out['status'], out['task_id']), ('attached', self.first['task_id'])); self.assertEqual(seen, [])

    def test_without_a_brain_nothing_joins_but_the_facts(self):
        out = line(self.s, 'Also, a completely different thing', f'{TODAY} 17:20:00', None)
        self.assertNotEqual(out['task_id'], self.first['task_id'])


class MailAndTrackersAreNotResetAtMidnight(unittest.TestCase):
    def test_an_email_reply_the_next_day_still_joins_its_thread(self):
        s = MemoryStore()
        mail = lambda ext, body, at, subject: ingest_message(s, {'external_id': ext, 'channel': 'email', 'from_email': 'dana@vendor.example',
                                                                 'conversation_id': 'AAQk-thread-1', 'subject': subject, 'body': body, 'sent_at': at},
                                                             llm=lambda *a, **k: '{"intent": "task", "kind": "task", "why": "x"}')
        first = mail('m1', 'Can you look at the export?', f'{YESTERDAY} 14:00:00', 'Export')
        out = mail('m2', 'Any news on the export?', f'{TODAY} 09:00:00', 'Re: Export')
        self.assertEqual((out['status'], out['task_id']), ('attached', first['task_id']))

    def test_the_separate_chat_classifier_is_gone(self):
        self.assertFalse(hasattr(triage, 'same_ask')); self.assertFalse(hasattr(ingest, 'chat_continues'))


if __name__ == '__main__':
    unittest.main()
