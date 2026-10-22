"""The Unread presentation of the same canonical roots used by All.

The funnel remains a card/navigation adapter. It no longer supplies membership,
read policy, history windows, or an independent size limit after activation.
"""
import json
import re
from .timewords import plural
from .categories import agent_word
from datetime import date, datetime, timedelta

from . import lanes, processing_all, proposals

# How long a row with NO open task behind it - a draft or an agent's question on its own - stays passed after Next, and how long a
# phone's section walk is held. FIXED, not a setting (the owner, 2026-10-21): it was task_return_minutes, which timed open tasks
# too; open tasks now pass for the rest of the walk (`this_walk`, below), and what the clock still covers is too small to be a knob.
# A home that still stores the old setting is simply not read.
RETURN_MINUTES = 180


def query_for(store, only=None, *, history=True):
    try:
        days = int(store.get_setting('feed_days') or 14)
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
    from .autoreply import is_auto
    # ...nor is a line triage FILED with nothing to do: a "thank you!" after the close brought TQ-0942 back under FYI
    # (the owner, 2026-10-05: "it should never be there, i closed it") - the same materiality the stale-draft check reads
    # (store.last_material_inbound_on_task, PW-240). A line still being triaged counts until triage files it.
    return any((processing_all._stamp(m.get('SentAt')) or at) > at
               for m in view.get('messages') or []
               if not is_ours(m) and not is_auto(m) and m.get('Status') not in ('filed', 'skipped', 'ignored'))


# the lanes that are the OWNER's move (processing_order band 2): what Next leaves in Passed for the quiet hours
# ...and URGENT work too (R3; the owner, 2026-09-25: "i hit next on urgent task and it's gone now but it should be in passed
# at least"). Only a row with an open task behind it is ever Passed, so a meeting with no task still leaves on Next (R2).
# Read off lanes.json: every lane whose section is Urgent or Tasks - a task an agent is working included (2026-10-21).
OWNER_LANES = lanes.OWNER_LANES
# A goal's CHILD is a task row of its own, whoever holds it (the owner, 2026-10-21): it was folded into the goal's row while
# an agent, a person or a hand-off had it, and a step being worked was nowhere on the rail. The goal's row still names who
# holds which step ("coding on step 5 · Ray owes step 4").
# what a new walk raises again whatever the old one did with it: work that blocks on the owner (funnel.reset_walk)
RAISED_BY_NEW_WALK = lanes.WAITS
WALK_KEY = 'walk_started_at'


def walk_started_at(store):
    return processing_all._stamp(store.get_setting(WALK_KEY))


def this_walk(at, walk_at) -> bool:
    """Was a read or a mark on an open task made in the walk now running? NEXT IS ONCE PER WALK (the owner, 2026-10-21: "next keeps
    a task on unless it's closed. It does not have to come back... if it starts over you see same list of tasks again"): it passes an
    open task until the walk ends or a new one starts (both stamp WALK_KEY, funnel.new_walk), never for a number of hours. The same
    second as the stamp is the old walk's: the Next that ran the walk out is written just before it."""
    return bool(at and (walk_at is None or at > walk_at))


def _decided(view, allowed) -> bool:
    """A draft on these messages was decided (sent, rejected, no reply) and nobody has written since."""
    from .ingest import is_ours
    at = [processing_all._stamp(r.get('DecidedAt')) for r in view.get('reviews') or []
          if r.get('Status') != 'pending' and r.get('MessageId') in allowed]
    at = [a for a in at if a]
    if not at: return False
    return not any((processing_all._stamp(m.get('SentAt')) or max(at)) > max(at) for m in view.get('messages') or [] if not is_ours(m))


def _idea_off(store, view, compact, now) -> bool:
    """An Advisor idea that is not work on the rail: put down, asleep until a later day, a meeting's prep (the calendar
    row IS the meeting), one its report's card said is not work, or one a reply you sent has since answered. The old
    rail kept the last four; the canonical road dropped them (I5, 2026-09-27)."""
    target = compact.get('open_target') or {}
    if target.get('kind') != 'idea': return False
    idea = next((i for i in view.get('ideas') or [] if i['IdeaId'] == target.get('id')), {})
    status = str(idea.get('Status') or 'open')
    if status == 'snoozed': return str(idea.get('SnoozeUntil') or '9') > now.strftime('%Y-%m-%d %H:%M:%S')
    if status != 'open' or idea.get('Kind') == 'prep': return True
    try: action = json.loads(idea.get('ActionJson') or '{}')
    except (ValueError, TypeError): action = {}
    if action.get('work') is False: return True
    from .assistant import sent_reply_for
    sent = sent_reply_for(store, {'action': action})
    return bool(sent) and str(sent.get('DecidedAt') or sent.get('CreatedAt') or '') >= str(idea.get('LastSaid') or idea.get('FirstSeen') or '')


def _noise_hidden(store) -> bool:
    return str(store.get_setting('rail_hide_noise', '1')).strip() not in ('0', 'false', 'off')


def _noise(row, view) -> bool:
    """Nobody asking anything: withdrawn, an auto-reply, or a thread whose last word is yours. Not a policy-IGNORED
    line: that one stays, saying so (the rail shows what a rule filed; unjudged is not fyi)."""
    from .autoreply import is_auto
    from .ingest import is_ours
    if row.get('MsgStatus') == 'withdrawn' or is_auto(row): return True
    at = processing_all._stamp(row.get('SentAt'))
    msgs = view.get('messages') or []
    last = max(msgs, key=lambda m: processing_all._stamp(m.get('SentAt')) or datetime.min, default=None)
    return bool(at and last and is_ours(last) and (processing_all._stamp(last.get('SentAt')) or at) >= at)


# who acts for the owner: the page, the phone and the Assistant's acts write 'owner' (or 'you'). Never 'assistant' - that
# is a regular agent's own name when it closes its work
OWNER_ACTORS = ('owner', 'you')


