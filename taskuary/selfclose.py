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

It lands in wrapup.wrap, which is exactly what the Done button calls. Nothing about the ending
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
# new task on the Tasks tab, Start session, Continue with the agent, the Wall - and never by the
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


# the note a `--done` leaves on the task - its sentence after this; responder.resolution_of reads it back
DONE_SAID = 'The agent says it is finished: '

def mode(store) -> str:
    """'on' | 'off'. There used to be three: 'auto' also let a judge close a quiet screen, 'ask' did not.
    The judge is gone (2026-09-24), so the two behaved the same and one is left; a stored 'ask' reads as on."""
    v = str(store.get_setting(SETTING, '1') or '1').strip().lower()
    return 'off' if v in ('0', 'off', 'false') else 'on'


def settle_legacy(store) -> bool:
    """A stored 'ask' becomes '1' once, so Settings' switch shows what the setting does. True when it moved."""
    if str(store.get_setting(SETTING) or '').strip().lower() != 'ask': return False
    store.set_setting(SETTING, '1', 'upgrade'); return True


# ── the gates ───────────────────────────────────────────────────────────────────────────
def blocked(store, tid: int, term=None) -> str:
    """'' when this task may close itself, else the reason it may not - which is written onto the
    task, because a self-close that silently declines is indistinguishable from one that is
    broken."""
    from . import workerstate as ws
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
        # ...both are a TERMINAL's: a CLI that just started has printed its banner and nothing else. An API conversation's turn
        # is a whole answer, and a short one is still an answer - a W-9 reply drafted in 188 characters was refused its own
        # [[TASKUARY-DONE]], silently, while a longer answer to the same kind of job closed (walk 2026-10-21)
        if getattr(term, 'started_ts', 0) and getattr(term, 'n', 0) < MIN_CHARS: return 'the session has barely printed anything'
        # A QUESTION THE RUN ITSELF RAISED and nobody has answered: one a hook holds (hooks.ask), or one the agent asked
        # through its CLI's question tool or a [[TASKUARY-ASK]] marker (both recorded as requests by hooks/general). Not
        # the words on its screen - a line ending in "?" read as a question and refused an agent's own --done (2026-10-11:
        # "everything should be ai").
        # ...but a question a HOOK holds blocks the CLI that asked it: an agent running `taskuary --done` is past it - answered in the
        # terminal, or its CLI gave up waiting - and the hold is a leftover nobody can release, which refused every close after it (the owner,
        # 2026-10-30: "it should be able to close task" - two --done refused by a hold the agent had already moved on from). It lets go
        # here, and the close goes on; a question asked in an API agent's own answer can ride the same turn as its close, and still refuses
        if ws.held_for(tid): ws.release(tid)
        if req and req['kind'] == 'input_needed' and req.get('source') in ('api', ws.RESUMED):
            return f'a question to you is still open: {req["text"][:160]}'
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
OWNER_ENDS = ('the owner opened this session, so they complete the task - your summary is filed on it for them. '
              'If whoever asked is owed a reply, save it now with `taskuary --reply "<text>"` - one written only in the chat is not kept')


def declare(store, tid: int, summary: str = '', agent: str = 'agent', no_reply: bool = False, sid: str = None) -> dict:
    """The agent ran `taskuary --done`. It said so, so no judge is consulted - only the gates that stop
    a double close or a task already shut, and the task's own say. A `stay:open` task is the owner's
    to complete: the agent's sentence is filed as a comment and nothing closes (the owner, 2026-09-25 -
    the docs and the seed said the tag vetoed `--done` while this road closed anyway). Otherwise the
    sentence is filed before the wrap, so the report is written with the agent's own last word in the
    transcript rather than instead of it."""
    from . import terminal as term
    if mode(store) == 'off': return {'closed': False, 'why': 'self-closing is switched off in Settings'}
    why = blocked(store, tid, term.session_for(tid))
    if why: return {'closed': False, 'why': why}
    # a batch ends when its items do: `done` closes every line it has, so one still open would be settled unread
    from . import batch
    if batch.is_batch(store, tid):
        left = [str(i['Place']) for i in store.batch_items(tid) if i['State'] in batch.OPEN]
        if left: return {'closed': False, 'why': f"item{'s' if len(left) > 1 else ''} {', '.join(left)} of this batch "
                                                 f"{'are' if len(left) > 1 else 'is'} still open - report each with `{batch.REPORT} <n>` first"}
    line = ' '.join(str(summary or '').split())[:1200]
    if stays_open(store, tid):
        store.add_comment(tid, agent, 'agent', f'{DONE_SAID}{line}' if line else 'The agent says it is finished.')
        return {'closed': False, 'why': OWNER_ENDS}
    # ...NOR WHILE ANYTHING ELSE ON IT IS STILL WORKING (the owner, 2026-11-01: "If anything still working never close the task
    # automatically"): another session open on it, a routine, a write-up - the word is filed and the task stays open.
    # `sid` is the asker's own session (TASKUARY_SID); an older CLI that sends none is taken to be the task's one live session
    from . import workerstate as ws
    me = sid or getattr(term.session_for(tid), 'sid', None) or ''
    live = ws.live_work(store, tid, but=me)
    if live:
        store.add_comment(tid, agent, 'agent', f'{DONE_SAID}{line}' if line else 'The agent says it is finished.')
        return {'closed': False, 'why': f"{'; '.join(live)} - the task stays open and the owner completes it"}
    if not _mark(tid): return {'closed': False, 'why': 'a self-close already ran for this task'}
    result = _finished(store, tid, term.session_for(tid), line)
    out = _wrap(store, tid, agent, 'the agent said it was finished' + (f' - {line}' if line else '')
                + (' (no reply owed)' if no_reply else ''), result, no_reply=no_reply)
    # ...said AFTER the ending, because the ending may not close it: work found to be in another repository is left open asking
    # where to move it (wrapup.asks_to_move), and "The agent closed this itself" over an open task read as handled (2026-10-27)
    if out.get('asks'):
        store.add_comment(tid, agent, 'agent', f'{DONE_SAID}{line}' if line else 'The agent says it is finished.'); return out
    if not out.get('ended'): return out                     # _wrap said why it could not, where the owner reads it
    # NO REPLY IS THE AGENT'S CALL TO MAKE, said where the owner reads it (the owner, 2026-10-08: "allow done with no reply") - and the
    # close is still the owner's (nothing_left)
    first = next((x.strip() for x in str(out.get('report') or '').splitlines() if x.strip()), '')[:300]       # no sentence: its report says what
    nothing_left(store, tid, agent, '; '.join(x for x in (line or first, 'no reply is owed, so none was drafted' if no_reply else '') if x), said=DONE_SAID)
    from .buttons import label
    return {**out, 'says': NEVER_CLOSES.format(close=label('close'))}


