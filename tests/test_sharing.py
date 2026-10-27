"""SHARE A RESULT (sharing.py): a link opens one frozen snapshot and nothing else, only while the owner allows links, until it
expires or is revoked; Email it drafts and never sends; an upload goes only through a sign-in that already holds a file scope."""
import json, re, unittest
from datetime import datetime, timedelta
from unittest import mock
from fastapi.testclient import TestClient

from taskuary import config, server, sharing, verdicts
from taskuary.store import MemoryStore
from taskuary.testing import Factory

c = TestClient(server.app)
web = TestClient(sharing.share_app)          # the share-only listener's app: what the network reaches
NOBODY = {'X-Taskuary-Token': ''}
AGENT = {'X-Taskuary-Token': config.load()['server']['agent_token']}
LAN = {'host': '0.0.0.0', 'port': 7787}
REPORT = '# Weekly spend\n\nTotal is **$1,200** <script>alert(1)</script>\n\n| vendor | amount |\n|---|---|\n| Payworth | 700 |\n| Trainly | 500 |'


class Rendering(unittest.TestCase):
    def test_markdown_is_escaped_before_any_tag_is_given_back(self):
        h = sharing.md_html(REPORT)
        self.assertIn('<h2>Weekly spend</h2>', h)
        self.assertIn('<b>$1,200</b>', h)
        self.assertIn('<td>Payworth</td>', h)
        self.assertNotIn('<script', h)
        self.assertIn('&lt;script&gt;', h)
        self.assertNotIn('href', sharing.md_html('[x](javascript:alert(1))'))

    def test_page_html_keeps_no_script_attribute_or_link(self):
        h = sharing.clean_html('<div onclick="x()"><img src=x onerror=alert(1)><script>steal()</script><b style="x">ok</b>'
                               '<a href="https://evil.example">l</a><td colspan="2">c</td><iframe src="//x"></iframe></div>')
        self.assertEqual(h, '<div><b>ok</b>l<td colspan="2">c</td></div>')

    def test_rows_are_a_table_and_escaped(self):
        self.assertIn('<th>vendor name</th>', sharing.rows_html([{'vendor_name': '<b>x</b>', 'n': 1200}]))
        self.assertIn('&lt;b&gt;x&lt;/b&gt;', sharing.rows_html([{'vendor_name': '<b>x</b>'}]))
        self.assertIn('1,200', sharing.rows_html([{'n': 1200}]))


