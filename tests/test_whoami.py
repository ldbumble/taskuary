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
