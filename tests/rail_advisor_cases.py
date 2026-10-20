"""THE RAIL ADVISOR'S EVAL (2026-10-20): every kind of idea the clock Advisor (assistant.run) can put on the rail, each in a world where
it SHOULD fire and in worlds where it SHOULD NOT, through the real run with a scripted brain - plus the demo + faults world run twice
with every line put down between, which is where a line that repeats, or one about automated mail, shows itself.

    hit    - should fire and did
    miss   - should fire and did not
    quiet  - should not fire and did not
    noise  - fired and is not useful: the reason says which (automated mail, repeats after a No, too early, wrong person, stale,
             duplicates a row already on the rail, an agent already on it)
    said   - the world's lines that passed every check (no case says whether they should fire)

The brain is scripted (`brain`): it says every candidate the hub hands it, under that candidate's key - so what is measured is what
the CODE raises and lets through, not a model's taste - plus the lines a case scripts for it (a model's own idea, a connect line
citing the threads it was shown), and, like a model following the automation card, a skip-rule idea for a sender the card counts as
ignored by hand. Invented Northwind people only. Used by tests/test_rail_advisor_cases.py; `python -m tests.rail_advisor_cases`
prints the table."""
import json, os, re, tempfile
from datetime import datetime, timedelta
from unittest import mock

OWNER = 'alex@northwind.example'


def at(d=0, h=0, m=0): return (datetime.now() - timedelta(days=d, hours=h, minutes=m)).strftime('%Y-%m-%d %H:%M:%S')


def brain(extra=None):
    """The scripted model: the assistant's pass says every candidate (and `extra(user)`'s lines); triage files everything as fyi."""
    def llm(system, user, max_tokens=None, **kw):
        system, user = str(system or ''), str(user or '')
        if system.startswith('YOUR INSTRUCTION'):
            say = [{'key': k, 'text': f'{facts[:120]}', 'why': 'the hub found it', 'section': 'loose'}
                   for k, facts in re.findall(r'^\[((?:followup|promise|cold|prep):[^\]]+)\] (.*)$', user, re.M)]
            # ...and what a model reading the automation card proposes: a skip rule on a sender ignored by hand, again and again
            for who, n, ig in re.findall(r'^  (\S+@\S+): (\d+) msgs - 0 became tasks, (\d+) ignored', user, re.M):
                if int(ig) >= 8: say.append({'key': f'idea:skip-{who.split("@")[0]}', 'text': f'A skip rule on {who} would save you {ig} mails a month.',
                                            'why': f'{ig} of {n} ignored by hand', 'section': 'ideas'})
            say += (extra(user) if extra else [])
            return json.dumps({'say': say, 'notes': ''})
        if 'asks_them' in system:
            # the sent-words judge, read the way a model reads them: "I'll ..." promises, a question asks them
            vs = []
            for i, w in re.findall(r'^\[(m\d+)\] sent .*?:\n  "(.*)"$', user, re.M):
                p = bool(re.search(r"\bI'?ll\b|\bI will\b", w))
                vs.append({'id': i, 'asks_them': '?' in w and not p, 'promise': p, 'what': w[:60], 'due': None, 'delivered': False, 'delivers': []})
            return json.dumps({'verdicts': vs})
        if 'intent' in system.lower() or 'JSON' in system: return json.dumps({'intent': 'fyi', 'why': 'scripted: files everything'})
        return json.dumps([])
    return llm


def store():
    from taskuary.store import MemoryStore
    s = MemoryStore()
    for k, v in (('owner_email', OWNER), ('calendar_enabled', '0'), ('triage_ai', 'scripted')): s.set_setting(k, v, 'eval')
    return s


def run(s, extra=None):
    """One Advisor check. Returns the lines it raised."""
    from taskuary import assistant, funnel
    b = brain(extra)
    with mock.patch('taskuary.llm.build_llm', return_value=b):
        out = assistant.run(s, llm=b, force=True)
    funnel.invalidate()
    return out.get('lines') or []


def put_all_down(s, lines):
    from taskuary import assistant
    for l in lines: assistant.act(s, l['id'], 'dismiss')


