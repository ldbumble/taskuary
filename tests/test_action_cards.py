"""Each connector declares what its act's card looks like (the owner, 2026-11-05: "each connector should have settings what the action
view looks like no?"): the catalogue names the fields a card shows, which the owner may change before the press, which the agent may name,
and the per-connection defaults; one card draws them. LinkedIn end to end: the connection's defaults fill the agent's proposal, the owner's
change on the card is what goes, and "Save as draft" saves it in LinkedIn's draft state. LinkedIn's HTTP is stubbed - nothing leaves.
"""
import json, unittest
from unittest import mock
from fastapi.testclient import TestClient
from taskuary import config, connectorcatalog as cat, general, guard, linkedin, proposals, scopes, server, verdicts
from taskuary.reports import REGISTRY, card_of

c = TestClient(server.app)
SRV = config.load()['server']
TYPES = {'text', 'line', 'image', 'choice', 'people', 'files'}


def agent(tid): return {'X-Taskuary-Token': SRV['agent_token'], guard.TASK_HDR: guard.task_proof(SRV, tid)}


class TheCatalogueDeclares(unittest.TestCase):
    def test_every_declared_act_is_well_formed(self):
        acts = [(card, a) for card in cat.cards() for a in card.get('actions') or []]
        self.assertGreaterEqual({card['type'] for card, _ in acts}, {'linkedin', 'bluesky', 'mastodon', 'outlook', 'gmail', 'teams', 'slack', 'jira'})
        for card, a in acts:
            self.assertIn(a['road'], ('run_tool', 'reply'), card['type'])
            self.assertTrue(a.get('press') and a.get('done') and a.get('undone'), card['type'])
            if a['road'] == 'run_tool':     # a run_tool card's tool is a real executor on this card, one whose call reaches somebody
                self.assertIn(a['tool'], REGISTRY); self.assertEqual(card_of(a['tool']), card['type']); self.assertIn(a['tool'], scopes.REACHES)
            for f in a['fields']:
                self.assertIn(f['type'], TYPES, f)
                if f['type'] == 'choice': self.assertIn(str(f.get('default')), [str(x['value']) for x in f['choices']], f)
                if f.get('setting'): self.assertEqual(f['type'], 'choice', f)   # a default is a pick, never words

    def test_linkedin_declares_audience_and_post_now_or_draft(self):
        a = cat.action_for('linkedin_post')
        self.assertEqual((a['card'], a['press']), ('linkedin', 'Post to LinkedIn'))
        self.assertEqual([f['key'] for f in a['fields']], ['text', 'image', 'visibility', 'publish'])
        self.assertEqual([x['label'] for x in cat.field(a, 'visibility')['choices']], ['Anyone', 'Connections only'])
        draft = next(x for x in cat.field(a, 'publish')['choices'] if x['value'] == 'draft')
        self.assertEqual(draft['press'], 'Save as draft')
        self.assertEqual(cat.text_key(cat.action_for('jira_comment')), 'body')
        self.assertIsNone(cat.action_for('sharepoint_save'))


class Defaults(unittest.TestCase):
    P = {'action': 'run_tool', 'type': 'linkedin_post', 'text': 'Hi'}

    def test_the_connections_default_fills_what_the_agent_left_out(self):
        self.assertEqual(cat.with_defaults(self.P, {})['visibility'], 'PUBLIC')             # the catalogue's
        got = cat.with_defaults(self.P, {'default_visibility': 'CONNECTIONS', 'default_publish': 'draft'})
        self.assertEqual((got['visibility'], got['publish']), ('CONNECTIONS', 'draft'))
        self.assertEqual(cat.with_defaults({**self.P, 'visibility': 'PUBLIC'}, {'default_visibility': 'CONNECTIONS'})['visibility'], 'PUBLIC')
        self.assertEqual(cat.with_defaults(self.P, {'default_visibility': 'EVERYONE'})['visibility'], 'PUBLIC')   # a stray value is no default

    def test_the_owner_changes_only_what_the_card_declares_editable(self):
        self.assertEqual(cat.owner_edits(self.P, {'visibility': 'CONNECTIONS'})['visibility'], 'CONNECTIONS')
        for bad in ({'connector_id': 9}, {'image': 'x.png'}, {'type': 'bluesky_post'}, {'visibility': 'EVERYONE'}):
            with self.assertRaises(ValueError): cat.owner_edits(self.P, bad)

    def test_a_tracker_comments_box_is_its_body(self):
        p = {'action': 'run_tool', 'type': 'jira_comment', 'item': 'NW-12', 'body': 'Done.'}
        self.assertEqual(proposals._edited(p, 'Done - the fix is out.')['body'], 'Done - the fix is out.')


class LinkedIn:
    "LinkedIn's HTTP, stubbed: every call recorded, none leaves the machine."
    def __init__(self): self.calls = []
    def get(self, url, **kw):
        self.calls.append(('GET', url)); return mock.Mock(ok=True, json=lambda: {'sub': 'ALEX1', 'name': 'Alex Doyle'})
    def post(self, url, **kw):
        self.calls.append(('POST', url, kw.get('json'))); return mock.Mock(ok=True, headers={'x-restli-id': 'urn:li:share:42'}, json=lambda: {})
    def posted(self): return [x[2] for x in self.calls if x[0] == 'POST' and x[1].endswith('/rest/posts')]


