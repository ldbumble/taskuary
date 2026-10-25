"""SIGNING IN FOR THE BROWSER AGENT (signin.py): the page's own origin decides where a password goes, never the agent's word or a
mail's; a fill link works once and not for long; nothing typed reaches a prompt, a log, the audit or a comment; a sign-in is kept only
when the owner ticks it, sealed, and filled by itself next time; Remove takes the password and the site's cookies with it."""
import json, os, tempfile, threading, time, unittest
from pathlib import Path
from unittest import mock
from fastapi.testclient import TestClient
from loguru import logger

from taskuary import browserview, config, selfclose, server, signin, vault, workerstate as ws
from taskuary.store import MemoryStore
from taskuary.testing import Factory

PW, USER = 'correct-horse-9!', 'alex@northwind.example'
c = TestClient(server.app)
AGENT = {'X-Taskuary-Token': config.load()['server']['agent_token']}


def on_page(url): return mock.patch.object(browserview, 'state', return_value={'open': True, 'url': url, 'port': 1})


class Sites(unittest.TestCase):
    def test_a_name_under_the_site_is_the_site(self):
        self.assertTrue(signin.on_site('https://login.bank.example/auth?x=1', 'bank.example'))
        self.assertTrue(signin.on_site('https://bank.example/', 'bank.example'))
        self.assertEqual(signin.site_of('https://www.bank.co.uk/login'), 'bank.co.uk')       # not co.uk: that would be every UK site

    def test_a_lookalike_is_another_site(self):
        for url in ('https://bank.example.evil.example/', 'https://bank-example.example/', 'https://evilbank.example/',
                    'https://xn--bnk-sna.example/', 'https://bаnk.example/',              # a Cyrillic а: its punycode is another name
                    'https://bank.example@evil.example/'):                                 # the user-info is not the host
            self.assertFalse(signin.on_site(url, 'bank.example'), url)

    def test_only_https_and_a_local_app_are_places_a_password_goes(self):
        self.assertEqual(signin.site_of('http://bank.example/login'), '')
        self.assertEqual(signin.site_of('javascript:alert(1)'), '')
        self.assertEqual(signin.site_of('file:///C:/x.html'), '')
        self.assertEqual(signin.site_of('http://127.0.0.1:8765/'), '127.0.0.1')

    def test_shared_hosting_siblings_are_not_one_site(self):
        self.assertEqual(signin.site_of('https://alice.github.io/'), 'alice.github.io')
        self.assertFalse(signin.on_site('https://mallory.github.io/', 'alice.github.io'))
        self.assertEqual(signin.registrable('co.uk'), '')                                  # a bare suffix belongs to nobody

    def test_the_marker_is_read_and_never_shown(self):
        self.assertEqual(selfclose.signin_marker('Opened the portal.\n[[TASKUARY-SIGNIN: bank.example]]'), ('Opened the portal.', 'bank.example'))
        self.assertEqual(selfclose.signin_marker('nothing here'), ('nothing here', None))
        self.assertNotIn('SIGNIN', selfclose.for_screen('going to sign in [[TASKUARY-SIGNIN: bank.example]]'))


class Links(unittest.TestCase):
    def setUp(self): self.s = MemoryStore(); self.tid = Factory(self.s).task('Pay the toll')

    def test_a_link_works_once_and_only_its_hash_is_kept(self):
        tok = signin.mint(self.s, self.tid, 'sid1', 'bank.example', 'signin:bank.example')
        self.assertEqual(signin.peek(self.s, tok)['Site'], 'bank.example')
        self.assertEqual(signin.peek(self.s, tok)['Site'], 'bank.example')               # reading does not spend it
        self.assertIsNotNone(signin.take(self.s, tok))
        self.assertIsNone(signin.take(self.s, tok))
        self.assertIsNone(signin.peek(self.s, tok))
        self.assertNotIn(tok, json.dumps(self.s._rows('SELECT * FROM signin_token')))

    def test_a_link_expires(self):
        tok = signin.mint(self.s, self.tid, 'sid1', 'bank.example', 'signin:bank.example')
        with mock.patch.object(signin, '_now', return_value=time.time() + signin.TTL + 1):
            self.assertIsNone(signin.peek(self.s, tok))
            self.assertIsNone(signin.take(self.s, tok))
        self.assertIsNone(signin.take(self.s, 'not-a-token'))

    def test_two_presses_at_once_spend_it_once(self):
        tok = signin.mint(self.s, self.tid, 'sid1', 'bank.example', 'signin:bank.example')
        got = []
        ts = [threading.Thread(target=lambda: got.append(signin.take(self.s, tok))) for _ in range(6)]
        for t in ts: t.start()
        for t in ts: t.join()
        self.assertEqual(sum(1 for g in got if g), 1)


