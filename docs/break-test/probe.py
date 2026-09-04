"""Break the assistant: every pipe item kind x every owner phrase, replaying what the PAGE does with the
server's decision, and diffing the receipt against the real effect. No model anywhere."""
import os, sys, json, re, tempfile, contextlib, io
os.environ['TASKUARY_HOME'] = tempfile.mkdtemp(prefix='tq-probe-')
REPO = r'C:\Users\unussbaum\Documents\General\Testing\taskhub'
sys.path[:0] = [REPO, REPO + r'\tests']
from unittest import mock
from fastapi.testclient import TestClient
from taskuary import concierge, funnel, general, ingest, server, terminal
from test_assistant_reactions import store, brain, arrive, session, ago, ahead

# ── builders: one of each thing the pipe can hold; returns (store, live_sessions, key) ─────────
def b_review(draft='Tuesday 3pm works.'):
    s = store(); out = arrive(s, subject='Are you around Tuesday?', body='Quick call?', llm=brain('reply_only', None))
    rv = s.pending_review(out['task_id'])
    if draft: s.update_review_draft(rv['ReviewId'], draft, rv.get('RunId'))    # a review with a real draft on it
    return s, [], f"review:{rv['ReviewId']}"
def b_todo():
    s = store()
    with mock.patch.object(ingest, '_spawn'): out = arrive(s, llm=brain('task', 'coding'))     # a stranger: held
    return s, [], f"msg:{out['message_id']}"
def b_general():
    s = store()
    with mock.patch.object(ingest, '_spawn'): out = arrive(s, subject='Which vendor?', body='Weigh these two quotes.', llm=brain('task', 'general'))
    return s, [], f"msg:{out['message_id']}"
def b_fyi():
    s = store()
    out = arrive(s, subject='FYI - Rebecca is back Tuesday', body='Just so you know.', who='Chana', email='chana@ours.com', conv='c:fyi', hours=2, llm=brain('fyi', None))
    return s, [], f"msg:{out['message_id']}"
def b_report(bad=False):
    s = store()
    sid = s.save_source({'Channel': 'report', 'Address': 'Nightly export', 'Owner': 'o', 'Active': 1, 'ConfigJson': json.dumps({'type': 'agent', 'title': 'Nightly export'})}, 'o')
    s.add_report_run(sid, {'at': ago(1), 'type': 'agent', 'title': 'Nightly export', 'failed': int(bad), 'error': 'timed out' if bad else None})
    funnel._SOURCES.update(at=0.0, by={})
    m = s.add_message({'ExternalId': 'r1', 'Channel': 'report', 'SourceName': 'Nightly export', 'Subject': 'Nightly export' + (' - FAILED' if bad else ' - 0 errors'),
                       'FromName': 'Nightly export', 'SentAt': ago(1), 'BodyText': 'error: timed out' if bad else 'Summary: all clear', 'Status': 'feed'})
    s.add_route(m, None, 'feed', None, 'a report you set up', [], 'feed'); funnel.invalidate()
    return s, [], f'msg:{m}' if False else f'report:{m}'
def b_agent():
    s = store()
    with mock.patch.object(ingest, '_spawn'): out = arrive(s, who='Chana', email='chana@ours.com', llm=brain('task', 'coding'))
    tid = out['task_id']; s.update_task(tid, {'Status': 'in_progress'}, 'router')
    live = session(tid, idle=200, waiting=True, tail=['Remove the old rows too? (y/n)'])
    return s, live, f'agent:{tid}'
def b_meeting():
    s = store(); s.set_setting('calendar_enabled', '1', 't')
    return s, [], 'meeting:*'
MEETING = [{'subject': 'Payroll cutover', 'start': ahead(10), 'end': ahead(40), 'who': ['Chana'], 'all_day': False, 'where': 'Teams', 'id': 'ev1'}]
def b_proposal():
    s = store()
    with mock.patch.object(ingest, '_spawn'): out = arrive(s, llm=brain('task', 'coding'))
    rid = s.add_review({'TaskId': out['task_id'], 'MessageId': out['message_id'], 'Kind': 'action', 'Status': 'pending',
                        'DraftText': json.dumps({'action': 'write_playbook', 'slug': 'pto-import', 'text': '# PTO import', 'why': 'it repeats'}), 'Reason': 'the agent proposes a playbook'})
    funnel.invalidate(); return s, [], f'review:{rid}'
