"""THE ASSISTANT SAYS ONLY WHAT HAPPENED - a stress walk of the chat popup (the owner, 2026-11-04: "stress test the assistant popup - it says
it's doing things and it does not do them"). One ask at a time over the demo world, through the popup's own roads: concierge.say for the
answer, then the page's part of it played as AssistantView.decide plays it (a reply or a rewrite is the page's POST to the reply door).

Every row records three things - what the Assistant SAID (its line, and the page's receipt under it), what CHANGED in the store (a snapshot
before and after), and whether the two match. A line that claims an act the store does not show is the bug; so is an under-way line left
standing with nothing landing under it. Faults are injected per row - an operation that raises, a drafter that comes back empty or with the
same words, a guard that refuses, a start that never starts, a task that is not there - and the reply must say so, never claim it.

`python -m tests.assistant_stress` runs the scripted model (what a good model answers, so it is the app's honesty that is graded);
`--real` asks the installed claude CLI instead, on its own TASKUARY_HOME, never the owner's, and with no user-level settings (assistant_walk
.real_cli_safe). tests/test_assistant_says_what_happened.py holds the scripted rows in CI. Invented people only (Northwind, *.example)."""
import json, os, re, sys, tempfile, time
from contextlib import ExitStack
from unittest import mock

def c(_kind, **params): return 'CALL: ' + json.dumps({'kind': _kind, 'params': params})
def d(verb, **kw): return c(verb, **kw)          # a decision is a CALL like any tool (concierge.parse_decision)

SPAWNS = []          # the agents the dispatch door started this walk (no process is ever spawned: the door answers as a start would)


class Ask:
    """One thing the owner types. `table`: the pile key on screen. `script`: what a good model answers (scripted mode). `check(b, a)`: what
    changed, from the snapshots before and after - (words, did). `fault(stack)`: patches that make the act fail. `family`: the action family."""
    def __init__(self, family, text, table, script, check, fault=None, note=''):
        self.family, self.text, self.table, self.script, self.check, self.fault, self.note = family, text, table, script, check, fault, note


# ---- the store, before and after --------------------------------------------------------------------------------------------------
def snap(s) -> dict:
    from taskuary import memoryedit
    rows = lambda q: s._rows(q)
    return {'tasks': {t['TaskId']: {k: t.get(k) for k in ('Status', 'RemindAt', 'WatchedAt', 'Title', 'Priority', 'Kind')} for t in rows('SELECT * FROM task')},
            'reviews': {r['ReviewId']: {'draft': r.get('DraftText') or '', 'status': r.get('Status'), 'task': r.get('TaskId'),
                                        'env': s.review_envelope(r['ReviewId']) or {}} for r in rows('SELECT * FROM review')},
            'notes': {t: len([c for c in s.list_comments(t) if c.get('ActorType') == 'human']) for t in (x['TaskId'] for x in rows('SELECT TaskId FROM task'))},
            'todo': {t['TaskId']: [(i['text'], bool(i.get('done'))) for i in s.task_checklist(t['TaskId'])] for t in rows('SELECT TaskId FROM task')},
            'msgs': {m['MessageId']: m.get('Status') for m in rows('SELECT MessageId, Status FROM message')},
            'learned': s.get_doc(memoryedit.DOC) or '', 'settings': dict(s.get_settings() or {}), 'spawns': list(SPAWNS)}


def task(n, field, want):
    "The task's `field` became `want` (a value, or a predicate)."
    def chk(b, a):
        v = (a['tasks'].get(n) or {}).get(field)
        ok = want(v) if callable(want) else v == want
        return f"TQ-{n:04d} {field}: {(b['tasks'].get(n) or {}).get(field)!r} -> {v!r}", bool(ok) and v != (b['tasks'].get(n) or {}).get(field)
    return chk

def draft(rid=None, tid=None):
    "A review's draft is there, not empty, and not the words that were there before."
    def chk(b, a):
        r = rid or next((k for k, v in a['reviews'].items() if v['task'] == tid and v['status'] == 'pending'), None)
        was, now = (b['reviews'].get(r) or {}).get('draft', ''), (a['reviews'].get(r) or {}).get('draft', '')
        return (f"review {r}: {len(was)} -> {len(now)} chars{' (same words)' if now and now == was else ''}",
                bool(now.strip()) and now != was)
    return chk

def cc_has(rid, who):
    def chk(b, a):
        env = (a['reviews'].get(rid) or {}).get('env') or {}
        got = [x.lower() for x in (env.get('cc') or []) + (env.get('to') or [])]
        return f"review {rid} to/cc: {got}", any(who in x for x in got)
    return chk

