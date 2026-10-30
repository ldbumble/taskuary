"""The combine level (the owner, 2026-10-29): each connection type says how readily its messages join a task already there, 1 keep
separate .. 5 combine, and triage is handed it with the message. What a level means is the guide's; whether a message belongs is the
model's word, in the verdict fields it already answers (same_problem / continues / same_as) - so these script the verdict and pin
what the code does with it: the level reaches the prompt, a join lands as a To do part, goes to a live agent, and reopens a task
closed this week; an unrelated fyi stays fyi at 5."""
import json, unittest
from unittest import mock

from fastapi.testclient import TestClient

from taskuary import combine, general, ingest, senders, server, triage
from taskuary.ingest import ingest_message
from taskuary.store import MemoryStore

ROOM = 'whatsapp:120363-budget@g.us'
FIX = 'The rent line in the household budget app double counts March'


def brain(verdicts, seen):
    "Triage, scripted by the line's body; every payload it was handed is kept in `seen`."
    def llm(system, user, **k):
        u = json.loads(user); seen.append((system, u))
        return json.dumps({'intent': 'task', 'kind': 'general', 'why': 'scripted', 'title': u['body'][:40], 'summary': 's',
                           'asks_owner': True, 'relationship': 'new', **verdicts.get(u['body'], {})})
    return llm


def say(s, ext, body, at, llm, channel='whatsapp', conv=ROOM):
    with mock.patch.object(ingest, '_spawn') as spawn, mock.patch.object(senders, 'wrote_to', return_value=True), \
         mock.patch.object(senders, '_chat_known', return_value=(True, 'You talk with them.')), \
         mock.patch.object(general, 'provider_options', return_value=[{'pick': 'cli:claude', 'type': 'cli'}]):
        out = ingest_message(s, {'external_id': ext, 'channel': channel, 'subject': 'Budget app', 'body': body, 'from_name': 'Erin Blake',
                                 'from_email': 'erin@northwind.example' if channel == 'email' else None, 'to': ['alex@northwind.example'],
                                 'conversation_id': conv, 'sent_at': at, 'source_name': 'Budget app'}, llm=llm)
    return out, [getattr(c[0][0], '__name__', '') for c in spawn.call_args_list]


def store():
    s = MemoryStore(); s.set_setting('owner_email', 'alex@northwind.example', 't'); return s


class TheSetting(unittest.TestCase):
    def test_defaults_are_four_for_whatsapp_and_email_three_for_the_rest(self):
        s = store()
        self.assertEqual({k: combine.level(s, k) for k in ('whatsapp', 'email', 'outlook', 'gmail', 'imap', 'teams', 'slack', 'telegram')},
                         {'whatsapp': 4, 'email': 4, 'outlook': 4, 'gmail': 4, 'imap': 4, 'teams': 3, 'slack': 3, 'telegram': 3})

    def test_a_mailbox_card_and_the_email_channel_share_one_level(self):
        s = store(); combine.set_level(s, 'outlook', 2)
        self.assertEqual((combine.level(s, 'email'), combine.level(s, 'gmail')), (2, 2))

    def test_out_of_range_is_refused(self):
        s = store()
        for bad in (0, 6, 'x', None): self.assertRaises(ValueError, combine.set_level, s, 'teams', bad)
        self.assertEqual(combine.level(s, 'teams'), 3)

    def test_it_round_trips_through_the_api(self):
        s = store()
        with mock.patch.object(server, 'store', s):
            c = TestClient(server.app)
            self.assertEqual(c.get('/api/combine/whatsapp').json()['level'], 4)
            self.assertEqual(c.put('/api/combine/teams', json={'level': 5}).json(), {'ok': True, 'kind': 'teams', 'level': 5})
            self.assertEqual(c.get('/api/combine/teams').json()['level'], 5)
            self.assertEqual(c.put('/api/combine/teams', json={'level': 9}).status_code, 422)
            got = c.get('/api/combine').json()['data']
        self.assertEqual((got['teams'], got['whatsapp'], got['email']), (5, 4, 4))