def b_idea():
    s = store()
    # the line is ABOUT a real message - an idea pointing at a mid that does not exist is a fixture
    # bug, and every verb on it came back 404 rather than telling us anything
    m = s.add_message({'ExternalId': 'i1', 'Channel': 'email', 'Subject': 'Corrected file for the audit', 'FromName': 'Dana Weiss',
                       'FromEmail': 'dana@ours.com', 'SentAt': ago(96), 'BodyText': 'Can you send the corrected file?', 'Status': 'filed'})
    s.upsert_idea({'key': 'followup:c9', 'kind': 'followup', 'text': 'No answer from Dana in 4 days - follow up?', 'sig': 'x',
                   'action': {'type': 'followup', 'mid': m, 'why': 'you asked on Monday'}}, ago(1))
    funnel.invalidate(); items = funnel.build(s)['items']
    k = next(i['key'] for i in items if i['kind'] == 'idea'); return s, [], k
BUILDERS = {'review': b_review, 'review(no draft)': lambda: b_review(''), 'todo(coding held)': b_todo, 'general': b_general, 'fyi': b_fyi, 'report': b_report, 'report-FAILED': lambda: b_report(True),
            'agent-asking': b_agent, 'meeting': b_meeting, 'proposal': b_proposal, 'idea': b_idea}

PHRASES = ['next', 'done', 'later', 'tomorrow', 'skip', 'skip it', 'approve', 'send it', 'looks good, send it', 'yes', 'ok', 'sure', 'go ahead', 'do it', 'no', 'nah',
           'reply and tell them we will look at it', 'tell them to ignore it', 'let them know we will fix it by Friday', 'tell Chana it is handled',
           'not ours', 'not my problem', 'ignore it', "don't ignore this one", 'leave it open', 'leave it with the agent', 'never again', 'that sender is spam',
           'remember that Kishan handles refunds', 'remember to reply to him', 'send it to the coder', 'look into it', 'can you check if the report ran?',
           "I'll take it", "I'll handle this", 'mine', 'make it a task', 'close it', 'close the task', 'stop the agent', 'wrap it up', 'rerun it', 'split it',
           "what's this about?", 'who sent this?', 'summarize the thread', 'show me the draft', 'make the reply shorter', 'forward it to Chana', 'assign it to Chana',
           'ask Chana to handle it', 'delete it', 'archive it', 'snooze it', 'remind me tomorrow', 'approve and remember that Kishan handles refunds',
           'reply: not ours, sorry', 'skip all the newsletters', "it's handled", 'answer the agent: yes remove them', 'tell the agent yes', 'yes remove them',
           'set up a weekly report on refunds', 'never mind', 'hold on', 'wait', 'stop', 'cancel', 'undo', 'go back', 'what did I miss?',
           # the sentence names ANOTHER subject than the card on the table (the A1 finding)
           'not ours, facilities handles the payroll portal outage', 'close the payroll portal one', 'approve the invoice one']

def snap(s):
    d = {}
    for t in s.list_tasks(): d[f"task{t['TaskId']}"] = f"{t.get('Status')}/{t.get('Kind')}/{t.get('Assignee') or '-'}"
    for r in s.list_reviews(): d[f"review{r['ReviewId']}"] = r.get('Status')
    for row in s.feed(limit=50, days=30): d[f"msg{row['MessageId']}"] = f"{row.get('MsgStatus')}/{row.get('Category')}"
    for k, v in s.funnel_states().items(): d[f"fs[{k}]"] = v.get('Status')
    d['n_tasks'] = len(s.list_tasks()); d['n_memory'] = len(s._rows('SELECT * FROM memory')); d['n_reviews'] = len(s.list_reviews())
    d['n_ideas'] = len(s._rows('SELECT * FROM idea')) if s._rows("SELECT name FROM sqlite_master WHERE name='idea'") else 0
    return d

def diff(a, b): return {k: f"{a.get(k)} -> {b.get(k)}" for k in sorted(set(a) | set(b)) if a.get(k) != b.get(k)}

