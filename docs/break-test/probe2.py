"""Flows, not phrases: cold start, the fyi batch, a setting asked mid-walk, later/skip coming back, lookup = read,
close under a live agent, 'skip it', the dead end after everything was shown."""
import os, sys, json, tempfile, contextlib
os.environ['TASKUARY_HOME'] = tempfile.mkdtemp(prefix='tq-probe2-')
REPO = r'C:\Users\unussbaum\Documents\General\Testing\taskhub'
sys.path[:0] = [REPO, REPO + r'\tests']
from unittest import mock
from datetime import datetime, timedelta
from fastapi.testclient import TestClient
from taskuary import concierge, funnel, general, ingest, server, terminal
from test_assistant_reactions import store, brain, arrive, session, ago, ahead

def H(): return {'X-Taskuary-Token': server.cfg['server'].get('token') or ''}
def chat(s): return [(h['role'], h['text'][:90], (h['card'] or {}).get('kind')) for h in concierge.history(s, general.dock_task(s)[0]['TaskId'])]
def keys(s): return [(i['key'], i['lane'], i.get('surfaced', False)) for i in funnel.build(s, keep_surfaced=True)['items']]
def show(title, *lines): print(f'\n### {title}'); [print('   ', l) for l in lines]

@contextlib.contextmanager
def world(s, live=()):
    with mock.patch.object(terminal, 'live_sessions', return_value=list(live)), mock.patch.object(server, 'store', s), \
         mock.patch.dict(terminal.SESSIONS, {}, clear=True), mock.patch.object(ingest, '_spawn') as sp, \
         mock.patch.object(concierge, 'brain', return_value=None), mock.patch.object(server, '_llm', return_value=None):
        funnel.invalidate(); funnel.forget_states()
        yield TestClient(server.app, base_url='http://127.0.0.1', headers=H()), sp

def three(s):
    with mock.patch.object(ingest, '_spawn'):
        a = arrive(s, subject='Are you around Tuesday?', body='Quick call?', llm=brain('reply_only', None))
        b = arrive(s, subject='Fix the export', body='Rows drop.', conv='c:b', hours=3, llm=brain('task', 'coding'))
        c = arrive(s, subject='FYI - Rebecca is back', body='Just so you know.', who='Chana', email='chana@ours.com', conv='c:c', hours=2, llm=brain('fyi', None))
        d = arrive(s, subject='FYI - lunch moved', body='Thursday now.', who='Chana', email='chana@ours.com', conv='c:d', hours=2, llm=brain('fyi', None))
    return a, b, c, d

# 1. cold start: the owner types before anything is on the table
s = store(); three(s)
with world(s) as (c, _):
    for t in ('next', 'done', 'approve', 'walk me through my tasks', 'start with the mail', "what's waiting?"):
        out = c.post('/api/concierge/say', json={'text': t, 'key': None}).json()
        show(f'cold start: {t!r}', f"item={bool(out.get('item'))} decision={out.get('decision')} say={out['say'][:100]!r}")

# 2. the fyi batch: what the owner says next
s = store(); three(s)
with world(s) as (c, _):
    for _ in range(2): c.post('/api/concierge/next', json={}).json()          # review, then todo
    out = c.post('/api/concierge/next', json={}).json()
    key = out['item']['key']; show('fyi batch surfaced', f"key={key} say={out['say'][:100]!r}")
    for t in ('next', 'done', 'not ours', 'skip all the fyi from Chana'):
        o = c.post('/api/concierge/say', json={'text': t, 'key': key}).json()
        show(f'on the fyi batch: {t!r}', f"decision={o.get('decision')} say={o['say'][:110]!r}")
    show('pile after', *keys(s))

# 3. a setting named while a review is on the table -> the page has no 'setting' branch and settles the item
s = store(); a, b, c_, d = three(s)
with world(s) as (c, _):
    out = c.post('/api/concierge/next', json={}).json(); key = out['item']['key']
    o = c.post('/api/concierge/say', json={'text': 'stop auto-starting the coder', 'key': key}).json()
    show('setting mid-walk', f"key on table={key}", f"decision={o.get('decision')}", f"say={o['say'][:120]!r}", 'PAGE: verb "setting" has no branch -> done(null) -> settle(key, done) -> the review is marked done for good')

# 4. later / skip: when do they come back
s = store(); three(s)
with world(s) as (c, _):
    out = c.post('/api/concierge/next', json={}).json(); key = out['item']['key']
    r = c.post('/api/funnel/settle', json={'key': key, 'verb': 'later'}).json(); show('later', r)
    out = c.post('/api/concierge/next', json={}).json(); key2 = out['item']['key']
    r = c.post('/api/funnel/settle', json={'key': key2, 'verb': 'skip'}).json(); show('skip (tomorrow)', r, f"now={datetime.now():%H:%M}")

