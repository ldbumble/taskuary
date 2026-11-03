"""Triage's fourth verdict, watch (the owner, 2026-11-03: "a task you care about but you don't have to take care of it").

A thread the owner cares about that somebody else will handle - typically a colleague on the To line who has answered asks like it
(answered_before). It becomes a task already under Watching (watch.py): walked after Tasks, back when its thread moves, Mark done lit
once someone else dealt with it. Watch it / Stop watching on a triaged item are corrections triage learns from."""
import json, unittest
from datetime import datetime, timedelta
from unittest import mock

from taskuary import categories, evalset, funnel, ingest, operations, rulebook, triage, watch
from taskuary.store import MemoryStore

WHY = 'Gail Moreno has answered the last three access asks from Erin - she is expected to handle this one'


def ago(hours=0): return (datetime.now() - timedelta(hours=hours)).strftime('%Y-%m-%d %H:%M:%S')


def store():
    s = MemoryStore()
    for k in ('calendar_enabled', 'coding_auto_enabled'): s.set_setting(k, '0', 't')
    funnel.invalidate(); funnel.forget_states(); funnel._CACHE.update(cands_at=0.0, cands=[])
    return s


def brain(intent, why=WHY, seen=None, **extra):
    def llm(system, user, **k):
        if seen is not None: seen.append({'sys': system, 'usr': user})
        return json.dumps({'intent': intent, 'why': why, 'title': 'Portal access for the new starter', 'summary': 's',
                           **({'kind': 'task'} if intent == 'task' else {}), **extra})
    return llm


def mail(s, xid, llm, frm='erin@northwind.example', name='Erin Blake', body='Can someone set up portal access for the new starter?', hours=0):
    with mock.patch.object(ingest, '_spawn'):
        return ingest.ingest_message(s, {'external_id': xid, 'channel': 'email', 'from_email': frm, 'from_name': name,
                                         'conversation_id': 'conv-portal', 'subject': 'Portal access', 'body': body,
                                         'to': [{'name': 'Gail Moreno', 'email': 'gail@northwind.example'},
                                                {'name': 'Alex Doyle', 'email': 'alex@northwind.example'}],
                                         'sent_at': ago(hours)}, llm=llm)


class VerdictTests(unittest.TestCase):
    def test_watch_is_a_verdict_the_schema_and_the_parser_take(self):
        self.assertIn('watch', triage.verdict_schema()['schema']['properties']['intent']['enum'])
        v = triage.classify_intent({'subject': 'Portal access', 'body': 'x', 'from_email': 'erin@northwind.example'}, llm=brain('watch'))
        self.assertEqual((v['intent'], v['why']), ('watch', WHY))

    def test_the_guide_explains_watch_and_an_older_document_is_given_it(self):
        self.assertIn('- **watch** -', triage.SHIPPED)
        self.assertIn('"intent": "task|reply_only|watch|fyi"', triage.SHIPPED)
        self.assertIn('watch for the owner when they would still want to know how it ends', triage.SHIPPED)
        seen = []
        triage.classify_intent({'subject': 'Portal access', 'body': 'x'}, llm=brain('fyi', seen=seen), system='Judge mail. Answer task or fyi.')
        self.assertIn(triage.WATCH, seen[-1]['sys'], 'a document written before watch never names it, so its bullet rides along')
        seen = []
        triage.classify_intent({'subject': 'Portal access', 'body': 'x'}, llm=brain('fyi', seen=seen), system=triage.SHIPPED)
        self.assertEqual(seen[-1]['sys'].count('- **watch** -'), 1, 'the shipped guide says it once')

    def test_the_route_record_reads_watch_back(self):
        head = categories.route_head('watch', 'task')
        self.assertEqual(categories.route_intent(f'triage: {head} - {WHY}'), 'watch')
        self.assertEqual(categories.route_intent('triage: watch - x'), 'watch')