class FakePage:
    """A stand-in for the browser tab: where it is, what it has, and everything typed into it."""
    def __init__(self, href='https://login.bank.example/', password=True, user=True, top=True, frames=(), moves_to=None, two_step=False):
        self.href, self.pw, self.user, self.top, self.frames_, self.moves_to, self.two_step = href, password, user, top, list(frames), moves_to, two_step
        self.typed, self.focus, self.looks = [], None, 0
    def fields(self, want=''):
        self.looks += 1
        if want: self.focus = want
        return {'href': self.href, 'origin': self.href, 'top': self.top, 'password': self.pw, 'user': self.user, 'frames': self.frames_,
                'focused': bool(want) and (self.pw if want == 'password' else self.user)}
    def js(self, expr):
        if self.moves_to: self.href = self.moves_to                 # the page navigated after the box was focused
        return {'href': self.href, 'password': self.focus == 'password'}
    def type(self, text): self.typed.append((self.focus, text))
    def enter(self):
        self.typed.append((self.focus, '<enter>'))
        if self.two_step and self.focus == 'user': self.pw = True


class Filling(unittest.TestCase):
    def test_it_types_into_the_pinned_site(self):
        p = FakePage()
        signin.fill_page(p, 'bank.example', USER, PW)
        self.assertEqual(p.typed, [('user', USER), ('password', PW), ('password', '<enter>')])

    def test_a_two_step_sign_in_waits_for_its_password_page(self):
        p = FakePage(password=False, two_step=True)
        with mock.patch.object(signin.time, 'sleep'): signin.fill_page(p, 'bank.example', USER, PW, wait=5)
        self.assertEqual(p.typed, [('user', USER), ('user', '<enter>'), ('password', PW), ('password', '<enter>')])

    def test_another_site_gets_nothing(self):
        for p in (FakePage(href='https://bank.example.evil.example/'), FakePage(href='https://evil.example/'), FakePage(top=False),
                  FakePage(href='http://bank.example/')):
            with self.assertRaises(signin.SignInError): signin.fill_page(p, 'bank.example', USER, PW)
            self.assertEqual(p.typed, [])

    def test_a_page_that_moves_under_the_password_gets_no_password(self):
        p = FakePage(moves_to='https://evil.example/')
        with self.assertRaises(signin.SignInError): signin.fill_page(p, 'bank.example', USER, PW)
        self.assertNotIn(PW, [t for _, t in p.typed])

    def test_a_form_inside_another_sites_frame_is_refused_and_said(self):
        p = FakePage(password=False, user=False, frames=['https://idp.evil.example/login'])
        with self.assertRaises(signin.SignInError) as e: signin.fill_page(p, 'bank.example', USER, PW)
        self.assertIn('frame from another site', str(e.exception))
        self.assertEqual(p.typed, [])


