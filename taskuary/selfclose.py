"""The agent decides it is done, and the task closes itself.

Every finished coding session used to wait for a human to click Done. That click is pure
ceremony: by the time the CLI has stopped talking, the work is over, the transcript is on
screen and the owner is being asked to confirm something the agent already knows. Worse, the
click is what TRIGGERS the ending - the report, the proposals, the drafted reply - so a session
nobody got round to closing produced no record and no answer to the person who asked. The
sender waited on a button.

So the ending moves to where the knowledge is: the agent runs `taskuary --done "<one line>"` in its
own shell. Deterministic, free, and the agent says it in words - the seed prompt tells every session
to do this when it is finished (terminal.seed_text).

There used to be a second road: when the CLI's stop hook fired, a model JUDGED the quiet screen and
closed on "finished". It is gone (the owner, 2026-09-24): a guess read off a quiet screen is not an
ending. Only the agent saying so, or the owner's Mark done, ends a task - and the agent only on a task
that allows it: one the owner opened to work in (STAY_TAG) is theirs to complete (2026-09-25).

It lands in coder.wrap, which is exactly what the Done button calls. Nothing about the ending
is different because a machine started it: the same report, the same proposals, the same drafted
reply sitting on the task with the task tagged "reply pending". The owner still approves what goes
out - that is the part a person is genuinely needed for, and it is the only part left.

What keeps this honest is that closing is the WRONG move most of the time it is tempting. An
agent that stopped to ask a question has also "stopped talking". A pty parked at a prompt for
three seconds after printing a plan has stopped talking. Closing either one throws away a live
session and mails somebody a half-answer, so the gates below are deliberately mean even for an
agent that says done: the screen must not read as a question AND the session must have actually
done something AND no self-close may have run already. When they disagree, nothing happens and
the Done button is still there.
"""
import json, re, threading, time
from loguru import logger

SETTING = 'agent_self_close'      # '1' (default) on, '0' off. A legacy 'ask' reads as on (see mode)
# A task the owner opened to WORK IN, rather than to have worked FOR them. Set by claim() the
# moment the OWNER opens a session on a task - by ANY door: + New on the Timeline or the Board, a
# new task on the Tasks tab, Start session, Continue with coder, the Wall - and never by the
# router: a message that arrived has somebody waiting on an answer, so finishing it should close
# it and draft the reply, which is the whole point of the funnel.
#
# It used to be a checkbox on one dialog (+ New, "leave it open"), and every other door left the
# task unmarked: TQ-0285 (2026-09-02) was continued by hand from the task page, the agent ran
# `taskuary --done`, and the session the owner was sitting in closed under them - the second time
# on the same task. Who opened the session is a fact the server knows; it is not asked again.
#
# ONE rule (the owner, 2026-09-25): an agent may close its own task only when the task allows it.
# With the tag on, `declare` refuses - the agent's word is filed on the task, the session stays at
# its prompt, and the owner keeps completion. The seed (STAY_LINE) tells the agent exactly that.
STAY_TAG = 'stay:open'
MIN_AGE = 45.0                    # seconds a session must have lived before it may close itself
MIN_CHARS = 400                   # ...and printed. A session that produced nothing did nothing.
_DONE = set()                     # task ids a self-close has already run for, this process
_LOCK = threading.Lock()


def mode(store) -> str:
    """'on' | 'off'. There used to be three: 'auto' also let a judge close a quiet screen, 'ask' did not.
    The judge is gone (2026-09-24), so the two behaved the same and one is left; a stored 'ask' reads as on."""
    v = str(store.get_settings().get(SETTING, '1') or '1').strip().lower()
    return 'off' if v in ('0', 'off', 'false') else 'on'


def settle_legacy(store) -> bool:
    """A stored 'ask' becomes '1' once, so Settings' switch shows what the setting does. True when it moved."""
    if str(store.get_settings().get(SETTING) or '').strip().lower() != 'ask': return False
    store.set_setting(SETTING, '1', 'upgrade'); return True


