"""Archive on an FYI filed the mail (filed -> ignored) and left it UNREAD on the walk: the press audit (2026-10-01) found
the row still under FYI after it. Archive means "I am done with this" - it must leave the item at least as settled as
pressing Next, whose floor is the read receipt (no-worse-than-next)."""
import unittest
from unittest import mock

from fastapi.testclient import TestClient

from taskuary import funnel, processing_unread, server
from test_funnel import ago, mail, store


def rail(s):
    s.reconcile_processing_membership(fixed_now=ago(0)); funnel.invalidate()
    with mock.patch('taskuary.terminal.live_sessions', return_value=[]):
        return processing_unread.build(s, live_state=[])['items']


class ArchiveIsReadTests(unittest.TestCase):
    def fyi(self):
        s = store()
        mid = mail(s, 'Platform digest', who='Payworth', email='digest@vendor.example', body='Your weekly digest.', status='filed')
        rail(s); s.activate_processing_reads(fixed_now=ago(0), live_state=[])
        on = [i for i in rail(s) if i.get('mid') == mid]
        self.assertTrue(on and on[0]['unread'], 'the fyi is unread on the walk to begin with')
        return s, mid

    def test_archive_takes_the_fyi_off_the_walk(self):
        s, mid = self.fyi()
        with mock.patch.object(server, 'store', s):
            r = TestClient(server.app).post(f'/api/messages/{mid}/file', json={'learn': False, 'archive': True})
        self.assertEqual(r.status_code, 200, r.text)
        self.assertEqual(s.get_message(mid)['Status'], 'ignored')
        self.assertFalse([i for i in rail(s) if i.get('mid') == mid and (i['unread'] or i['actionable'])], 'still unread after Archive')

    def test_the_assistants_archive_is_the_same_door(self):
        s, mid = self.fyi()
        with mock.patch.object(server, 'store', s):
            server._run_operation({'kind': 'message.archive', 'target': mid, 'params': {}}, None)
        self.assertFalse([i for i in rail(s) if i.get('mid') == mid and (i['unread'] or i['actionable'])])
