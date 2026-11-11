"""Agent channels (agentchannels.py): a WhatsApp, Telegram, Slack or Teams chat bound to one coding agent. Named members only; a
teammate's words reach the agent labelled and are never the owner's authority - no permission, no landing, no answer to what the agent
asked; the agent stays in its repo; and only its own answers, questions and permission requests reach the chat."""
import json, os, tempfile, threading, time
from types import SimpleNamespace
from unittest import mock

import pytest

from taskuary import agentchannels as ac, landing, messengers, permissions as perm, terminal as term, waitroom, workerstate as ws
from taskuary.ingest import ingest_message
from taskuary.store import MemoryStore, task_ref
from taskuary.testing import Factory

REPO = tempfile.mkdtemp(prefix='ledger_')
ELSEWHERE = tempfile.mkdtemp(prefix='portal_')
GAIL, RAY = {'name': 'Gail Moreno', 'id': 'U0GAIL', 'role': 'teammate'}, {'name': 'Ray Colton', 'id': 'U0RAY', 'role': 'teammate'}
ME = {'name': 'Alex Doyle', 'id': 'U0ALEX', 'role': 'owner'}
CHAN = 'C0LEDGER'


class World:
    def __init__(self):
        self.s, self.posts, self.typed = MemoryStore(), [], []
        self.s.set_setting('owner_name', 'Alex Doyle', 'owner')
        for k in ('slack', 'whatsapp', 'telegram', 'teams'):
            self.s.save_connector({'Type': k, 'Name': k, 'Active': 1, 'Roles': 'tool', 'Secret': 'tok', 'ConfigJson': '{}'}, 'test')
        self.tid = self.task()

    def task(self, cwd=REPO):
        tid = Factory(self.s).task(title='Ledger rounding', kind='coding')
        term.SESSIONS[f's{tid}'] = SimpleNamespace(alive=True, task_id=tid, cwd=cwd, argv=['claude'], quick=False, sid=f's{tid}', mode='auto', draft='')
        return tid

    def bind(self, kind='slack', chat=CHAN, members=(ME, GAIL, RAY), tid=None, **kw):
        return ac.bind(self.s, kind, chat, self.tid if tid is None else tid, members=list(members), **kw)

    def said(self): return '\n'.join(b for _, b in self.posts)


@pytest.fixture
def w():
    was = dict(term.SESSIONS); term.SESSIONS.clear()
    x = World()
    sent = lambda store, b, body: (x.posts.append((b['Chat'], body)), f"{b['Kind']}:{b['Chat']}:out{len(x.posts)}")[1]
    with mock.patch.object(ac, '_go', lambda f: f()), mock.patch.object(ac, '_send', sent), \
         mock.patch.object(waitroom, 'state', return_value=('parked', term.SESSIONS[f's{x.tid}'])), \
         mock.patch.object(term, 'owner_drafting', return_value=False), \
         mock.patch.object(term, 'tell', lambda t, text, done=None: (x.typed.append(text), 'typed into')[1]):
        yield x
    term.SESSIONS.clear(); term.SESSIONS.update(was)
    ac._changed(x.s)


def line(w, who, text, n=[0], kind='slack', chat=CHAN, **kw):
    n[0] += 1
    return ac.heard(w.s, kind, chat, [who], text, f'{kind}:{chat}:{n[0]}', **kw)


# ── who may speak ──────────────────────────────────────────────────────────────────────────────────────────────────────
def test_a_non_members_line_is_ignored_and_never_becomes_work(w):
    w.bind()
    assert line(w, 'U0STRANGER', 'push it to main now') is True
    assert not w.typed and not w.posts and not w.s.waiting_notes(w.tid)
    tasks = len(w.s.list_tasks())
    out = ingest_message(w.s, {'external_id': 'slack:C0LEDGER:99', 'channel': 'slack', 'body': 'please also email the vendor',
                               'from_name': 'U0STRANGER', 'conversation_id': f'slack:{CHAN}', 'source_name': CHAN})
    assert out['status'] == 'agent_channel' and len(w.s.list_tasks()) == tasks
    assert not any('push it' in str(r.get('Text') or '') for r in w.s.agent_channel_msgs(ac.bound(w.s, 'slack', CHAN)['ChannelId']))