# NOTHING TO DO IS SAID, AND THE TASK STAYS OPEN (the owner, 2026-11-07): the reply writer decided nothing went back and closed a task
# triage had said needed a reply, 14 s after it came in - off the rail, unseen. Neither the agent nor the reply writer closes a task: the
# finding is said in one plain line on the task, which stays where the owner sees it, and their Mark done is the close.
def nothing_left(store, tid: int, by: str, why: str, said: str = 'Nothing to do here: ') -> None:
    from .buttons import label
    why = ' '.join(str(why or '').split()).rstrip('.')
    store.add_comment(tid, by, 'agent', f"{said}{why}. You can close it with {label('close')}." if why else f"{said.rstrip(': ')}. You can close it with {label('close')}.")


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


def _wrap(store, tid: int, agent: str, why: str, final_message: str = '', no_reply: bool = False) -> dict:
    """The same ending the Done button gets. A failure here must not take the hook (or the CLI)
    with it, and it must not leave the task looking closed when it is not - so the mark is
    dropped and the reason is written where the owner reads it."""
    from . import wrapup
    from .store import task_ref
    try:
        # ...the ending runs (report, drafted reply, proposals) and the task stays open: closing it is the owner's (nothing_left)
        out = wrapup.wrap(store, tid, close=False, actor=agent or 'agent', final_message=final_message, no_reply=no_reply)
        # ...and a reply already waiting (triage's early draft, one the agent saved) goes down with it: nobody hears back
        if no_reply:
            for rv in (store.pending_review(tid, 'draft_reply', live_only=False), store.pending_review(tid, 'draft', live_only=False),
                       store.held_review(tid)):
                if rv and rv.get('Status') in ('pending', 'held'):
                    store.decide_review(rv['ReviewId'], 'no_reply', None, agent or 'agent', 'the agent said no reply is owed')
    except Exception as e:
        forget(tid)
        logger.warning(f'self-close failed for task {tid}: {e}')
        store.add_comment(tid, 'router', 'agent',
                          f'The agent tried to close this itself and could not ({str(e)[:200]}) - '
                          'the Done button on the task still works.')
        return {'closed': False, 'why': str(e)[:200]}
    # the work is in another repository: the ending asked where to move it and left the task open (wrapup.asks_to_move) - not a close,
    # and a later --done, once it is moved, may close it
    if out.get('asks') == 'repo':
        forget(tid)
        return {**out, 'closed': False, 'why': 'the work is in another repository - the owner was asked where to move it'}
    store.audit('task', tid, 'self_close', agent or 'agent', 'agent', {'why': why[:300], 'drafting': out.get('drafting'), 'closed': False})
    logger.info(f'{task_ref(tid)}: its agent ended its run, the task stays open for the owner - {why[:120]}'
                + (' (reply drafted)' if out.get('drafting') else ''))
    return {**out, 'closed': False, 'ended': True, 'drafting': bool(out.get('drafting')), 'why': why}


# ── what the session is told ────────────────────────────────────────────────────────────
# The explicit road only exists if the agent knows about it, so this rides in every seed prompt.
# It is phrased as the CHEAP ending, because that is what it is: the alternative is a human
# looking at a screen hours later.
# Short on purpose. Every character here rides on a command line that a canonical tty caps at
# 1024 bytes, so the WHOLE rule lives in CODING.md (which rides in as RULES) and this is only the
# part that must survive a blanked document: the command, and what pressing it does.
# ...FOR WHOEVER WROTE IN, never the owner (the real-CLI walk, 2026-11-12: asked a question in the chat, a coding agent saved its answer as a
# reply to him, was refused, and told him so): what he asks here is answered in the session's own words
SEED_LINE = ('REPLY: save the answer for whoever wrote in with `taskuary --reply "<text>"` (a file it promises: add `--attach <path>`) - the owner approves it; '
             'what the owner asks you here, answer in your own words, never as a reply. '
             'WHEN FINISHED: run `taskuary --done "<one sentence>"` - it files your ending, and a reply owed that you did not save is asked of you; the owner closes the task; '
             'add `--no-reply` when nobody should hear back. '
             'ONLY SOMEONE ELSE CAN ANSWER: ask them, then `taskuary --waiting-on "<who>"` - their reply brings the task back.')
# ...and its opposite, for a session the owner opened to sit in (stays_open): the one thing the
# agent must NOT do is end it. Said in the prompt, because CODING.md's finishing rules say the
# reverse and an agent reading both without this line picks the one with a command in it. It says
# what `declare` does: the command is refused here and the owner completes the task.
STAY_LINE = ('THE OWNER OPENED THIS SESSION: `taskuary --done` is refused. Reply via `taskuary --reply "<text>" --to "<who>"`, not chat. '
             'Answer what is asked, then wait.')
# ...because this line REPLACES SEED_LINE (terminal.seed_parts), the reply road was the one thing an owner-opened session never
# heard of: an agent wrote the whole reply into its chat, ran a refused --done, said "the reply above is ready", and the
# drafter wrote a placeholder from that pointer (2026-10-13)


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
    f'found>. That files your ending and drafts the answer the person who asked will get - the owner closes the task and '
    f'approves it before it leaves. Only on a real ending. Never write it when you have asked a '
    f'question, offered options, or still need something; a conversation that is still going is '
    f'not an ending, and neither is an answer the owner may want to push back on.')

# ...SAID ONCE (the agent walk, 2026-11-10): each draft stood twice - its subject and body quoted in the answer, over the card that showed the
# same words - and the owner, 2026-11-10: a replaced reply was quoted whole, with its scratch folder's path under it. One sentence, read
# from the guide every general turn carries (owner_closes_line) and from the draft tools' own answer (agenttools.propose_reply/propose_email)
# ...ONE DUTY LINE (the owner's rule 8, 2026-11-11: the agent talks like a person helping - "no repeating what the card says"): it was told
# to say what it set up and for whom, and said that over a card that says it - then "it waits for your Send", "nothing has been sent". What
# the card shows is never said; the agent adds only what the card cannot
CARD_SAID = ('A reply, an email or an act you set up is its card under your answer, with its own button - the result itself: it shows '
             'what it is, to whom, its words, the file it carries, that it waits and that nothing went. Say none of that or what it replaced, and never '
             'retell its content in other words. Add only what the card cannot say - what you will do after the press, an assumption in it (a '
             'guessed address, a picked date), the one question - in one short line, or nothing. Raise your cards in the order they should '
             'happen; what stands on his screen is told you at the head of every turn. Many of one act (25 emails, 40 issues to close) go as '
             'ONE card, in one call with `items`.')
