"""An approved action runs ONCE. A reply's send is claimed before it leaves (store.claim_review_delivery); an action - a post, a push, a
merge - ran first and was only marked answered after, so two presses of one Approve (a double click, the desk and the phone) both ran it."""
import threading, time
from unittest import mock
from taskuary import proposals, verdicts
from taskuary.store import MemoryStore

BOOK = '# Monthly export\nwhen: the month ends\n\nRun the export, check the totals against the ledger, then send the file to Erin Blake.\n'


def test_two_presses_of_one_approve_run_the_action_once():
    s = MemoryStore()
    s.set_setting('playbooks_enabled', '1', 't')
    tid = s.create_task({'Title': 'Write the export playbook', 'Kind': 'general', 'Status': 'waiting'}, 'router')
    rv = proposals.queue(s, tid, {'action': 'write_playbook', 'slug': 'monthly-export', 'text': BOOK, 'why': 'it recurs'}, 'agent')
    rid, ran, outs = rv['reviewId'], [], []
    def slow(*a, **k): ran.append(1); time.sleep(.3); return {'said': 'written'}
    with mock.patch.object(proposals, 'execute', slow), mock.patch.object(proposals, 'settle'), mock.patch('taskuary.general.approved'):
        ts = [threading.Thread(target=lambda: outs.append(verdicts.decide(s, s.get_review(rid), 'approve'))) for _ in range(2)]
        for t in ts: t.start()
        for t in ts: t.join()
    assert len(ran) == 1
    assert sorted(o['ok'] for o in outs) == [False, True]
    assert s.get_review(rid)['Status'] == 'approved'
