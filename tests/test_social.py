"""Bluesky and Mastodon - the last two of the twenty-five.

Shaped like LinkedIn, not like a chat server: a public timeline is not an inbox, so nothing here
reaches the Timeline as work. Both are report sources and tools, both ship at authority `read`, and
the only verb that leaves the house is a post the owner approves.

The two differ in exactly one interesting way, and it is where the bugs are. Bluesky takes TWO
steps - an app password buys a session, and the `did` that session returns is the repo a post is
addressed to, so a post is impossible without having logged in. Mastodon takes ONE, but every
instance is its own server, so there is no host that is right for everybody.
"""
import json
import unittest
from unittest import mock

from taskuary import social
from taskuary.reports import CONNECTION_OF, REGISTRY, resolve_cfg
from taskuary.store import MemoryStore

TYPES = ('bluesky_me', 'bluesky_timeline', 'bluesky_post',
         'mastodon_me', 'mastodon_timeline', 'mastodon_post')


class _Resp:
    def __init__(self, payload=None, status=200, text=''):
        self._payload, self.status_code, self.text = payload, status, text or ''

    def json(self):
        if self._payload is None: raise ValueError('no json')
        return self._payload


SESSION = {'accessJwt': 'jwt-1', 'did': 'did:plc:abc', 'handle': 'alex.bsky.social'}


def _bsky_cfg(**kw):
    return {'handle': 'alex.bsky.social', 'app_password': 'abcd-efgh-ijkl-mnop', **kw}


class BlueskySignsInBeforeItCanDoAnything(unittest.TestCase):
    def setUp(self): social._SESSIONS.clear()

    def test_the_app_password_buys_a_session_not_a_bearer_token(self):
        with mock.patch.object(social.requests, 'post', return_value=_Resp(SESSION)) as post:
            jwt, did, handle = social.session(_bsky_cfg())
        self.assertEqual(post.call_args[0][0], 'https://bsky.social/xrpc/com.atproto.server.createSession')
        self.assertEqual(post.call_args.kwargs['json'],
                         {'identifier': 'alex.bsky.social', 'password': 'abcd-efgh-ijkl-mnop'})
        self.assertEqual((jwt, did, handle), ('jwt-1', 'did:plc:abc', 'alex.bsky.social'))

    def test_the_session_is_cached_per_card_not_re_bought_every_call(self):
        """createSession is rate-limited far harder than the read endpoints. A report that logs in
        on every run is a report that dies on a busy day."""
        with mock.patch.object(social.requests, 'post', return_value=_Resp(SESSION)) as post:
            social.session(_bsky_cfg(_cid=1))
            social.session(_bsky_cfg(_cid=1))
        self.assertEqual(post.call_count, 1)

    def test_two_accounts_on_one_install_do_not_share_a_login(self):
        with mock.patch.object(social.requests, 'post', return_value=_Resp(SESSION)) as post:
            social.session(_bsky_cfg(_cid=1))
            social.session(_bsky_cfg(_cid=2, handle='other.bsky.social'))
        self.assertEqual(post.call_count, 2)

    def test_a_leading_at_on_the_handle_is_forgiven(self):
        with mock.patch.object(social.requests, 'post', return_value=_Resp(SESSION)) as post:
            social.session(_bsky_cfg(handle='@alex.bsky.social'))
        self.assertEqual(post.call_args.kwargs['json']['identifier'], 'alex.bsky.social')

    def test_the_login_password_is_refused_with_the_fix_attached(self):
        """Bluesky says "App password" and little else. Most people try their real password first,
        and 'invalid identifier or password' does not tell them why it will never work."""
        with mock.patch.object(social.requests, 'post',
                               return_value=_Resp({'message': 'Invalid identifier or password'}, 401)):
            with self.assertRaises(RuntimeError) as e:
                social.session(_bsky_cfg())
        self.assertIn('APP PASSWORD', str(e.exception))

    def test_a_missing_handle_and_a_missing_password_each_say_which(self):
        with self.assertRaises(RuntimeError) as e:
            social.session({'app_password': 'x'})
        self.assertIn('handle', str(e.exception))
        with self.assertRaises(RuntimeError) as e:
            social.session({'handle': 'a.bsky.social'})
        self.assertIn('App passwords', str(e.exception))


