"""The handbook: on by default, written on close, and gated where it counts.

It shipped switched OFF and nobody noticed. `handbook.enabled()` reads the connector card when
one exists, and every card is seeded Active 0 - so on every install that ever ran, coder.wrap
skipped learn_from_session, `--learned` was refused and the Social tab could only hold what a
person typed. The docstring said "Default ON" the whole time.

The other half is who may write. An entry is not a note: handbook.block reads it into every later
agent's seed prompt, so it is a claim handed to every future session as company fact. scopes.py
calls that a WRITE, and until the card existed there was nothing for the ladder to hang on.
"""
import json
import unittest
from unittest import mock

from fastapi.testclient import TestClient

from taskuary import config, handbook, scopes, server
from taskuary.store import MemoryStore

c = TestClient(server.app)
AGENT = {'X-Taskuary-Token': config.load()['server']['agent_token']}


class OnByDefault(unittest.TestCase):
    def test_a_fresh_install_has_the_handbook_on(self):
        """The seeded card is Active, so the feature its docstring promises is the one you get."""
        s = MemoryStore()
        self.assertTrue(handbook.enabled(s))

    def test_turning_the_card_off_turns_it_off(self):
        s = MemoryStore()
        card = s.get_connector_by_type('handbook')
        self.assertIsNotNone(card, 'the handbook needs a card for its switch to exist')
        s.save_connector({'ConnectorId': card['ConnectorId'], 'Active': 0}, 'owner')
        self.assertFalse(handbook.enabled(s))

    def test_the_card_defaults_to_write_authority(self):
        """A handbook only agents may read is a handbook nobody writes - but it stays on the
        ladder, so an owner who wants them hands-off can drop it to read."""
        s = MemoryStore()
        self.assertEqual(scopes.scope_of(s.get_connector_by_type('handbook')), 'write')
        self.assertTrue(scopes.allows(s.get_connector_by_type('handbook'), 'handbook_write'))


class WrittenOnClose(unittest.TestCase):
    """coder.wrap asks the transcript one question that is not about the task."""

    def _llm(self, payload):
        return lambda system, user, **kw: json.dumps(payload)

    def test_a_lasting_fact_is_filed(self):
        s = MemoryStore()
        tid = s.create_task({'Title': 'fix the export', 'Kind': 'coding'}, 'o')
        out = handbook.learn_from_session(
            s, tid, 'ran the tests; they need pyodbc installed first', 'coder',
            llm=self._llm({'entries': [{'title': 'The tests need pyodbc installed first',
                                        'topic': 'taskuary', 'kind': 'gotcha', 'body': 'pip install pyodbc'}]}))
        self.assertEqual(len(out), 1)
        self.assertEqual(out[0]['Title'], 'The tests need pyodbc installed first')
        self.assertEqual(out[0]['Kind'], 'gotcha')

    def test_nothing_is_the_usual_answer_and_is_accepted(self):
        s = MemoryStore()
        tid = s.create_task({'Title': 'x', 'Kind': 'coding'}, 'o')
        self.assertEqual(handbook.learn_from_session(s, tid, 'did the thing', 'coder',
                                                     llm=self._llm({'entries': []})), [])

    def test_a_broken_brain_never_stops_a_task_closing(self):
        """A handbook entry is a bonus. A session that finished must still close."""
        s = MemoryStore()
        tid = s.create_task({'Title': 'x', 'Kind': 'coding'}, 'o')
        def boom(system, user, **kw): raise RuntimeError('no brain')
        self.assertEqual(handbook.learn_from_session(s, tid, 'transcript', 'coder', llm=boom), [])

    def test_an_empty_transcript_asks_nothing(self):
        s = MemoryStore()
        tid = s.create_task({'Title': 'x', 'Kind': 'coding'}, 'o')
        called = []
        handbook.learn_from_session(s, tid, '   ', 'coder', llm=lambda *a, **k: called.append(1))
        self.assertEqual(called, [])