NEEDS = {'reply': 'mid', 'approve': 'rid', 'redraft': 'rid', 'not_ours': 'mid', 'not_ours_remember': 'mid', 'not_ours_sender': 'mid',
         'coder': 'mid', 'regular_agent': 'mid', 'mine': 'mid', 'forward': 'mid', 'archive': 'mid', 'answer_agent': 'tid',
         'rerun': 'source_id', 'close': 'tid'}
SETTLES = ('later', 'skip', 'next', 'done', 'closed', 'ack')     # the verbs that move the walk on

def page(c, cur, d, key, calls=None):
    """What AssistantView.decide() does with the server's decision. Returns a list of (call, status)."""
    calls = calls if calls is not None else []
    verb = d['verb']
    if d.get('target'):                                  # the words named another subject: acted on THERE
        cur = d['target']; key = None
        calls.append(f"PAGE: acting on the named item {cur.get('key')} - the one on the table is untouched")
    mid = cur.get('mid')
    def post(p, body=None):
        r = c.post(p, json=body) if body is not None else c.post(p); calls.append(f"POST {p} -> {r.status_code}{'' if r.status_code < 400 else ' ' + r.text[:80]}")
        if r.status_code >= 400: raise RuntimeError('PAGE: error banner, nothing after this ran')
        return r
    if verb in NEEDS and not cur.get(NEEDS[verb]): calls.append(f"PAGE-REFUSED: {cur.get('ref') or 'this one'} has nothing to {verb} on it"); return calls
    if verb == 'reply':
        post(f'/api/messages/{mid}/reply', {'draft': True, 'instruction': d.get('text') or None})
        if key: post('/api/funnel/settle', {'key': key, 'verb': 'done'})
        return calls
    if verb == 'redraft': post(f'/api/messages/{mid}/reply', {'draft': True, 'redraft': True, 'instruction': d.get('text') or None}); return calls
    if verb == 'answer_agent': post(f"/api/tasks/{cur['tid']}/waitroom", {'text': d.get('text') or 'yes'})
    elif verb == 'archive': post(f'/api/messages/{mid}/file', {'learn': False, 'archive': True})
    elif verb in ('remembered', 'forwarded', 'setting', 'split'): calls.append(f'PAGE: receipt only ({verb}) - nothing settles'); return calls
    elif verb == 'approve':
        r = post(f"/api/reviews/{cur['rid']}/decide", {'verb': 'approve', 'final_text': None, 'note': None})
        if (r.json() or {}).get('empty') or (r.json() or {}).get('already'):
            calls.append('PAGE: refused by the server - nothing sent, nothing settled'); return calls
    elif verb == 'not_ours_sender': post(f'/api/messages/{mid}/not-mine', {'scope': 'sender'})
    elif verb == 'remember': post('/api/memory', {'note': d.get('text'), 'scope': 'global'}); calls.append('PAGE: returns without settling or surfacing'); return calls
    elif verb == 'not_ours': post(f'/api/messages/{mid}/file', {'learn': False})
    elif verb == 'not_ours_remember': post(f'/api/messages/{mid}/not-mine', {'scope': 'subject'})
    # dispatch REFUSES to guess which agent (server.dispatch_message: 422 'Choose an agent type'),
    # because reading it off triage's kind is the bug that endpoint exists to prevent - so the page
    # names it, and the two hand-off verbs are the two answers (AssistantView.decide).
    elif verb == 'coder': post(f'/api/messages/{mid}/dispatch', {'kind': 'coding', 'instruction': d.get('text') or None})
    elif verb == 'regular_agent': post(f'/api/messages/{mid}/dispatch', {'kind': 'general', 'instruction': d.get('text') or None})
    # a follow-up is drafted through the pile's own door - the mail it chases may never have been a task
    elif verb == 'followup': post('/api/concierge/act', {'key': key, 'verb': 'followup'})
    elif verb == 'mine': post(f'/api/messages/{mid}/mine', {'kind': 'task'})
    elif verb == 'rerun': post(f"/api/reports/{cur['source_id']}/rerun")
    elif verb == 'close': r = c.patch(f"/api/tasks/{cur['tid']}", json={'Status': 'done'}); calls.append(f'PATCH task -> {r.status_code}')
    elif verb == 'stop_agent':
        # NOTE: `effects` stays empty here and that is the HARNESS, not a bug. Ending a session is
        # in-memory, and run_one mocks live_sessions and empties terminal.SESSIONS - so there is no
        # real pty to kill and snap() (tasks, reviews, messages, funnel_state) cannot see it either way.
        post(f"/api/tasks/{d['taskId']}/wrap", {'close': True}) if d.get('wrap') else post(f"/api/tasks/{d['taskId']}/agent/stop"); return calls
    elif verb in ('walkthrough', 'created', 'clear'): calls.append(f'PAGE: receipt only ({verb})'); return calls
    elif verb == 'setup': post('/api/concierge/setup', {'text': d.get('text')})
    elif verb == 'done' and cur.get('kind') != 'agent':
        if cur.get('rid'): post(f"/api/reviews/{cur['rid']}/decide", {'verb': 'no_reply', 'final_text': None, 'note': 'handled - the owner said so'})
        if cur.get('tid'): r = c.patch(f"/api/tasks/{cur['tid']}", json={'Status': 'done'}); calls.append(f'PATCH task done -> {r.status_code}')
    elif verb not in NEEDS and verb not in SETTLES:
        calls.append(f'PAGE: no road for {verb} - a receipt, and the item stays on the table'); return calls
    if not key: calls.append('PAGE: the named item was acted on; the table is untouched'); return calls
    if verb in ('later', 'skip'): post('/api/funnel/settle', {'key': key, 'verb': verb}); return calls
    post('/api/funnel/settle', {'key': key, 'verb': 'done'}); calls.append('PAGE: then surfaces the next item')
    return calls

