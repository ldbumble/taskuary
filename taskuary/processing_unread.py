"""The Unread presentation of the same canonical roots used by All.

The funnel remains a card/navigation adapter. It no longer supplies membership,
read policy, history windows, or an independent size limit after activation.
"""
import copy
import json
from datetime import datetime, timedelta

from . import processing_all

# An open task the owner cleared comes back to the work tab once it has been quiet this long. Done
# used to be the end of it: the task stayed open in the task tab and the work tab never raised it
# again (the owner, 2026-09-15: "it should show back up in the work also if it's still open later").
RETURN_MINUTES = 60


def return_minutes(store) -> int:
    try: return max(1, int(store.get_settings().get('task_return_minutes') or RETURN_MINUTES))
    except (TypeError, ValueError): return RETURN_MINUTES


def query_for(store, only=None, *, history=True):
    try:
        days = int(store.get_settings().get('feed_days') or 14)
    except (TypeError, ValueError):
        days = 14
    filters = {}
    if only and only.startswith('view:'):
        try:
            filters = json.loads(only[5:])
            if not isinstance(filters, dict) or set(filters) - {'channel', 'source'}:
                raise ValueError()
        except (ValueError, TypeError):
            raise ValueError('Invalid shared inventory filter') from None
    return processing_all.normalize_query(filters.get('channel'), filters.get('source'), days if history else 36500)


def _arrived_after_close(task, view) -> bool:
    """Did THEY write after the task was closed? Closing ends the work, it does not deafen the
    thread - so a real reply afterwards is new work and comes back.

    Our OWN line is not that, and it is the common case: the reply is usually the very thing that
    closed the task, filed a second after it. Counting it put every task closed by answering it
    straight back into the work tab and left it there - TQ-0491 closed 18:18:07 with its own sent
    reply stamped 18:18:08, and TQ-0404, four days closed, the same way (the owner, 2026-09-11:
    "why are closed tasks showing up in work??").
    """
    from .ingest import is_ours
    at = processing_all._stamp(task.get('ClosedAt'))
    if not at: return False
    return any((processing_all._stamp(m.get('SentAt')) or at) > at
               for m in view.get('messages') or [] if not is_ours(m))


# the lanes that are the OWNER's move (processing_order band 2): what Next leaves in Passed for the hour
# ('stopped' is not here: it stays unread however often it is looked at - its own rule, below)
OWNER_LANES = ('yours', 'asked', 'approve', 'blocked', 'queued', 'broken')
FINISHED_HOURS = 72          # an agent's result nobody opened for three days is history, not news


def _agent_finished(store, tid, active, review, read_at, now):
    """{'who', 'summary', 'unread'} when this task was closed by its agent - not the owner - in the last three days.
    What the card IS does not turn on the read: putting it on the table reads it, and a read that turned it into
    a closed fyi row took it off the rail under the chat that was showing it (the owner, 2026-09-24). The read
    decides only whether it is still waiting."""
    if not tid or active or review: return None
    t = store.get_task(tid) or {}
    by, closed_at = str(t.get('UpdatedBy') or ''), processing_all._stamp(t.get('ClosedAt'))
    if t.get('Status') != 'done' or by in ('', 'owner') or t.get('SourceRef') == 'assistant:dock' or closed_at is None: return None
    if closed_at < now - timedelta(hours=FINISHED_HOURS): return None
    # the agent's own close note is the proof (selfclose.py): 'who last wrote the row' also named the owner's
    # other spellings ('you', a migration), which the read used to hide once it no longer decided the card
    said = next((c['Body'] for c in reversed(store.list_comments(tid) or [])
                 if str(c.get('Body') or '').startswith('The agent closed this itself')), None)
    if said is None: return None
    return {'who': 'The agent' if by in ('assistant', 'agent', 'system', 'router') else by, 'summary': said.split(':', 1)[1].strip() if ':' in said else '',
            'unread': not (read_at and read_at >= closed_at)}


