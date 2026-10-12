"""Bulk processing, one task per batch.

A ranked tracker input (a GitHub repository, a Jira project) used to let its top four arrivals in as four tasks: nothing
ever read two of them side by side, so two pull requests fixing the same field came in as two jobs, and the circled
place a row wore vanished the moment it was opened (the owner, 2026-10-12: "they should all come in as one task and the
agent will process them one by one picking the most valuable one first").

Now the top N of ONE repository come in as one task. Its items are rows of batch_item, in the order ranking put them; an
agent works them top-down and says what it found per item. The rules the owner set:
  - a batch is one input (SourceName - the repository, the board). Which input an arrival came from is a fact on it,
    never a judgement; the AI ranks only WITHIN an input.
  - arrivals while a batch is open wait for the next one. A batch is a fixed set you can finish.
  - an item ending upstream (merged, closed) settles ITS line. The task closes when no line is left open.
  - a comment on an item re-opens that line, not a new task.
  - mail is not batched: four senders are not one job.
"""
from loguru import logger

from .store import task_ref

# Inputs whose arrivals are items of somebody's backlog. Mail and chat are conversations with people, and are not batched.
CHANNELS = frozenset({'github', 'gitlab', 'azdo', 'linear', 'trello', 'jira', 'sentry', 'pagerduty'})
OPEN, SETTLED = ('waiting', 'working', 'needs_you'), ('done', 'ended')
PREFIX = 'batch:'


def batches(channel) -> bool: return str(channel or '') in CHANNELS
def source_ref(channel, source) -> str: return f'{PREFIX}{channel}:{source}'
def is_batch(store, tid) -> bool: return str((store.get_task(tid) or {}).get('SourceRef') or '').startswith(PREFIX)


def _noun(rows) -> str:
    heads = [str(r.get('BodyText') or '')[:40].lower() for r in rows]
    if rows and all('[pull request by' in h for h in heads): return 'pull request'
    if rows and all('[issue by' in h for h in heads): return 'issue'
    return 'item'


def _title(r, source) -> str:
    s = str(r.get('Subject') or '(no subject)')
    return (s[len(source):].strip() if source and s.startswith(source) else s)[:200]


def title_for(n: int, noun: str, source: str) -> str: return f"{n} {noun}{'' if n == 1 else 's'} on {source}"


def create(store, channel: str, source: str, rows: list, actor: str = 'router') -> int:
    """Let these arrivals in as one task - `rows` in ranked order, best first. Nothing is triaged: what each item is,
    the agent reads; what it is worth, ranking already said."""
    noun = _noun(rows)
    tid = store.create_task({
        'Title': title_for(len(rows), noun, source), 'Kind': 'coding' if channel in ('github', 'gitlab') else 'general',
        'Status': 'open', 'Source': channel, 'SourceRef': source_ref(channel, source), 'Tags': 'batch',
        'Summary': f"The {len(rows)} most valuable {noun}s waiting on {source}, in ranked order. "
                   f"Each one is reviewed in turn; nothing is merged, closed or answered without you."}, actor)
    for n, r in enumerate(rows, 1):
        conv = r.get('ConversationId') or f"m{r['MessageId']}"
        store.place_message(r['MessageId'], tid, 'routed')
        store.add_route(r['MessageId'], tid, 'batch', r.get('RankValue'),
                        f"item {n} of {task_ref(tid)}'s batch" + (f" - {r['RankWhy']}" if r.get('RankWhy') else ''), [], 'rank')
        store.add_batch_item(tid, conv, r['MessageId'], n, _title(r, source), r.get('SourceLink'))
    logger.info(f'batch: {task_ref(tid)} let in {len(rows)} {noun}(s) from {source}')
    return tid


def items(store, tid) -> list: return store.batch_items(tid)


def admit(store, rows: list) -> list:
    """The ranked rows of batched inputs become batches; returns the rows left for ordinary triage.

    A row whose conversation already has a task is not an arrival but a follow-up (a comment on a pull request already
    let in): it goes on to triage, which joins it to its task - a batch's own included (arrived below)."""
    from . import rank
    rest, groups = [], {}
    for r in rows:
        ch = str(r.get('Channel') or '')
        if not batches(ch) or store.task_for_conversation(r.get('ConversationId')): rest.append(r); continue
        groups.setdefault((ch, str(r.get('SourceName') or '')), []).append(r)
    for (ch, source), rs in groups.items():
        if store.open_batch(source_ref(ch, source)): continue          # the next batch waits for this one to finish
        rs = sorted(rs, key=lambda r: (r.get('RankValue') is None, -(r.get('RankValue') or 0), r['MessageId']))
        try: create(store, ch, source, rs[:rank.head_size(store, ch)])
        except Exception as e: logger.warning(f'batch: {source} could not be let in ({e})')
    return rest


def set_item(store, tid, conv, actor: str = 'agent', **fields) -> bool:
    """One item's state, result or overlap - then close the batch if that was the last line open."""
    ok = store.update_batch_item(tid, conv, fields)
    if ok and fields.get('State') in SETTLED: close_if_settled(store, tid, actor)
    return ok


def close_if_settled(store, tid, actor: str = 'router') -> bool:
    its = store.batch_items(tid)
    if not its or any(i['State'] in OPEN for i in its): return False
    if (store.get_task(tid) or {}).get('Status') in ('done', 'dropped'): return False
    from . import coder, terminal as term
    store.add_comment(tid, 'router', 'agent', 'Every item of this batch is settled.')
    wrapped = False
    if getattr(term.session_for(tid), 'alive', False):
        try: coder.wrap(store, tid, close=True, actor=actor, no_reply=True); wrapped = True
        except Exception as e: logger.warning(f'{task_ref(tid)}: the batch ending failed ({e}) - closing it plainly')
    if not wrapped: store.update_task(tid, {'Status': 'done'}, actor)
    _next(store)
    return True


def _next(store):
    """The batch is over: let the next one in, off the caller's thread - a drain takes the triage lock."""
    import threading
    from . import rank
    threading.Thread(target=lambda: rank.top_up(store, 1), daemon=True, name='batch-next').start()


def ended(store, tid, conv, said: str, actor: str = 'router') -> bool:
    """The item behind one line ended upstream: that line settles, with the reason, and the batch closes only when none is
    left. Said on the item, never as the task's ending line (channels.ENDED_SAID), which would close the whole batch."""
    it = store.batch_item(tid, conv)
    if not it or it['State'] == 'ended': return False
    store.add_comment(tid, 'router', 'agent', f"{it.get('Title') or conv}: {said}")
    return set_item(store, tid, conv, actor, State='ended', EndedWhy=said)


def arrived(store, tid, conv, who: str, actor: str = 'router'):
    """Something new was said on one item (a comment on a pull request in the batch): its line opens again for the agent,
    and a closed batch opens again for that line alone."""
    it = store.batch_item(tid, conv)
    if not it: return False
    store.update_batch_item(tid, conv, {'State': 'waiting', 'Result': f"{who} wrote on it since"
                                        + (f" - before that: {it['Result']}" if it.get('Result') else '')})
    if (store.get_task(tid) or {}).get('Status') in ('done', 'dropped'): store.update_task(tid, {'Status': 'open'}, actor)
    return True