def finish_evidence(store, tid):
    """{'who', 'summary'} when this task was closed by its agent or its upstream item ending, else None.
    WHOEVER EDITED IT LAST OWNS IT (the owner, 2026-09-25): an edit by the owner - Mark done, sending the reply the
    agent drafted, anything - makes the close theirs, and the result is not shown again. Otherwise the agent's own
    note says who finished it and what it found. A ten-minute window around the close stood in for this and got it
    wrong: sending the drafted reply closed a task seconds after the agent's note, and an answered task came back as
    "agent finished" (TQ-0726, TQ-0734)."""
    if str((store.get_task(tid) or {}).get('UpdatedBy') or '') in OWNER_ACTORS: return None
    for c in reversed(store.list_comments(tid) or []):
        body = str(c.get('Body') or '')
        if body.startswith('The agent closed this itself'):
            return {'who': c.get('Actor') if c.get('Actor') not in (None, '', 'assistant', 'agent', 'system') else 'The agent',
                    'summary': body.split(':', 1)[1].strip() if ':' in body else ''}
        if c.get('Actor') == 'router' and 'this task came from was' in body:
            kind = 'pull request' if 'pull request' in body else 'issue' if 'issue' in body else 'item'
            return {'who': f'Its {kind}', 'summary': body}
    return None


def _agent_finished(store, tid, active, review, read_at, now):
    """{'who', 'summary', 'unread'} when this task was closed by its agent or its upstream item ending - not the owner.
    NEVER SEEN BY A PERSON STAYS ON THE RAIL (the owner, 2026-09-24): there is no age limit any more - it was
    three days, and a result nobody read simply vanished.
    What the card IS does not turn on the read: putting it on the table reads it, and a read that turned it into
    a closed fyi row took it off the rail under the chat that was showing it (the owner, 2026-09-24). The read
    decides only whether it is still waiting."""
    if not tid or active or review: return None
    t = store.get_task(tid) or {}
    closed_at = processing_all._stamp(t.get('ClosedAt'))
    if t.get('Status') != 'done' or t.get('SourceRef') == 'assistant:dock' or closed_at is None: return None
    ev = finish_evidence(store, tid)
    if not ev: return None
    return {**ev, 'unread': not (read_at and read_at >= closed_at)}


# the lanes an agent's run puts a row in by stopping - blocked (asking, parked), stopped, saved
AGENT_STOPS = ('blocked', 'stopped', 'saved')


def _agent_spoke_at(store, tid):
    """When the task's run last said anything (a question, a turn ending, a session ending) - the moment its row became
    the owner's again. None with no run word, where the old read stands."""
    evs = store.worker_events(tid) if tid else []
    return processing_all._stamp(evs[-1].get('CreatedAt')) if evs else None


def names(item) -> list:
    """Every key a card for this inventory item answers to: its own first, then its aliases - ONE list for card_for
    and for a keyed build, so a lookup that skips the other items can never disagree with the card about who it is."""
    return ['processing:' + item['item_id'], *[a['Value'] for a in item.get('aliases', []) if a.get('Namespace') == 'legacy_funnel'],
            *['processing:' + root['ItemId'] for root in item.get('item_history', [])]]


def holder_name(assignee: str) -> str:
    """Who holds a step, as a name: 'person:ray.colton@northwind.example' -> 'Ray Colton', 'agent:coding' -> 'coding'."""
    who = str(assignee or '')
    if who.startswith('agent:'): return who.split(':', 1)[1]
    if who.startswith('person:'): return ' '.join(p[:1].upper() + p[1:] for p in re.split(r'[._-]+', who.split(':', 1)[1].split('@')[0]) if p)
    return ''


def goal_facts(store, task, tid, now) -> dict:
    """What the goal's row says (spec 2026-10-12): kind (slipped / on track / not started), news, the count, who holds
    it, its date. Facts, not a progress bar."""
    steps = store.goal_steps(tid)
    done, n = sum(1 for x in steps if x['done']), len(steps)
    today = now.strftime('%Y-%m-%d')
    due = str(task.get('DueAt') or '')[:10] or None
    kids = [x for x in steps if x['child']]
    late_kid = any(x['child'].get('Status') == 'waiting' and str(x['child'].get('DueAt') or '')[:10] and str(x['child'].get('DueAt'))[:10] < today for x in kids)
    slipped = bool((due and due < today and done < n) or late_kid)
    started = bool(done or any(x['child'].get('Status') != 'open' or x['child'].get('Assignee') for x in kids))
    kind = 'goal_slipped' if slipped else 'goal_fresh' if not started else 'goal'
    # WHEN the news happened, so a read goal comes back only for news newer than the read (card_for): the latest step
    # closed, the day the goal slipped, the day a late step slipped
    stamps = [str(x['child'].get('ClosedAt') or '')[:19].replace('T', ' ') for x in kids if x['child'].get('ClosedAt')]
    if due and due < today and done < n: stamps.append(f'{due} 00:00:00')
    stamps += [f"{str(x['child'].get('DueAt'))[:10]} 00:00:00" for x in kids
               if x['child'].get('Status') == 'waiting' and str(x['child'].get('DueAt') or '')[:10] and str(x['child'].get('DueAt'))[:10] < today]
    news_at = max(stamps) if stamps else None
    bits, holders = [f'{done} of {n}' if n else 'no steps yet'], []
    for k, x in enumerate(steps, 1):
        c = x['child']
        if not c or c.get('Status') in ('done', 'dropped'): continue
        who = str(c.get('Assignee') or ''); name = holder_name(who)
        if who.startswith('agent:'): bits.append(f"{name} on step {k}"); holders.append(name)
        elif who.startswith('person:'): bits.append(f"{name} owes step {k}"); holders.append(name)
        elif c.get('Status') == 'open': bits.append(f'step {k} is on you')
    if slipped and due and due < today: bits.append(f"slipped {(now - datetime.strptime(due, '%Y-%m-%d')).days}d")
    # `who` is the row's person column everywhere else (the day card lists them): for a goal it is who holds it, never its creator
    return {'kind': kind, 'news': bool(news_at), 'news_at': news_at, 'due': due, 'steps': n, 'steps_done': done, 'who': holders[0] if holders else '',
            'why': ' · '.join(bits), 'back_at': f'{due} 08:00:00' if due else None, 'folded': False}


