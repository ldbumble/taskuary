"""The agent decides it is done, and the task closes itself.

Every finished coding session used to wait for a human to click Done. That click is pure
ceremony: by the time the CLI has stopped talking, the work is over, the transcript is on
screen and the owner is being asked to confirm something the agent already knows. Worse, the
click is what TRIGGERS the ending - the report, the proposals, the drafted reply - so a session
nobody got round to closing produced no record and no answer to the person who asked. The
sender waited on a button.

So the ending moves to where the knowledge is. Two roads in, deliberately different:

- EXPLICIT: the agent runs `taskuary --done "<one line>"` in its own shell. Deterministic, free,
  and the agent says it in words - the seed prompt tells every session to do this when it is
  finished (terminal.seed_text). This is the road we want taken.
- AUTOMATIC: the CLI's own stop hook fires (hooks.receive on Claude Code's `Stop`), and the last
  thing the agent said is JUDGED - did this run end finished, or end waiting? Codex has no stop
  hook, so its sessions fall back to a settle check on the same judge.

Both land in coder.wrap, which is exactly what the Done button calls. Nothing about the ending
is different because a machine started it: the same report, the same proposals, the same drafted
reply sitting in Review with the task tagged "reply pending". The owner still approves what goes
out - that is the part a person is genuinely needed for, and it is the only part left.

What keeps this honest is that closing is the WRONG move most of the time it is tempting. An
agent that stopped to ask a question has also "stopped talking". A pty parked at a prompt for
three seconds after printing a plan has stopped talking. Closing either one throws away a live
session and mails somebody a half-answer, so the gates below are deliberately mean: the judge
must say finished AND the screen must not read as a question AND the session must have actually
done something AND no self-close may have run already. When they disagree, nothing happens and
the Done button is still there.
"""
import json, re, threading, time
from loguru import logger

SETTING = 'agent_self_close'      # '1' (default) auto, 'ask' explicit-only, '0' off
# A task the owner opened to WORK IN, rather than to have worked FOR them. Set when they start a
# coding session from + New with "leave it open" ticked (website/src/newTask.js), and never by the
# router - a message that arrived has somebody waiting on an answer, so finishing it should close
# it and draft the reply, which is the whole point of the funnel.
#
# deliberately NOT checked in blocked(): declare() calls that, and `taskuary --done` must still
# close a stay-open task. The agent SAYING it is finished outranks the tag; only the JUDGE - which
# guesses from a screen that has gone quiet - is refused.
STAY_TAG = 'stay:open'
MIN_AGE = 45.0                    # seconds a session must have lived before it may close itself
MIN_CHARS = 400                   # ...and printed. A session that produced nothing did nothing.
JUDGE_TAIL = 6000                 # how much of the end of the transcript the judge reads
_DONE = set()                     # task ids a self-close has already run for, this process
_LOCK = threading.Lock()


def mode(store) -> str:
    """'auto' | 'ask' | 'off'. 'ask' is the middle setting people actually want when they are
    still learning to trust it: an agent that SAYS it is done closes the task, and one that
    merely stops talking does not."""
    v = str(store.get_settings().get(SETTING, '1') or '1').strip().lower()
    return 'off' if v in ('0', 'off', 'false') else 'ask' if v == 'ask' else 'auto'


# ── the judge ───────────────────────────────────────────────────────────────────────────
# It reads the END of a transcript, which is where "I'm done" and "which of these do you want?"
# both live, and they are the two answers that matter. Everything else is 'working' - the safe
# verdict, because being wrong about 'working' costs a Done click and being wrong about
# 'finished' mails a stranger half an answer.
JUDGE_SYSTEM = (
    'You are reading the last part of a coding agent\'s terminal session. The agent has stopped '
    'printing. Decide ONE thing: is this run OVER, or is it waiting on the owner?\n'
    'Answer JSON only: {"state": "finished|asking|working", "why": "<one short sentence quoting '
    'what told you>"}.\n'
    'finished = the agent has said, in its own words, that the work is complete - it fixed it, or '
    'it looked and there was nothing to fix, or it produced what was asked for - and it is not '
    'waiting for anything from the owner. A summary of what it did with no open question is '
    'finished.\n'
    'asking = the last thing on screen wants something from the owner: a question, a choice '
    'between options, a permission request, a "let me know", a blocked step. Anything the owner '
    'must answer before the agent can go on. When in the slightest doubt between finished and '
    'asking, say asking.\n'
    'working = the run is mid-flight, or it crashed, or the screen simply does not say - it '
    'printed a plan, a partial edit, an error it has not addressed. Say working whenever the '
    'screen does not clearly say one of the other two.\n'
    'You are deciding whether to END a live session and MAIL somebody the result. Guessing '
    'finished when it is not is the expensive mistake; guessing working costs one click.')