# ...AND A ROUTINE'S OWN EMAIL IS NO CARD (slots.routine_sends, the owner 2026-11-17: "routines should send on their own too"): it went at
# once, and its agent was told the card "shows ... that it waits and that nothing went" - so it said nothing went (the tools stress round)
def card_said(out: dict) -> str:
    "How a draft that stood is spoken of, on every road (the draft tools, `taskuary --draft`): sent at once, failed to go, or its card."
    if out.get('sent'): return ("It went at once - a routine's email to what its owner saved into it is sent without a press, so there is no card: say in a few words that "
                                "it was sent, and to whom.")
    if out.get('send_error'): return (f"It did not go ({out['send_error']}), so it stands as its card for the owner's Send - say that in one "
                                      f"line. {CARD_SAID}")
    return CARD_SAID
# ...AND A STEP TASKUARY HELD IS A CARD TOO (the real-CLI walks, 2026-11-12: "The delete of old-export.csv is waiting for your approval",
# over the card that says so; "still waiting for your Approve" the turn after): every hold's answer to its agent ends on this one tail
CARD_TAIL = ('It is a card in this task now: the card says what it is and that it waits for their press - never say either. Add only what '
             'you will do once it is pressed, in one short line, or nothing.')
# ...and WHAT A TURN IS HANDED IS CONTEXT, NOT NEWS (same walks): each turn is told what waits, what went and what he pressed, and said it
# back to him - so the block says once, at its head, that it is his page's own news (general.latest_block)
FACTS_HEAD = ('WHAT TASKUARY TELLS YOU FOR THIS TURN - context for you alone: the owner sees each of these on the task already. Act on them; '
              'never say them back - no "still waiting on your approval", no card or draft quoted, no id.')
HANDLES_LINE = ("An id Taskuary gives a draft or a card (rv4) is your tools' handle - the owner never sees it: to them, name a thing by what it "
                'is and whom it is to.')
# ...and WHERE THE OWNER CLOSES IT (no CHAT_LINE: nobody wrote in, or the owner keeps the task to finish): the agent said "I couldn't
# close the task from here", a failure over finished work (the desktop stress test, 2026-11-03). It is told whose press the close is
# ...and ONE ANSWER TO "DID IT CLOSE": none of an agent's steps closes the task (the owner, 2026-11-16, "straight up lying": a coding agent ran
# its finish and wrote "I've closed the task", then "I had just marked the task done, so I'm reopening it" over a task open all along)
NEVER_CLOSES = ('Taskuary did not close the task - closing it is the owner\'s, with {close}, which is lit for them now. Your sentence is filed on '
                'the task. Never say you closed, marked done or reopened it.')
def owner_closes_line() -> str:
    from .buttons import label
    # ...and never names the close at all (design round 4, 2026-11-19: "Ready for Mark done" ended answers on three AIs - this line taught it):
    # the page lights the button when the work is done, so the answer ends on the result
    return (f'ENDING THE TASK: the owner closes it with {label("close")}, which the page lights for them once your work is done - none of your '
            f'steps closes it, so never say you closed, marked done or reopened it, and never name the button or the close: end on the result. '
            # ...and where what it drafts is (the owner, 2026-11-05: a draft said to be in a section that no longer exists): earlier turns of the
            # conversation may still name another screen - the page they were written for is gone
            f'WHERE YOUR DRAFTS ARE: this task is one chat - no other screen or tab, whatever an earlier turn said. {CARD_SAID} '
            # ...and NAMED AS THE OWNER KNOWS IT (agent walk 2, 2026-11-10: "send it after rv3", "set up for your Send (review 5)")
            f'{HANDLES_LINE}')


# THE ONE ENDING THE AGENT SAYS (the owner, 2026-11-05: "it should trigger a new taskuary chat ... saying i saw you reply so i will close the
# task" - then: "so i recommend close it"): the owner answered the thread themselves, outside Taskuary (general.owner_answered_last); the
# agent thinks again and RECOMMENDS the close - the owner makes it
OWNER_ANSWERED_LINE = ('THE OWNER ANSWERED THIS THEMSELVES: the newest message on the thread is their own reply, sent outside Taskuary. Think '
                       'again about the task in its light. Say in one or two short lines that you saw their reply and what it settled; if that '
                       'took care of it, recommend they close the task (you never close it yourself); if something is still open, say what. '
                       'Do not draft a reply they already sent.')


# ...and its reply. The chat writes the answer the sender gets inside a marked block; the words between
# the markers become the task's pending reply as written (wrapup.agent_reply) and stay in the chat too.
REPLY_OPEN, REPLY_CLOSE = '[[TASKUARY-REPLY]]', '[[/TASKUARY-REPLY]]'
# ...its opening may say who hears it (2026-11-06): [[TASKUARY-REPLY answers=12 only=yes cc="a@x.example, b@y.example" why="..."]] (reply_who)
_REPLY_RE = re.compile(r'\[\[\s*TASKUARY[-_ ]?REPLY(?:\s+(?P<who>[^\]]*?))?\s*\]\](?P<said>.*?)\[\[\s*/\s*TASKUARY[-_ ]?REPLY\s*\]\]', re.I | re.S)
_WHO_RE = re.compile(r'(to|answers|only|cc|why)\s*=\s*(?:"([^"]*)"|(\S+))', re.I)
REPLY_LINE = (f'REPLYING FOR THE OWNER: the answer the person who asked will get goes exactly between {REPLY_OPEN} and {REPLY_CLOSE} - '
              f'the block IS the draft waiting on the owner\'s approval, so its words are written once, there, and nowhere else in your '
              f'answer. A file rides only if you name it on its own line: [[TASKUARY-ATTACH: <full path>]] - one you made in your working '
              f'folder, or one under ATTACHED FILES; never say a file is attached otherwise. Who hears it is yours to decide, in the opening '
              f'marker, each optional: [[TASKUARY-REPLY answers=<the mail number it replies to, when an earlier one> only=yes (its sender '
              f'alone, nobody copied) cc="<who else is copied, instead of the thread>" why="<one line: why it goes to whom it goes>"]].')


