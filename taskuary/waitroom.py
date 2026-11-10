"""The waiting room: what the owner thinks of WHILE an agent is working, held until it stops.

Ideas arrive mid-run - "also handle the null case", "rename that flag", "check the other repo" -
and both ways of giving them to a coding agent were bad: interrupt it (an agent mid-edit loses
its thread; "LLMs Get Lost in Multi-Turn Conversation" puts the turn-splitting tax at ~-39%,
almost all of it unreliability), or hold them in your head and retype them when it finally
stops. So they queue HERE, on the task, and are typed into the session as ONE batch at the next
boundary: the agent parked at its prompt (terminal silent for IDLE_WAITING seconds - the same
fact the Board reads as "waiting on you"). When it parked because it ASKED something, the words the
owner writes next are its ANSWER and go in at once, plainly: waiting behind the question meant
they never arrived, and the agent sat on a question the owner had already answered on screen.

A session that has ENDED with notes still waiting (headless run finished, TUI closed) reopens
one on the same task with the notes as the ask - same task, fresh agent, never a chained session.
Affinity's cousin: dispatchq queues TASKS behind an agent; the waiting room queues WORDS for one.
"""
import re, threading, time
from loguru import logger
from .store import task_ref

TAIL_LINES = 6
WATCH_EVERY = 10          # seconds between looks - delivery lands within IDLE_WAITING + this of the agent parking
MAX_BATCH = 6000          # chars typed in one go; a TUI paste past this is asking for dropped frames


# A NOTE THE ASSISTANT PASSED ON keeps the owner's own words and what the Assistant added, apart (general.relayed): one row, so the drip
# never splits them across two stops
SEP = '\x1f'
TEAMMATE = 'teammate'           # CreatedBy of a teammate's line from a bound chat: never the owner's, never an answer
def parts(note) -> tuple:
    "(the owner's words, what the Assistant added - '' when nothing)"
    o, _, extra = str(note or '').partition(SEP)
    return o.strip(), extra.strip()
def said(note) -> str:
    "A note as one line for the agent: the owner's words, then what the Assistant added."
    o, extra = parts(note)
    return f'{o} ({extra})' if extra else o


def batch(notes: list, after_restart: bool = False, remaining: int = 0, words: bool = True) -> str:
    """The notes as one typed message. Flattened to one line: in a TUI a newline is Enter.
    `remaining` = notes still waiting behind these (the drip): the agent is told the next one
    comes when it stops again, so it does not go looking for it. `words=False`: Taskuary's part alone, the notes left out."""
    n = len(notes)
    # ...a message relayed from someone else (terminal.say_to_task, CreatedBy 'router') is not the owner's note: it names its own sender
    # ...and a teammate's words on a bound chat (agentchannels.py) are never "the owner's" - each one names its writer and its guard
    by = {x.get('CreatedBy') or 'owner' for x in notes}
    who = 'Taskuary' if 'router' in by else ('a teammate' if by == {TEAMMATE} else 'the owner and a teammate') if TEAMMATE in by else 'the owner'
    head = (f'{who[0].upper() + who[1:]} left {n} note{"s" if n > 1 else ""} for you after the last session ended. Take them in order:'
            if after_restart else
            f'While you were working, {who} queued {n} note{"s" if n > 1 else ""} for you. Take them in order, '
            'after finishing the step you are on; if one conflicts with work already done, say so instead of undoing it:')
    tail = (f' ({remaining} more note{"s" if remaining > 1 else ""} wait{"" if remaining > 1 else "s"} behind this one - the next comes when you stop again; '
            'finish this and stop, do not ask for it.)' if remaining else '')
    each = ' '.join(f'({i}) {said(x.get("Note"))}' for i, x in enumerate(notes, 1)) if words else ''
    extra = '' if words else ' '.join(f'{general_relay()} ({i}) {e}' for i, x in enumerate(notes, 1) if (e := parts(x.get('Note'))[1]))
    return ' '.join((head + ' ' + each + extra + tail).split())[:MAX_BATCH]


def general_relay() -> str:
    from .general import RELAY
    return RELAY


