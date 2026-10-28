"""Separate asks are separate tasks, even in one chat or one thread (the owner, 2026-10-28: "of course emails/chats should be split
by triage if they are separate").

The shape that pinned it: in a group chat one colleague wrote all morning about unrelated things - onboarding, a report, a team
chat that would not load, the wording of a marketing email, a hardware idea. Triage read each line as continuing the first, so all
of them joined one task, and every line renamed it: the title drifted to whatever was said last and its to-do list mixed them all.
Now triage measures each line against the ask of the task it would join (room_tasks, same_problem): another subject opens its own
task, a follow-up on the same subject joins - and joining never renames a task unless its own ask was refined.
"""
import json, unittest
from unittest import mock

from taskuary import general, ingest, senders, triage
from taskuary.ingest import ingest_message
from taskuary.store import MemoryStore

ROOM = 'whatsapp:120363-ops@g.us'


def brain(script, seen=None):
    """Triage, scripted per line: `script` maps a line's body to its verdict. A line that names `joins` is said to continue the
    room's line with that body - the old mistake - and its `same` says whether it is that task's own ask."""
    def llm(system, user, **k):
        u = json.loads(user)
        if seen is not None: seen.append(u)
        v = dict(script[u['body']])
        lines = {c['text']: c for c in u.get('same_day_lines', [])}
        if (to := v.pop('joins', None)) is not None:
            c = lines[to]
            v.update(relationship='continues', related_message_ids=[c['id']], existing_task_id=c['task_id'], same_problem=v.pop('same'))
        return json.dumps({'intent': 'task', 'kind': 'general', 'why': 'scripted', 'summary': 's', 'asks_owner': True,
                           **({} if 'relationship' in v else {'relationship': 'new'}), **v})
    return llm


def say(s, ext, body, at, llm, who='Paula Vance'):
    with mock.patch.object(ingest, '_spawn') as spawn, mock.patch.object(senders, 'wrote_to', return_value=True), \
         mock.patch.object(senders, '_chat_known', return_value=(True, 'You talk with them one-to-one.')), \
         mock.patch.object(general, 'provider_options', return_value=[{'pick': 'cli:claude', 'type': 'cli'}]):
        out = ingest_message(s, {'external_id': ext, 'channel': 'whatsapp', 'subject': 'Ops team', 'body': body, 'from_name': who,
                                 'from_email': None, 'conversation_id': ROOM, 'sent_at': at, 'source_name': 'Ops team'}, llm=llm)
    return out, [getattr(c[0][0], '__name__', '') for c in spawn.call_args_list]


ONBOARD = 'Can you set up onboarding for the two new hires next week?'
SCRIPT = {
    ONBOARD: {'title': 'Set up onboarding for two new hires'},
    'Also on that - they both need laptops by Monday': {'joins': ONBOARD, 'same': True, 'title': 'Laptops for the new hires by Monday',
                                                        'checklist': ['Laptops ready by Monday']},
    'The weekly analytics report is missing last Friday': {'joins': ONBOARD, 'same': False, 'title': 'Weekly analytics report missing Friday'},
    'Our team chat is not showing up for Gail': {'joins': ONBOARD, 'same': False, 'title': "Team chat not showing for Gail"},
    'Can you reword the subject line of the Trainly marketing email?': {'relationship': 'new', 'title': 'Reword the Trainly email subject'},
}


