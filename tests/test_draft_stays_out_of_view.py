"""A DRAFT'S BODY STAYS IN THE DRAFT (the owner, 2026-11-04): a login the thread asks the owner for goes in the drafted reply, which
waits for their Send - and never in the agent's pane, its live trace or the kept steps. The tool call that files the draft carried the
whole body into all three: `tool> propose_reply <body>` on the pane, the args in every assistant-state response, the body as the
kept step's target. The draft itself still lands in the review as before. Invented people; a fake secret."""
import json
from unittest import mock

from taskuary import general, llm, sessionrecord, terminal
from taskuary.store import MemoryStore

SECRET = 'Pl4ceholder-Secret-9'
CALLS = [('mcp__taskuary__propose_reply', {'text': f'Hi Gail, the portal login is gail / {SECRET}', 'to': 'Gail Moreno'}),
         ('propose_email', {'to': 'gail@northwind.example', 'subject': 'Portal', 'text': f'Password: {SECRET}'}),
         ('Bash', {'command': f'taskuary --reply "Hi Gail - the password is {SECRET}" --to "Gail Moreno"', 'description': 'File the reply'}),
         ('Bash', {'command': f"taskuary --draft='Login {SECRET}\nThanks' --subject Portal"}),
         ('shell', {'command': ['bash', '-lc', f'taskuary --reply "$(cat <<EOF\nuser: gail\npass: {SECRET}\nEOF\n)"']})]


def test_a_drafted_body_reaches_neither_the_pane_nor_the_trace_nor_the_kept_steps():
    s = MemoryStore()
    tid = s.create_task({'Title': 'Portal login for Gail', 'Kind': 'general', 'Status': 'open'}, 'owner')
    session = general.GeneralSession(s, tid); session.pick, session.provider = 'cli:claude', 'claude'

    def fake_build(*a, trace=None, **k):
        def brain(system, user, **kw):
            for i, (name, args) in enumerate(CALLS): trace('tool_call', name, {'tool_call_id': f't{i}', 'args': args})
            return 'Drafted the reply to Gail for your Send.'
        return brain

    with mock.patch.dict(terminal.SESSIONS, {}, clear=True), mock.patch.object(llm, 'build_llm', side_effect=fake_build):
        session.send_prompt('Get Gail the login')
    assert 'tool>' in session.scrollback() and SECRET not in session.scrollback()
    trace = json.dumps(session.info()['trace'])
    assert 'propose_reply' in trace and SECRET not in trace and sessionrecord.DRAFT_SHOWN in trace
    steps = json.dumps(sessionrecord.general_steps(s, tid))
    assert 'propose_reply' in steps and SECRET not in steps


def test_kept_steps_hide_the_body_from_any_trace_or_cli_log():
    raw = [{'type': 'tool_call', 'name': n, 'detail': {'args': a}} for n, a in CALLS]
    steps = [sessionrecord._tool(e['name'], e['detail']['args']) for e in raw]
    assert SECRET not in json.dumps(steps) and steps[0]['text'] == sessionrecord.DRAFT_SHOWN
    assert steps[2]['detail'].startswith('taskuary --reply') and '--to "Gail Moreno"' in steps[2]['detail']   # the rest of the line stays
    s = MemoryStore()
    tid = s.create_task({'Title': 'Portal login for Gail', 'Kind': 'general', 'Status': 'open'}, 'owner')
    sessionrecord.keep_turn(tid, 1, raw)
    assert SECRET not in sessionrecord._gen_path(tid).read_text(encoding='utf-8')


def test_a_call_that_drafts_nothing_is_shown_as_before():
    assert sessionrecord._tool('Bash', {'command': 'git status --short'})['text'] == 'git status --short'
    assert sessionrecord._tool('Bash', {'command': 'taskuary --draft-file out.md'})['text'] == 'taskuary --draft-file out.md'