# A GENERAL AGENT'S CHAT SAYS WHO SAID WHAT (the overnight run, 2026-11-03): the batch typed into its conversation was filed whole as the
# owner's, so YOU read "While you were working, the owner queued 1 note for you. Take them in order..." - Taskuary's words in the owner's
# bubble. Taskuary's part is its brief (the grey line), each note its writer's own words, and the agent's turn is the batch, as it was
def to_general(store, tid, session, notes: list, after_restart: bool = False, remaining: int = 0) -> None:
    from . import general
    store.add_comment(tid, general.BRIEF_ACTOR, general.USER_TYPE, batch(notes, after_restart, remaining, words=False))
    for x in notes:
        store.add_comment(tid, 'owner' if (x.get('CreatedBy') or 'owner') not in ('router', TEAMMATE) else general.BRIEF_ACTOR, general.USER_TYPE,
                          parts(x.get('Note'))[0])
    threading.Thread(target=session.send_prompt, args=(batch(notes, after_restart, remaining),), kwargs={'kept': True, 'brief': True},
                     daemon=True).start()


def drip(store) -> bool:
    """One note per stop (the default) or everything queued at once. Twenty prompts pasted as a
    funnel want a drip: each lands as its own turn, with the agent's full attention, in order."""
    return store.get_setting('waitroom_drip', '1') == '1'


_ITEM = re.compile(r'^\s*(?:[-*•]|\d+[.)])\s*')

def split_many(text: str) -> list:
    """A pasted list into notes: one per line, bullets and numbering stripped, blanks dropped. A
    line that is only a continuation (starts with whitespace and the previous exists) joins it."""
    out = []
    for raw in (text or '').splitlines():
        if not raw.strip(): continue
        if raw[:1].isspace() and out and not _ITEM.match(raw): out[-1] = f'{out[-1]} {raw.strip()}'; continue
        out.append(_ITEM.sub('', raw).strip())
    return [o for o in out if o]


def add_many(store, tid: int, text: str, actor: str = 'owner') -> dict:
    """A whole funnel at once: every line becomes its own note, in order; delivery decides the pace."""
    items = split_many(text)
    if not items: raise ValueError('nothing to queue')
    if not store.get_task(tid): raise ValueError(f'no task {tid}')
    for it in items: store.add_waiting(tid, it, actor)
    store.audit('task', tid, 'waitroom_add_many', actor, detail={'n': len(items)})
    return {'queued': len(items), **deliver(store, tid)}


def _screen(t) -> list:
    """The RENDERED tail where the session has one - a TUI's chooser is drawn in place and the raw
    stream keeps the frames that went before it - else the raw tail the small test doubles carry."""
    try: return t.status_tail(TAIL_LINES)
    except (AttributeError, TypeError): return t.tail(TAIL_LINES)


def state(store, tid: int) -> tuple:
    """('working'|'asking'|'parked'|'no_session', live Term or None) - where the agent on this
    task stands right now: the run's own word first (an open request), then the rendered screen.

    Read off the RAW tail, Claude's first-run trust dialog and its AskUserQuestion chooser both
    read `parked`, and the next queued note was typed straight into them - Enter on "No, exit"
    ended the session, the notes left behind reopened it, and the loop ran until the folder was
    trusted by hand (measured 2026-09-20)."""
    from . import terminal as term, workerstate as ws
    t = next((x for x in list(term.SESSIONS.values()) if x.task_id == tid and x.alive), None)
    if t is None:
        return ('working', None) if any(r.get('TaskId') == tid for r in store.running_runs()) else ('no_session', None)
    # A HELD ASK IS ASKING, WHATEVER THE SCREEN SAYS (B11, the owner, 2026-10-11): while hooks.ask holds a question
    # Claude keeps its spinner up, so the screen read `working` and the owner's typed answer queued until the 540 s
    # hold ran out - then went in as keystrokes on a form. The hold is waiting on exactly these words.
    if ws.held_for(tid):
        try: req = ws.asking_of(store, t)
        except Exception: req = None
        if req and ws.group_of(req['request_id']) in ws.held_for(tid): return 'asking', t
    parked = t.waiting() if hasattr(t, 'waiting') else term.waiting_of(t)
    if not parked: return 'working', t
    try: req = ws.asking_of(store, t)
    except Exception: req = None
    # A STALL IS NOT A QUESTION (A13, the owner, 2026-09-25): a rate limit or an API error left the CLI at its prompt
    # with a `stalled` request open, and a note was typed into it as if it had been asked - and marked the stall
    # answered. Nothing can be answered through a rate limit; the note waits until the limit lifts.
    if (req or {}).get('kind') == 'stalled': return 'working', t
    # ASKING = the run's own word (a hook's question, a [[TASKUARY-ASK]], the model's read of its last message - hooks.
    # judge_turn) or the CLI's own chooser chrome on screen. The words on the tail used to decide it (`looks_like_question`:
    # "?" at a line's end, "should i", "do you want") - so a report closing on a rhetorical question took the next note as
    # its ANSWER (the owner, 2026-10-11: "everything should be ai"). Parked without either is parked: the note is typed.
    return ('asking' if req or term.chooser_in(_screen(t)) else 'parked'), t


