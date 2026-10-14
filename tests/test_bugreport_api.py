"""The two owner-only routes behind "Report this bug": a scrubbed draft, and the one page they may open."""
import json, time, unittest
from unittest import mock

from fastapi.testclient import TestClient

from taskuary import bugreport, guard, server
from taskuary.store import MemoryStore

c = TestClient(server.app)
AGENT = {'X-Taskuary-Token': server.cfg['server']['agent_token']}
STRANGER = {'X-Taskuary-Token': guard.stranger_token(server.cfg['server'], 7)}
GH = 'https://github.com/ldbumble/taskuary/issues/new'
CLIENT = {'screen': 'Today', 'route': '/tasks/12', 'error': 'Boom: no mail from ray@vendor.example', 'stack': '', 'actions': ['open'], 'at': ''}


def _post(path, body, h=None, **kw): return c.post(path, json=body, headers=h or {}, **kw)


class DraftTests(unittest.TestCase):
    def setUp(self):
        self.p = mock.patch.object(server, 'store', MemoryStore()); self.p.start(); self.addCleanup(self.p.stop)

    def test_the_draft_comes_back_scrubbed(self):
        with mock.patch.object(bugreport, '_ask', return_value={}):
            r = _post('/api/bug-report/draft', CLIENT)
        self.assertEqual(r.status_code, 200)
        self.assertNotIn('ray@vendor.example', json.dumps(r.json()))
        self.assertIn('[removed]', r.json()['error'])

    def test_any_failure_while_drafting_is_the_unsafe_sentence(self):
        with mock.patch.object(bugreport, 'collect', side_effect=RuntimeError('x')):
            r = _post('/api/bug-report/draft', CLIENT)
        self.assertEqual((r.status_code, r.json()['detail']), (422, bugreport.SAFE_MSG))

    def test_unsafe_is_422(self):
        with mock.patch.object(bugreport, 'draft', side_effect=bugreport.Unsafe(bugreport.SAFE_MSG)):
            r = _post('/api/bug-report/draft', CLIENT)
        self.assertEqual((r.status_code, r.json()['detail']), (422, bugreport.SAFE_MSG))

    def test_a_huge_body_is_refused(self):
        r = c.post('/api/bug-report/draft', content=json.dumps({'stack': 'x' * 250_000}), headers={'content-type': 'application/json'})
        self.assertEqual(r.status_code, 413)

    def test_oversize_never_reaches_the_scrub(self):
        big, hd = json.dumps({'stack': 'x' * 250_000}), {'content-type': 'application/json'}
        with mock.patch.object(bugreport, 'draft') as d:
            self.assertEqual(c.post('/api/bug-report/draft', content=big, headers=hd).status_code, 413)
            self.assertEqual(c.post('/api/bug-report/draft', content=iter([big[:150_000].encode(), big[150_000:].encode()]), headers=hd).status_code, 413)
        d.assert_not_called()

    def test_malformed_json_is_a_400_not_the_privacy_sentence(self):
        r = c.post('/api/bug-report/draft', content='{nope', headers={'content-type': 'application/json'})
        self.assertEqual(r.status_code, 400); self.assertNotEqual(r.json()['detail'], bugreport.SAFE_MSG)

    def test_a_draft_does_not_stall_the_server(self):
        import threading
        with mock.patch.object(bugreport, '_ask', side_effect=lambda *a: time.sleep(1) or {}):
            t = threading.Thread(target=_post, args=('/api/bug-report/draft', CLIENT)); t.start(); time.sleep(.3)
            t0 = time.time(); c.get('/api/health'); dt = time.time() - t0; t.join()
        self.assertLess(dt, .3)

    def test_no_session_reaches_it(self):
        for h in (AGENT, STRANGER): self.assertEqual(_post('/api/bug-report/draft', CLIENT, h).status_code, 403)


class OpenUrlTests(unittest.TestCase):
    def test_the_new_issue_page_opens(self):
        with mock.patch('webbrowser.open') as o:
            r = _post('/api/open-url', {'url': GH + '?title=a%20b&body=x&labels=bug'})
            for _ in range(100):
                if o.called: break
                time.sleep(.02)
        self.assertEqual((r.status_code, r.json()), (200, {'opened': True}))
        o.assert_called_once_with(GH + '?title=a%20b&body=x&labels=bug')

    def test_the_validated_form_is_what_opens(self):
        with mock.patch('webbrowser.open') as o:
            _post('/api/open-url', {'url': GH + '?a=1#f'}); time.sleep(.2)
        o.assert_called_once_with(GH + '?a=1#f')

    def test_nothing_else_opens(self):
        bad = ['https://example.com/', 'javascript:alert(1)', GH + '@evil.example', GH + '/../../x', GH + 'x', 'http://github.com/ldbumble/taskuary/issues/new',
               'https://github.com.evil.example/ldbumble/taskuary/issues/new', 'https://user@github.com/ldbumble/taskuary/issues/new',
               'https://github.com/ldbumble/taskuary/issues/new/../../../x', 'https://github.com:444/ldbumble/taskuary/issues/new', '', 'file:///c:/x']
        for u in bad:
            with self.subTest(u=u), mock.patch('webbrowser.open') as o:
                self.assertEqual(_post('/api/open-url', {'url': u}).status_code, 400); o.assert_not_called()

    def test_no_session_reaches_it(self):
        with mock.patch('webbrowser.open') as o:
            for h in (AGENT, STRANGER): self.assertEqual(_post('/api/open-url', {'url': GH}, h).status_code, 403)
        o.assert_not_called()
