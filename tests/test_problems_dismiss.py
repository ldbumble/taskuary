"""Dismissing what is failing: once, against the failure you actually read.

A bell that can be emptied by clicking is a bell nobody believes. So a dismissal is tied to the
error's own text and timestamp - the same connector failing the same way an hour later is news
again, and comes back.
"""
import json, unittest
from datetime import datetime, timedelta

from fastapi.testclient import TestClient

from taskuary import guard, problems, server
from taskuary.store import MemoryStore

c = TestClient(server.app)


def _ago(m): return (datetime.now() - timedelta(minutes=m)).strftime('%Y-%m-%d %H:%M:%S')


def _failing(err='the bridge is down', when=None):
    when = when or _ago(60)
    s = MemoryStore()
    cid = s.get_connector_by_type('github')['ConnectorId']
    s.save_connector({'ConnectorId': cid, 'Active': 1}, 'o')
    s.touch_connector(cid, err)
    if when: s._exec('UPDATE connector SET LastErrorAt=? WHERE ConnectorId=?', (when, cid))
    return s, f'connector:{cid}'


class DismissTests(unittest.TestCase):
    def test_one_failure_can_be_put_down(self):
        s, key = _failing()
        self.assertEqual([p['key'] for p in problems.collect(s)], [key])
        out = problems.dismiss(s, key)
        self.assertEqual((out['ok'], out['remaining']), (True, 0))
        self.assertEqual(problems.collect(s), [])

    def test_the_next_failing_poll_does_not_bring_it_back(self):
        """Per connection, not per poll (2026-10-26): every failing poll re-stamps LastErrorAt, and a dismissal signed
        with that stamp let a broken chat bridge back thirty seconds after it was put down."""
        s, key = _failing()
        problems.dismiss(s, key)
        cid = int(key.split(':')[1])
        s._exec('UPDATE connector SET LastErrorAt=? WHERE ConnectorId=?', (_ago(0), cid))
        self.assertEqual(problems.collect(s), [])
        s.touch_connector(cid, 'the token expired')                       # worded differently, still the same outage
        self.assertEqual(problems.collect(s), [])

    def test_it_comes_back_when_it_fails_again_after_working(self):
        """The whole point: dismissing is reading, not fixing."""
        s, key = _failing()
        problems.dismiss(s, key)
        cid = int(key.split(':')[1])
        s.touch_connector(cid)                                            # it worked
        problems.collect(s)
        s.touch_connector(cid, 'the bridge is down')
        s._exec('UPDATE connector SET LastErrorAt=? WHERE ConnectorId=?', (_ago(30), cid))
        self.assertEqual([p['key'] for p in problems.collect(s)], [key])

    def test_a_dismissal_for_something_that_cleared_is_forgotten(self):
        """Not housekeeping for its own sake: without it the list grows forever and a card that
        fails again months later is silently pre-dismissed."""
        s, key = _failing()
        problems.dismiss(s, key)
        cid = int(key.split(':')[1])
        s.touch_connector(cid, '')                       # polled clean
        self.assertEqual(problems.collect(s), [])
        s.touch_connector(cid, 'down again')
        s._exec('UPDATE connector SET LastErrorAt=? WHERE ConnectorId=?', (_ago(30), cid))
        self.assertEqual([p['key'] for p in problems.collect(s)], [key])
        problems.dismiss(s, key)                          # rewrites the record, dropping the stale one
        self.assertEqual(list(json.loads(s.get_settings()[problems.DISMISSED])), [key])

    def test_dismissing_nothing_says_so(self):
        s, _key = _failing()
        with self.assertRaisesRegex(ValueError, 'nothing failing'):
            problems.dismiss(s, 'connector:9999')

    def test_the_door_and_who_may_use_it(self):
        r = c.post('/api/problems/connector%3A9999/dismiss')
        self.assertEqual(r.status_code, 404)              # nothing failing under that key
        # an agent does not get to clear the owner's bell
        self.assertTrue(guard.denied('POST', '/api/problems/connector:1/dismiss'))
        self.assertFalse(guard.denied('GET', '/api/problems'))


class AssistantDismissTests(unittest.TestCase):
    """THE BELL'S DISMISS, SAID IN THE CHAT (the owner, 2026-11-02: "clear the error on the bell"): problems.dismiss does what the
    bell's own Dismiss / Got it does, with the bell open or shut - kept and said, never a card to press."""
    def test_the_tool_is_offered_and_runs_at_once(self):
        from taskuary import operations, toolcatalog
        self.assertIn('problems.dismiss', operations.KINDS)
        self.assertIn('problems.dismiss', {k for _, _, ks in toolcatalog.BUCKETS for k in ks})
        self.assertIn('runs at once, said', toolcatalog.describe('problems.dismiss'))
        self.assertEqual(toolcatalog.valid('problems.dismiss', {}), '')

    def test_the_only_problem_is_put_down_and_comes_back_if_it_fails_again(self):
        from taskuary import concierge
        s, key = _failing('the bridge is down')
        out = concierge.call_turn(s, 0, {'kind': 'problems.dismiss', 'params': {}}, None, 'clear the error on the bell')
        self.assertEqual(out['did'], 'problems.dismiss')
        self.assertTrue(out['say'].startswith('Put down “') and 'comes back if it fails again' in out['say'], out['say'])
        self.assertEqual(problems.collect(s), [])
        self.assertIn(key, json.loads(s.get_settings()[problems.DISMISSED]))                # the bell's own record, as its button writes

    def test_several_on_the_bell_name_one_or_all_and_a_miss_changes_nothing(self):
        from taskuary import concierge
        s, gh = _failing('the token expired')
        cid = s.get_connector_by_type('outlook')['ConnectorId']
        s.save_connector({'ConnectorId': cid, 'Active': 1, 'Name': 'Work mail'}, 'o')
        s.touch_connector(cid, 'the mailbox did not answer'); s._exec('UPDATE connector SET LastErrorAt=? WHERE ConnectorId=?', (_ago(60), cid))
        self.assertEqual(len(problems.collect(s)), 2)
        with self.assertRaisesRegex(concierge.CallMiss, 'several.*Nothing was changed'):
            concierge.call_turn(s, 0, {'kind': 'problems.dismiss', 'params': {}}, None, 'clear the bell')
        with self.assertRaisesRegex(concierge.CallMiss, 'Nothing on the bell matches'):
            concierge.call_turn(s, 0, {'kind': 'problems.dismiss', 'params': {'which': 'payroll'}}, None, 'x')
        self.assertEqual(len(problems.collect(s)), 2)
        concierge.call_turn(s, 0, {'kind': 'problems.dismiss', 'params': {'which': 'work mail'}}, None, 'dismiss the work mail one')
        self.assertEqual([p['key'] for p in problems.collect(s)], [gh])
        concierge.call_turn(s, 0, {'kind': 'problems.dismiss', 'params': {'which': 'all'}}, None, 'clear them all')
        self.assertEqual(problems.collect(s), [])
        with self.assertRaisesRegex(concierge.CallMiss, 'Nothing is on the bell'):
            concierge.call_turn(s, 0, {'kind': 'problems.dismiss', 'params': {}}, None, 'clear the bell')


if __name__ == '__main__':
    unittest.main()