class OneSenderManyAsks(unittest.TestCase):
    def setUp(self):
        self.s = MemoryStore(); self.s.set_setting('owner_email', 'alex@northwind.example', 't')
        self.seen = []
        self.first, _ = say(self.s, 'w1', ONBOARD, '2026-10-28 08:05:00', brain(SCRIPT, self.seen))
        self.tid = self.first['task_id']

    def line(self, ext, body, at):
        return say(self.s, ext, body, at, brain(SCRIPT, self.seen))

    def test_unrelated_asks_in_one_chat_are_separate_tasks_with_their_own_titles(self):
        outs = [self.line(f'w{i}', b, f'2026-10-28 09:{i:02d}:00')[0] for i, b in enumerate(list(SCRIPT)[2:], 2)]
        self.assertEqual([o['status'] for o in outs], ['created'] * 3)
        self.assertEqual(len({o['task_id'] for o in outs} | {self.tid}), 4)
        self.assertEqual([self.s.get_task(o['task_id'])['Title'] for o in outs],
                         ['Weekly analytics report missing Friday', 'Team chat not showing for Gail', 'Reword the Trainly email subject'])
        self.assertEqual(self.s.get_task(self.tid)['Title'], 'Set up onboarding for two new hires')
        reason = self.s.message_routes(outs[0]['message_id'])[-1]['Reason']
        self.assertIn(f'a separate ask from Paula Vance in Ops team - not the topic of {ingest.task_ref(self.tid)}', reason)
        # ...and the task each was measured against is told where it went, once - the line itself lives on its own task only
        notes = [c['Body'] for c in self.s.list_comments(self.tid) if 'was a different ask' in c['Body']]
        self.assertEqual(len(notes), 2)
        self.assertTrue(all('in this chat' in n for n in notes))
        self.assertEqual({m['TaskId'] for m in self.s.thread_messages(ROOM) if m['TaskId'] == self.tid}, {self.tid})
        self.assertEqual(sum(1 for m in self.s.thread_messages(ROOM) if m['TaskId'] == self.tid), 1)

    def test_a_related_follow_up_joins_and_keeps_the_title(self):
        out, _ = self.line('w2', 'Also on that - they both need laptops by Monday', '2026-10-28 08:20:00')
        self.assertEqual((out['status'], out['task_id']), ('attached', self.tid))
        t = self.s.get_task(self.tid)
        self.assertEqual(t['Title'], 'Set up onboarding for two new hires')
        self.assertFalse(any('Now about' in c['Body'] for c in self.s.list_comments(self.tid)))
        self.assertIn('Laptops ready by Monday', [i['text'] for i in self.s.task_checklist(self.tid)])

    def test_triage_is_shown_the_room_tasks_by_their_own_ask(self):
        self.line('w2', 'The weekly analytics report is missing last Friday', '2026-10-28 09:00:00')
        rt = self.seen[-1]['room_tasks']
        self.assertEqual([(t['tid'], t['title']) for t in rt], [(self.tid, 'Set up onboarding for two new hires')])
        self.assertIn('room_tasks', triage.SHIPPED); self.assertIn('**refines**', triage.SHIPPED)

    def test_an_answer_said_to_be_another_subject_is_new_too(self):
        v = triage.relationship_of({'relationship': 'answers', 'related_message_ids': [1], 'same_problem': False}, [{'id': 1, 'task_id': 9}])
        self.assertEqual(v['relationship'], 'new')
        v = triage.relationship_of({'relationship': 'answers', 'related_message_ids': [1], 'same_problem': True}, [{'id': 1, 'task_id': 9}])
        self.assertEqual(v['relationship'], 'answers')


class JoinDoesNotRetitle(unittest.TestCase):
    def test_a_refined_ask_retitles_and_a_plain_join_does_not(self):
        s = MemoryStore()
        tid = say(s, 'w1', ONBOARD, '2026-10-28 08:05:00', brain(SCRIPT))[0]['task_id']
        plain = {'more': {'joins': ONBOARD, 'same': True, 'title': 'Paula adds the start dates'}}
        say(s, 'w2', 'more', '2026-10-28 08:10:00', brain(plain))
        self.assertEqual(s.get_task(tid)['Title'], 'Set up onboarding for two new hires')
        refined = {'make it three': {'joins': ONBOARD, 'same': True, 'refines': True, 'title': 'Set up onboarding for three new hires'}}
        say(s, 'w3', 'make it three', '2026-10-28 08:15:00', brain(refined))
        self.assertEqual(s.get_task(tid)['Title'], 'Set up onboarding for three new hires')

    def test_the_schema_asks_refines_only_where_a_task_may_be_joined(self):
        self.assertNotIn('refines', triage.verdict_schema()['schema']['properties'])
        self.assertIn('refines', triage.verdict_schema(candidates=[])['schema']['properties'])
        self.assertIn('refines', triage.verdict_schema(thread_task=True)['schema']['properties'])


