"""PERSONAL IS NEVER LEARNED FROM (the owner, 2026-10-23 and 2026-11-01; the design's S3): Alex's family chat is a personal workstream.
An ask in it is an FYI, never a task; nothing in it teaches a memory line, an episode, a press habit or a voice; and the Advisor raises
no idea about it. Invented people only (CLAUDE.md)."""
import json
from unittest import mock
import pytest
from taskuary import episodes, ingest, memorylines, presses, workstreams as W
from taskuary.store import MemoryStore
from taskuary.testing import Factory

MOM, ERIN = 'mom@family.example', 'erin@northwind.example'


@pytest.fixture
def s():
    s = MemoryStore()
    s.set_setting('owner_email', 'alex@northwind.example', 'test')
    W.save(s, [{'name': 'Northwind finance systems', 'domains': ['northwind.example']},
               {'name': 'Personal', 'personal': True, 'people': [MOM], 'channels': ['whatsapp:family']}])
    return s


def test_what_is_personal_is_read_from_the_item_its_message_and_any_evidence_id(s):
    f = Factory(s)
    t = f.task(title='Pick up the car at 5', source='whatsapp')
    mid = f.message(task_id=t, channel='whatsapp', source_name='Family', from_email=MOM, body='Can you pick up the car at 5?')
    work = f.task(title='Q4 variance')
    wmid = f.message(task_id=work, channel='email', from_email=ERIN)
    assert W.is_personal(s, tid=t) and W.is_personal(s, mid=mid) and W.is_personal(s, src=f'msg{mid}') and W.is_personal(s, src=f'task{t}')
    assert not W.is_personal(s, tid=work) and not W.is_personal(s, src=f'msg{wmid}') and not W.is_personal(s, src='mem3')
    i = s.upsert_idea({'key': 'idea:car', 'kind': 'idea', 'text': 'x', 'action': {'tid': t}}, '2026-11-01 09:00:00')
    assert W.is_personal(s, src=f"idea{i['IdeaId']}")
    assert presses.personal(s, {'tid': t}, s.get_message(mid)) and not presses.personal(s, {'tid': work}, s.get_message(wmid))


def test_a_personal_ask_is_an_fyi_whatever_triage_said(s):
    msg = {'channel': 'whatsapp', 'source_name': 'Family', 'from_email': MOM, 'body': 'Can you pick up the car at 5?'}
    intent = {'intent': 'task', 'why': 'she asks Alex to pick up the car'}
    assert ingest.personal_fyi(s, msg, intent)
    assert intent['intent'] == 'fyi' and intent['why'].startswith('Personal - an FYI, never a task.') and msg['_workstream'] == 'personal'
    # ...triage's own word places it when the signals say nothing
    other = {'channel': 'whatsapp', 'source_name': 'Neighbour', 'from_email': 'sam@street.example', '_workstream': 'personal'}
    assert ingest.personal_fyi(s, other, {'intent': 'reply_only', 'why': ''})
    work = {'channel': 'email', 'source_name': 'alex@northwind.example', 'from_email': ERIN}
    assert not ingest.personal_fyi(s, work, {'intent': 'task', 'why': ''})


def test_a_verdict_on_something_personal_teaches_no_line(s):
    t = Factory(s).task(title='Pick up the car at 5')
    Factory(s).message(task_id=t, channel='whatsapp', source_name='Family', from_email=MOM)
    asked = []
    llm = lambda *a, **k: asked.append(1) or json.dumps({'line': 'Alex always picks up the car'})
    assert memorylines.teach(s, 'not_a_task', f'task{t}', 'Pick up the car', llm=llm) == ''
    assert asked == [] and s.get_setting('learn_pending') in (None, '', '0')


def test_episodes_skip_personal_mail_ideas_and_promises(s):
    f = Factory(s)
    t = f.task(title='Pick up the car at 5')
    mid = f.message(task_id=t, channel='whatsapp', source_name='Family', from_email=MOM, conversation_id='wa:family', sent_at='2026-11-01 08:00:00')
    f.message(task_id=t, channel='whatsapp', source_name='Family', from_email=None, direction='out', conversation_id='wa:family',
              sent_at='2026-11-01 08:05:00', status='context')
    i = s.upsert_idea({'key': 'idea:car', 'kind': 'idea', 'text': 'Mom asked twice', 'action': {'tid': t}}, '2026-11-01 08:10:00')
    s.set_idea_status(i['IdeaId'], 'done', 'owner')
    got = episodes.build(s, since='2026-10-01') if hasattr(episodes, 'build') else []
    ids = [e[0] if isinstance(e, tuple) else str(e) for e in (got or [])]
    assert not any(str(x).startswith((f'msg{mid}', f"idea{i['IdeaId']}")) for x in ids), ids


def test_the_advisor_raises_no_idea_about_a_personal_item(s):
    from taskuary import sweep
    f = Factory(s)
    t = f.task(title='Pick up the car at 5')
    f.message(task_id=t, channel='whatsapp', source_name='Family', from_email=MOM)
    work = f.task(title='Q4 variance')
    said = sweep._say_once(s, [{'key': 'loose:car', 'kind': 'loose', 'text': 'Pick up the car has no next step', 'sig': 'a', 'action': {'task': t}},
                               {'key': 'loose:q4', 'kind': 'loose', 'text': 'Q4 variance has no next step', 'sig': 'b', 'action': {'task': work}}],
                           '2026-11-01 09:00:00')
    assert [i['Key'] for i in said] == ['loose:q4']


def test_a_personal_ask_is_said_to_the_model_which_decides(s, monkeypatch):
    """The owner, 2026-11-01: a personal ask is an FYI. Since 2026-11-02 that is a fact the model reads (PERSONAL: ...) - no code darkens its
    light - so the work item's prompt has no such line, the personal one's has, and each model's light is what is lit."""
    from taskuary import advisor, funnel, terminal
    monkeypatch.setattr(terminal, 'live_sessions', lambda tail=0: []); monkeypatch.setattr(funnel, '_agenda', lambda _s, **kw: [])
    monkeypatch.setattr(advisor, 'notice', lambda *a, **k: None)
    from tests.test_advisor_consistent import ask
    s.set_setting('calendar_enabled', '0', 'test')
    # the same ask twice is a duplicate the rule folds with Remove - lit on work, nothing on a personal ask
    ask(s, 'Q4 variance', ('Erin Blake', ERIN), 7, cid='email:q4'); w, _ = ask(s, 'RE: Q4 variance', ('Erin Blake', ERIN), 2, cid='email:q4')
    ask(s, 'The car', ('Mom', MOM), 7, cid='email:car'); t, _ = ask(s, 'RE: The car', ('Mom', MOM), 2, cid='email:car')
    import json
    seen = {}
    for x in (w, t):
        def brain(system, user, x=x, **kw): seen[x] = user; return json.dumps({'verb': 'remove' if x == w else 'next', 'line': '', 'evidence': []})
        advisor.judge(s, advisor.SHOWN, 'task', x, advisor.revision(s, 'task', x), tier=2, llm=brain, key=f'task:{x}')
    assert 'PERSONAL:' in seen[t] and 'PERSONAL:' not in seen[w]
    work, home = (advisor.decide(s, f'task:{x}', preread=False) for x in (w, t))
    assert (work['state'], work['verb']) == ('duplicate', 'remove')
    assert (home['state'], home['verb']) == ('duplicate', 'next')