def sweep_task(store, idea: dict, action: dict) -> dict | None:
    """The open task a standalone loose-end line names (sweep.py's `task`, set where the task has no row of its own)."""
    if idea.get('Kind') != 'loose' or not action.get('task'): return None
    return store.get_task(int(action['task']))


def card_for(store, item, compact, live_state, now, states=None, quiet=RETURN_MINUTES, walk_at=None, noise=None):
    """`noise`: _noise_hidden, read once by a build for all its cards (a setting read per card was 10,000 queries)."""
    from . import funnel
    from .processing_reads import state
    from .funnel_presentation import detach

    view = item['view']
    read = state(item, now)
    row = detach(compact['row'])          # deepcopy's result at a quarter of its cost: 3,842 roots per rebuild (2026-10-20)
    tasks = view.get('tasks') or []
    task = next((t for t in tasks if t['TaskId'] == row.get('TaskId')), tasks[0] if tasks else {})
    tid = task.get('TaskId')
    allowed = set(compact.get('display_message_ids', []))
    pending = [r for r in view.get('reviews', []) if r.get('Status') == 'pending'
               and (r.get('MessageId') in allowed or (not row.get('MessageId') and not r.get('MessageId'))
                    or (r.get('Kind') == 'slot' and tid and r.get('TaskId') == tid))]     # a task's emails have no message
    review = max(pending, key=lambda r: r['ReviewId']) if pending else None
    workers = [w for w in live_state if w.get('taskId') == tid] if tid else []
    worker = workers[-1] if workers else None
    active = task.get('Status') not in ('done', 'dropped')
    # REMIND ME (2026-09-25): put away until a day - held like a deferral until that morning, then back as asked for
    from . import remind
    reminded = str(task.get('RemindAt') or '') if active else ''
    # ...unless its agent is waiting on you: a new question gets through a reminder (A11, the owner, 2026-09-25) -
    # Remind me holds a quiet task, never a question nobody would see until its day
    asking_now = bool(worker and worker.get('waiting'))
    if reminded and remind.waiting(task, now) and not asking_now: read = {**read, 'deferred': True, 'defer_until': reminded}
    persisted_working = active and any(r.get('TaskId') == tid and r.get('Status') == 'running'
                                      for r in view.get('runs', []))
    # handed to an agent and not started: on the rail until it starts, however often it was looked at
    # ...or a regular-agent task nobody has started yet: unassigned when triage named no specialist, it read as the
    # owner's own work (A10, 2026-09-25)
    from .processing_all import _has_conversation
    # NEWS AFTER THE AGENT (the owner, 2026-10-12): a sender wrote again after the agent's last session - the task is that
    # message now, on you, not "handed to an agent" nor "you ended the session" from days before
    news = funnel.news_since_agent(store, tid) if active and tid and not workers else None
    queued = active and not workers and not persisted_working and not news and (
        str(task.get('Assignee') or '').startswith('agent:') or funnel.general_not_started(task, _has_conversation(view, tid), view.get('routes', []))
        or funnel.held_for_repo(task))    # a start that stopped on "which repository?" is on the rail until you pick one
    # a done task is not work any more - its own row, the assistant's note that became it, AND the mail
    # it was opened from. That last one used to stay in the pipe wearing an fyi face with its task
    # already closed (the owner, 2026-09-07: "it should just go off the unread timeline"), and reading
    # the fact rather than a receipt clears the ones closed before this shipped too. Mail that arrived
    # AFTER the close is new: closing a task ends the work on it, it does not deafen the thread.
    closed = not active and not review and (not row.get('MessageId') or row.get('Channel') == 'assistant'
                                            or not _arrived_after_close(task, view))
    # DECIDED IS OFF, WHEREVER IT WAS DECIDED (R4, 2026-09-25): a draft sent, rejected or answered "no reply" on the
    # Review page, or an idea dismissed in the chat, stayed on the rail as an unread fyi. Off until THEY write again.
    if not tid and not review and not closed: closed = _decided(view, allowed) or _idea_off(store, view, compact, now)
    # ...and the noise the old rail filtered (R5): withdrawn lines, auto-replies, a thread you already answered
    if not tid and not review and not closed and row.get('MessageId') and (_noise_hidden(store) if noise is None else noise): closed = _noise(row, view)
    if row.get('MessageId'):
        if review:
            exact = next(m for m in view['messages'] if m['MessageId'] == (review.get('MessageId') or row['MessageId']))   # a task's email has none
            row = processing_all.message_row(exact, item, processing_all._thread_index([item]), now.strftime('%Y-%m-%d %H:%M:%S'))
            row.update(ReviewId=review['ReviewId'], ReviewStatus='pending', ReviewKind=review.get('Kind'),
                       HasDraft=bool(review.get('DraftText')))
        cards = funnel.from_feed(store, [row], canonical=True)
        card = cards[0]
        card['channel'] = processing_all.task_mark([task], view.get('messages', [])) or card.get('channel')
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
            slip, late, quiet, day = funnel.slipped_followup(store, action, now)   # a quiet thread past the person's day: the owner's move
            if slip == 'answered': store.set_idea_status(idea['IdeaId'], 'done', 'funnel'); late = 0
            elif slip: lane = slip
            base.update(idea=idea['IdeaId'], idea_kind=idea.get('Kind'), action=action,
                        priority=triage.get('priority'), tid=action.get('tid') or tid,
                        mid=action.get('mid'), settling=bool(triage.get('pending')), who_email=action.get('who_email') or '', late_days=late,
                        urgent_request=lane == 'asked' and (bool(triage.get('urgent')) or funnel.priority_rank(triage.get('priority')) == 0))
            card = funnel._item('', 'idea', lane, compact['title'], **base)
            # A LOOSE END ABOUT A TASK THE RAIL DRAWS NO ROW FOR (sweep.loose_tasks: its only mail is your own) is THAT task's row -
            # its own verbs, Close, Remind me, Send to agent - never an idea's: Make a task on it made the same work twice
            about = sweep_task(store, idea, action)
            if about:
                card = funnel._item('', 'todo', 'yours', compact['title'], **(base | {'tid': about['TaskId'], 'idea': None, 'idea_kind': None,
                                                                                        'mid': None, 'priority': about.get('Priority')}))
                card.update(loose=True, loose_at=idea.get('LastSaid'))
                if about.get('Status') in ('done', 'dropped'): closed = True     # closed is closed: off at once, the check puts it down
        else:
            card = funnel._item('', 'todo' if kind == 'task' else 'action',
                                # a task with no message is YOUR task, like one with mail (R14, 2026-09-25) - not "asked"
                                'queued' if kind == 'task' and queued else 'yours' if kind == 'task' and active else 'fyi',
                                compact['title'], **base)
        if review:
            card.update(kind='action' if review.get('Kind') == 'action' else 'review', lane='approve',
                        rid=review['ReviewId'], mid=review.get('MessageId'), draft=bool(review.get('DraftText')),
                        why='A proposed action is waiting for your approval' if review.get('Kind') == 'action' else 'A reply is waiting for your approval')
            # WHAT THE AGENT DID, between what triggered the task and what you are approving (the owner, 2026-09-28: "the
            # goal is to see what triggered the task, agent action, and what we are reviewing") - the rail knew it only
            # inside the `why` sentence; the older walk (funnel.from_feed) always carried it as `summary`
            if not card.get('summary'): card['summary'] = funnel.agent_found(store, tid)
            # a REPLY whose task also waits on a merge: its Close out runs both (verdicts.decide), so its card says so
            if review.get('Kind') not in ('action', 'slot'):
                other = proposals.closeout_pending(store, tid)
                if other: card.update(closeout=proposals.CLOSEOUT.get(proposals._action(other)), rides=True)
            # the task's close-out (merge the PR, close the issue): ONE word, Approve - the card's sentence says what it does there
            closeout = proposals.CLOSEOUT.get(proposals._action(review)) if review.get('Kind') == 'action' else None
            if closeout:
                ev = finish_evidence(store, tid)
                # a reply waiting beside it rides WITH it (verdicts reply_text) - the same one button
                rides = bool(store._one("SELECT 1 x FROM review WHERE TaskId=? AND Status='pending' AND Kind NOT IN ('action','slot')", (tid,)))
                card.update(closeout=closeout, rides=rides, why=f"{(ev or {}).get('who') or 'The agent'} finished it - {proposals.CLOSE_WORD} {closeout}"
                                                   + (' and posts your reply' if rides else '')
                                                   + (f": {ev['summary']}" if (ev or {}).get('summary') else ''))
    if review and review.get('Kind') == 'slot':     # the task's emails (slots.py), counted - never called its reply
        n = len([r for r in pending if r.get('Kind') == 'slot'])
        card.update(lane='approve', why=f"{plural(n, 'email')} drafted for you to send")
    # ONE "AGENT FINISHED" (A17, 2026-09-25): a finish that drafted a reply left the task waiting on it, and the owner saw
    # only "reply ready" - never that the agent had finished. The reply is the move, so the card stays the reply to
    # send, and says who finished it.
    if review and task.get('Status') == 'waiting' and review.get('Kind') not in ('action', 'slot'):
        ev = finish_evidence(store, tid)
        if ev: card['why'] = f"{ev['who']} finished it - its reply is ready for your yes" + (f": {ev['summary']}" if ev.get('summary') else '')
    # ...and the row behind it says so too: a mail-backed row read 'asked you' - as if a person were
    # waiting on the owner - while the task under it was already an agent's (the owner, 2026-09-07:
    # "What about all the other tasks?")
    # WAITING ON THEM (the owner, 2026-09-25): a task set to waiting read "on you" here while the Tasks list and the
    # task page said "waiting on them" - the rail had no lane for it. The TASK only: a message from them is their
    # answer, and that is your move again (FollowUpTests)
    if not row.get('MessageId') and task.get('Status') == 'waiting' and not review and card['lane'] == 'yours': card['lane'] = 'theirs'
    # ...and a step a PERSON owes, quiet past its day plus that person's usual day, is SLIPPED: the owner's move (spec 2026-10-12)
    who = str(task.get('Assignee') or '')
    # ...whatever row leads the item (their mail, somebody else's on the thread, none): the step is theirs while it waits, and it
    # has slipped unless THEY have written on it since its day
    if (card['lane'] in ('theirs', 'asked', 'yours', 'fyi') and who.startswith('person:') and task.get('Status') == 'waiting'
            and str(task.get('DueAt') or '')[:10]):
        from . import outcomes
        try: due = date.fromisoformat(str(task['DueAt'])[:10])
        except ValueError: due = None
        if due and store._one("SELECT 1 x FROM message WHERE TaskId=? AND lower(FromEmail)=? AND SentAt>=? LIMIT 1", (tid, who[7:].lower(), due.isoformat())): due = None
        if due:
            day = outcomes.late_after(store, who[7:], int(store.get_setting('slipped_default_days', 5) or 5))
            past = (now.date() - due).days - day
            if past >= 0:
                card.update(lane='forgotten', who_email=who[7:].lower(), late_days=past,
                            why=f"{holder_name(who)} has been quiet {(now.date() - due).days} days past {due:%b %d} - late for them after {day}")
    # ...and a SLIPPED FOLLOW-UP among the item's members is the owner's move whatever row leads the item: on this rail the
    # Advisor's line about a thread joins the thread's own item, so the rule reads the members, not only the target
    if card['lane'] not in ('forgotten', 'blocked', 'approve', 'time'):
        for i in view.get('ideas') or []:
            if i.get('Status') != 'open' or i.get('Kind') != 'followup': continue
            try: a = json.loads(i.get('ActionJson') or '{}')
            except (ValueError, TypeError): a = {}
            slip, late, quiet, day = funnel.slipped_followup(store, a, now)
            if slip == 'answered': store.set_idea_status(i['IdeaId'], 'done', 'funnel'); continue
            if slip:
                card.update(lane=slip, who_email=a.get('who_email') or '', late_days=late, idea=card.get('idea') or i['IdeaId'], action=a,
                            idea_kind=card.get('idea_kind') or i.get('Kind'), why=funnel.slipped_why(a.get('who_email'), quiet, day)); break
    # A GOAL IS ONE ROW (spec 2026-10-12): its kind says its state, its sub line says the count and who is holding it, its
    # date sits where the age goes, and it is never gone while open. Its children are rows of their own, naming it.
    from .store import is_goal
    if is_goal(task) and active and not review and not worker: card.update(**goal_facts(store, task, tid, now))
    elif task.get('ParentId') and active: card.update(goal=funnel.task_ref(task['ParentId']), folded=False)
    if news:
        who = agent_word(task.get('Kind'))                 # what it IS - a profile's name is not a worker
        frm = str(news.get('FromName') or news.get('FromEmail') or 'they').split(' at ')[0]
        card.update(lane='asked' if card['lane'] in ('queued', 'saved', 'stopped') else card['lane'], why=f'{frm} wrote again since {who} finished')
    # ...and WHY it has not started, which the lane word cannot say. "waiting to start" reads as a
    # queue that clears itself; every cause underneath it needs the owner instead (2026-09-14). The row says
    # which in a few words: "handed to coder, not started yet" sat on a task held for the owner, that
    # nothing would ever start (the owner, 2026-10-16) - held, failed and a real queue are three facts.
    idle = funnel.idle_state(store, card['tid']) if card.get('tid') and (card['lane'] == 'queued' or queued and card['lane'] in ('asked', 'yours')) else None
    if queued and card['lane'] in ('asked', 'yours'): card.update(lane='queued', why=(idle or {}).get('row') or 'not started yet')
    if card['lane'] == 'queued' and card.get('tid'):
        card['why_idle'] = idle['line']
        if not card.get('why') or funnel.held_for_repo(task): card['why'] = idle['row'] or 'not started yet'
        # ...unless an agent HAD it and is gone. That is not a queue that will clear itself, it is work
        # that stopped, and the owner is the only one who moves it: `stopped`, wearing the cause as its
        # word (the owner, 2026-09-17: "stopped should stay on stopped and shown to user to handle").
        # ...and a session YOU ended is `session saved`, not `agent stopped` (A1, 2026-09-25): its report is written
        if funnel.agent_left(store, card['tid']):
            card.update(lane='saved' if funnel.session_saved(store, card['tid']) else 'stopped', why=card['why_idle'])
    # HOW ITS LAST RUN ENDED, in the run's own word (workerstate.ended) - the reading the task list and the Board take (taskstate):
    # a run that failed or was stopped read "on you" here and one that finished "waiting to start", whatever the worker had said (G7)
    if tid and active and not workers and not persisted_working and not news and not review and card['lane'] in ('yours', 'queued'):
        from . import workerstate as ws
        end = ws.ended(store, tid)
        if end in ws.TERMINAL:
            last = store.last_worker_event(tid, kinds=ws.TERMINAL) or {}
            # a failure in plain words (funnel.run_failed): "connect a CLI agent or an AI provider ..." reached the row as it was
            said = ((funnel.run_failed(store, tid) or {}).get('sentence') if end == 'failed' else '') or ' '.join(str(last.get('Text') or '').split())
            said = said[:160]
            card.update(lane='saved' if funnel.session_saved(store, tid) else 'stopped',
                        why=f"{agent_word(task.get('Kind'))} {'failed' if end == 'failed' else 'stopped'}" + (f': {said}' if said else ''))
        elif end == 'finished':
            last = store.last_worker_event(tid, kinds=('finished',)) or {}
            said = ' '.join(str(last.get('Text') or '').split())[:160]
            # `finished`: what the move reads (funnel_presentation.move_of) - Mark done, not "who should take it?" (the owner, 2026-10-22)
            card.update(lane='yours', finished=True, why=f"{agent_word(task.get('Kind'))} finished" + (f': {said}' if said else ' - read what it found'))
    # THE LATEST ACTION IS THE STATUS (the owner, 2026-09-24). An agent parked or asking already spoke
    # for its task over a draft; one still WORKING did not, so a reply it wrote a minute into the session
    # read "reply ready" through forty more minutes of edits. Working is newer than any draft it made -
    # the reply is back the moment the agent parks or its session ends.
    if worker and active:
        agent_cards = funnel.from_agents(store, live_state=[worker], now=now)
        if agent_cards:
            # ...but where it came from stays the row's own: the agent card has no channel, and taking its blank
            # drew every row an agent picked up with a terminal instead of the Advisor, report or mail behind it
            card.update({k: v for k, v in agent_cards[0].items() if k != 'channel' or v})
        else:
            card.update(kind='agent', lane='working', working=worker.get('agent') or worker.get('label') or 'agent',
                        agent=worker.get('agent') or worker.get('label') or 'agent', sid=worker.get('sid'),
                        mode=worker.get('mode') or 'terminal', tail=worker.get('tail') or [],
                        why='An agent is working on this; nothing needs your input yet')
    elif (row.get('Working') or persisted_working) and active:          # ...a headless run too
        who = row.get('Working') or 'agent'
        card.update(kind='agent', lane='working', working=who, agent=who)
    elif active and not review:
        card = funnel.paused_conversation(store, card)
    # ...but the reply is still there behind the agent: closing from its card dismisses it, so the card
    # says so ("Close without sending") rather than losing it quietly
    if review and card.get('kind') == 'agent': card.update(rid=None, draft=False, reply_pending=True)
    # ...and what an agent already did on it, for the card's middle part (AgentDid) - the reply card had it, the agent's did not
    if card.get('kind') == 'agent' and not card.get('summary'): card['summary'] = funnel.agent_found(store, tid)
    # ...and an open task nobody closed comes BACK once it has been quiet, so clearing it is a
    # "not now", never a way to lose it. `queued` used to sit in the force-unread clause below, which
    # made a task handed to an agent the one row Done could not shift - the same question answered two
    # ways in one column (the owner, 2026-09-15: "why is that one showing up but not 575"). It clears
    # like the rest now, and the next walk brings it back (it was the quiet hours, task_return_minutes, until 2026-10-21). A Remind me date outranks it.
    # A LOOSE END (sweep.py): the daily check found this open task in no state that moves it - waiting on nobody named, or with
    # no date - and said so on the task's own row. It is the owner's move until the state is fixed, read live here, so a date or
    # a name put on it takes the line off at once; `lane_was` is what the check reads again tomorrow
    if active and not review and not worker and tid:
        from . import sweep
        loose = sweep.loose_on(store, view.get('ideas'), task, card, deferred=bool(read.get('deferred')), now=now,
                               mids=[m['MessageId'] for m in view.get('messages') or []])
        if loose: card.update(lane_was=card['lane'], lane='yours', why=loose['Text'], loose=True, loose_at=loose.get('LastSaid'))
    read_at = processing_all._stamp(read.get('read_at'))
    # ...read in an EARLIER walk: the walk that passed it is over, so it is the owner's again (this_walk) - an open task, whatever
    # its lane, a yes still owed and an agent waiting included: shown in the old chat is not answered
    back = bool(tid and active and not read.get('deferred') and read_at and not this_walk(read_at, walk_at))
    if back: card['why_open'] = 'Nothing has closed this since you last looked. If it is done, close it.'
    # A GOAL COMES BACK ON NEWS, never on the quiet hours (the review, 2026-10-12): a step closed or a day slipped since you
    # last read it is what puts it under Tasks; a quiet goal stays in For later however long it has been quiet
    if str(card.get('kind') or '').startswith('goal'):
        back = bool(card.get('news_at') and (not read_at or read_at <= processing_all._stamp(card['news_at'])))   # same second counts
        card.pop('why_open', None)
    # PASSED IS STILL YOURS (the owner, 2026-09-23: "i thought if you hit next it goes to passed section?"):
    # Next reads the row, and a read row used to leave the rail altogether until the hour brought it back -
    # an open task, a draft waiting for a yes, simply gone. Work that is still the owner's stays on the rail
    # for that hour, marked shown, which is what the Passed band draws; the walk does not offer it again.
    # NEXT only - the shown mark, below. Done is "off work for the hour" (2026-09-15) and stays gone.
    # ...a pass counts only for the state it passed (the owner, 2026-09-28: "If agent stopped working after a next it
    # should shoot up to your task category"). A Next pressed while the agent worked, or on its last question, read the
    # row - and when the agent stopped or asked again minutes later, that old receipt and mark filed the NEW stop straight
    # into Passed. An agent's row is back in Your task when its run spoke after the pass.
    since = _agent_spoke_at(store, tid) if card['lane'] in AGENT_STOPS else None
    passed = bool(tid and active and read_at and not read['unread'] and not read.get('deferred') and not back
                  and card['lane'] in OWNER_LANES and not (since and read_at < since))
    # AN AGENT FINISHED IT (same message: "same for finished agent task?"): a task its agent closed is a
    # result nobody has looked at yet. It is on the rail once, with Reports, until it is read; a task the
    # owner closed stays closed and gone.
    finished = _agent_finished(store, tid, active, review, processing_all._stamp(read.get('last_read_at')) or read_at, now)
    if finished:
        from .wrapup import no_one_behind
        card.update(kind='agentdone', lane='report', who=finished['who'], summary=finished['summary'], closed=True,
                    why='the agent finished and closed it - read what it found')
        # work the owner started here has nobody behind it to answer (a brief typed in the chat)
        if no_one_behind(row.get('Channel')): card['mid'] = None
        closed = False
        # ...and READ ONCE IS READ (the owner, 2026-09-24: "make the Next button skip reports that have
        # already been read"). The task unit's fingerprint carries its comments and artifacts, so anything
        # filed on the closed task after the read - a note, the reply going out - made it unread again and
        # Next offered the same finished result a second time. Whether the result was read after the close
        # is finished['unread']'s to say; a new MESSAGE on the task is still news and still brings it back.
        # ...THEIR message, not ours: the owner's reply to the result going out is a message on the task too,
        # and it brought the result they had just answered straight back to Next (the same ask, again)
        from .ingest import is_ours
        # ...and not one triage FILED as nothing new: a report that repeats every run joins the task it repeats
        # (same_as, fyi) and brought the finished result back after every run - read ten times (the owner, 2026-09-25)
        ours = {str(m['MessageId']) for m in view.get('messages') or [] if is_ours(m) or m.get('Status') == 'filed'}
        units = view.get('processing_read', {}).get('units', ())
        # ...nor an Advisor idea about it: the idea is the Advisor's own card, and one never opened kept a result the
        # owner had read on the rail for days (2026-09-25)
        read = read | {'unread': any(not u.get('read') for u in units if u.get('entity_kind') not in ('task', 'idea')
                                     and not (u.get('entity_kind') == 'message' and u.get('local_id') in ours))}
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
    # ...and stopped work is on the rail until it is looked at. It used to stay however often it was looked at, with
    # Later the only way to put it down - and Later is gone (R6, the owner, 2026-09-25: "next should move it to passed
    # and done should close it"). Next puts it in Passed like the rest of your work; the quiet hours bring it back.
    stopped = active and card['lane'] in ('stopped', 'saved') and not read.get('deferred') and (read_at is None or bool(since and read_at < since))
    # ...and Remind me puts away a live agent or a paused conversation too, until its day (R7, 2026-09-25)
    away = bool(reminded and remind.waiting(task, now)) and not asking_now
    # ...said since it was last read: on the rail until it is read, like news on the task (Next puts it down for the quiet hours)
    raised = bool(card.get('loose') and (read_at is None or read_at < (processing_all._stamp(card.get('loose_at')) or now)))
    unread = not closed and not receipt and bool((read['unread'] and not read.get('deferred')) or back or stopped or raised or (finished and finished['unread']) or
                                                 (active and not away and (worker or row.get('Working') or persisted_working or card.get('paused'))))
    # the arrow means triage moved it up: an idea or a task raised to "asked you", or an urgent ask
    card['promoted'] = bool(card.get('urgent_request')) or (card['lane'] == 'asked' and (card['kind'] == 'idea' or row.get('Channel') == 'assistant'))
    from . import processing_reads
    processing_reads.drawn(store, item['item_id'], item['view_revision'], view.get('processing_read', {}).get('units', ()))
    card.update(key='processing:' + item['item_id'], processing_id=item['item_id'],
                member_ids=list(item['member_ids']), context_revision=item['context_revision'],
                view_revision=item['view_revision'], aliases=names(item)[1:],
                unread=unread, deferred=bool(read.get('deferred')), defer_until=read.get('defer_until'),
                more=max(0, compact['counts'].get('messages', 0) - 1),
                source=row.get('SourceName') or compact['source'], status=row.get('MsgStatus') or compact['status'], order_band=funnel._band(card))
    # ...and on its day it says why it is back
    # ...said off the morning's note: remind.due clears the date as it files the note, so the date alone never said it (R13)
    due = any(c.get('Body') == remind.DUE_NOTE and str(c.get('CreatedAt') or '')[:10] == f'{now:%Y-%m-%d}' for c in view.get('comments') or [])
    if active and not read.get('deferred') and due: card['why'] = 'you asked to be reminded about this today'
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
    # with the receipt, so the row comes round again when the quiet hours bring it back.
    # ONE CLOCK FOR ALL OF THEM (the owner, 2026-09-23: "promote later after an hour or so unless it's
    # silenced until tomorrow"): an agent waiting on you and a reply ready kept a 30-minute cooldown of their own
    # and the mark for good, so the rail's Passed band and the walk disagreed about when they were back.
    # The mark is the timer now - this walk for an open task (2026-10-21), RETURN_MINUTES otherwise - and Remind me is the silence.
    card.pop('surfaced', None); card.pop('surfaced_at', None)
    shown = next((st for k in [card['key'], *card['aliases']] for st in [(states or {}).get(k)] if st and st.get('Status') == 'surfaced'), None)
    # ...and 'working': a task an agent is working is forced unread like these, and the walk takes it now (2026-10-21) - without
    # the mark Next would put the same working task straight back on the table
    if shown and card['lane'] in ('approve', 'blocked', 'queued', 'stopped', 'saved', 'working'):
        shown_at = processing_all._stamp(shown.get('At'))
        if since and shown_at and shown_at < since: shown = None                  # passed before the agent stopped
        # ...an open task's mark holds for this walk, a row with no task behind it for the quiet hours
        elif shown_at is None or (this_walk(shown_at, walk_at) if tid and active else shown_at > now - timedelta(minutes=quiet)):
            card.update(surfaced=True, surfaced_at=shown.get('At'))
    # AN OPEN TASK IS ALWAYS ON THE RAIL (the owner, 2026-09-29: "everything should be one driver from work rail to tasks
    # board"). Passed used to need the shown mark as well as the read, so any door that read a task without marking it - a
    # new walk clearing the marks, Done on a task it did not close - took open work off the rail for the quiet hours. The
    # task being open is what puts it here; the read only picks the band. Closing it or Remind me takes it off.
    if passed:
        unread = True
        card.update(unread=True, surfaced=True, surfaced_at=(shown or {}).get('At') or read.get('read_at'))
    # ...and WALKED PAST is not the same as shown: only a mark Next left (it carries when the row is back) or Remind me files it
    # under For later. A card merely put up, then another row clicked, stays where it was (the owner, 2026-10-08: "i had this
    # task open and then hit another task in work rail and it moved 1003 automatically to later?")
    mark = next((st for k in [card['key'], *card['aliases']] for st in [(states or {}).get(k)] if st and st.get('Status') == 'surfaced'), None)
    card['put_down'] = bool(card.get('surfaced') and mark and mark.get('Until'))
    # FOR LATER SAYS WHEN IT COMES BACK (the canvas redesign, 2026-09-29): the rail's gutter counts down to it - a row put away
    # with Remind me, on its date. An open task walked past has no time to say: it is back when this walk ends (this_walk); a
    # row with no task behind it, when its mark ages out.
    if card.get('deferred'): card['back_at'] = card.get('defer_until')
    elif card.get('put_down') and not (tid and active):
        base = read_at if passed else processing_all._stamp(card.get('surfaced_at'))
        if base: card['back_at'] = (base + timedelta(minutes=quiet)).strftime('%Y-%m-%d %H:%M:%S')
    if card['lane'] == 'fyi' and not card.get('sig'):
        summaries = [r for r in view.get('processing_summaries', [])
                     if r.get('ContextRevision') == item['context_revision'] and r.get('Summary')
                     and r.get('Key') in [card['key'], *card['aliases']]]
        if summaries:
            card['summary'] = next((r for r in summaries if r['Key'] == card['key']), summaries[-1])['Summary']
    # ...and the walk takes what the rail puts on you: a READ open task without a Next mark sits under Tasks, so `passed` alone
    # (any read - opening it from the rail is one) let the walk start on the second row (the owner, 2026-10-14: "it skipped the
    # first task again in walk through"). Only Next, Done or Remind me puts it down - shown-is-not-acted-on.
    done = any(st and st.get('Status') == 'done' for k in [card['key'], *card['aliases']] for st in [(states or {}).get(k)])
    card['actionable'] = bool(unread and not (passed and (card['put_down'] or done)) and not card['deferred'] and not card.get('settling')
                              and not funnel._not_yet(card))     # ...a task an agent is WORKING is walked like the rest (2026-10-21)
    card['arrived_at'] = arrived_at(store, card, task, view, allowed)
    return card


