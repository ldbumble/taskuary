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
from taskuary.testing import Factory

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
        self.assertIn('1 post', head)
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
        self.assertIn('1 post', head)

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
            row = {**s.get_connector_by_type(card), 'Scope': 'read'}  # every connection starts at full; read is the owner's narrowing (2026-10-05)
            self.assertFalse(allows(row, f'{card}_post'), f'an agent could post to {card} unattended at read')
            self.assertTrue(allows(row, f'{card}_timeline'))

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


# ── Reddit and X: posts from the cards that already read their inboxes ──────────────────
def _rd_card(**cfg):
    return {'ConnectorId': 41, 'Type': 'reddit', 'Secret': 'pw', 'Active': 1,
            'ConfigJson': json.dumps({'client_id': 'cid', 'client_secret': 'cs', 'username': 'alexdoyle', **cfg})}


class RedditNet:
    "Reddit's HTTP, stubbed: the sign-in, the flair list, the submit - every call recorded, none leaves."
    OK = {'json': {'errors': [], 'data': {'url': 'https://www.reddit.com/r/smallbusiness/comments/abc/payroll/', 'name': 't3_abc', 'id': 'abc'}}}

    def __init__(self, submit=None, flairs=()): self.calls, self.submit, self.flairs = [], submit or self.OK, list(flairs)

    def request(self, method, url, **kw):
        self.calls.append((method.upper(), url, kw))
        if url.endswith('/api/v1/access_token'): return _Resp({'access_token': 'rtok', 'expires_in': 3600})
        if url.endswith('/api/link_flair_v2'): return _Resp(self.flairs)
        return _Resp(self.submit)

    def submitted(self): return [kw for m, u, kw in self.calls if u.endswith('/api/submit')]


class RedditPosts(unittest.TestCase):
    def setUp(self):
        from taskuary import net
        net._TOKENS.clear()

    def post(self, rd, **cfg):
        from taskuary import inboxes
        with mock.patch.object(inboxes.requests, 'request', rd.request):
            return inboxes.run_reddit_post({'_card': _rd_card(), **cfg})

    def test_a_text_post_goes_to_the_subreddit_as_the_signed_in_user(self):
        rd = RedditNet()
        out = self.post(rd, subreddit='r/smallbusiness', title='How we moved payroll', text='Three things we learned.')
        sent = rd.submitted()[0]
        self.assertEqual({k: sent['data'][k] for k in ('sr', 'kind', 'title', 'text', 'api_type')},
                         {'sr': 'smallbusiness', 'kind': 'self', 'title': 'How we moved payroll', 'text': 'Three things we learned.', 'api_type': 'json'})
        self.assertEqual(sent['headers']['Authorization'], 'Bearer rtok')
        self.assertNotIn('alexdoyle', sent['headers']['User-Agent'])         # names the app, never the person
        self.assertEqual(out['rows'][0]['url'], 'https://www.reddit.com/r/smallbusiness/comments/abc/payroll/')

    def test_a_link_alone_is_a_link_post(self):
        rd = RedditNet()
        self.post(rd, subreddit='smallbusiness', title='Our write-up', link='https://northwind.example/payroll')
        sent = rd.submitted()[0]['data']
        self.assertEqual((sent['kind'], sent['url']), ('link', 'https://northwind.example/payroll'))

    def test_a_refused_post_says_reddits_words_and_nothing_was_posted(self):
        "Reddit answers 200 with its refusal inside - a 200 is not a post."
        rd = RedditNet({'json': {'errors': [['SUBREDDIT_NOTALLOWED', 'you are not allowed to post there.', 'sr']]}})
        with self.assertRaises(RuntimeError) as e: self.post(rd, subreddit='smallbusiness', title='T', text='x')
        self.assertIn('you are not allowed to post there', str(e.exception))
        self.assertIn('nothing was posted', str(e.exception))

    def test_a_subreddit_that_wants_a_flair_names_the_flairs_it_takes(self):
        rd = RedditNet({'json': {'errors': [['SUBMIT_VALIDATION_FLAIR_REQUIRED', 'Your post must contain post flair.', 'flair']]}},
                       [{'id': 'f1', 'text': 'Question'}, {'id': 'f2', 'text': 'Story'}])
        with self.assertRaises(RuntimeError) as e: self.post(rd, subreddit='smallbusiness', title='T', text='x')
        self.assertIn('r/smallbusiness asks for a flair', str(e.exception))
        self.assertIn('Question, Story', str(e.exception))

    def test_a_named_flair_is_sent_as_its_id(self):
        rd = RedditNet(flairs=[{'id': 'f1', 'text': 'Question'}, {'id': 'f2', 'text': 'Story'}])
        self.post(rd, subreddit='smallbusiness', title='T', text='x', flair='story')
        self.assertEqual(rd.submitted()[0]['data']['flair_id'], 'f2')
        rd = RedditNet(flairs=[{'id': 'f1', 'text': 'Question'}])
        with self.assertRaises(RuntimeError) as e: self.post(rd, subreddit='smallbusiness', title='T', text='x', flair='Rant')
        self.assertIn('Question', str(e.exception))
        self.assertEqual(rd.submitted(), [])

    def test_what_is_missing_is_refused_before_anything_is_called(self):
        rd = RedditNet()
        for cfg, said in (({'title': 'T', 'text': 'x'}, 'subreddit'), ({'subreddit': 'smallbusiness', 'text': 'x'}, 'title'),
                          ({'subreddit': 'smallbusiness', 'title': 'T'}, '`text` or a `link`')):
            with self.assertRaises(RuntimeError) as e: self.post(rd, **cfg)
            self.assertIn(said, str(e.exception))
        self.assertEqual(rd.calls, [])


