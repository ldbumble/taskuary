"""THE ASSISTANT BUILDS IT, ON ITS OWN PAGE (the owner, 2026-11-13): one loop for every Set up with AI - draft, check, save, the check's
problem back to the model, one question when only the owner knows. Each kind through its real check and save; only the model is a stand-in."""
import json
from unittest import mock

import pytest

from taskuary import build, channels, compose, concierge, playbooks, server
from taskuary.store import MemoryStore


@pytest.fixture
def st(tmp_path):
    s = MemoryStore()
    with mock.patch.object(server, 'store', s), mock.patch.object(playbooks, 'folder', lambda: tmp_path / 'pb'):
        yield s


def run(st, llm, *a, **k):
    with mock.patch.object(concierge, '_compose_llm', lambda store: llm):
        v = build.start(st, *a, **k); build.BUILDS[v['id']]['thread'].join(10)
    return build.view(v['id'])


def again(st, llm, bid, text):
    with mock.patch.object(concierge, '_compose_llm', lambda store: llm):
        build.answer(st, bid, text); build.BUILDS[bid]['thread'].join(10)
    return build.view(bid)


ROUTINE = {'title': 'Vendor bills check', 'agent': 'general', 'prompt': 'Each Friday list the vendors with no bill this month.', 'cron': '0 8 * * 5'}


def test_a_routine_is_drafted_saved_and_its_page_linked(st):
    with mock.patch.object(compose, 'compose_workflow', return_value={'config': ROUTINE}) as c:
        v = run(st, object(), 'workflow', 'every Friday tell me which vendors have not sent a bill')
    assert c.call_args[0][1] == 'every Friday tell me which vendors have not sent a bill'
    assert v['done'] and not v['busy'] and v['link'] == f"#report={v['ref']}"
    src = st.get_source(v['ref'])
    assert src['Address'] == 'Vendor bills check' and json.loads(src['ConfigJson'])['prompt'].startswith('Each Friday')
    assert [s['text'] for s in v['steps']] == ['every Friday tell me which vendors have not sent a bill', 'Drafted: Vendor bills check', 'Saved Vendor bills check']


def test_a_question_waits_for_the_owner_and_the_answer_goes_back_to_the_model(st):
    outs = iter([{'questions': ['Which mailbox should it read?']}, {'config': ROUTINE}])
    with mock.patch.object(compose, 'compose_workflow', side_effect=lambda *a, **k: next(outs)) as c:
        v = run(st, object(), 'workflow', 'chase late vendors')
        assert v['ask'] == 'Which mailbox should it read?' and not v['done'] and not v['busy']
        v = again(st, object(), v['id'], 'the accounts payable one')
    assert v['done'] and c.call_args.kwargs['answers']['Which mailbox should it read?'] == 'the accounts payable one'
    assert {'kind': 'you', 'text': 'the accounts payable one'} in v['steps']


def test_a_draft_that_fails_its_check_goes_back_with_the_problem_then_it_says_it_is_stuck(st):
    with mock.patch.object(compose, 'compose', return_value={'config': {'type': 'nope', 'title': 'Overdue'}}) as c:
        v = run(st, object(), 'report', 'overdue invoices every Monday')
    assert c.call_count == build.TRIES, 'each failed check is drafted again'
    assert 'problem_with_your_last_draft' in c.call_args.kwargs['answers'], 'the model is told what was wrong'
    assert not v['done'] and v['error'].startswith('I could not get the report to pass its check')
    assert 'Overdue' not in [s['Address'] for s in st.list_sources(active_only=False)], 'nothing half-made is saved'


def test_a_routine_that_only_reads_is_built_as_a_report_and_said(st):
    rep = {'type': 'taskuary_data', 'title': 'Open tasks', 'query': 'tasks'}
    with mock.patch.object(compose, 'compose_workflow', return_value={'report': rep}), \
         mock.patch.object(compose, 'validate', return_value=(True, '')), mock.patch.object(build, 'preview_problem', return_value=''):
        v = run(st, object(), 'workflow', 'show me my open tasks')
    assert v['done'] and v['kind'] == 'report' and 'set it up as a report' in v['steps'][1]['text']