def arrived_at(store, card, task, view, allowed):
    """WHEN THE ROW ARRIVED, its place on the rail (funnel.order_key): its task's creation, else its idea's, else its first message.
    The card's own time is its NEWEST activity - the last mail on the thread, its agent's start or question - and ordering by it moved
    a row each time one of those happened (the owner, 2026-10-22: "set by time, oldest to newest and then never move")."""
    tid = card.get('tid')
    t = task if tid and task.get('TaskId') == tid else (store.get_task(tid) or {}) if tid else {}
    idea = next((i for i in view.get('ideas') or [] if i.get('IdeaId') == card.get('idea')), None) if card.get('idea') else None
    sent = [str(m['SentAt']) for m in view.get('messages') or [] if m.get('SentAt') and (not allowed or m.get('MessageId') in allowed)]
    # the earlier of the task's creation and its first message: triage makes a task a little after the mail that asked for it
    seen = [str(x) for x in (t.get('CreatedAt'), *((idea.get('CreatedAt') or idea.get('FirstSeen'),) if idea and not t else ()), *sent) if x]
    return min(seen, key=funnel_time) if seen else card.get('sort_at') or card.get('since') or card.get('when')


def funnel_time(stamp):
    from .funnel import _activity_time
    return _activity_time(stamp) or datetime.max