def _x_card(**cfg):
    return {'ConnectorId': 42, 'Type': 'x', 'Secret': 'app-bearer', 'Active': 1, 'ConfigJson': json.dumps(
        {'username': 'alexdoyle', 'consumer_key': 'ck', 'consumer_secret': 'cs', 'access_token': 'at', 'access_secret': 'as', **cfg})}


class XPosts(unittest.TestCase):
    def post(self, resp, card=None, **cfg):
        from taskuary import inboxes
        with mock.patch.object(inboxes.requests, 'post', return_value=resp) as post:
            out = inboxes.run_x_post({'_card': card or _x_card(), **cfg})
        return out, post

    def test_a_post_is_signed_with_the_users_own_keys_not_the_app_bearer(self):
        out, post = self.post(_Resp({'data': {'id': '1850', 'text': 'We shipped.'}}, 201), text='We shipped.')
        self.assertEqual(post.call_args[0][0], 'https://api.x.com/2/tweets')
        self.assertEqual(post.call_args.kwargs['json'], {'text': 'We shipped.'})
        auth = post.call_args.kwargs['headers']['Authorization']
        self.assertTrue(auth.startswith('OAuth '), auth)
        for k in ('oauth_consumer_key="ck"', 'oauth_token="at"', 'HMAC-SHA1'): self.assertIn(k, auth)
        self.assertNotIn('app-bearer', auth)
        self.assertEqual(out['rows'][0]['url'], 'https://x.com/alexdoyle/status/1850')

    def test_a_refused_post_says_why_in_xs_words_and_the_way_past(self):
        with self.assertRaises(RuntimeError) as e:
            self.post(_Resp({'title': 'Forbidden', 'detail': 'You are not permitted to perform this action.'}, 403), text='hi')
        self.assertIn('not permitted', str(e.exception))
        self.assertIn('Read and write', str(e.exception))

    def test_without_the_user_keys_it_says_which_and_where(self):
        from taskuary.outbound import Fixable
        card = {**_x_card(), 'ConfigJson': json.dumps({'username': 'alexdoyle'})}
        with self.assertRaises(Fixable) as e: self.post(_Resp({}), card=card, text='hi')
        self.assertIn('Keys and tokens', str(e.exception))
        self.assertEqual(e.exception.fix['href'], '#connector=x')

    def test_an_over_long_post_is_refused_before_the_call(self):
        with self.assertRaises(RuntimeError) as e: self.post(_Resp({}), text='x' * 281)
        self.assertIn('280', str(e.exception))

    def test_a_picture_is_uploaded_then_named_on_the_post(self):
        import pathlib, tempfile
        f = pathlib.Path(tempfile.mkdtemp()) / 'chart.png'
        f.write_bytes(b'\x89PNG\r\n\x1a\n' + b'0' * 64)
        from taskuary import inboxes
        seen = []
        def post(url, **kw):
            seen.append((url, kw))
            return _Resp({'data': {'id': '77'}}) if url.endswith('/media/upload') else _Resp({'data': {'id': '1851'}}, 201)
        with mock.patch.object(inboxes.requests, 'post', post):
            out = inboxes.run_x_post({'_card': _x_card(), 'text': 'The chart.', 'image_path': str(f)})
        self.assertEqual([u for u, _ in seen], ['https://api.x.com/2/media/upload', 'https://api.x.com/2/tweets'])
        self.assertEqual(seen[1][1]['json']['media'], {'media_ids': ['77']})
        self.assertEqual(out['rows'][0]['image'], '77')