# ── the gates ───────────────────────────────────────────────────────────────────────────
def blocked(store, tid: int, term=None) -> str:
    """'' when this task may close itself, else the reason it may not - which is written onto the
    task, because a self-close that silently declines is indistinguishable from one that is
    broken."""
    from . import waitroom, workerstate as ws
    if not tid: return 'no task'
    with _LOCK:
        if tid in _DONE: return 'a self-close already ran for this task'
    t = store.get_task(tid) or {}
    if not t: return 'no task'
    if t.get('Status') in ('done', 'dropped'): return 'the task is already closed'
    if term is not None:
        # a pending approval is the owner's decision to make, not the judge's (PW-234): the automatic
        # road must not close a run that is still waiting to be let through
        req = ws.asking_of(store, term)
        if req and req['kind'] == 'approval_needed': return f'a pending approval is open: {req["text"][:160]}'
        age = time.time() - (getattr(term, 'started_ts', 0) or 0)
        if getattr(term, 'started_ts', 0) and age < MIN_AGE: return f'the session is younger than {int(MIN_AGE)}s'
        if getattr(term, 'n', 0) < MIN_CHARS: return 'the session has barely printed anything'
        # the screen's own words beat any judge: a CLI parked at a question says so, in a
        # phrasing waitroom already knows how to spot
        if waitroom.looks_like_question(term.tail(waitroom.TAIL_LINES)):
            return 'the last lines read as a question for you'
    return ''


def unclaim(store, tid: int, actor: str = 'owner') -> None:
    """The owner closed the task they had opened a session on: the mark comes off, so a later close by
    a draft's verdict or by an agent is not refused for it."""
    t = store.get_task(tid)
    if not t or not stays_open(store, tid): return
    tags = [x.strip() for x in str(t.get('Tags') or '').replace(' ', ',').split(',') if x.strip() and x.strip() != STAY_TAG]
    store.update_task(tid, {'Tags': ','.join(tags)}, actor)


def claim(store, tid: int, actor: str = 'owner') -> bool:
    """The owner is opening a session on this task: mark it theirs to end. True when the mark was
    just set. A router/agent opening leaves the task as it is - that is the funnel's own work."""
    if actor != 'owner' or not tid or stays_open(store, tid): return False
    t = store.get_task(tid)
    if not t: return False
    tags = [x.strip() for x in str(t.get('Tags') or '').replace(' ', ',').split(',') if x.strip()]
    store.update_task(tid, {'Tags': ','.join(tags + [STAY_TAG])}, actor)
    store.audit('task', tid, 'stay_open', actor, detail={'why': 'the owner opened a session on it'})
    return True


def stays_open(store, tid: int) -> bool:
    """Did the owner open this one to sit in? Then its agent does not get to end it - the owner does.

    A session started from the Board or + New is a place the owner is working: an agent finishing a
    step is not the owner finishing the task, and closing it would drop them out of their own session
    with a reply drafted to nobody."""
    tags = str((store.get_task(tid) or {}).get('Tags') or '')
    return STAY_TAG in [t.strip() for t in tags.replace(',', ' ').split()]


def _mark(tid: int) -> bool:
    """True the first time only - two hooks firing in the same second must not both wrap."""
    with _LOCK:
        if tid in _DONE: return False
        _DONE.add(tid)
        return True


def forget(tid: int) -> None:
    """A task reopened by hand may close itself again."""
    with _LOCK: _DONE.discard(tid)


# ── the one road ────────────────────────────────────────────────────────────────────────
OWNER_ENDS = 'the owner opened this session, so they complete the task - your summary is filed on it for them'