# ...and EVERY TURN ENDS WITH WHERE THE OWNER STANDS (Task 3.4, 2026-11-04): the general agent's one goal is to get the owner to done, so
# each turn closes on a block the page draws as three parts - what the task wants, what the agent did, what is on the owner (the parser
# is Task 3.5's). Not `SUMMARY:`, which the brief already uses as the task-summary label.
SUMMARY_OPEN, SUMMARY_CLOSE = '[[TASKUARY-SUMMARY]]', '[[/TASKUARY-SUMMARY]]'
AFTER_PRESS = ('send', 'handoff')
from .buttons import label as _label
RETRY_LABEL = _label('try_again')          # the button a summary's `retry` draws
SUMMARY_LINE = (f'ENDING EVERY TURN: close with {SUMMARY_OPEN}{{"name": "<the task in three to six words, as a to-do list names it>", "about": "<two or three plain sentences from the whole thread: which '
                f'conversation, what about, who asked, for whom, why - naming only people it shows in that role>", "did": "<the RESULT ITSELF '
                f'first (the path, link, figure or name), then what you did; any part unmet or unchecked>", "on_you": ["<a step for what they '
                f'asked that only they can take, a line each with why, said nowhere in your words above; [] when nothing_left>"],"nothing_left": <true only when the goal '
                f'is met and you checked it>, "answer_is_result": <true when your words above ARE what was asked>, "after_press": <"send" only if you '
                f'carry on once the owner presses what you set up (deploy once he approves the merge) - that press wakes you once; "handoff" '
                f'only if you carry on once he hands this to a person; else leave it out: a press with nothing after it never wakes you>, "retry": <true when what '
                f'stopped you may work on another try (a page that did not load, a site that did not answer): Taskuary puts a {RETRY_LABEL} button under '
                f'your turn - never ask the owner to send a message to try again>}}'
                f'{SUMMARY_CLOSE} - valid JSON, plain words, no secret, "you" to the owner. A card you set up and a question you ask are never an on_you step. When their newest message CORRECTS you, add "corrections": '
                f'[{{"kind": "redraft" (their words for the draft) or "ask" (you misread the task), "review": <the draft\'s id or null>, '
                f'"said": "<the correction, in their words>"}}], never shown. When what came in needs nothing from you or them - judged from '
                f'the thread, not its wording; in a group chat banter, a question already answered, a reply that would only say "ok" or '
                f'"thanks" (you are a participant there, not their voice) - the turn is ONE plain line ("Ray thanked you.") and '
                f'{SUMMARY_OPEN}{{"did": "<that line>", "about": "", "on_you": []}}{SUMMARY_CLOSE}: no draft, no research, the waiting draft '
                f'left as it is.')
_SUMMARY_RE = re.compile(r'\[\[\s*TASKUARY[-_ ]?SUMMARY\s*\]\](.*?)\[\[\s*/\s*TASKUARY[-_ ]?SUMMARY\s*\]\]', re.I | re.S)
# ...and one that never closed: a live line is cut to 300-400 characters before it is drawn (agents.py), and a turn can end without
# the closing tag - the opening tag through to the end goes, and so does a tag cut off part-way at the very end ("[[TASKUA")
_SUMMARY_CUT = re.compile(r'\[\[\s*TASKUARY[-_ ]?SUMMARY\s*\]\].*\Z', re.I | re.S)
_SUMMARY_TAGS = re.compile(r'\[\[\s*/?\s*TASKUARY[-_ ]?SUMMARY\s*\]\]', re.I)
_TAG_STUB = re.compile('(?:' + '|'.join(re.escape(SUMMARY_OPEN[:k]) for k in range(len(SUMMARY_OPEN) - 1, 2, -1)) + r')\s*\Z', re.I)
def without_summary(text: str) -> str:
    "`text` with every summary block, an unclosed one and a cut-off tag at its end taken out."
    return _TAG_STUB.sub('', _SUMMARY_CUT.sub('', _SUMMARY_RE.sub('', str(text or ''))))


def summary_marker(text: str, letters=()) -> tuple:
    """(text with every summary block taken out, {about, did, on_you, nothing_left}) - the dict None when it wrote none, or none that
    reads as JSON or says nothing. The block comes out either way, closed or not: a broken one is Taskuary's plumbing, never words for
    the owner - unless it was all the answer said, when its words are kept without the tags. `on_you` is there only when the agent
    gave a list: a summary without one leaves the owner's steps as they are. `letters`: the pending drafts' bodies, each of their
    lines said as SEE_DRAFT (without_letters) before the fields are cut to size."""
    t = str(text or ''); m = _SUMMARY_RE.search(t)
    if not m and not _SUMMARY_CUT.search(t): return text, None
    rest, bare = without_summary(t).strip(), lambda: (rest or _SUMMARY_TAGS.sub('', t).strip(), None)
    if not m: return bare()
    # ...read however the model wrapped it: Gemini and Claude behind a gateway put a ```json fence inside the tags (llm.json_of)
    from .llm import json_of
    try: j = json_of(m.group(1))
    except ValueError: return bare()
    if not isinstance(j, dict): return bare()
    # ...cut on a sentence, never mid-word: a step cut at 200 characters read "then ask me again and." under the answer (2026-11-16)
    from .store import ON_YOU_MAX, by_sentence
    flat = lambda x, n: by_sentence(without_letters(' '.join(str(x or '').split()), letters), n)
    out = {'about': flat(j.get('about'), 600), 'did': flat(j.get('did'), 600), 'nothing_left': j.get('nothing_left') is True}
    if (name := ' '.join(str(j.get('name') or '').split())[:80]): out['name'] = name
    # ...and the agent's own say on whether its prose is the deliverable (GeneralWorkspace: agentSummary.answerShown) - kept only when it said
    if isinstance(j.get('answer_is_result'), bool): out['answer_is_result'] = j['answer_is_result']
    # ...and the one press it waits on to carry on (general.follow_up): that press starts its next turn
    if j.get('after_press') in AFTER_PRESS: out['after_press'] = j['after_press']
    # ...and that what stopped it is worth another go: the page draws Try again under the turn (GeneralWorkspace), his press the go-ahead
    if j.get('retry') is True: out['retry'] = True
    if isinstance(j.get('on_you'), list): out['on_you'] = list(dict.fromkeys(x for x in (flat(o, ON_YOU_MAX) for o in j['on_you'] if isinstance(o, str)) if x))[:6]
    if cs := [{'kind': c['kind'], 'review': c['review'] if isinstance(c.get('review'), int) else None, 'said': ' '.join(c['said'].split())[:1000]}
              for c in j.get('corrections') or [] if isinstance(c, dict) and c.get('kind') in ('redraft', 'ask') and isinstance(c.get('said'), str) and c['said'].strip()]:
        out['corrections'] = cs[:6]
    # ...and the turn's check-back (general.CHECK_BACK_LINE): taken off the summary, never drawn
    if isinstance(c := j.get('check_back'), dict) and isinstance(c.get('what'), str) and c['what'].strip(): out['check_back'] = c
    return (rest, out) if out['about'] or out['did'] or out.get('on_you') else bare()


# ...and never a second copy of the letter (the owner, 2026-11-04): what goes to the sender - a login in it above all - lives in the draft
# only, never kept again in the summary or the On you list. A line of a pending letter found in it is said as SEE_DRAFT. Short lines
# ("Hi Gail,") are left alone: they carry nothing a summary could leak, and swapping them would garble its own words
SEE_DRAFT = '(see the drafted reply)'
def without_letters(s: str, letters=()) -> str:
    "`s` with every line (12+ characters) of the `letters` in it said as SEE_DRAFT, longest first."
    lines = sorted({x for l in letters or () for x in (' '.join(r.split()) for r in str(l or '').splitlines()) if len(x) >= 12}, key=len, reverse=True)
    for x in lines: s = s.replace(x, SEE_DRAFT)
    return s