def notes(n):
    def chk(b, a): return f"TQ-{n:04d} notes: {b['notes'].get(n)} -> {a['notes'].get(n)}", (a['notes'].get(n) or 0) > (b['notes'].get(n) or 0)
    return chk

def todos(n, text=None, done=None):
    def chk(b, a):
        was, now = b['todo'].get(n) or [], a['todo'].get(n) or []
        if done is None: return f"TQ-{n:04d} to-dos: {len(was)} -> {len(now)}", len(now) > len(was)
        hit = [d_ for t, d_ in now if text.lower() in t.lower()]
        return f"TQ-{n:04d} “{text}” done: {[d_ for t, d_ in was if text.lower() in t.lower()]} -> {hit}", bool(hit) and hit[0] == done
    return chk

def learned(words):
    def chk(b, a): return f"LEARNED.md has “{words}”: {words.lower() in a['learned'].lower()}", words.lower() in a['learned'].lower() and words.lower() not in b['learned'].lower()
    return chk

def spawned(n):
    def chk(b, a): new = a['spawns'][len(b['spawns']):]; return f"agents started: {new}", n in new
    return chk

def nothing(b, a):
    "An ask that should change nothing in the store (a page opened, a look-up, a button lit for the owner's own press)."
    ch = [k for k in ('tasks', 'reviews', 'notes', 'todo', 'learned', 'spawns') if
          ({x: a[k].get(x) for x in b[k]} if isinstance(b[k], dict) else a[k]) != b[k]]          # the chat's own task is new: not a change
    return f"changed: {ch or 'nothing'}", False

def setting(key, want):
    def chk(b, a): return f"{key}: {b['settings'].get(key)!r} -> {a['settings'].get(key)!r}", str(a['settings'].get(key)) == str(want) != str(b['settings'].get(key))
    return chk


# ---- the faults ---------------------------------------------------------------------------------------------------------------------
def drafter(text):
    "The drafting AI answers `text` (None: it raises; '': nothing; 'SAME': the words already in the box)."
    def f(st):
        from taskuary import responder
        def write(store, tid, rid, *a, **k):
            if text is None: raise RuntimeError('the drafting AI timed out')
            if text == 'SAME': return (store.get_review(rid) or {}).get('DraftText') or ''
            return text
        st.enter_context(mock.patch.object(responder, 'write_draft', write))
        st.enter_context(mock.patch.object(responder, 'draft_for_message', lambda store, m, rid, **k: write(store, None, rid)))
    return f

def no_effect(kind):
    "The operation's handler comes back as if it ran, and changes nothing - the shape a silent no-op has."
    def f(st):
        from taskuary import server
        real = server._run_operation
        st.enter_context(mock.patch.object(server, '_run_operation', lambda op, bg: {'ok': True} if op['kind'] == kind else real(op, bg)))
    return f

def raises_op(kind, err='the database is busy'):
    def f(st):
        from taskuary import server
        real = server._run_operation
        def run(op, bg):
            if op['kind'] == kind: raise RuntimeError(err)
            return real(op, bg)
        st.enter_context(mock.patch.object(server, '_run_operation', run))
    return f

def start_fails(how):
    def f(st):
        from taskuary import server
        def go(tid, body, bg):
            if how == 'raise': raise RuntimeError('the coding tool was not found on this computer')
            return {'dispatch': 'session', 'started': False, 'existing': False, 'taskId': tid, 'ref': f'TQ-{int(tid):04d}'}
        st.enter_context(mock.patch.object(server, '_dispatch_task_to_its_agent', go))
    return f

def store_raises(attr, err='disk I/O error'):
    def f(st):
        from taskuary import server
        def raise_(*a, **k): raise RuntimeError(err)
        st.enter_context(mock.patch.object(server.store, attr, raise_))
    return f

def remember_says_ok():
    "The memory's write comes back ok and writes nothing."
    def f(st):
        from taskuary import memoryedit
        st.enter_context(mock.patch.object(memoryedit, 'remember', lambda store, t, *a, **k: {'ok': True, 'text': t, 'section': 'people', 'title': 'Your people', 'closed': None}))
    return f


