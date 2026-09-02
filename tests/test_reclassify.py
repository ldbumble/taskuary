"""Correcting the road triage chose - and meaning it.

The Triage tab has always promised that correcting it teaches it, and offered nothing to click.
A correction is the highest-signal thing the funnel ever gets: the owner looking at one real
message and saying what should have happened. So it does both halves - the message goes down the
road for real, and the verdict is written where the next classification reads it.
"""
import json, unittest
from unittest import mock

from fastapi.testclient import TestClient

from taskuary import server

c = TestClient(server.app)
S = server.store


def _msg(subject='the vendor form is broken', frm='tova@corp.example', body='it writes empty files'):
    return S.add_message({'ExternalId': f'x{S.add_message.__hash__() ^ hash(subject)}', 'Channel': 'email',
                          'SourceName': 'me@corp.example', 'FromEmail': frm, 'FromName': 'Tova',
                          'Subject': subject, 'BodyText': body, 'Status': 'filed',
                          'SentAt': '2026-09-02 15:01:00'})


class RoadTests(unittest.TestCase):
    def test_an_unknown_road_is_refused(self):
        mid = _msg('unknown road')
        r = c.post(f'/api/messages/{mid}/reclassify', json={'road': 'sideways'})
        self.assertEqual(r.status_code, 422)
        self.assertIn('unknown road', r.json()['detail'])

    def test_a_missing_message_is_a_404(self):
        self.assertEqual(c.post('/api/messages/999999/reclassify', json={'road': 'fyi'}).status_code, 404)

    def test_making_it_the_owners_task_really_makes_the_task(self):
        mid = _msg('the vendor form needs a person')
        out = c.post(f'/api/messages/{mid}/reclassify', json={'road': 'task'}).json()
        self.assertTrue(out['changed'])
        tid = out['task']['taskId']
        t = S.get_task(tid)
        self.assertEqual(t['Kind'], 'task')                       # not an agent's, and nothing works it
        self.assertEqual(S.get_message(mid)['TaskId'], tid)

    def test_calling_it_fyi_drops_the_task_it_had(self):
        mid = _msg('actually this was nothing')
        tid = c.post(f'/api/messages/{mid}/reclassify', json={'road': 'task'}).json()['task']['taskId']
        out = c.post(f'/api/messages/{mid}/reclassify', json={'road': 'fyi'}).json()
        self.assertEqual((out['was'], out['road']), ('task', 'fyi'))
        self.assertIsNone(S.get_task(tid))                        # really dropped, not relabelled

    def test_reclassifying_to_what_it_already_is_changes_nothing(self):
        mid = _msg('already right')
        c.post(f'/api/messages/{mid}/reclassify', json={'road': 'task'})
        out = c.post(f'/api/messages/{mid}/reclassify', json={'road': 'task'}).json()
        self.assertFalse(out['changed'])
        self.assertIsNone(out.get('memory'))

    def test_coding_starts_the_agent_it_says_it_does(self):
        mid = _msg('the importer is broken')
        with mock.patch.object(server, 'start_session', return_value={'sid': 'abc'}) as start:
            out = c.post(f'/api/messages/{mid}/reclassify', json={'road': 'coding'}).json()
        start.assert_called_once()
        self.assertEqual(S.get_task(out['agent']['taskId'])['Kind'], 'coding')


class MemoryTests(unittest.TestCase):
    def test_the_verdict_is_written_where_the_next_one_reads_it(self):
        mid = _msg('honey cake recipe', frm='gabi@corp.example')
        before = len(S.list_memories())
        out = c.post(f'/api/messages/{mid}/reclassify', json={'road': 'reply'}).json()
        self.assertTrue(out['memory'])
        self.assertEqual(len(S.list_memories()), before + 1)
        note = next(m for m in S.list_memories() if m['MemoryId'] == out['memory'])['Note']
        self.assertIn('REPLY ONLY', note)
        self.assertIn('honey cake', note)

    def test_it_is_evidence_about_the_topic_not_a_rule_about_the_person(self):
        """A verdict keyed to the sender alone is how one message becomes a policy about someone."""
        mid = _msg('quarterly close checklist', frm='gabi@corp.example')
        out = c.post(f'/api/messages/{mid}/reclassify', json={'road': 'task'}).json()
        mem = next(m for m in S.list_memories() if m['MemoryId'] == out['memory'])
        self.assertEqual(mem['Scope'], 'subject')
        self.assertEqual(mem['Source'], 'verdict')

    def test_the_correction_shows_on_the_panel_as_the_new_road(self):
        """The pill reads the newest route row, so the correction has to be written there too."""
        mid = _msg('please just answer this one')
        c.post(f'/api/messages/{mid}/reclassify', json={'road': 'reply'})
        reason = (S.message_routes(mid) or [])[-1]['Reason']
        self.assertIn('triage: reply_only', reason)               # what FeedView roadOf looks for
        self.assertIn('you reclassified this', reason)

    def test_it_is_on_the_audit_trail(self):
        mid = _msg('for the record')
        c.post(f'/api/messages/{mid}/reclassify', json={'road': 'fyi'})
        recent = [a for a in S.list_audit('message', mid) if a['Action'] == 'reclassified']
        self.assertTrue(recent)
        self.assertEqual(json.loads(recent[0]['Detail'])['to'], 'fyi')


if __name__ == '__main__':
    unittest.main()