def reply_marker(text: str) -> tuple:
    """(reply with the markers taken out, the marked reply text) - or (text, None) when it wrote none."""
    m = _REPLY_RE.search(text or '')
    if not m: return text, None
    said, rest = m.group('said').strip(), text[:m.start()] + text[m.end():]
    # ...said once: an agent that wrote the answer out and then marked the same words had both left on screen (2026-10-15)
    flat = lambda s: ' '.join(s.split())
    if said and flat(said) in flat(rest): return rest.strip(), said
    # ...and a paragraph of its own where it stood: glued to the words before it ("Drafted.Hi Ray - ..."), the letter was no paragraph
    # without_draft could find, and the chat drew it in the answer AND as its card (the scenario run, 2026-11-06)
    return '\n\n'.join(x for x in (text[:m.start()].rstrip(), said, text[m.end():].lstrip()) if x).strip(), said or None


def reply_who(text: str) -> dict:
    """Who the marked reply goes to, as its opening marker says - {to, answers, only, cc, why}, each only when given (wrapup.agent_reply's
    own names: answers an int, only a bool, cc a list, why as why_to)."""
    m = _REPLY_RE.search(text or '')
    if not m: return {}
    a = {k.lower(): (x or y).strip() for k, x, y in _WHO_RE.findall(m.group('who') or '')}
    out = {**({'to': a['to']} if a.get('to') else {}), **({'why_to': a['why']} if a.get('why') else {})}
    if str(a.get('answers') or '').lstrip('#').isdigit(): out['answers'] = int(a['answers'].lstrip('#'))
    if str(a.get('only') or '').lower() in ('yes', 'true', '1'): out['only'] = True
    if a.get('cc'): out['cc'] = [c.strip() for c in re.split(r'[,;]', a['cc']) if c.strip()]
    return out


# ...and said in ONE place: the draft is Close out's to show (the owner, 2026-11-02: "in agent we should just say 'agent drafted a message'").
# A model that wrote the reply out in its answer as well as filing it left the whole letter in the agent's pane over the same letter in
# Close out (the overnight run, 2026-11-03) - its words around the letter stay, the letter's own paragraphs and their rules go
_RULE = re.compile(r'^\s*([-*_=~])(\s*\1){2,}\s*$')
# ...only the letter itself: a run of paragraphs that together are substantially the whole draft. Any paragraph found anywhere in a draft
# used to go, so "Thanks, Gail." - the agent's own line, and the draft's sign-off too - vanished from its answer (the owner, 2026-11-05)
DRAFT_WHOLE = 0.6
def without_draft(text: str, draft: str) -> str:
    "`text` with the run of paragraphs that IS `draft` (with the rules inside it) taken out - '' when it was nothing else."
    flat = lambda s: ' '.join(str(s or '').split()).lower()
    d, paras = flat(draft), [p for p in re.split(r'\n\s*\n', str(text or '')) if flat(p)]
    if not d: return str(text or '').strip()
    runs, cur = [], []
    for i, p in enumerate(paras):
        if _RULE.match(p) or flat(p) in d: cur.append(i)
        elif cur: runs.append(cur); cur = []
    if cur: runs.append(cur)
    gone = {i for r in runs if sum(len(flat(paras[i])) for i in r if not _RULE.match(paras[i])) >= DRAFT_WHOLE * len(d) for i in r}
    if not gone: return str(text or '').strip()
    return '\n\n'.join(p.strip('\r\n') for i, p in enumerate(paras) if i not in gone and not _RULE.match(p)).strip()


# ...and the files that go with it. A chat brain has no `taskuary --attach` it can use: an API provider has no shell, and a
# CLI's command would run mid-turn, before the reply block above is read. So it names the file and the turn's end attaches it.
_ATTACH_RE = re.compile(r'^[ \t]*\[\[\s*TASKUARY[-_ ]?ATTACH\s*:?\s*(.+?)\s*\]\][ \t]*\n?', re.I | re.M)

def attach_markers(text: str) -> tuple:
    """(text with every attach line taken out, [the paths it named])."""
    return _ATTACH_RE.sub('', text or '').strip(), [m.strip().strip('"\'') for m in _ATTACH_RE.findall(text or '')]


# ...and what it SHOWS the owner. Words are the answer; a picture, a chart or a page only when it makes the answer easier
# to understand (the owner, 2026-10-09: "only if the agent thinks it's a good way to understand things - random scratch
# stuff not"). Nothing it writes on the way is shown: only a file it names this way lands in the chat, under this turn.
# LATEST MESSAGE WINS (the owner, 2026-11-06: "Latest message should recalculate all the prior messages. it's just resending the original
# response that was already sent"): corrected after a draft was waiting, the agent answered the first ask of the thread again and left that
# draft standing under its newest turn, reading as the answer to the correction. Every turn is told it answers the NEWEST message, read
# against all before it, what is pending and what already went (general.latest_block) - and how to take a draft back: this marker, on a road
# with no shell, or `taskuary --withdraw-draft` / the withdraw_draft tool (verdicts.withdraw). The model judges; no word list does
# ...AND A NEWER MESSAGE NEVER RETIRES WHAT IS STILL OWED (the walk, 2026-11-19: asked for three caterer options, then "did you hear back?",
# the agent called the options "no longer needed" and drafted only "Not yet" - "never an earlier ask again" read as dropping it)
LATEST_LINE = ('LATEST MESSAGE WINS: answer the newest message against the whole conversation - an ask it corrects or one already answered '
               'is never answered again, but a newer message never retires what is still owed to its sender: answer that, then the new '
               'question. When the thread changed (someone answered, plans or facts moved), re-plan - maybe no reply, new research, corrected '
               'drafts, or nothing. Replace a pending draft with a corrected one or withdraw it (why, one line), never leave it standing as '
               'this answer; never draft again what already went out below.')
# ...A TURN NO MESSAGE STARTED (agent walk 2, 2026-11-10): woken by the owner's Send, the agent was handed the line it had answered a minute
# before as "THE NEWEST MESSAGE", under "your answer is to the newest message" - and answered "What is left here?" a second time. A turn
# Taskuary starts on an answered task (a press, a result that came back, a check-back) is told nothing new was said (general.latest_block)
NO_NEW_LINE = ('NO NEW MESSAGE STARTED THIS TURN: the last message on the task is one you have answered - never answer it again. This turn '
               'is about the rest of what you are told here. A draft still waiting stays as it is unless that undoes it; never draft again '
               'what already went out below.')
