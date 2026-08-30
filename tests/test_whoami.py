"""About you (whoami.py + /api/whoami): every identity a connector learned, with its provenance,
the manual facts, what the agents are told, and a deterministic avatar."""
import json, unittest
from unittest import mock
from fastapi.testclient import TestClient
from taskuary import server, whoami
from taskuary.store import MemoryStore

c_api = TestClient(server.app)


class ProfileTests(unittest.TestCase):
    def test_identities_come_with_where_they_were_learned(self):
        s = MemoryStore()
        s.set_setting('owner_name', 'Uri Nussbaum', 't'); s.set_setting('owner_email', 'uri@mfaheritage.net', 't')
        o = s.get_connector_by_type('outlook')
        s.save_connector({'ConnectorId': o['ConnectorId'], 'Active': 1, 'Secret': 'RT',
                          'ConfigJson': json.dumps({'auth': 'user', 'account': 'uri@theacropora.com', 'name': 'Josh Nussbaum'})}, 't')
        s.save_source({'Channel': 'email', 'Address': 'uri@theacropora.com', 'ConnectorId': o['ConnectorId'], 'Active': 1}, 't')
        s.save_source({'Channel': 'teams', 'Address': 'unussbaum@mfaheritage.net', 'ConnectorId': s.get_connector_by_type('teams')['ConnectorId'], 'Active': 1}, 't')
        tg = s.get_connector_by_type('telegram')
        s.save_connector({'ConnectorId': tg['ConnectorId'], 'ConfigJson': json.dumps({'notify_chat': '777'})}, 't')
        s.set_setting('owner_phone', '+1 555 0100', 't')
        p = whoami.profile(s)
        by = {(i['channel'], i['kind']): i for i in p['identities']}
        self.assertEqual(by[('email', 'address')]['value'], 'uri@mfaheritage.net'); self.assertTrue(by[('email', 'address')]['primary'])
        self.assertEqual((by[('email', 'Microsoft account')]['value'], by[('email', 'Microsoft account')]['name']), ('uri@theacropora.com', 'Josh Nussbaum'))
        self.assertIn('Sign in with Microsoft', by[('email', 'Microsoft account')]['source'])
        self.assertEqual(by[('teams', 'UPN')]['value'], 'unussbaum@mfaheritage.net')
        self.assertEqual(by[('telegram', 'your chat id')]['value'], '777'); self.assertIn('notify chat', by[('telegram', 'your chat id')]['source'])
        self.assertEqual(by[('whatsapp', 'phone')]['source'], 'you typed it here')
        self.assertEqual(p['facts']['owner_name'], 'Uri Nussbaum'); self.assertTrue(p['avatar'].startswith('<svg'))
        self.assertIn('UN', p['avatar'])                                       # the monogram: first and last initials

    def test_the_paired_whatsapp_number_the_bot_and_the_pat_login_come_from_the_cards(self):
        """These three were never recorded anywhere: the bridge knows the paired number, Test knows
        the bot, discovery knows the PAT's login - so the page read as if the connectors knew nothing."""
        s = MemoryStore()
        wa = s.get_connector_by_type('whatsapp'); s.save_connector({'ConnectorId': wa['ConnectorId'], 'Active': 1}, 't')
        s.save_connector({'ConnectorId': s.get_connector_by_type('telegram')['ConnectorId'], 'ConfigJson': json.dumps({'bot_username': 'uri_hub_bot'})}, 't')
        s.save_connector({'ConnectorId': s.get_connector_by_type('github')['ConnectorId'], 'ConfigJson': json.dumps({'login': 'ldbumble'})}, 't')
        from taskuary import messengers
        with mock.patch.object(messengers, 'wa_status', return_value={'connected': True, 'me': 'Uri', 'jid': '15550100200:12@s.whatsapp.net', 'phone': '+15550100200'}):
            by = {(i['channel'], i['kind']): i for i in whoami.profile(s)['identities']}
        self.assertEqual((by[('whatsapp', 'your number')]['value'], by[('whatsapp', 'your number')]['name']), ('+15550100200', 'Uri'))
        self.assertEqual(by[('telegram', 'your bot')]['value'], '@uri_hub_bot')
        self.assertEqual(by[('github', 'login')]['value'], 'ldbumble')
        with mock.patch.object(messengers, 'wa_status', side_effect=RuntimeError('bridge down')):
            self.assertNotIn(('whatsapp', 'your number'), {(i['channel'], i['kind']) for i in whoami.profile(s)['identities']})   # absent, not an error
        # the bridge's jid becomes a phone in wa_status itself
        with mock.patch.object(messengers, '_wa', lambda c_, p, body=None: {'connected': True, 'me': 'Uri', 'jid': '15550100200:12@s.whatsapp.net', 'qr': '', 'pairingCode': ''}):
            self.assertEqual(messengers.wa_status(wa)['phone'], '+15550100200')

    def test_a_card_set_up_before_discover_and_test_learns_its_login_on_first_look(self):
        """The GitHub login and the Telegram bot were saved only by Discover / Test; a card connected
        earlier had neither, and the page read as if the connectors knew nothing about the owner."""
        s = MemoryStore()
        gh, tg = s.get_connector_by_type('github'), s.get_connector_by_type('telegram')
        s.save_connector({'ConnectorId': gh['ConnectorId'], 'Active': 1, 'Secret': 'ghp_x'}, 't')
        s.save_connector({'ConnectorId': tg['ConnectorId'], 'Active': 1, 'Secret': '123:abc'}, 't')
        fake = mock.Mock(); fake.json.return_value = {'login': 'ldbumble'}; fake.raise_for_status = lambda: None
        with mock.patch('requests.get', return_value=fake) as g, mock.patch('taskuary.messengers.tg', return_value={'username': 'uri_hub_bot'}):
            by = {(i['channel'], i['kind']): i for i in whoami.profile(s)['identities']}
        self.assertEqual(by[('github', 'login')]['value'], 'ldbumble'); self.assertEqual(by[('telegram', 'your bot')]['value'], '@uri_hub_bot')
        self.assertEqual(json.loads(s.get_connector(gh['ConnectorId'])['ConfigJson'])['login'], 'ldbumble')        # saved on the card: one call, ever
        with mock.patch('requests.get', side_effect=AssertionError('must not be called again')):
            self.assertEqual({(i['channel'], i['kind']): i for i in whoami.profile(s)['identities']}[('github', 'login')]['value'], 'ldbumble')

    def test_a_bridge_running_old_code_says_so_instead_of_showing_nothing(self):
        s = MemoryStore()
        wa = s.get_connector_by_type('whatsapp'); s.save_connector({'ConnectorId': wa['ConnectorId'], 'Active': 1}, 't')
        from taskuary import messengers
        with mock.patch.object(messengers, 'wa_status', return_value={'connected': True, 'me': 'Uri', 'jid': '', 'phone': ''}):
            row = {(i['channel'], i['kind']): i for i in whoami.profile(s)['identities']}[('whatsapp', 'your number')]
        self.assertIn('restart the bridge', row['value']); self.assertIn('older code', row['source'])

    def test_the_avatar_is_deterministic_and_every_style_renders(self):
        a, b = whoami.avatar_svg('Uri Nussbaum', 'seed-1'), whoami.avatar_svg('Uri Nussbaum', 'seed-1')
        self.assertEqual(a, b); self.assertNotEqual(a, whoami.avatar_svg('Uri Nussbaum', 'seed-2'))
        for st in whoami.STYLES:
            svg = whoami.avatar_svg('Uri Nussbaum', 'x', st)
            self.assertTrue(svg.startswith('<svg') and svg.endswith('</svg>'), st)
        self.assertEqual(whoami.initials('Uri J Nussbaum'), 'UN'); self.assertEqual(whoami.initials(''), 'T')

    def test_save_is_whitelisted_and_name_email_go_through_the_owner_route(self):
        s = MemoryStore()
        out = whoami.save(s, {'owner_phone': ' +1 555 0100 ', 'owner_avatar_style': 'rings'})
        self.assertEqual((out['facts']['owner_phone'], out['facts']['owner_avatar_style']), ('+1 555 0100', 'rings'))
        with self.assertRaises(ValueError): whoami.save(s, {'triage_ai': 'x'})
        with self.assertRaises(ValueError): whoami.save(s, {'owner_name': 'x'})
        with self.assertRaises(ValueError): whoami.save(s, {'owner_avatar_style': 'neon'})


class EndpointTests(unittest.TestCase):
    def test_the_page_reads_saves_and_previews(self):
        r = c_api.get('/api/whoami').json()
        self.assertIn('identities', r); self.assertIn('told_to_agents', r); self.assertEqual(r['styles'], list(whoami.STYLES))
        r = c_api.patch('/api/whoami', json={'owner_telegram': '@uri'}).json()
        self.assertEqual(r['facts']['owner_telegram'], '@uri')
        self.assertEqual(c_api.patch('/api/whoami', json={'coder_auto_enabled': '0'}).status_code, 422)   # never a back door into settings
        pv = c_api.get('/api/whoami/avatar', params={'style': 'grid', 'seed': 'abc'}).json()
        self.assertTrue(pv['svg'].startswith('<svg')); self.assertEqual((pv['style'], pv['seed']), ('grid', 'abc'))
        self.assertEqual(c_api.get('/api/whoami/avatar', params={'style': 'neon'}).status_code, 422)