def declare(store, tid: int, summary: str = '', agent: str = 'agent') -> dict:
    """The agent ran `taskuary --done`. It said so, so no judge is consulted - only the gates that stop
    a double close or a task already shut, and the task's own say. A `stay:open` task is the owner's
    to complete: the agent's sentence is filed as a comment and nothing closes (the owner, 2026-09-25 -
    the docs and the seed said the tag vetoed `--done` while this road closed anyway). Otherwise the
    sentence is filed before the wrap, so the report is written with the agent's own last word in the
    transcript rather than instead of it."""
    from . import terminal as term
    if mode(store) == 'off': return {'closed': False, 'why': 'self-closing is switched off in Settings'}
    why = blocked(store, tid, term.session_for(tid))
    # an explicit declaration outranks "it looks like a question": the agent just said otherwise
    if why and 'question' not in why: return {'closed': False, 'why': why}
    line = ' '.join(str(summary or '').split())[:1200]
    if stays_open(store, tid):
        store.add_comment(tid, agent, 'agent', f'The agent says it is finished: {line}' if line else 'The agent says it is finished.')
        return {'closed': False, 'why': OWNER_ENDS}
    if not _mark(tid): return {'closed': False, 'why': 'a self-close already ran for this task'}
    result = _finished(store, tid, term.session_for(tid), line)
    store.add_comment(tid, agent, 'agent',
                      f'The agent closed this itself: {line}' if line else 'The agent closed this itself.')
    return _wrap(store, tid, agent, 'the agent said it was finished' + (f' - {line}' if line else ''), result)


def _finished(store, tid: int, s, line: str) -> str:
    """The explicit result as an event (workerstate.py, PW-222/230). The RESULT is the agent's own last message -
    the Stop hook kept this run's last_assistant_message as its newest turn_end - and the `--done` sentence is
    the summary; only with nothing spoken does the sentence stand in. Finished does not close the task by
    itself: the wrap does that, on its own terms."""
    try:
        from . import workerstate as ws
        sid = getattr(s, 'sid', None) or ws.current_sid(store, tid) or 'cli'
        spoken = next((e['Text'] for e in reversed(ws.events(store, tid, sid)) if e['Kind'] == 'turn_end' and e['Text']), '')
        result = spoken or line
        ws.record(store, tid, sid, 'finished', text=result, source='cli')
        return result
    except Exception as e:
        logger.debug(f'finished event skipped: {e}'); return line


def _wrap(store, tid: int, agent: str, why: str, final_message: str = '') -> dict:
    """The same ending the Done button gets. A failure here must not take the hook (or the CLI)
    with it, and it must not leave the task looking closed when it is not - so the mark is
    dropped and the reason is written where the owner reads it."""
    from . import coder
    from .store import task_ref
    try:
        out = coder.wrap(store, tid, close=True, actor=agent or 'coder', final_message=final_message)
    except Exception as e:
        forget(tid)
        logger.warning(f'self-close failed for task {tid}: {e}')
        store.add_comment(tid, 'router', 'agent',
                          f'The agent tried to close this itself and could not ({str(e)[:200]}) - '
                          'the Done button on the task still works.')
        return {'closed': False, 'why': str(e)[:200]}
    store.audit('task', tid, 'self_close', agent or 'coder', 'agent', {'why': why[:300], 'drafting': out.get('drafting')})
    logger.info(f'{task_ref(tid)} closed itself - {why[:120]}'
                + (' (reply drafted)' if out.get('drafting') else ''))
    return {'closed': True, 'drafting': bool(out.get('drafting')), 'why': why, **out}


# ── what the session is told ────────────────────────────────────────────────────────────
# The explicit road only exists if the agent knows about it, so this rides in every seed prompt.
# It is phrased as the CHEAP ending, because that is what it is: the alternative is a human
# looking at a screen hours later.
# Short on purpose. Every character here rides on a command line that a canonical tty caps at
# 1024 bytes, so the WHOLE rule lives in CODER.md (which rides in as RULES) and this is only the
# part that must survive a blanked document: the command, and what pressing it does.
SEED_LINE = ('REPLY: save the answer for the person who asked with `taskuary --reply "<text>"` - the owner approves it. '
             'WHEN FINISHED: run `taskuary --done "<one sentence>"` - it closes the task and drafts the reply unless you saved one.')
# ...and its opposite, for a session the owner opened to sit in (stays_open): the one thing the
# agent must NOT do is end it. Said in the prompt, because CODER.md's finishing rules say the
# reverse and an agent reading both without this line picks the one with a command in it. It says
# what `declare` does: the command is refused here and the owner completes the task.
STAY_LINE = ('THE OWNER OPENED THIS SESSION: they complete this task, not you - `taskuary --done` is refused here. '
             'Summarize finished work and wait.')