def rail_rows(s) -> list:
    from taskuary import funnel
    funnel.invalidate()
    return funnel.pile(s, quiet=True).get('items') or []


# ── the seeded situations ────────────────────────────────────────────────────────────────────────────────────────────────────────
def _thread(s, cid, who, subj, theirs_d, mine_d=None, cls='person', asks=True, promise=None, delivered=False, reply_d=None):
    """Their mail, then (optionally) the owner's reply that asks or promises, then (optionally) their answer."""
    name, em = who
    s.add_message({'ConversationId': cid, 'Channel': 'email', 'Subject': subj, 'FromName': name, 'FromEmail': em, 'SentAt': at(d=theirs_d),
                   'BodyText': f'About {subj}.', 'Status': 'filed', 'SenderClass': cls})
    if mine_d is not None:
        mid = s.add_message({'ConversationId': cid, 'Channel': 'email', 'Subject': f'Re: {subj}', 'FromName': 'Alex Doyle', 'FromEmail': OWNER,
                             'SentAt': at(d=mine_d, m=1), 'BodyText': promise or 'Could you send the signed copy?', 'Status': 'context', 'Direction': 'out'})
        s.put_sent_verdict(mid, cid, asks and not promise, bool(promise), (promise or '')[:60], None, 'eval', mid if delivered else None)
    if reply_d is not None:
        s.add_message({'ConversationId': cid, 'Channel': 'email', 'Subject': f'Re: {subj}', 'FromName': name, 'FromEmail': em, 'SentAt': at(h=reply_d),
                       'BodyText': 'Here it is - signed.', 'Status': 'filed', 'SenderClass': cls})


TOM, NOREPLY, ERIN = ('Tom Alvarez', 'talvarez@vendor.example'), ('Vendor Portal', 'noreply@vendor.example'), ('Erin Blake', 'erin@northwind.example')


def _task(s, title, quiet_d, status='open', **kw):
    t = s.create_task({'Title': title, 'Status': status, 'Kind': 'task', **kw}, 'owner')
    s._exec('UPDATE task SET CreatedAt=?, UpdatedAt=? WHERE TaskId=?', (at(d=quiet_d), at(d=quiet_d), t))
    return t


def _report(s, title, fails=0, ok=0, workflow=False, active=True, error='connection refused on port 5432', clock=True):
    cfg = {'type': 'sql', 'title': title, **({'daily_at': '07:00'} if clock else {})}
    if workflow: cfg |= {'type': 'agent', 'access': 'write', 'prompt': 'pull the vendor statements into the ledger'}      # a job that writes
    sid = s.save_source({'Channel': 'report', 'Address': title, 'Active': 1 if active else 0, 'ConfigJson': json.dumps(cfg)}, 'owner')
    for i in range(ok): s.add_report_run(sid, {'at': at(d=10 - i), 'title': title, 'failed': False, 'said': 1})
    for i in range(fails): s.add_report_run(sid, {'at': at(h=fails - i), 'title': title, 'failed': True, 'error': f'{error} (run {i + 1})'})
    return sid


def _ignored(s, em, n, cls='automated', start=0):
    for i in range(start, start + n):
        mid = s.add_message({'ConversationId': f'email:{em}:{i}', 'Channel': 'email', 'Subject': f'Weekly digest {i}', 'FromEmail': em,
                             'FromName': em.split('@')[0], 'SentAt': at(d=1 + i % 30), 'BodyText': 'This week...', 'Status': 'ignored', 'SenderClass': cls})
        s.add_route(mid, None, 'ignore', None, 'not ours - their digest', [], 'owner')


def _connect_threads(s, n, subj='QuickBooks sync: invoice {i} failed to post', dom='intuit.example'):
    for i in range(n):
        s.add_message({'ConversationId': f'email:qb:{i}', 'Channel': 'email', 'Subject': subj.format(i=i), 'FromEmail': f'billing@{dom}',
                       'FromName': 'Billing', 'SentAt': at(d=2 + i), 'BodyText': 'sync failed', 'Status': 'filed', 'SenderClass': 'automated'})


