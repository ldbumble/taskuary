"""Triage got the SHAPE of the work wrong: one task holding two jobs, or two tasks holding
one. Both are the same class of mistake - the AI read the mail and drew the boundary in the
wrong place - and neither was fixable without deleting work and retyping it.

    split  - one task becomes two. The first half KEEPS the task: its ref, its session, its
             report, its history. The second half is a new task, and the messages you tick
             move with it.
    merge  - two tasks become one. The messages move, the ask is appended, and the folded
             task is dropped (never deleted) with a pointer at the survivor, so the trail of
             what triage did - and what you did about it - stays readable.

`ingest.split_message` is a different, narrower move: pull one MESSAGE out of a thread that
was routed onto the wrong task. This module splits by the ASK, inside a single message.
"""
import json, re
from .timewords import plural
from .routing import WEIGHTS, score_candidate
from .store import task_ref

SPLIT_SYSTEM = (
    'One work task, and the mail it came from. Decide whether it is really TWO independent jobs '
    'that were filed as one, and if so name them. Answer JSON only:\n'
    '{"two": true|false, "why": "<10 words max>", '
    '"first": {"title": "...", "summary": "..."}, "second": {"title": "...", "summary": "..."}}\n'
    'two = the task carries two jobs that could be finished, handed over or dropped separately - '
    'usually two asks that happened to arrive in the same message. Steps of one job are NOT two jobs; '
    'neither is one job with a deadline, a caveat or a question attached.\n'
    'Torn? Answer false. Splitting doubles the tracking for the owner, and they can still split by hand.\n'
    '"first" KEEPS this task - its ref, its agent session, its report - so put the job already under way, '
    'or the larger one, first. "second" becomes a brand-new task.\n'
    'Each title is one imperative line under 90 characters, in the sender\'s own words where you can. '
    'Each summary quotes the part of the ask that belongs to that half - do not invent detail.')

MAX_SUMMARY = 4000


def no_split(store, tid: int, why: str) -> dict:
    """No AI connector, or the AI fell over: the task as it stands and an EMPTY second job for the
    owner to name. Never claims a split and never guesses one - a word list used to pick "the
    ask-shaped lines" (please, also, fix, send...) and offered a greeting's neighbour as the second
    job (the owner, 2026-10-11: "everything should be ai"). The message list below it is the help."""
    t = store.get_task(tid) or {}
    return {'two': False, 'why': why, 'first': {'title': (t.get('Title') or '')[:200], 'summary': str(t.get('Summary') or '')[:MAX_SUMMARY]},
            'second': {'title': '', 'summary': ''}}


def propose_split(store, tid: int, llm=None) -> dict:
    """What are the two jobs in here? Nothing is created - this is the drawer's starting text,
    and the owner edits it before anything happens."""
    t = store.get_task(tid)
    if not t: raise ValueError(f'no task {tid}')
    msgs = store.list_messages(tid)
    out = {'ai': False, 'messages': [{'message_id': m['MessageId'], 'subject': m.get('Subject'),
                                      'from': m.get('FromName') or m.get('FromEmail'), 'sent_at': m.get('SentAt'),
                                      'preview': str(m.get('BodyText') or '')[:200]} for m in msgs],
           **no_split(store, tid, 'no AI brain is connected - name the second job yourself; the mail is listed below')}
    if not llm: return out
    try:
        user = json.dumps({'title': t.get('Title'), 'summary': str(t.get('Summary') or '')[:2000], 'kind': t.get('Kind'),
                           'messages': [{'from': m.get('FromEmail'), 'subject': m.get('Subject'),
                                         'body': str(m.get('BodyText') or '')[:2500]} for m in msgs[:6]]})
        j = json.loads(re.sub(r'^```(json)?|```$', '', llm(SPLIT_SYSTEM, user, 700).strip(), flags=re.M))
        half = lambda k, d: {'title': str((j.get(k) or {}).get('title') or d)[:200],
                             'summary': str((j.get(k) or {}).get('summary') or '')[:MAX_SUMMARY]}
        return {**out, 'ai': True, 'two': bool(j.get('two')), 'why': str(j.get('why') or '')[:200],
                'first': half('first', t.get('Title') or ''), 'second': half('second', '')}
    except Exception as e:
        return {**out, 'why': f'the AI could not read it ({str(e)[:60]}) - name the second job yourself'}