class EmailThreadReplies(unittest.TestCase):
    def mail(self, s, ext, body, verdict, at):
        llm = lambda *a, **k: json.dumps({'intent': 'task', 'kind': 'task', 'why': 'scripted', 'summary': 's', **verdict})
        with mock.patch.object(ingest, '_spawn'):
            return ingest_message(s, {'external_id': ext, 'channel': 'email', 'from_email': 'erin@northwind.example', 'from_name': 'Erin Blake',
                                      'conversation_id': 'AAQk-budget', 'subject': 'Re: Q4 budget', 'body': body, 'sent_at': at}, llm=llm)

    def test_a_normal_reply_on_the_same_subject_joins_and_keeps_the_title(self):
        s = MemoryStore()
        tid = self.mail(s, 'e1', 'Can you send the Q4 budget sheet?', {'title': 'Send Erin the Q4 budget sheet'}, '2026-10-28 08:00')['task_id']
        out = self.mail(s, 'e2', 'And please include the travel line.', {'title': 'Include the travel line in the Q4 budget', 'new_job': None},
                        '2026-10-28 09:00')
        self.assertEqual((out['status'], out['task_id']), ('attached', tid))
        self.assertEqual(s.get_task(tid)['Title'], 'Send Erin the Q4 budget sheet')

    def test_an_unrelated_question_on_the_thread_is_its_own_task(self):
        s = MemoryStore()
        tid = self.mail(s, 'e1', 'Can you send the Q4 budget sheet?', {'title': 'Send Erin the Q4 budget sheet'}, '2026-10-28 08:00')['task_id']
        out = self.mail(s, 'e2', 'Unrelated - who renews the PhishGuard licence?',
                        {'title': 'Who renews the PhishGuard licence', 'new_job': 'a licence question, not the budget'}, '2026-10-28 09:00')
        self.assertEqual(out['status'], 'created'); self.assertNotEqual(out['task_id'], tid)
        self.assertIn(f'a separate ask from Erin Blake on the thread of {ingest.task_ref(tid)}', s.message_routes(out['message_id'])[-1]['Reason'])
        self.assertEqual(s.get_task(tid)['Title'], 'Send Erin the Q4 budget sheet')


class CarryOnOnlyForTheSameTopic(unittest.TestCase):
    """196492ad: new work on a stopped assistant task carries its conversation on. A same-topic line still does; a separate ask that
    was split off is its own task and never turns the old conversation."""
    def setUp(self):
        self.s = MemoryStore(); self.s.set_setting('owner_email', 'alex@northwind.example', 't')
        out, spawned = say(self.s, 'w1', ONBOARD, '2026-10-28 08:05:00', brain(SCRIPT))
        self.assertEqual(spawned, ['_auto_general'])
        self.tid = out['task_id']
        self.s.add_comment(self.tid, 'owner', general.USER_TYPE, ONBOARD)
        self.s.add_comment(self.tid, 'assistant', general.ASSISTANT_TYPE, 'Drafted the onboarding plan.')

    def test_a_same_topic_line_carries_the_conversation_on(self):
        out, spawned = say(self.s, 'w2', 'Also on that - they both need laptops by Monday', '2026-10-28 08:30:00', brain(SCRIPT))
        self.assertEqual(out['task_id'], self.tid)
        self.assertIn('_continue_general', spawned)
        general.OPENING.discard(self.tid)

    def test_a_separate_ask_does_not(self):
        out, spawned = say(self.s, 'w2', 'The weekly analytics report is missing last Friday', '2026-10-28 09:00:00', brain(SCRIPT))
        self.assertNotEqual(out['task_id'], self.tid)
        self.assertNotIn('_continue_general', spawned)
        self.assertFalse(any('carries on its conversation' in c['Body'] for c in self.s.list_comments(self.tid)))


if __name__ == '__main__':
    unittest.main()