class BlueskyReadsAndPosts(unittest.TestCase):
    def setUp(self): social._SESSIONS.clear()

    FEED = {'feed': [{'post': {'uri': 'at://did:plc:abc/app.bsky.feed.post/xyz',
                               'author': {'handle': 'erin.bsky.social'},
                               'record': {'text': 'shipping today', 'createdAt': '2026-09-22T10:00:00Z'},
                               'likeCount': 4, 'repostCount': 1, 'replyCount': 2}}]}

    def test_the_timeline_comes_back_as_rows_with_the_numbers_on_them(self):
        with mock.patch.object(social.requests, 'post', return_value=_Resp(SESSION)), \
             mock.patch.object(social.requests, 'request', return_value=_Resp(self.FEED)) as req:
            head, body = social.run_bluesky_timeline(_bsky_cfg())
        self.assertIn('app.bsky.feed.getTimeline', req.call_args[0][1])
        self.assertIn('1 posts', head)
        self.assertIn('shipping today', body)
        self.assertIn('erin.bsky.social', body)

    def test_naming_an_author_reads_that_account_instead(self):
        with mock.patch.object(social.requests, 'post', return_value=_Resp(SESSION)), \
             mock.patch.object(social.requests, 'request', return_value=_Resp(self.FEED)) as req:
            social.run_bluesky_timeline(_bsky_cfg(author='@erin.bsky.social'))
        self.assertIn('app.bsky.feed.getAuthorFeed', req.call_args[0][1])
        self.assertEqual(req.call_args.kwargs['params']['actor'], 'erin.bsky.social')

    def test_a_post_is_addressed_to_the_repo_the_session_named(self):
        """The did is not something a person can paste - it comes back from the sign-in, and a
        post addressed to the wrong repo is a post into somebody else's account."""
        with mock.patch.object(social.requests, 'post', return_value=_Resp(SESSION)), \
             mock.patch.object(social.requests, 'request',
                               return_value=_Resp({'uri': 'at://did:plc:abc/app.bsky.feed.post/k1'})) as req:
            out = social.run_bluesky_post(_bsky_cfg(text='hello world'))
        sent = req.call_args.kwargs['json']
        self.assertEqual(sent['repo'], 'did:plc:abc')
        self.assertEqual(sent['collection'], 'app.bsky.feed.post')
        self.assertEqual(sent['record']['text'], 'hello world')
        self.assertTrue(sent['record']['createdAt'].endswith('Z'))
        self.assertEqual(out['rows'][0]['url'], 'https://bsky.app/profile/alex.bsky.social/post/k1')

    def test_an_over_long_post_is_refused_before_the_call(self):
        """A post refused for length is one the owner already approved, so the refusal has to
        happen here rather than as a 400 nobody sees."""
        with self.assertRaises(RuntimeError) as e:
            social.run_bluesky_post(_bsky_cfg(text='x' * 301))
        self.assertIn('300 characters', str(e.exception))
        self.assertIn('301', str(e.exception))

    def test_an_empty_post_is_refused(self):
        with self.assertRaises(RuntimeError) as e:
            social.run_bluesky_post(_bsky_cfg(text='   '))
        self.assertIn('needs `text`', str(e.exception))


class MastodonIsOneStepButEveryInstanceIsItsOwnServer(unittest.TestCase):
    def test_the_instance_url_is_where_the_call_goes(self):
        with mock.patch.object(social.requests, 'request',
                               return_value=_Resp({'acct': 'alex', 'display_name': 'Alex Doyle',
                                                   'followers_count': 12, 'following_count': 30,
                                                   'statuses_count': 5})) as req:
            out = social.run_mastodon_me({'token': 't', 'base_url': 'https://fosstodon.org/'})
        self.assertEqual(req.call_args[0][1], 'https://fosstodon.org/api/v1/accounts/verify_credentials')
        self.assertEqual(out['rows'][0]['instance'], 'fosstodon.org')

    def test_the_html_is_stripped_so_a_summary_reads_words_not_markup(self):
        toots = [{'id': '1', 'content': '<p>first line</p><p>second <b>line</b></p>',
                  'account': {'acct': 'erin@x.social'}, 'created_at': '2026-09-22T10:00:00Z',
                  'reblogs_count': 1, 'favourites_count': 2, 'replies_count': 0,
                  'url': 'https://x.social/@erin/1'}]
        with mock.patch.object(social.requests, 'request', return_value=_Resp(toots)):
            head, body = social.run_mastodon_timeline({'token': 't'})
        self.assertIn('first line', body)
        self.assertNotIn('<p>', body)
        self.assertNotIn('<b>', body)
        self.assertIn('1 posts', head)

    def test_the_three_timelines_map_to_the_right_endpoints(self):
        for which, path, local in (('home', '/timelines/home', None),
                                   ('public', '/timelines/public', None),
                                   ('local', '/timelines/public', 'true')):
            with mock.patch.object(social.requests, 'request', return_value=_Resp([])) as req:
                social.run_mastodon_timeline({'token': 't', 'timeline': which})
            self.assertTrue(req.call_args[0][1].endswith(path), which)
            self.assertEqual(req.call_args.kwargs['params'].get('local'), local, which)

    def test_an_unknown_timeline_is_refused_rather_than_guessed(self):
        with self.assertRaises(RuntimeError) as e:
            social.run_mastodon_timeline({'token': 't', 'timeline': 'federated'})
        self.assertIn('home, public or local', str(e.exception))

    def test_a_post_carries_an_idempotency_key_so_a_retry_posts_once(self):
        """A retry after a timeout is the ordinary case for a scheduled job. Without the key, a
        network hiccup posts twice and only one of them can be deleted by hand."""
        with mock.patch.object(social.requests, 'post',
                               return_value=_Resp({'id': '9', 'url': 'https://m.s/@a/9',
                                                   'visibility': 'public'})) as post:
            social.run_mastodon_post({'token': 't', 'text': 'hello'})
        self.assertIn('Idempotency-Key', post.call_args.kwargs['headers'])
        self.assertEqual(post.call_args.kwargs['json'], {'status': 'hello', 'visibility': 'public'})

    def test_the_same_post_twice_produces_the_same_key(self):
        keys = []
        with mock.patch.object(social.requests, 'post', return_value=_Resp({'id': '1'})) as post:
            for _ in range(2):
                social.run_mastodon_post({'token': 't', 'text': 'same words'})
                keys.append(post.call_args.kwargs['headers']['Idempotency-Key'])
        self.assertEqual(keys[0], keys[1])

    def test_visibility_is_checked_because_direct_and_public_are_not_a_typo_apart(self):
        with self.assertRaises(RuntimeError) as e:
            social.run_mastodon_post({'token': 't', 'text': 'x', 'visibility': 'friends'})
        self.assertIn('public, unlisted, private or direct', str(e.exception))

    def test_an_instance_that_raised_its_cap_is_respected(self):
        with mock.patch.object(social.requests, 'post', return_value=_Resp({'id': '1'})):
            social.run_mastodon_post({'token': 't', 'text': 'x' * 900, 'max_chars': 1000})
        with self.assertRaises(RuntimeError) as e:
            social.run_mastodon_post({'token': 't', 'text': 'x' * 900})
        self.assertIn('500 characters', str(e.exception))

    def test_no_token_names_where_to_get_one(self):
        with self.assertRaises(RuntimeError) as e:
            social.run_mastodon_me({})
        self.assertIn('Development', str(e.exception))


