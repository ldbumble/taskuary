"""A turn that ends with work still running is not "waiting on you" (background.py).

The shape: a coder starts a long pull in the background, arms a monitor on it, says "re-pulling now" and ends
its turn. Claude's Stop fires, the pane sits at a bare prompt with "1 shell, 1 monitor still running" under it,
and every surface read the agent as parked on the owner while the work went on.
"""
import json, os, tempfile, time, unittest
from datetime import datetime, timezone

from taskuary import background, workerstate as ws
from tests.test_hooks_events import Base


def _ts(ago=0): return datetime.fromtimestamp(time.time() - ago, timezone.utc).isoformat().replace('+00:00', 'Z')


def use(uid, name, **inp): return {'type': 'assistant', 'message': {'content': [{'type': 'tool_use', 'id': uid, 'name': name, 'input': inp}]}}
def result(uid, r, ago=0):
    return {'type': 'user', 'timestamp': _ts(ago), 'toolUseResult': r,
            'message': {'content': [{'type': 'tool_result', 'tool_use_id': uid, 'content': 'ok'}]}}
def note(tid, end=True, queued=False):
    body = f"<task-notification>\n<task-id>{tid}</task-id>\n" + ('<status>completed</status>' if end else '<event>2024-01: 1,204 rows</event>') + '\n</task-notification>'
    return {'type': 'queue-operation', 'operation': 'enqueue', 'content': body} if queued else {'type': 'user', 'message': {'content': body}}

SHELL = [use('t1', 'Bash', command='python pull.py', run_in_background=True, description='pull the ledger'),
         result('t1', {'stdout': '', 'backgroundTaskId': 'bshell1'})]
MONITOR = [use('t2', 'Monitor', command='tail -f pull.log', description='pull progress', timeout_ms=1800000),
           result('t2', {'taskId': 'bmon1', 'timeoutMs': 1800000, 'persistent': False})]
AGENT = [use('t3', 'Agent', description='review the pull', prompt='...', run_in_background=True),
         result('t3', {'isAsync': True, 'status': 'async_launched', 'agentId': 'a0123456789abcdef', 'description': 'review the pull'})]


class Files:
    def file(self, lines):
        f = tempfile.NamedTemporaryFile('w', suffix='.jsonl', delete=False, encoding='utf-8')
        f.write('\n'.join(json.dumps(o, separators=(',', ':')) for o in lines)); f.close()     # compact, as Claude writes it
        self.addCleanup(os.unlink, f.name)
        return f.name


class Transcript(Files, unittest.TestCase):
    def kinds(self, lines): return sorted(j['kind'] for j in background.pending(self.file(lines)))

    def test_a_shell_a_monitor_and_a_subagent_are_seen_running(self):
        self.assertEqual(self.kinds(SHELL + MONITOR + AGENT), ['agent', 'monitor', 'shell'])
        self.assertEqual(background.summary(background.pending(self.file(SHELL + MONITOR))), '1 shell, 1 monitor still running')

    def test_a_status_ends_a_job_and_a_monitor_event_does_not(self):
        self.assertEqual(self.kinds(SHELL + MONITOR + [note('bmon1', end=False)]), ['monitor', 'shell'])
        self.assertEqual(self.kinds(SHELL + MONITOR + [note('bshell1')]), ['monitor'])
        self.assertEqual(self.kinds(SHELL + [note('bshell1', queued=True)]), [])       # queued for Claude still means it ended
        expired = {'type': 'user', 'message': {'content': '<task-notification><task-id>bmon1</task-id><event>[Monitor expired after 30m]</event></task-notification>'}}
        self.assertEqual(self.kinds(MONITOR + [expired]), [])

    def test_task_stop_and_the_restart_sweep_end_jobs(self):
        self.assertEqual(self.kinds(SHELL + [use('t9', 'TaskStop', task_id='bshell1')]), [])
        sweep = {'type': 'user', 'message': {'content': '<task-notification><task-id>bshell1</task-id><task-id>bmon1</task-id>'
                                                        '<task-id>__orphan_summary__:shell</task-id><status>stopped</status></task-notification>'}}
        self.assertEqual(self.kinds(SHELL + MONITOR + [sweep]), [])

    def test_a_job_past_its_own_deadline_is_not_counted(self):
        """Some stops leave no marker - a shell killed from Claude's UI - so the timeout is the backstop."""
        old = [SHELL[0], result('t1', {'backgroundTaskId': 'bshell1'}, ago=31 * 60)]
        self.assertEqual(self.kinds(old), [])
        long = [use('t1', 'Bash', command='x', run_in_background=True, timeout=3_600_000), result('t1', {'backgroundTaskId': 'b'}, ago=31 * 60)]
        self.assertEqual(self.kinds(long), ['shell'])

    def test_no_transcript_is_nothing_running(self):
        self.assertEqual(background.pending(None), [])
        self.assertEqual(background.pending(r'C:\nowhere\missing.jsonl'), [])


