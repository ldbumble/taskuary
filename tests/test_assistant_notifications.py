"""Background updates never advance the conversation (PW-165 to PW-170).

An agent that starts, stops to ask, or finishes used to be narrated INTO the chat by the watcher, card
and all, as if the owner had asked. Now an unsolicited update is a NOTICE on the one bottom strip: the
server keeps it on the funnel state until the owner opens it or puts it down, a newer fact about the
same task replaces the older one, a parked agent is the pile's own alert and is never kept twice, and
nothing about it marks the item read, touches the task, or moves the walk. Later puts the notice down,
not the item; a new chat does not raise a put-down notice again.

And a FINISHED task is no update at all (2026-09-14): the strip is what waits on the owner, so a closed
task leaves neither a row nor a spoken line - only what the agent left behind, which the pile raises.
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
    s.upsert_agent('coding', 'coding', 'cli', '{}')
    for k in ('calendar_enabled', 'coding_auto_enabled', 'auto_draft_enabled'): s.set_setting(k, '0', 't')
    funnel.invalidate(); funnel.forget_states()
    return s


def task(s, title='Import census'):
    t = s.create_task({'Title': title, 'Kind': 'coding', 'Status': 'in_progress'}, 'o')
    s.add_message({'TaskId': t, 'ExternalId': f'x:{title}', 'ConversationId': f'c:{title}', 'Channel': 'email', 'Subject': title, 'FromName': 'Erin',
                   'FromEmail': 'erin@ours.com', 'SentAt': ago(2), 'BodyText': 'Please import it.', 'Status': 'routed'})
    return t


def live(tid, **kw):
    return [{'taskId': tid, 'agent': 'codex', 'label': 'codex', 'started': ago(1), 'idle': 2, 'waiting': False, 'tail': ['editing'], **kw}]


class WatcherTests(unittest.TestCase):
    def setUp(self):
        p = mock.patch.object(funnel, 'DWELL', 0); p.start(); self.addCleanup(p.stop)

    def _events(self, s, sessions):
        with mock.patch.object(terminal, 'live_sessions', return_value=sessions): return funnel.announce(s)

    def _alerts(self, s, sessions=()):
        with mock.patch.object(terminal, 'live_sessions', return_value=list(sessions)): return funnel.pile(s, force=True)['alerts']

    def test_a_finished_agent_leaves_nothing_on_the_strip_and_nothing_in_the_chat(self):
        s = store(); t = task(s); dock = general.dock_task(s)[0]['TaskId']
        self.assertEqual(self._events(s, live(t)), [])                                  # the first look only remembers
        s.add_comment(t, 'codex', 'agent', 'AGENT REPORT\nSummary: imported all 80 files.')
        s.update_task(t, {'Status': 'done'}, 'o')
        ev = self._events(s, [])
        self.assertEqual([(e['kind'], e['card']) for e in ev], [('done', None)])        # the transition is still SEEN...
        self.assertEqual(concierge.history(s, dock), [])                                # nothing written into the chat (PW-165)
        self.assertEqual([a for a in self._alerts(s) if a.get('notice')], [])           # ...and it asks the owner for nothing
        self.assertNotIn(f'notice:{t}', s.funnel_states())
        self.assertEqual(self._events(s, []), [])                                       # a closed task is not watched again

    def test_a_parked_agent_is_the_piles_own_alert_and_is_never_kept_twice(self):
        s = store(); t = task(s); dock = general.dock_task(s)[0]['TaskId']
        self._events(s, live(t))
        asking = live(t, idle=200, waiting=True, state='asking', tail=['Which cutoff should I use?'])     # the session's own reading
        ev = self._events(s, asking)
        self.assertEqual([e['kind'] for e in ev], ['asking']); self.assertIsNone(ev[0]['card'])
        self.assertEqual(concierge.history(s, dock), [])
        al = self._alerts(s, asking)
        row = next(i for i in funnel.pile(s)['items'] if f'agent:{t}' in i['aliases'])
        self.assertEqual([a['key'] for a in al if a['kind'] == 'agent'], [f"alert:{row['key']}"])
        self.assertEqual([a for a in al if a.get('notice')], [])                        # one surface, one entry

    def test_a_newer_fact_about_the_same_task_replaces_the_older_notice(self):
        s = store(); t = task(s)
        self._events(s, live(t, idle=200, waiting=True, tail=['ok?']))                  # first look: parked, remembered
        ev = self._events(s, live(t))                                                   # ...then it works
        self.assertEqual([e['kind'] for e in ev], ['working'])
        self.assertEqual([a['kind'] for a in self._alerts(s, live(t)) if a.get('notice')], ['working'])
        self.assertNotIn('next thing', ev[0]['text'])                                   # not a nudge to advance (PW-168)
        s.update_task(t, {'Status': 'done'}, 'o')
        self._events(s, [])
        self.assertEqual([a for a in self._alerts(s) if a.get('notice')], [])            # and finishing takes the row away

    def test_later_puts_the_notice_down_and_nothing_else(self):
        s = store(); t = task(s)
        self._events(s, live(t, idle=200, waiting=True, tail=['ok?']))                   # first look: parked, remembered
        self._events(s, live(t))                                                         # ...then it starts working: a notice
        key = f'notice:{t}'
        self.assertEqual([a['kind'] for a in self._alerts(s, live(t)) if a.get('notice')], ['working'])
        with mock.patch.object(server, 'store', s), mock.patch.object(terminal, 'live_sessions', return_value=live(t)):
            c = TestClient(server.app)
            self.assertEqual(c.post('/api/funnel/settle', json={'key': key, 'verb': 'ack'}).json()['verb'], 'ack')
            self.assertNotIn('alerts', c.get('/api/funnel/pile?force=1').json())     # the desk reads no alerts at all (2026-11-10)
        self.assertEqual([a for a in self._alerts(s, live(t)) if a.get('notice')], [])   # ...and the phone's own are put down
        self.assertEqual(s.get_task(t)['Status'], 'in_progress')                        # the task is as it was
        self.assertEqual({k: v['Status'] for k, v in s.funnel_states().items() if not k.startswith('notice:')}, {})   # no item was marked
        funnel.reset_walk(s)                                                             # a new chat...
        self.assertEqual([a for a in self._alerts(s, live(t)) if a.get('notice')], [])   # ...does not raise it again
        self.assertNotIn(key, s.funnel_states())

    def test_a_walk_on_is_the_owners_move_never_the_watchers(self):
        s = store(); t = task(s)
        other = task(s, 'Refund for Mrs Garnett'); s.update_task(other, {'Status': 'open'}, 'o')
        # ...the OTHER task on the table: the walk takes the in-progress one too now, in its place (2026-10-21), and this one closes below
        with mock.patch.object(terminal, 'live_sessions', return_value=[]):
            key = next(i['key'] for i in funnel.build(s)['items'] if i.get('tid') == other)
            first = concierge.surface(s, key=key, llm=lambda *a, **k: 'never asked')['item']   # something on the table
        dock = general.dock_task(s)[0]['TaskId']
        n = len(concierge.history(s, dock))
        self._events(s, live(t)); s.update_task(t, {'Status': 'done'}, 'o')
        with mock.patch.object(terminal, 'live_sessions', return_value=[]): p = funnel.pile(s, force=True)
        self.assertEqual([e['kind'] for e in p['events']], ['done'])
        self.assertEqual(len(concierge.history(s, dock)), n)                              # no turn of the assistant's own
        with mock.patch.object(terminal, 'live_sessions', return_value=[]):
            self.assertEqual(funnel.next_item(s, first['key'], include_surfaced=True)['key'], first['key'])   # still on the table
        self.assertEqual(s.funnel_states()[first['key']]['Status'], 'surfaced')

    def test_no_news_of_a_task_reaches_the_assistants_chat(self):
        """THE ASSISTANT HEARS ONLY WHAT IT IS ASKED (the owner, 2026-11-10: "i still see the assistant gets numbers in the corner of messages
        that happens on tasks ... the agents don't tell the assistant anything unless you ask assistant questions"). Each kind of news on the
        task on the table - its agent asked, a draft, a card waiting, new mail, a Send pressed that failed, one that went, its agent done -
        leaves the Assistant's conversation as it was: the pill counts lines of it (AssistantView unseenAnswers)."""
        from taskuary import operations
        s = store(); t = task(s)
        with mock.patch.object(terminal, 'live_sessions', return_value=[]):
            key = next(i['key'] for i in funnel.build(s)['items'] if i.get('tid') == t)
            concierge.surface(s, key=key, llm=lambda *a, **k: 'never asked')                          # the task is on the table
        dock = general.dock_task(s)[0]['TaskId']
        said = lambda: [(m['role'], m['text']) for m in concierge.history(s, dock)]
        before = said()
        self._events(s, live(t)); self._events(s, live(t, idle=200, waiting=True, state='asking', tail=['Which cutoff?']))
        self.assertEqual(said(), before, 'its agent asked')
        mid = s.add_message({'TaskId': t, 'ExternalId': 'x:2', 'ConversationId': 'c:Import census', 'Channel': 'email', 'Subject': 'Re: Import census',
                             'FromName': 'Erin', 'FromEmail': 'erin@northwind.example', 'SentAt': ago(0), 'BodyText': 'Any news?', 'Status': 'routed'})
        rid = s.add_review({'TaskId': t, 'MessageId': mid, 'Kind': 'reply', 'DraftText': 'Tomorrow.', 'Status': 'pending'})
        operations.propose(s, 'task.complete', t, {}, 'agent')
        with mock.patch.object(terminal, 'live_sessions', return_value=[]): funnel.pile(s, force=True)
        self.assertEqual(said(), before, 'new mail, a draft and a card waiting')
        with mock.patch.object(server, 'store', s), mock.patch.object(terminal, 'live_sessions', return_value=[]):
            c = TestClient(server.app)
            for run, what in ((mock.Mock(side_effect=RuntimeError('the mail server refused it')), 'a Send that failed'), (mock.Mock(return_value={}), 'a Send that went')):
                op = c.post('/api/operations', json={'kind': 'review.approve', 'target': rid, 'params': {}}).json()
                with mock.patch.object(server, '_run_operation', run): out = c.post(f"/api/operations/{op['id']}/execute", json={'version': op['version']}).json()
                self.assertTrue(out.get('receipt'), f'{what} still answers the press that made it')
                self.assertEqual(said(), before, what)
        s.add_comment(t, 'codex', 'agent', 'AGENT REPORT\nSummary: imported all 80 files.'); self._events(s, [])
        self.assertEqual(said(), before, 'its agent finished')


if __name__ == '__main__':
    unittest.main()
