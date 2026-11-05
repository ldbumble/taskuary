"""A Slack line is answered in Slack (the owner, 2026-11-05: "fix slack reply"). Before, Slack was read here and answered there:
the draft was written and the button said "copy it and answer in Slack". Network stubbed - nothing leaves."""
import json, unittest
from unittest import mock
from taskuary import outbound
from taskuary.store import MemoryStore


def slack_store(token='xoxp-test'):
    s = MemoryStore()
    c = s.get_connector_by_type('slack')
    cid = c['ConnectorId'] if c else s.save_connector({'Type': 'slack', 'Name': 'Slack'}, 't')
    s.save_connector({'ConnectorId': cid, 'Active': 1, 'Secret': token, 'ConfigJson': json.dumps({})}, 't')
    return s


class Resp:
    def __init__(self, j): self.j = j
    def raise_for_status(self): pass
    def json(self): return self.j


class SlackReply(unittest.TestCase):
    def test_no_card_still_says_answer_it_in_slack(self):
        s = MemoryStore()
        self.assertFalse(outbound.can_reply(s, 'slack')); self.assertIn('answer it in Slack', outbound.send_block(s, 'slack'))

    def test_a_connected_card_can_reply(self):
        self.assertTrue(outbound.can_reply(slack_store(), 'slack'))

    def test_a_channel_line_is_answered_in_its_thread_in_slack_markup(self):
        s, sent = slack_store(), []
        msg = {'Channel': 'slack', 'ExternalId': 'slack:C0123:1730800000.000100', 'ConversationId': 'slack:C0123', 'SourceName': 'C0123'}
        with mock.patch('taskuary.channels.requests.post', side_effect=lambda url, data=None, **kw: sent.append((url, data)) or Resp({'ok': True, 'ts': '1.2'})):
            out = outbound.reply_to_message(s, msg, 'Hi Erin - **yes**, Thursday works.')
        url, data = sent[0]
        self.assertTrue(url.endswith('chat.postMessage'))
        self.assertEqual((data['channel'], data['thread_ts']), ('C0123', '1730800000.000100'))
        self.assertEqual(data['text'], 'Hi Erin - *yes*, Thursday works.')      # Slack's bold is one star
        self.assertTrue(out['threaded'])

    def test_a_direct_message_is_answered_plainly(self):
        s, sent = slack_store(), []
        msg = {'Channel': 'slack', 'ExternalId': 'slack:D0456:1730800000.000200', 'ConversationId': 'slack:D0456', 'SourceName': 'D0456'}
        with mock.patch('taskuary.channels.requests.post', side_effect=lambda url, data=None, **kw: sent.append(data) or Resp({'ok': True})):
            outbound.reply_to_message(s, msg, 'On it.')
        self.assertNotIn('thread_ts', sent[0])

    def test_a_token_without_chat_write_says_what_to_do(self):
        s = slack_store('xoxb-test')
        msg = {'Channel': 'slack', 'ExternalId': 'slack:C0123:1.1', 'ConversationId': 'slack:C0123', 'SourceName': 'C0123'}
        with mock.patch('taskuary.channels.requests.post', return_value=Resp({'ok': False, 'error': 'missing_scope'})):
            with self.assertRaises(RuntimeError) as e: outbound.reply_to_message(s, msg, 'On it.')
        self.assertIn('chat:write', str(e.exception))


if __name__ == '__main__': unittest.main()
