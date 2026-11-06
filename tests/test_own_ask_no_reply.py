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


def test_the_reply_tools_are_not_offered_on_the_owners_own_ask():
    s = MemoryStore(); own, mailed = own_task(s), mailed_task(s)
    names = lambda tid: {t['name'] for t in c.post(f'/api/mcp?task={tid}', headers=hdr(tid),
                                                 json={'jsonrpc': '2.0', 'id': 1, 'method': 'tools/list'}).json()['result']['tools']}
    with mock.patch.object(server, 'store', s):
        assert not names(own) & set(agenttools.REPLY_TOOLS) and set(agenttools.REPLY_TOOLS) <= names(mailed)
        r = c.post(f'/api/mcp?task={own}', headers=hdr(own), json={'jsonrpc': '2.0', 'id': 2, 'method': 'tools/call',
                                                                   'params': {'name': 'propose_reply', 'arguments': {'text': 'hi'}}}).json()
        assert 'unknown tool' in r['error']['message']