class Asking(unittest.TestCase):
    def setUp(self):
        self.s = MemoryStore(); self.tid = Factory(self.s).task('Pay the toll'); self.sid = 'sess1'
        signin._TRIED.clear()
        self.logs = []; self.h = logger.add(lambda m: self.logs.append(str(m)), level='DEBUG')

    def tearDown(self): logger.remove(self.h)

    def everything_written(self) -> str:
        rows = [self.s._rows(f'SELECT * FROM {t}') for t in ('audit', 'comment', 'worker_event', 'signin_token')]
        vault_rows = self.s._rows('SELECT * FROM signin_vault')
        return json.dumps(rows, default=str) + json.dumps(vault_rows, default=str) + '\n'.join(self.logs)

    def wait_for(self, pred, secs=5):
        end = time.time() + secs
        while time.time() < end and not pred(): time.sleep(.02)
        self.assertTrue(pred())

    def test_the_site_is_the_pages_not_the_agents_word(self):
        with on_page('https://login.bank.example/'): out = signin.needs(self.s, self.tid, self.sid, 'evil.example')
        self.assertEqual(out, {'site': 'bank.example', 'auto': False})
        req = ws.status(self.s, self.tid)['requests'][-1]
        self.assertEqual((req['request_id'], req['text']), ('signin:bank.example', 'Sign in to bank.example to continue'))
        self.assertEqual(signin.pending(self.s, self.tid)['site'], 'bank.example')
        self.assertEqual(signin.phone_line(self.s, self.tid), 'Sign in to bank.example on your PC to continue')

    def test_no_sign_in_page_no_fill_ever(self):
        with on_page('http://bank.example/'): out = signin.needs(self.s, self.tid, self.sid, 'bank.example')
        self.assertEqual(out['site'], '')
        self.assertIsNone(signin.pending(self.s, self.tid))
        with self.assertRaises(LookupError): signin.link(self.s, self.tid)

    def test_save_is_off_unless_ticked(self):
        self.assertIn('<input type="checkbox" name="save" value="1">', signin.form_html('bank.example', 15))
        self.assertNotIn('checked', signin.form_html('bank.example', 15))
        with on_page('https://login.bank.example/'): signin.needs(self.s, self.tid, self.sid)
        typed = []
        tok = signin.link(self.s, self.tid)['url'].rsplit('/', 1)[1]
        out = signin.by_owner(self.s, tok, USER, PW, False, fill=lambda *a: typed.append(a))
        self.assertEqual((out['saved'], typed), (False, [(self.sid, 'bank.example', USER, PW)]))
        self.assertIsNone(signin.saved(self.s, 'bank.example'))
        self.assertNotIn(PW, self.everything_written())

    def test_a_ticked_save_is_sealed_and_fills_by_itself_next_time(self):
        with on_page('https://login.bank.example/'): signin.needs(self.s, self.tid, self.sid)
        tok = signin.link(self.s, self.tid)['url'].rsplit('/', 1)[1]
        self.assertTrue(signin.by_owner(self.s, tok, USER, PW, True, fill=lambda *a: None)['saved'])
        row = signin.saved(self.s, 'bank.example')
        self.assertTrue(vault.sealed(row['Secret']) and vault.sealed(row['User']))
        self.assertEqual(vault.unseal(row['Secret']), PW)
        # ...the agent asks again on another task, on the same site: the server types it, the owner does nothing
        t2, typed = Factory(self.s).task('Pay the next toll'), []
        with on_page('https://www.bank.example/signin'): out = signin.needs(self.s, t2, 'sess2', 'bank.example', fill=lambda *a: typed.append(a))
        self.assertTrue(out['auto'])
        self.wait_for(lambda: any(r['Action'] == 'signin_fill' and r['EntityId'] == t2 for r in self.s._rows('SELECT * FROM audit')))
        self.assertEqual(typed, [('sess2', 'bank.example', USER, PW)])
        audit = [json.loads(r['Detail']) for r in self.s._rows("SELECT * FROM audit WHERE Action='signin_fill' AND EntityId=?", (t2,))]
        self.assertEqual(audit, [{'site': 'bank.example', 'how': 'vault', 'ok': True}])
        self.assertIsNotNone(signin.saved(self.s, 'bank.example')['LastUsed'])
        self.assertNotIn(PW, self.everything_written())
        self.assertNotIn(USER, json.dumps(signin.listing(self.s)))
        # ...and a site that asks AGAIN minutes later is not tried twice
        with on_page('https://www.bank.example/signin'): self.assertFalse(signin.needs(self.s, t2, 'sess2', fill=lambda *a: typed.append(a))['auto'])

    def test_a_saved_sign_in_is_never_typed_on_another_site(self):
        signin.save(self.s, 'bank.example', USER, PW)
        typed = []
        with on_page('https://bank-example.example/login'): out = signin.needs(self.s, self.tid, self.sid, 'bank.example', fill=lambda *a: typed.append(a))
        self.assertEqual((out['site'], out['auto']), ('bank-example.example', False))
        time.sleep(.1)
        self.assertEqual(typed, [])

    def test_the_agent_is_told_only_that_it_is_signed_in(self):
        class Chat:
            sid, alive, task_id = 'sess1', True, None
            def __init__(self): self.said = []
            def send_prompt(self, text, as_owner=True): self.said.append((text, as_owner))
        sess = Chat(); sess.task_id = self.tid
        with on_page('https://login.bank.example/'), mock.patch.dict('taskuary.terminal.SESSIONS', {'sess1': sess}):
            signin.needs(self.s, self.tid, 'sess1')
            self.assertEqual(ws.status(self.s, self.tid)['requests'][-1]['choices'], ['Signed in'])
            tok = signin.link(self.s, self.tid)['url'].rsplit('/', 1)[1]
            signin.by_owner(self.s, tok, USER, PW, False, fill=lambda *a: None)
            self.wait_for(lambda: sess.said)
            self.wait_for(lambda: not ws.status(self.s, self.tid)['requests'])
        self.assertEqual(sess.said, [('Signed in to bank.example - continue.', False)])

    def test_a_failed_fill_is_audited_without_the_secret(self):
        with on_page('https://login.bank.example/'): signin.needs(self.s, self.tid, self.sid)
        tok = signin.link(self.s, self.tid)['url'].rsplit('/', 1)[1]
        def boom(*a): raise signin.SignInError('the page is no longer on bank.example - nothing was typed')
        with self.assertRaises(signin.SignInError): signin.by_owner(self.s, tok, USER, PW, True, fill=boom)
        self.assertIsNone(signin.saved(self.s, 'bank.example'))                        # a sign-in that did not go in is not kept
        self.assertNotIn(PW, self.everything_written())

    def test_no_keychain_no_save(self):
        with mock.patch.dict(os.environ, {'TASKUARY_VAULT': 'plain'}), self.assertRaises(ValueError): signin.save(self.s, 'bank.example', USER, PW)
        self.assertIsNone(signin.saved(self.s, 'bank.example'))


