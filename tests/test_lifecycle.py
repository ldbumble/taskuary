"""The whole loop, one scenario, no model: a mail arrives and is triaged -> it is in the pipe -> the chat
opens with the day -> the owner starts and the item comes out onto the table -> the owner hands it to the
coder in words -> the coder works (in hand, at the top), stops to ask (front, card), finishes (the watcher
says so, offers the report) -> its reply waits for the yes -> approving sends and closes the task -> the
pipe is empty and says so. Every state is asserted where the owner would see it: the pile, the chat, the
task. If any link breaks, this is the test that says which."""
import unittest
from datetime import datetime, timedelta
from unittest import mock

from fastapi.testclient import TestClient

from taskuary import concierge, funnel, general, server, terminal, verdicts
from taskuary.store import MemoryStore


def ago(hours=0, minutes=0): return (datetime.now() - timedelta(hours=hours, minutes=minutes)).strftime('%Y-%m-%d %H:%M:%S')


class LifecycleTests(unittest.TestCase):
    def setUp(self):
        self.s = MemoryStore()
        self.s.upsert_agent('coder', 'coding', 'cli', '{}')     # config.toml seeds one at boot
        for k in ('calendar_enabled', 'coder_auto_enabled', 'learn_enabled', 'auto_draft_enabled'): self.s.set_setting(k, '0', 't')
        funnel.invalidate(); funnel.forget_states()
        self.no_model = mock.patch.object(concierge, 'brain', return_value=None); self.no_model.start(); self.addCleanup(self.no_model.stop)

    def chat(self):
        return [(h['role'], h['text'][:70], (h['card'] or {}).get('kind')) for h in concierge.history(self.s, general.dock_task(self.s)[0]['TaskId'])]

    def test_from_mail_to_closed_task(self):
        s = self.s
        # 1. a person asks; triage made it a coding task with nobody on it
        t = s.create_task({'Title': 'T&E portal', 'Kind': 'coding', 'Status': 'open'}, 'router')
        m = s.add_message({'TaskId': t, 'ExternalId': 'x:te', 'ConversationId': 'te', 'Channel': 'email', 'Subject': 'RE: T&E Portal', 'FromName': 'Craig',
                           'FromEmail': 'craig@mfa.com', 'SentAt': ago(1), 'BodyText': 'I still see Bulk approve - can you turn it off?', 'Status': 'routed'})
        s.add_route(m, t, 'create', .9, 'a concrete ask', [], 'router')
        with mock.patch('taskuary.terminal.live_sessions', return_value=[]):
            p = funnel.pile(s, force=True)
        self.assertEqual([(i['kind'], i['lane'], i['coding']) for i in p['items']], [('todo', 'asked', True)])
        # 2. the chat opens with the day, nothing on the table yet
        opened = concierge.open_day(s)
        self.assertTrue(opened['opened']); self.assertEqual(opened['card']['n'], 1)
        # 3. the owner starts; the item comes onto the table in three beats
        with mock.patch('taskuary.terminal.live_sessions', return_value=[]):
            out = concierge.surface(s, only='mail')
        self.assertEqual(out['item']['key'], f'msg:{m}')
        self.assertIn('Craig wrote on email', out['say']); self.assertIn('From you:', out['say'])
        # 4. the owner decides in words: hand it to the coder, with every word of the ask
        with mock.patch('taskuary.terminal.live_sessions', return_value=[]):
            said = concierge.say(s, 'send it to the coding agent and find out why the old fix did not stick', key=f'msg:{m}')
        self.assertEqual(said['decision']['verb'], 'coder'); self.assertIn('old fix did not stick', said['decision']['text'])
        # ...and 'next' costs no model call at all: the introduction is the facts
        self.assertFalse(concierge.INTRO_AI)
        self.assertIn('Sent off to the coding agent', said['say']); self.assertIn('watch it on the Board', said['say'])
        # 5. the coder works: the item rides at the top, in hand, under the agent's key; the watcher says so.
        # The watcher only believes a state that HOLDS (funnel.DWELL, so a moment of quiet is not "it
        # stopped") - this walk changes state on purpose, line by line, so it opts out of the wait.
        dwell = mock.patch.object(funnel, 'DWELL', 0); dwell.start(); self.addCleanup(dwell.stop)
        working = [{'taskId': t, 'agent': 'coder', 'label': 'coder', 'started': ago(0), 'idle': 2, 'waiting': False, 'tail': ['reading…']}]
        s.update_task(t, {'Status': 'in_progress'}, 'router')
        with mock.patch('taskuary.terminal.live_sessions', return_value=working):
            funnel.announce(s)                                                   # first look remembers
            p = funnel.pile(s, force=True)
            self.assertIsNone(funnel.next_item(s))
        self.assertEqual([(i['key'], i['lane']) for i in p['items']], [(f'agent:{t}', 'working')])
        # 6. it stops to ask: front of the pipe, a line in the chat with the card
        parked = [dict(working[0], idle=120, waiting=True, tail=['Remove Bulk Deny as well? (y/n)'])]
        with mock.patch('taskuary.terminal.live_sessions', return_value=parked):
            ev = funnel.pile(s, force=True)['events']
            self.assertEqual([e['kind'] for e in ev], ['asking'])
            self.assertEqual(funnel.next_item(s)['kind'], 'agent')
            out = concierge.surface(s)
        self.assertEqual(out['item']['kind'], 'agent'); self.assertIn('asked: Remove Bulk Deny as well?', out['say'])
        # 7. it finishes with a report and drafts the reply; the watcher offers the report, the pipe holds the draft
        s.add_comment(t, 'coder', 'agent', 'CODER REPORT' + chr(10) + 'Summary: removed Bulk Approve and Deny; deployed.')
        r = s.add_review({'TaskId': t, 'MessageId': m, 'Kind': 'reply', 'DraftText': 'Done - both are off now.', 'Status': 'pending'})
        s.update_task(t, {'Status': 'waiting'}, 'coder')
        with mock.patch('taskuary.terminal.live_sessions', return_value=[]):
            p = funnel.pile(s, force=True)
        self.assertEqual([(i['kind'], i['lane']) for i in p['items']], [('review', 'approve')])
        self.assertIn('removed Bulk Approve and Deny', p['items'][0]['summary'])
        with mock.patch('taskuary.terminal.live_sessions', return_value=[]):
            out = concierge.surface(s)
        self.assertEqual(out['item']['rid'], r); self.assertIn('the agent removed Bulk Approve and Deny', out['say']); self.assertIn('approve the draft below', out['say'])
        # 8. approving sends and CLOSES the task; the pipe empties and says so
        sent = {'channel': 'email', 'to': ['craig@mfa.com'], 'cc': []}
        with mock.patch('taskuary.outbound.reply_to_message', return_value=sent), mock.patch('taskuary.terminal.live_sessions', return_value=[]):
            done = verdicts.decide(s, s.get_review(r), 'approve', 'Done - both are off now.', None, 'owner')
        self.assertTrue(done['ok']); self.assertEqual(s.get_task(t)['Status'], 'done')
        with mock.patch('taskuary.terminal.live_sessions', return_value=[]):
            p = funnel.pile(s, force=True)
            self.assertEqual([e['kind'] for e in p['events']], ['done'])        # the watcher offers the report, on the table
            self.assertEqual(p['items'], [])
            out = concierge.surface(s)
        self.assertIsNone(out['item']); self.assertEqual(out['say'], concierge.ALL_DONE)
        # 9. the whole conversation reads as the day it was
        roles = self.chat()
        self.assertEqual([c for _, _, c in roles if c], ['brief', 'todo', 'agent', 'agent', 'review'])   # closed is a status line, never a live card
        self.assertEqual([r for r, _, _ in roles].count('user'), 1)

    def test_the_page_walks_the_same_loop(self):
        s = self.s
        t = s.create_task({'Title': 'Invoice question', 'Kind': 'coding', 'Status': 'waiting'}, 'router')
        m = s.add_message({'TaskId': t, 'ExternalId': 'x:inv', 'ConversationId': 'inv', 'Channel': 'email', 'Subject': 'Invoice 4471', 'FromName': 'Sam',
                           'FromEmail': 'sam@vendor.com', 'SentAt': ago(2), 'BodyText': 'Can you resend invoice 4471?', 'Status': 'routed'})
        r = s.add_review({'TaskId': t, 'MessageId': m, 'Kind': 'reply', 'DraftText': 'Resent - see attached.', 'Status': 'pending'})
        with mock.patch.object(server, 'store', s), mock.patch.dict(terminal.SESSIONS, {}, clear=True), \
             mock.patch('taskuary.outbound.reply_to_message', return_value={'channel': 'email', 'to': ['sam@vendor.com'], 'cc': []}):
            c = TestClient(server.app)
            self.assertTrue(c.post('/api/concierge/open').json()['opened'])
            nxt = c.post('/api/concierge/next', json={'only': 'mail'}).json()
            self.assertEqual(nxt['item']['rid'], r)
            self.assertEqual(c.get('/api/funnel/pile?force=1').json()['items'][0]['surfaced'], True)      # on the table, still in the pipe
            said = c.post('/api/concierge/say', json={'text': 'looks good, send it', 'key': f'review:{r}'}).json()
            self.assertEqual(said['decision']['verb'], 'approve'); self.assertEqual(said['say'], 'Sending it as drafted. Moving on.')   # a word too
            decided = c.post(f'/api/reviews/{r}/decide', json={'verb': 'approve', 'final_text': 'Resent - see attached.', 'note': None}).json()
            self.assertTrue(decided['ok'])
            self.assertEqual(c.get(f'/api/tasks/{t}').json()['task']['Status'], 'done')
            self.assertEqual(c.get('/api/funnel/pile?force=1').json()['items'], [])
            self.assertEqual(c.post('/api/concierge/next', json={}).json()['say'], concierge.ALL_DONE)


if __name__ == '__main__':
    unittest.main()
