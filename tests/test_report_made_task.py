"""A task the owner made from a report is their own work, never "asked you" (2026-10-26): Put it on my list on a report run, and
Reopen task on a report-born task, filed the row in the asked lane - "a person asked you for something", the 🙋 pill and a lit
Reply - over a report no person wrote (the owner, 2026-09-16: "i don't like this asked you" on rows derived from a report).

A REPORT IS SENT ON AS A TASK (the owner, 2026-11-13): "it should just have button send to agent and that will move it to task"; "when you hit
send to agent it should look like every task with coming from and then you should be able to write what you want to send to agent about the
prompt so the report plus your prompt will be injected together into the agent on the task". The row offers Send to agent and no Make it a task.
AS A REPORT, A DASHBOARD OR AN FYI ALL DO (the owner, 2026-11-16: "they should all work the same ... it requires user prompt on the reports/dashboard
what they want to know about it"): his words go in the box the press opens on the item, and they start the agent on a task whose Came from is the
report - the press once made an empty task, its agent a line waiting on him."""
import time
from unittest import mock

from fastapi.testclient import TestClient

from taskuary import concierge, demo, funnel, general, operations, server, terminal
from taskuary.store import MemoryStore


def _world():
    s = MemoryStore(); demo.seed(s); funnel.invalidate()
    return s


def _lane(s, tid):
    funnel.invalidate()
    with mock.patch.object(terminal, 'live_sessions', return_value=[]):
        got = [i for i in funnel.build(s, keep_surfaced=True)['items'] if i.get('tid') == tid]
        return [(i['kind'], i['lane']) for i in got], funnel.item_for_key(s, f'task:{tid}')


def test_put_it_on_my_list_on_a_report_is_the_owners_own_work_and_so_is_reopening_it():
    s = _world()
    mid = s._one("SELECT MessageId FROM message WHERE Channel='report' ORDER BY MessageId LIMIT 1")['MessageId']
    with mock.patch.object(terminal, 'live_sessions', return_value=[]), mock.patch.object(server, 'store', s):
        concierge.run_proposal(s, operations.propose(s, 'task.create_from_message', mid, {'kind': 'task'}, 'owner'), 'owner')
    tid = s._one('SELECT TaskId FROM message WHERE MessageId=?', (mid,))['TaskId']
    assert tid
    rows, it = _lane(s, tid)
    assert rows == [('todo', 'yours')], rows
    assert (it['kind'], it['lane']) == ('todo', 'yours') and 'asked you' not in str(it.get('why'))
    s.update_task(tid, {'Status': 'done'}, 'owner'); s.update_task(tid, {'Status': 'open'}, 'owner')       # Reopen task
    rows, _ = _lane(s, tid)
    assert rows == [('todo', 'yours')], rows


def _report(s):
    with mock.patch.object(terminal, 'live_sessions', return_value=[]):
        return next(i for i in funnel.build(s, keep_surfaced=True)['items'] if i.get('kind') == 'report' and i.get('mid') and not i.get('bad'))


def test_a_report_row_offers_send_to_agent_and_never_make_it_a_task():
    s = _world()
    it = _report(s)
    verbs = [c['verb'] for c in concierge.chips_for(s, it)]
    assert 'regular_agent' in verbs and 'mine' not in verbs, verbs
    assert 'mine' not in [b['verb'] for b in concierge.row_buttons(s, it)]
    # ...nor by words or a sweep: the Assistant's Put it on my list says the one way, and pipe.mine leaves it
    assert concierge.cannot(it, 'mine', s) and 'Send to agent' in concierge.cannot(it, 'mine', s)
    from taskuary import bulk
    assert bulk.refusal(it, 'mine')


class Brain:
    "An API card's model: answers at once, and keeps what each turn was asked."
    def __init__(self): self.asked = []
    def __call__(self, system, user, **kw):
        self.asked.append(f'{system}\n\n{user}')
        return 'Read it - the biggest site is Fairhaven.'


def test_send_to_agent_on_a_report_starts_its_agent_on_the_report_and_his_words(monkeypatch):
    s = _world()
    it = _report(s)
    body = str(s.get_message(it['mid']).get('BodyText') or '')
    from taskuary import browserview, llm
    brain = Brain()
    monkeypatch.setattr(general, 'provider_options', lambda store: [{'pick': 'connector:1', 'label': 'Northwind AI', 'model': '', 'type': 'openai'}])
    monkeypatch.setattr(general, 'default_pick', lambda store, task=None: 'connector:1')
    monkeypatch.setattr(llm, 'build_llm', lambda *a, **k: brain)
    monkeypatch.setattr(browserview, 'installed', lambda: False)
    monkeypatch.setattr(browserview, 'can_set_up', lambda: False)
    words, tid = 'Pull out the three biggest numbers for Erin Blake', None
    with mock.patch.dict(terminal.SESSIONS, {}, clear=True), mock.patch.object(server, 'store', s), \
            mock.patch.object(terminal, 'live_sessions', return_value=[]):
        try:
            # ...the desk's press with his words, as the item's own box sends it (AssistantView.startOnItem)
            prop = concierge.propose_direct(s, 'regular_agent', it['key'], words, 'owner', table=True, exact=True, press=True)
            assert prop['label'] == 'Send to agent' and not prop['params'].get('box'), prop
            concierge.run_proposal(s, prop, 'owner')
            tid = s.get_message(it['mid'])['TaskId']
            end = time.time() + 20
            while not any(words in a for a in brain.asked) and time.time() < end: time.sleep(0.05)
        finally:
            for t in list(terminal.SESSIONS.values()):
                try: t.close()
                except Exception: pass
            if tid: general.answered(tid, every=True)
    # ...its Came from is the report, as any task made from a message
    assert tid and s.get_task(tid)['Source'] == 'report' and [m['MessageId'] for m in s.list_messages(tid)] == [it['mid']]
    # ...the agent's first turn has his words (the model's first call may be the task's own read of the message, triage.extract_ask)
    first = next((a for a in brain.asked if words in a), '')
    assert first, 'his words started no agent'
    # the report's own rows, as the run wrote them, reach that first turn as the task's source: in it, or - a report read from a source not marked
    # the owner's own system is a stranger's text (origin.report_rests_on) - in the source file it is told to read first
    from taskuary import origin
    src = origin.stranger_file_path(tid)
    seen = first + (src.read_text(encoding='utf-8') if str(src) in first and src.exists() else '')
    assert body and any(ln.strip() and ln.strip()[:60] in seen for ln in body.splitlines()[:3]), first[-3000:]
    assert general.handles(s.get_task(tid)), "the box made it the agent's"
    said = [c['Body'] for c in s.list_comments(tid) if c.get('ActorType') == general.USER_TYPE]
    assert said == [words], f'his words are his first line in its chat, once: {said}'