# EACH DUTY ONCE, IN THE STARTUP CONTEXT (the owner, 2026-11-11: "why would an agent say the same thing twice?"): the rules above rode EVERY
# turn of a chat's agent, beside the same duty in its startup lines (REPLY_LINE, WHERE YOUR DRAFTS ARE, the summary's), and an agent says
# back what it is told more than once - "ready for your Send below", then "Nothing has been sent", then "the new draft takes the place of
# the old one". A chat's agent is told them once (DRAFTS_ONCE, general.prompt_parts) and a turn carries only its facts under a short head
# ...and never said back (the real-CLI walks, 2026-11-12: "Nothing new has come in since my last answer" opened a turn a peer's note woke)
LATEST_HEAD, NO_NEW_HEAD = 'A NEW MESSAGE STARTED THIS TURN.', ('NO NEW MESSAGE STARTED THIS TURN: the last message on the task is one you have '
                                                                 'answered. Say only what this turn changed, in a line - never that nothing came in.')
WITHDRAW_MARK = '[[TASKUARY-WITHDRAW: <why, one line>]]'
# ...and any unsent thing it set up, as withdraw_draft takes it (verdicts.withdraw): an agent with no shell took back only the reply draft,
# so an email to the wrong person stood beside the right one with its Send (agent-flow audit, 2026-11-07)
WITHDRAW_LINE = (f'Withdraw it with {WITHDRAW_MARK} on its own line (shell: `taskuary --withdraw-draft "<why>"`; the withdraw_draft '
                 'tool), another proposal you set up with [[TASKUARY-WITHDRAW which=<its review id or who it was to>: <why>]] - kept under '
                 'Not sent, never deleted.')
DRAFTS_ONCE = (f'{LATEST_LINE} A turn no new message started never answers the last one again and leaves a waiting draft unless told '
               f'otherwise. {WITHDRAW_LINE}')
_WITHDRAW_RE = re.compile(r'^[ \t]*\[\[\s*TASKUARY[-_ ]?WITHDRAW\b\s*(?:which\s*=\s*(?:"([^"]*)"|([^\s:\]]+)))?\s*:?\s*(.*?)\s*\]\][ \t]*\n?',
                          re.I | re.M)
def withdraw_markers(text: str) -> tuple:
    "(text with every withdraw line taken out, [(which, why)]) - which '' for the reply draft, why '' when it gave no reason."
    found = [(' '.join((a or b or '').split()), ' '.join(w.split())) for a, b, w in _WITHDRAW_RE.findall(text or '')]
    return (text, []) if not found else (_WITHDRAW_RE.sub('', text).strip(), found)


# ...a VIEW freely, a FILE only when it truly helps (the owner, 2026-11-09: "use visuals ... ensure they are used liberally"; the 2026-10-09
# "random scratch stuff not" stands for files): "either way" here held the views back as well
# WHAT IT MAKES FOR HIM TO LOOK AT, IT SHOWS (the owner, 2026-11-15, of a query he asked to review that the agent saved as a file and only
# said was ready: "anything an agent creates should not be hidden" - and the ruling: the agent decides, as it does on Claude.ai and ChatGPT,
# and code draws what it showed). ONE sentence, in the show tool's own words on every road: the tool a CLI session is handed
# (agenttools), the one an API brain is handed (apiagent) and the line a chat with no tool reads (SHOW_LINE)
SHOW_WHAT = ('Whatever you make for the owner to look at - a query, a script, a document, a picture - show it: a file you only saved '
             'is not in front of them.')
_SHOW_RE = re.compile(r'^[ \t]*\[\[\s*TASKUARY[-_ ]?SHOW\s*:?\s*(.+?)\s*\]\][ \t]*\n?', re.I | re.M)
SHOW_LINE = ('SHOWING YOUR ANSWER: a table, a chart, a few numbers or a checklist is drawn in the chat by the `show` tool. Make a file '
             'only for what show cannot draw (an image, a long page, a spreadsheet to keep, a query, a script) and name it on its own line, '
             '[[TASKUARY-SHOW: <full path>]] (or show\'s `files`): it appears under this answer and stays on the task. ' + SHOW_WHAT +
             ' A file only when it truly helps - never your working files, test data or drafts. An .html page runs with no network: put its data and scripts in it.')


def show_markers(text: str) -> tuple:
    """(text with every show line taken out, [the paths it named])."""
    return _SHOW_RE.sub('', text or '').strip(), [m.strip().strip('"\'') for m in _SHOW_RE.findall(text or '')]


# ...and the emails that close a task (slots.draft): one block per email, its attributes say which slot or who.
DRAFT_OPEN, DRAFT_CLOSE = '[[TASKUARY-DRAFT', '[[/TASKUARY-DRAFT]]'
_DRAFT_RE = re.compile(r'\[\[\s*TASKUARY[-_ ]?DRAFT\b([^\]]*)\]\](.*?)\[\[\s*/\s*TASKUARY[-_ ]?DRAFT\s*\]\]', re.I | re.S)
_ATTR_RE = re.compile(r'(slot|to|subject)\s*=\s*(?:"([^"]*)"|(\S+))', re.I)
# ONE ROAD A SESSION (the agent walk, 2026-11-10): a chat was told the block, the tool and `taskuary --slot` at once, and wrote "an email to
# Ray Colton" a second time beside the checklist line that asked for it. The block is how a session with none of Taskuary's tools writes an
# email - one the checklist owes or one the work turned up; a session with the tools hears DRAFT_TOOL_LINE in its place (general.by_tool)
DRAFT_LINE = (f'EMAILS THIS TASK NEEDS: write each as {DRAFT_OPEN} slot=<id> subject="<subject>"]]<the email>{DRAFT_CLOSE} - the one way '
              'you draft an email here; the block IS the draft, its words written once, there, and nowhere else in your answer. A checklist '
              'line marked "-> email to" is an email only you write - write it or ask the owner what it needs; `slot` is its id, and your '
              'email fills it, never a second beside it. An email the checklist does not list takes to=<address> in place of slot (and beside '
              'slot, when the line names a person whose address you found). The subject is for its reader, never this task\'s title; to '
              'someone who mailed on this task, "Re: " their subject.')
DRAFT_TOOL_LINE = ('EMAILS THIS TASK ALREADY OWES: a checklist line marked "-> email to" is an email only you will write - write it, or ask the owner what it '
                   'needs: propose_email with `slot` set to its id and its words in `text` fills it, never a second email; no `slot` only for '
                   'an email the checklist does not list.')


def draft_markers(text: str) -> tuple:
    """(reply with every draft block taken out, [(attrs, body)]) - attrs keyed slot / to / subject."""
    found = [({k.lower(): (a or b) for k, a, b in _ATTR_RE.findall(m.group(1))}, m.group(2).strip()) for m in _DRAFT_RE.finditer(text or '')]
    return _DRAFT_RE.sub('', text or '').strip(), [f for f in found if f[1]]