def add(store, tid: int, note: str, actor: str = 'owner', owner: str = None) -> dict:
    """Queue one note on a task. An agent already parked gets it at once; otherwise it waits."""
    note = (note or '').strip()
    if not note: raise ValueError('empty note')
    from .general import relayed
    if (extra := relayed(owner, note)): note = f"{' '.join(str(owner).split())}{SEP}{extra}"     # the owner's words kept as typed
    if not store.get_task(tid): raise ValueError(f'no task {tid}')
    wid = store.add_waiting(tid, note, actor)
    store.audit('task', tid, 'waitroom_add', actor, detail={'wid': wid, 'chars': len(note)})
    # The note is QUEUED the moment it is written; handing it over may not be possible right now
    # (no CLI on this machine, no provider, every slot taken). That is not a failure of the note -
    # it used to come back as a 422 with the note already in the room (2026-09-03).
    try: return {'wid': wid, **deliver(store, tid)}
    except Exception as e:
        logger.warning(f'waitroom: {task_ref(tid)} kept the note but could not hand it over - {e}')
        return {'wid': wid, 'delivered': 0, 'state': 'held', 'why': str(e)[:200]}


HELD_STRANGER = ("Notes are waiting: someone you have not vouched for wrote on this task since its agent started with full tools, so nothing "
                 "is typed into it. Continue picks the work up under the reviewer, or Trust them.")


def full_on_stranger(store, tid: int, t) -> bool:
    """Whether the live session `t` runs full while the task is now a stranger's (origin.of_task, worst wins)."""
    from . import origin
    try: return getattr(t, 'mode', 'full') != 'auto' and origin.of_task(store, tid)[0] == 'stranger'
    except Exception: return True


_DELIVERING, _DLOCK = {}, threading.Lock()


def deliver(store, tid: int) -> dict:
    """Hand this task's waiting notes over IF the agent has stopped. {'delivered': n, 'state': ...}
    - 'held' states are the ones where nothing moved: working, asking, closed, full, owner_typing."""
    # ONE NOTE, ONE HANDOVER (2026-11-09): the owner's POST steered a line in, and before it marked the line handed over (a slow store:
    # 4 s) the turn ended and the clock's deliver read it as still waiting - the chat drew it twice. A task's deliveries take turns.
    with _DLOCK: lk = _DELIVERING.setdefault(tid, threading.RLock())
    with lk: return _deliver(store, tid)