def on_rail(card) -> bool:
    """What the rail holds: the unread, a task put away with Remind me - still open work, in For later with its day
    (the canvas redesign, 2026-09-29) - and a goal, never gone while open (spec 2026-10-12); a goal's child folded into
    its row is not a row. ONE rule for the builder and for funnel.pile, the road the page is served - the builder alone
    kept put-away rows that pile() then dropped (the final review)."""
    if card.get('folded'): return False
    if str(card.get('kind') or '').startswith('goal') and card.get('tid') and not card.get('closed'): return True
    return bool(card.get('unread') or (card.get('deferred') and card.get('tid') and not card.get('closed')))


def build(store, *, now=None, live_state=None, include_read=False, only=None,
          full_history=False, keys=None):
    """`keys`: a LOOKUP, not a rail - only the items answering to one of these keys are compacted and carded (calendar
    and broken connections as ever). Looking up Current carded every root to keep one: ~300 ms in the window, ~3 s
    over the whole history (P4, 2026-10-12). The kept cards are the ones the whole build makes; counts are theirs."""
    from . import funnel, terminal
    now = now or datetime.now()
    keep = None if keys is None else (lambda item, want=frozenset(keys): not want.isdisjoint(names(item)))
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
                snapshot, query, include_excluded=include_read, degraded_ok=attempt == 2, keep=keep)
            break
        except processing_all.AllError as e:      # a write landed between the settle check and the snapshot: once more
            if attempt == 2 or e.detail.get('code') != 'processing_coverage_pending': raise
    by_id = {item['item_id']: item for item in snapshot['items']}
    states = store.funnel_states()
    quiet, walk_at = RETURN_MINUTES, walk_started_at(store)
    noise = _noise_hidden(store)
    cards = [card_for(store, by_id[row['item_id']], row, live_state, now, states, quiet, walk_at, noise) for row in rows]
    # ...and a task put away with Remind me stays on the rail, in For later, saying its day - it is still open work, and
    # the rail is where open work lives (2026-09-29). It is never actionable, so the walk does not offer it early.
    kept = on_rail
    # ...a goal's child told by the goal's row is not a row, read or unread (on_rail)
    cards = [card for card in cards if (include_read or kept(card)) and not card.get('ranked_wait') and not card.get('folded')]
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
        # ...but SHOWN is not walked past: the card on the table writes a bare shown mark, and the error left the rail while
        # it was being read (the owner, 2026-10-15) - only Next's put-down (its Until) dismisses it, as with every other row
        if st.get('Status') == 'surfaced' and st.get('Until') and not (st.get('Note') and st['Note'] != card.get('sig')): continue
        cards.append(card)
    cards = funnel._order(cards)
    return {'rev': snapshot['snapshot_revision'], 'items': cards, 'hidden': 0, 'muted': 0,
            'rules': [], 'canonical': True, 'coverage': coverage,
            'counts': {'all': counts['total'], 'unread': sum(c['unread'] for c in cards),
                       'actionable': sum(c['actionable'] for c in cards)},
            'lanes': [{'lane': lane, 'word': funnel.LANE_WORDS[lane][0], 'role': funnel.LANE_WORDS[lane][1],
                       'n': sum(c['lane'] == lane for c in cards)} for lane in funnel.LANES]}