class Links(unittest.TestCase):
    def setUp(self):
        self.s = server.store
        self.s.set_setting(sharing.SETTING, '1', 'test')
        self.f = Factory(self.s)
        self.mid = self.f.message(subject='Weekly spend', body=REPORT, channel='report')
        self.ip = mock.patch.object(sharing, 'lan_address', return_value='192.168.1.20'); self.ip.start()
        # the listener itself is a real port - stood in for here (ShareListener below drives its start and stop)
        self.on = mock.patch.object(sharing, 'sync_listener', return_value=''); self.on.start()
        self.port = mock.patch.object(sharing, 'listening', return_value=7797); self.port.start()
        sharing._L['store'] = self.s

    def tearDown(self):
        self.ip.stop(); self.on.stop(); self.port.stop()
        self.s.set_setting(sharing.SETTING, '0', 'test')

    def make(self, **kw):
        r = c.post('/api/shares', json={'how': 'link', 'kind': 'report', 'message': self.mid, **kw})
        self.assertEqual(r.status_code, 200, r.text)
        return r.json()

    def test_a_link_opens_the_one_snapshot_without_the_owner_token(self):
        out = self.make()
        self.assertRegex(out['url'], r'^http://192\.168\.1\.20:7797/share/[A-Za-z0-9_-]{40,}$')
        page = web.get('/share/' + out['url'].rsplit('/', 1)[1], headers=NOBODY)
        self.assertEqual(page.status_code, 200)
        self.assertIn('<h1>Weekly spend</h1>', page.text)
        self.assertNotIn('<script', page.text)
        self.assertNotIn(server.cfg['server']['token'], page.text)
        h = page.headers
        self.assertEqual(h['cache-control'], 'no-store')
        self.assertIn('noindex', h['x-robots-tag'])
        self.assertIn('sandbox', h['content-security-policy'])
        self.assertIn("default-src 'none'", h['content-security-policy'])
        self.assertEqual(h['referrer-policy'], 'no-referrer')

    def test_nothing_else_is_reachable_without_the_token(self):
        for path in ('/api/shares', '/api/shares/ways', f'/api/messages/{self.mid}', '/api/tasks'):
            self.assertEqual(c.get(path, headers=NOBODY).status_code, 401, path)
        self.assertEqual(c.post('/api/shares', json={'how': 'link', 'message': self.mid}, headers=NOBODY).status_code, 401)

    def test_the_snapshot_is_frozen(self):
        tok = self.make()['url'].rsplit('/', 1)[1]
        self.s._exec('UPDATE message SET BodyText=? WHERE MessageId=?', ('# Changed since', self.mid))
        self.assertIn('Payworth', web.get('/share/' + tok, headers=NOBODY).text)
        self.assertNotIn('Changed since', web.get('/share/' + tok, headers=NOBODY).text)

    def test_only_the_hash_of_the_token_is_kept(self):
        tok = self.make()['url'].rsplit('/', 1)[1]
        rows = self.s._rows('SELECT * FROM share_link')
        self.assertFalse(any(tok in json.dumps(r, default=str) for r in rows))
        self.assertNotIn(tok, json.dumps(c.get('/api/shares').json()))

    def test_revoked_expired_unknown_and_switched_off_are_one_404(self):
        a, b, d = (self.make()['url'].rsplit('/', 1)[1] for _ in range(3))
        sid = c.get('/api/shares').json()['data'][0]['id']
        self.assertEqual(c.delete(f'/api/shares/{sid}').status_code, 200)
        self.assertEqual(web.get('/share/' + d, headers=NOBODY).status_code, 404)           # the newest, revoked
        past = (datetime.now() - timedelta(minutes=1)).strftime('%Y-%m-%d %H:%M:%S')
        self.s._exec('UPDATE share_link SET ExpiresAt=? WHERE TokenHash=?', (past, sharing._hash(b)))
        self.assertEqual(web.get('/share/' + b, headers=NOBODY).status_code, 404)
        self.assertEqual(web.get('/share/' + 'x' * 43, headers=NOBODY).status_code, 404)
        self.assertEqual(web.get('/share/' + a, headers=NOBODY).status_code, 200)
        self.s.set_setting(sharing.SETTING, '0', 'test')
        self.assertEqual(web.get('/share/' + a, headers=NOBODY).status_code, 404)
        self.assertEqual({r.status_code for r in (web.get('/share/' + t, headers=NOBODY) for t in (a, b, d))}, {404})

    def test_off_by_default_and_refused_while_off(self):
        self.assertEqual(MemoryStore().get_setting(sharing.SETTING), '0')
        self.s.set_setting(sharing.SETTING, '0', 'test')
        r = c.post('/api/shares', json={'how': 'link', 'message': self.mid})
        self.assertEqual(r.status_code, 422)
        self.assertIn('Share links on your network', r.json()['detail'])

    def test_the_share_port_serves_nothing_but_share_pages(self):
        tok = self.make()['url'].rsplit('/', 1)[1]
        for path in ('/', '/api/tasks', '/api/shares', '/api/health', f'/api/messages/{self.mid}', '/assets/index.js', '/api/docs', '/openapi.json'):
            self.assertEqual(web.get(path, headers=NOBODY).status_code, 404, path)
            self.assertEqual(web.get(path, headers={'X-Taskuary-Token': server.cfg['server']['token']}).status_code, 404, path)
        self.assertEqual(web.post('/api/shares', json={'how': 'link', 'message': self.mid}).status_code, 404)
        self.assertEqual(web.get('/share/' + tok).headers['cache-control'], 'no-store')
        # ...and the app's own port does not serve them: it stays on this computer, behind the token
        self.assertEqual(c.get('/share/' + tok, headers=NOBODY).status_code, 404)

    def test_a_port_that_would_not_open_greys_the_link(self):
        self.on.stop(); self.port.stop()
        try:
            with mock.patch.object(sharing, 'sync_listener', return_value='port 7797 could not be opened'), mock.patch.object(sharing, 'listening', return_value=None):
                w = c.get('/api/shares/ways').json()
                self.assertEqual(w['link'], {'ok': False, 'why': 'port 7797 could not be opened'})
                self.assertEqual(c.post('/api/shares', json={'how': 'link', 'message': self.mid}).status_code, 422)
        finally: self.on.start(); self.port.start()

    def test_expiry_is_seven_days_by_default(self):
        exp = datetime.strptime(self.make()['expires'], '%Y-%m-%d %H:%M:%S')
        self.assertAlmostEqual((exp - datetime.now()).total_seconds(), 7 * 86400, delta=120)

    def test_an_agent_may_not_share_or_revoke(self):
        self.assertEqual(c.post('/api/shares', json={'how': 'link', 'message': self.mid}, headers=AGENT).status_code, 403)
        self.assertEqual(c.delete('/api/shares/1', headers=AGENT).status_code, 403)

    def test_every_share_is_on_the_audit_chain(self):
        self.make()
        rows = [r for r in self.s._rows("SELECT * FROM audit WHERE EntityType='share' ORDER BY Id DESC LIMIT 1")]
        self.assertEqual(rows[0]['Action'], 'link')
        self.assertEqual(json.loads(rows[0]['Detail'])['title'], 'Weekly spend')