# ── the general chat's version of the same thing ────────────────────────────────────────
# A conversational agent has no shell to run a command in, and half the time no CLI behind it at
# all, so it says it in the reply instead. A marker, not a judge: a chat is a conversation and
# most turns in one are not endings - guessing here would close tasks out from under someone
# mid-thought.
MARKER = '[[TASKUARY-DONE]]'
_MARK_RE = re.compile(r'\[\[\s*TASKUARY[-_ ]?DONE\s*\]\]\s*:?\s*(.*)', re.I)

CHAT_LINE = (
    f'ENDING THE TASK: when the work this task asked for is COMPLETE and you need nothing further '
    f'from the owner, end your reply with a final line: {MARKER} <one sentence on what you did or '
    f'found>. That closes the task and drafts the answer the person who asked will get - the owner '
    f'approves it before it leaves. Only on a real ending. Never write it when you have asked a '
    f'question, offered options, or still need something; a conversation that is still going is '
    f'not an ending, and neither is an answer the owner may want to push back on.')


# ...and its reply. The chat writes the answer the sender gets inside a marked block; the words between
# the markers become the task's pending reply as written (coder.agent_reply) and stay in the chat too.
REPLY_OPEN, REPLY_CLOSE = '[[TASKUARY-REPLY]]', '[[/TASKUARY-REPLY]]'
_REPLY_RE = re.compile(r'\[\[\s*TASKUARY[-_ ]?REPLY\s*\]\](.*?)\[\[\s*/\s*TASKUARY[-_ ]?REPLY\s*\]\]', re.I | re.S)
REPLY_LINE = (f'REPLYING FOR THE OWNER: when you write the answer the person who asked will get, put exactly that '
              f'text between {REPLY_OPEN} and {REPLY_CLOSE}. It becomes the reply waiting on the owner\'s approval, '
              f'in your words - nothing is sent until they approve it.')


def reply_marker(text: str) -> tuple:
    """(reply with the markers taken out, the marked reply text) - or (text, None) when it wrote none."""
    m = _REPLY_RE.search(text or '')
    if not m: return text, None
    said = m.group(1).strip()
    return (text[:m.start()] + said + text[m.end():]).strip(), said or None


def chat_marker(text: str) -> tuple:
    """(cleaned reply, the agent's closing sentence) - or (text, None) when it did not say so."""
    m = _MARK_RE.search(text or '')
    if not m: return text, None
    return (text[:m.start()].rstrip(), ' '.join((m.group(1) or '').split())[:600])


# ── ...and its question (PW-225) ────────────────────────────────────────────────────────
# A regular worker has no AskUserQuestion tool and no hook: when it cannot go on without the owner it says
# so with a marker, and Taskuary records the exact question as an Input-needed request - the one the
# owner's answer is bound to (workerstate.answer). A marker, again, not a judge reading prose for a '?'.
ASK_MARKER = '[[TASKUARY-ASK]]'
_ASK_RE = re.compile(r'\[\[\s*TASKUARY[-_ ]?ASK\s*\]\]\s*:?\s*(.*)', re.I | re.S)
ASK_LINE = (f'ASKING THE OWNER: when you cannot continue without their answer, end your reply with a final line: '
            f'{ASK_MARKER} <the exact question> | <choice> | <choice> (choices optional). Taskuary shows it as a question '
            f'waiting for them and brings their answer back to you. Only for a real blocker, never for a rhetorical question.')


def without_ask(text: str) -> str:
    """The marker taken out of anything the owner READS. It was stripped from the filed reply and
    nowhere else, so a CLI that put its question in a progress line printed Taskuary's own plumbing
    into the middle of the agent's thinking - `[[TASKUARY-ASK]] Have you signed in? | Signed in |
    Login failed`, verbatim, on screen (2026-09-15). The question itself is shown as a question."""
    return _ASK_RE.sub('', str(text or '')).rstrip()


def ask_marker(text: str) -> tuple:
    """(cleaned reply, question, choices) - or (text, None, []) when the reply asks nothing structurally."""
    m = _ASK_RE.search(text or '')
    if not m: return text, None, []
    parts = [' '.join(p.split()) for p in m.group(1).split('|')]
    return text[:m.start()].rstrip(), (parts[0][:600] or None), [p[:120] for p in parts[1:] if p]
