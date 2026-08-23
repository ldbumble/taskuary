"""How a coding task ENDS. The work itself happens in a live session you watch (terminal.py);
this closes the loop: the transcript becomes the report, the responder drafts the reply the
sender gets, and the task waits on you to send it.
"""
import json, re
from loguru import logger

FIELDS = ('determination', 'actions', 'summary')


TRANSCRIPT_SYSTEM = (
    'You are reading the terminal transcript of a coding agent that has just worked a task for '
    "the owner, who has now closed the session. Write the owner's record of what happened, from "
    'the transcript ALONE - never a step it did not take, never a claim it did not make.\n'
    'Output ONLY this JSON: {"determination": "...", "actions": "...", "summary": "..."} - '
    'determination is what was decided and why, actions is what was actually changed (files, '
    'commands, records, ids), summary is the two-sentence version for someone who read none of it.')


def report_from_transcript(store, task_id: int, transcript: str, agent: str = 'coder') -> dict:
    """The report, written from what is already on screen. The agent is never asked for prose:
    by the time you click Done you are done talking to it, and a transcript cannot argue. No AI
    configured (or a bad answer) files the transcript tail itself - the record never disappears."""
    from .llm import build_llm
    blank = dict.fromkeys(FIELDS, '')
    if not (transcript or '').strip(): return blank | {'summary': '(the session ended with nothing on screen)'}
    try:
        llm = build_llm(store)
        if not llm: raise RuntimeError('no AI connector is set up to write the report')
        out = llm(TRANSCRIPT_SYSTEM, f"Task: {(store.get_task(task_id) or {}).get('Title') or ''}\n\n"
                                     f'Transcript:\n{transcript}', max_tokens=900)
        j = json.loads(re.sub(r'^```(json)?|```$', '', (out or '').strip(), flags=re.M))
        rep = blank | {k: str(j.get(k) or '') for k in ('determination', 'actions', 'summary')}
        if not any(rep.values()): raise ValueError('empty report')
        return rep
    except Exception as e:
        logger.warning(f'transcript report failed for task {task_id}: {e}')
        return blank | {'summary': transcript[-2000:]}


PAUSE_MARKER = 'HANDOVER NOTE'
PAUSE_SYSTEM = (
    'You are reading the terminal transcript of a coding agent that has been PAUSED mid-task - the '
    'owner is stopping for now and the same work will be picked up later, by an agent with no memory '
    'of this session. Write the handover note it will be given. From the transcript ALONE.\n'
    'Output ONLY this JSON: {"found": "...", "did": "...", "next": "..."} - found is what it worked '
    'out about the problem (causes, file and record names, ids, dead ends worth not repeating), did '
    'is what it already changed, next is the concrete next step it was about to take. Say "nothing '
    'yet" in a field rather than inventing.')


def pause_note(store, task_id: int, transcript: str) -> str:
    """What a paused session knew, in the words the next session needs. A pty has no resumable
    id (no --resume for a TUI), so the note IS the continuity - it gets typed into the next
    session by terminal.seed_text. No AI, or a bad answer, keeps the transcript tail instead."""
    from .llm import build_llm
    if not (transcript or '').strip(): return 'Nothing on screen - the session was paused before it did anything.'
    try:
        llm = build_llm(store)
        if not llm: raise RuntimeError('no AI connector is set up to write the note')
        out = llm(PAUSE_SYSTEM, f"Task: {(store.get_task(task_id) or {}).get('Title') or ''}\n\n"
                                f'Transcript:\n{transcript}', max_tokens=900)
        j = json.loads(re.sub(r'^```(json)?|```$', '', (out or '').strip(), flags=re.M))
        note = '\n'.join(f'{k.capitalize()}: {j[k]}' for k in ('found', 'did', 'next') if str(j.get(k) or '').strip())
        if not note: raise ValueError('empty note')
        return note
    except Exception as e:
        logger.warning(f'pause note failed for task {task_id}: {e}')
        return f'(no AI note - the last of the session, verbatim)\n{transcript[-2000:]}'


