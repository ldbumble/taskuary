"""What the desktop stress run (2026-11-04) found the general agent's pane saying wrong, with the network down and after a restart."""
import time, unittest
from unittest import mock

from fastapi.testclient import TestClient

from taskuary import agents, general, server
from taskuary.store import MemoryStore


def test_claudes_retries_are_said_while_it_cannot_reach_its_servers():
    "The network down: \"Starting Taskuary on Claude Code… 3m\" for the ten tries Claude made, and nothing said why it was slow."
    said = agents._live_line({'type': 'system', 'subtype': 'api_retry', 'attempt': 3, 'max_retries': 10, 'error_status': None})
    assert said == "Can't reach Claude's servers right now - trying again (3 of 10)"
    assert agents._live_line({'type': 'system', 'subtype': 'hook_response'}) is None            # the other system events stay quiet


def test_the_agent_is_told_its_reply_is_a_card_under_next_steps():
    """\"Your reply to her is drafted below\" said the agent, over a draft that is Close out's to show, beside its answer. Since the chat is
    the task's home (2026-11-04) there is no Close out on it: the stress run (2026-11-05) had the agent say "The reply is in Close out" and
    list "Review the reply in Close out and press Send" as an On you step, over the draft's own card under Next steps."""
    from taskuary import general, selfclose
    assert 'its own card under Next steps' in selfclose.REPLY_LINE and 'never "in Close out"' in selfclose.REPLY_LINE
    assert 'none is ever an on_you step' in selfclose.SUMMARY_LINE      # ...nor its own question again (email-04 of the run: said twice)
    assert 'Close out' not in general.DRAFTED


class Ses:
    def __init__(self): self.sent = []
    def send_prompt(self, text, *a, **kw): raise RuntimeError("claude: API Error: Connection refused (ECONNREFUSED)")


class ContinueFailure(unittest.TestCase):
    def test_a_continued_turn_that_fails_is_said_once_by_its_run(self):
        """"Failed - Claude: API Error ..." on the run, and under it a Taskuary line "The session could not continue: claude: API Error ...":
        the turn's failure is its run's to say, with Try again."""
        s = MemoryStore(); tid = s.create_task({'Title': 'Folder summary', 'Kind': 'general', 'Status': 'open'}, 'router')
        s.add_comment(tid, 'assistant', general.ASSISTANT_TYPE, 'Read three of nine files.')
        with mock.patch.object(server, 'store', s), mock.patch.object(general, 'start_session', return_value=Ses()), \
             mock.patch.object(general, 'provider_options', return_value=[{'pick': 'cli:claude'}]):
            self.assertEqual(TestClient(server.app).post(f'/api/tasks/{tid}/continue-work', json={}).status_code, 200)
            time.sleep(0.3)
        self.assertFalse(any('could not continue' in c['Body'] for c in s.list_comments(tid)))

    def test_a_session_that_cannot_start_still_says_so(self):
        s = MemoryStore(); tid = s.create_task({'Title': 'Folder summary', 'Kind': 'general', 'Status': 'open'}, 'router')
        s.add_comment(tid, 'assistant', general.ASSISTANT_TYPE, 'Read three of nine files.')
        with mock.patch.object(server, 'store', s), mock.patch.object(general, 'start_session', side_effect=RuntimeError('no AI is connected')), \
             mock.patch.object(general, 'provider_options', return_value=[{'pick': 'cli:claude'}]):
            TestClient(server.app).post(f'/api/tasks/{tid}/continue-work', json={})
            time.sleep(0.3)
        self.assertTrue(any('could not continue: no AI is connected' in c['Body'] for c in s.list_comments(tid)))