def card_for(store, item, compact, live_state, now, states=None, quiet=RETURN_MINUTES):
    from . import funnel
    from .processing_reads import state

    view = item['view']
    read = state(item, now)
    row = copy.deepcopy(compact['row'])
    tasks = view.get('tasks') or []
    task = next((t for t in tasks if t['TaskId'] == row.get('TaskId')), tasks[0] if tasks else {})
    tid = task.get('TaskId')
    allowed = set(compact.get('display_message_ids', []))
    pending = [r for r in view.get('reviews', []) if r.get('Status') == 'pending'
               and (r.get('MessageId') in allowed or (not row.get('MessageId') and not r.get('MessageId')))]
    review = max(pending, key=lambda r: r['ReviewId']) if pending else None
    workers = [w for w in live_state if w.get('taskId') == tid] if tid else []
    worker = workers[-1] if workers else None
    active = task.get('Status') not in ('done', 'dropped')
    persisted_working = active and any(r.get('TaskId') == tid and r.get('Status') == 'running'
                                      for r in view.get('runs', []))
    # handed to an agent and not started: on the rail until it starts, however often it was looked at
    queued = active and not workers and str(task.get('Assignee') or '').startswith('agent:') and not persisted_working
    # a done task is not work any more - its own row, the assistant's note that became it, AND the mail
    # it was opened from. That last one used to stay in the pipe wearing an fyi face with its task
    # already closed (the owner, 2026-09-07: "it should just go off the unread timeline"), and reading
    # the fact rather than a receipt clears the ones closed before this shipped too. Mail that arrived
    # AFTER the close is new: closing a task ends the work on it, it does not deafen the thread.
    closed = not active and not review and (not row.get('MessageId') or row.get('Channel') == 'assistant'
                                            or not _arrived_after_close(task, view))
    if row.get('MessageId'):
        if review:
            exact = next(m for m in view['messages'] if m['MessageId'] == review['MessageId'])
            row = processing_all.message_row(exact, item, processing_all._thread_index([item]), now.strftime('%Y-%m-%d %H:%M:%S'))
            row.update(ReviewId=review['ReviewId'], ReviewStatus='pending', ReviewKind=review.get('Kind'),
                       HasDraft=bool(review.get('DraftText')))
        cards = funnel.from_feed(store, [row], canonical=True)
        card = cards[0]
    else:
        target = compact['open_target']
        kind = target['kind']
        base = dict(tid=tid, when=compact['activity_at'], priority=task.get('Priority'),
                    channel=compact['channel'], category=compact['category'], who=compact['actor'],
                    preview=compact['preview'])
        if kind == 'idea':
            idea = next(i for i in view['ideas'] if i['IdeaId'] == target['id'])
            try: action = json.loads(idea.get('ActionJson') or '{}')
            except (ValueError, TypeError): action = {}
            triage = action.get('triage') or {}
            lane = processing_all.idea_lane(idea)
            base.update(idea=idea['IdeaId'], idea_kind=idea.get('Kind'), action=action,
                        priority=triage.get('priority'), tid=action.get('tid') or tid,
                        mid=action.get('mid'), settling=bool(triage.get('pending')),
                        urgent_request=lane == 'asked' and funnel.priority_rank(triage.get('priority')) == 0)
            card = funnel._item('', 'idea', lane, compact['title'], **base)
        else:
            card = funnel._item('', 'todo' if kind == 'task' else 'action',
                                'queued' if kind == 'task' and queued else 'asked' if kind == 'task' and active else 'fyi',
                                compact['title'], **base)
        if review:
            card.update(kind='action' if review.get('Kind') == 'action' else 'review', lane='approve',
                        rid=review['ReviewId'], mid=review.get('MessageId'), draft=bool(review.get('DraftText')),
                        why='A proposed action is waiting for your approval' if review.get('Kind') == 'action' else 'A reply is waiting for your approval')
    # ...and the row behind it says so too: a mail-backed row read 'asked you' - as if a person were
    # waiting on the owner - while the task under it was already an agent's (the owner, 2026-09-07:
    # "What about all the other tasks?")
    if queued and card['lane'] == 'asked':
        card.update(lane='queued', why=f"handed to {task['Assignee'].split(':', 1)[-1] or 'an agent'}, not started yet")
    # ...and WHY it has not started, which the lane word cannot say. "waiting to start" reads as a
    # queue that clears itself; every cause underneath it needs the owner instead (2026-09-14).
    if card['lane'] == 'queued' and card.get('tid'):
        card['why_idle'] = funnel.not_started_why(store, card['tid'])
        if not card.get('why'):
            card['why'] = f"handed to {str(task.get('Assignee') or '').split(':', 1)[-1] or 'an agent'}, not started yet"
        # ...unless an agent HAD it and is gone. That is not a queue that will clear itself, it is work
        # that stopped, and the owner is the only one who moves it: `stopped`, wearing the cause as its
        # word (the owner, 2026-09-17: "stopped should stay on stopped and shown to user to handle").
        if funnel.agent_left(store, card['tid']): card.update(lane='stopped', why=card['why_idle'])
    # THE LATEST ACTION IS THE STATUS (the owner, 2026-09-24). An agent parked or asking already spoke
    # for its task over a draft; one still WORKING did not, so a reply it wrote a minute into the session
    # read "reply ready" through forty more minutes of edits. Working is newer than any draft it made -
    # the reply is back the moment the agent parks or its session ends.
    if worker and active:
        agent_cards = funnel.from_agents(store, live_state=[worker], now=now)
        if agent_cards:
            card.update(agent_cards[0])
        else:
            if review: card.update(rid=None, draft=False)
            card.update(kind='agent', lane='working', working=worker.get('agent') or worker.get('label') or 'agent',
                        agent=worker.get('agent') or worker.get('label') or 'agent', sid=worker.get('sid'),
                        mode=worker.get('mode') or 'terminal', tail=worker.get('tail') or [],
                        why='An agent is working on this; nothing needs your input yet')
    elif (row.get('Working') or persisted_working) and active:          # ...a headless run too
        who = row.get('Working') or 'agent'
        if review: card.update(rid=None, draft=False)
        card.update(kind='agent', lane='working', working=who, agent=who)
    elif active and not review:
        card = funnel.paused_conversation(store, card)
    # ...and an open task nobody closed comes BACK once it has been quiet, so clearing it is a
    # "not now", never a way to lose it. `queued` used to sit in the force-unread clause below, which
    # made a task handed to an agent the one row Done could not shift - the same question answered two
    # ways in one column (the owner, 2026-09-15: "why is that one showing up but not 575"). It clears
    # like the rest now, and the hour brings it back. The owner's own Later/Skip still outranks it.
    read_at = processing_all._stamp(read.get('read_at'))
    back = bool(tid and active and not read.get('deferred') and read_at
                and read_at <= now - timedelta(minutes=quiet))
    if back: card['why_open'] = 'Nothing has closed this since you last looked. If it is done, close it.'
    # PASSED IS STILL YOURS (the owner, 2026-09-23: "i thought if you hit next it goes to passed section?"):
    # Next reads the row, and a read row used to leave the rail altogether until the hour brought it back -
    # an open task, a draft waiting for a yes, simply gone. Work that is still the owner's stays on the rail
    # for that hour, marked shown, which is what the Passed band draws; the walk does not offer it again.
    # NEXT only - the shown mark, below. Done is "off work for the hour" (2026-09-15) and stays gone.
    passed = bool(tid and active and read_at and not read['unread'] and not read.get('deferred') and not back
                  and card['lane'] in OWNER_LANES)
    # AN AGENT FINISHED IT (same message: "same for finished agent task?"): a task its agent closed is a
    # result nobody has looked at yet. It is on the rail once, with Reports, until it is read; a task the
    # owner closed stays closed and gone.
    finished = _agent_finished(store, tid, active, review, read_at, now)
    if finished:
        from .coder import no_one_behind
        card.update(kind='agentdone', lane='report', who=finished['who'], summary=finished['summary'], closed=True,
                    why='the agent finished and closed it - read what it found')
        # work the owner started here has nobody behind it to answer (a brief typed in the chat)
        if no_one_behind(row.get('Channel')): card['mid'] = None
        closed = False
    # OUR OWN SEND IS A RECEIPT, NOT AN ARRIVAL. A report's alert files the message it just sent so
    # you can see that it went (reports.send_alert) - Taskuary writing to you, on WhatsApp or
    # Telegram. It arrived on the table wearing a sender's face: "Ignore this sender", "Block them
    # in Settings", offered on Taskuary's own outbound line, where blocking the sender would mean
    # blocking yourself (the owner, 2026-09-17). The funnel has always known this - _feed_skip drops
    # `Direction == 'out'` - but the canonical road asks from_feed to RENDER a row whose membership
    # was already decided, so the rule has to be said again here, where Unread is decided.
    #
    # Only when nothing else is going on: a send on a live task is part of that task's story, and a
    # draft still waiting for a yes is the owner's move whichever way the last line pointed.
    receipt = bool(not tid and not review and row.get('Direction') == 'out')
    # Worker attention is not a read operation. An active worker remains visible.
    # ...and stopped work is on the rail however often it was looked at - a look is not handling it;
    # only the owner's own Later holds it (same decision, 2026-09-17).
    stopped = active and card['lane'] == 'stopped' and not read.get('deferred')
    unread = not closed and not receipt and bool((read['unread'] and not read.get('deferred')) or back or stopped or (finished and finished['unread']) or
                                                 (active and (worker or row.get('Working') or persisted_working or card.get('paused'))))
    # the arrow means triage moved it up: an idea or a task raised to "asked you", or an urgent ask
    card['promoted'] = bool(card.get('urgent_request')) or (card['lane'] == 'asked' and (card['kind'] in ('idea', 'todo') or row.get('Channel') == 'assistant'))
    card.update(key='processing:' + item['item_id'], processing_id=item['item_id'],
                member_ids=list(item['member_ids']), context_revision=item['context_revision'],
                view_revision=item['view_revision'], aliases=[a['Value'] for a in item.get('aliases', [])
                    if a.get('Namespace') == 'legacy_funnel'] + ['processing:' + root['ItemId'] for root in item.get('item_history', [])],
                unread=unread, deferred=bool(read.get('deferred')), defer_until=read.get('defer_until'),
                more=max(0, compact['counts'].get('messages', 0) - 1),
                source=row.get('SourceName') or compact['source'], status=row.get('MsgStatus') or compact['status'], order_band=funnel._band(card))
    # shown-but-not-read exists for the lanes whose unread is NOT the receipt's to give: the mark keeps
    # Next from bouncing straight back to what it just introduced (everything else shown is read - the
    # receipt says so).
    # 'queued' belongs with them. A task handed to an agent that has not started is forced unread by the
    # clause above, so its receipts - all of them read - decide nothing, and with no shown-mark either
    # there was nothing left to keep it out of the walk: Next introduced it, Next chose it again, for as
    # long as the owner kept pressing (the owner, 2026-09-14: "i keep on clicking next on the assistant
    # idea but it just comes right back behind the current one"). It stays unread, so the work tab still
    # holds it; it is simply no longer the thing the walk offers next.
    # ...for the same hour the receipt holds. A new chat clears the mark for agent: keys only
    # (funnel.reset_walk), so on these rows it held for good: the quiet hour brought a task waiting to
    # start back unread (`back`, above), the walk skipped it for the mark, and stranded it at the end
    # as "1 unread thing still waits. Say next" for as long as Next was pressed (the owner, 2026-09-18:
    # "it skipped it but then saw it at the end and hitting next just confuses it"). The mark ages out
    # with the receipt, so the row comes round again when the hour brings it back.
    # ONE CLOCK FOR ALL OF THEM (the owner, 2026-09-23: "promote later after an hour or so unless it's
    # silenced until tomorrow"): an agent waving and a reply ready kept a 30-minute cooldown of their own
    # and the mark for good, so the rail's Passed band and the walk disagreed about when they were back.
    # The mark is the timer now - task_return_minutes, an hour by default - and Tomorrow is the silence.
    card.pop('surfaced', None); card.pop('surfaced_at', None)
    shown = next((st for k in [card['key'], *card['aliases']] for st in [(states or {}).get(k)] if st and st.get('Status') == 'surfaced'), None)
    if shown and card['lane'] in ('approve', 'blocked', 'queued', 'stopped'):
        shown_at = processing_all._stamp(shown.get('At'))
        if shown_at is None or shown_at > now - timedelta(minutes=quiet):
            card.update(surfaced=True, surfaced_at=shown.get('At'))
    passed = passed and shown is not None
    if passed:
        unread = True
        card.update(unread=True, surfaced=True, surfaced_at=shown.get('At') or read.get('read_at'))
    if card['lane'] == 'fyi' and not card.get('sig'):
        summaries = [r for r in view.get('processing_summaries', [])
                     if r.get('ContextRevision') == item['context_revision'] and r.get('Summary')
                     and r.get('Key') in [card['key'], *card['aliases']]]
        if summaries:
            card['summary'] = next((r for r in summaries if r['Key'] == card['key']), summaries[-1])['Summary']
    card['actionable'] = bool(unread and not passed and not card['deferred'] and not card.get('settling')
                              and card['lane'] != 'working' and not funnel._not_yet(card))
    return card