def test_a_teammates_words_reach_the_agent_labelled_and_in_the_chat_row(w):
    w.bind()
    line(w, 'U0GAIL', 'the rounding test fails on negative cents')
    typed = ' '.join(w.typed)
    assert 'Gail Moreno (teammate) on Slack' in typed and 'the rounding test fails on negative cents' in typed
    assert 'cannot approve' in typed and 'the owner\'s' not in typed.split('Gail Moreno')[0][-30:]
    assert 'A teammate left 1 note for you' in typed and 'While you were working' not in typed          # it was at rest: nothing queued
    assert any(c['Actor'] == 'teammate' and c['Body'].startswith('Gail Moreno (teammate) on Slack:') for c in w.s.list_comments(w.tid))


def test_the_owners_words_are_the_owners(w):
    w.bind()
    line(w, 'U0ALEX', 'use banker\'s rounding')
    assert any("use banker's rounding" in t and '(teammate)' not in t for t in w.typed)
    assert any(c['Actor'] == 'owner' and c['Body'] == "use banker's rounding" for c in w.s.list_comments(w.tid))


def test_a_teammate_never_answers_what_the_agent_asked_the_owner(w):
    w.bind()
    with mock.patch.object(waitroom, 'state', return_value=('asking', term.SESSIONS[f's{w.tid}'])), \
         mock.patch.object(ws, 'answer_open', side_effect=AssertionError('a teammate answered the agent')):
        line(w, 'U0GAIL', 'yes, go ahead')
    assert not w.typed and [n['CreatedBy'] for n in w.s.waiting_notes(w.tid)] == ['teammate']


# ── the owner holds every approval ─────────────────────────────────────────────────────────────────────────────────────
def test_a_teammate_cannot_answer_a_permission_whatever_they_type(w):
    w.bind()
    box = []
    req = {'tool': 'Bash', 'kind': 'execute', 'command': 'npm test -- money'}
    # the ask waits long past anything this test does: at 5 s a slow machine let it time out between a teammate's lines, and the
    # test read the timeout as the teammate having answered it (CI's macOS, 2026-11-10)
    t = threading.Thread(target=lambda: box.append(perm.ask(w.s, w.tid, req, wait=120)), daemon=True); t.start()
    # ...and waits for what it reads next - the ask SAID in the channel, which lands after the ask is pending (CI's macOS, 2026-11-11)
    for _ in range(1500):
        if perm.pending(w.tid, w.s) and 'asks permission' in w.said(): break
        time.sleep(0.02)
    assert 'asks permission' in w.said() and '1. Allow once' in w.said() and 'only Alex Doyle can answer' in w.said()
    for words in ('1', 'Allow once', 'allow_once', 'Always allow', '2'):
        line(w, 'U0GAIL', words)
        assert perm.pending(w.tid, w.s), f'{words!r} from a teammate answered it'
    assert ac.OWNER_ONLY in w.said()
    line(w, 'U0GAIL', 'yes')                      # plain words go to the agent, labelled - and still answer nothing
    assert perm.pending(w.tid, w.s)
    line(w, 'U0ALEX', '1'); t.join(3)
    assert box == ['allow_once'] and 'Allow once - ' in w.said()


def test_a_teammate_cannot_land_and_the_owners_pick_lands(w):
    w.bind()
    st = {'ask': True, 'line': 'fix-rounding is 2 commits ahead of main', 'answers': [{'how': 'rebase', 'label': 'Rebase and fast-forward'},
          {'how': 'merge', 'label': 'Merge commit'}, {'how': 'pr', 'label': 'Open a PR'}], 'proposal': None}
    landed = []
    with mock.patch.object(landing, 'state', return_value=st), \
         mock.patch.object(landing, 'land', lambda s, tid, how, actor='owner': (landed.append((tid, how, actor)), {'says': 'Landed by merge commit.'})[1]):
        line(w, 'U0GAIL', 'land')
        assert not (ac.bound(w.s, 'slack', CHAN)['state'].get('ask')) and ac.OWNER_ONLY in w.said()
        line(w, 'U0ALEX', 'land')
        assert '2. Merge commit' in w.said()
        for words in ('2', 'Merge commit', 'merge commit.'): line(w, 'U0GAIL', words)
        assert not landed
        line(w, 'U0ALEX', 'merge commit')
    assert landed == [(w.tid, 'merge', 'owner')] and 'Landed by merge commit.' in w.said()