def split_task(store, tid: int, second: dict, first: dict = None, move_message_ids=None, actor: str = 'owner') -> int:
    """Break one task in two. `first` retitles the task in place (optional); `second` becomes a
    new one. Only messages you name move - the rest stay with the history they belong to."""
    t = store.get_task(tid)
    if not t: raise ValueError(f'no task {tid}')
    title = str((second or {}).get('title') or '').strip()
    if not title: raise ValueError('the second job needs a title')
    if first and str(first.get('title') or '').strip():
        keep = {'Title': str(first['title']).strip()[:200]}
        if first.get('summary'): keep['Summary'] = str(first['summary'])[:MAX_SUMMARY]
        store.update_task(tid, keep, actor)
    # An agent is dispatched at a task, so a new task must not inherit one - but work the owner
    # kept for themselves splits into more work for themselves.
    own = t.get('Assignee') if not str(t.get('Assignee') or '').startswith('agent:') else None
    new = store.create_task({'Title': title[:200], 'Summary': str((second or {}).get('summary') or '')[:MAX_SUMMARY],
                             'Kind': t.get('Kind') or 'general', 'Priority': t.get('Priority') or 'normal',
                             'Source': t.get('Source') or 'manual', 'SourceRef': t.get('SourceRef'),
                             'Tags': t.get('Tags'), **({'Assignee': own} if own else {})}, actor)
    mine = {m['MessageId'] for m in store.list_messages(tid)}
    moved = [int(m) for m in (move_message_ids or []) if int(m) in mine]
    for mid in moved:
        store.attach_message(mid, new)
        store.add_route(mid, new, 'split', None, f'{task_ref(tid)} was two jobs - this one is {task_ref(new)}', [], actor)
    store.add_comment(tid, actor, 'human',
                      f'Broke this in two: "{title[:120]}" is now {task_ref(new)}'
                      + (f' ({plural(len(moved), "message")} moved with it).' if moved else '.'))
    store.add_comment(new, actor, 'human', f'Broken out of {task_ref(tid)} - triage filed two jobs as one.')
    store.audit('task', new, 'split_from_task', actor, detail={'from_task': tid, 'messages': moved})
    store.audit('task', tid, 'split_into_task', actor, detail={'new_task': new, 'title': title[:120]})
    return new


def _why(sig: dict) -> str:
    if sig['thread']: return 'same email thread'
    bits = (['same subject'] if sig['subject'] else []) + (['same sender'] if sig['sender'] else []) \
        + (['alike in meaning'] if sig['meaning'] else [])
    return ' + '.join(bits) or 'nothing obvious in common'


OPEN = ('open', 'in_progress', 'waiting')
OPEN_EDGE, MAX_CLOSED, MAX_FOUND = 0.05, 200, 20

def _snapshot(store, t: dict) -> dict:
    """A task as the router sees a candidate: its thread, senders and subjects. What it is ABOUT is read off its title and
    summary by embeddings (context.alike), so a task typed in by hand - all of its ask in Summary - still meets its duplicate."""
    ms = store.list_messages(t['TaskId'])
    return {'task_id': t['TaskId'], 'title': t.get('Title'),
            'subjects': [m['Subject'] for m in ms if m['Subject']],
            'senders': [m['FromEmail'] for m in ms if m['FromEmail']],
            'conversation_ids': [m['ConversationId'] for m in ms if m['ConversationId']]}


def _match(t: dict, q: str) -> bool:
    """The owner's search: a number is the task's ("1182", "TQ-1182"), anything else is words in its title, all of them."""
    n = re.fullmatch(r'(?:tq-?)?\s*0*(\d+)', q.strip().lower())
    if n: return t['TaskId'] == int(n.group(1))
    return all(w in str(t.get('Title') or '').lower() for w in q.lower().split())