class FromAHook(unittest.TestCase):
    """A CLI's Stop hook carries the marker in its last message: it becomes the sign-in ask, and no judge reads the turn for one."""
    def test_the_stop_hook_raises_the_sign_in(self):
        from types import SimpleNamespace
        from taskuary import hooks, terminal as term
        s = MemoryStore(); tid = Factory(s).task('Pay the toll', kind='coding'); signin._TRIED.clear()
        pty = SimpleNamespace(sid='run1', alive=True, task_id=tid, cwd=r'C:\code\repo', agent='coding', label='coding', argv=['claude'],
                              last=1.0, ext_id='c-sess', started='2026-10-24 09:00:00', typed=[], files=lambda: [], tail=lambda n=3: [],
                              idle=lambda: 0.0, witness=SimpleNamespace(note=lambda n: None), store=s, bg={})
        judged = []
        with mock.patch.dict(term.SESSIONS, {'run1': pty}, clear=True), mock.patch.object(term, 'bind_ext', lambda t, sid: None), \
                on_page('https://login.bank.example/'), mock.patch.object(hooks, 'judge_turn', lambda *a, **k: judged.append(a)):
            hooks.receive({'hook_event_name': 'Stop', 'session_id': 'c-sess', 'cwd': r'C:\code\repo',
                           'last_assistant_message': 'The toll portal wants a sign-in.\n[[TASKUARY-SIGNIN: bank.example]]'}, cli='claude')
            st = ws.status(s, tid)
        self.assertEqual([r['request_id'] for r in st['requests']], ['signin:bank.example'])
        self.assertEqual(st['requests'][0]['choices'], [])                    # a pty is answered in words, never by typing "1"
        self.assertEqual(judged, [])
        self.assertNotIn('SIGNIN', st['said'])