def chat_marker(text: str) -> tuple:
    """(cleaned reply, the agent's closing sentence) - or (text, None) when it did not say so."""
    m = _MARK_RE.search(text or '')
    if not m: return text, None
    return (text[:m.start()].rstrip(), ' '.join((m.group(1) or '').split())[:600])


# ...and the to-dos it finished. A chat with no shell (an API card, or a CLI the owner set to look things up only) cannot run
# `taskuary --tick`, so it was told to and could not: its boxes stayed empty until the close ticked them all (2026-11-02). It says
# so with a mark instead, and the mark takes the same road the command does (store.agent_tick).
TICK_MARKER = '[[TASKUARY-TICK: <id>]]'
_TICK_RE = re.compile(r'^[ \t]*\[\[\s*TASKUARY[-_ ]?TICK\s*:?\s*([A-Za-z0-9_-]+)\s*\]\][ \t]*\n?', re.I | re.M)
TICK_CHAT_LINE = (f'TO-DOS HERE: you have no shell, so `taskuary --tick` is not yours to run. When you finish one of the checklist\'s '
                  f'to-dos, put a line {TICK_MARKER} in your reply - the id in brackets after it - and Taskuary ticks it. One line per '
                  f'to-do, only for what you actually did.')


# ...and a session that HAS the tick tool (an AI card whose Taskuary toolbox answered) is told the tool, never "you have no shell"
TICK_TOOL_LINE = ("TO-DOS HERE: when you finish one of the checklist's to-dos, tick it with the tick tool, its id - in brackets after it - as `item`. "
                  'Only what you actually did.')


def tick_markers(text: str) -> tuple:
    "(reply with every tick line taken out, [ids] in the order said)."
    return _TICK_RE.sub('', text or '').strip(), list(dict.fromkeys(_TICK_RE.findall(text or '')))


# ── ...and its question (PW-225) ────────────────────────────────────────────────────────
# A regular worker has no AskUserQuestion tool and no hook: when it cannot go on without the owner it says
# so with a marker, and Taskuary records the exact question as an Input-needed request - the one the
# owner's answer is bound to (workerstate.answer). A marker, again, not a judge reading prose for a '?'.
# ...and the question is plain words, answered in the box under it (the owner, 2026-11-03): option chips are only for a CLI's own
# question tool or its on-screen chooser, so the line no longer offers `| choice | choice` - and one written anyway stays text.
# ...and A QUESTION, NEVER PERMISSION (the agent walk, 2026-11-10): "cannot continue without their answer" read as leave to ask "shall I send
# it?" over the Send card that already asks it, while the summary line said the card IS the confirmation - the two now say one thing
ASK_MARKER = '[[TASKUARY-ASK]]'
_ASK_RE = re.compile(r'\[\[\s*TASKUARY[-_ ]?ASK\s*\]\]\s*:?\s*(.*)', re.I | re.S)
ASK_LINE = (f'ASKING THE OWNER: a real blocker - a fact or a decision only they can give - is one question, asked once in your own words, with '
            f'your recommended answer; end the reply with {ASK_MARKER} on its own line, which only marks that you wait on him. Never ask for '
            f'permission to do what a card already asks (its Send, Post or Approve is that question).')


def without_ask(text: str) -> str:
    """The marker taken out of anything the owner READS. It was stripped from the filed reply and
    nowhere else, so a CLI that put its question in a progress line printed Taskuary's own plumbing
    into the middle of the agent's thinking - `[[TASKUARY-ASK]] Have you signed in? | Signed in |
    Login failed`, verbatim, on screen (2026-09-15). The question itself is shown as a question."""
    return _TURN_RE.sub('', _SIGNIN_RE.sub('', _ASK_RE.sub('', str(text or '')))).rstrip()


# ── ...and a sign-in it needs (signin.py) ────────────────────────────────────────────────────
# The browser agent's "sign me in here". Its domain is only the agent's WORD, shown to the owner - what gets signed in is the page
# the browser is on (signin.needs), so a marker a mail talked the agent into writing can name anything and fill nothing.
# ...and its "sign me UP here" (signin.new_account): the same marker with UP, its claim then signin.NEW before the site
_SIGNIN_RE = re.compile(r'\[\[\s*TASKUARY[-_ ]?SIGN[-_ ]?(IN|UP)\s*(?::\s*([^\]]*))?\]\][^\n]*', re.I)


def signin_marker(text: str) -> tuple:
    """(cleaned reply, the domain the agent named - '' when it named none) - or (text, None) when it asked for no sign-in."""
    t = str(text or '')
    m = _SIGNIN_RE.search(t)
    if not m: return text, None
    site = ' '.join((m.group(2) or '').split())[:200]
    return _SIGNIN_RE.sub('', t).rstrip(), (f'new:{site}' if m.group(1).lower() == 'up' else site)


# ── ...and a step only the owner can do on the page (browserview.TURN_PREFIX) ────────────────────────────────────────────────
# A CAPTCHA, a sign-in the agent cannot finish, a card number: the agent stops and HANDS THE PAGE OVER, and the owner does it in the
# browser view and hands it back. The owner's words in the marker are shown on the view; the page is the browser's, never the marker's.
_TURN_RE = re.compile(r'\[\[\s*TASKUARY[-_ ]?YOUR[-_ ]?TURN\s*(?::\s*([^\]]*))?\]\][^\n]*', re.I)


def turn_marker(text: str) -> tuple:
    """(cleaned reply, what the owner is to do on the page - '' when it named nothing) - or (text, None) when it handed nothing over."""
    t = str(text or '')
    m = _TURN_RE.search(t)
    if not m: return text, None
    return _TURN_RE.sub('', t).rstrip(), ' '.join((m.group(1) or '').split())[:300]


# the done line as a progress line carries it: its sentence is filed as the task's comment (or is the answer), never progress
_DONE_LINE = re.compile(r'[ \t]*\[\[\s*TASKUARY[-_ ]?DONE\s*\]\][^\n]*', re.I)


# EVERY TAG TASKUARY TOLD AN AGENT TO WRITE, out of what the owner reads (the 2026-11-18 walk: "[[TASKUARY-FULL-AGENT]] Paying on ... needs a
# browser" stood in his chat - the quick lane's hand-on mark, written by a turn of the same session the quick road no longer read). The
# markers a turn acts on are read first, each by its own road; this is the last word on what is left: the [[TASKUARY-...]] tags, the Hub's
# <TASKUARY-HUB>...</TASKUARY-HUB> with what it carries, and a bare TASKUARY-PROPOSE (proposals.MARK)
_TAG = re.compile(r'<\s*TASKUARY-HUB[^>]*>.*?<\s*/\s*TASKUARY-HUB[^>]*>|\[\[\s*/?\s*TASKUARY[^\]]*\]\][ 	]*|<\s*/?\s*TASKUARY[^>]*>|TASKUARY-PROPOSE', re.I | re.S)
def unmark(text) -> str:
    "Every Taskuary tag out: words for the owner."
    return _TAG.sub('', str(text or '')).strip()