def test_a_report_whose_executor_writes_is_never_previewed(st):
    with mock.patch.object(server, 'report_preview') as pv:
        assert build.preview_problem(st, {'type': 'intacct_create'}) == ''
    pv.assert_not_called()


PB = ('# Chase a late bill\nwhen: a vendor bill is late\nuses: quickbooks (read)\nsteps: look it up, then write the vendor\nalone: look\n'
      'ask first: write\ndone when: the vendor is written to')


def test_a_playbook_is_written_after_its_check_and_a_bad_draft_is_drafted_again(st):
    said = iter([json.dumps({'text': '# Only a title'}), json.dumps({'text': PB})])
    v = run(st, lambda sys, user, **k: next(said), 'playbook', 'how we chase late bills')
    assert v['done'] and v['ref'] == 'chase-a-late-bill' and playbooks.read('chase-a-late-bill').startswith('# Chase a late bill')
    assert v['steps'][1]['kind'] == 'failed' and 'when:' in v['steps'][1]['text']


def test_a_connection_saves_what_it_knows_never_a_secret_tests_and_finishes(st):
    cid = st.save_connector({'Type': 'imap', 'Name': 'Mail', 'ConfigJson': '{}'}, 'owner')
    said = iter(['Filling in the server.\n[[CARD-SAVE: host = imap.example.com]]\n[[CARD-SAVE: password = hunter2]]\n[[CARD-TEST]]',
                 'The password is yours.\n[[CARD-ASK: Secret]] Paste the app password into Password, then Save.'])
    ctx = {'guide': ['Find the IMAP server'], 'fields': [['Server', 'host']], 'secret_label': 'Password'}
    with mock.patch.object(channels, 'test_connector', return_value={'ok': False, 'detail': 'login failed'}):
        v = run(st, lambda sys, user, **k: next(said), 'connection', '', ref=cid, ctx=ctx)
    cfg = json.loads(st.get_connector(cid)['ConfigJson'])
    assert cfg.get('host') == 'imap.example.com' and 'password' not in cfg
    assert v['ask'].startswith('Paste the app password') and 'Test failed: login failed' in [s['text'] for s in v['steps']]
    said = iter(['[[CARD-TEST]]', '[[CARD-DONE]] Mail comes in now.'])
    with mock.patch.object(channels, 'test_connector', return_value={'ok': True, 'detail': 'signed in'}):
        v = again(st, lambda sys, user, **k: next(said), v['id'], 'pasted it')
    assert v['done'] and v['link'] == f'#connector={cid}'


def test_with_no_ai_it_says_how_to_connect_one(st):
    v = run(st, None, 'report', 'overdue invoices')
    assert not v['done'] and v['error'] == concierge.no_brain()


def test_the_endpoints(st):
    from fastapi.testclient import TestClient
    c = TestClient(server.app)
    assert c.post('/api/build', json={'kind': 'spaceship', 'words': 'x'}).status_code == 422
    assert c.post('/api/build', json={'kind': 'report', 'words': ''}).status_code == 422
    assert c.get('/api/build/nope').status_code == 404
    with mock.patch.object(concierge, '_compose_llm', lambda store: None):
        v = c.post('/api/build', json={'kind': 'report', 'words': 'overdue invoices'}).json()
        build.BUILDS[v['id']]['thread'].join(10)
    assert c.get(f"/api/build/{v['id']}").json()['error']


def test_a_playbook_from_a_past_email_reads_it_as_reference_data(st):
    mid = st.add_message({'Channel': 'email', 'Direction': 'in', 'Subject': 'Updated item numbers', 'FromEmail': 'buyer@example.test',
                          'BodyText': 'Send the latest numbers for item X.', 'SentAt': '2020-01-01 12:00:00'})
    from fastapi.testclient import TestClient
    seen = []
    def llm(sys, user, **k): seen.append(json.loads(user)); return json.dumps({'text': PB})
    with mock.patch.object(concierge, '_compose_llm', lambda store: llm):
        v = TestClient(server.app).post('/api/build', json={'kind': 'playbook', 'words': 'Build a playbook from this email.', 'message_id': mid}).json()
        build.BUILDS[v['id']]['thread'].join(10)
    assert seen[0]['example_email']['Subject'] == 'Updated item numbers' and 'reference data' in build.PLAYBOOK_SYSTEM
    assert build.view(v['id'])['done']