class TheLevelReachesTriage(unittest.TestCase):
    def test_each_connection_type_hands_triage_its_own_level(self):
        s, seen = store(), []
        kinds = ['whatsapp', 'teams', 'slack', 'telegram', 'discord', 'email']
        for i, k in enumerate(kinds): combine.set_level(s, k, i % 5 + 1)
        for i, k in enumerate(kinds): say(s, f'm{i}', f'Line {i} about the budget app', '2026-10-28 09:00:00', brain({}, seen), channel=k, conv=f'{k}:c{i}')
        self.assertEqual([u.get('combine') for _, u in seen], [{'connection': k, 'level': i % 5 + 1} for i, k in enumerate(kinds)])

    def test_a_guide_that_never_names_it_is_told_what_the_levels_mean(self):
        s, seen = store(), []
        s.save_doc('triage', 'Decide task, reply_only or fyi.', 't')
        say(s, 'm1', FIX, '2026-10-28 09:00:00', brain({}, seen))
        self.assertIn(triage.FIELDS['combine'], seen[0][0])
        self.assertIn('How far to combine', triage.SHIPPED)


class AJoin(unittest.TestCase):
    """A second fix to the same budget app, the next day, in the same group: at a wide level triage says it belongs (same_problem true,
    the earlier task named) - the task it names is shown to it although no line of today's sits on it."""
    def setUp(self):
        self.s, self.seen = store(), []
        self.tid = say(self.s, 'w1', FIX, '2026-10-27 08:00:00', brain({}, self.seen))[0]['task_id']
        self.join = {'relationship': 'continues', 'same_problem': True, 'existing_task_id': self.tid,
                     'checklist': ['Fix the rates line rounding']}

    def line(self, body='Also the rates line rounds wrong'):
        return say(self.s, 'w2', body, '2026-10-28 10:00:00', brain({body: self.join}, self.seen))

    def test_the_rooms_older_task_is_shown_and_the_join_adds_a_to_do_part(self):
        out, _ = self.line()
        self.assertEqual((out['status'], out['task_id']), ('attached', self.tid))
        self.assertIn(self.tid, [t['tid'] for t in self.seen[-1][1]['room_tasks']])
        self.assertTrue(any(c['Body'].startswith('New from the latest message:') and 'Fix the rates line rounding' in c['Body']
                            for c in self.s.list_comments(self.tid)))

    def test_a_live_agent_is_handed_the_line(self):
        with mock.patch.object(ingest, 'live_agent', return_value='coding'), mock.patch.object(ingest, 'pass_in_why', return_value=''):
            out, spawned = self.line()
        self.assertEqual(out['task_id'], self.tid); self.assertIn('_pass_coding', spawned)

    def test_a_task_closed_this_week_reopens(self):
        self.s.update_task(self.tid, {'Status': 'done'}, 't')
        out, _ = self.line()
        self.assertEqual((out['task_id'], self.s.get_task(self.tid)['Status']), (self.tid, 'open'))

    def test_a_task_closed_longer_ago_is_not_shown(self):
        self.s.update_task(self.tid, {'Status': 'done'}, 't')
        self.s._exec("UPDATE task SET ClosedAt='2026-01-01 00:00:00' WHERE TaskId=?", (self.tid,))
        out, _ = self.line()
        self.assertNotIn(self.tid, [t['tid'] for t in self.seen[-1][1].get('room_tasks') or []])
        self.assertNotEqual(out['task_id'], self.tid)

    def test_an_unrelated_fyi_at_five_stays_fyi(self):
        combine.set_level(self.s, 'whatsapp', 5)
        body = 'Saw this article on garden birds, thought you would like it'
        out, _ = say(self.s, 'w3', body, '2026-10-28 11:00:00', brain({body: {'intent': 'fyi', 'relationship': 'new'}}, self.seen))
        self.assertEqual(self.seen[-1][1]['combine'], {'connection': 'whatsapp', 'level': 5})
        self.assertNotEqual(out.get('task_id'), self.tid)
        self.assertEqual(out['status'], 'filed')
        self.assertEqual(sum(1 for m in self.s.thread_messages(ROOM) if m['TaskId'] == self.tid), 1)


