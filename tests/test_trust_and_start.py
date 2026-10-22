"""A start refused for a stranger has one way on: Trust and start (the owner, 2026-10-22: "if i hit start it should just say not
trusted sender ... if i hit go then it should start anyway"). The refusal used to offer Try again - refused the same way - and name
another coding tool to switch to. Now the chip is the same proposal told to vouch first, and the runner vouches before it starts."""
import json
from unittest import mock

from taskuary import concierge, operations, server
from tests.test_chat_proposals import store


def _refused(s):
    tid = s.create_task({'Title': 'Look at the new user setup', 'Kind': 'coding', 'Status': 'open'}, 'router')
    op = operations.propose(s, 'agent.continue', tid, {})
    s.update_operation(op['id'], {'Status': 'error', 'Error': "this tool has no built-in reviewer, so it does not run a stranger's task with its tools",
                                  'OutcomeJson': json.dumps({'retry': True})})
    return tid, operations.get(s, op['id'])


def test_a_start_refused_for_a_stranger_offers_trust_and_start_not_try_again():
    s = store(); tid, op = _refused(s)
    chips = concierge.recover(s, op, llm=False)['chips']
    assert chips[0]['label'] == 'Trust and start' and chips[0]['verb'] == 'revise' and chips[0]['params']['trust'] is True
    assert 'retry' not in [c['verb'] for c in chips]


def test_a_start_told_to_trust_vouches_for_the_task_before_it_runs():
    s = store(); tid, op = _refused(s)
    with mock.patch.object(server, 'store', s), mock.patch('taskuary.origin.raise_to') as vouch:
        try: server._run_kind({**op, 'kind': 'task.comment', 'params': {'text': 'go', 'trust': True}}, None)
        except Exception: pass
    vouch.assert_called_once_with(s, tid, 'trusted', server.ACTOR)