def merge_candidates(store, tid: int, limit: int = 8, q: str = '') -> list:
    """Which task is this one a duplicate of? The router's own signals, run backwards - the same scoring that decided
    to open a second task in the first place. A CLOSED one too (the owner, 2026-10-26: "we can't merge this with other
    tasks only open tasks?"): the real original is often last week's task on the same thread, already done. One ranking,
    open ahead on a near-tie: a closed task on the same thread outranks an unrelated open one, but between two alike the
    live one is the likelier home. Dropped ones never - they are folded away already. Unasked, only the latest closed
    are scored (each is a read of its mail); `q` reaches any task by number or title words."""
    t = store.get_task(tid)
    if not t: raise ValueError(f'no task {tid}')
    mine = _snapshot(store, t)
    me = {'subject': mine['title'], 'from_email': next(iter(mine['senders']), None),
          'conversation_id': next(iter(mine['conversation_ids']), None)}
    pool = [o for o in store.list_tasks() if o['TaskId'] != tid and (o.get('Status') in OPEN or o.get('Status') == 'done')]
    if q.strip(): pool = sorted((o for o in pool if _match(o, q)), key=lambda o: -o['TaskId'])[:MAX_FOUND]
    else:
        shut = sorted((o for o in pool if o.get('Status') == 'done'), key=lambda o: str(o.get('ClosedAt') or o.get('UpdatedAt') or ''))
        pool = [o for o in pool if o.get('Status') in OPEN] + shut[-MAX_CLOSED:]
    # how alike in MEANING, off embeddings (textsim) - {} with no embedder, and the thread, the sender and the subject rank alone
    from .context import alike
    near = alike(store, f"{t.get('Title') or ''}\n{t.get('Summary') or ''}", pool)
    out = []
    for other in pool:
        s = _snapshot(store, other)
        sig = score_candidate(me, s, near.get(other['TaskId'], 0.0))
        score, closed = round(min(1.0, sum(WEIGHTS[k] * v for k, v in sig.items())), 4), other.get('Status') == 'done'
        out.append({'task_id': s['task_id'], 'ref': task_ref(s['task_id']), 'title': s['title'], 'closed': closed,
                    'score': score, 'why': _why(sig), '_rank': score - (OPEN_EDGE if closed else 0)})
    out.sort(key=lambda c: -c['_rank'])
    return [{k: v for k, v in c.items() if k != '_rank'} for c in out[:MAX_FOUND if q.strip() else limit]]


def merge_tasks(store, src: int, dst: int, actor: str = 'owner') -> dict:
    """Fold `src` into `dst`: the messages move, the ask is appended, and src is DROPPED with a
    pointer at dst. Dropped rather than deleted - what triage did, and what you did about it,
    is the part you want to be able to read later."""
    if src == dst: raise ValueError('a task cannot be folded into itself')
    a, b = store.get_task(src), store.get_task(dst)
    if not a: raise ValueError(f'no task {src}')
    if not b: raise ValueError(f'no task {dst}')
    if b.get('Status') == 'dropped': raise ValueError(f'{task_ref(dst)} was dropped - fold into the task it went to')
    if any(r['Status'] == 'running' for r in store.list_runs(src)):
        raise ValueError(f'{task_ref(src)} has an agent working on it - stop that session first')
    # FOLDED INTO A CLOSED TASK, IT REOPENS (the owner, 2026-10-26): it now carries mail that is owed an answer - the same rule
    # as a line on a closed thread (ingest._reopen, "a closed task reopens on what triage says is owed"), and the same reopen
    # as the page's button (task.reopen: open, an old Remind me cleared). Said on it, so its history reads why it came back.
    reopened = b.get('Status') == 'done'
    if reopened:
        from . import selfclose
        store.update_task(dst, {'Status': 'open', 'RemindAt': ''}, actor); selfclose.forget(dst)
        store.add_comment(dst, actor, 'human', f'Reopened - {task_ref(src)} was folded in, and its mail is still owed an answer.')
        store.audit('task', dst, 'reopen', actor, detail={'why': f'{task_ref(src)} folded in'})
    msgs = store.list_messages(src)
    for m in msgs:
        store.attach_message(m['MessageId'], dst)
        store.add_route(m['MessageId'], dst, 'merge', None, f'folded {task_ref(src)} into {task_ref(dst)} - one job, two tasks', [], actor)
    ask = str(a.get('Summary') or '').strip()
    if ask and ask not in str(b.get('Summary') or ''):
        store.update_task(dst, {'Summary': f"{str(b.get('Summary') or '').strip()}\n\n--- folded in from "
                                           f"{task_ref(src)}: {a.get('Title')}\n{ask}"[:MAX_SUMMARY]}, actor)
    notes = [c for c in store.list_comments(src) if c['ActorType'] == 'human']
    store.add_comment(dst, actor, 'human',
                      f'Folded {task_ref(src)} in: "{str(a.get("Title") or "")[:120]}" - the same job, filed twice. '
                      f'{plural(len(msgs), "message")} moved over'
                      + (f'; {plural(len(notes), "note")} stayed on {task_ref(src)}.' if notes else '.'))
    store.add_comment(src, actor, 'human', f'Folded into {task_ref(dst)} - same job as that one. Nothing to do here.')
    store.update_task(src, {'Status': 'dropped'}, actor)
    store.audit('task', src, 'merged_into_task', actor, detail={'into': dst, 'messages': [m['MessageId'] for m in msgs]})
    store.audit('task', dst, 'merged_from_task', actor, detail={'from_task': src, 'messages': len(msgs)})
    return {'task_id': dst, 'ref': task_ref(dst), 'dropped': src, 'moved': len(msgs), 'reopened': reopened}