class StopWithWorkRunning(Files, Base):
    def test_the_agent_reads_working_not_waiting(self):
        t = self.session()
        self.fire('UserPromptSubmit', prompt='pull the ledger')
        self.fire('Stop', last_assistant_message='Re-pulling Jan 2024 now.', transcript_path=self.file(SHELL + MONITOR))
        st = self.state()
        self.assertEqual(st['state'], 'working')
        self.assertEqual(sorted(j['kind'] for j in st['background']), ['monitor', 'shell'])
        self.assertEqual(st['said'], 'Re-pulling Jan 2024 now.')                       # what it said still shows
        self.assertIs(ws.waiting_of(self.s, t), False)                                 # the screen is not asked

    def test_once_the_work_ends_the_next_stop_is_a_plain_turn_end(self):
        t = self.session()
        self.fire('Stop', last_assistant_message='Pulling.', transcript_path=self.file(SHELL))
        self.assertIs(ws.waiting_of(self.s, t), False)
        self.fire('Stop', last_assistant_message='Done: 12 months pulled.', transcript_path=self.file(SHELL + [note('bshell1')]))
        self.assertIsNone(ws.waiting_of(self.s, t))                                    # silent again: the screen decides
        self.assertNotEqual(self.state()['state'], 'working')

    def test_claudes_own_list_on_stop_is_the_answer(self):
        """Claude 2.1.286 sends `background_tasks` on Stop (the shape measured 2026-10-01). Its word beats the
        transcript: here the transcript knows nothing, and the agent still reads working."""
        t = self.session()
        listed = [{'id': 'b1', 'type': 'shell', 'status': 'running', 'description': 'pull the ledger', 'command': 'python pull.py'},
                  {'id': 'a1', 'type': 'subagent', 'status': 'running', 'description': 'review the pull', 'agent_type': 'general-purpose'}]
        self.fire('Stop', last_assistant_message='Pulling.', background_tasks=listed, transcript_path=self.file([]))
        st = self.state()
        self.assertEqual((st['state'], sorted(j['kind'] for j in st['background'])), ('working', ['agent', 'shell']))
        self.assertIs(ws.waiting_of(self.s, t), False)
        # ...and an empty list is Claude saying nothing runs - even if the transcript still shows a job open
        self.fire('Stop', last_assistant_message='Done.', background_tasks=[], transcript_path=self.file(SHELL))
        self.assertIsNone(ws.waiting_of(self.s, t))

    def test_a_job_waking_the_agent_is_not_the_owner_answering(self):
        """A job ending wakes Claude with a UserPromptSubmit nobody typed. It is working again - but a question
        it asked is still the owner's to answer."""
        t = self.session()
        self.fire('Notification', notification_type='agent_needs_input', message='Which ledger, 2024 or 2025?')
        self.fire('UserPromptSubmit', prompt='<task-notification>\n<task-id>b1</task-id>\n<status>completed</status>\n</task-notification>')
        self.assertEqual([r['text'] for r in ws.status(self.s, self.tid)['requests']], ['Which ledger, 2024 or 2025?'])
        self.fire('UserPromptSubmit', prompt='2025')                                   # the owner, typing
        self.assertEqual(ws.status(self.s, self.tid)['requests'], [])

    def test_a_question_still_outranks_running_work(self):
        t = self.session()
        self.fire('PermissionRequest', tool_name='Bash', tool_input={'command': 'rm -rf build'})
        self.fire('Stop', last_assistant_message='Waiting.', transcript_path=self.file(SHELL))
        self.assertIs(ws.waiting_of(self.s, t), True)
        self.assertEqual(self.state()['state'], 'approval_needed')


if __name__ == '__main__':
    unittest.main()