def judge(store, text: str, said: str = '') -> dict:
    """{'state', 'why'} for the tail of a transcript. No AI configured means no automatic
    closing at all - a keyword scan is not allowed to end sessions and mail people."""
    from .llm import build_llm
    tail = (text or '')[-JUDGE_TAIL:]
    if not tail.strip(): return {'state': 'working', 'why': 'nothing on screen'}
    try:
        llm = build_llm(store)
        if not llm: return {'state': 'working', 'why': 'no AI is configured to judge the ending'}
        body = (f'The last thing the agent said:\n{said.strip()[:2000]}\n\n' if said.strip() else '') + f'Screen:\n{tail}'
        j = json.loads(re.sub(r'^```(json)?|```$', '', str(llm(JUDGE_SYSTEM, body, max_tokens=200) or '').strip(), flags=re.M))
        state = str(j.get('state') or '').lower()
        return {'state': state if state in ('finished', 'asking', 'working') else 'working',
                'why': str(j.get('why') or '')[:300]}
    except Exception as e:
        logger.debug(f'self-close judge failed: {e}')
        return {'state': 'working', 'why': f'the judge could not answer ({str(e)[:80]})'}


# ── the gates ───────────────────────────────────────────────────────────────────────────
def blocked(store, tid: int, term=None) -> str:
    """'' when this task may close itself, else the reason it may not - which is written onto the
    task, because a self-close that silently declines is indistinguishable from one that is
    broken."""
    from . import waitroom
    if not tid: return 'no task'
    with _LOCK:
        if tid in _DONE: return 'a self-close already ran for this task'
    t = store.get_task(tid) or {}
    if not t: return 'no task'
    if t.get('Status') in ('done', 'dropped'): return 'the task is already closed'
    if term is not None:
        age = time.time() - (getattr(term, 'started_ts', 0) or 0)
        if getattr(term, 'started_ts', 0) and age < MIN_AGE: return f'the session is younger than {int(MIN_AGE)}s'
        if getattr(term, 'n', 0) < MIN_CHARS: return 'the session has barely printed anything'
        # the screen's own words beat any judge: a CLI parked at a question says so, in a
        # phrasing waitroom already knows how to spot
        if waitroom.looks_like_question(term.tail(waitroom.TAIL_LINES)):
            return 'the last lines read as a question for you'
    return ''


def stays_open(store, tid: int) -> bool:
    """Did the owner open this one to sit in? Then the judge does not get to end it.

    A session started from the Board or + New is a place the owner is working - they alt-tab, the
    agent goes quiet for forty-five seconds, the judge reads the last screen as 'finished' and the
    task closes with a reply drafted to nobody. The tag says: only an explicit ending counts."""
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


