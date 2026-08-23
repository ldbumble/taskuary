"""The per-connector poll fix: a connection whose source row is only a marker must poll
even with NO source row at all - that was the "Telegram Sync does nothing" bug (no '*'
marker, so getUpdates never ran and no chat could ever announce itself).
"""
import unittest
from datetime import datetime, timedelta
from unittest import mock

from taskuary import channels, messengers
from taskuary.store import MemoryStore

FRESH = datetime.now() - timedelta(minutes=10)


def arm(s, typ):
    cid = s.get_connector_by_type(typ)['ConnectorId']
    s.save_connector({'ConnectorId': cid, 'Secret': 'tok', 'Active': 1}, 't')
    return s.get_connector(cid, with_secret=True)


class PerConnectorPollTests(unittest.TestCase):
    """The reported bug: Telegram Sync did nothing because the poll lived inside the
    per-source loop - no '*' marker row meant getUpdates never ran, so no chat could ever
    announce itself, and there was no error anywhere to explain it."""
    def test_telegram_polls_with_no_source_rows_at_all(self):
        s = MemoryStore(); arm(s, 'telegram')
        self.assertEqual([x for x in s.list_sources(active_only=False) if x['Channel'] == 'telegram'], [])
        with mock.patch.object(messengers, 'poll_telegram', return_value=0) as poll:
            channels.poll_channels(s)
        poll.assert_called_once()
        self.assertEqual(poll.call_args[0][2], [])          # no sources, polled anyway

    def test_unknown_chat_registers_through_a_real_sync(self):
        s = MemoryStore(); arm(s, 'telegram')
        upd = [{'update_id': 5, 'message': {'message_id': 1, 'date': int(FRESH.timestamp()),
                                            'text': 'hi', 'chat': {'id': 4242, 'title': 'Ops'},
                                            'from': {'first_name': 'Lea'}}}]
        with mock.patch.object(messengers, 'tg', lambda tok, m, **kw: upd if m == 'getUpdates' else {}):
            channels.poll_channels(s)
        src = next(x for x in s.list_sources(active_only=False) if x['Channel'] == 'telegram')
        self.assertEqual((src['Address'], src['Active']), ('4242', 0))    # discovered, OFF - approve-first

    def test_devtools_card_polls_without_a_source(self):
        s = MemoryStore(); arm(s, 'linear')
        from taskuary import devtools
        with mock.patch.object(devtools, 'poll', return_value=0) as poll:
            channels.poll_channels(s)
        poll.assert_called_once()


if __name__ == '__main__':
    unittest.main()