class TheLevelIsTheMeasure(unittest.TestCase):
    """A colleague's report that a chat bridge was down, then within minutes their screenshot of it and a request to test it - at level 4
    triage opened two more tasks, because the guide's older lines ("two problems are two jobs", a different screen is new) outweighed the
    level paragraph and `same_problem` read as its name. The guide now says those lines are level 1's, and the field's bar moves with it."""
    def test_the_chat_paragraph_hands_the_measure_to_the_level(self):
        g = triage.SHIPPED
        chat = g[g.index('**A chat line.**'):g.index('\n', g.index('**A chat line.**'))]
        self.assertIn('it is THE measure: at 1 a different error', chat)
        self.assertIn('at 4 and 5 a line about the same product or feature', chat)
        self.assertIn('Despite its name, `same_problem`', chat)
        self.assertLess(chat.index('at 1 a different'), chat.index('two problems are two jobs'))

    def test_the_level_paragraph_says_what_four_joins_and_that_unrelated_never_does(self):
        para = triage.FIELDS['combine']
        for n in range(1, 6): self.assertIn(f'- **{n}**', para)
        self.assertIn('a screenshot of it, a request to test it', para)
        self.assertIn('those lines describe level 1', para)
        self.assertIn('what has nothing to do with the task never joins it', para)

    def test_the_room_tasks_field_moves_same_problems_bar_with_the_level(self):
        self.assertIn("same_problem's bar moves with combine.level", triage.FIELDS['room_tasks'])
        self.assertIn('unrelated content never is', triage.FIELDS['room_tasks'])

    def test_a_group_line_carries_the_level_and_the_rooms_task(self):
        s, seen = store(), []
        combine.set_level(s, 'whatsapp', 4)
        tid = say(s, 'g1', 'The chat bridge is not bringing my messages in', '2026-10-28 09:00:00', brain({}, seen))[0]['task_id']
        say(s, 'g2', '(no text - see the attachment)', '2026-10-28 09:02:00', brain({}, seen))
        u = seen[-1][1]
        self.assertEqual(u['combine'], {'connection': 'whatsapp', 'level': 4})
        self.assertIn(tid, [t['tid'] for t in u['room_tasks']])
        self.assertIn(tid, [c['task_id'] for c in u['same_day_lines']])


class AJoinWidensTheTitle(unittest.TestCase):
    """A line that joins at the combine level never renames the task to its own part: when the title no longer covers what is on the
    task, triage answers `task_title`, the common subject, and the task takes that (the owner, 2026-10-29)."""
    def setUp(self):
        self.s, self.seen = store(), []
        self.tid = say(self.s, 'w1', FIX, '2026-10-27 08:00:00', brain({}, self.seen))[0]['task_id']
        self.first = self.s.get_task(self.tid)['Title']

    def join(self, **v):
        body = 'Also the rates line rounds wrong'
        verdict = {'relationship': 'continues', 'same_problem': True, 'existing_task_id': self.tid, 'title': 'Fix the rates line rounding', **v}
        return say(self.s, 'w2', body, '2026-10-28 10:00:00', brain({body: verdict}, self.seen))[0]

    def test_the_guide_and_the_schema_ask_for_it(self):
        self.assertIn('**task_title**', triage.SHIPPED); self.assertIn("never this line's own part", triage.TASK_TITLE)
        self.assertIn('task_title', triage.verdict_schema(candidates=[])['schema']['properties'])
        self.assertNotIn('task_title', triage.verdict_schema()['schema']['properties'])

    def test_a_join_with_a_wider_title_renames_the_task_to_it(self):
        out = self.join(task_title='Budget app line fixes')
        self.assertEqual(out['task_id'], self.tid)
        self.assertEqual(self.s.get_task(self.tid)['Title'], 'Budget app line fixes')
        self.assertTrue(any(c['Body'] == f'Now covers: Budget app line fixes (was: {self.first})' for c in self.s.list_comments(self.tid)))

    def test_a_join_without_one_keeps_the_title_never_the_lines_own(self):
        self.assertEqual(self.join()['task_id'], self.tid)
        self.assertEqual(self.s.get_task(self.tid)['Title'], self.first)

    def test_refines_still_says_the_ask_as_it_now_stands(self):
        self.join(refines=True, task_title='Budget app line fixes')
        self.assertEqual(self.s.get_task(self.tid)['Title'], 'Fix the rates line rounding')


if __name__ == '__main__':
    unittest.main()
