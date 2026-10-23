"""Wake a waiting task on their reply (waiton.py, the owner's pick 2026-10-22).

An agent needs something only a third party knows: it asks them, says `taskuary --waiting-on "<who>"`, and the task reads
`waiting on them`. That person's reply wakes it - back on the owner's rail as news, Continue leading where the agent left a
session - and nothing starts by itself. Anybody else writing on the thread leaves the wait as it was.
"""
import json, unittest
from unittest import mock

from taskuary import concierge, funnel, ingest, lanes, processing_unread, terminal, waiton
from taskuary.testing import Factory
from test_funnel import ago, mail, store

ERIN, GAIL, PAULA = 'erin@northwind.example', 'gail.moreno@northwind.example', 'paula@vendor.example'


def fyi(*a, **k): return json.dumps({'intent': 'fyi', 'kind': 'general', 'why': 'a short answer, nothing to do'})


def arrive(s, ext, sender, name, body, llm=fyi):
    with mock.patch.object(ingest, '_spawn'), mock.patch.object(terminal, 'start_on_task') as start, \
         mock.patch.object(terminal, 'say_to_task', return_value=True) as say:
        out = ingest.ingest_message(s, {'external_id': ext, 'channel': 'email', 'subject': 'RE: PTO import', 'body': body,
                                        'from_email': sender, 'from_name': name, 'conversation_id': 'c1',
                                        'sent_at': '2026-08-23 11:00:00'}, llm=llm)
    return out, start, say


class DeclareTests(unittest.TestCase):
    def setUp(self):
        self.s = store()
        self.tid = Factory(self.s).attachable(from_email=ERIN).tid
        self.s.add_message({'TaskId': self.tid, 'ExternalId': 'cc1', 'Channel': 'email', 'ConversationId': 'c1', 'Subject': 'RE: PTO import',
                            'FromName': 'Moreno, Gail', 'FromEmail': GAIL, 'BodyText': 'Looping in.', 'Status': 'routed'})

    def test_a_name_on_the_thread_is_recorded_as_their_address(self):
        out = waiton.declare(self.s, self.tid, 'Gail Moreno', 'coding')
        t = self.s.get_task(self.tid)
        self.assertEqual((out['ok'], t['WaitingOn'], t['Status']), (True, GAIL, 'waiting'))

    def test_a_name_nobody_on_it_has_is_kept_as_the_name(self):
        waiton.declare(self.s, self.tid, 'Omar Keller')
        self.assertEqual(self.s.get_task(self.tid)['WaitingOn'], 'omar keller')

    def test_never_on_the_owner_nor_a_closed_task(self):
        self.s.set_setting('owner_email', 'alex@northwind.example', 't')
        self.assertFalse(waiton.declare(self.s, self.tid, 'alex@northwind.example')['ok'])
        self.s.update_task(self.tid, {'Status': 'done'}, 't')
        self.assertFalse(waiton.declare(self.s, self.tid, GAIL)['ok'])

    def test_closing_the_task_ends_the_wait(self):
        waiton.declare(self.s, self.tid, GAIL)
        self.s.update_task(self.tid, {'Status': 'done'}, 't')
        self.assertFalse(self.s.get_task(self.tid)['WaitingOn'])


class WakeTests(unittest.TestCase):
    """The answer arriving through ingest - judged fyi ("Thursday works" reads as nothing to do), which used to file it."""
    def setUp(self):
        self.s = store()
        self.tid = Factory(self.s).attachable(from_email=ERIN).tid
        waiton.declare(self.s, self.tid, PAULA, 'coding')

    def test_a_reply_from_the_person_it_waits_on_wakes_it(self):
        out, _, _ = arrive(self.s, 'w1', PAULA, 'Paula Vance', 'The file is the 8/17 one.')
        t = self.s.get_task(self.tid)
        self.assertEqual((out['status'], out['task_id']), ('attached', self.tid))       # routed onto the task, never filed away
        self.assertEqual((t['WaitingOn'], t['Status'], str(t['WokeMid'])), (None, 'open', str(out['message_id'])))

    def test_a_reply_from_someone_else_leaves_the_wait(self):
        out, _, _ = arrive(self.s, 'w2', GAIL, 'Gail Moreno', 'Thanks all.')
        t = self.s.get_task(self.tid)
        self.assertEqual(out['status'], 'filed')
        self.assertEqual((t['WaitingOn'], t['Status'], t['WokeMid']), (PAULA, 'waiting', None))

    def test_nothing_starts_by_itself(self):
        # the default answer_to_agent is 'ask': no session is started, and none is typed into
        _, start, say = arrive(self.s, 'w3', PAULA, 'Paula Vance', 'The file is the 8/17 one.')
        start.assert_not_called(); say.assert_not_called()

    def test_the_owners_auto_setting_hands_it_to_a_live_session(self):
        # answer_to_agent=auto is the owner's own switch: their answer is typed into the session already running - still no start
        self.s.set_setting('answer_to_agent', 'auto', 't')
        with mock.patch.object(terminal, 'mode_of_task', return_value='auto'):
            _, start, say = arrive(self.s, 'w4', PAULA, 'Paula Vance', 'The file is the 8/17 one.')
        self.assertEqual(say.call_args[0][1], self.tid); start.assert_not_called()


