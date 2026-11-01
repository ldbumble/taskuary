"""The Advisor's "Report this?" (reportideas.py, the owner 2026-11-01: "yes the advisor can suggest fixes/features"): Taskuary itself failing
the same way again and again is one idea, raised once, whose move opens the Report popup. Counted, quiet unless sure: one task failing is
that task, a refused sign-in is the owner's, a stranger's task is never read - and a No sticks."""
import json, unittest
from datetime import datetime, timedelta
from unittest import mock

from taskuary import __version__, assistant, concierge, reportideas
from taskuary.store import MemoryStore

NOW = datetime(2026, 11, 1, 12, 0, 0)
BROKE = "TypeError: cannot read properties of undefined (reading 'session') at C:\\Users\\alexd\\x.py:41"


def stamp(**kw): return (NOW - timedelta(**kw)).strftime('%Y-%m-%d %H:%M:%S')


def failed(s, tid, err=BROKE, at=None, agent='coding'):
    rid = s.start_run(tid, agent, 'do it', 'owner')
    s._exec("UPDATE run SET Status='error', LastError=?, FinishedAt=? WHERE RunId=?", (err, at or stamp(hours=2), rid))


class AgentFailures(unittest.TestCase):
    def setUp(self):
        self.s = MemoryStore()
        self.s.set_setting(reportideas.VERSIONS, json.dumps({__version__: stamp(days=60)}), 't')     # updated long ago
        self.tasks = [self.s.create_task({'Title': f'Job {i}', 'Kind': 'general', 'Status': 'open'}, 'owner') for i in range(3)]

    def test_one_error_on_several_tasks_is_one_report_idea(self):
        for i, t in enumerate(self.tasks): failed(self.s, t, BROKE.replace('41', str(40 + i)), at=stamp(hours=i + 1))
        (i,) = reportideas.ideas(self.s, NOW)
        self.assertEqual((i['kind'], i['sig'], i['action']['type']), ('report', 'once', 'report'))
        r = i['action']['report']
        self.assertEqual((r['kind'], r['screen']), ('bug', 'Advisor'))
        self.assertIn('3 times this week', i['text']); self.assertNotIn('alexd', i['text'])     # numbers read as one; the user's folder out
        self.assertIn("Taskuary's", i['action']['why'])

    def test_one_task_failing_three_times_is_that_task(self):
        for h in (1, 2, 3): failed(self.s, self.tasks[0], at=stamp(hours=h))
        self.assertEqual(reportideas.ideas(self.s, NOW), [])

    def test_a_refused_sign_in_is_the_owners_to_fix(self):
        for t in self.tasks: failed(self.s, t, 'Graph said (401) token expired')
        self.assertEqual(reportideas.ideas(self.s, NOW), [])

    def test_a_strangers_task_is_never_counted(self):
        theirs = [self.s.create_task({'Title': 'Look', 'Status': 'open', 'OriginBase': 'stranger'}, 'triage') for _ in range(3)]
        for t in theirs: failed(self.s, t)
        self.assertEqual(reportideas.ideas(self.s, NOW), [])

    def test_a_failure_this_version_brought_needs_only_two(self):
        self.s.set_setting(reportideas.VERSIONS, json.dumps({__version__: stamp(days=2)}), 't')
        failed(self.s, self.tasks[0], at=stamp(hours=3)); failed(self.s, self.tasks[1], at=stamp(hours=1))
        (i,) = reportideas.ideas(self.s, NOW)
        self.assertIn(f'since Taskuary updated to {__version__}', i['text'])
        # ...but not when it failed that way before the update too
        failed(self.s, self.tasks[2], at=stamp(days=10))
        self.assertEqual(reportideas.ideas(self.s, NOW), [])

    def test_the_version_is_written_the_first_time_it_is_asked(self):
        s = MemoryStore()
        self.assertEqual(reportideas.updated_at(s, NOW), stamp())
        self.assertEqual(reportideas.updated_at(s, NOW + timedelta(days=3)), stamp())


class GaveUp(unittest.TestCase):
    def test_the_troubleshooter_giving_up_twice_on_one_connection(self):
        s = MemoryStore()
        tid = concierge.general.dock_task(s, 'owner')[0]['TaskId']
        chip = {'verb': 'bug', 'label': 'Report this bug', 'report': {'message': 'WhatsApp is not working: bridge', 'screen': 'Assistant', 'route': 'connector whatsapp'}}
        concierge.record(s, tid, 'assistant', 'It still does not answer.', {'kind': 'words', 'key': None, 'chips': [chip]})
        self.assertEqual(reportideas.gave_up(s, datetime.now()), [], 'once is not sure')
        concierge.record(s, tid, 'user', 'whatsapp again', None)
        concierge.record(s, tid, 'assistant', 'Still nothing.', {'kind': 'words', 'key': None, 'chips': [chip]})
        # ...and a report the owner asked for (issue.draft, it carries a kind) is not the troubleshooter giving up
        concierge.record(s, tid, 'assistant', 'Drafted.', {'kind': 'words', 'key': None, 'chips': [concierge.issue_chip({'kind': 'bug', 'route': 'connector whatsapp'})]})
        (i,) = reportideas.gave_up(s, datetime.now())
        self.assertEqual((i['kind'], i['action']['report']['route']), ('report', 'connector whatsapp'))
        self.assertIn('2 times', i['text'])


class RaisedOnce(unittest.TestCase):
    def test_a_no_sticks_and_a_raised_one_is_not_said_again(self):
        cand = {'key': 'report:abc', 'kind': 'report', 'sig': reportideas.SIG}
        self.assertTrue(assistant.fresh({}, cand, NOW))
        for status in ('open', 'dismissed', 'done'):
            self.assertFalse(assistant.fresh({'report:abc': {'Status': status, 'Sig': reportideas.SIG}}, cand, NOW), status)

    def test_the_advisor_run_raises_it_beside_the_health_lines(self):
        s = MemoryStore()
        line = reportideas._idea('report:x', 'Agent runs failed the same way 3 times this week.', 'why', {'trying': 'a', 'happened': 'b'})
        with mock.patch.object(reportideas, 'ideas', return_value=[line]) as found, mock.patch.object(assistant, 'health_ideas', return_value=[]):
            assistant.run(s, llm=lambda *a, **k: '{"say": [], "notes": ""}', force=True)
        found.assert_called()
        rows = s._rows("SELECT Kind, ActionJson FROM idea WHERE Key='report:x'")
        self.assertEqual([r['Kind'] for r in rows], ['report'])
        self.assertEqual(json.loads(rows[0]['ActionJson'])['report']['kind'], 'bug')


if __name__ == '__main__':
    unittest.main()
