"""Chat lifecycle and retention (PW-156 to PW-161).

New chat archives the conversation and opens a blank one - it deletes nothing, reads nothing as read,
and starts no walk. Listing and opening earlier chats is read-only and paginated; the old list marked
anything past twenty days `dropped` as a side effect of being looked at. Retention is its own daily
operation with a fifteen-day default the owner can change: it removes only archived guide chats whose
last word is older than the cutoff - never the open chat, never a real task - and what a chat said
about a task, confirmed actions, agent results, send outcomes, memories and rules all outlive it.
"""
import json, unittest
from datetime import datetime, timedelta
from unittest import mock

from fastapi.testclient import TestClient

from taskuary import concierge, funnel, general, operations, retention, server, terminal
from taskuary.store import MemoryStore


def ago(days=0, minutes=0): return (datetime.now() - timedelta(days=days, minutes=minutes)).strftime('%Y-%m-%d %H:%M:%S')


def store():
    s = MemoryStore()
    for k in ('calendar_enabled', 'coder_auto_enabled', 'learn_enabled', 'auto_draft_enabled'): s.set_setting(k, '0', 't')
    funnel.invalidate(); funnel.forget_states()
    return s


def chat(s, said='what is waiting?', days=0, item=None, archive=True):
    """One guide conversation, its rows stamped `days` ago, archived unless told otherwise."""
    dock, _ = general.dock_task(s)
    concierge.record_related(s, dock['TaskId'], item, 'user', said)
    concierge.record_related(s, dock['TaskId'], item, 'assistant', f'About "{said}": nothing yet.')
    s._exec('UPDATE comment SET CreatedAt=? WHERE TaskId=?', (ago(days), dock['TaskId']))
    s._exec('UPDATE task SET CreatedAt=? WHERE TaskId=?', (ago(days), dock['TaskId']))
    if archive: s.update_task(dock['TaskId'], {'Status': 'done'}, 'owner')
    return dock['TaskId']


def real_task(s, title='Fix the export'):
    t = s.create_task({'Title': title, 'Kind': 'coding', 'Status': 'open'}, 'o')
    m = s.add_message({'TaskId': t, 'ExternalId': f'x:{title}', 'ConversationId': f'c:{title}', 'Channel': 'email', 'Subject': title, 'FromName': 'Craig',
                       'FromEmail': 'craig@vendor.com', 'SentAt': ago(minutes=30), 'BodyText': 'Rows drop.', 'Status': 'routed'})
    return t, m


class NewChatTests(unittest.TestCase):
    def test_new_chat_archives_deletes_nothing_marks_nothing_and_starts_no_walk(self):
        s = store(); t, m = real_task(s)
        with mock.patch.object(terminal, 'live_sessions', return_value=[]):
            concierge.surface(s, llm=lambda *a, **k: 'Craig wants the export fixed.')       # something on the table
            old = general.dock_task(s)[0]['TaskId']
            states = dict(s.funnel_states())
            with mock.patch.object(server, 'store', s), mock.patch.dict(terminal.SESSIONS, {}, clear=True):
                c = TestClient(server.app)
                fresh = c.post('/api/assistant/dock/new').json()
                self.assertEqual(c.get('/api/concierge').json()['messages'], [])                      # blank, awaiting the owner
            self.assertEqual(s.get_task(old)['Status'], 'done'); self.assertTrue(general.chat_rows(s, old))  # archived, not deleted
            self.assertNotEqual(fresh['task']['TaskId'], old)
            self.assertEqual(general.chat_rows(s, fresh['task']['TaskId']), [])                           # no walk started itself
            self.assertEqual({k: v['Status'] for k, v in s.funnel_states().items() if v['Status'] != 'ack'},
                             {k: v['Status'] for k, v in states.items() if v['Status'] != 'ack'})          # read state as it was
            self.assertIsNone(s.get_settings().get(retention.RAN_KEY))                                    # retention did not run
            self.assertEqual(s.get_message(m)['Status'], 'routed'); self.assertEqual(s.get_task(t)['Status'], 'open')


class HistoryIsReadOnlyTests(unittest.TestCase):
    def test_listing_and_opening_old_chats_writes_nothing_and_pages(self):
        s = store()
        ids = [chat(s, f'chat {n}', days=d) for n, d in enumerate((40, 30, 20, 2))]
        before = {tid: dict(s.get_task(tid)) for tid in ids}
        first = concierge.chats(s, limit=2)
        self.assertEqual([c['taskId'] for c in first], ids[-1:-3:-1])                                     # newest first, two at a time
        second = concierge.chats(s, limit=2, before=first[-1]['taskId'])
        self.assertEqual([c['taskId'] for c in second], ids[-3::-1])                                       # ...then the forty-day-old one, still there
        self.assertEqual({tid: dict(s.get_task(tid)) for tid in ids}, before)                              # nothing changed
        self.assertFalse(hasattr(concierge, 'CHATS_KEPT_DAYS'))
        with mock.patch.object(server, 'store', s), mock.patch.dict(terminal.SESSIONS, {}, clear=True):
            c = TestClient(server.app)
            page = c.get('/api/concierge/chats', params={'limit': 2}).json()
            self.assertEqual(([x['taskId'] for x in page['data']], page['next']), (ids[-1:-3:-1], ids[-2]))
            page2 = c.get('/api/concierge/chats', params={'limit': 2, 'before': page['next']}).json()
            self.assertEqual(([x['taskId'] for x in page2['data']], page2['next']), (ids[-3::-1], ids[0]))
            self.assertEqual(c.get('/api/concierge/chats', params={'limit': 2, 'before': page2['next']}).json(), {'data': [], 'next': None})
            one = c.get(f'/api/concierge/chats/{ids[0]}').json()
            self.assertEqual([m['text'] for m in one['messages']][:1], ['chat 0'])
        self.assertEqual({tid: dict(s.get_task(tid)) for tid in ids}, before)
        self.assertIsNone(s.get_settings().get(retention.RAN_KEY))