class WiredInTests(unittest.TestCase):
    def test_every_type_is_a_report_source(self):
        for t in TYPES: self.assertIn(t, REGISTRY, f'{t} is not a report source')

    def test_reading_is_a_read_and_posting_is_a_write(self):
        from taskuary.scopes import needs
        for t in TYPES:
            self.assertEqual(needs(t), 'write' if t.endswith('_post') else 'read', t)

    def test_both_cards_ship_at_read_so_a_post_is_a_proposal(self):
        """A public post cannot be recalled. The card's authority is what makes an agent draft it
        and the owner send it, and lowering that is a decision, not a default."""
        from taskuary.scopes import allows, default_scope
        s = MemoryStore()
        for card in ('bluesky', 'mastodon'):
            self.assertEqual(default_scope(card), 'read')
            self.assertFalse(allows(s.get_connector_by_type(card), f'{card}_post'),
                             f'an agent could post to {card} unattended')
            self.assertTrue(allows(s.get_connector_by_type(card), f'{card}_timeline'))

    def test_the_credential_reaches_the_executor(self):
        s = MemoryStore()
        for card, name in (('bluesky', 'app_password'), ('mastodon', 'token')):
            cid = s.get_connector_by_type(card)['ConnectorId']
            s.save_connector({'ConnectorId': cid, 'Secret': f'sec-{card}', 'Active': 1}, 'test')
            for t in (t for t in TYPES if t.startswith(card)):
                self.assertEqual(resolve_cfg(s, {'type': t}).get(name), f'sec-{card}',
                                 f'{t} cannot see the credential on its card')

    def test_a_bluesky_cfg_carries_its_card_id_so_the_session_cache_is_per_card(self):
        s = MemoryStore()
        cid = s.get_connector_by_type('bluesky')['ConnectorId']
        s.save_connector({'ConnectorId': cid, 'Secret': 'pw', 'Active': 1}, 'test')
        self.assertEqual(resolve_cfg(s, {'type': 'bluesky_me'}).get('_cid'), cid)

    def test_each_has_a_connection_resolver_and_a_seeded_card(self):
        s = MemoryStore()
        for t in TYPES: self.assertIn(t, CONNECTION_OF)
        for card in ('bluesky', 'mastodon'):
            self.assertIsNotNone(s.get_connector_by_type(card), f'no {card} card was seeded')

    def test_neither_is_a_trigger_because_a_timeline_is_not_an_inbox(self):
        """It has no thread waiting on you and nobody expecting a reply. Rolling it into the
        Timeline would put the whole of the internet in the work rail."""
        from taskuary.store import DEFAULT_ROLES
        for card in ('bluesky', 'mastodon'):
            self.assertEqual(DEFAULT_ROLES[card], 'report,tool')
            self.assertNotIn('trigger', DEFAULT_ROLES[card])


if __name__ == '__main__':
    unittest.main()