# ---- the asks -----------------------------------------------------------------------------------------------------------------------
REDRAFT = 'Thanks for the reminder - invoice 88213 goes out with Friday\'s payment run, and I will send the remittance the same day.\n\nAlex'
ASKS = [
    # redraft and rewrite a reply with instructions
    Ask('redraft', "rewrite the draft: say we pay on Friday's run and I'll send the remittance", 'review:2',
        "Rewriting it.\n" + d('redraft', text="say we pay on Friday's run and I'll send the remittance"), draft(rid=2)),
    Ask('redraft', 'make the draft shorter and warmer', 'review:3', d('redraft', text='shorter and warmer'), draft(rid=3)),
    Ask('redraft', 'redraft it with my points: the cutover stays Thursday, Ray signs off the schema first', 'review:3',
        d('redraft', text='the cutover stays Thursday, Ray signs off the schema first'), draft(rid=3), fault=drafter(''), note='drafter returns nothing'),
    Ask('redraft', 'rewrite it to say the numbers go out tomorrow morning', 'review:4', d('redraft', text='the numbers go out tomorrow morning'),
        draft(rid=4), fault=drafter('SAME'), note='drafter returns the same words'),
    Ask('redraft', 'redo the draft - decline politely, I am out that week', 'review:5', d('redraft', text='decline politely, out that week'),
        draft(rid=5), fault=drafter(None), note='drafter times out'),
    Ask('reply', "reply to this: thanks, the laptop and accounts will be ready Monday", 'msg:2',
        d('reply', text='thanks, the laptop and accounts will be ready Monday'), draft(tid=2)),
    Ask('reply', "answer them: we'll have the audit list by Wednesday", 'msg:15', d('reply', text="we'll have the audit list by Wednesday"),
        draft(tid=11), fault=drafter(''), note='drafter returns nothing'),
    # change To/Cc
    Ask('cc', 'copy Gail Moreno on this reply', 'review:2', d('reply', text='', cc=['Gail Moreno']), cc_has(2, 'gail')),
    # mark done, remind me, watch it, not a task
    Ask('put-down', 'mark this done', 'msg:1', d('close'), task(1, 'Status', 'done')),
    Ask('put-down', 'done with this one', 'msg:2', d('close'), task(2, 'Status', 'done'), fault=raises_op('task.complete'), note='the close raises'),
    Ask('put-down', 'close it, it is handled', 'msg:2', d('close'), task(2, 'Status', 'done'), fault=no_effect('task.complete'), note='the close changes nothing'),
    Ask('remind', 'remind me about this tomorrow at 9', 'msg:15', c('task.defer', until='tomorrow 9am'), task(11, 'RemindAt', bool)),
    Ask('watch', 'watch this one for me', 'msg:17', c('task.watch', what='any'), task(12, 'WatchedAt', bool)),
    Ask('not-a-task', 'this is not a task', 'msg:45', d('remove'), task(30, 'Status', lambda v: v in (None, 'dropped'))),     # Not a task deletes it
    Ask('not-a-task', 'not a task, drop it', 'review:1', d('remove'), task(3, 'Status', 'dropped'), fault=no_effect('task.not_a_task'), note='the drop changes nothing'),
    # start an agent, continue an agent, answer an agent's question
    Ask('agent', 'start an agent on this: find where the 4,180 went', 'msg:1', d('regular_agent', text='find where the 4,180 went'), spawned(1)),
    Ask('agent', 'have an agent pull the audit documents together', 'msg:15', d('regular_agent', text='pull the audit documents together'),
        spawned(11), fault=start_fails('raise'), note='the agent tool is missing'),
    Ask('agent', 'send this to an agent', 'msg:15', d('regular_agent', text='work the audit requests'), spawned(11), fault=start_fails('empty'),
        note='the start comes back not started'),
    Ask('agent', 'continue the agent on TQ-0012 with: use the new template', None, c('agent.continue', ref='TQ-0012', note='use the new template'), nothing),
    Ask('agent', 'tell the agent on TQ-0006 to use the August bank file', None, c('agent.tell', ref='TQ-0006', text='use the August bank file'), notes(6)),
    # move or merge a task
    Ask('merge', 'merge TQ-0010 into TQ-0004', None, c('task.merge', ref='TQ-0010', into='TQ-0004'), task(10, 'Status', lambda v: v in ('done', 'dropped', 'merged'))),
    Ask('merge', 'merge TQ-0014 into TQ-0099', None, c('task.merge', ref='TQ-0014', into='TQ-0099'), task(14, 'Status', lambda v: v != 'reply'), note='no such task'),
    # add or tick a to-do
    Ask('todo', 'add a to-do: call the bank about the feed', 'msg:1', c('task.checklist', ref='TQ-0001', add=['call the bank about the feed']), todos(1)),
    Ask('todo', 'tick "find the 4,180"', 'msg:1', [c('task.check', ref='TQ-0001', item='find the 4,180', done=True), c('task.check', ref='TQ-0001', item=2, done=True)], todos(1, 'find the 4,180', True)),
    Ask('todo', 'add a to-do: chase Ray for the sign-off', 'msg:2', c('task.checklist', ref='TQ-0002', add=['chase Ray for the sign-off']), todos(2),
        fault=store_raises('merge_task_checklist'), note='the store write fails'),
    Ask('todo', 'tick the to-do about the zip file', 'msg:1', c('task.check', ref='TQ-0001', item='the zip file', done=True), todos(1, 'zip file', True), note='no such to-do'),
    # notes and fields
    Ask('note', 'add a note on TQ-0007: waiting on the vendor export', None, c('task.comment', ref='TQ-0007', text='waiting on the vendor export'), notes(7)),
    Ask('note', 'note on TQ-0009: Ray is out until Monday', None, c('task.comment', ref='TQ-0009', text='Ray is out until Monday'), notes(9),
        fault=store_raises('add_comment'), note='the store write fails'),
    Ask('rename', 'rename TQ-0007 to Census export cutover', None, c('task.update', ref='TQ-0007', title='Census export cutover'), task(7, 'Title', 'Census export cutover')),
    # open a page or a report
    Ask('open', 'open the AP ageing report', None, c('page.open', page='reports'), nothing),
    Ask('open', 'bring up TQ-0012', None, 'Here: [TQ-0012](#task=12).', nothing),
    # remember something
    Ask('remember', 'remember that Ray Colton signs off every schema change', None,
        c('memory.remember', note='Ray Colton signs off every schema change', about='Ray Colton', section='people'), learned('Ray Colton signs off every schema change')),
    Ask('remember', 'remember that Paula Vance runs the vendor portal', None,
        c('memory.remember', note='Paula Vance runs the vendor portal', about='Paula Vance', section='people'), learned('Paula Vance runs the vendor portal'),
        fault=remember_says_ok(), note='the write says ok and writes nothing'),
    # set a setting
    Ask('setting', 'turn off the sounds', None, c('setting.set', setting='sounds', value='off'), nothing),
    # hand off or email someone
    Ask('handoff', 'hand this to Gail Moreno', 'msg:15', c('task.handoff', ref='TQ-0011', who='Gail Moreno'), nothing),
    Ask('email', 'email Ray Colton asking for the schema sign-off by Friday', None,
        c('task.create_from_text', kind='send', text='Ask Ray Colton for the schema sign-off by Friday', to='Ray Colton'), nothing),
    # search
    Ask('search', 'find the mail about invoice 88213', None, c('pipe.read', text='invoice 88213'), nothing),
    # the wrong task
    Ask('wrong-task', 'mark TQ-0099 done', None, c('task.complete', ref='TQ-0099'), task(99, 'Status', 'done'), note='no such task'),
    Ask('wrong-task', 'mark TQ-0015 done', None, c('task.complete', ref='TQ-0015'), task(15, 'Status', lambda v: v != 'done'), note='already done'),
]