class WhoMayWrite(unittest.TestCase):
    """POST /api/handbook is the same act as the handbook_write tool, through another door."""

    def test_the_owner_writes_whatever_the_authority_says(self):
        """The ladder measures AGENTS. The owner typing on the Social tab is the person it
        protects, not a caller to check."""
        card = server.store.get_connector_by_type('handbook')
        server.store.save_connector({'ConnectorId': card['ConnectorId'], 'Scope': 'read', 'Active': 1}, 'owner')
        try:
            r = c.post('/api/handbook', json={'title': 'the owner may always write'})
            self.assertEqual(r.status_code, 200, r.text)
        finally:
            server.store.save_connector({'ConnectorId': card['ConnectorId'], 'Scope': '', 'Active': 1}, 'owner')

    def test_an_agent_is_refused_below_write(self):
        card = server.store.get_connector_by_type('handbook')
        server.store.save_connector({'ConnectorId': card['ConnectorId'], 'Scope': 'read', 'Active': 1}, 'owner')
        try:
            r = c.post('/api/handbook', json={'title': 'an agent should not get this in'}, headers=AGENT)
            self.assertEqual(r.status_code, 403)
            self.assertIn('authority', r.json()['detail'].lower())
        finally:
            server.store.save_connector({'ConnectorId': card['ConnectorId'], 'Scope': '', 'Active': 1}, 'owner')

    def test_an_agent_may_write_at_the_default(self):
        self.assertEqual(c.post('/api/handbook', json={'title': 'agents fill this by design'},
                                headers=AGENT).status_code, 200)

    def test_nobody_writes_while_the_card_is_off(self):
        with mock.patch('taskuary.handbook.enabled', return_value=False):
            r = c.post('/api/handbook', json={'title': 'not while it is off'})
            self.assertEqual(r.status_code, 403)
            self.assertIn('off', r.json()['detail'])


if __name__ == '__main__':
    unittest.main()


class VotedOn(unittest.TestCase):
    """Social is a forum: one vote per voter, the score ranks what agents are handed, and below
    zero a post is off the shelf - kept, restorable, never deleted (the owner, 2026-09-01)."""

    def test_one_vote_per_voter_and_the_second_press_does_not_stack(self):
        s = MemoryStore()
        p = handbook.post(s, 'The census lives in the old view', 'not the new one', 'census', 'gotcha', 'coder')
        handbook.vote(s, p['LoreId'], 1, 'coder'); handbook.vote(s, p['LoreId'], 1, 'coder')
        self.assertEqual(s.lore_get(p['LoreId'])['Score'], 1)
        handbook.vote(s, p['LoreId'], 1, 'codex')
        self.assertEqual(s.lore_get(p['LoreId'])['Score'], 2)
        handbook.vote(s, p['LoreId'], -1, 'codex')                      # flipped, not added
        self.assertEqual(s.lore_get(p['LoreId'])['Score'], 0)

    def test_below_zero_it_leaves_social_and_the_seed_prompt_and_an_upvote_brings_it_back(self):
        s = MemoryStore()
        p = handbook.post(s, 'The nightly export runs at 2am', '', 'census', 'system', 'coder')
        self.assertIn('nightly export', handbook.block(s, 'when does the nightly export run'))
        out = handbook.vote(s, p['LoreId'], -1, 'owner')
        self.assertEqual(out['Status'], 'downvoted')
        self.assertEqual(handbook.block(s, 'when does the nightly export run'), '')
        self.assertEqual([r['LoreId'] for r in s.lore_posts(status='removed')], [p['LoreId']])
        handbook.vote(s, p['LoreId'], 1, 'codex')                       # the room disagrees: back to zero
        self.assertEqual(s.lore_get(p['LoreId'])['Status'], 'live')

    def test_saying_what_is_already_there_is_an_upvote_not_a_second_post(self):
        s = MemoryStore()
        first = handbook.post(s, 'Adjustment rows take the first line date, not the batch date', 'so they post to the wrong month', 'payroll', 'gotcha', 'coder')
        again = handbook.post(s, 'Adjustment rows take the first line date rather than the batch date', 'check the batch header', 'payroll', 'gotcha', 'codex')
        self.assertTrue(again['merged'])
        self.assertEqual(again['LoreId'], first['LoreId'])
        self.assertEqual(again['Score'], 1)
        self.assertEqual(s.lore_count()['posts'], 1)
        self.assertEqual([c['Body'] for c in s.lore_comments(first['LoreId'])], ['check the batch header'])
        # a different fact on the same shelf is its own post
        other = handbook.post(s, 'Payroll closes on the first Wednesday', '', 'payroll', 'decision', 'coder')
        self.assertFalse(other['merged'])

    def test_a_post_is_a_line_not_a_report(self):
        s = MemoryStore()
        with self.assertRaises(ValueError): handbook.post(s, 'x' * 141, '', 'payroll')
        with self.assertRaises(ValueError): handbook.post(s, 'short', 'y' * 701, 'payroll')
        clipped = handbook.post(s, 'x' * 141, 'y' * 701, 'payroll', clip=True)   # the on-close road shortens instead
        self.assertEqual((len(clipped['Title']), len(clipped['Body'])), (140, 700))

    def test_the_seed_block_names_each_entry_so_an_agent_can_vote_on_it(self):
        s = MemoryStore()
        p = handbook.post(s, 'The AP importer needs pyodbc before its tests mean anything', '', 'importers', 'gotcha', 'coder')
        blk = handbook.block(s, 'run the AP importer tests')
        self.assertIn(f"#{p['LoreId']} [importers] (+0)", blk)
        self.assertIn('--upvote <id>', blk)