class Removing(unittest.TestCase):
    def test_remove_takes_the_password_and_the_sites_cookies(self):
        s = MemoryStore()
        signin.save(s, 'bank.example', USER, PW)
        d = Path(tempfile.mkdtemp()); (d / 'sessions').mkdir()
        kept = {'cookies': [{'name': 'sid', 'domain': '.bank.example', 'value': 'x'}, {'name': 'a', 'domain': 'login.bank.example', 'value': 'y'},
                            {'name': 'keep', 'domain': '.other.example', 'value': 'z'}, {'name': 'nope', 'domain': 'bank.example.evil.example', 'value': 'w'}],
                'origins': [{'origin': 'https://login.bank.example', 'localStorage': []}, {'origin': 'https://other.example', 'localStorage': []}]}
        (d / 'sessions' / 'taskuary-tq-abc.json').write_text(json.dumps(kept), encoding='utf-8')
        (d / 'sessions' / 'someone-else.json').write_text(json.dumps(kept), encoding='utf-8')
        with mock.patch.dict(os.environ, {'AGENT_BROWSER_HOME': str(d)}):
            self.assertTrue(signin.remove(s, 'bank.example'))
        self.assertIsNone(signin.saved(s, 'bank.example'))
        self.assertEqual(signin.listing(s), [])
        left = json.loads((d / 'sessions' / 'taskuary-tq-abc.json').read_text(encoding='utf-8'))
        self.assertEqual([k['name'] for k in left['cookies']], ['keep', 'nope'])
        self.assertEqual([o['origin'] for o in left['origins']], ['https://other.example'])
        self.assertEqual(json.loads((d / 'sessions' / 'someone-else.json').read_text(encoding='utf-8')), kept)   # not Taskuary's: untouched


class Routes(unittest.TestCase):
    def setUp(self):
        self.s = server.store; self.tid = Factory(self.s).task('Pay the toll'); signin._TRIED.clear()
        with on_page('https://login.bank.example/'): signin.needs(self.s, self.tid, f'route-{self.tid}')

    def test_the_fill_page_names_the_site_and_works_once(self):
        r = c.post(f'/api/tasks/{self.tid}/signin/link'); self.assertEqual(r.status_code, 200, r.text)
        url = r.json()['url']
        page = c.get(url)
        self.assertEqual(page.status_code, 200)
        self.assertIn('<p class="site">bank.example</p>', page.text)
        self.assertIn("frame-ancestors 'none'", page.headers['content-security-policy'])
        with mock.patch.object(signin, 'type_in') as typed:
            r = c.post(url, data={'username': USER, 'password': PW})
            self.assertEqual(r.status_code, 200, r.text)
            typed.assert_called_once_with(f'route-{self.tid}', 'bank.example', USER, PW)
            self.assertEqual(c.post(url, data={'username': USER, 'password': PW}).status_code, 410)
        self.assertEqual(c.get(url).status_code, 410)

    def test_another_site_cannot_post_the_form(self):
        url = c.post(f'/api/tasks/{self.tid}/signin/link').json()['url']
        with mock.patch.object(signin, 'type_in') as typed:
            r = c.post(url, data={'password': PW}, headers={'Origin': 'https://evil.example', 'Sec-Fetch-Site': 'cross-site'})
        self.assertEqual(r.status_code, 403)
        typed.assert_not_called()

    def test_an_agent_reaches_none_of_it(self):
        self.assertEqual(c.post(f'/api/tasks/{self.tid}/signin/link', headers=AGENT).status_code, 403)
        self.assertEqual(c.get('/api/signins', headers=AGENT).status_code, 403)
        self.assertEqual(c.delete('/api/signins/bank.example', headers=AGENT).status_code, 403)
        self.assertEqual(c.get('/signin/whatever', headers=AGENT).status_code, 403)

    def test_settings_lists_and_removes(self):
        signin.save(self.s, 'bank.example', USER, PW)
        self.assertEqual([r['site'] for r in c.get('/api/signins').json()['data']], ['bank.example'])
        with mock.patch.object(browserview, 'forget_site', return_value=0), mock.patch.object(signin, '_forget_live'):
            self.assertEqual(c.delete('/api/signins/bank.example').status_code, 200)
            self.assertEqual(c.delete('/api/signins/bank.example').status_code, 404)
        self.assertEqual(c.get('/api/signins').json()['data'], [])


if __name__ == '__main__': unittest.main()