def run_one(name, phrase):
    s, live, key = BUILDERS[name]()
    ctx = contextlib.ExitStack(); ctx.enter_context(mock.patch.object(terminal, 'live_sessions', return_value=live))
    ctx.enter_context(mock.patch.object(funnel, '_agenda', return_value=MEETING if name == 'meeting' else []))
    ctx.enter_context(mock.patch.object(server, 'store', s)); ctx.enter_context(mock.patch.dict(terminal.SESSIONS, {}, clear=True))
    spawn = ctx.enter_context(mock.patch.object(ingest, '_spawn')); ctx.enter_context(mock.patch.object(concierge, 'brain', return_value=None))
    ctx.enter_context(mock.patch.object(server, '_llm', return_value=None))
    with ctx:
        funnel.invalidate(); funnel.forget_states()
        c = TestClient(server.app, base_url='http://127.0.0.1', headers={'X-Taskuary-Token': server.cfg['server'].get('token') or ''})
        if key.endswith(':*'): key = next((i['key'] for i in funnel.build(s)['items'] if i['kind'] == key[:-2]), key)
        sf = concierge.surface(s, key, llm=None)
        cur = sf.get('item') or {}
        if cur.get('key') != key: return {'item': name, 'phrase': phrase, 'error': f"surface gave {cur.get('key')} not {key}: {sf['say'][:80]}"}
        before = snap(s)
        out = concierge.say(s, phrase, key=key, llm=None)
        d = out.get('decision')
        calls = ['PAGE: nothing (no decision)']
        if d:
            calls = []
            try: page(c, cur, d, key, calls)
            except RuntimeError as e: calls.append(str(e))
        after = snap(s)
        return {'item': name, 'phrase': phrase, 'verb': (d or {}).get('verb'), 'say': out['say'][:110], 'page': calls, 'spawned': spawn.called,
                'effects': diff(before, after), 'still_in_pipe': key in {i['key'] for i in funnel.build(s)['items']}}

if __name__ == '__main__':
    only = sys.argv[1:]
    rows = []
    for name in BUILDERS:
        if only and name not in only: continue
        for ph in PHRASES:
            try: rows.append(run_one(name, ph))
            except Exception as e: rows.append({'item': name, 'phrase': ph, 'error': f'{type(e).__name__}: {e}'})
    out = os.path.join(os.path.dirname(__file__), 'probe_out.json')
    json.dump(rows, open(out, 'w'), indent=1, default=str)
    print('wrote', out, len(rows))
