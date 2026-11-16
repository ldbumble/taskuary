"""A STOPPED AGENT, AS A FACT (the live audit, 2026-10-28): one that left a result is stopped_done, one stopped mid-work is stopped, and a
done note or a run's own result is a finished run - the states rulebook.recommended reads its move off."""
from taskuary import rulebook, workerstate
from taskuary.store import MemoryStore

V = lambda *vs: [{'verb': v, 'label': v} for v in vs]


# ── 2. a finished stopped agent, as the fact the model reads ─────────────────────────────────────────────────────────────────────────────────────────
def _stopped(s, *events, title='Reconcile the vendor export'):
    t = s.create_task({'Title': title, 'Status': 'in_progress', 'Kind': 'general'}, 'owner')
    for kind, text in events: workerstate.record(s, t, 'r1', kind, text=text)
    return t, {'key': f'agent:{t}', 'kind': 'agent', 'lane': 'stopped', 'tid': t, 'title': title}


def test_a_stopped_agent_that_left_a_result_is_named_stopped_done():
    s = MemoryStore()
    t, it = _stopped(s, ('working', 'go'), ('finished', 'The export reconciles; two rows were fixed.'), ('stopped', ''))
    assert rulebook.left_result(s, t)
    r = rulebook.facts(s, it, V('continue', 'close'))
    assert r['state'] == 'stopped_done' and r['line'].startswith('Finished ') and r['line'].endswith('; nothing since.'), r
    assert 'verb' not in r, 'a fact for the model, never a light'


def test_a_stopped_agent_mid_work_is_named_stopped():
    """A plain stop is no reason (the measure, 2026-10-28: Continue agreed 5 times of 21) - the finish check lights Continue with this."""
    s = MemoryStore()
    t, it = _stopped(s, ('working', 'go'), ('finished', 'Half done.'), ('working', 'and the rest'), ('stopped', ''))
    assert not rulebook.left_result(s, t), 'a finish a later prompt took up is not the result'
    assert (r := rulebook.facts(s, it, V('continue', 'close')))['state'] == 'stopped' and r['line'] == '', r


def test_a_done_note_or_a_runs_result_is_a_finished_run():
    s = MemoryStore()
    t, it = _stopped(s, ('working', 'go'), ('stopped', ''))
    s.add_note({'TaskId': t, 'Agent': 'general', 'Kind': 'ready', 'Body': 'ready to push'})
    assert rulebook.facts(s, it, V('continue', 'close'))['state'] == 'stopped'
    s.add_note({'TaskId': t, 'Agent': 'general', 'Kind': 'done', 'Body': 'reconciled'})
    assert rulebook.facts(s, it, V('continue', 'close'))['state'] == 'stopped_done'
    t2, it2 = _stopped(s, ('working', 'go'), ('stopped', ''), title='Vendor W-9 lookup')
    rid = s.start_run(t2, 'general', 'look it up', 'owner'); s.update_run(rid, {'Status': 'stopped', 'Result': 'The W-9 is on file.'}, finished=True)
    assert rulebook.facts(s, it2, V('continue', 'close'))['state'] == 'stopped_done'