class RetentionTests(unittest.TestCase):
    def test_fifteen_days_by_default_the_owner_can_change_it_and_the_boundary_is_exact(self):
        s = store()
        self.assertEqual(retention.keep_days(s), 15)
        old = chat(s, 'old', days=16); edge_in = chat(s, 'edge in', days=15)
        s._exec('UPDATE comment SET CreatedAt=? WHERE TaskId=?', (ago(days=15, minutes=-1), edge_in))      # a minute inside the window
        out = retention.cleanup(s)
        self.assertEqual((out['removed'], out['keep_days']), ([old], 15))
        self.assertIsNone(s.get_task(old)); self.assertTrue(s.get_task(edge_in))
        s.set_setting(retention.KEY, '3', 'owner')
        five = chat(s, 'five', days=5); two = chat(s, 'two', days=2)
        self.assertEqual(sorted(retention.cleanup(s)['removed']), sorted([edge_in, five]))                 # the override
        self.assertTrue(s.get_task(two))
        s.set_setting(retention.KEY, 'soon', 'owner'); self.assertEqual(retention.keep_days(s), 15)         # nonsense falls back

    def test_the_open_chat_and_real_tasks_are_never_touched_and_the_tick_runs_once_a_day(self):
        s = store()
        t, m = real_task(s); s._exec('UPDATE task SET CreatedAt=? WHERE TaskId=?', (ago(days=40), t))
        gone = chat(s, 'archived', days=40)
        cur = chat(s, 'today, still open', days=40, archive=False)                                        # the open guide, old rows and all
        now = datetime(2026, 9, 6, 8, 0, 0)
        first = retention.tick(s, now)
        self.assertEqual(first['removed'], [gone]); self.assertTrue(s.get_task(cur)); self.assertTrue(s.get_task(t))
        self.assertIsNone(retention.tick(s, now + timedelta(hours=5)))                                      # same day: not again
        s.update_task(cur, {'Status': 'done'}, 'owner')                                                     # archived later (New chat)...
        self.assertEqual(retention.tick(s, now + timedelta(days=1))['removed'], [cur])                       # ...goes on the next day's tick

    def test_what_a_chat_said_about_a_task_and_every_independent_record_outlive_the_archive(self):
        s = store(); t, m = real_task(s)
        item = {'key': f'msg:{m}', 'kind': 'asked', 'lane': 'asked', 'title': 'Fix the export', 'mid': m, 'tid': t}
        dock = chat(s, 'send it to the coder when the export fix is ready', days=30, item=item)
        # an fyi discussed in that chat and promoted later: its discussion travelled onto the task (PW-133)
        fyi = s.add_message({'ExternalId': 'x:fyi', 'ConversationId': 'c:fyi', 'Channel': 'email', 'Subject': 'FYI - Rebecca is back', 'FromName': 'Chana',
                             'FromEmail': 'chana@ours.com', 'SentAt': ago(days=30), 'BodyText': 'Back Tuesday.', 'Status': 'filed'})
        operations.discuss(s, 'owner', 'make this a task when she is back', message_id=fyi)
        promoted = s.create_task({'Title': 'Welcome Rebecca back', 'Kind': 'task', 'Status': 'open'}, 'o')
        operations.link_discussion(s, promoted, [fyi])
        op = operations.record_direct(s, 'task.complete', t, {}, 'owner', {'status': 'done'})
        s.add_comment(t, 'coder', 'agent', 'CODER REPORT\nSummary: fixed the export.')
        rv = s.add_review({'TaskId': t, 'MessageId': m, 'Kind': 'reply', 'DraftText': 'Fixed.', 'Status': 'approved'})
        mem = concierge.remember_fact(s, 'Hindy signs off on refunds')
        funnel.remember_mute(s, {'sender': 'nozur@hrtgcs.com', 'words': ['mfa'], 'why': 'the financials process'}, 'o')
        s.add_correction({'OpId': op['id'], 'MessageId': m, 'TaskId': t, 'Sender': 'craig@vendor.com', 'Topic': 'export', 'Verdict': 'fyi',
                          'VerdictRouteId': None, 'Change': 'coding', 'ContextJson': '{}'})
        self.assertEqual(retention.cleanup(s)['removed'], [dock])
        self.assertIsNone(s.get_task(dock))
        mirrored = [c['Body'] for c in s.list_comments(t) if c['ActorType'] in (concierge.DISCUSSION_USER_TYPE, concierge.DISCUSSION_ASSISTANT_TYPE)]
        self.assertIn('send it to the coder when the export fix is ready', mirrored)                          # readable on the task itself
        self.assertEqual([d['Body'] for d in operations.discussion(s, task_id=promoted)], ['make this a task when she is back'])
        self.assertEqual([h['type'] for h in operations.history(s, task_id=t) if h['type'] != 'discussion'], ['operation', 'correction'])
        self.assertTrue(any('CODER REPORT' in c['Body'] for c in s.list_comments(t)))
        self.assertEqual(s.get_review(rv)['Status'], 'approved')
        self.assertEqual([x['Note'] for x in s.list_memories()], ['Hindy signs off on refunds'])
        self.assertEqual([r['sender'] for r in funnel.mutes(s)], ['nozur@hrtgcs.com'])
        self.assertEqual(len(s.corrections(task_id=t)), 1)


if __name__ == '__main__':
    unittest.main()
