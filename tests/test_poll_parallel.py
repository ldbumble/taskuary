"""Independent connector HTTP waits overlap; SQLite writes stay on one thread.

Outlook vs Slack vs GitHub do not share a conversation, so their network waits can
run at the same time. WAL still wants a single writer, and drain of the same
conversation stays sequential - that is a later pass, not this one.
"""
import threading, time, unittest
from unittest import mock

from taskuary import channels
from taskuary.store import MemoryStore


def arm(s, typ, address=None):
    cid = s.get_connector_by_type(typ)['ConnectorId']
    s.save_connector({'ConnectorId': cid, 'Secret': 'tok', 'Active': 1}, 't')
    ch = channels.CH2SRC[typ]
    addr = address or ('me@x.example' if ch == 'email' else 'C1')
    s.save_source({'Channel': ch, 'Address': addr, 'Owner': 'me', 'Active': 1,
                   'ConnectorId': cid}, 't')
    return cid


class ParallelPollTests(unittest.TestCase):
    def test_http_waits_overlap(self):
        s = MemoryStore()
        arm(s, 'outlook')
        arm(s, 'slack')
        marks = {}
        def mail(*a, **k):
            marks.setdefault('o0', time.time())
            time.sleep(0.12)
            marks['o1'] = time.time()
            return []
        def slack(*a, **k):
            marks.setdefault('s0', time.time())
            time.sleep(0.12)
            marks['s1'] = time.time()
            return {}
        with mock.patch.object(channels, '_mail_msgs', side_effect=mail), \
             mock.patch.object(channels, '_slack', side_effect=slack), \
             mock.patch.object(channels, 'graph_token', return_value='t'):
            channels.poll_channels(s)
        self.assertIn('o0', marks)
        self.assertIn('s0', marks)
        self.assertLess(marks['s0'], marks['o1'], 'slack must start before outlook finishes')
        self.assertLess(marks['o0'], marks['s1'], 'outlook must start before slack finishes')

    def test_writes_hop_onto_one_thread(self):
        s = MemoryStore()
        arm(s, 'outlook')
        arm(s, 'slack')
        ids = []
        real = type(s)._exec
        def wrapped(st, q, p=()):
            ids.append(threading.current_thread().ident)
            return real(st, q, p)
        with mock.patch.object(type(s), '_exec', wrapped), \
             mock.patch.object(channels, '_mail_msgs', return_value=[]), \
             mock.patch.object(channels, '_slack', return_value={}), \
             mock.patch.object(channels, 'graph_token', return_value='t'):
            channels.poll_channels(s)
        self.assertTrue(ids)
        self.assertEqual(len(set(ids)), 1, f'writes used threads {set(ids)}')

    def test_one_connector_does_not_need_the_pool(self):
        s = MemoryStore()
        arm(s, 'telegram')
        from taskuary import messengers
        with mock.patch.object(messengers, 'poll_telegram', return_value=0) as poll:
            channels.poll_channels(s)
        poll.assert_called_once()

    def test_poll_does_not_drain(self):
        """Drain of the same conversation stays sequential, on the poll thread, after
        the workers close. poll_channels itself must not judge."""
        s = MemoryStore()
        arm(s, 'outlook')
        arm(s, 'slack')
        with mock.patch.object(channels, '_mail_msgs', return_value=[]), \
             mock.patch.object(channels, '_slack', return_value={}), \
             mock.patch.object(channels, 'graph_token', return_value='t'), \
             mock.patch('taskuary.ingest.drain') as drain:
            channels.poll_channels(s)
        drain.assert_not_called()


if __name__ == '__main__':
    unittest.main()