def connect_says(pattern, card='quickbooks'):
    def extra(user):
        ts = [f'T{i}' for i, subj in re.findall(r'^\[T(\d+)\] \S+ \| (.*)$', user, re.M) if re.search(pattern, subj, re.I)]
        return [{'key': f'connect:{card}', 'text': 'x', 'why': 'the threads', 'threads': ts, 'named_in': []}] if ts else []
    return extra


def idea_says(text, mid_of=None):
    """The model's own line - under a NEW slug each check, as a model rewording itself does."""
    n = [0]
    def extra(user):
        n[0] += 1
        return [{'key': f'idea:scripted-{n[0]}', 'text': text, 'why': 'scripted', 'section': 'ideas', 'mid': mid_of() if mid_of else None}]
    return extra


def soul_says(card='quickbooks'):
    def extra(user): return [{'key': f'connect:{card}', 'text': 'x', 'why': 'SOUL.md names it', 'threads': [], 'named_in': ['SOUL']}]
    return extra


# Each case: (kind, name, should it fire, build(s) -> extra-lines fn or None, [second run: (between(s, lines), should it fire again)])
def _followup_plus(s): _thread(s, 'email:w9', TOM, 'Vendor W-9', theirs_d=5, mine_d=3)
def _followup_answered(s): _thread(s, 'email:w9', TOM, 'Vendor W-9', theirs_d=5, mine_d=3, reply_d=2)
def _followup_noreply(s): _thread(s, 'email:portal', NOREPLY, 'Your portal password expires', theirs_d=5, mine_d=3, cls='automated')
def _followup_early(s):
    _thread(s, 'email:w9', TOM, 'Vendor W-9', theirs_d=1)
    mid = s.add_message({'ConversationId': 'email:w9', 'Channel': 'email', 'Subject': 'Re: Vendor W-9', 'FromEmail': OWNER, 'SentAt': at(h=3),
                         'BodyText': 'Could you send the signed copy?', 'Status': 'context', 'Direction': 'out'})
    s.put_sent_verdict(mid, 'email:w9', True, False, '', None, 'eval')
def _promise_plus(s): _thread(s, 'email:budget', ERIN, 'Q4 budget', theirs_d=6, mine_d=4, promise="I'll send you the Q4 budget by Friday.")
def _promise_delivered(s): _thread(s, 'email:budget', ERIN, 'Q4 budget', theirs_d=6, mine_d=4, promise="I'll send you the Q4 budget by Friday.", delivered=True)
def _promise_tasked(s):
    _promise_plus(s); m = s._one("SELECT MessageId FROM message WHERE Direction='out'")
    s.task_for_promise(m['MessageId'], 'send the Q4 budget', None)
def _cold_plus(s): _task(s, 'Renew the PhishGuard licence', quiet_d=6)
def _cold_fresh(s): _task(s, 'Renew the PhishGuard licence', quiet_d=1)
def _cold_running(s):
    t = _task(s, 'Migrate the census export', quiet_d=6)
    s._exec("INSERT INTO run (TaskId, AgentName, Status, StartedAt, UpdatedAt) VALUES (?,?,?,?,?)", (t, 'coding', 'running', at(d=6), at(d=6)))
def _cold_agent_failed(s):
    t = _task(s, 'Fix the export', quiet_d=6, Kind='coding')
    s._exec("INSERT INTO run (TaskId, AgentName, Status, StartedAt, UpdatedAt, FinishedAt) VALUES (?,?,?,?,?,?)", (t, 'coding', 'failed', at(d=6), at(d=6), at(d=6)))
def _cold_five(s):
    for i, title in enumerate(('Renew the PhishGuard licence', 'Close the August books', 'Trainly seats', 'Move payroll to Payworth', 'Lease renewal')):
        _task(s, title, quiet_d=6 + i)
def _cold_put_away(s):
    t = _task(s, 'Renew the PhishGuard licence', quiet_d=6)
    s._exec('UPDATE task SET RemindAt=? WHERE TaskId=?', ((datetime.now() + timedelta(days=5)).strftime('%Y-%m-%d 08:00:00'), t))