class RedditTwoFactor(unittest.TestCase):
    """An account with two-factor sign-in (the owner, 2026-11-18: "it should work anyway"): Reddit's script app takes the password with the
    current authenticator code after a colon. The card keeps the account's authenticator key, sealed, and the code is made at each sign-in."""
    KEY = 'JBSWY3DPEHPK3PXP'                          # an invented setup key, as a site prints it

    def setUp(self):
        from taskuary import net
        net._TOKENS.clear()

    def sign_in(self, rd, card):
        from taskuary import inboxes
        with mock.patch.object(inboxes.requests, 'request', rd.request):
            return inboxes.run_reddit_post({'_card': card, 'subreddit': 'smallbusiness', 'title': 'T', 'text': 'x'})

    def test_the_saved_key_puts_the_current_code_after_the_password(self):
        from taskuary import totp
        rd = RedditNet()
        with mock.patch.object(totp.time, 'time', return_value=1_800_000_000.0):
            self.sign_in(rd, _rd_card(totp_key=self.KEY))
            want = totp.code(totp.parse(self.KEY))
        grant = next(kw['data'] for m, u, kw in rd.calls if u.endswith('/api/v1/access_token'))
        self.assertEqual(grant['password'], f'pw:{want}')
        self.assertEqual(len(rd.submitted()), 1)

    def test_with_no_key_the_password_goes_alone_and_a_refusal_names_the_key(self):
        rd = RedditNet()
        rd.request = (lambda m, u, **kw: (rd.calls.append((m, u, kw)), _Resp({'error': 'invalid_grant'}))[1])
        with self.assertRaises(RuntimeError) as e: self.sign_in(rd, _rd_card())
        grant = rd.calls[0][2]['data']
        self.assertEqual(grant['password'], 'pw')
        self.assertIn('two-factor', str(e.exception)); self.assertIn('authenticator key', str(e.exception))
        self.assertNotIn('cannot', str(e.exception))                          # a 2FA account can use the card now

    def test_a_key_that_is_not_one_is_said_plainly_before_any_sign_in(self):
        rd = RedditNet()
        with self.assertRaises(RuntimeError) as e: self.sign_in(rd, _rd_card(totp_key='not a key!'))
        self.assertIn('setup key', str(e.exception)); self.assertEqual(rd.calls, [])

    def test_the_key_is_sealed_and_never_sent_back_to_the_page(self):
        from taskuary import guard
        from taskuary.store import SQLiteStore
        self.assertIn('totp_key', SQLiteStore.SEALED_CONFIG)
        self.assertIn('totp_key', guard.WRITE_ONLY_CONFIG['reddit'])


