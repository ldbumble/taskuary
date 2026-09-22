"""Four chat servers shaped like Discord: Mattermost, Rocket.Chat, Matrix, Google Chat.

Discord is the model rather than Slack because these share its two properties - each watched room
is its OWN source, so a rate limit in one room cannot skip the rooms after it, and each can carry
a reply BACK, which is what makes a chat server worth connecting rather than merely reading.

Three of them are the same object with different spelling: a base url you host and a token. The
tests below are mostly about the ONE place each differs, because that is where the bug is - a
header name, a path, or a timestamp in the wrong unit.
"""
import json
import unittest
from datetime import datetime, timedelta
from unittest import mock

from taskuary import chatservers
from taskuary.store import MemoryStore

FOUR = ('mattermost', 'rocketchat', 'matrix', 'google_chat')


class _Resp:
    def __init__(self, payload=None, status=200, text=''):
        self._payload, self.status_code, self.text = payload, status, text or json.dumps(payload or {})

    def json(self): return self._payload

    def raise_for_status(self):
        if self.status_code >= 400: raise RuntimeError(f'http {self.status_code}')


def _card(typ, cfg=None, secret='tok'):
    return {'ConnectorId': 1, 'Type': typ, 'Secret': secret, 'ConfigJson': json.dumps(cfg or {})}


SRC = {'Address': 'room-1', 'Channel': 'x'}
SINCE = datetime(2026, 9, 1, 12, 0, 0).astimezone()


class MattermostTests(unittest.TestCase):
    CARD = _card('mattermost', {'base_url': 'https://chat.acme.com/'})

    def test_the_trailing_slash_on_the_server_url_does_not_double_up(self):
        """A url pasted out of a browser ends in / more often than not, and //api/v4 is a 404 the
        owner has no way to read."""
        with mock.patch.object(chatservers.requests, 'request',
                               return_value=_Resp({'username': 'uri'})) as req:
            chatservers.test_mattermost(MemoryStore(), self.CARD)
        self.assertEqual(req.call_args[0][1], 'https://chat.acme.com/api/v4/users/me')

    def test_the_window_is_milliseconds_because_that_is_what_mattermost_counts_in(self):
        posts = {'order': ['p1'], 'posts': {'p1': {'message': 'hello', 'user_id': 'u1',
                                                   'create_at': 1789000000000}}}
        with mock.patch.object(chatservers.requests, 'request', return_value=_Resp(posts)) as req:
            with mock.patch.object(chatservers, '_ingest', return_value=1) as ing:
                n = chatservers.poll_mattermost(MemoryStore(), self.CARD, SRC, SINCE)
        self.assertEqual(req.call_args.kwargs['params']['since'], int(SINCE.timestamp() * 1000))
        self.assertEqual(n, 1)
        self.assertEqual(ing.call_args[0][2], 'mattermost')

    def test_a_join_or_leave_is_not_a_message(self):
        """Mattermost marks room events with a `type`; ingesting them would put "uri joined the
        channel" on the Timeline as work."""
        posts = {'order': ['p1'], 'posts': {'p1': {'message': 'uri joined', 'type': 'system_join_channel',
                                                   'create_at': 1789000000000}}}
        with mock.patch.object(chatservers.requests, 'request', return_value=_Resp(posts)):
            with mock.patch.object(chatservers, '_ingest', return_value=1) as ing:
                n = chatservers.poll_mattermost(MemoryStore(), self.CARD, SRC, SINCE)
        self.assertEqual((n, ing.call_count), (0, 0))

    def test_no_server_url_says_so_before_the_call(self):
        with self.assertRaises(RuntimeError) as e:
            chatservers.test_mattermost(MemoryStore(), _card('mattermost'))
        self.assertIn('server url', str(e.exception))


class RocketChatTests(unittest.TestCase):
    CARD = _card('rocketchat', {'base_url': 'https://chat.acme.com', 'user_id': 'uid1'})

    def test_it_sends_both_values_because_one_is_not_enough(self):
        """Rocket.Chat authenticates with a token AND the user id it belongs to. A card holding
        only the token gets a 401 that reads like a bad token."""
        with mock.patch.object(chatservers.requests, 'request',
                               return_value=_Resp({'username': 'uri'})) as req:
            chatservers.test_rocketchat(MemoryStore(), self.CARD)
        h = req.call_args.kwargs['headers']
        self.assertEqual((h['X-Auth-Token'], h['X-User-Id']), ('tok', 'uid1'))

    def test_a_missing_user_id_is_named_rather_than_left_to_a_401(self):
        with self.assertRaises(RuntimeError) as e:
            chatservers.test_rocketchat(MemoryStore(), _card('rocketchat', {'base_url': 'https://c.x'}))
        self.assertIn('user id', str(e.exception))

    def test_a_room_event_is_skipped_and_a_message_is_not(self):
        hist = {'messages': [{'_id': 'm1', 'msg': 'hello', 'ts': '2026-09-02T10:00:00Z',
                              'u': {'name': 'Uri'}},
                             {'_id': 'm2', 'msg': 'uri added x', 't': 'au', 'ts': '2026-09-02T10:01:00Z'}]}
        with mock.patch.object(chatservers.requests, 'request', return_value=_Resp(hist)):
            with mock.patch.object(chatservers, '_ingest', return_value=1) as ing:
                n = chatservers.poll_rocketchat(MemoryStore(), self.CARD, SRC, SINCE)
        self.assertEqual((n, ing.call_count), (1, 1))
        self.assertEqual(ing.call_args[0][4], 'hello')

    def test_a_reply_goes_to_the_room_it_came_from(self):
        s = MemoryStore()
        c = s.get_connector_by_type('rocketchat')
        s.save_connector({'ConnectorId': c['ConnectorId'], 'Secret': 'tok',
                          'ConfigJson': json.dumps({'base_url': 'https://c.x', 'user_id': 'u'}),
                          'Active': 1}, 'test')
        with mock.patch.object(chatservers.requests, 'request', return_value=_Resp({'success': True})) as req:
            out = chatservers.rocketchat_send(s, 'GENERAL', 'hi there')
        self.assertEqual(req.call_args.kwargs['json'], {'roomId': 'GENERAL', 'text': 'hi there'})
        self.assertEqual(out, {'channel': 'rocketchat', 'chat': 'GENERAL'})