class ShareListener(unittest.TestCase):
    """The second server: on its own port while the switch is on, on every interface, gone when it goes off; never in the demo."""
    def setUp(self): self.s = MemoryStore(); sharing.stop_listener()
    def tearDown(self): sharing.stop_listener()

    def test_it_follows_the_switch_and_the_port(self):
        started = []
        def start(port):
            started.append(port); sharing._L.update(port=port, srv=mock.Mock(started=True, should_exit=False), thread=mock.Mock(is_alive=lambda: True)); return ''
        with mock.patch.object(sharing, '_start', side_effect=start):
            self.assertEqual(sharing.sync_listener(self.s), '')
            self.assertEqual(started, [])                                      # off by default: no port at all
            self.s.set_setting(sharing.SETTING, '1', 'test')
            sharing.sync_listener(self.s); sharing.sync_listener(self.s)
            self.assertEqual((started, sharing.listening()), ([7797], 7797))   # once, on the default port
            self.s.set_setting('share_port', '8123', 'test')
            sharing.sync_listener(self.s)
            self.assertEqual((started, sharing.listening()), ([7797, 8123], 8123))
            self.s.set_setting(sharing.SETTING, '0', 'test')
            sharing.sync_listener(self.s)
            self.assertIsNone(sharing.listening())

    def test_it_binds_every_interface_on_its_own_port_with_only_the_share_app(self):
        import uvicorn
        seen = {}
        class Srv:
            def __init__(self, config): seen['cfg'] = config; self.started = True; self.should_exit = False
            def run(self): pass
        with mock.patch.object(uvicorn, 'Server', Srv):
            self.assertEqual(sharing._start(7797), '')
        self.assertEqual((seen['cfg'].host, seen['cfg'].port, seen['cfg'].app), ('0.0.0.0', 7797, sharing.share_app))
        self.assertNotEqual(seen['cfg'].app, server.app)

    def test_a_bad_port_falls_back_to_the_default(self):
        for v in ('80', 'abc', '70000', ''):
            self.s.set_setting('share_port', v, 'test')
            self.assertEqual(sharing.share_port(self.s), 7797, v)

    def test_never_in_the_demo(self):
        self.s.set_setting(sharing.SETTING, '1', 'test')
        with mock.patch('taskuary.demo.enabled', return_value=True), mock.patch.object(sharing, '_start') as start:
            sharing.sync_listener(self.s)
        start.assert_not_called()