def build(store, *, now=None, live_state=None, include_read=False, only=None,
          full_history=False):
    from . import funnel, terminal
    now = now or datetime.now()
    live_state = terminal.live_sessions(tail=6) if live_state is None else live_state
    query = query_for(store, only, history=not full_history)
    for attempt in (1, 2):
        processing_all.wait_settled(store)
        snapshot = store.processing_inventory_snapshot(
            fixed_now=now.isoformat(), live_state=live_state, display_only=True,
            history_days=query['days'])
        # ...and the SECOND attempt takes what there is. A write landing between the settle check and
        # the snapshot deserves one more try; a census that is still unsettled after it is a state
        # the rail has to live in, not a reason to have no rail (processing_all.compact_inventory).
        # The pile then carries coverage.degraded and says so rather than disappearing.
        try:
            rows, coverage, counts = processing_all.compact_inventory(
                snapshot, query, include_excluded=include_read, degraded_ok=attempt == 2)
            break
        except processing_all.AllError as e:      # a write landed between the settle check and the snapshot: once more
            if attempt == 2 or e.detail.get('code') != 'processing_coverage_pending': raise
    by_id = {item['item_id']: item for item in snapshot['items']}
    states = store.funnel_states()
    quiet = return_minutes(store)
    cards = [card_for(store, by_id[row['item_id']], row, live_state, now, states, quiet) for row in rows]
    cards = [card for card in cards if include_read or card['unread']]
    # Calendar keeps its established adapter; source filtering applies to it too.
    query = query_for(store, only)
    if processing_all._matches('calendar', '', query):
        calendar_states = store.processing_calendar_states()
        for card in funnel.from_calendar(store, now):
            receipt = calendar_states.get(card['key'], {})
            until = processing_all._stamp(receipt.get('until'))
            deferred = receipt.get('status') in ('later', 'skip') and (until is None or until > now)
            if not include_read and (receipt.get('read') or deferred):
                continue
            card.update(unread=True, deferred=False, actionable=not funnel._not_yet(card), order_band=funnel._band(card))
            card.update(unread=not receipt.get('read') and not deferred, deferred=deferred,
                        actionable=not receipt.get('read') and not deferred and not funnel._not_yet(card))
            cards.append(card)
    # A broken connection is a CONDITION: no receipt, no defer, no census row - it is on the rail
    # while it is broken and gone when it is fixed. The owner, 2026-09-18, on a repo that had been
    # answering 404 for days: "we should have notification for the github issue in the notification
    # place". Before this the `broken` lane was produced by exactly one thing, a failing report.
    # ...but the walk's own marks still hold on it (funnel_state, keyed conn:<id>): it had none, so Next
    # put the same broken connection back on the table on every press and the walk could not get past it
    # (the owner, 2026-09-23: "when I hit next it takes me back to linkedin failed"). Shown = walked past,
    # still on the rail; later/skip = held until then; a changed error (its sig) is new again.
    states = store.funnel_states()
    stamp = now.strftime('%Y-%m-%d %H:%M:%S')
    for card in funnel.broken_connections(store):
        st = states.get(card['key']) or {}
        held = st.get('Status') in ('later', 'skip', 'done') and (not st.get('Until') or funnel._ts(st['Until']) > stamp)
        if held and st.get('Status') == 'done' and st.get('Note') and st['Note'] != card.get('sig'): held = False
        if held and not include_read: continue
        card.update(unread=not held, deferred=held, actionable=not held, order_band=funnel._band(card))
        # NEXT DISMISSES AN ERROR (the owner, 2026-09-23: "next on error should dismiss it no?" / "i hit
        # next on LinkedIn and it went to passed not gone"): walked past, it is GONE from the rail and the
        # walk - not waiting in Passed - until the error CHANGES (its sig), which is a new failure
        # ...and that holds for the rail's read-inclusive pile too, or Passed keeps it on screen (2026-09-23:
        # "still see linkedin error. can't get rid of it")
        if st.get('Status') == 'surfaced' and not (st.get('Note') and st['Note'] != card.get('sig')): continue
        cards.append(card)
    cards = funnel._order(cards)
    return {'rev': snapshot['snapshot_revision'], 'items': cards, 'hidden': 0, 'muted': 0,
            'rules': [], 'canonical': True, 'coverage': coverage,
            'counts': {'all': counts['total'], 'unread': sum(c['unread'] for c in cards),
                       'actionable': sum(c['actionable'] for c in cards)},
            'lanes': [{'lane': lane, 'word': funnel.LANE_WORDS[lane][0], 'role': funnel.LANE_WORDS[lane][1],
                       'n': sum(c['lane'] == lane for c in cards)} for lane in funnel.LANES]}
