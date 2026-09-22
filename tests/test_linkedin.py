"""LinkedIn publishes only on the owner's click.

The point of this file is the LADDER, not the HTTP. An agent reads untrusted mail; if it could
reach `linkedin_post` directly, a crafted email could put words on the owner's feed under their
own name. The card ships at `read` and the post is a `write`, so the only road is a proposal.
"""
import unittest
from unittest import mock

from taskuary import linkedin, scopes
from taskuary.reports import CARD_OF, REGISTRY


class TheLadder(unittest.TestCase):
    def test_a_post_is_a_write_on_a_card_that_ships_at_read(self):
        self.assertEqual(scopes.ACTIONS['linkedin_post'], 'write')
        self.assertEqual(scopes.ACTIONS['linkedin_me'], 'read')
        self.assertEqual(scopes.DEFAULT_SCOPE['linkedin'], 'read')

    def test_the_card_at_its_default_scope_refuses_to_publish(self):
        card = {'Type': 'linkedin', 'Scope': scopes.DEFAULT_SCOPE['linkedin']}
        scopes.require(card, 'linkedin_me')                      # reading is fine
        with self.assertRaises(PermissionError):
            scopes.require(card, 'linkedin_post')                # publishing is not

    def test_both_executors_resolve_to_the_card(self):
        for t in ('linkedin_me', 'linkedin_post'):
            self.assertIn(t, REGISTRY)
            self.assertEqual(CARD_OF[t], 'linkedin')


class TheCall(unittest.TestCase):
    def test_a_post_needs_text_and_is_capped(self):
        with self.assertRaises(RuntimeError):
            linkedin.run_linkedin_post({'token': 't', 'text': '   '})
        with self.assertRaises(RuntimeError):
            linkedin.run_linkedin_post({'token': 't', 'text': 'x' * 3001, 'author': 'urn:li:person:a'})

    def test_no_token_says_where_to_get_one(self):
        with self.assertRaises(RuntimeError) as e:
            linkedin.whoami({})
        self.assertIn('token generator', str(e.exception))

    def test_it_resolves_the_author_urn_itself(self):
        """Nobody can paste urn:li:person:<opaque> from memory, so the post fetches it."""
        with mock.patch.object(linkedin.requests, 'get') as get, \
             mock.patch.object(linkedin.requests, 'post') as post:
            get.return_value = mock.Mock(ok=True, json=lambda: {'sub': 'ABC123', 'name': 'A Person'})
            post.return_value = mock.Mock(ok=True, headers={'x-restli-id': 'urn:li:share:987'},
                                          json=lambda: {})
            out = linkedin.run_linkedin_post({'token': 't', 'text': 'hello'})
        sent = post.call_args.kwargs['json']
        self.assertEqual(sent['author'], 'urn:li:person:ABC123')
        self.assertEqual(sent['commentary'], 'hello')
        self.assertEqual(sent['visibility'], 'PUBLIC')
        self.assertEqual(sent['lifecycleState'], 'PUBLISHED')
        self.assertEqual(out['rows'][0]['id'], 'urn:li:share:987')

    def test_an_expired_token_says_so_rather_than_printing_401(self):
        with mock.patch.object(linkedin.requests, 'get') as get:
            get.return_value = mock.Mock(ok=False, status_code=401,
                                         json=lambda: {'message': 'Invalid access token'})
            with self.assertRaises(RuntimeError) as e:
                linkedin.whoami({'token': 'stale'})
        said = str(e.exception)
        self.assertIn('60 days', said)              # the actual cause, most of the time
        self.assertIn('Share on LinkedIn', said)    # ...and the other one

    def test_visibility_is_validated(self):
        with self.assertRaises(RuntimeError):
            linkedin.run_linkedin_post({'token': 't', 'text': 'hi', 'author': 'urn:li:person:a',
                                        'visibility': 'EVERYONE'})


if __name__ == '__main__':
    unittest.main()
