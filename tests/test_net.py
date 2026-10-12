"""The connectors' shared HTTP seam (taskuary/net.py): one pooled Session, (connect, read) timeouts so a
dead IPv6 route gives up in seconds, app-only Graph tokens kept until a minute before they expire, and
the Teams mailbox's object id looked up once rather than on every 30 s poll. Offline: the Session is
replaced by a recorder, so nothing here leaves the machine."""
import unittest
from datetime import datetime, timedelta
from unittest import mock
from taskuary import channels, messengers, net
from taskuary.store import MemoryStore

CFG = {'tenant_id': 'tid-1', 'client_id': 'cid-1'}


class R:
    def __init__(self, code=200, j=None, content=b''): self.status_code, self._j, self.content, self.text = code, j or {}, content, ''
    def json(self): return self._j
    def raise_for_status(self):
        if self.status_code >= 400: raise net.HTTPError(str(self.status_code))


class Recorder:
    """Stands in for the shared Session: answers by URL and keeps every call."""
    def __init__(self, answer): self.answer, self.calls = answer, []
    def request(self, method, url, **kw):
        self.calls.append((method, url, kw)); return self.answer(method, url, kw)


def _minted():
    n = [0]
    def answer(method, url, kw):
        if 'oauth2' in url: n[0] += 1; return R(200, {'access_token': f'T{n[0]}', 'expires_in': 3600})
        return R(200, {})
    return answer


class TokenCacheTests(unittest.TestCase):
    def test_reused_until_a_minute_before_expiry_then_minted_again(self):
        rec, now = Recorder(_minted()), [1000.0]
        with mock.patch.object(net, 'session', lambda: rec), mock.patch.object(net.time, 'time', lambda: now[0]):
            a = channels.graph_token(CFG, 'S')
            now[0] += 3000; b = channels.graph_token(CFG, 'S')       # well inside the hour
            now[0] += 541; c = channels.graph_token(CFG, 'S')        # 59 s left: too close, mint
        self.assertEqual((a, b, c), ('T1', 'T1', 'T2'))
        self.assertEqual(sum('oauth2' in u for _, u, _ in rec.calls), 2)

    def test_another_secret_or_tenant_never_shares_a_token(self):
        rec = Recorder(_minted())
        with mock.patch.object(net, 'session', lambda: rec):
            toks = {channels.graph_token(CFG, 'S'), channels.graph_token(CFG, 'S2'),
                    channels.graph_token({**CFG, 'tenant_id': 'tid-2'}, 'S')}
        self.assertEqual(len(toks), 3)

    def test_a_401_drops_the_cached_token(self):
        def answer(method, url, kw):
            if 'oauth2' in url: return R(200, {'access_token': f'T{len(rec.calls)}', 'expires_in': 3600})
            return R(401) if kw['headers']['Authorization'] == 'Bearer T1' else R(200)
        rec = Recorder(answer)
        with mock.patch.object(net, 'session', lambda: rec):
            tok = channels.graph_token(CFG, 'S')
            self.assertEqual(tok, 'T1')
            self.assertEqual(net.get(f'{channels.GRAPH}/users/x', headers={'Authorization': f'Bearer {tok}'}).status_code, 401)
            self.assertNotEqual(channels.graph_token(CFG, 'S'), 'T1')    # the next caller mints fresh

    def test_a_failed_mint_is_not_cached(self):
        rec = Recorder(lambda m, u, kw: R(400))
        with mock.patch.object(net, 'session', lambda: rec):
            for _ in range(2): self.assertRaises(RuntimeError, channels.graph_token, CFG, 'S')
        self.assertEqual(len(rec.calls), 2)


class TimeoutTests(unittest.TestCase):
    def test_a_number_becomes_connect_and_read(self):
        self.assertEqual(net.timeout(30), (net.CONNECT, 30))
        self.assertEqual(net.timeout((1, 2)), (1, 2))
        self.assertEqual(net.timeout(), (net.CONNECT, net.READ))

    def test_telegram_calls_carry_a_short_connect_timeout(self):
        rec = Recorder(lambda m, u, kw: R(200, {'ok': True, 'result': {'file_path': 'p/f.jpg'}}, content=b'x'))
        with mock.patch.object(net, 'session', lambda: rec):
            messengers.tg('TOKEN', 'getUpdates', offset=0)
            messengers._tg_file('TOKEN', {'file_id': 'f'}, 'voice.ogg')
        self.assertEqual([kw['timeout'] for _, _, kw in rec.calls], [(4, 30), (4, 30), (4, 60)])
        # getUpdates is a SHORT poll (no server-side timeout param), so a 30 s read never cuts a long poll short
        self.assertNotIn('timeout', rec.calls[0][2]['json'])

    def test_one_session_is_shared(self):
        self.assertIs(net.session(), net.session())


class TeamsUserLookupTests(unittest.TestCase):
    def test_the_mailbox_object_id_is_looked_up_once_across_polls(self):
        s, upn = MemoryStore(), 'alex@northwind.example'
        rec = Recorder(lambda m, u, kw: R(200, {'id': 'oid-alex'} if u.endswith(f'/users/{upn}') else {'value': []}))
        since = datetime.now() - timedelta(hours=1)
        with mock.patch.object(net, 'session', lambda: rec):
            for _ in range(3): channels.ingest_teams_chats(s, upn, 'tok', since)
            lookups = lambda: sum(u.endswith(f'/users/{upn}') for _, u, _ in rec.calls)
            self.assertEqual(lookups(), 1)
            self.assertEqual(sum('getAllMessages/delta' in u for _, u, _ in rec.calls), 3)     # the delta still runs every poll
            channels.ingest_teams_chats(s, 'erin@northwind.example', 'tok', since)            # another mailbox: its own lookup
            self.assertEqual(sum(u.endswith('/users/erin@northwind.example') for _, u, _ in rec.calls), 1)

    def test_a_failed_lookup_is_asked_again_next_poll(self):
        s, upn = MemoryStore(), 'alex@northwind.example'
        rec = Recorder(lambda m, u, kw: R(503) if u.endswith(f'/users/{upn}') else R(200, {'value': []}))
        with mock.patch.object(net, 'session', lambda: rec):
            for _ in range(2): channels.ingest_teams_chats(s, upn, 'tok', datetime.now() - timedelta(hours=1))
        self.assertEqual(sum(u.endswith(f'/users/{upn}') for _, u, _ in rec.calls), 2)