# 5. lookup = read: asking ABOUT a thing marks it shown
s = store(); three(s)
with world(s) as (c, _):
    before = keys(s)
    o = c.post('/api/concierge/say', json={'text': 'what did Chana say about Rebecca?', 'key': None}).json()
    show('lookup', f"item={(o.get('item') or {}).get('key')} say={o['say'][:100]!r}", 'before: ' + str(before), 'after:  ' + str(keys(s)))

# 6. close it under a live agent; not ours under a live agent
for words in ('close it', 'not ours', 'done'):
    s = store()
    with mock.patch.object(ingest, '_spawn'): out = arrive(s, who='Chana', email='chana@ours.com', llm=brain('task', 'coding'))
    tid = out['task_id']; s.update_task(tid, {'Status': 'in_progress'}, 'router')
    live = session(tid, idle=200, waiting=True, tail=['Remove the old rows too? (y/n)'])
    with world(s, live) as (c, _):
        o = c.post('/api/concierge/next', json={}).json(); key = o['item']['key']
        o = c.post('/api/concierge/say', json={'text': words, 'key': key}).json()
        d = o.get('decision') or {}
        if d.get('verb') == 'not_ours': r = c.post(f"/api/messages/{out['message_id']}/file", json={'learn': False}).json()
        elif d.get('verb') == 'done': r = c.patch(f'/api/tasks/{tid}', json={'Status': 'done'}).json()
        else: r = None
        show(f'{words!r} with an agent parked on it', f"decision={d} say={o['say'][:90]!r}", f"page call -> {str(r)[:80]}",
             f"task now: {s.get_task(tid)}", f"pipe: {keys(s)}", 'live session untouched (no /agent/stop was called)')

# 7. 'skip it' - a sweep with a pronoun: what does it sweep?
s = store(); three(s)
with world(s) as (c, _):
    o = c.post('/api/concierge/next', json={}).json(); key = o['item']['key']
    o2 = c.post('/api/concierge/say', json={'text': 'skip it', 'key': key}).json()
    show("'skip it' on the review", f"decision={o2.get('decision')}", f"say={o2['say'][:120]!r}", f"pipe: {keys(s)}")
    o = c.post('/api/concierge/next', json={}).json(); key = o['item']['key']
    o2 = c.post('/api/concierge/say', json={'text': 'skip it', 'key': key}).json()
    show("'skip it' on the todo", f"decision={o2.get('decision')}", f"say={o2['say'][:120]!r}", f"pipe: {keys(s)}")

# 8. the dead end: everything shown, nothing decided
s = store(); three(s)
with world(s) as (c, _):
    for _ in range(3): c.post('/api/concierge/next', json={})
    o = c.post('/api/concierge/next', json={}).json(); show('after everything was shown once', f"say={o['say'][:200]!r}", f"left={o.get('left')}")
    o = c.post('/api/concierge/say', json={'text': 'next', 'key': None}).json(); show("...and 'next' typed then", f"decision={o.get('decision')} say={o['say'][:120]!r}")

# 9. the same phrase twice: is 'approve' idempotent? approve then approve again (page double-click / repeated word)
s = store(); three(s)
with world(s) as (c, _):
    o = c.post('/api/concierge/next', json={}).json(); key = o['item']['key']; rid = o['item']['rid']
    with mock.patch('taskuary.outbound.reply_to_message', return_value={'channel': 'email', 'to': ['x'], 'cc': []}):
        r1 = c.post(f'/api/reviews/{rid}/decide', json={'verb': 'approve', 'final_text': None, 'note': None})
        r2 = c.post(f'/api/reviews/{rid}/decide', json={'verb': 'approve', 'final_text': None, 'note': None})
    show('approve twice', f"first={r1.status_code} {r1.text[:100]}", f"second={r2.status_code} {r2.text[:100]}")
    o = c.post('/api/concierge/say', json={'text': 'approve', 'key': key}).json()
    show("'approve' said on an already-sent review (stale key)", f"decision={o.get('decision')} say={o['say'][:100]!r}")

# 10. a reply with no draft yet: 'approve' on a review whose DraftText is empty
s = store()
out = arrive(s, subject='Are you around Tuesday?', body='Quick call?', llm=brain('reply_only', None))
rv = s.pending_review(out['task_id'])
with world(s) as (c, _):
    o = c.post('/api/concierge/next', json={}).json(); key = o['item']['key']
    show('review with NO draft', f"draft flag={o['item'].get('draft')} say={o['say'][:140]!r}")
    o2 = c.post('/api/concierge/say', json={'text': 'approve', 'key': key}).json()
    r = c.post(f"/api/reviews/{rv['ReviewId']}/decide", json={'verb': 'approve', 'final_text': None, 'note': None})
    show("'approve' with no draft", f"decision={o2.get('decision')} say={o2['say'][:80]!r}", f"decide -> {r.status_code} {r.text[:120]}")

print('\nCHAT TRANSCRIPT of the last world:'); [print('   ', x) for x in chat(s)]