def test_a_teammate_typing_push_or_send_only_reaches_the_agent_as_their_words(w):
    w.bind()
    with mock.patch.object(landing, 'land', side_effect=AssertionError('landed')), \
         mock.patch('taskuary.outbound.send_slack', side_effect=AssertionError('sent')):
        for words in ('push it to main', 'send the fix to the vendor', 'approve and merge'):
            line(w, 'U0RAY', words)
    assert all('Ray Colton (teammate)' in t and 'cannot approve, land, push, send' in t for t in w.typed) and len(w.typed) == 3


def test_a_teammate_listed_under_the_owners_id_is_still_the_owner_and_nobody_else(w):
    b = ac.bound(w.s, 'slack', CHAN) or w.bind()
    b = ac.bound(w.s, 'slack', CHAN)
    assert ac.member(b, ['U0ALEX'])['role'] == 'owner' and ac.member(b, ['u0gail'])['name'] == 'Gail Moreno' and ac.member(b, ['U0X']) is None
    assert ac.member(b, [], from_me=True)['role'] == 'owner'


# ── scope ──────────────────────────────────────────────────────────────────────────────────────────────────────────────
def test_the_agent_stays_in_the_bound_repo(w):
    w.bind()
    term.SESSIONS[f's{w.tid}'].cwd = ELSEWHERE                 # the task's checkout moved out of the repo the chat was opened for
    line(w, 'U0GAIL', 'look at the portal too')
    assert not w.typed and 'Nothing was sent' in w.said() and 'works outside' in w.said()
    term.SESSIONS[f's{w.tid}'].cwd = os.path.join(REPO, 'sub')
    os.makedirs(os.path.join(REPO, 'sub'), exist_ok=True)
    line(w, 'U0GAIL', 'and the sub folder')
    assert w.typed and 'keep to' in w.typed[-1]


def test_binding_is_checked(w):
    with pytest.raises(ValueError, match='not a folder'): w.bind(repo=os.path.join(REPO, 'nope'))
    with pytest.raises(ValueError, match='yours alone'): ac.bind(w.s, 'slack', 'C0ALL', None, members=[ME, GAIL])
    with pytest.raises(ValueError, match='which messages are yours'): ac.bind(w.s, 'slack', 'C0X', w.tid, members=[GAIL])
    with pytest.raises(ValueError, match='name and their'): w.bind(members=[ME, {'name': 'Gail Moreno', 'role': 'teammate'}])
    general = Factory(w.s).task(title='Payroll question')
    with pytest.raises(ValueError, match='coding task'): w.bind(tid=general)
    w.bind()
    with pytest.raises(ValueError, match='one agent per chat'): w.bind()
    with mock.patch('taskuary.agents.developer_mode', return_value=False), pytest.raises(PermissionError): ac.bind(w.s, 'slack', 'C0Y', w.tid, members=[ME])
    v = ac.view(w.s, w.tid)
    assert [c['chat'] for c in v['channels']] == [CHAN] and {k['kind'] for k in v['kinds']} == set(ac.KINDS)
    ac.unbind(w.s, v['channels'][0]['id'])
    assert not ac.bound(w.s, 'slack', CHAN)


def test_whatsapp_owner_needs_no_id_and_the_assistant_chat_is_not_bindable(w):
    b = w.bind('whatsapp', '120363000000000001@g.us', members=[{'name': 'Gail Moreno', 'id': '+1 555 010 2233', 'role': 'teammate'}])
    assert b['members'][0]['role'] == 'owner'
    assert ac.heard(w.s, 'whatsapp', '120363000000000001@g.us', ['whatsapp:15550102233'], 'hi from gail', 'wa:1')
    assert 'Gail Moreno (teammate) on WhatsApp' in w.typed[-1]
    assert ac.heard(w.s, 'whatsapp', '120363000000000001@g.us', [''], 'owner here', 'wa:2', from_me=True)
    assert w.typed[-1].endswith('owner here') or 'owner here' in w.typed[-1]
    wa = w.s.connectors_by_type('whatsapp')[0]
    w.s.merge_connector_config(wa['ConnectorId'], {'assistant_chat': '15550001111@s.whatsapp.net'})
    with pytest.raises(ValueError, match='Assistant chat'): ac.bind(w.s, 'whatsapp', '15550001111@s.whatsapp.net', w.tid, members=[])


