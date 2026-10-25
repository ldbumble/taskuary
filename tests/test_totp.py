"""AUTHENTICATOR CODES IN THE SIGN-IN VAULT (totp.py, signin.py): the code is RFC 6238's to the digit; the key is kept sealed and only
with a sign-in the owner saved; the server types the code on the pinned site's code prompt and nowhere else; nothing of the key or the
code reaches the audit, a comment, a log or the agent; the receipt says a code went in."""
import base64, json, sys, time, unittest
from unittest import mock
from fastapi.testclient import TestClient
from loguru import logger

from taskuary import server, signin, totp, vault
from taskuary.store import MemoryStore
from taskuary.testing import Factory
from tests.test_signin import AGENT, FakeKeyring, FakePage, PW, USER, on_page

c = TestClient(server.app)
# a key as a site prints it: base32, in groups. Invented - no account anywhere holds it
KEY = 'JBSW Y3DP EHPK 3PXP JBSW Y3DP EHPK 3PXP'
URI = 'otpauth://totp/Northwind:alex@northwind.example?secret=JBSWY3DPEHPK3PXPJBSWY3DPEHPK3PXP&issuer=Northwind&digits=6&period=30'


def setUpModule():
    if sys.platform != 'win32':
        p = mock.patch.object(vault, '_keyring', return_value=FakeKeyring()); p.start(); unittest.addModuleCleanup(p.stop)


def b32(s: str) -> str: return base64.b32encode(s.encode()).decode()


class Rfc(unittest.TestCase):
    def test_rfc4226_hotp_vectors(self):
        want = ['755224', '287082', '359152', '969429', '338314', '254676', '287922', '162583', '399871', '520489']
        self.assertEqual([totp.hotp(b'12345678901234567890', i) for i in range(10)], want)

    def test_rfc6238_totp_vectors(self):
        keys = {'SHA1': '12345678901234567890', 'SHA256': '12345678901234567890123456789012',
                'SHA512': '1234567890123456789012345678901234567890123456789012345678901234'}
        table = {59: ('94287082', '46119246', '90693936'), 1111111109: ('07081804', '68084774', '25091201'),
                 1111111111: ('14050471', '67062674', '99943326'), 1234567890: ('89005924', '91819424', '93441116'),
                 2000000000: ('69279037', '90698825', '38618901'), 20000000000: ('65353130', '77737706', '47863826')}
        for t, codes in table.items():
            for algo, want in zip(('SHA1', 'SHA256', 'SHA512'), codes):
                cfg = {'secret': b32(keys[algo]), 'digits': 8, 'period': 30, 'algorithm': algo}
                self.assertEqual(totp.code(cfg, t), want, (t, algo))

    def test_a_key_as_sites_print_it_and_as_its_link(self):
        a, b = totp.parse(KEY), totp.parse(URI)
        self.assertEqual(a, b)
        self.assertEqual(a, {'secret': 'JBSWY3DPEHPK3PXPJBSWY3DPEHPK3PXP', 'digits': 6, 'period': 30, 'algorithm': 'SHA1'})
        self.assertEqual(totp.parse(KEY.lower()), a)
        self.assertEqual(totp.loads(totp.dumps(a)), a)
        self.assertEqual(len(totp.code(a)), 6)
        self.assertAlmostEqual(totp.left(a, 61.0), 29.0)

    def test_what_is_no_key_is_refused_not_guessed(self):
        for bad in ('', 'not a key!', 'JBSWY3DP', 'otpauth://hotp/x?secret=JBSWY3DPEHPK3PXPJBSWY3DPEHPK3PXP&counter=1',
                    'otpauth://totp/x?secret=JBSWY3DPEHPK3PXPJBSWY3DPEHPK3PXP&algorithm=MD5',
                    'otpauth://totp/x?secret=JBSWY3DPEHPK3PXPJBSWY3DPEHPK3PXP&digits=4'):
            with self.assertRaises(totp.BadKey, msg=bad): totp.parse(bad)


class CodePage(FakePage):
    """A stand-in tab that asks a code: after the password (otp_after), or straight away (otp)."""
    def __init__(self, otp=False, otp_after=False, **kw):
        super().__init__(**kw); self.otp, self.otp_after = otp, otp_after
    def fields(self, want=''):
        f = super().fields(want)
        if want == 'otp': f['focused'] = self.otp
        return {**f, 'otp': self.otp}
    def enter(self):
        super().enter()
        if self.otp_after and self.focus == 'password': self.pw, self.user, self.otp = False, False, True