def _cold_waiting_on_them(s):
    _task(s, 'Vendor W-9 for the new supplier', quiet_d=6, status='waiting', Assignee='person:talvarez@vendor.example')
def _health_plus(s): _report(s, 'Nightly AP aging', fails=3)
def _health_two(s): _report(s, 'Nightly AP aging', fails=2, ok=3)
def _health_off(s): _report(s, 'Nightly AP aging', fails=3, active=False)
def _health_workflow(s): _report(s, 'Monthly vendor statement pull', workflow=True)
def _health_unscheduled(s):
    """A workflow with no clock, known for two days, never run - said once (the owner, 2026-10-20)."""
    sid = _report(s, 'Vendor statement pull', workflow=True, clock=False)
    s.set_setting('health_workflow_seen', json.dumps({str(sid): at(d=2)}), 'eval')
def _nothing(s, lines): pass
def _health_workflow_old(s):
    """A workflow the Advisor has known for two days whose daily clock has passed twice, and that never ran."""
    sid = _report(s, 'Monthly vendor statement pull', workflow=True)
    s.set_setting('health_workflow_seen', json.dumps({str(sid): at(d=2)}), 'eval')
def _health_brain(s):
    s.set_setting('triage_ai', '', 'eval')
    s.add_message({'ConversationId': 'email:x', 'Channel': 'email', 'Subject': 'Gate code', 'FromEmail': 'gail@northwind.example', 'SentAt': at(h=2),
                   'BodyText': 'what is the gate code?', 'Status': 'triaging'})
def _connect_plus(s): _connect_threads(s, 4)
def _connect_two(s): _connect_threads(s, 2)
def _connected(s):
    _connect_threads(s, 4); s._exec("INSERT INTO connector (Type, Name, Active) VALUES ('quickbooks', 'QuickBooks', 1)")
def _idea_plus(s): s.add_message({'ConversationId': 'email:lease', 'Channel': 'email', 'Subject': 'Lease renewal', 'FromEmail': 'gail@northwind.example',
                                  'FromName': 'Gail Moreno', 'SentAt': at(h=5), 'BodyText': 'The lease renewal is due the 30th.', 'Status': 'filed'})
def _idea_closed(s):
    t = s.create_task({'Title': 'Fix the vendor loop', 'Status': 'done'}, 'owner')
    s._exec("UPDATE task SET ClosedAt=? WHERE TaskId=?", (at(d=1), t))
    s.add_message({'ConversationId': 'email:loop', 'Channel': 'email', 'Subject': 'Vendor loop', 'FromEmail': 'gail@northwind.example', 'SentAt': at(d=2),
                   'BodyText': 'The vendor loop is back.', 'Status': 'routed', 'TaskId': t})
def _rule_plus(s): _ignored(s, 'newsletter@vendor.example', 12)
def _rule_colleague(s): _ignored(s, 'erin@northwind.example', 12, cls='person')
def _rule_replied(s):
    _ignored(s, 'newsletter@vendor.example', 12)
    s.add_message({'ConversationId': 'email:newsletter@vendor.example:2', 'Channel': 'email', 'Subject': 'Re: Weekly digest 2', 'FromEmail': OWNER,
                   'SentAt': at(d=1), 'BodyText': 'please unsubscribe me', 'Status': 'context', 'Direction': 'out'})
def _rule_under(s): _ignored(s, 'newsletter@vendor.example', 7)
def _rule_pressed(s):
    """Only the press log: Not ours pressed on each of their mails while the Advisor's line was shown."""
    for i in range(9):
        s.add_message({'ConversationId': f'email:promo:{i}', 'Channel': 'email', 'Subject': f'Offer {i}', 'FromEmail': 'promo@vendor.example',
                       'SentAt': at(d=1 + i), 'BodyText': 'x', 'Status': 'filed', 'SenderClass': 'bulk'})
        s._exec('INSERT INTO advice_press (Key, Pressed, Sender, SenderDomain, Thread, CreatedAt) VALUES (?,?,?,?,?,?)',
                (f'msg:{i}', 'not_ours', 'promo@vendor.example', 'vendor.example', f'email:promo:{i}', at(d=i)))