# ── the two roads ───────────────────────────────────────────────────────────────────────
def declare(store, tid: int, summary: str = '', agent: str = 'agent') -> dict:
    """The EXPLICIT road: the agent ran `taskuary --done`. It said so, so no judge is consulted -
    only the gates that stop a double close or a task already shut. Its sentence is filed as a
    comment before the wrap, so the report is written with the agent's own last word in the
    transcript rather than instead of it."""
    from . import coder, terminal as term
    if mode(store) == 'off': return {'closed': False, 'why': 'self-closing is switched off in Settings'}
    why = blocked(store, tid, term.session_for(tid))
    # an explicit declaration outranks "it looks like a question": the agent just said otherwise
    if why and 'question' not in why: return {'closed': False, 'why': why}
    line = ' '.join(str(summary or '').split())[:1200]
    # A session the owner opened to SIT IN is theirs to end. `--done` used to close it anyway -
    # "either way", the box said - and TQ-0297 (2026-09-01) closed under the owner mid-review
    # because the agent decided it was finished. The agent's verdict is filed where the owner
    # reads it; the session stays at its prompt, which raises its hand; the owner presses Done.
    if stays_open(store, tid):
        store.add_comment(tid, agent, 'agent', f'The agent says it is finished: {line}' if line else 'The agent says it is finished.')
        store.audit('task', tid, 'agent_done_held', agent, detail={'why': 'opened to work in'})
        return {'closed': False, 'held': True,
                'why': 'the owner opened this session to work in, so only they end it - your summary is on the task; stay at the prompt'}
    if not _mark(tid): return {'closed': False, 'why': 'a self-close already ran for this task'}
    store.add_comment(tid, agent, 'agent',
                      f'The agent closed this itself: {line}' if line else 'The agent closed this itself.')
    return _wrap(store, tid, agent, 'the agent said it was finished' + (f' - {line}' if line else ''))


def on_stop(store, term, said: str = '') -> dict:
    """The AUTOMATIC road: the CLI's stop hook fired. Judge the ending, and close only on a clear
    'finished'. Runs on its own thread from the caller - a hook must never hold the agent."""
    tid = getattr(term, 'task_id', None)
    if not tid or mode(store) != 'auto': return {'closed': False, 'why': 'not automatic'}
    why = blocked(store, tid, term)
    if why: return {'closed': False, 'why': why}
    if stays_open(store, tid):
        logger.debug(f'self-close: task {tid} was opened to work in - only `taskuary --done` ends it')
        return {'closed': False, 'why': 'you opened this one to work in'}
    from . import terminal as _t
    v = judge(store, _t.harvest(term), said)
    if v['state'] != 'finished':
        logger.debug(f'self-close: task {tid} stays open - {v["state"]}: {v["why"]}')
        return {'closed': False, 'why': f"{v['state']}: {v['why']}"}
    if not _mark(tid): return {'closed': False, 'why': 'a self-close already ran for this task'}
    store.add_comment(tid, getattr(term, 'agent', None) or 'agent', 'agent',
                      f'The session stopped and read as finished, so it closed itself: {v["why"]}')
    return _wrap(store, tid, getattr(term, 'agent', None) or 'coder', v['why'])


def _wrap(store, tid: int, agent: str, why: str) -> dict:
    """The same ending the Done button gets. A failure here must not take the hook (or the CLI)
    with it, and it must not leave the task looking closed when it is not - so the mark is
    dropped and the reason is written where the owner reads it."""
    from . import coder
    from .store import task_ref
    try:
        out = coder.wrap(store, tid, close=True, actor=agent or 'coder')
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


def spawn_on_stop(store, term, said: str = '') -> None:
    """Fire-and-forget: a hook has 3 seconds and the judge is an AI call."""
    threading.Thread(target=lambda: on_stop(store, term, said), daemon=True).start()


# ── what the session is told ────────────────────────────────────────────────────────────
# The explicit road only exists if the agent knows about it, so this rides in every seed prompt.
# It is phrased as the CHEAP ending, because that is what it is: the alternative is a human
# looking at a screen hours later.
# Short on purpose. Every character here rides on a command line that a canonical tty caps at
# 1024 bytes, so the WHOLE rule lives in CODER.md (which rides in as RULES) and this is only the
# part that must survive a blanked document: the command, and what pressing it does.
SEED_LINE = ('WHEN FINISHED: run `taskuary --done "<one sentence>"` - it closes the task and '
             "drafts the sender's reply for the owner.")


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


def chat_marker(text: str) -> tuple:
    """(cleaned reply, the agent's closing sentence) - or (text, None) when it did not say so."""
    m = _MARK_RE.search(text or '')
    if not m: return text, None
    return (text[:m.start()].rstrip(), ' '.join((m.group(1) or '').split())[:600])