# ── what reaches the chat ──────────────────────────────────────────────────────────────────────────────────────────────
def test_only_the_bound_agents_answers_and_questions_reach_the_chat(w):
    w.bind()
    other = w.task()
    ws.record(w.s, other, f's{other}', 'turn_end', text='The portal build is green.')
    ws.record(w.s, other, f's{other}', 'input_needed', text='Which portal branch?')
    assert not w.posts, 'another task spoke on the chat'
    ws.record(w.s, w.tid, f's{w.tid}', 'turn_end', text='**Fixed** the rounding: `round_half_even` now.')
    ws.record(w.s, w.tid, f's{w.tid}', 'input_needed', text='Should negative cents round toward zero?')
    assert w.posts[0][1].startswith('*Fixed* the rounding') and '**' not in w.posts[0][1]          # rendered for Slack
    assert 'is waiting on you: Should negative cents round toward zero?' in w.posts[1][1] and len(w.posts) == 2
    ws.record(w.s, w.tid, f's{w.tid}', 'turn_end', text='interrupted')
    assert len(w.posts) == 2


def test_our_own_post_read_back_is_not_the_owners_line(w):
    w.bind()
    ws.record(w.s, w.tid, f's{w.tid}', 'turn_end', text='Fixed the rounding.')
    ext = next(r['ExtId'] for r in w.s.agent_channel_msgs(ac.bound(w.s, 'slack', CHAN)['ChannelId']) if r['Dir'] == 'out')
    assert ac.heard(w.s, 'slack', CHAN, ['U0ALEX'], 'Fixed the rounding.', ext)                 # by its id
    assert ac.heard(w.s, 'slack', CHAN, ['U0ALEX'], 'Fixed the rounding.', 'slack:C0LEDGER:other')   # by its words, just now
    assert not w.typed


def test_with_developer_mode_off_a_bound_chat_goes_nowhere(w):
    w.bind()
    with mock.patch('taskuary.agents.developer_mode', return_value=False):
        assert line(w, 'U0ALEX', 'keep going')
        ws.record(w.s, w.tid, f's{w.tid}', 'turn_end', text='Done.')
    assert not w.typed and not w.posts


# ── the pollers route first ────────────────────────────────────────────────────────────────────────────────────────────
def test_slack_reads_a_bound_channel_by_its_own_cursor(w):
    w.bind()
    hist = {'messages': [{'ts': '1767000002.0', 'user': 'U0GAIL', 'text': 'second'}, {'ts': '1767000001.0', 'user': 'U0GAIL', 'text': 'first'},
                         {'ts': '1767000003.0', 'bot_id': 'B1', 'text': 'Fixed the rounding.'}, {'ts': '1767000004.0', 'user': 'U0BOB', 'text': 'me too'}]}
    c = w.s.connectors_by_type('slack')[0]
    with mock.patch('taskuary.channels._slack', return_value=hist): ac.poll_slack(w.s, c, 'tok')
    assert ['first' in w.typed[0], 'second' in w.typed[1], len(w.typed)] == [True, True, 2]
    assert ac.bound(w.s, 'slack', CHAN)['state']['cursor'] == 1767000004.0
    with mock.patch('taskuary.channels._slack', return_value=hist): ac.poll_slack(w.s, c, 'tok')
    assert len(w.typed) == 2, 'a re-read routed a line twice'


def test_telegram_routes_a_bound_group_before_anything_else(w):
    w.bind('telegram', '-100777', members=[{'name': 'Alex Doyle', 'id': '4242', 'role': 'owner'}, {'name': 'Gail Moreno', 'id': '5151', 'role': 'teammate'}])
    ups = [{'update_id': 1, 'message': {'message_id': 10, 'chat': {'id': -100777, 'type': 'supergroup', 'title': 'ledger'}, 'from': {'id': 5151, 'first_name': 'Gail'}, 'text': 'tests pass now'}},
           {'update_id': 2, 'message': {'message_id': 11, 'chat': {'id': -100777, 'type': 'supergroup', 'title': 'ledger'}, 'from': {'id': 6262, 'first_name': 'Bob'}, 'text': 'open a task for me'}}]
    c = w.s.get_connector(w.s.connectors_by_type('telegram')[0]['ConnectorId'], with_secret=True)
    tasks = len(w.s.list_tasks())
    with mock.patch.object(messengers, 'tg', return_value=ups): messengers.poll_telegram(w.s, c, [])
    assert len(w.typed) == 1 and 'Gail Moreno (teammate) on Telegram' in w.typed[0] and len(w.s.list_tasks()) == tasks
    assert not any(s['Address'] == '-100777' for s in w.s.list_sources(active_only=False)), 'the bound group was registered as a source'