def resolution_text(rep: dict) -> str:
    return '\n'.join(f'{k.capitalize()}: {rep[k]}' for k in ('determination', 'actions', 'summary') if rep.get(k))


def reply_target(store, task_id: int):
    """Which message a reply answers: the last one that came IN. Our own sent mail rides in
    the chain as 'context', and answering that would mail ourselves."""
    return next((m['MessageId'] for m in reversed(store.list_messages(task_id)) if m.get('Status') != 'context'), None)


def finish(store, task_id: int, rep: dict, run_id: int = None, actor: str = 'coder') -> dict:
    """The end of finished work: the responder drafts the reply the sender gets and the task waits
    on you to send it. Nothing to reply to means nothing to wait for, so it just closes."""
    # a held draft is itself proof there is someone waiting on an answer, so it names the message
    # to reply to when reply_target cannot find one (a chat thread, a promoted feed item)
    held = store.held_review(task_id) or {}
    mid = reply_target(store, task_id) or held.get('MessageId')
    # can this channel carry a reply at all? outbound.can_reply is the ONE answer - the
    # owner's per-channel setting, plus the rules that are not theirs to change (a public
    # GitHub comment needs that card's switch; a tracker is read-only by design). With it
    # off, finished work just closes: the report lands on the task, no dead-end draft.
    if mid:
        from .outbound import can_reply
        if not can_reply(store, (store.get_message(mid) or {}).get('Channel')): mid = None
    if mid: raise_reply(store, task_id, mid, run_id, rep)
    store.update_task(task_id, {'Status': 'waiting' if mid else 'done'}, actor)
    return {'drafting': bool(mid), 'message_id': mid}


def raise_reply(store, task_id: int, mid: int, run_id: int, rep: dict) -> None:
    """The session reported; the responder writes what the sender actually reads. One voice for
    every reply the owner sends - and no coding CLI drafting prose from inside a repo. A draft
    that fails to write still leaves the review standing: 'Draft with AI' retries it.

    A reply triage already drafted from the mail alone was HELD when the session started - it
    promised what the agent had not looked at yet. That same review comes back here and is
    rewritten from the report, so the sender gets one answer, and it is the true one."""
    from . import responder
    held = store.held_review(task_id, mid) or store.held_review(task_id)
    if held:
        rid = held['ReviewId']
        store.unhold_review(rid, 'the agent finished - the reply is rewritten from what it found')
        store.update_review_reason(rid, 'the agent finished - the reply is rewritten from what it found', run_id)
    else:
        rid = store.add_review({'TaskId': task_id, 'MessageId': mid, 'RunId': run_id, 'Kind': 'draft_reply',
                                'Status': 'pending', 'Reason': 'coder finished the work - reply awaiting approval'})
    try: responder.write_draft(store, task_id, rid, resolution_text(rep), 'coder')
    except Exception as e: logger.warning(f'reply draft failed for task {task_id}: {e}')
    # the ping that matters most: work FINISHED and its reply is sitting in Review on you
    if (store.get_settings().get('notify_level') or 'needs_me') != 'off':
        from .outbound import notify
        from .phone import ping_tail
        from .store import task_ref
        t = store.get_task(task_id) or {}
        head = (t.get('Title') or '')[:100]
        # with phone approvals on, the ping carries the draft and the [rvN] tag - replying
        # 'approve' in the chat sends it (phone.py), so 'done' really can mean done
        tail = ping_tail(store, rid, (store.get_review(rid) or {}).get('DraftText'))
        try: notify(store, f'{task_ref(task_id)} is done - the reply is drafted and waiting on '
                           f'your approval in Review.\n{head}{tail}')
        except Exception as e: logger.warning(f'notify failed for task {task_id}: {e}')