def _rule_notes(s):
    """Only LEARNED.md's evidence: the verdict notes Not a task writes, one per mail."""
    for i in range(8):
        s.add_message({'ConversationId': f'email:dig:{i}', 'Channel': 'email', 'Subject': f'Digest {i}', 'FromEmail': 'digest@vendor.example',
                       'SentAt': at(d=1 + i), 'BodyText': 'x', 'Status': 'filed', 'SenderClass': 'automated'})
        s.add_memory({'Scope': 'subject', 'ScopeKey': f'digest {i}', 'Source': 'verdict', 'Active': 1, 'CreatedBy': 'owner',
                      'Note': f'{at(d=i)[:10]}: "Digest {i}" from digest@vendor.example - NOT A TASK: the owner filed it, no task, no reply'})
def _rule_urgent(s):
    for i in range(5):
        t = s.create_task({'Title': f'Disk alert {i}', 'Status': 'open'}, 'triage')
        s.add_message({'ConversationId': f'email:alert:{i}', 'Channel': 'email', 'Subject': f'Disk alert {i}', 'FromEmail': 'alerts@vendor.example',
                       'SentAt': at(d=1 + i), 'BodyText': 'disk at 95%', 'Status': 'routed', 'TaskId': t, 'SenderClass': 'automated'})
        s.audit('task', t, 'priority', 'owner', detail={'from': 'normal', 'to': 'urgent'})
def _cold_draft_waits(s):
    t = _task(s, 'Vendor master clean-up', quiet_d=6, status='waiting')
    s._exec("INSERT INTO review (TaskId, Kind, DraftText, Status, CreatedAt) VALUES (?,?,?,?,?)", (t, 'draft', 'Here is the list.', 'pending', at(d=6)))
def _connect_soul(s): s.save_doc('soul', 'I run finance at Northwind. Our books are in QuickBooks Online.', 'owner')
def _new_error(s, lines):
    """Put down, then the report fails a new way: a new fact, worth saying."""
    from taskuary import assistant
    for l in lines: assistant.act(s, l['id'], 'dismiss')
    sid = s._one("SELECT SourceId FROM source WHERE Address='Nightly AP aging'")['SourceId']
    for i in range(3): s.add_report_run(sid, {'at': at(m=3 - i), 'title': 'x', 'failed': True, 'error': 'permission denied for table ap_aging'})
def _rule_urgent_answered(s):
    _rule_urgent(s)
    s.add_message({'ConversationId': 'email:alert:0', 'Channel': 'email', 'Subject': 'Re: Disk alert 0', 'FromEmail': OWNER, 'SentAt': at(h=2),
                   'BodyText': 'on it', 'Status': 'context', 'Direction': 'out'})
def _rule_covered(s):
    _ignored(s, 'newsletter@vendor.example', 12)
    s.save_policy({'Name': 'x', 'Kind': 'sender', 'Pattern': 'newsletter@vendor.example', 'Action': 'skip', 'Reason': 'x', 'Active': 1}, 'owner')