class RailTests(unittest.TestCase):
    def rail(self):
        self.s.reconcile_processing_membership(fixed_now=ago(0)); funnel.invalidate()
        with mock.patch('taskuary.terminal.live_sessions', return_value=[]):
            return [c for c in processing_unread.build(self.s, live_state=[])['items'] if c.get('tid') == self.tid]

    def setUp(self):
        self.s = store()
        self.tid = self.s.create_task({'Title': 'PTO import', 'Kind': 'coding', 'Status': 'in_progress'}, 'o')
        mail(self.s, 'PTO import', who='Erin Blake', email=ERIN, hours=5, tid=self.tid, conv='c1')
        self.s.add_transcript(self.tid, 'sid1', 'asked Paula for the file', agent='coding', cwd='.', ext_id='abc')
        self.s._exec('UPDATE transcript SET CreatedAt=? WHERE TaskId=?', (ago(3), self.tid))     # the session ended three hours ago
        waiton.declare(self.s, self.tid, PAULA, 'coding')

    def test_waiting_reads_theirs_and_offers_no_continue(self):
        card = self.rail()[0]
        self.assertEqual((card['lane'], card['waiting_on']), ('theirs', PAULA)); self.assertFalse(lanes.on_you(card))
        self.assertNotIn('continue', [c['verb'] for c in concierge.chips_for(self.s, card)])

    def test_their_reply_is_news_with_continue_leading(self):
        mid = mail(self.s, 'RE: PTO import', who='Paula Vance', email=PAULA, hours=1, tid=self.tid, conv='c1', body='It is the 8/17 file.')
        waiton.arrived(self.s, self.tid, self.s.get_message(mid), mid)
        card = self.rail()[0]
        self.assertTrue(card.get('woke')); self.assertTrue(lanes.on_you(card), card['lane'])      # back on you, as news
        self.assertEqual(concierge.chips_for(self.s, card)[0]['verb'], 'continue')

    def test_the_advisor_reads_the_wake_afresh(self):
        from taskuary import advisor
        was = advisor.revision(self.s, 'task', self.tid)
        mid = mail(self.s, 'RE: PTO import', who='Paula Vance', email=PAULA, hours=1, tid=self.tid, conv='c1', body='It is the 8/17 file.')
        with mock.patch.object(advisor, 'notice') as notice: waiton.arrived(self.s, self.tid, self.s.get_message(mid), mid)
        self.assertNotEqual(advisor.revision(self.s, 'task', self.tid), was)
        self.assertEqual(notice.call_args[0][1:], ('reply.arrived', 'task', self.tid))

    def test_someone_elses_line_is_news_but_no_wake(self):
        mail(self.s, 'RE: PTO import', who='Gail Moreno', email=GAIL, hours=1, tid=self.tid, conv='c1', body='Any news?')
        card = self.rail()[0]
        self.assertFalse(card.get('woke'))
        self.assertEqual(self.s.get_task(self.tid)['WaitingOn'], PAULA)


class CliTests(unittest.TestCase):
    def test_a_strangers_session_may_say_it_waits(self):
        from taskuary import cli, floor, guard
        self.assertIn('waiting_on', cli.STRANGER_ACTS)
        self.assertIn('--waiting-on', floor.TASKUARY_OK)
        self.assertTrue(any(p.fullmatch('/api/agent/waiting') for p in guard._STRANGER_WRITES))

    def test_the_seed_names_it(self):
        from taskuary import selfclose
        self.assertIn('--waiting-on', selfclose.SEED_LINE)


def test_the_cli_posts_the_wait_and_then_the_reply(monkeypatch, capsys):
    # `--reply "..." --waiting-on Paula` both asks and waits: the wait is recorded first, the reply branch ends the command
    from taskuary import cli
    calls = []
    def post(path, body, stranger, **k): calls.append((path, body)); return mock.Mock(text=''), {'ok': True}
    monkeypatch.setenv('TASKUARY_TASK', '7'); monkeypatch.setattr(cli, '_post', post); monkeypatch.setattr(cli, 'session', lambda: (True, None))
    monkeypatch.setattr('sys.argv', ['taskuary', '--waiting-on', 'Paula Vance', '--reply', 'Paula, which file is it?'])
    cli.main()
    assert [(p, b.get('who')) for p, b in calls] == [('/api/agent/waiting', 'Paula Vance'), ('/api/agent/reply', None)]
    assert calls[0][1]['task_id'] == 7
    assert 'waits on Paula Vance' in capsys.readouterr().out


if __name__ == '__main__':
    unittest.main()