# A TURN STORED AS ONE CALL'S RAW OBJECT (until 2026-11-13 a quick answer was one JSON object, and a few were filed whole, fenced or cut
# short - the owner, 2026-11-03): a database still holds them, and they read back as the report they hold wherever the chat is read
RAW = re.compile(r'^\s*(?:```(?:json)?\s*)?\{\s*"(?:report|draft|question|done|escalate|why)"\s*:', re.I)
def is_raw(text) -> bool: return bool(RAW.match(str(text or '')))

_REPORT = re.compile(r'"report"\s*:\s*"((?:[^"\\]|\\.)*)', re.S)
def report_of(text) -> str:
    "The report a raw stored answer holds - or the text as it is, when it is not one."
    t = str(text or '')
    if not is_raw(t): return t
    clean = lambda x: unmark(for_screen(draft_markers(reply_marker(str(x or ''))[0])[0]))
    body = re.sub(r'^\s*```(?:json)?\s*|\s*```\s*$', '', t)
    try: d = json.loads(body)
    except ValueError: d = None
    if isinstance(d, dict) and d.get('report'): return clean(d['report'])
    m = _REPORT.search(body)                       # cut short: the report as far as it got, its last escape whole or dropped
    if not m: return ''
    try: return clean(json.loads('"' + re.sub(r'\\u?[0-9a-fA-F]{0,3}$|\\$', '', m.group(1)) + '"'))
    except ValueError: return clean(m.group(1).replace('\\n', '\n'))


def for_screen(text: str) -> str:
    """A progress line as the owner reads it: no ask marker, no attach lines, no done line, and no reply block - the reply is shown
    once, as the answer. A CLI's final text streams in as a progress line too, so the box drew the markers and the answer twice
    (2026-10-15); a done line left in kept the last paragraph from matching the answer, so it was drawn twice again (walk 2026-10-29)."""
    # ...and no show line: its file is drawn under the answer, and left in it kept the answer drawn twice again (stress test 2026-11-02)
    # ...and no summary block: it is the turn's three parts, drawn under the answer from the row it is filed as (Task 3.5)
    return unmark(show_markers(attach_markers(_DONE_LINE.sub('', without_summary(_REPLY_RE.sub('', without_ask(text)))))[0])[0])


_ASK_ONE = re.compile(r'\[\[\s*TASKUARY[-_ ]?ASK\s*\]\]\s*:?', re.I)
_ASK_TAIL = re.compile(r'\[\[\s*TASKUARY[-_ ]?ASK\s*\]\][^\n]*', re.I)          # a marker and the rest of its line: its question, if any


def ask_markers(text: str) -> tuple:
    """(cleaned reply, [(question, choices)]) - EVERY marker, in order (the owner, 2026-09-28: a regular agent's three
    questions reached the card as one; the first marker swallowed the rest as its own choices)."""
    t = without_summary(str(text or ''))
    cuts = [m for m in _ASK_TAIL.finditer(t)]
    if not cuts: return text, []
    asks, prev = [], 0
    for m in cuts:
        # ...ONE GRAMMAR (the agent audit, 2026-11-22: words written after the marker - "Meanwhile I drafted the agenda..." - were recorded as the
        # question, and cut from the answer): the question is what the marker's own line says after it, its choices split by '|' - or, where
        # the marker stands bare (ASK_LINE: asked in its own words), the paragraph above it. What follows on later lines is the answer's
        parts = [' '.join(p.split()) for p in _ASK_ONE.sub('', m.group(0), 1).split('|')]
        q = parts[0] or ' '.join((re.split(r'\n\s*\n', t[prev:m.start()].strip()) or [''])[-1].split())
        if q: asks.append((q[:600], [p[:120] for p in parts[1:] if p]))
        prev = m.end()
    return re.sub(r'\n{3,}', '\n\n', _ASK_TAIL.sub('', t)).strip(), asks


def carried(earlier: str, last: str) -> str:
    """What the turn wrote FOR THE APP before its last message, which that message does not carry: a question (its paragraph and its marker),
    a reply or draft block, a tick, attach, show, withdraw, done, sign-in or hand-over line - and its summary where the last message has none.
    The answer is the last message (acp.prompt); read off it alone, a question asked before one more tool call was never recorded, and the
    turn read "agent done" over it (the agent audit, 2026-11-22). One reader of markers (general._file) then reads them all."""
    e, out = str(earlier or ''), []
    held = lambda x: x.strip() and x.strip() not in str(last or '')
    for rx in (_REPLY_RE, _DRAFT_RE): out += [m.group(0) for m in rx.finditer(e) if held(m.group(0))]
    if not _SUMMARY_RE.search(str(last or '')): out += [m.group(0) for m in _SUMMARY_RE.finditer(e)][-1:]
    for rx in (_ATTACH_RE, _SHOW_RE, _TICK_RE, _WITHDRAW_RE, _DONE_LINE, _SIGNIN_RE, _TURN_RE):
        out += [m.group(0).strip() for m in rx.finditer(e) if held(m.group(0))]
    # ...a question: the marker's own line, and the paragraph above it where the marker stands bare (ASK_LINE: asked in its own words)
    bare = without_summary(e)
    for m in _ASK_LINE.finditer(bare):
        asked = _ASK_ONE.sub('', m.group(0)).strip(' :\t')
        above = '' if asked else (re.split(r'\n\s*\n', bare[:m.start()].strip()) or [''])[-1]
        if held(q := '\n'.join(x for x in (above, m.group(0).strip()) if x)): out.append(q)
    return '\n\n'.join(out)
_ASK_LINE = re.compile(r'[^\n]*\[\[\s*TASKUARY[-_ ]?ASK\s*\]\][^\n]*', re.I)


def asked_inline(text: str) -> tuple:
    """(the answer with its questions as plain lines, [(question, choices)]). THE QUESTION STAYS IN THE ANSWER: the marker line IS the question,
    and cutting the marker cut the question with it - the chat showed "the laptop spend needs your yes first" and never what to say yes to (walk
    2026-10-21). Every chat's answer reads so: a coding turn's over ACP drew the bare marker (the audit, 2026-11-10)."""
    reply, asks = ask_markers(text)
    said = '\n\n'.join(q + (f" ({' / '.join(c)})" if c else '') for q, c in asks if q not in reply)
    return '\n\n'.join(x for x in (reply, said) if x), asks


def ask_marker(text: str) -> tuple:
    """(cleaned reply, question, choices) - or (text, None, []) when the reply asks nothing structurally."""
    m = _ASK_RE.search(text or '')
    if not m: return text, None, []
    parts = [' '.join(p.split()) for p in m.group(1).split('|')]
    return text[:m.start()].rstrip(), (parts[0][:600] or None), [p[:120] for p in parts[1:] if p]