class FileAccess(unittest.TestCase):
    """Allow saving files: asked for only when the card chooses it - Files.ReadWrite on a Microsoft sign-in, drive.file on Google's."""
    def test_microsoft_asks_for_files_only_when_chosen(self):
        from taskuary import msauth
        cid = next(x for x in server.store.list_connectors() if x['Type'] == 'outlook')['ConnectorId']
        d = {'device_code': 'D', 'user_code': 'X', 'verification_uri': 'u', 'expires_in': 9, 'interval': 1, 'message': ''}
        with mock.patch.object(msauth, 'device_start', return_value=dict(d)) as start:
            c.post(f'/api/connectors/{cid}/ms/signin', json={'code': True})
            c.post(f'/api/connectors/{cid}/ms/signin', json={'code': True, 'files': True})
            c.post(f'/api/connectors/{cid}/ms/signin', json={'code': True, 'files': False})
        scopes = [call.args[1].split() for call in start.call_args_list]
        self.assertNotIn('Files.ReadWrite', scopes[0])
        self.assertIn('Files.ReadWrite', scopes[1])
        self.assertNotIn('Files.ReadWrite', scopes[2])
        self.assertEqual(msauth.SCOPES, 'offline_access User.Read Mail.ReadWrite Mail.Send Calendars.ReadWrite')   # the default never widens
        self.assertIn('Files.ReadWrite', msauth.scopes_for('teams', True).split())

    def test_a_teams_card_that_may_save_files_carries_onedrive(self):
        s = MemoryStore()
        s.save_connector({'Type': 'outlook', 'Name': 'Outlook', 'Active': 1, 'Secret': 'r',
                          'ConfigJson': json.dumps({'auth': 'user', 'granted_scope': 'Mail.Send'})}, 'test')
        s.save_connector({'Type': 'teams', 'Name': 'Teams', 'Active': 1, 'Secret': 'r',
                          'ConfigJson': json.dumps({'auth': 'user', 'granted_scope': 'Chat.ReadWrite Files.ReadWrite'})}, 'test')
        self.assertEqual(sharing.onedrive_block(s), '')
        self.assertEqual(sharing._ms_card(s)['Type'], 'teams')

    def gmail(self, **cfg):
        return server.store.save_connector({'Type': 'gmail', 'Name': 'Gmail', 'Active': 1,
                                            'ConfigJson': json.dumps({'address': 'alex@northwind.example', 'google_client_id': 'cid.apps.example',
                                                                      'google_client_secret': 'sec', 'google_refresh_token': 'old', **cfg})}, 'test')

    def test_google_asks_again_with_drive_file_and_keeps_the_new_token(self):
        from urllib.parse import parse_qs, urlsplit
        from taskuary import fileaccess
        cid = self.gmail()
        with mock.patch('taskuary.calwrite._google_token', return_value=('t', 'https://www.googleapis.com/auth/calendar.events')):
            url = c.post(f'/api/connectors/{cid}/google/files', json={'on': True}).json()['url']
        q = {k: v[0] for k, v in parse_qs(urlsplit(url).query).items()}
        self.assertEqual(q['scope'].split(), ['https://www.googleapis.com/auth/calendar.events', fileaccess.DRIVE_FILE])
        self.assertTrue(q['redirect_uri'].startswith('http://127.0.0.1:') and q['redirect_uri'].endswith('/api/google/files/callback'))
        self.assertEqual(q['code_challenge_method'], 'S256')
        bad = c.get('/api/google/files/callback', params={'code': 'x', 'state': 'forged'}, headers=NOBODY)
        self.assertEqual(bad.status_code, 200); self.assertIn('was not started here', bad.text)
        tok = mock.Mock(status_code=200, json=lambda: {'refresh_token': 'new', 'scope': f"https://www.googleapis.com/auth/calendar.events {fileaccess.DRIVE_FILE}"})
        with mock.patch.object(fileaccess.requests, 'post', return_value=tok) as post:
            ok = c.get('/api/google/files/callback', params={'code': 'C', 'state': q['state']}, headers=NOBODY)   # outside the token gate
        self.assertIn('may now save files', ok.text)
        self.assertEqual(post.call_args.kwargs['data']['code_verifier'] and post.call_args.kwargs['data']['code'], 'C')
        cfg = json.loads(server.store.get_connector(cid, with_secret=True)['ConfigJson'])
        self.assertEqual((cfg['google_refresh_token'], cfg['allow_files']), ('new', True))
        again = c.get('/api/google/files/callback', params={'code': 'C', 'state': q['state']}, headers=NOBODY)
        self.assertIn('was not started here', again.text)                  # a state answers once

    def test_a_google_card_with_no_oauth_client_cannot(self):
        cid = server.store.save_connector({'Type': 'gmail', 'Name': 'Gmail 2', 'Active': 1, 'ConfigJson': json.dumps({'address': 'x@northwind.example'})}, 'test')
        self.assertEqual(c.post(f'/api/connectors/{cid}/google/files', json={'on': True}).status_code, 409)

    def test_an_agent_may_not_widen_a_sign_in(self):
        cid = self.gmail()
        self.assertEqual(c.post(f'/api/connectors/{cid}/google/files', json={'on': True}, headers=AGENT).status_code, 403)


