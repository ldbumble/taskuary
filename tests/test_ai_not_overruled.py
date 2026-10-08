"""No code in front of the AI (the owner, 2026-10-08: "all these should not exist as hard coded rules"). The model reads the
words and picks the action; code checks the pick and carries it out, or hands it back - it never swaps the action for another
or decides from the words itself."""
import json

from taskuary import concierge


def test_clear_names_its_set_and_the_old_word_sweep_is_gone():
    # "clear" with the owner's sentence swept whatever a word list matched; the model is handed pipe.clear and names the set
    rest, call = concierge.parse_call('Clearing those.\nCALL: ' + json.dumps({'kind': 'clear', 'params': {'text': 'the vendor reports'}}))
    assert call == {'kind': 'tools.describe', 'params': {'kind': 'pipe.clear', 'why': 'clearing names its set: pipe.clear with `select`'}}
    for gone in ('clear_matching', '_sweep_words', '_sweep', '_SWEEP_CUES', '_last_owner_words'):
        assert not hasattr(concierge, gone), gone
    assert 'clear' not in concierge.PROPOSALS and 'clear' not in concierge.VERBS


def test_a_batch_tells_the_model_what_it_can_do_and_its_verb_is_never_rewritten():
    batch = {'kind': 'fyis', 'lane': 'fyi', 'key': 'fyis:a,b', 'title': '2 fyi', 'items': [{'key': 'a', 'who': 'Spendly', 'title': 'Receipt'},
                                                                                        {'key': 'b', 'who': 'Payworth', 'title': 'Invoice ready'}]}
    said = concierge.facts(None, batch)
    assert 'BATCH:' in said and 'not_ours_remember' in said and '`on`' in said
    import inspect
    src = inspect.getsource(concierge)
    assert "{**decision, 'verb': 'done'}, 'done'" not in src, 'not ours / remember / archive on a batch were turned into "read"'


def test_an_answer_that_misses_is_handed_back_to_the_model_with_the_reason_never_swapped_in_silence():
    from taskuary import general
    from taskuary.store import MemoryStore
    s = MemoryStore()
    tid = general.dock_task(s)[0]['TaskId']
    item = {'key': 'task:7', 'kind': 'task', 'lane': 'asked', 'title': 'Fix the ledger export', 'who': 'Erin Blake', 'tid': 7, 'ref': 'TQ-0007'}
    asked = []
    def model(system, user, **kw):
        asked.append(user)
        return 'TQ-0003 is about the portal.' if len(asked) == 1 else 'Erin Blake wants the ledger export fixed before Friday.'
    say, _options, _verb = concierge._ask(s, model, tid, item, 'Introduce it.', [])
    assert say == 'Erin Blake wants the ledger export fixed before Friday.'
    assert len(asked) == 2 and 'spoke about another task than TQ-0007' in asked[1]
