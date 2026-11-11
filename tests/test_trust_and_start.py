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
    # ...the refusal as the start raised it (origin.Refusal, re-raised as the door's 409): its KIND rides on the op, read off the type - the
    # way on was found by searching the sentence for "stranger's task", and a reworded sentence would have offered Try again
    from fastapi import HTTPException
    from taskuary import failures, origin
    try:
        try: raise origin.Refusal('this AI cannot be kept to only reading their words, so it does not start')
        except origin.Refusal as e: raise HTTPException(409, str(e))
    except HTTPException as e: c = failures.classify(e, act='agent.continue')
    s.update_operation(op['id'], {'Status': 'error', 'Error': c['sentence'], 'OutcomeJson': json.dumps(failures.outcome(c))})
    return tid, operations.get(s, op['id'])


def test_a_start_refused_for_a_stranger_offers_trust_and_start_not_try_again():
    s = store(); tid, op = _refused(s)
    chips = concierge.recover(s, op)['chips']
    assert chips[0]['label'] == 'Trust and start' and chips[0]['verb'] == 'revise' and chips[0]['params']['trust'] is True
    assert 'retry' not in [c['verb'] for c in chips]


def test_a_start_told_to_trust_vouches_for_the_task_before_it_runs():
    s = store(); tid, op = _refused(s)
    with mock.patch.object(server, 'store', s), mock.patch('taskuary.origin.raise_to') as vouch:
        try: server._run_kind({**op, 'kind': 'task.comment', 'params': {'text': 'go', 'trust': True}}, None)
        except Exception: pass
    vouch.assert_called_once_with(s, tid, 'trusted', server.ACTOR)
