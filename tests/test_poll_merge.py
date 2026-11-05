"""A POLL NEVER ROLLS BACK AN OWNER'S EDIT (the owner, 2026-11-05: every field on a card saves itself; #242).

Every poller, test and sign-in that keeps state on a card - a watermark, who the token is, the workspace it reaches, a refresh token -
read the card, went out to the service, and wrote the WHOLE config it had read back with its own key on top. A field the owner saved
while it was out (the card autosaves on every pause in the typing) was put back the way it was. Each now merges only its own keys over
the card as it is when it writes (store.merge_connector_config). Each test lands an owner field save in exactly that window - inside the
faked network call, or between the store read and the write - and checks both survive. Nothing here reaches a real service."""
import json, unittest
from unittest import mock

from taskuary import aidefaults, channels, fileaccess, googlecal, messengers, pm, remote_assistant, signatures, whoami
from taskuary.store import MemoryStore

OWNER = {'poll_seconds': 45}          # a field the owner saves on the card mid-poll (what POST /api/connectors merges)


class R:
    def __init__(self, j=None, status=200): self.status_code, self._j, self.text = status, j or {}, json.dumps(j or {})
    def json(self): return self._j
    def raise_for_status(self): pass


class Race(unittest.TestCase):
    def setUp(self): self.s = MemoryStore()

    def card(self, typ, cfg=None, secret='tok'):
        cid = self.s.get_connector_by_type(typ)['ConnectorId']
        self.s.save_connector({'ConnectorId': cid, 'Active': 1, 'Secret': secret, 'ConfigJson': json.dumps({'kept': 'yes', **(cfg or {})})}, 'test')
        return cid, self.s.get_connector(cid, with_secret=True)

    def owner_saves(self, cid): self.s.merge_config('connector', cid, OWNER)

    def cfg(self, cid): return json.loads(self.s.get_connector(cid, with_secret=True)['ConfigJson'] or '{}')

    def survived(self, cid, **theirs):
        cfg = self.cfg(cid)
        self.assertEqual(cfg.get('poll_seconds'), 45, f"the owner's save was rolled back: {cfg}")
        self.assertEqual(cfg.get('kept'), 'yes')
        for k, v in theirs.items(): self.assertEqual(cfg.get(k), v, f'{k}: {cfg}')

    # ── the pollers' watermarks ──
    def test_telegram_poll_offset(self):
        cid, c = self.card('telegram')
        self.s.save_source({'Channel': 'telegram', 'Address': '*', 'ConnectorId': cid, 'Active': 1}, 'test')
        def tg(tok, method, **p):
            self.owner_saves(cid)
            return [{'update_id': 300, 'message': {'message_id': 1, 'date': 1755700000, 'chat': {'id': 5, 'type': 'private'}, 'text': 'hi'}}]
        with mock.patch.object(messengers, 'tg', tg): messengers.poll_telegram(self.s, c, self.s.list_sources(), llm=None)
        self.survived(cid, tg_offset=301)

    def test_whatsapp_poll_sequence(self):
        cid, c = self.card('whatsapp', secret=None)
        self.s.save_source({'Channel': 'whatsapp', 'Address': '155@s.whatsapp.net', 'ConnectorId': cid, 'Active': 1}, 'test')
        def wa(c_, p, body=None):
            self.owner_saves(cid)
            return {'seq': 9, 'boot': 'b1', 'messages': []}
        with mock.patch.object(messengers, '_wa', wa): messengers.poll_whatsapp(self.s, c, self.s.list_sources(), llm=None)
        self.survived(cid, wa_seq=9, wa_boot='b1')

    def test_imessage_poll_cursor(self):
        from taskuary import imessage
        cid, c = self.card('imessage', secret=None)
        self.s.save_source({'Channel': 'imessage', 'Address': '*', 'ConnectorId': cid, 'Active': 1}, 'test')
        db = mock.Mock(); db.execute.return_value.fetchone.return_value = (12, None)
        def opened(cfg): self.owner_saves(cid); return db, set()
        with mock.patch.object(imessage, 'open_db', opened): imessage.poll(self.s, c, self.s.list_sources())
        self.survived(cid, imessage_rowid=12)

    # ── what a Test learns about the token ──
    def test_telegram_test_bot_name(self):
        cid, c = self.card('telegram')
        with mock.patch.object(messengers, 'tg', lambda tok, m, **p: (self.owner_saves(cid), {'username': 'northwind_bot'})[1]):
            messengers.tg_test(self.s, c)
        self.survived(cid, bot_username='northwind_bot')

    def test_asana_workspace(self):
        cid, c = self.card('asana')
        def get(c_, path, **p):
            self.owner_saves(cid); return {'name': 'Alex', 'workspaces': [{'gid': '77', 'name': 'Northwind'}]}
        with mock.patch.object(pm, '_asana_get', get): pm.test_asana(self.s, c)
        self.survived(cid, workspace_gid='77')

    def test_monday_me(self):
        cid, c = self.card('monday')
        with mock.patch.object(pm, '_monday', lambda c_, q: (self.owner_saves(cid), {'me': {'id': 42, 'name': 'Alex'}})[1]):
            pm.test_monday(self.s, c)
        self.survived(cid, me_id='42')

    def test_clickup_me_and_workspace(self):
        cid, c = self.card('clickup')
        def cu(c_, path, **p):
            self.owner_saves(cid)
            return {'user': {'id': 183, 'username': 'alex'}} if path == '/user' else {'teams': [{'id': 512, 'name': 'Northwind'}]}
        with mock.patch.object(pm, '_clickup', cu): pm.test_clickup(self.s, c)
        self.survived(cid, user_id='183', team_id='512')

    def test_github_discover_login(self):
        cid, c = self.card('github')
        def get(url, **k): self.owner_saves(cid); return R({'login': 'alexd'})
        with mock.patch.object(channels.requests, 'get', get), \
             mock.patch.object(channels, 'list_accessible_repos', side_effect=RuntimeError('stop after the login')):
            with self.assertRaises(RuntimeError): channels.github_discover(self.s, c)
        self.survived(cid, login='alexd')

    def test_slack_own_workspace(self):
        cid, c = self.card('slack')
        with mock.patch.object(channels, '_slack', lambda tok, m, **p: (self.owner_saves(cid), {'team_id': 'T1', 'team': 'Northwind'})[1]):
            self.assertEqual(channels.slack_own_team(self.s, c, 'tok'), 'T1')
        self.survived(cid, team_id='T1', team_name='Northwind')

    def test_amazon_test_fills_its_dots(self):
        cid, _ = self.card('amazon_sp')
        from taskuary import amazon_sp
        with mock.patch.object(amazon_sp, 'connection', lambda store, i: {}), \
             mock.patch.object(amazon_sp, 'probe_apis', lambda conn: (self.owner_saves(cid), ('ok', ['orders']))[1]):
            channels.test_connector(self.s, cid)
        self.survived(cid, apis=['orders'])

    def test_who_am_i_learns_the_github_login(self):
        cid, c = self.card('github')
        with mock.patch('requests.get', lambda url, **k: (self.owner_saves(cid), R({'login': 'alexd'}))[1]):
            whoami._learn_github(self.s, dict(c))
        self.survived(cid, login='alexd')

    def test_who_am_i_learns_the_bot_name(self):
        cid, c = self.card('telegram')
        with mock.patch.object(messengers, 'tg', lambda tok, m, **p: (self.owner_saves(cid), {'username': 'northwind_bot'})[1]):
            whoami._learn_telegram(self.s, dict(c))
        self.survived(cid, bot_username='northwind_bot')

    # ── a Google sign-in finishing while the card was edited ──
    def test_google_calendar_sign_in(self):
        cid, _ = self.card('gmail', secret='app-pw')
        f = {'cid': cid, 'verifier': 'v', 'client': ('', '')}
        tok = R({'refresh_token': 'rt1', 'scope': googlecal.SCOPE})
        with mock.patch.object(googlecal.requests, 'post', lambda *a, **k: (self.owner_saves(cid), tok)[1]):
            ok, why = googlecal._exchange(self.s, {}, f, 'C', None)
        self.assertTrue(ok, why)
        self.survived(cid, google_refresh_token='rt1', google_scope=googlecal.SCOPE)

    def test_google_files_sign_in(self):
        cid, _ = self.card('gmail', secret='app-pw')
        fileaccess._STATES['st'] = {'cid': cid, 'verifier': 'v', 'on': True, 'at': __import__('time').time()}
        tok = R({'refresh_token': 'rt2', 'scope': fileaccess.DRIVE_FILE})
        with mock.patch.object(fileaccess.requests, 'post', lambda *a, **k: (self.owner_saves(cid), tok)[1]):
            ok, why = fileaccess.google_callback(self.s, {}, 'C', 'st')
        self.assertTrue(ok, why)
        self.survived(cid, google_refresh_token='rt2', allow_files=True)

    def test_microsoft_sign_in_finishing_minutes_after_it_started(self):
        from taskuary import msauth, server
        cid, c = self.card('outlook', secret=None)
        start = json.loads(c['ConfigJson'])
        f = {'cid': cid, 'kind': 'outlook', 'cfg': {**start, 'allow_files': True}, 'was': start, 'at': 0}
        self.owner_saves(cid)                                  # while the owner was in Microsoft's tab
        with mock.patch.object(server, 'store', self.s), mock.patch.object(msauth, 'me', return_value={'account': 'alex@northwind.example', 'name': 'Alex Doyle'}):
            server._ms_finish(cid, f, {'refresh_token': 'rt', 'access_token': 'at'})
        self.survived(cid, allow_files=True, account='alex@northwind.example', auth='user')


