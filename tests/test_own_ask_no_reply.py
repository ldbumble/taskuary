"""THE OWNER'S OWN ASK HAS NOBODY TO REPLY TO (the owner, 2026-11-06: "What is this? doesn't make any sense").

An agent on a task the owner made themselves tried to save a reply, and told the owner Taskuary refused it "because nobody else is on
this task". At the root: the first prompt - coding and general - says plainly there is nobody to reply to, the reply tools are not
offered, and a reply saved anyway comes back as a fact to act on, never a refusal to narrate. Invented people.
"""
from unittest import mock

from fastapi.testclient import TestClient

from taskuary import agenttools, general, selfclose, server, terminal, wrapup
from taskuary.store import MemoryStore
from test_agent_toolbox import hdr

c = TestClient(server.app)


def own_task(s, kind='coding'):
    tid = s.create_task({'Title': 'Tidy the ledger exports', 'Kind': kind, 'Status': 'in_progress', 'OriginBase': 'owner'}, 'owner')
    s.add_message({'TaskId': tid, 'ExternalId': 'own-1', 'Channel': 'own', 'Subject': 'Tidy the ledger exports', 'FromName': 'You',
                   'BodyText': 'tidy the exports in northwind/ledger', 'Status': 'routed'})
    return tid


def mailed_task(s, kind='coding'):
    tid = s.create_task({'Title': 'Fix the August export', 'Kind': kind, 'Status': 'in_progress'}, 'owner')
    s.add_message({'TaskId': tid, 'ExternalId': 'x-1', 'ConversationId': 'c-1', 'Channel': 'email', 'FromName': 'Erin Blake',
                   'FromEmail': 'erin@northwind.example', 'Subject': 'August export', 'BodyText': 'Could you fix the August export?',
                   'SentAt': '2026-11-06 09:00:00', 'Status': 'routed'})
    return tid


def test_who_is_behind_the_task():
    s = MemoryStore()
    assert wrapup.no_correspondent(s, own_task(s)) and not wrapup.no_correspondent(s, mailed_task(s))


def test_the_coding_seed_says_there_is_nobody_to_reply_to():
    s = MemoryStore(); own, mailed = own_task(s), mailed_task(s)
    seed = terminal.seed_text(s, own, 'tidy the exports')
    # ...the standing rules (CODING.md) still name the reply road; the seed's own line about it is this task's, and it says no
    assert wrapup.OWN_ASK in seed and 'No `taskuary --reply`' in seed and selfclose.SEED_LINE not in seed
    assert wrapup.OWN_ASK not in terminal.seed_text(s, mailed, 'fix it')


def test_the_general_prompt_says_so_and_drops_the_reply_block():
    s = MemoryStore(); own, mailed = own_task(s, 'general'), mailed_task(s, 'general')
    sys_own, sys_mailed = general._prompt(s, own)[0], general._prompt(s, mailed)[0]
    assert wrapup.OWN_ASK in sys_own and 'REPLYING FOR THE OWNER' not in sys_own
    assert 'REPLYING FOR THE OWNER' in sys_mailed and wrapup.OWN_ASK not in sys_mailed


def test_a_reply_saved_anyway_reads_back_as_a_fact_never_a_refusal():
    s = MemoryStore(); tid = own_task(s)
    with mock.patch.object(wrapup, 'REFRESH', None): out = wrapup.agent_reply(s, tid, 'Exports tidied; three files renamed.', 'coding')
    assert out['ok'] and out['saved'] == 'result' and out['says'].startswith(wrapup.OWN_ASK)
    assert 'refused' not in out['says'] and s.list_reviews('pending') == []