class MatrixTests(unittest.TestCase):
    CARD = _card('matrix', {})

    def test_a_blank_homeserver_means_matrix_org(self):
        with mock.patch.object(chatservers.requests, 'request',
                               return_value=_Resp({'user_id': '@uri:matrix.org'})) as req:
            detail = chatservers.test_matrix(MemoryStore(), self.CARD)
        self.assertTrue(req.call_args[0][1].startswith(chatservers.MATRIX_HOME))
        self.assertIn('@uri:matrix.org', detail)

    def test_the_room_id_is_escaped_because_it_starts_with_a_bang_and_holds_a_colon(self):
        """!AbC:matrix.org unescaped in a path is a different url than the one meant."""
        with mock.patch.object(chatservers.requests, 'request', return_value=_Resp({'chunk': []})) as req:
            chatservers.poll_matrix(MemoryStore(), self.CARD, {'Address': '!AbC:matrix.org'}, SINCE)
        self.assertIn('%21AbC%3Amatrix.org', req.call_args[0][1])

    def test_only_text_messages_come_through(self):
        old = int((SINCE - timedelta(days=2)).timestamp() * 1000)
        new = int((SINCE + timedelta(minutes=5)).timestamp() * 1000)
        chunk = [{'event_id': 'e1', 'sender': '@a:x', 'origin_server_ts': new,
                  'content': {'msgtype': 'm.text', 'body': 'hello'}},
                 {'event_id': 'e2', 'sender': '@a:x', 'origin_server_ts': new,
                  'content': {'msgtype': 'm.image', 'body': 'cat.png'}},
                 {'event_id': 'e3', 'sender': '@a:x', 'origin_server_ts': old,
                  'content': {'msgtype': 'm.text', 'body': 'last week'}}]
        with mock.patch.object(chatservers.requests, 'request', return_value=_Resp({'chunk': chunk})):
            with mock.patch.object(chatservers, '_ingest', return_value=1) as ing:
                n = chatservers.poll_matrix(MemoryStore(), self.CARD, SRC, SINCE)
        self.assertEqual((n, ing.call_count), (1, 1))
        self.assertEqual(ing.call_args[0][4], 'hello')

    def test_a_send_carries_a_transaction_id_so_a_retry_posts_once(self):
        s = MemoryStore()
        c = s.get_connector_by_type('matrix')
        s.save_connector({'ConnectorId': c['ConnectorId'], 'Secret': 'tok', 'Active': 1}, 'test')
        with mock.patch.object(chatservers.requests, 'request', return_value=_Resp({'event_id': 'e'})) as req:
            chatservers.matrix_send(s, '!AbC:matrix.org', 'hi')
        method, url = req.call_args[0][0], req.call_args[0][1]
        self.assertEqual(method, 'put')
        self.assertIn('/send/m.room.message/', url)
        self.assertEqual(req.call_args.kwargs['json'], {'msgtype': 'm.text', 'body': 'hi'})