# ---- what was said ------------------------------------------------------------------------------------------------------------------
FAIL = re.compile(r"\b(could not|couldn.t|did not|didn.t|not done|not started|not sent|nothing was|nothing has|nothing changed|failed|no such|"
                  r"refused|can.t|cannot|unable|is not|isn.t|has no|no line|not on|not there|already)\b|✗|^Not ", re.I)
DONE = re.compile(r"^(✓|Done\b|Added|Ticked|Unticked|Noted|Remembered|Saved|Told|Answered|Pressed|Picked up|Marked|Put down|Put away|Merged|Moved|"
                  r"Renamed|Rewritten|Drafted|Took|Asked|Kept|Copied|Closed|Started|Wrote|Org chart|Set |Snoozed|Filed|Blocked|Stopped)", re.I)
UNDERWAY = re.compile(r"^(Rewriting|Drafting|Starting|Sending|Writing|Working|Putting|Clearing|Looking)\b", re.I)


def claim(said: str, out: dict) -> str:
    """done | failed | underway | lit | opened | words - what the owner reads the answer as."""
    if said.startswith('RAISED '): return 'failed'               # the popup's route answers 500: the page shows the error, nothing claimed
    if out.get('new'): return 'opened'                             # New brought up filled in: the owner's own press is still to come
    line = said.strip().splitlines()[-1].strip() if said.strip() else ''
    if line and FAIL.search(line): return 'failed'
    if out.get('pressed') and not line: return 'done'
    if line and DONE.search(line): return 'done'
    if line and UNDERWAY.search(line): return 'underway'
    if out.get('light') is not None: return 'lit'
    if out.get('open') or re.search(r'^Opened\b|\]\(#', line): return 'opened'
    return 'words'