CASES = [
    # followup: the owner's last word asked them for something, and the silence is a day old or more
    ('followup', 'asked a vendor 3 days ago, no answer', True, _followup_plus, None),
    ('followup', 'they answered', False, _followup_answered, None),
    ('followup', 'the last word was to an automated address', False, _followup_noreply, None),
    ('followup', 'asked three hours ago', False, _followup_early, None),
    ('followup', 'put down, the silence has not grown a step', False, _followup_plus, 'dismiss'),
    # promise: the owner committed to something nothing later of theirs delivered
    ('promise', 'promised a budget by Friday, not sent', True, _promise_plus, None),
    ('promise', 'the budget went', False, _promise_delivered, None),
    ('promise', 'already a task on the owner', False, _promise_tasked, None),
    # cold: open work nothing has touched for the window
    ('cold', 'open task untouched for six days', True, _cold_plus, None),
    ('cold', 'touched yesterday', False, _cold_fresh, None),
    ('cold', 'an agent has been on it for six days', False, _cold_running, None),
    ('cold', 'its agent failed six days ago - the agent row says it', False, _cold_agent_failed, None),
    ('cold', 'put away until next week (Remind me)', False, _cold_put_away, None),
    ('cold', 'waiting on someone else six days - the slipped lane chases', False, _cold_waiting_on_them, None),
    ('cold', 'put down, nothing moved since', False, _cold_plus, 'dismiss'),
    ('cold', 'five tasks quiet - three said today', True, _cold_five, None),
    ('cold', 'five tasks quiet - the next check the same day says none', False, _cold_five, 'dismiss'),
    ('cold', 'a draft has waited on you for six days', True, _cold_draft_waits, None),
    # health: the app's own failures
    ('health', 'a report failed its last three runs', True, _health_plus, None),
    ('health', 'two failures after good runs', False, _health_two, None),
    ('health', 'the report is switched off', False, _health_off, None),
    ('health', 'the same failure again after a No', False, _health_plus, 'dismiss'),
    ('health', 'a new failure after a No', True, _health_plus, _new_error),
    ('health', 'a workflow saved a minute ago, never run yet', False, _health_workflow, None),
    ('health', 'a workflow known for two days that never ran', True, _health_workflow_old, None),
    ('health', 'an unscheduled workflow that never ran', True, _health_unscheduled, None),
    ('health', 'the unscheduled workflow again, next check', False, _health_unscheduled, _nothing),
    ('health', 'mail waits and no brain is set', True, _health_brain, None),
    # connect: a system the threads are really about, nothing connected
    ('connect', 'four threads about QuickBooks', True, _connect_plus, None),
    ('connect', 'two threads - under the floor', False, _connect_two, None),
    ('connect', 'already connected', False, _connected, None),
    ('connect', 'raised before and put down', False, _connect_plus, 'dismiss'),
    ('connect', "the owner's SOUL.md names it, no threads", True, _connect_soul, None),
    # idea: the model's own line
    ('idea', "the model's own line about a mail", True, _idea_plus, None),
    ('idea', 'about a task closed yesterday', False, _idea_closed, None),
    ('idea', 'the same thought again after a No', False, _idea_plus, 'dismiss'),
    # rule: a learned pattern clear-cut enough to be a rule (promote.py)
    ('rule', 'twelve mails put down, none taken up', True, _rule_plus, None),
    ('rule', 'Not ours pressed on nine mails (the press log only)', True, _rule_pressed, None),
    ('rule', "eight Not a task notes (LEARNED.md's evidence only)", True, _rule_notes, None),
    ('rule', 'every task from them marked urgent by hand', True, _rule_urgent, None),
    ('rule', 'marked urgent every time, and the owner answers them', True, _rule_urgent_answered, None),
    ('rule', 'a colleague', False, _rule_colleague, None),
    ('rule', 'the owner wrote to them once', False, _rule_replied, None),
    ('rule', 'seven put down - under the bar', False, _rule_under, None),
    ('rule', 'a rule already covers them', False, _rule_covered, None),
    ('rule', 'put down - the evidence has not grown', False, _rule_plus, 'dismiss'),
]
EXTRA = {"the model's own line about a mail": lambda s: idea_says('Gail says the lease renewal is due the 30th - nothing on your list covers it.',
                                                                   lambda: (s._one("SELECT MessageId FROM message WHERE Subject='Lease renewal'") or {}).get('MessageId')),
         'the same thought again after a No': lambda s: idea_says('Gail says the lease renewal is due the 30th - nothing on your list covers it.',
                                                                   lambda: (s._one("SELECT MessageId FROM message WHERE Subject='Lease renewal'") or {}).get('MessageId')),
         'about a task closed yesterday': lambda s: idea_says('The vendor loop Gail flagged is back.',
                                                               lambda: (s._one("SELECT MessageId FROM message WHERE Subject='Vendor loop'") or {}).get('MessageId')),
         'four threads about QuickBooks': lambda s: connect_says('QuickBooks'),
         'two threads - under the floor': lambda s: connect_says('QuickBooks'),
         'already connected': lambda s: connect_says('QuickBooks'),
         'raised before and put down': lambda s: connect_says('QuickBooks'),
         "the owner's SOUL.md names it, no threads": lambda s: soul_says()}


