"""Background updates never advance the conversation (PW-165 to PW-170).

An agent that starts, stops to ask, or finishes used to be narrated INTO the chat by the watcher, card
and all, as if the owner had asked. Now an unsolicited update is a NOTICE on the one bottom strip: the
server keeps it on the funnel state until the owner opens it or puts it down, a newer fact about the
same task replaces the older one, a parked agent is the pile's own alert and is never kept twice, and
nothing about it marks the item read, touches the task, or moves the walk. Later puts the notice down,
not the item; a new chat does not raise a put-down notice again.
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
    s.upsert_agent('coder', 'coding', 'cli', '{}')
    for k in ('calendar_enabled', 'coder_auto_enabled', 'learn_enabled', 'auto_draft_enabled'): s.set_setting(k, '0', 't')
    funnel.invalidate(); funnel.forget_states()
    return s


def task(s, title='Import census'):
    t = s.create_task({'Title': title, 'Kind': 'coding', 'Status': 'in_progress'}, 'o')
    s.add_message({'TaskId': t, 'ExternalId': f'x:{title}', 'ConversationId': f'c:{title}', 'Channel': 'email', 'Subject': title, 'FromName': 'Chana',
                   'FromEmail': 'chana@ours.com', 'SentAt': ago(2), 'BodyText': 'Please import it.', 'Status': 'routed'})
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

    def test_a_finished_agent_is_a_notice_on_the_strip_and_not_a_line_in_the_chat(self):
        s = store(); t = task(s); dock = general.dock_task(s)[0]['TaskId']
        self.assertEqual(self._events(s, live(t)), [])                                  # the first look only remembers
        s.add_comment(t, 'codex', 'agent', 'CODER REPORT\nSummary: imported all 80 files.')
        s.update_task(t, {'Status': 'done'}, 'o')
        ev = self._events(s, [])
        self.assertEqual([(e['kind'], e['card']) for e in ev], [('done', None)])
        self.assertEqual(concierge.history(s, dock), [])                                # nothing written into the chat (PW-165)
        notice = [a for a in self._alerts(s) if a.get('notice')]
        self.assertEqual([(a['key'], a['item'], a['kind']) for a in notice], [(f'notice:{t}', f'task:{t}', 'done')])
        self.assertIn('imported all 80 files', notice[0]['text'])
        # it STAYS - a second look, a later poll, a reload all find it (PW-166) - and it is not repeated
        self.assertEqual(self._events(s, []), [])
        self.assertEqual(len([a for a in self._alerts(s) if a.get('notice')]), 1)

    def test_a_parked_agent_is_the_piles_own_alert_and_is_never_kept_twice(self):
        s = store(); t = task(s); dock = general.dock_task(s)[0]['TaskId']
        self._events(s, live(t))
        asking = live(t, idle=200, waiting=True, tail=['Which cutoff should I use?'])
        ev = self._events(s, asking)
        self.assertEqual([e['kind'] for e in ev], ['asking']); self.assertIsNone(ev[0]['card'])
        self.assertEqual(concierge.history(s, dock), [])
        al = self._alerts(s, asking)
        self.assertEqual([a['key'] for a in al if a['kind'] == 'agent'], [f'alert:agent:{t}'])
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
        self.assertEqual([a['kind'] for a in self._alerts(s) if a.get('notice')], ['done'])   # one notice per task

    def test_later_puts_the_notice_down_and_nothing_else(self):
        s = store(); t = task(s)
        self._events(s, live(t)); s.update_task(t, {'Status': 'done'}, 'o'); self._events(s, [])
        key = f'notice:{t}'
        with mock.patch.object(server, 'store', s), mock.patch.object(terminal, 'live_sessions', return_value=[]):
            c = TestClient(server.app)
            self.assertEqual(c.post('/api/funnel/settle', json={'key': key, 'verb': 'ack'}).json()['verb'], 'ack')
            self.assertEqual([a for a in c.get('/api/funnel/pile?force=1').json()['alerts'] if a.get('notice')], [])
        self.assertEqual(s.get_task(t)['Status'], 'done')                                # the task is as it was
        self.assertEqual({k: v['Status'] for k, v in s.funnel_states().items() if not k.startswith('notice:')}, {})   # no item was marked
        funnel.reset_walk(s)                                                             # a new chat...
        self.assertEqual([a for a in self._alerts(s) if a.get('notice')], [])            # ...does not raise it again
        self.assertNotIn(key, s.funnel_states())

    def test_a_walk_on_is_the_owners_move_never_the_watchers(self):
        s = store(); t = task(s)
        other = task(s, 'Refund for Mrs Garnett'); s.update_task(other, {'Status': 'open'}, 'o')
        with mock.patch.object(terminal, 'live_sessions', return_value=[]):
            first = concierge.surface(s, llm=lambda *a, **k: 'never asked')['item']          # something on the table
        dock = general.dock_task(s)[0]['TaskId']
        n = len(concierge.history(s, dock))
        self._events(s, live(t)); s.update_task(t, {'Status': 'done'}, 'o')
        with mock.patch.object(terminal, 'live_sessions', return_value=[]): p = funnel.pile(s, force=True)
        self.assertEqual([e['kind'] for e in p['events']], ['done'])
        self.assertEqual(len(concierge.history(s, dock)), n)                              # no turn of the assistant's own
        with mock.patch.object(terminal, 'live_sessions', return_value=[]):
            self.assertEqual(funnel.next_item(s, first['key'], include_surfaced=True)['key'], first['key'])   # still on the table
        self.assertEqual(s.funnel_states()[first['key']]['Status'], 'surfaced')


if __name__ == '__main__':
    unittest.main()