def notice_task(s, kind='coding'):
    "A task made from a code host's failure notice: the class triage stored on it says a machine sent it."
    tid = s.create_task({'Title': 'CI failed on main', 'Kind': kind, 'Status': 'in_progress'}, 'owner')
    s.add_message({'TaskId': tid, 'ExternalId': 'n-1', 'ConversationId': 'c-9', 'Channel': 'email', 'FromName': 'Code host',
                   'FromEmail': 'notifications@codehost.example', 'Subject': 'Run failed: CI - main', 'SenderClass': 'automated',
                   'BodyText': 'The run failed on main in northwind/ledger.', 'SentAt': '2026-11-10 07:00:00', 'Status': 'routed'})
    return tid


def test_an_automated_notice_has_nobody_to_reply_to_on_every_road():
    """The owner, 2026-11-10: "it's replying to a no reply email ... github emails are not supposed to be respodned to". The agent is told
    so, the reply tools are not offered, a reply asked for at the door is refused with what to do instead, and a person who writes on the
    thread is still the one answered."""
    s = MemoryStore(); tid, gen = notice_task(s), notice_task(s, 'general')
    assert wrapup.no_correspondent(s, tid) and wrapup.nobody_line(s, tid) == wrapup.NOTICE
    with mock.patch('taskuary.origin.of_task', return_value=('trusted', 'the code host the owner set up')):     # its notices are the owner's own
        assert wrapup.NOTICE in terminal.seed_text(s, tid, 'fix the build')
        assert wrapup.NOTICE in general._prompt(s, gen)[0] and 'REPLYING FOR THE OWNER' not in general._prompt(s, gen)[0]
    with mock.patch.object(wrapup, 'REFRESH', None): out = wrapup.agent_reply(s, tid, 'Fixed the import test; CI is green.', 'coding')
    assert not out['ok'] and out['why'].startswith(wrapup.NOTICE) and 'propose_email' in out['why'] and s.list_reviews('pending') == []
    names = lambda t: {x['name'] for x in c.post(f'/api/mcp?task={t}', headers=hdr(t),
                                                json={'jsonrpc': '2.0', 'id': 1, 'method': 'tools/list'}).json()['result']['tools']}
    with mock.patch.object(server, 'store', s): assert not names(tid) & set(agenttools.REPLY_TOOLS)
    # ...and once a person writes on the same thread, they are the one a reply answers
    pid = s.add_message({'TaskId': tid, 'ExternalId': 'n-2', 'ConversationId': 'c-9', 'Channel': 'email', 'FromName': 'Gail Moreno',
                         'FromEmail': 'gail@northwind.example', 'Subject': 'Re: Run failed', 'BodyText': 'Is main fixed?',
                         'SentAt': '2026-11-10 07:30:00', 'Status': 'routed'})
    s.add_message({'TaskId': tid, 'ExternalId': 'n-3', 'ConversationId': 'c-9', 'Channel': 'email', 'FromName': 'Code host',
                   'FromEmail': 'notifications@codehost.example', 'Subject': 'Run failed again', 'SenderClass': 'automated',
                   'BodyText': 'The run failed again.', 'SentAt': '2026-11-10 08:00:00', 'Status': 'routed'})
    assert wrapup.reply_target(s, tid) == pid and not wrapup.no_correspondent(s, tid)


def test_the_reply_tools_are_not_offered_on_the_owners_own_ask():
    s = MemoryStore(); own, mailed = own_task(s), mailed_task(s)
    names = lambda tid: {t['name'] for t in c.post(f'/api/mcp?task={tid}', headers=hdr(tid),
                                                 json={'jsonrpc': '2.0', 'id': 1, 'method': 'tools/list'}).json()['result']['tools']}
    with mock.patch.object(server, 'store', s):
        assert not names(own) & set(agenttools.REPLY_TOOLS) and set(agenttools.REPLY_TOOLS) <= names(mailed)
        r = c.post(f'/api/mcp?task={own}', headers=hdr(own), json={'jsonrpc': '2.0', 'id': 2, 'method': 'tools/call',
                                                                   'params': {'name': 'propose_reply', 'arguments': {'text': 'hi'}}}).json()
        assert 'unknown tool' in r['error']['message']
