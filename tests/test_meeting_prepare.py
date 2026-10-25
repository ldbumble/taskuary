"""Prepare on a meeting card (the owner, 2026-10-25: "add prepare that creates agent to research about person and topic through your
mails"): the meeting's task, opened with what the saved mail already says about its people and subject, and a general agent
started on it. It writes to nobody, and pressed twice it is the same task."""
import unittest
from unittest import mock
from fastapi.testclient import TestClient

from taskuary import concierge, server

c = TestClient(server.app)
EVENT = {'subject': 'Ledger cut-over plan', 'start': '2026-10-27T10:00:00', 'end': '2026-10-27T10:30:00', 'where': 'Teams',
         'organizer': 'Erin Blake', 'who': ['Erin Blake', 'Gail Moreno'], 'about': 'Who moves which entities first'}


class PrepareTests(unittest.TestCase):
    def setUp(self):
        server.store.add_message({'ExternalId': 'graph:prep-erin-1', 'Channel': 'email', 'Subject': 'Ledger cut-over: entity order',
                                  'FromName': 'Erin Blake', 'FromEmail': 'erin@northwind.example', 'SentAt': '2026-10-20 09:00:00',
                                  'BodyText': 'Can we move the two smaller entities first and the main one after close?'})
        self.started = []
        def fake(tid, body, background):
            self.started.append((tid, body.kind))
            return {'dispatch': 'assistant', 'started': len(self.started) == 1, 'existing': len(self.started) > 1, 'taskId': tid}
        p = mock.patch.object(server, '_dispatch_task_to_its_agent', side_effect=fake); p.start(); self.addCleanup(p.stop)

    def _press(self, **extra):
        r = c.post('/api/calendar/prepare', json={**EVENT, **extra})
        self.assertEqual(r.status_code, 200, r.text)
        return r.json()

    def test_it_starts_a_general_agent_on_a_brief_of_the_people_and_the_subject(self):
        d = self._press()
        self.assertEqual(self.started, [(d['taskId'], 'general')])
        t = server.store.get_task(d['taskId'])
        self.assertEqual(t['Kind'], 'general')
        self.assertTrue(t['Summary'].startswith('Prepare me for this meeting.'))
        self.assertIn('Erin Blake, Gail Moreno', t['Summary'])                      # the invite's people
        self.assertIn('Ledger cut-over: entity order', t['Summary'])                # ...and what the saved mail already says
        self.assertIn('Write to nobody', t['Summary'])

    def test_pressed_twice_it_is_the_same_task(self):
        a, b = self._press(start='2026-10-28T10:00:00'), self._press(start='2026-10-28T10:00:00')
        self.assertEqual(a['taskId'], b['taskId'])
        self.assertTrue(b['existing'])

    def test_the_owners_words_lead_the_research(self):
        d = self._press(start='2026-10-29T10:00:00', instruction='Mostly what Gail thinks of the order.')
        self.assertTrue(server.store.get_task(d['taskId'])['Summary'].startswith('Mostly what Gail thinks of the order.\n\nPrepare me'))

    def test_the_rows_press_runs_it_off_the_rail_item(self):
        item = {'key': 'meeting:2026-10-30T10:00:Ledger cut-over plan', 'kind': 'meeting',
                'event': {**EVENT, 'start': '2026-10-30T10:00:00', 'join': 'https://meet.northwind.example/x'}}
        with mock.patch('taskuary.funnel.next_item', return_value=item):
            out = server._run_kind({'kind': 'calendar.prepare', 'target': 0, 'params': {'key': item['key']}}, mock.Mock())
        self.assertEqual(self.started[-1], (out['taskId'], 'general'))
        self.assertIn('meet.northwind.example', server.store.get_task(out['taskId'])['Summary'])

    def test_the_rows_button_is_a_proposal_that_runs_at_its_press(self):
        item = {'key': 'meeting:2026-10-31T10:00:Ledger cut-over plan', 'kind': 'meeting', 'title': 'Ledger cut-over plan',
                'event': {**EVENT, 'start': '2026-10-31T10:00:00'}}
        with mock.patch('taskuary.funnel.next_item', return_value=item):
            prop = concierge.propose_direct(server.store, 'prepare', item['key'], table=True)
        self.assertTrue(prop.get('auto'), prop)
        self.assertEqual(server.store.get_operation(prop['id'])['Kind'], 'calendar.prepare')

    def test_a_press_runs_but_typed_words_only_light_it(self):
        self.assertIn('prepare', concierge.AUTO)
        self.assertIn('prepare', concierge.AGENT_STARTS)
        self.assertNotIn('prepare', concierge.AGENT_STARTS[:2])                  # the phone's hand-off box is for Send to agent alone


if __name__ == '__main__': unittest.main()