def _deliver(store, tid: int) -> dict:
    from . import terminal as term, peers
    from .ingest import has_room
    pending = store.waiting_notes(tid)
    if not pending: return {'delivered': 0, 'state': state(store, tid)[0]}
    st, t = state(store, tid)
    # the drip: one note per stop, the rest keep their place in line
    notes = pending[:1] if drip(store) else pending
    left = len(pending) - len(notes)
    # MID-TURN, INTO THE TURN (the owner, 2026-11-06): an ACP coding session whose adapter steers (acpcoding.steerable) takes the words now,
    # into the turn at work, rather than at its end - the parked road below, under every one of its holds
    steer = st == 'working' and t is not None and term.is_acp(t) and bool(getattr(t, 'steerable', lambda: False)())
    # A STRANGER'S WORDS NEVER REACH FULL TOOLS UNASKED (the Advisor design rev 2): a session started full on a task a stranger has written on
    # since - a batch's outside contributor among them - gets nothing typed in; the owner's Continue picks it up under the reviewer
    if (st in ('asking', 'parked') or steer) and full_on_stranger(store, tid, t):
        why = HELD_STRANGER
        last = next((c for c in reversed(store.list_comments(tid)) if c.get('Actor') == 'router'), None)
        if (last or {}).get('Body') != why: store.add_comment(tid, 'router', 'agent', why)
        return {'delivered': 0, 'state': 'held_stranger', 'why': why, 'left': len(pending)}
    # NEVER INTO THE OWNER'S HALF-TYPED WORDS (2026-11-02): the owner typed in the box while the agent worked, it stopped, and the note
    # went in mid-sentence - one garbled prompt, their words split around it. It keeps its place; the next tick looks again.
    if (st in ('asking', 'parked') or steer) and term.owner_drafting(t):
        return {'delivered': 0, 'state': 'owner_typing', 'left': len(pending)}
    # A TEAMMATE NEVER ANSWERS WHAT THE AGENT ASKED THE OWNER (agentchannels.py): their line waits for its next plain stop, and the owner's
    # own answer - the card, the box, their reply on the channel - is what lets the question go
    if st == 'asking' and any((x.get('CreatedBy') or '') == TEAMMATE for x in notes):
        return {'delivered': 0, 'state': 'held_teammate', 'left': len(pending)}
    if st == 'asking':
        # An agent parked on a QUESTION is asking the OWNER, so the words they write next are the
        # ANSWER to it: bound to its open request where the worker reported one, typed in plainly
        # where it did not. They used to queue behind the question and never arrive at all - the card
        # said "Told the agent" over a session still parked on its own words (2026-09-07 live check).
        from . import workerstate as ws
        own, extra = parts(notes[0]['Note']) if len(notes) == 1 else ('', '')
        text = (extra or own) if len(notes) == 1 else batch(notes, remaining=left)
        who = notes[0].get('CreatedBy') or 'owner'
        out = ws.answer_open(store, tid, text, who, owner=own if extra else None)
        # ...words that name none of a chooser's options are not typed into it: Enter would submit whatever is
        # highlighted (B12). The note keeps its place and the owner is told why; it waits for the chooser to go.
        if out.get('state') == 'not_a_choice':
            return {'delivered': 0, 'state': 'not_a_choice', 'why': out.get('why') or '', 'left': len(pending)}
        if not out.get('delivered'):
            term.type_into(t, text, **ws._as(who))
            store.add_comment(tid, who, 'human', f'Answered the agent: {text[:500]}')
        store.deliver_waiting([x['WId'] for x in notes], 'answered')
        store.audit('task', tid, 'waitroom_deliver', 'router', 'agent', {'n': len(notes), 'how': 'answered', 'left': left})
        return {'delivered': len(notes), 'state': 'answered', 'left': left}
    if st == 'parked' or steer:
        from . import general
        if isinstance(t, general.GeneralSession): to_general(store, tid, t, notes, remaining=left); how = 'typed into'
        # ...an ACP coding session (acpcoding.py) takes it as its next prompt, the batch as Taskuary's brief and each of the owner's own notes
        # drawn as theirs in the coding chat - never "While you were working, the owner queued..." in the owner's bubble (to_general's rule)
        elif term.is_acp(t):
            t.prompt(' '.join(x for x in (peers.take(store, tid), batch(notes, remaining=left)) if x),
                     shown=[parts(x.get('Note'))[0] for x in notes if (x.get('CreatedBy') or 'owner') not in ('router', TEAMMATE)])
            how = 'sent into the running turn of' if steer else 'sent to'
        # ...with what other agents said since its last turn in front, framed as theirs (peers.py) - one turn, not two
        else:
            said_ = ' '.join(x for x in (peers.take(store, tid), batch(notes, remaining=left)) if x)
            # ...Taskuary's own notes alone (an approval's result, a landing) are its brief in the record, never the owner's line: kept as a
            # seed (sessionrecord.mark_briefs); a batch carrying the owner's notes is split there into their lines and Taskuary's head
            if all((x.get('CreatedBy') or 'owner') == 'router' for x in notes):
                from . import sessionrecord
                sessionrecord.keep_seed(tid, said_)
            how = term.tell(t, said_)
        store.deliver_waiting([x['WId'] for x in notes], 'typed')
        store.add_comment(tid, 'router', 'agent', f'{len(notes)} waiting-room note(s) {how} the live session'
                          + (' while the agent worked.' if steer else ' once the agent stopped.')
                          + (f' {left} still waiting for its next stop.' if left else ''))
        store.audit('task', tid, 'waitroom_deliver', 'router', 'agent', {'n': len(notes), 'how': 'typed', 'left': left})
        return {'delivered': len(notes), 'state': 'steered' if steer else 'parked', 'left': left}
    if st == 'no_session':
        task = store.get_task(tid) or {}
        if task.get('Status') not in ('open', 'in_progress'): return {'delivered': 0, 'state': 'closed'}
        if not has_room(store): return {'delivered': 0, 'state': 'full'}
        # ...a coding session that IDLED OUT (acpcoding.idle_out) comes back as the same run on its own conversation, and the notes are its
        # next prompt - to the owner nothing stopped
        from . import acpcoding
        if (woke := acpcoding.wake(store, tid)): return deliver(store, tid) if term.is_acp(woke) else {'delivered': 0, 'state': 'working'}
        # General work reopens in its connector-backed conversation. Coding work still reopens
        # the configured CLI. The waiting room therefore feeds the same underlying session no
        # matter which of its two renderers (assistant or terminal) the owner happens to prefer.
        from . import general
        if general.handles(task):
            if not general.provider_options(store): return {'delivered': 0, 'state': 'no_provider'}
            to_general(store, tid, general.start_session(store, tid, actor='router'), notes, after_restart=True, remaining=left)
            how = 'assistant'
        else:
            from . import agents as hub_agents
            previous = store.last_transcript(tid) or {}
            agent = previous.get('Agent') or hub_agents.default_agent(store)
            # Reopening a task is continuity, not a new dispatch decision: keep the profile and
            # checkout that already know this work. A missing old profile is allowed to fail
            # visibly rather than silently handing private context to a different configured CLI.
            term.start_on_task(store, tid, agent, instruction=batch(notes, after_restart=True, remaining=left),
                               actor='router', cwd=previous.get('Cwd') or None)
            how = 'seeded'
        store.deliver_waiting([x['WId'] for x in notes], 'seeded')
        store.add_comment(tid, 'router', 'agent', f'Reopened a session for {len(notes)} waiting-room note(s) - the previous one had ended.'
                          + (f' {left} still waiting for its next stop.' if left else ''))
        store.audit('task', tid, 'waitroom_deliver', 'router', 'agent', {'n': len(notes), 'how': how, 'left': left})
        return {'delivered': len(notes), 'state': 'restarted', 'left': left}
    return {'delivered': 0, 'state': st}