class Typing(unittest.TestCase):
    def setUp(self): self.p = mock.patch.object(signin.time, 'sleep'); self.p.start()
    def tearDown(self): self.p.stop()

    def test_the_code_follows_the_password_on_the_sites_next_page(self):
        p = CodePage(otp_after=True)
        out = signin.fill_page(p, 'bank.example', USER, PW, code=lambda: '123456', code_wait=5)
        self.assertEqual(out, {'code': True})
        self.assertEqual(p.typed, [('user', USER), ('password', PW), ('password', '<enter>'), ('otp', '123456'), ('otp', '<enter>')])

    def test_a_code_prompt_alone_gets_the_code_alone(self):
        p = CodePage(otp=True, password=False, user=False)
        self.assertEqual(signin.fill_page(p, 'bank.example', USER, PW, code=lambda: '654321'), {'code': True})
        self.assertEqual(p.typed, [('otp', '654321'), ('otp', '<enter>')])

    def test_no_prompt_no_code_and_no_failure(self):
        p = CodePage()
        with mock.patch.object(signin.time, 'time', side_effect=[0, 0, 1, 99, 99]):
            out = signin.fill_page(p, 'bank.example', USER, PW, code=lambda: '111111', code_wait=5)
        self.assertEqual(out, {'code': False})
        self.assertNotIn('111111', [t for _, t in p.typed])

    def test_a_code_prompt_on_another_site_gets_nothing(self):
        p = CodePage(otp=True, password=False, user=False, href='https://bank-example.example/verify')
        with self.assertRaises(signin.SignInError): signin.fill_page(p, 'bank.example', USER, PW, code=lambda: '222222')
        self.assertEqual(p.typed, [])

    def test_a_code_in_its_last_seconds_is_waited_out(self):
        cfg = totp.parse(KEY)
        with mock.patch.object(totp, 'left', return_value=1.0), mock.patch.object(totp, 'code', return_value='333333'):
            self.assertEqual(signin._code_of(totp.dumps(cfg))(), '333333')
        signin.time.sleep.assert_called_once()


class Vaulted(unittest.TestCase):
    def setUp(self):
        self.s = MemoryStore(); self.tid = Factory(self.s).task('Pay the toll'); signin._TRIED.clear()
        self.logs = []; self.h = logger.add(lambda m: self.logs.append(str(m)), level='DEBUG')

    def tearDown(self): logger.remove(self.h)

    def written(self) -> str:
        rows = [self.s._rows(f'SELECT * FROM {t}') for t in ('audit', 'comment', 'worker_event', 'signin_token', 'signin_vault')]
        return json.dumps(rows, default=str) + '\n'.join(self.logs)

    def wait_for(self, pred, secs=5):
        end = time.time() + secs
        while time.time() < end and not pred(): time.sleep(.02)
        self.assertTrue(pred())

    def test_a_key_is_kept_sealed_only_with_a_saved_sign_in(self):
        self.assertFalse(signin.set_key(self.s, 'bank.example', KEY))                    # nothing saved: a key alone is kept for nothing
        signin.save(self.s, 'bank.example', USER, PW)
        self.assertTrue(signin.set_key(self.s, 'bank.example', URI))
        row = signin.saved(self.s, 'bank.example')
        self.assertTrue(vault.sealed(row['Totp']))
        self.assertEqual(totp.loads(vault.unseal(row['Totp']))['secret'], 'JBSWY3DPEHPK3PXPJBSWY3DPEHPK3PXP')
        self.assertEqual(signin.listing(self.s)[0]['code'], True)
        signin.save(self.s, 'bank.example', USER, 'a-new-password')                       # a changed password keeps the authenticator
        self.assertTrue(signin.listing(self.s)[0]['code'])
        with self.assertRaises(totp.BadKey): signin.set_key(self.s, 'bank.example', 'nonsense')
        self.assertTrue(signin.set_key(self.s, 'bank.example', ''))
        self.assertFalse(signin.listing(self.s)[0]['code'])
        self.assertNotIn('JBSWY3DP', self.written())

    def test_the_server_types_the_code_and_says_so_without_it(self):
        signin.save(self.s, 'bank.example', USER, PW, key=KEY)
        typed = []
        def fill(sid, site, user, pw, code=None):
            typed.append((sid, site, user, pw, code())); return {'code': True}
        with on_page('https://login.bank.example/'): self.assertTrue(signin.needs(self.s, self.tid, 'sess1', fill=fill)['auto'])
        self.wait_for(lambda: any('authenticator code' in (r.get('Body') or r.get('Text') or '') for r in self.s._rows('SELECT * FROM comment')))
        self.assertEqual(typed[0][:4], ('sess1', 'bank.example', USER, PW))
        self.assertEqual(typed[0][4], totp.code(totp.parse(KEY)))
        audit = [json.loads(r['Detail']) for r in self.s._rows("SELECT * FROM audit WHERE Action='signin_fill'")]
        self.assertEqual(audit, [{'site': 'bank.example', 'how': 'vault', 'ok': True, 'code': True}])
        w = self.written()
        self.assertNotIn(PW, w); self.assertNotIn('JBSWY3DP', w); self.assertNotIn(typed[0][4], w)

    def test_the_fill_page_takes_a_key_and_keeps_it_when_ticked(self):
        self.assertIn('name="key" type="password"', signin.form_html('bank.example', 15))
        with on_page('https://login.bank.example/'): signin.needs(self.s, self.tid, 'sess1')
        tok = signin.link(self.s, self.tid)['url'].rsplit('/', 1)[1]
        with self.assertRaises(totp.BadKey): signin.by_owner(self.s, tok, USER, PW, True, fill=lambda *a, **k: None, key='nope')
        self.assertIsNotNone(signin.peek(self.s, tok))                                    # a mistyped key did not spend the link
        got = []
        out = signin.by_owner(self.s, tok, USER, PW, True, fill=lambda *a, code=None: got.append(code()) or {'code': True}, key=KEY)
        self.assertTrue(out['saved'])
        self.assertEqual(got, [totp.code(totp.parse(KEY))])
        self.assertTrue(signin.listing(self.s)[0]['code'])
        self.assertNotIn('JBSWY3DP', self.written())

    def test_remove_forgets_the_key_too(self):
        signin.save(self.s, 'bank.example', USER, PW, key=KEY)
        with mock.patch.object(vault, 'forget') as forgot, mock.patch('taskuary.browserview.forget_site', return_value=0), \
                mock.patch.object(signin, '_forget_live'):
            signin.remove(self.s, 'bank.example')
        self.assertEqual(len(forgot.call_args_list), 3)