class GoogleChatTests(unittest.TestCase):
    def test_it_borrows_the_gmail_cards_oauth_client(self):
        """One registration in Google Cloud, not two - the road SharePoint takes with Outlook's
        app. A card demanding its own client id is a card people give up on."""
        s = MemoryStore()
        g = s.get_connector_by_type('gmail')
        s.save_connector({'ConnectorId': g['ConnectorId'], 'Active': 1,
                          'ConfigJson': json.dumps({'google_client_id': 'cid',
                                                    'google_client_secret': 'sec'})}, 'test')
        card = _card('google_chat', {}, secret='refresh-token')
        with mock.patch.object(chatservers.requests, 'post',
                               return_value=_Resp({'access_token': 'at'})) as post:
            self.assertEqual(chatservers._google_access(s, card), 'at')
        sent = post.call_args.kwargs['data']
        self.assertEqual((sent['client_id'], sent['client_secret'], sent['refresh_token']),
                         ('cid', 'sec', 'refresh-token'))

    def test_with_no_client_anywhere_it_says_what_is_missing(self):
        with self.assertRaises(RuntimeError) as e:
            chatservers._google_access(MemoryStore(), _card('google_chat', {}, secret='rt'))
        self.assertIn('OAuth client', str(e.exception))

    def test_a_bare_space_id_is_given_its_prefix(self):
        """Sources hold what the owner pasted. spaces/AAAA and AAAA should behave the same."""
        s = MemoryStore()
        with mock.patch.object(chatservers, '_google_access', return_value='at'):
            with mock.patch.object(chatservers.requests, 'request',
                                   return_value=_Resp({'messages': []})) as req:
                chatservers.poll_google_chat(s, _card('google_chat'), {'Address': 'AAAAxyz'}, SINCE)
        self.assertIn('/spaces/AAAAxyz/messages', req.call_args[0][1])

    def test_a_card_only_post_has_nothing_to_triage(self):
        msgs = {'messages': [{'name': 'spaces/A/messages/1', 'createTime': '2026-09-02T10:00:00Z',
                              'sender': {'displayName': 'Bot'}},
                             {'name': 'spaces/A/messages/2', 'text': 'real words',
                              'createTime': '2026-09-02T10:01:00Z', 'sender': {'displayName': 'Uri'}}]}
        with mock.patch.object(chatservers, '_google_access', return_value='at'):
            with mock.patch.object(chatservers.requests, 'request', return_value=_Resp(msgs)):
                with mock.patch.object(chatservers, '_ingest', return_value=1) as ing:
                    n = chatservers.poll_google_chat(MemoryStore(), _card('google_chat'),
                                                     {'Address': 'spaces/A'}, SINCE)
        self.assertEqual((n, ing.call_count), (1, 1))
        self.assertEqual(ing.call_args[0][4], 'real words')


class OneServersTokenCannotBeAimedAtAnother(unittest.TestCase):
    def test_a_connector_id_naming_a_different_type_is_ignored(self):
        """The rule discord_send already has: a tool call that passes somebody else's connector id
        must not get that card's token pointed at this server."""
        s = MemoryStore()
        mm = s.get_connector_by_type('mattermost')
        s.save_connector({'ConnectorId': mm['ConnectorId'], 'Secret': 'mm-token', 'Active': 1}, 'test')
        rc = s.get_connector_by_type('rocketchat')
        with self.assertRaises(RuntimeError):
            chatservers._card(s, 'rocketchat', mm['ConnectorId'])
        self.assertIsNotNone(rc)

    def test_the_right_card_is_found_by_type_when_no_id_is_given(self):
        s = MemoryStore()
        mm = s.get_connector_by_type('mattermost')
        s.save_connector({'ConnectorId': mm['ConnectorId'], 'Secret': 'mm-token', 'Active': 1}, 'test')
        self.assertEqual(chatservers._card(s, 'mattermost')['Secret'], 'mm-token')


class WiredInTests(unittest.TestCase):
    def test_all_four_are_chat_everywhere_chat_is_decided(self):
        """Four separate word-lists decide whether a message is chat: how it is categorised, how
        its thread is split, whether a verdict carries forward, and which prefix its conversation
        id takes. A channel in three of them and not the fourth behaves like mail in one place."""
        from taskuary.categories import CHAT
        from taskuary.ingest import CHAT_CHANNELS as INGEST_CHAT
        from taskuary.store import CHAT_CHANNELS as STORE_CHAT, CHAT_PREFIXES
        for t in FOUR:
            self.assertIn(t, CHAT, f'{t} is not chat to categories')
            self.assertIn(t, INGEST_CHAT, f'{t} is not chat to ingest')
            self.assertIn(t, STORE_CHAT, f'{t} is not chat to the store')
            self.assertIn(f'{t}:', CHAT_PREFIXES, f'{t} has no conversation prefix')

    def test_each_can_carry_a_reply_and_a_report(self):
        from taskuary.outbound import REPORTABLE, SENDABLE
        for t in FOUR:
            self.assertIn(t, SENDABLE, f'{t} cannot be replied on')
            self.assertIn(t, REPORTABLE, f'{t} cannot carry a report out')

    def test_each_is_a_card_the_poller_and_the_tester_can_reach(self):
        from taskuary.channels import CH2SRC, CHAT_SERVERS
        s = MemoryStore()
        for t in FOUR:
            self.assertIn(t, CHAT_SERVERS)
            self.assertIn(t, CH2SRC, f'{t} sources would not be found')
            self.assertIsNotNone(s.get_connector_by_type(t), f'no {t} card was seeded')
            self.assertIn(t, chatservers.TESTS)
            self.assertIn(t, chatservers.POLLS)
            self.assertIn(t, chatservers.SENDS)

    def test_posting_back_into_a_room_needs_write_authority(self):
        from taskuary.scopes import default_scope
        for t in FOUR:
            self.assertEqual(default_scope(t), 'write', f'{t} could not post a reply')


if __name__ == '__main__':
    unittest.main()