def stubbed(net): return mock.patch.multiple(linkedin.requests, get=net.get, post=net.post)


class TheExecutor(unittest.TestCase):
    def test_save_as_draft_is_linkedins_draft_state_with_no_feed_link(self):
        net = LinkedIn()
        with stubbed(net):
            out = linkedin.run_linkedin_post({'token': 't', 'text': 'Hi', 'author': 'urn:li:person:a', 'publish': 'draft', 'visibility': 'CONNECTIONS'})
        sent = net.posted()[0]
        self.assertEqual((sent['lifecycleState'], sent['visibility']), ('DRAFT', 'CONNECTIONS'))
        self.assertEqual((out['rows'][0]['url'], out['rows'][0]['publish']), ('', 'draft'))

    def test_post_now_is_published(self):
        net = LinkedIn()
        with stubbed(net): linkedin.run_linkedin_post({'token': 't', 'text': 'Hi', 'author': 'urn:li:person:a'})
        self.assertEqual(net.posted()[0]['lifecycleState'], 'PUBLISHED')
        with self.assertRaises(RuntimeError): linkedin.run_linkedin_post({'token': 't', 'text': 'Hi', 'author': 'a', 'publish': 'later'})


class OnePress(unittest.TestCase):
    def setUp(self):
        s = server.store
        self.tid = s.create_task({'Title': 'A post about the spring hiring fair', 'Kind': 'general', 'Status': 'open'}, 'owner')
        self.card = s.get_connector_by_type('linkedin')
        s.save_connector({'ConnectorId': self.card['ConnectorId'], 'Active': 1, 'Secret': 'tok', 'ConfigJson': json.dumps(
            {'member_name': 'Alex Doyle', 'default_visibility': 'CONNECTIONS', 'default_publish': 'draft'})}, 'linkedin')

    def tearDown(self): server.store.save_connector({'ConnectorId': self.card['ConnectorId'], 'Active': 0, 'ConfigJson': '{}'}, 'test')

    def propose(self, **kw):
        r = c.post('/api/agent/propose', headers=agent(self.tid), json={'task_id': self.tid, 'action': 'run_tool', 'type': 'linkedin_post',
                                                                         'connector_id': self.card['ConnectorId'], **kw})
        self.assertEqual(r.status_code, 200, r.text)
        return server.store.get_review(r.json()['review'])

    def test_defaults_fill_the_proposal_and_the_owners_change_is_what_goes(self):
        net = LinkedIn()
        with stubbed(net):
            rv = self.propose(text='Northwind is at the spring hiring fair on Friday.')
            p = json.loads(rv['DraftText'])
            self.assertEqual((p['visibility'], p['publish']), ('CONNECTIONS', 'draft'))        # the connection's own defaults
            card = next(x for x in c.get(f'/api/tasks/{self.tid}/assistant').json()['cards'] if x['ReviewId'] == rv['ReviewId'])
            self.assertEqual((card['network'], card['as'], card['post']['publish']), ('LinkedIn', 'Alex Doyle', 'draft'))
            self.assertEqual(net.calls, [])                                                     # nothing reached LinkedIn before the press
            r = c.post(f"/api/reviews/{rv['ReviewId']}/decide", json={'verb': 'approve', 'final_text': 'See you Friday at the fair.',
                                                                      'fields': {'publish': 'now'}})
        self.assertTrue(r.json()['ok'], r.text)
        sent = net.posted()[0]
        self.assertEqual((sent['commentary'], sent['visibility'], sent['lifecycleState']), ('See you Friday at the fair.', 'CONNECTIONS', 'PUBLISHED'))
        kept = json.loads(server.store.get_review(rv['ReviewId'])['FinalText'])
        self.assertEqual((kept['publish'], kept['result']['url']), ('now', 'https://www.linkedin.com/feed/update/urn:li:share:42'))

    def test_a_change_the_card_does_not_offer_posts_nothing(self):
        net = LinkedIn()
        with stubbed(net):
            rv = self.propose(text='Hi')
            out = verdicts.decide(server.store, rv, 'approve', 'Hi', fields={'connector_id': 1})
        self.assertFalse(out['ok']); self.assertEqual(net.posted(), [])
        self.assertEqual(server.store.get_review(rv['ReviewId'])['Status'], 'pending')

    def test_a_choice_the_card_does_not_have_is_refused_when_proposed(self):
        r = c.post('/api/agent/propose', headers=agent(self.tid), json={'task_id': self.tid, 'action': 'run_tool', 'type': 'linkedin_post',
                                                                         'connector_id': self.card['ConnectorId'], 'text': 'Hi', 'visibility': 'EVERYONE'})
        self.assertEqual(r.status_code, 422, r.text)

    def test_the_prompt_says_which_fields_the_agent_may_name(self):
        r = general.roads(server.store)
        self.assertIn("linkedin_post - posts on LinkedIn under your name, with a picture; it takes `text`, `image`", r)
        self.assertIn("`publish` (now or draft) come from the owner's defaults", r)


if __name__ == '__main__':
    unittest.main()