class EmailIt(unittest.TestCase):
    def setUp(self):
        self.s = MemoryStore(); self.f = Factory(self.s)
        self.ok = mock.patch('taskuary.capabilities.send_refusal', return_value='')
        self.ok.start()

    def tearDown(self): self.ok.stop()

    def test_drafts_on_a_task_of_its_own_and_sends_nothing(self):
        mid = self.f.message(subject='Weekly spend', body=REPORT, channel='report')
        with mock.patch('taskuary.outbound.send_out') as send:
            out = sharing.share(self.s, LAN, {'how': 'email', 'message': mid, 'to': ['erin@northwind.example', 'gail@northwind.example']})
        send.assert_not_called()
        rv = self.s.get_review(out['review_id'])
        self.assertEqual(rv['Status'], 'pending')
        env = json.loads(rv['Deliver'])
        self.assertEqual((env['to'], env['cc'], env['format'], env['subject']),
                         (['erin@northwind.example'], ['gail@northwind.example'], 'html', 'Weekly spend'))
        self.assertIn('Payworth', rv['DraftText'])

    def test_an_open_tasks_result_lands_in_its_close_out(self):
        tid = self.f.task(title='Vendor numbers')
        with mock.patch('taskuary.outbox.work_of', return_value='Payworth is 700.'):
            out = sharing.share(self.s, LAN, {'how': 'email', 'kind': 'agent', 'task': tid, 'to': ['erin@northwind.example']})
        self.assertEqual(out['task_id'], tid)
        self.assertEqual(self.s.get_review(out['review_id'])['TaskId'], tid)
        self.assertEqual(self.s.get_review(out['review_id'])['DraftText'], 'Payworth is 700.')

    def test_a_bad_address_or_none_is_refused(self):
        mid = self.f.message(subject='x', body='y')
        with self.assertRaises(ValueError): sharing.share(self.s, LAN, {'how': 'email', 'message': mid, 'to': ['not an address']})
        with self.assertRaises(ValueError): sharing.share(self.s, LAN, {'how': 'email', 'message': mid, 'to': []})

    def test_a_mailbox_that_cannot_send_is_greyed(self):
        self.ok.stop()
        try:
            with mock.patch('taskuary.capabilities.send_refusal', return_value='email cannot send from here - no mailbox'):
                w = sharing.ways(self.s, LAN)
                self.assertEqual(w['email'], {'ok': False, 'why': 'email cannot send from here - no mailbox'})
        finally: self.ok.start()

    def test_the_send_carries_html_rendered_from_the_approved_text(self):
        snap = {'envelope': {'channel': 'email', 'to': ['erin@northwind.example'], 'subject': 'Weekly spend', 'format': 'html'},
                'body': 'Edited **by me**', 'message': None}
        with mock.patch('taskuary.outbound.send_out', return_value={'channel': 'email'}) as send:
            verdicts._send_snapshot(self.s, snap)
        html = send.call_args.kwargs['html']
        self.assertIn('<b>by me</b>', html)
        self.assertEqual(send.call_args.args[4], 'Edited **by me**')        # the plain part is the text as approved
        with mock.patch('taskuary.outbound.send_out', return_value={'channel': 'email'}) as send:
            verdicts._send_snapshot(self.s, {**snap, 'envelope': {**snap['envelope'], 'format': None}})
        self.assertNotIn('html', send.call_args.kwargs)

    def test_smtp_sends_html_beside_the_text(self):
        from taskuary import imapmail
        sent = {}
        class S:
            def __init__(self, *a, **k): pass
            def __enter__(self): return self
            def __exit__(self, *a): pass
            sock = None
            def starttls(self, **k): pass
            def login(self, *a): pass
            def sendmail(self, frm, to, msg): sent['msg'] = msg
        with mock.patch.object(imapmail.smtplib, 'SMTP', S), mock.patch.object(imapmail, 'verify_pin'):
            imapmail.send_smtp(None, {'ConfigJson': json.dumps({'address': 'alex@northwind.example', 'smtp_host': 'smtp.northwind.example'}),
                                      'Type': 'imap', 'Secret': 'x'}, ['erin@northwind.example'], 'Weekly', 'plain words', html='<p>rich</p>')
        self.assertIn('multipart/alternative', sent['msg'])
        self.assertIn('text/plain', sent['msg']); self.assertIn('text/html', sent['msg'])