def tick(store) -> int:
    """Every task with notes waiting: deliver where its agent has stopped."""
    # The same clock also backs chat hand-raises. It must look at every session, not only tasks
    # with queued notes, and it is separate so note delivery remains deterministic.
    from . import general, handraise
    from . import acpcoding
    for sweep in (general.idle_sweep, acpcoding.idle_sweep):    # a chat or ACP coding agent idle past its period closes quietly (idle_out)
        try: sweep()
        except Exception as e: logger.warning(f'idle sweep failed: {e}')
    try: handraise.tick(store)
    except Exception as e: logger.warning(f'hand raise tick failed: {e}')
    n = 0
    for tid in store.tasks_with_waiting():
        try: n += deliver(store, tid)['delivered']
        except Exception as e: logger.warning(f'waiting room: {task_ref(tid)}: {e}')
    from . import peers                        # ...and the notes agents left each other, on the same clock (peers.py)
    try: n += peers.tick(store)
    except Exception as e: logger.warning(f'peer notes tick failed: {e}')
    return n


def watch(store):
    """The clock. Silence is the signal, and only a clock can notice silence."""
    def loop():
        while True:
            time.sleep(WATCH_EVERY)
            try: tick(store)
            except Exception as e: logger.warning(f'waiting room tick failed: {e}')
    threading.Thread(target=loop, daemon=True).start()


def later(store, delay: float = 3.0):
    """Look shortly - called from a dying session's own pump thread, which must not host the
    next session's startup."""
    tm = threading.Timer(delay, lambda: _safe(store))
    tm.daemon = True
    tm.start()

def _safe(store):
    try: tick(store)
    except Exception as e: logger.warning(f'waiting room tick failed: {e}')