def noise_of(s, kind, line, rail) -> str:
    """Why a raised line is not useful, or '' - the generic checks every line gets, whatever its case."""
    a = line.get('action') or {}
    txt = str(line.get('text') or '')
    mid = a.get('mid')
    m = s.get_message(mid) if mid else None
    if m and str(m.get('SenderClass') or '').lower() in ('automated', 'bulk') and kind in ('followup', 'promise'):
        return f"about automated mail ({m.get('FromEmail')})"
    t = s.get_task(a.get('tid')) if a.get('tid') else None
    if t and t.get('Status') in ('done', 'dropped'): return f"stale - {t.get('Title')} is {t['Status']}"
    if kind == 'cold' and t and not s._one("SELECT 1 FROM review WHERE TaskId=? AND Status='pending'", (t['TaskId'],)):
        # the hub's own words for the line (the brain echoes the facts): "a reply waiting on you" with no draft waiting is wrong
        from taskuary import assistant
        own = next((c for c in assistant.cold(s, 0) if c['key'] == line.get('key')), {})
        if re.search(r'waiting on you|waits for you', f"{own.get('text')} {own.get('facts')}"):
            return f"wrong person - says a reply waits on you, the task waits on {t.get('Assignee') or 'someone else'}"
    if kind == 'cold' and t and str(t.get('RemindAt') or '') > datetime.now().strftime('%Y-%m-%d %H:%M:%S'):
        return f"too early - put away until {str(t['RemindAt'])[:10]}"
    if kind == 'cold' and t:
        from taskuary import workerstate
        w = workerstate.status(s, t['TaskId'])
        if w.get('live'): return 'an agent is on it - its own row on the rail is the line, not "gone quiet"'
        if w.get('state') in ('finished', 'failed', 'stopped', 'disconnected'): return f"its agent {w['state']} - the agent's own row says it"
        if (s.list_runs(t['TaskId']) or [{}])[-1].get('Status') in ('finished', 'failed', 'stopped', 'done'): return "its agent's run ended - the agent's own row says it"
    # the same thing twice on the rail: the idea's own row beside the row of the task or mail it is about
    me = next((r for r in rail if r.get('idea') == line.get('id')), None)
    if me and (twin := next((r for r in rail if r is not me and ((a.get('tid') and r.get('tid') == a['tid']) or (mid and r.get('mid') == mid))), None)):
        return f"duplicates a row already on the rail ({twin.get('key')})"
    if kind == 'idea' and re.search(r'skip rule', txt, re.I):
        who = re.search(r'(\S+@\S+)', txt)
        if who and any(i.get('Kind') == 'rule' and who.group(1).lower() in str(i.get('Key') or '') for i in s.list_ideas()):
            return f'duplicates the rule question already raised for {who.group(1)}'
    return ''


def evaluate(case) -> dict:
    kind, name, should, build, between = case
    s = store(); build(s)
    extra = EXTRA.get(name, lambda s: None)(s)
    lines = run(s, extra)
    if between:
        (put_all_down if between == 'dismiss' else between)(s, lines)
        lines = run(s, extra)
    mine = [l for l in lines if l['kind'] == kind]
    rail = rail_rows(s)
    noise = [r for r in (noise_of(s, l['kind'], l, rail) for l in lines) if r]
    today = datetime.now().strftime('%Y-%m-%d')
    if (n := sum(1 for i in s.list_ideas() if i.get('Kind') == 'cold' and str(i.get('LastSaid') or '')[:10] == today)) > 3:
        noise.append(f'{n} "gone quiet" lines today - more than three a day')
    # a line of another kind is not this case's subject, but a line that should not be anywhere is noise wherever it lands
    if mine and not should: out, why = 'noise', f"fired: {mine[0]['text'][:110]}"
    elif mine and noise: out, why = 'noise', noise[0]
    elif mine: out, why = 'hit', mine[0]['text'][:110]
    elif should: out, why = 'miss', 'nothing raised' + (f" (raised instead: {[l['kind'] for l in lines]})" if lines else '')
    elif noise: out, why = 'noise', noise[0]
    else: out, why = 'quiet', ''
    return {'kind': kind, 'case': name, 'should': should, 'out': out, 'why': why, 'lines': [(l['kind'], l['text'][:90]) for l in lines]}