class RedditAndXAreWired(unittest.TestCase):
    def test_each_post_is_a_write_that_reaches_people_on_its_own_card(self):
        from taskuary import connectorcatalog as cat, proposals, scopes
        from taskuary.reports import card_of
        for t, card, press in (('reddit_post', 'reddit', 'Post to Reddit'), ('x_post', 'x', 'Post to X')):
            self.assertIn(t, REGISTRY); self.assertEqual(card_of(t), card); self.assertEqual(scopes.needs(t), 'write')
            self.assertIn(t, scopes.REACHES); self.assertIn(t, proposals.POSTS)
            a = cat.action_for(t)
            self.assertEqual((a['card'], a['press'], a['road']), (card, press, 'run_tool'))
        self.assertIn('x_post', proposals.MEDIA); self.assertNotIn('reddit_post', proposals.MEDIA)
        self.assertIn('developer app', cat.by_type('x')['desc'])

    def test_a_post_card_is_named_by_its_own_press_never_its_tool(self):
        # "1 of 3 · next: write x post on X (Twitter)" (design round 6, D3): the next card's line is the card's own words
        from taskuary import cardqueue, proposals
        s = MemoryStore(); tid = Factory(s).task(title='Post the Q3 headline')
        self.assertEqual(proposals.tool_words(s, {'action': 'run_tool', 'type': 'x_post', 'text': 'Q3 is in.'}), 'post to X')
        for t in ('linkedin_post', 'x_post'): proposals.queue(s, tid, {'action': 'run_tool', 'type': t, 'text': 'Q3 is in.'})
        q = cardqueue.state(s, tid)
        self.assertEqual(cardqueue.line(q), '1 of 2 · next: post to X')

    def test_a_post_he_dismissed_raised_again_is_his_no_not_a_second_card(self):
        # the roads audit, 2026-11-19 (#7): a post, a payment, an email stay cards, but they ask the one rule the shell's, the browser's and
        # the desktop's gates do (actrule.decide) - the same card raised again after his Dismiss, with no word from him since, is his no
        from taskuary import proposals, verdicts
        s = MemoryStore(); tid = Factory(s).task(title='Post the Q3 headline')
        p = {'action': 'run_tool', 'type': 'x_post', 'text': 'Q3 is in.'}
        q = proposals.queue(s, tid, dict(p))
        self.assertTrue(verdicts.decide(s, s.get_review(q['reviewId']), 'reject')['ok'])
        miss = []
        self.assertIsNone(proposals.queue(s, tid, dict(p), refused=miss))
        self.assertIn('The owner dismissed this same step', miss[0])
        self.assertTrue(proposals.queue(s, tid, {**p, 'text': 'Q3 is in - up 12%.'}), 'a changed post is another step, put to him')

    def test_the_saved_card_reaches_the_executor_and_no_body_can_bring_its_own(self):
        from taskuary.reports import query_only
        s = MemoryStore()
        for card, t in (('reddit', 'reddit_post'), ('x', 'x_post')):
            cid = s.get_connector_by_type(card)['ConnectorId']
            s.save_connector({'ConnectorId': cid, 'Secret': f'sec-{card}', 'Active': 1}, 'test')
            got = resolve_cfg(s, {'type': t, 'text': 'hi'})
            self.assertEqual((got['_card']['ConnectorId'], got['_card']['Secret']), (cid, f'sec-{card}'))
            self.assertNotIn('_card', query_only({'type': t, '_card': {'Secret': 'theirs'}}))

    def test_reddit_is_an_agent_tool_so_the_agent_can_propose_a_post(self):
        from taskuary.store import DEFAULT_ROLES
        self.assertIn('tool', DEFAULT_ROLES['reddit'].split(','))


if __name__ == '__main__':
    unittest.main()


# THE HYDROGEN WALK, 2026-11-19: a card for a tool named "linkedin" raised, its Approve answered "Failed 'linkedin'" (a raw key), and its card
# read "Write linkedin on LinkedIn / Where linkedin" - nothing before the press said LinkedIn was not connected
def test_a_post_to_a_tool_that_is_not_one_is_refused_to_its_agent_never_at_his_press():
    from taskuary import proposals
    from taskuary.store import MemoryStore
    from taskuary.testing import Factory
    s = MemoryStore(); tid = Factory(s).task('Announce the portal'); refused = []
    assert proposals.queue(s, tid, {'action': 'run_tool', 'type': 'linkedin', 'text': 'The portal launches Monday.'}, 'agent', refused) is None
    assert refused and "no tool 'linkedin'" in refused[0] and 'linkedin_post' in refused[0]
    with __import__('pytest').raises(RuntimeError, match="no tool 'linkedin'"):
        proposals.execute(s, {'TaskId': tid, 'Kind': 'action', 'DraftText': '{"action": "run_tool", "type": "linkedin"}', 'ReviewId': 9}, 'owner')


def test_a_post_card_names_its_network_in_his_words():
    from taskuary import proposals
    from taskuary.store import MemoryStore
    from taskuary.testing import Factory
    s = MemoryStore(); tid = Factory(s).task('Announce the portal')
    out = proposals.queue(s, tid, {'action': 'run_tool', 'type': 'x_post', 'text': 'The portal launches Monday.'}, 'agent')
    import json
    p = json.loads(s.get_review(out['ReviewId'] if isinstance(out, dict) and 'ReviewId' in out else s._rows("SELECT ReviewId FROM review")[0]['ReviewId'])['DraftText'])
    assert p['network'] == 'X' and proposals.tool_words(s, p).lower().startswith('post to x')
