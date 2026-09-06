"""Opening Assistant restores, it does not start (PW-162 to PW-164).

Current used to be inferred on the page from the last card in the transcript, so a handled item came back
as live work after a reload. Now the server writes the item down as it is put on the table
(`concierge.set_current`), validates it against the pile when the conversation is read back
(`restore_current`), and clears it - choosing nothing in its place - when the item was settled, closed,
or is simply gone. Reading the state never adds a turn.
"""
import unittest
from datetime import datetime, timedelta
from unittest import mock

from fastapi.testclient import TestClient

from taskuary import concierge, funnel, general, server, terminal
from taskuary.store import MemoryStore


def ago(hours=0): return (datetime.now() - timedelta(hours=hours)).strftime('%Y-%m-%d %H:%M:%S')


def store():
    s = MemoryStore()
    for k in ('calendar_enabled', 'coder_auto_enabled', 'learn_enabled', 'auto_draft_enabled'): s.set_setting(k, '0', 't')
    s.set_setting('team_domains', 'ours.com', 't')
    funnel.invalidate(); funnel.forget_states()
    return s


def asked(s, title='Fix the export', who='Craig', hours=2):
    t = s.create_task({'Title': title, 'Kind': 'coding', 'Status': 'open'}, 'o')
    m = s.add_message({'TaskId': t, 'ExternalId': f'x:{title}', 'ConversationId': f'c:{title}', 'Channel': 'email', 'Subject': title, 'FromName': who,
                       'FromEmail': f'{who.lower()}@vendor.com', 'SentAt': ago(hours), 'BodyText': 'Rows drop.', 'Status': 'routed'})
    return t, m


def client(s):
    patches = [mock.patch.object(server, 'store', s), mock.patch.dict(terminal.SESSIONS, {}, clear=True),
               mock.patch.object(terminal, 'live_sessions', return_value=[]), mock.patch.object(concierge, 'brain', return_value=None)]
    return patches, TestClient(server.app)


class RestoreTests(unittest.TestCase):
    def setUp(self):
        self.s = store()
        self.patches, self.c = client(self.s)
        for p in self.patches: p.start(); self.addCleanup(p.stop)

    def test_a_first_visit_restores_nothing_and_starts_nothing(self):
        asked(self.s)
        st = self.c.get('/api/concierge').json()
        self.assertEqual((st['messages'], st['current']), ([], None))
        self.assertEqual(self.c.get('/api/concierge').json()['messages'], [])                          # reading twice adds nothing
        self.assertEqual(funnel.build(self.s, keep_surfaced=True)['items'][0].get('surfaced'), None)    # nothing was put on the table

    def test_a_reload_restores_the_item_on_the_table_without_a_new_turn(self):
        t, m = asked(self.s)
        nxt = self.c.post('/api/concierge/next', json={}).json()
        self.assertEqual(nxt['item']['key'], f'msg:{m}')
        before = self.c.get('/api/concierge').json()
        self.assertEqual((before['current']['key'], before['current']['kind'], len(before['messages'])), (f'msg:{m}', 'todo', 1))
        again = self.c.get('/api/concierge').json()                                                     # a tab switch, a reload, a reconnect
        self.assertEqual((again['current']['key'], len(again['messages'])), (f'msg:{m}', 1))
        self.assertEqual(concierge.current_key(self.s, general.dock_task(self.s)[0]['TaskId']), f'msg:{m}')

    def test_a_handled_item_stays_readable_history_but_is_not_revived(self):
        t, m = asked(self.s)
        self.c.post('/api/concierge/next', json={})
        self.c.post('/api/funnel/settle', json={'key': f'msg:{m}', 'verb': 'done'})
        st = self.c.get('/api/concierge').json()
        self.assertIsNone(st['current']); self.assertEqual(st['messages'][0]['card']['key'], f'msg:{m}')   # the card is still in the transcript
        self.assertEqual(concierge.current_key(self.s, general.dock_task(self.s)[0]['TaskId']), '')
        # deferring clears it the same way, and so does a task that closed underneath it
        t2, m2 = asked(self.s, 'Invoice 4471', 'Sam', 1)
        self.c.post('/api/concierge/next', json={})
        self.c.post('/api/funnel/settle', json={'key': f'msg:{m2}', 'verb': 'later'})
        self.assertIsNone(self.c.get('/api/concierge').json()['current'])
        t3, m3 = asked(self.s, 'PTO import', 'Chana', 0)
        self.assertEqual(self.c.post('/api/concierge/next', json={}).json()['item']['key'], f'msg:{m3}')
        self.s.update_task(t3, {'Status': 'done'}, 'owner'); funnel.invalidate()
        st = self.c.get('/api/concierge').json()
        self.assertIsNone(st['current'])                                                                # gone, and nothing chosen instead
        self.assertEqual(len([x for x in st['messages'] if x['card']]), 3)                              # no turn was added by the read

    def test_a_named_item_and_the_fyi_handful_are_written_down_too(self):
        t, m = asked(self.s)
        other_t, other_m = asked(self.s, 'Refund for Mrs Garnett', 'Rivka', 1)
        self.c.post('/api/concierge/next', json={})
        self.c.post('/api/concierge/next', json={'key': f'msg:{other_m}'})                                # the owner pulled another in
        self.assertEqual(self.c.get('/api/concierge').json()['current']['key'], f'msg:{other_m}')
        s2 = store(); patches, c2 = client(s2)
        for p in patches: p.start(); self.addCleanup(p.stop)
        for n in range(2):
            mm = s2.add_message({'ExternalId': f'f{n}', 'ConversationId': f'f{n}', 'Channel': 'email', 'Subject': f'FYI {n}', 'FromName': 'Chana',
                                 'FromEmail': 'chana@ours.com', 'SentAt': ago(n), 'BodyText': 'fyi', 'Status': 'filed'})
            s2.add_route(mm, None, 'file', None, 'triage: fyi', [], 'triage')
        batch = c2.post('/api/concierge/next', json={}).json()['item']
        self.assertEqual(batch['kind'], 'fyis')
        cur = c2.get('/api/concierge').json()['current']
        self.assertEqual((cur['key'], cur['kind'], len(cur['items'])), (batch['key'], 'fyis', 2))

    def test_a_new_chat_has_nothing_on_the_table(self):
        t, m = asked(self.s)
        self.c.post('/api/concierge/next', json={})
        self.c.post('/api/assistant/dock/new')
        st = self.c.get('/api/concierge').json()
        self.assertEqual((st['messages'], st['current']), ([], None))


if __name__ == '__main__':
    unittest.main()
