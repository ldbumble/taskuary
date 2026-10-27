"""WHERE A TASK IS UP TO, once (stages.json, the owner 2026-10-26: "are these modes defined well anywhere besides the UI ... we should
define this well"): the rules' order, each stage's parts, and the server's reading of a task from its rows."""
import json, unittest
from pathlib import Path

from taskuary import buttons, stages, terminal
from taskuary.store import MemoryStore

WHEN = '2026-10-26 09:00:00'


def task(s, **kw):
    return s.create_task({'Title': 'Month-end close is short', 'Kind': kw.pop('Kind', 'task'), 'Status': kw.pop('Status', 'open'), **kw}, 'owner')


def mail(s, t, **kw):
    return s.add_message({'ConversationId': f'c{t}', 'Channel': 'email', 'Subject': 'Month-end', 'FromEmail': 'marcus@northwind.example',
                          'FromName': 'Marcus Reed', 'SentAt': WHEN, 'BodyText': 'Can you look before Thursday?', 'Status': 'routed', 'TaskId': t, **kw})


class TheStages(unittest.TestCase):
    def test_every_stage_names_its_parts_and_its_moves_are_buttons(self):
        for k, p in stages.STAGE.items():
            self.assertIn(p['main'], ('task', 'work'), k)
            self.assertTrue(p['shows'] and p['drawer'] and p['word'], k)
            self.assertIn(p['advisor'], (None, 'main', 'drawer'), k)
            if p['advisor']: self.assertEqual(p['advisor'], 'main' if p['main'] == 'work' else 'drawer', k)
            if p['lit']: self.assertEqual(p['main'], 'task', f'{k}: only the right drawer is lit')
            self.assertTrue(p['verbs'] and all(v in buttons.VERBS for v in p['verbs']), k)
        self.assertEqual(set(stages.KEYS), {'to_start', 'to_reply', 'todo', 'agent_working', 'agent_result', 'close_out', 'waiting', 'done'})

    def test_the_page_reads_the_same_file(self):
        js = (Path(stages.__file__).parents[1] / 'website' / 'src' / 'stages.js').read_text(encoding='utf-8')
        self.assertIn('../../taskuary/stages.json', js)

    def test_the_first_rule_that_holds_wins(self):
        self.assertEqual(stages.of({}), 'to_start')
        self.assertEqual(stages.of({'live': True, 'closed': True}), 'agent_working')
        self.assertEqual(stages.of({'waiting': True, 'drafted': True}), 'waiting')
        self.assertEqual(stages.of({'closed': True, 'drafted': True}), 'done')
        self.assertEqual(stages.of({'drafted': True, 'result': True}), 'close_out')
        self.assertEqual(stages.of({'result': True, 'owed': True}), 'agent_result')
        self.assertEqual(stages.of({'owed': True, 'list': True}), 'to_reply')
        self.assertEqual(stages.of({'list': True}), 'todo')
        self.assertEqual(stages.FACTS, ('live', 'waiting', 'closed', 'drafted', 'result', 'owed', 'list'))


class ATaskReadFromItsRows(unittest.TestCase):
    def test_a_mail_owed_a_reply_then_drafted_then_closed(self):
        s = MemoryStore(); t = task(s); m = mail(s, t)
        self.assertEqual(stages.of_task(s, s.get_task(t)), 'to_reply')
        s.add_review({'TaskId': t, 'MessageId': m, 'Kind': 'reply', 'DraftText': 'Thursday works.', 'Status': 'pending'})
        self.assertEqual(stages.of_task(s, s.get_task(t)), 'close_out', 'its pending review read from the store')
        s.update_task(t, {'Status': 'done'}, 'owner')
        self.assertEqual(stages.of_task(s, s.get_task(t)), 'done')

    def test_an_agents_task_is_started_not_replied_to(self):
        s = MemoryStore(); t = task(s, Kind='general'); mail(s, t)
        self.assertEqual(stages.of_task(s, s.get_task(t)), 'to_start', 'its agent answers in its Result')

    def test_a_to_do_with_a_list_and_a_task_waiting_on_a_person(self):
        s = MemoryStore(); t = task(s, DoneWhen='the close balances')
        self.assertEqual(stages.of_task(s, s.get_task(t)), 'todo')
        w = task(s, Status='waiting', Assignee='person:ray@northwind.example')
        self.assertEqual(stages.of_task(s, s.get_task(w)), 'waiting')

    def test_a_live_agent_and_one_that_stopped(self):
        s = MemoryStore(); t = task(s, Kind='coding')
        self.assertEqual(stages.of(stages.facts(s, s.get_task(t), 'working')), 'agent_working')
        self.assertEqual(stages.of(stages.facts(s, s.get_task(t), 'blocked')), 'agent_working')
        s.tag_task(t, terminal.SAVED, True, 'owner')
        self.assertEqual(stages.of_task(s, {**s.get_task(t), 'Assignee': 'agent:coding'}), 'agent_result')


def test_the_task_detail_says_the_stage_it_is_at(monkeypatch):
    from taskuary import server
    s = MemoryStore(); monkeypatch.setattr(server, 'store', s)
    t = task(s); mail(s, t)
    assert server.task_detail(t)['stage'] == 'to_reply'
    s.update_task(t, {'Status': 'done'}, 'owner')
    assert server.task_detail(t)['stage'] == 'done'


if __name__ == '__main__': unittest.main()