def match(cl: str, did: bool) -> bool:
    """A claim of done needs the act; a failure said needs none; an under-way line standing alone is never a match - the page's receipt
    under it is what lands. A lit button, a page opened and words are the owner's to press: honest when nothing changed."""
    return {'done': did, 'failed': not did, 'underway': False}.get(cl, not did)


# ---- the page's part ----------------------------------------------------------------------------------------------------------------
def play_page(client, s, out: dict, table: dict | None) -> str:
    """What AssistantView.decide does with the answer's decision: a reply opens at once and its draft is written behind it (replyDraft
    .openReply, then /draft), a rewrite is the reply door's redraft - each handed the under-way line's id. What the owner reads after is the
    receipt the door confirmed, and the line itself said again in place (concierge.settle); a CC nobody knows is the page's own line."""
    dec = out.get('decision') or {}
    verb, cur = dec.get('verb'), dec.get('target') or table or {}
    if verb not in ('reply', 'redraft') or not cur.get('mid'): return ''
    line = {'line': dec['line']} if dec.get('line') else {}
    body = {'draft': True, 'instruction': dec.get('text') or None, **({'cc': dec['cc']} if dec.get('cc') else {}),
            **({'redraft': True} if verb == 'redraft' else {'later': True}), **line}
    r = client.post(f"/api/messages/{cur['mid']}/reply", json=body)
    if r.status_code >= 400: return f"✗ {r.json().get('detail') or r.status_code}"
    data, said = r.json(), []
    if data.get('cc_unknown'): said.append(f"✗ I have no address for {', '.join(data['cc_unknown'])} - add them in the reply's CC.")
    if data.get('drafting'):
        r2 = client.post(f"/api/reviews/{data['reviewId']}/draft", json={'instruction': dec.get('text') or None, **line})
        data = {**data, **(r2.json() if r2.status_code < 400 else {'receipt': {'status': 'failed', 'text': f"No reply was drafted - {r2.json().get('detail')}"}})}
    rc = data.get('receipt')
    if rc: said.append(('✗ ' if rc.get('status') == 'failed' else '✓ ') + rc['text'])
    # the page as it was before the receipt came from the door: any draft field wore the tick, and a reply drew no line at all
    elif verb == 'redraft': said.append('✓ Rewritten - read it below before you send it.' if data.get('draft') else '✗ I could not rewrite it here')
    return ' '.join(said)


def scripted(script):
    """What a good model answers: `script` on the first round (a list: one answer a round), and after a miss Taskuary handed back - an
    action that could not be done - that miss said plainly, as HOW YOU ACT asks."""
    rounds = list(script) if isinstance(script, list) else [script]
    def llm(system, user, max_tokens=None, **k):
        if rounds: return rounds.pop(0)
        m = re.search(r'it answered: ([^\n]*)', user)
        return f"That did not go through - {m.group(1).strip()}" if m else 'Ok.'
    return llm


def world(real: bool):
    from tests.assistant_walk import world as w
    s = w(real)
    s.set_task_checklist(1, ['pull the bank feed', 'find the 4,180', 'send Marcus the answer'], 'owner')
    return s