class StoreRace(unittest.TestCase):
    """The writers with no network call between their read and their write: the owner's save is landed on the store's first write."""
    def setUp(self):
        self.s, landed = MemoryStore(), []
        real = self.s.merge_connector_config
        def first_the_owner(cid, patch):
            if not landed: landed.append(cid); self.s.merge_config('connector', cid, OWNER)
            return real(cid, patch)
        self.s.merge_connector_config = first_the_owner
        self.s.set_connector_config = lambda cid, cfg: (first_the_owner(cid, {}), MemoryStore.set_connector_config(self.s, cid, cfg))

    def card(self, typ, cfg=None):
        cid = self.s.get_connector_by_type(typ)['ConnectorId']
        self.s.save_connector({'ConnectorId': cid, 'Active': 1, 'Secret': 'tok', 'ConfigJson': json.dumps({'kept': 'yes', **(cfg or {})})}, 'test')
        return cid

    def cfg(self, cid): return json.loads(self.s.get_connector(cid)['ConfigJson'])

    def test_phone_assistant_listening_and_chat(self):
        cid = self.card('telegram')
        remote_assistant.set_listens(self.s, 'telegram', 'always')
        with mock.patch.object(remote_assistant, 'candidates', lambda store, c: [{'to': '777'}]):
            remote_assistant.use_chat(self.s, 'telegram', '777')
        cfg = self.cfg(cid)
        self.assertEqual((cfg['poll_seconds'], cfg['kept'], cfg['assistant_listen'], cfg['assistant_chat']), (45, 'yes', 'always', '777'))

    def test_a_mailbox_signature(self):
        cid = self.card('imap')
        with mock.patch.object(signatures.outbound, '_box', lambda store, a: {'connector_id': cid, 'address': a}):
            signatures.save_mailbox(self.s, 'alex@northwind.example', 'Alex')
        cfg = self.cfg(cid)
        self.assertEqual((cfg['poll_seconds'], cfg['signatures']), (45, {'alex@northwind.example': 'Alex'}))

    def test_an_ai_cards_strong_model(self):
        cid = self.card('anthropic', {'model': 'claude-haiku-4-5'})
        with mock.patch.object(aidefaults, '_strong_home', lambda store, cfg, r: ('connector', cid)), \
             mock.patch.object(aidefaults, 'resolve', lambda store, cfg, k: {}):
            aidefaults.apply(self.s, {}, 'triage_ai', strong='claude-opus-5')
        cfg = self.cfg(cid)
        self.assertEqual((cfg['poll_seconds'], cfg['model'], cfg['strong_model']), (45, 'claude-haiku-4-5', 'claude-opus-5'))


class NoWholeConfigWriter(unittest.TestCase):
    def test_nothing_outside_the_store_writes_a_cards_whole_config_from_its_own_read(self):
        """The guard against the next one: set_connector_config is the store's own (and DraftStore's pass-through), and no module
        rebuilds a card's config with `{**cfg, ...}` to save it whole."""
        import pathlib, re
        bad = []
        for p in sorted(pathlib.Path(channels.__file__).parent.glob('*.py')):
            if p.name == 'store.py': continue
            for i, line in enumerate(p.read_text(encoding='utf-8').splitlines(), 1):
                if 'set_connector_config(' in line and 'def set_connector_config' not in line and 'self._store.set_connector_config' not in line:
                    bad.append(f'{p.name}:{i}')
                if re.search(r"save_connector\(\{[^}]*'ConfigJson': json\.dumps\(\{\*\*", line): bad.append(f'{p.name}:{i}')
        self.assertEqual(bad, [])


if __name__ == '__main__': unittest.main()