AGED = {'message': ('SentAt', 'CreatedAt'), 'task': ('CreatedAt', 'UpdatedAt', 'ClosedAt', 'DueAt'), 'comment': ('CreatedAt',),
        'run': ('StartedAt', 'UpdatedAt', 'FinishedAt'), 'review': ('CreatedAt', 'DecidedAt'), 'route': ('CreatedAt',),
        'idea': ('FirstSeen', 'LastSaid'), 'report_run': ('At',)}


def age(s, days: int):
    """The whole world `days` older - the demo is stamped "now", and what goes quiet only shows once time has passed."""
    for t, cols in AGED.items():
        for c in cols:
            try: s._exec(f"UPDATE {t} SET {c}=datetime({c}, '-{int(days)} days') WHERE {c} IS NOT NULL AND {c}<>''")
            except Exception: pass


def world() -> list:
    """The demo + faults world, five days on, checked twice with every line put down between: what the second check raises
    again is noise (a repeat after a No), and every line is held to the generic checks."""
    from taskuary import demo, faults
    s = store(); demo.seed(s)
    with mock.patch.dict(os.environ, {faults.ENV: '1'}):
        assert faults.active(), 'the eval needs a scratch home'
        faults.world(s)
    age(s, 5)
    out = []
    first = run(s)
    rail = rail_rows(s)
    for l in first:
        why = noise_of(s, l['kind'], l, rail)
        out.append({'kind': l['kind'], 'case': f"world: {l['key']}", 'should': None, 'out': 'noise' if why else 'said', 'why': why or l['text'][:110]})
    put_all_down(s, first)
    was = {l['key'] for l in first}
    for l in run(s):
        if l['key'] in was:
            out.append({'kind': l['kind'], 'case': f"world, after a No: {l['key']}", 'should': False, 'out': 'noise', 'why': 'raised again after it was put down'})
        else:
            why = noise_of(s, l['kind'], l, rail_rows(s))
            out.append({'kind': l['kind'], 'case': f"world, next check: {l['key']}", 'should': None, 'out': 'noise' if why else 'said', 'why': why or l['text'][:110]})
    today = datetime.now().strftime('%Y-%m-%d')
    if (n := sum(1 for i in s.list_ideas() if i.get('Kind') == 'cold' and str(i.get('LastSaid') or '')[:10] == today)) > 3:
        out.append({'kind': 'cold', 'case': 'world: gone quiet, the day', 'should': False, 'out': 'noise', 'why': f'{n} "gone quiet" lines in one day'})
    return out


def run_all() -> list:
    return [evaluate(c) for c in CASES] + world()


def table(res) -> str:
    from collections import defaultdict
    t = defaultdict(lambda: defaultdict(int))
    for r in res: t[r['kind']][r['out']] += 1
    rows = [f"{'kind':10} {'hit':>4} {'miss':>5} {'quiet':>6} {'noise':>6} {'said (world)':>13}"]
    rows += [f"{k:10} {v['hit']:4} {v['miss']:5} {v['quiet']:6} {v['noise']:6} {v['said']:13}" for k, v in sorted(t.items())]
    return '\n'.join(rows)


if __name__ == '__main__':
    os.environ.setdefault('TASKUARY_HOME', tempfile.mkdtemp(prefix='tq-railadv-'))
    res = run_all()
    for r in res: print(f"{r['out']:6} {r['kind']:9} {r['case'][:52]:52} {r['why'][:100]}")
    print(table(res))
