"""A credential phish is danger, not only a filed fyi (the overnight QA, 2026-10-30).

"Verify your password within 24 hours" from a look-alike IT sender was read right - its why said "phishing" - and filed with no
`danger`, because the guide's danger was only text that steers an AI. So the rail, the FYI card and the task page, which all show
message.Danger as their one warning line (B3), showed none. The guide now says a scam aimed at the owner is danger too. Model
guidance, no word list."""
import json
from fastapi.testclient import TestClient
from taskuary import server, triage
from taskuary.store import MemoryStore


def test_the_guide_reads_a_scam_aimed_at_the_owner_as_danger():
    g = ' '.join(triage.SHIPPED.split())
    bullet = g.split('- **danger**', 1)[1].split('- **', 1)[0]
    assert 'a scam aimed at the owner' in bullet and 'a password, a code or a sign-in' in bullet
    assert 'what it tries to make an agent or the owner do' in bullet
    # ...and the line that files a scam as fyi asks for the reading too, so the two never disagree
    scams = g.split('**Strangers and scams.**', 1)[1].split('##', 1)[0]
    assert '`danger` saying what it is after' in scams


def test_a_document_that_takes_only_the_shape_is_handed_the_same_bullet():
    assert 'a scam aimed at the owner' in triage.DANGER


# WHOM IT IS AIMED AT (the owner, 2026-10-30): a phish on the owner read "an attempt to steer the agent". The verdict says whom - the owner
# or the agent - and the warning's words follow it; the steer words stay for text written to hijack the agent
MSG = {'subject': 'Verify your password', 'body': 'Sign in within 24 hours or lose access.', 'from_email': 'it@northwind-support.invalid',
       'from_name': 'IT Helpdesk', 'channel': 'email'}


def _read(**j):
    return triage.classify_intent(MSG, llm=lambda sy, u, **k: json.dumps({'intent': 'fyi', 'why': 'phishing', 'title': 't', 'summary': 's', **j}))


def test_the_verdict_says_whom_the_danger_is_aimed_at():
    p = triage.verdict_schema()['schema']
    assert 'danger_aim' in p['required'] and p['properties']['danger_aim']['enum'] == ['owner', 'agent', None]
    assert triage.DANGER_AIM.startswith('- **danger_aim**') and '"owner"' in triage.DANGER_AIM and '"agent"' in triage.DANGER_AIM
    assert '"danger_aim": null' in triage.TASK_FIELDS
    v = _read(danger='Wants Alex to sign in on a look-alike page.', danger_aim='owner')
    assert (v['danger'], v['danger_aim']) == ('Wants Alex to sign in on a look-alike page.', 'owner')
    assert _read(danger='Tells the agent to mail the payroll file out.', danger_aim='agent')['danger_aim'] == 'agent'
    assert 'danger_aim' not in _read(danger='x', danger_aim='nobody'), 'a word that is neither is not kept'
    assert 'danger_aim' not in _read(danger=None, danger_aim='owner'), 'no danger, no aim'


def test_an_owner_document_that_never_asks_whom_is_handed_the_bullet():
    seen = []
    doc = '# Triage\nJSON only: {"intent": "task|reply_only|fyi", "why": "...", "title": "...", "summary": "...", "checklist": [], "danger": null}'
    triage.classify_intent(MSG, llm=lambda sy, u, **k: (seen.append(sy), json.dumps({'intent': 'fyi', 'why': 'w', 'title': 't', 'summary': 's'}))[1],
                           system=doc)
    assert seen and triage.DANGER_AIM in seen[0]


def test_the_aim_lands_on_the_message_and_ranking_s_reading_is_the_agent_s():
    s = MemoryStore(); mid = s.add_message({'Channel': 'email', 'FromEmail': 'it@northwind-support.invalid', 'BodyText': 'x', 'Status': 'filed'})
    s.add_route(mid, None, 'file', None, 'r', [], verdict={'intent': 'fyi', 'danger': 'Wants Alex to sign in.', 'danger_aim': 'owner'})
    assert (s.get_message(mid)['Danger'], s.get_message(mid)['DangerAim']) == ('Wants Alex to sign in.', 'owner')
    s.set_message_danger(mid, 'Tells the agent to run a script.')
    assert s.get_message(mid)['DangerAim'] == 'agent', 'a reading that never said whom is the agent'


def test_the_task_page_carries_whom():
    c, s = TestClient(server.app), server.store
    t = s.create_task({'Title': 'Verify your password', 'Kind': 'general', 'Source': 'email'}, 'router')
    mid = s.add_message({'TaskId': t, 'Channel': 'email', 'FromEmail': 'it@northwind-support.invalid', 'BodyText': 'x', 'Status': 'routed'})
    assert c.get(f'/api/tasks/{t}').json()['origin']['danger_aim'] is None
    s.set_message_danger(mid, 'Wants Alex to sign in on a look-alike page.', 'owner')
    o = c.get(f'/api/tasks/{t}').json()['origin']
    assert (o['danger'], o['danger_aim']) == ('Wants Alex to sign in on a look-alike page.', 'owner')
