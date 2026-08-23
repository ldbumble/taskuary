"""Switching a source ON must look BACK, not only forward.

The bug this pins down: the per-source watermark advances on every poll, including polls
that deliberately read nothing from that source (a repo whose issues are 'off', a cloud
object left on 'report'). So by the time the owner flips it on, LastPolledAt is already
'now' - and everything already sitting there is invisible forever. Observed for real: nine
GitHub issues stayed off the Timeline until a backfill reached behind the watermark.
"""
import json, unittest
from unittest import mock

from taskuary import channels
from taskuary.store import MemoryStore


def gh(s, cfg, active=1):
    cid = s.get_connector_by_type('github')['ConnectorId']
    s.save_connector({'ConnectorId': cid, 'Secret': 'ghp_x', 'Active': 1}, 't')
    return s.save_source({'Channel': 'github', 'Address': 'o/r', 'ConnectorId': cid,
                          'Active': active, 'ConfigJson': json.dumps(cfg)}, 't')


class WatermarkTests(unittest.TestCase):
    def test_an_off_repo_keeps_its_watermark(self):
        """The heart of it: polling past an 'off' repo must not move its clock."""
        s = MemoryStore(); sid = gh(s, {'issues': 'off', 'prs': 'off'})
        with mock.patch.object(channels, 'ingest_github_issues', return_value=0) as ing:
            channels.poll_channels(s)
        ing.assert_not_called()                                  # it was not read...
        self.assertIsNone(s.get_source(sid)['LastPolledAt'])      # ...so it was not stamped

    def test_a_live_repo_is_polled_and_stamped(self):
        s = MemoryStore(); sid = gh(s, {'issues': 'feed'})
        with mock.patch.object(channels, 'ingest_github_issues', return_value=2) as ing:
            channels.poll_channels(s)
        ing.assert_called_once()
        self.assertIsNotNone(s.get_source(sid)['LastPolledAt'])

    def test_gh_modes_precedence(self):
        # an explicit picker beats the role; unconfigured kinds follow it; PRs default off
        self.assertEqual(channels.gh_modes({'ConfigJson': '{"issues": "tasks"}'}, True), ('tasks', 'off'))
        self.assertEqual(channels.gh_modes({'ConfigJson': '{}'}, True), ('feed', 'off'))
        self.assertEqual(channels.gh_modes({'ConfigJson': '{}'}, False), ('tasks', 'off'))
        self.assertEqual(channels.gh_modes({'ConfigJson': 'not json'}, True), ('feed', 'off'))


class RewindTests(unittest.TestCase):
    """Turning something on rewinds it, so the next poll reaches back over what is there."""
    def test_off_to_feed_rewinds(self):
        from taskuary.server import _woke_up
        off = {'Active': 1, 'ConfigJson': '{"issues": "off", "prs": "off"}'}
        feed = {'Active': 1, 'ConfigJson': '{"issues": "feed", "prs": "off"}'}
        self.assertTrue(_woke_up(off, feed))
        self.assertFalse(_woke_up(feed, off))          # switching OFF never rewinds
        self.assertFalse(_woke_up(feed, feed))

    def test_cloud_object_report_to_feed_rewinds(self):
        from taskuary.server import _woke_up
        self.assertTrue(_woke_up({'Active': 1, 'ConfigJson': '{"mode": "report"}'},
                                 {'Active': 1, 'ConfigJson': '{"mode": "feed"}'}))
        self.assertFalse(_woke_up({'Active': 1, 'ConfigJson': '{"mode": "feed"}'},
                                  {'Active': 1, 'ConfigJson': '{"mode": "report"}'}))

    def test_activating_a_plain_source_rewinds(self):
        from taskuary.server import _woke_up
        self.assertTrue(_woke_up({'Active': 0, 'ConfigJson': None}, {'Active': 1, 'ConfigJson': None}))
        self.assertFalse(_woke_up({'Active': 1, 'ConfigJson': None}, {'Active': 0, 'ConfigJson': None}))

    def test_rewind_source_clears_the_stamp(self):
        s = MemoryStore(); sid = gh(s, {'issues': 'feed'})
        s.touch_source(sid)
        self.assertIsNotNone(s.get_source(sid)['LastPolledAt'])
        s.rewind_source(sid)
        self.assertIsNone(s.get_source(sid)['LastPolledAt'])

    def test_the_endpoint_rewinds_on_wake(self):
        """End to end through the API, the way the picker actually saves."""
        from fastapi.testclient import TestClient
        from taskuary import server
        c = TestClient(server.app)
        sid = gh(server.store, {'issues': 'off', 'prs': 'off'})
        server.store.touch_source(sid)
        c.post('/api/sources', json={'SourceId': sid, 'ConfigJson': '{"issues": "feed", "prs": "off"}'})
        self.assertIsNone(server.store.get_source(sid)['LastPolledAt'])


if __name__ == '__main__':
    unittest.main()