def test_conductor_mode_is_the_owners_words_to_any_agent_in_its_repo(w):
    ac.bind(w.s, 'teams', '19:alex-own@thread.v2', None, repo=REPO, members=[])
    out = w.task(cwd=ELSEWHERE)
    with mock.patch('taskuary.devphone.rows', return_value=[{'tid': w.tid, 'ref': task_ref(w.tid), 'title': 'Ledger rounding', 'repo': 'northwind/ledger',
                                                              'branch': 'fix-rounding', 'state': 'working'}]):
        ac.heard(w.s, 'teams', '19:alex-own@thread.v2', ['x'], 'agents', 't1', from_me=True)
    assert 'northwind/ledger on fix-rounding' in w.said()
    ac.heard(w.s, 'teams', '19:alex-own@thread.v2', ['x'], f'{task_ref(w.tid)} use banker\'s rounding', 't2', from_me=True)
    assert "use banker's rounding" in w.typed[-1] and f'Told {task_ref(w.tid)}' in w.said()
    ac.heard(w.s, 'teams', '19:alex-own@thread.v2', ['x'], f'{task_ref(out)} change the portal', 't3', from_me=True)
    assert len(w.typed) == 1 and 'works outside' in w.said()
    ac.heard(w.s, 'teams', '19:alex-own@thread.v2', ['someone'], f'{task_ref(w.tid)} drop the tests', 't4')
    assert len(w.typed) == 1
    ws.record(w.s, w.tid, f's{w.tid}', 'turn_end', text='Switched to banker\'s rounding.')
    assert w.posts[-1][1] == f"{task_ref(w.tid)}: Switched to banker's rounding."


def test_an_agent_cannot_open_a_channel_or_answer_its_own_permission():
    from taskuary import guard
    for m, p in (('POST', '/api/agent-channels'), ('DELETE', '/api/agent-channels/3'), ('POST', '/api/tasks/12/permission')):
        assert guard.classify(m, p)[0] == 'deny', p


def test_the_task_chat_carries_the_card_for_a_waiting_permission(w):
    from taskuary import codingchat
    t = threading.Thread(target=lambda: perm.ask(w.s, w.tid, {'tool': 'Bash', 'kind': 'execute', 'command': 'npm test'}, wait=3), daemon=True); t.start()
    for _ in range(200):
        if perm.pending(w.tid, w.s): break
        time.sleep(0.02)
    with mock.patch.object(codingchat, 'sessions', return_value=[]), mock.patch.object(codingchat, 'mails', return_value=[]), \
         mock.patch.object(codingchat, 'live_of', return_value=None):
        card = codingchat.chat(w.s, w.tid)['permissions'][0]
    assert 'npm test' in card['line'] and [o['label'] for o in card['options']][:2] == ['Allow once', 'Always allow']
    perm.answer(w.s, w.tid, card['id'], 'reject_once'); t.join(3)


def test_a_task_bound_to_a_teammate_chat_launches_safe_and_full_power_is_the_owner_s_choice(w):
    from taskuary import origin
    assert origin.of_task(w.s, w.tid)[0] != 'stranger'
    w.bind()
    with mock.patch.object(origin, '_claude_version', lambda cmd='claude': (2, 1, 300)):
        o, why = origin.of_task(w.s, w.tid)
        assert o == 'stranger' and 'Teammate chats' in why and origin.launch_mode(w.s, w.tid, 'claude') == 'auto'
        origin.raise_to(w.s, w.tid, 'owner', 'owner'); assert origin.of_task(w.s, w.tid)[0] == 'stranger'   # the owner's word does not lift it
        w.s.set_setting('teammate_chat_power', 'full', 'owner')
        assert origin.of_task(w.s, w.tid)[0] != 'stranger' and origin.launch_mode(w.s, w.tid, 'claude') == 'full'

def test_an_owner_only_binding_keeps_the_task_s_own_trust(w):
    from taskuary import origin
    w.bind(members=(ME,)); assert origin.of_task(w.s, w.tid)[0] != 'stranger'

def test_a_full_session_on_a_teammate_bound_task_gets_nothing_until_it_restarts_safe(w):
    w.bind(); term.SESSIONS[f's{w.tid}'].mode = 'full'
    line(w, 'U0GAIL', 'please fix the rounding')
    assert not w.typed and 'Nothing was sent' in w.said()