def guards(st, s, real: bool):
    from taskuary import concierge, general, ingest, server, terminal, toolcatalog, waitroom
    st.enter_context(mock.patch.object(server, 'store', s))
    st.enter_context(mock.patch.object(terminal, 'live_sessions', return_value=[]))
    st.enter_context(mock.patch.object(terminal, 'for_task', lambda tid, **k: None))
    st.enter_context(mock.patch.object(ingest, '_spawn')); st.enter_context(mock.patch.object(ingest, 'ask_later'))
    st.enter_context(mock.patch.object(general, 'start_session', return_value=mock.Mock()))
    st.enter_context(mock.patch.object(toolcatalog, '_offered', lambda store, kind: True))
    st.enter_context(mock.patch.object(server, '_brainless', lambda coding: ''))
    st.enter_context(mock.patch.object(waitroom, 'state', lambda store, tid: ('working', None)))
    def go(tid, body, bg):
        SPAWNS.append(int(tid)); s.update_task(int(tid), {'Status': 'in_progress'}, 'owner')
        return {'dispatch': 'session', 'started': True, 'existing': False, 'taskId': tid, 'ref': f'TQ-{int(tid):04d}'}
    st.enter_context(mock.patch.object(server, '_dispatch_task_to_its_agent', go))
    st.enter_context(mock.patch.object(concierge, '_compose_llm', return_value=lambda *a, **k: '{"kind": "report", "why": "scripted"}'))
    if not real:
        from taskuary import llm as llm_mod
        def never(*a, **k): raise AssertionError('a real model was asked for')
        st.enter_context(mock.patch.object(llm_mod, 'make_cli_llm', never))
        st.enter_context(mock.patch.object(llm_mod, 'build_llm', lambda *a, **k: (lambda *a_, **k_: REDRAFT)))
    else:
        from taskuary import agents
        env = agents.spawn_env
        st.enter_context(mock.patch.object(agents, 'spawn_env', lambda *a, **k: {k_: v for k_, v in env(*a, **k).items() if not k_.startswith('TASKUARY_')}))


def run(asks=ASKS, real: bool = False, fresh: bool = True, quiet: bool = True) -> list:
    """Every ask, each on a fresh demo world (`fresh`) so one row's act never decides the next row's check. Returns a row per ask."""
    from fastapi.testclient import TestClient
    from taskuary import concierge, funnel, server
    if quiet:
        from loguru import logger
        logger.remove()
    rows, s = [], None
    for a in asks:
        if fresh or s is None: s = world(real)
        with ExitStack() as st:
            guards(st, s, real)
            if a.fault: a.fault(st)
            client = TestClient(server.app, base_url='http://127.0.0.1', headers={'X-Taskuary-Token': server.cfg['server'].get('token') or ''})
            funnel.invalidate()
            table = (funnel.next_item(s, a.table, items=funnel.full_items(s)) or funnel.item_for_key(s, a.table)) if a.table else None
            llm = None if real else scripted(a.script)
            b, t0, err = snap(s), time.perf_counter(), None
            try: out = concierge.say(s, a.text, key=a.table, llm=llm)
            except Exception as e: out, err = {'say': f'RAISED {type(e).__name__}: {e}'}, e
            page = ''
            if err is None:
                try: page = play_page(client, s, out, table)
                except Exception as e: page = f'PAGE RAISED {type(e).__name__}: {e}'
            after = snap(s)
            changed, did = a.check(b, after)
            said = ' '.join(x for x in (str(out.get('say') or '').strip(), page) if x)
            shown = said or (f"(lit {out['light'].get('label')})" if out.get('light') else f"(pressed {out['pressed'].get('label')})" if out.get('pressed')
                             else f"(opened {out['open']})" if out.get('open') else '(nothing)')
            cl = claim(page or said, out)
            rows.append({'ask': a, 'said': shown, 'claim': cl, 'changed': changed, 'did': did, 'match': match(cl, did) and err is None,
                         'secs': time.perf_counter() - t0, 'out': out})
        if real: concierge_close()
    return rows


def concierge_close():
    from taskuary import clipool, concierge
    try: clipool.close(f'{concierge.LIVE_KEY}:')
    except Exception: pass


def table(rows) -> str:
    out = [f"{'family':<11}{'ask':<58}{'claim':<9}{'match':<6}said / changed"]
    for r in rows:
        a = r['ask']
        out.append(f"{a.family:<11}{a.text[:56]:<58}{r['claim']:<9}{'ok' if r['match'] else 'NO':<6}{r['said'][:150]!r}")
        out.append(f"{'':<11}{('fault: ' + a.note) if a.note else '':<58}{'':<15}-> {r['changed']}{'' if r['did'] else '  (no change)'}")
    bad = [r for r in rows if not r['match']]
    out.append(f"\n{len(rows)} asks, {len(rows) - len(bad)} match, {len(bad)} mismatch")
    return '\n'.join(out)


if __name__ == '__main__':
    real = '--real' in sys.argv
    if real:
        from tests.assistant_walk import real_cli_safe
        ok, why = real_cli_safe(); print(f'real CLI safe: {ok} - {why}')
        if not ok: sys.exit(1)
    pick = [a for a in ASKS if not (sys.argv[-1].startswith('family=')) or a.family == sys.argv[-1][7:]]
    rows = run(pick, real=real)
    print(table(rows))