class Uploads(unittest.TestCase):
    def setUp(self):
        self.s = MemoryStore(); self.f = Factory(self.s)
        self.mid = self.f.message(subject='Weekly spend', body=REPORT, channel='report')
        sharing._CACHE.clear()

    def outlook(self, scope):
        self.s.save_connector({'Type': 'outlook', 'Name': 'Outlook', 'Active': 1, 'Secret': 'refresh',
                               'ConfigJson': json.dumps({'auth': 'user', 'client_id': 'app', 'granted_scope': scope})}, 'test')

    def test_without_a_file_scope_onedrive_is_greyed_and_refused(self):
        self.outlook('offline_access User.Read Mail.ReadWrite Mail.Send Calendars.ReadWrite')
        w = sharing.ways(self.s, LAN)
        self.assertFalse(w['onedrive']['ok'])
        self.assertIn('Files.ReadWrite', w['onedrive']['why'])
        with mock.patch.object(sharing.requests, 'put') as put, self.assertRaises(PermissionError):
            sharing.share(self.s, LAN, {'how': 'onedrive', 'message': self.mid})
        put.assert_not_called()

    def test_onedrive_uploads_the_page_to_the_taskuary_folder(self):
        self.outlook('offline_access User.Read Mail.Send Files.ReadWrite')
        res = mock.Mock(status_code=201, json=lambda: {'webUrl': 'https://northwind-my.sharepoint.example/x.html'})
        with mock.patch.object(sharing, '_ms_token', return_value=({'auth': 'user'}, 'tok')), \
             mock.patch.object(sharing.requests, 'put', return_value=res) as put:
            out = sharing.share(self.s, LAN, {'how': 'onedrive', 'message': self.mid})
        self.assertEqual(out['url'], 'https://northwind-my.sharepoint.example/x.html')
        url = put.call_args.args[0]
        self.assertTrue(url.startswith('https://graph.microsoft.com/v1.0/me/drive/root:/Taskuary/Weekly%20spend'), url)
        self.assertIn(b'<h1>Weekly spend</h1>', put.call_args.kwargs['data'])

    def test_no_google_sign_in_greys_google_drive(self):
        w = sharing.ways(self.s, LAN)
        self.assertFalse(w['gdrive']['ok'])
        self.assertIn('Google', w['gdrive']['why'])

    def test_google_drive_uploads_through_a_drive_file_scope(self):
        self.s.save_connector({'Type': 'gmail', 'Name': 'Gmail', 'Active': 1,
                               'ConfigJson': json.dumps({'google_refresh_token': 'r', 'address': 'alex@northwind.example'})}, 'test')
        with mock.patch('taskuary.calwrite._google_token', return_value=('tok', 'https://www.googleapis.com/auth/drive.file')), \
             mock.patch.object(sharing.requests, 'get', return_value=mock.Mock(status_code=200, json=lambda: {'files': [{'id': 'F1'}]})), \
             mock.patch.object(sharing.requests, 'post', return_value=mock.Mock(status_code=200, json=lambda: {'webViewLink': 'https://drive.google.example/f'})) as post:
            out = sharing.share(self.s, LAN, {'how': 'gdrive', 'message': self.mid})
        self.assertEqual(out['url'], 'https://drive.google.example/f')
        self.assertIn(b'"parents": ["F1"]', post.call_args.kwargs['data'])

    def test_a_google_sign_in_without_drive_is_greyed(self):
        self.s.save_connector({'Type': 'gmail', 'Name': 'Gmail', 'Active': 1, 'ConfigJson': json.dumps({'google_refresh_token': 'r'})}, 'test')
        with mock.patch('taskuary.calwrite._google_token', return_value=('tok', 'https://www.googleapis.com/auth/calendar.events')):
            self.assertIn('drive.file', sharing.ways(self.s, LAN)['gdrive']['why'])


class Snapshot(unittest.TestCase):
    def test_a_report_that_is_only_rows_is_its_table(self):
        s = MemoryStore(); mid = Factory(s).message(subject='Rows', body=json.dumps([{'a': 1}, {'a': 2}]))
        snap = sharing.snapshot(s, {'message': mid})
        self.assertEqual((snap['text'], snap['data']), ('', [{'a': 1}, {'a': 2}]))
        self.assertIn('| a |', sharing.as_text(snap))

    def test_nothing_to_share_says_so(self):
        with self.assertRaises(ValueError): sharing.snapshot(MemoryStore(), {'kind': 'dashboard', 'title': 'Empty'})

    def test_a_dashboard_brings_its_own_cleaned_html(self):
        snap = sharing.snapshot(MemoryStore(), {'kind': 'dashboard', 'title': 'Spend', 'html': '<h2>Spend</h2><script>x()</script>'})
        doc = sharing.document(snap)
        self.assertIn('<h2>Spend</h2>', doc)
        self.assertNotIn('x()', doc)


if __name__ == '__main__': unittest.main()
