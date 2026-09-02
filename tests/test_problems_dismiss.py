"""Dismissing what is failing: once, against the failure you actually read.

A bell that can be emptied by clicking is a bell nobody believes. So a dismissal is tied to the
error's own text and timestamp - the same connector failing the same way an hour later is news
again, and comes back.
"""
import json, unittest

from fastapi.testclient import TestClient

from taskuary import guard, problems, server
from taskuary.store import MemoryStore

c = TestClient(server.app)


def _failing(err='the bridge is down', when='2026-09-02 10:02:29'):
    s = MemoryStore()
    cid = s.get_connector_by_type('github')['ConnectorId']
    s.save_connector({'ConnectorId': cid, 'Active': 1}, 'o')
    s.touch_connector(cid, err)
    if when: s._exec('UPDATE connector SET LastSyncAt=? WHERE ConnectorId=?', (when, cid))
    return s, f'connector:{cid}'


class DismissTests(unittest.TestCase):
    def test_one_failure_can_be_put_down(self):
        s, key = _failing()
        self.assertEqual([p['key'] for p in problems.collect(s)], [key])
        out = problems.dismiss(s, key)
        self.assertEqual((out['ok'], out['remaining']), (True, 0))
        self.assertEqual(problems.collect(s), [])

    def test_it_comes_back_when_it_fails_again(self):
        """The whole point: dismissing is reading, not fixing."""
        s, key = _failing()
        problems.dismiss(s, key)
        self.assertEqual(problems.collect(s), [])
        cid = int(key.split(':')[1])
        s._exec('UPDATE connector SET LastSyncAt=? WHERE ConnectorId=?', ('2026-09-02 11:02:29', cid))
        self.assertEqual([p['key'] for p in problems.collect(s)], [key])   # same error, later: news again

    def test_a_different_error_on_the_same_card_is_not_dismissed(self):
        s, key = _failing()
        problems.dismiss(s, key)
        cid = int(key.split(':')[1])
        s.touch_connector(cid, 'the token expired')
        s._exec('UPDATE connector SET LastSyncAt=? WHERE ConnectorId=?', ('2026-09-02 10:02:29', cid))
        got = problems.collect(s)
        self.assertEqual([p['key'] for p in got], [key])
        self.assertIn('token expired', got[0]['detail'])

    def test_a_dismissal_for_something_that_cleared_is_forgotten(self):
        """Not housekeeping for its own sake: without it the list grows forever and a card that
        fails again months later is silently pre-dismissed."""
        s, key = _failing()
        problems.dismiss(s, key)
        cid = int(key.split(':')[1])
        s.touch_connector(cid, '')                       # polled clean
        self.assertEqual(problems.collect(s), [])
        s.touch_connector(cid, 'down again')
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


if __name__ == '__main__':
    unittest.main()