class Routes(unittest.TestCase):
    def tearDown(self):                     # the app's store is shared with test_signin's routes, which count what it lists
        with mock.patch('taskuary.browserview.forget_site', return_value=0), mock.patch.object(signin, '_forget_live'):
            signin.remove(server.store, 'toll.example')

    def test_settings_keeps_and_drops_a_key_and_never_reads_it_back(self):
        s = server.store
        signin.save(s, 'toll.example', USER, PW)
        self.assertEqual(c.post('/api/signins/toll.example/code', json={'key': 'nope'}).status_code, 400)
        self.assertEqual(c.post('/api/signins/nowhere.example/code', json={'key': KEY}).status_code, 404)
        r = c.post('/api/signins/toll.example/code', json={'key': KEY}); self.assertEqual(r.status_code, 200, r.text)
        rows = c.get('/api/signins').json()['data']
        self.assertEqual([x['code'] for x in rows if x['site'] == 'toll.example'], [True])
        self.assertNotIn('JBSWY3DP', json.dumps(rows))
        self.assertEqual(c.post('/api/signins/toll.example/code', json={'key': KEY}, headers=AGENT).status_code, 403)
        self.assertEqual(c.post('/api/signins/toll.example/code', json={'key': ''}).status_code, 200)
        self.assertEqual([x['code'] for x in c.get('/api/signins').json()['data'] if x['site'] == 'toll.example'], [False])

    def test_a_mistyped_key_on_the_fill_page_is_said_there(self):
        s = server.store; tid = Factory(s).task('Pay the toll'); signin._TRIED.clear()
        with on_page('https://login.bank.example/'): signin.needs(s, tid, f'route-{tid}')
        url = c.post(f'/api/tasks/{tid}/signin/link').json()['url']
        with mock.patch.object(signin, 'type_in') as typed:
            r = c.post(url, data={'username': USER, 'password': PW, 'key': 'nope'})
            self.assertEqual(r.status_code, 400)
            self.assertIn('authenticator key', r.text)
            typed.assert_not_called()
            self.assertEqual(c.get(url).status_code, 200)                              # still good: fix the key and press again


if __name__ == '__main__': unittest.main()