class IngestTests(unittest.TestCase):
    def test_a_watch_opens_a_task_already_under_watching_with_nothing_working_it(self):
        s = store(); out = mail(s, 'p1', brain('watch'))
        self.assertEqual(out['status'], 'created')
        t = s.get_task(out['task_id'])
        self.assertTrue(watch.watching(t), 'a watch verdict lands under Watching, as Watch it does')
        self.assertEqual((t['Status'], t['Kind']), ('open', 'task'))
        self.assertFalse(s.list_reviews('pending'), 'nothing is drafted for a thread someone else handles')
        reason = s.message_routes(out['message_id'])[-1]['Reason']
        self.assertTrue(reason.startswith('triage: watching - Gail Moreno'), reason)
        self.assertTrue(any('Gail Moreno' in c['Body'] for c in s.list_comments(out['task_id'])), 'the task says who is expected to handle it')
        self.assertEqual(s.task_verdict(out['task_id'])['intent'], 'watch')

    def test_the_thread_moving_brings_it_back_and_handled_lights_mark_done(self):
        s = store(); tid = mail(s, 'p1', brain('watch'), hours=3)['task_id']
        got = mail(s, 'p2', brain('fyi', why='Gail says it is done', handled_elsewhere=True), frm='gail@northwind.example', name='Gail Moreno',
                   body='Done - the starter can log in now.')
        self.assertEqual((got['status'], got['task_id']), ('filed', tid))
        t = s.get_task(tid)
        self.assertEqual((t['Status'], t['WatchBack'], bool(t['WatchedAt'])), ('open', 'handled', False), 'a watch comes back, never closed for the owner')
        st, _ = rulebook.state(s, {'tid': tid, 'kind': 'task', 'lane': 'yours', 'key': f'task:{tid}'}, [{'verb': 'close'}])
        self.assertEqual(st, 'watch_handled')

    def test_a_watch_on_a_line_that_joins_open_work_is_kept_for_the_chain(self):
        s = store(); tid = mail(s, 'p1', brain('task'), hours=3)['task_id']
        got = mail(s, 'p2', brain('watch', why='Gail is taking this one'), frm='gail@northwind.example', name='Gail Moreno', body='I will take this.')
        self.assertEqual((got['status'], got['task_id']), ('filed', tid))
        self.assertEqual(len(s.list_tasks()), 1)
        self.assertIn('triage: watching - Gail is taking this one', s.message_routes(got['message_id'])[-1]['Reason'])


class LearningTests(unittest.TestCase):
    def press(self, s, tid, off=False):
        operations.record_direct(s, 'task.watching', tid, {'off': True} if off else {}, 'owner', {'taskId': tid, 'watching': not off})

    def test_stop_watching_a_triaged_watch_teaches_task(self):
        s = store(); out = mail(s, 'p1', brain('watch'))
        self.assertEqual(operations.verdict_of_task(s, out['task_id'])[0], 'watch')
        watch.stop(s, out['task_id']); self.press(s, out['task_id'], off=True)
        c = operations.corrections(s, task_id=out['task_id'])
        self.assertEqual([(x['Verdict'], x['Change']) for x in c], [('watch', 'task')])
        self.assertEqual(evalset._labels(s)[out['message_id']][:2], ('task', 'owner:unwatch'))

    def test_watch_it_on_what_triage_called_the_owners_teaches_watch(self):
        s = store(); out = mail(s, 'p1', brain('task'))
        watch.watch(s, out['task_id']); self.press(s, out['task_id'])
        c = operations.corrections(s, task_id=out['task_id'])
        self.assertEqual([(x['Verdict'], x['Change']) for x in c], [('task', 'watch')])
        self.assertEqual(evalset._labels(s)[out['message_id']][:2], ('watch', 'owner:watch'))
        self.assertIn('watch', evalset.LABELS)

    def test_undoing_the_owners_own_watch_and_rewatching_a_triaged_one_teach_nothing(self):
        s = store(); mine = mail(s, 'p1', brain('task'))['task_id']
        self.press(s, mine); self.press(s, mine, off=True)
        self.assertEqual(len(operations.corrections(s, task_id=mine)), 1, 'only the Watch it was a correction; its undo is the owner, not triage')
        s2 = store(); theirs = mail(s2, 'p1', brain('watch'))['task_id']
        self.press(s2, theirs)
        self.assertEqual(operations.corrections(s2, task_id=theirs), [], 'watch on a watch agrees with triage')


if __name__ == '__main__': unittest.main()
