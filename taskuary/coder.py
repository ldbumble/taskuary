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
    'Output ONLY this JSON: {"determination": "...", "actions": "...", "summary": "...", '
    '"outcome": "did_work|nothing_to_do"} - '
    'determination is what was decided and why, in plain language and at most 80 words. '
    'actions is only what was actually changed or produced (files, commands, records, ids), '
    'at most 80 words; do not repeat the determination. summary is the concrete outcome for '
    'someone who read none of the transcript: one or two natural sentences, at most 55 words, '
    'with no headings, process narration, or repetition of the other fields.\n'
    'outcome is nothing_to_do ONLY when the session changed, produced and chased nothing because there '
    'was nothing here to do at all - the message turned out to be a notice, a reminder, a newsletter or '
    "somebody else's job. Anything the session did, found out or settled for the owner is did_work, and "
    'that includes looking and reporting that the problem is not real.')


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
        rep = blank | {k: str(j.get(k) or '') for k in FIELDS}
        if not any(rep.values()): raise ValueError('empty report')
        # a flag, not prose: resolution_text never renders it, finish() reads it (see nobody_waiting).
        # Absent or unrecognised means did_work - the ending that drafts, because swallowing a reply
        # somebody is waiting for is the worse failure of the two.
        if j.get('outcome') == 'nothing_to_do': rep['outcome'] = 'nothing_to_do'
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


def reply_source(transcript: str, final_message: str = '') -> str:
    """The unabridged result the sender's reply is written from.

    The compact three-field report is for scanning the task card. It is deliberately lossy and
    must never be the only source for a reply: one 55-word summary cannot carry eight separate
    questions and their answers. Hooks give us the CLI's exact final response when they can;
    otherwise the durable readable transcript is the honest fallback and contains that ending.
    """
    final = str(final_message or '').strip()
    if final:
        return 'COMPLETE FINAL RESPONSE FROM THE WORK SESSION:\n' + final
    return 'COMPLETE WORK SESSION TRANSCRIPT (the final response is near the end):\n' + str(transcript or '').strip()


def reply_target(store, task_id: int):
    """Which message a reply answers: the last one that came IN. Our own sent mail rides in
    the chain as 'context', and answering that would mail ourselves."""
    return next((m['MessageId'] for m in reversed(store.list_messages(task_id)) if m.get('Status') != 'context'), None)


# ── the cheap ending ────────────────────────────────────────────────────────────────────
# Almost everything a keyboard can do goes to the coding agent (the owner's rule), and the
# whole bargain is that an agent with nothing to do says "nothing to do here" and stops CHEAPLY.
# It did not stop cheaply: finish() drafted a reply whatever the session found, so a CyberHoot
# training reminder came back as mail to the vendor's training bot reading "Done. This was just a
# CyberHoot training reminder, not an engineering or repo issue, so I closed it as FYI with no
# further action" - our own internal wrap-up, in our own internal words, posted to the robot that
# sent the notice (TQ-0252). Nothing about that was a reply to the sender.
def nobody_waiting(store, mid: int, rep: dict) -> bool:
    """Did this run end with nothing done, for a sender who is not waiting to hear anything back?
    Then there is no reply to write and the notice is simply filed with its report.

    BOTH halves are required, and the second is the one that keeps this honest. "Nothing to do"
    said to a PERSON who asked is still the answer they are owed - "I looked, the import is fine"
    is a reply, and swallowing it would be the worse bug. "Nothing to do" on an automated notice
    is a mailer's inbox, and whatever we write there is only ever about ourselves."""
    if rep.get('outcome') != 'nothing_to_do': return False
    from .categories import sender_class, team_domains_of
    return sender_class(store.get_message(mid) or {}, team_domains_of(store.get_settings())) != 'person'


# The server installs its conversation refresh here (PW-235): called as REFRESH(store, task_id, mid)
# before finished work becomes a reply, it reads the provider so the draft answers the thread as it
# stands. None means the freshness is UNCHECKED - said as such, never called fresh.
REFRESH = None


def no_one_behind(channel) -> bool:
    """A row Taskuary wrote itself - a report, work started here, the assistant speaking - has no
    correspondent, so there is nobody a reply could go to. Every other channel has a person behind it,
    whether or not a reply can LEAVE on it (that is outbound.can_reply's question, PW-237)."""
    from . import assistant, ownwork
    return str(channel or '').lower() in ('', 'report', ownwork.CHANNEL, assistant.CHANNEL)


def answered_elsewhere(store, msg: dict, task_id: int):
    """The owner's own line on this conversation, newer than the newest inbound message: they already
    answered from the mail client or the chat itself, so no reply is owed here (PW-235)."""
    conv = msg.get('ConversationId')
    channel = str(msg.get('Channel') or '').strip().lower()
    source = str(msg.get('SourceName') or '').strip()
    if not conv or not channel or not source: return None
    # ConversationId alone is not an account boundary. Only this channel/source
    # may discharge the reply; missing attribution leaves the draft available.
    def same_source(row):
        other = str(row.get('SourceName') or '').strip()
        return (str(row.get('Channel') or '').strip().lower() == channel
                and (other.casefold() == source.casefold() if channel == 'email' else other == source))
    from .ingest import is_ours
    latest = store.last_inbound_on_task(task_id) or msg
    cut = max(str(msg.get('SentAt') or ''), str(latest.get('SentAt') or ''))
    own = [m for m in store.thread_messages(conv)
           if same_source(m) and is_ours(m) and str(m.get('SentAt') or '') > cut]
    return own[-1] if own else None


def freshen(store, task_id: int, mid: int) -> dict:
    """Refresh the source conversation and say where the ask stands before the result becomes a reply:
    fresh | changed (a newer inbound message - the draft answers that one) | answered (the owner already
    did, elsewhere) | unresolved (the refresh failed - the draft is shown stale until one succeeds) |
    unchecked (no refresh installed)."""
    if REFRESH is None: return {'state': 'unchecked', 'mid': mid}
    try: REFRESH(store, task_id, mid)
    except Exception as e: return {'state': 'unresolved', 'mid': mid, 'error': str(e)[:200]}
    m = store.get_message(mid) or {}
    own = answered_elsewhere(store, m, task_id)
    if own: return {'state': 'answered', 'mid': mid, 'by': own}
    latest = store.last_inbound_on_task(task_id) or m
    if latest.get('MessageId') and latest['MessageId'] != mid: return {'state': 'changed', 'mid': latest['MessageId'], 'latest': latest}
    return {'state': 'fresh', 'mid': mid}


def finish(store, task_id: int, rep: dict, run_id: int = None, actor: str = 'coder',
           complete_result: str = None, owner_done: bool = False) -> dict:
    """The end of finished work: the conversation is refreshed, the ask reassessed, and the responder
    drafts the reply the sender gets from the saved result and the thread as it stands; the task waits
    on you to send it. Nothing to reply to means nothing to wait for, so it just closes."""
    # a held draft is itself proof there is someone waiting on an answer, so it names the message
    # to reply to when reply_target cannot find one (a chat thread, a promoted feed item)
    held = store.held_review(task_id) or {}
    mid = reply_target(store, task_id) or held.get('MessageId')
    can_send, block = True, ''
    if mid:
        from .outbound import can_reply, send_block
        m = store.get_message(mid) or {}
        if not can_reply(store, m.get('Channel')):
            # a report cannot be replied to (nobody sent it), but its card may name somewhere its
            # FINDINGS should go - the one configured exception to "work off a report lands on the
            # timeline and nowhere else" (reports.findings_target)
            from .reports import findings_target
            tgt = findings_target(store, m)
            if tgt:
                deliver_findings(store, task_id, mid, run_id, rep, tgt)
                store.update_task(task_id, {'Status': 'waiting'}, actor)
                return {'drafting': True, 'message_id': mid, 'can_send': True, 'send_block': '', 'freshness': 'unchecked'}
            # the always-draft rule (PW-237): a channel that cannot CARRY the reply hides Send and says why -
            # it does not hide the answer. Only a row nobody sent has nobody to answer.
            if no_one_behind(m.get('Channel')): mid = None
            else: can_send, block = False, send_block(store, m.get('Channel'))
    # the owner pressed Done (2026-09-07: "Done did not close it"): a reply that CAN go out still waits for
    # their send - dismissing it closes the task too, now that the stay-open mark comes off - but a draft
    # nobody can send does not hold a task the owner just closed
    if owner_done and mid and not can_send: mid = None
    # a held draft is proof somebody IS waiting on an answer, so it is never quietly dropped here
    if mid and not held and nobody_waiting(store, mid, rep):
        store.add_comment(task_id, actor, 'agent', 'Nothing needed doing here and the sender is not waiting on an '
                                                   'answer - filed with the report, no reply drafted.')
        mid = None
    # refresh first, draft second (PW-235): an answer the owner already sent means none is owed; a newer
    # ask is the one the reply answers; a failed refresh is shown, not assumed away
    fresh = freshen(store, task_id, mid) if mid else {'state': 'unchecked', 'mid': mid}
    if fresh['state'] == 'answered':
        by = fresh['by']
        store.add_comment(task_id, actor, 'agent', f"You already answered this thread yourself ({by.get('SentAt')}) - the result is "
                                                   'filed with the report, no reply drafted.')
        if held: store.decide_review(held['ReviewId'], 'no_reply', None, actor, 'answered from the mail client before the work finished')
        mid = None
    elif fresh['state'] == 'changed': mid = fresh['mid']
    # The terminal and report are already closed at this point. Publish that truth BEFORE the
    # reply-writing AI call: it can take seconds (or fail), and during that time the task used to
    # remain `in_progress` with no live agent. A pending review is already durable, so `waiting`
    # is honest even while its draft text is being filled in.
    store.update_task(task_id, {'Status': 'waiting' if mid else 'done'}, actor)
    if mid: raise_reply(store, task_id, mid, run_id, rep, complete_result, fresh=fresh)
    return {'drafting': bool(mid), 'message_id': mid, 'can_send': bool(mid) and can_send,
            'send_block': block if mid else '', 'freshness': fresh['state']}


def deliver_findings(store, task_id: int, mid: int, run_id: int, rep: dict, tgt: dict) -> None:
    """A report's task finished and its card names somewhere the findings should go. Same shape as
    every other outgoing message: a pending review carrying its destination, which the owner reads
    and approves. Nothing about "a report started this" makes the sending automatic."""
    from . import outbox
    rid = store.add_review({'TaskId': task_id, 'MessageId': mid, 'RunId': run_id, 'Kind': 'draft_reply',
                            'Status': 'pending', 'Deliver': json.dumps(tgt),
                            'Reason': f"the report's findings, for {tgt['to']} - approve to send"})
    try:
        draft = outbox.draft_message(store, tgt['channel'], tgt['to'],
                                     f"what we found looking into the \"{tgt['subject']}\" report", resolution_text(rep))
        store.update_review_draft(rid, draft, run_id)
    except Exception as e:
        logger.warning(f'findings draft failed for task {task_id}: {e}')


def wrap(store, tid: int, close: bool = True, actor: str = 'owner', sid: str = None,
         final_message: str = '') -> dict:
    """"We're done" - the whole ending, in one callable. The transcript becomes the report, the
    session dies, proposals become reviews, and finish() drafts the reply the sender gets.

    It lived inside the HTTP handler, which meant the ONLY way a task could be closed out was a
    person clicking Done in the browser. An agent that has finished knows it has finished long
    before anyone looks at the screen (selfclose.py), so the ending had to become something other
    than a route. Raises ValueError for the cases a caller must be told about; the route maps
    those to 422.

    Wrapping up belongs to the TASK, not to a pty: keyed on a live session it quietly vanished
    ten minutes after the CLI exited and was reaped, leaving a task that could never be closed."""
    from . import aisetup, general, proposals, terminal as term
    task = store.get_task(tid) if tid else None
    if not task: raise ValueError('this session is not on a task')
    # a setup session kept no transcript on purpose (secrets were typed into it) and has no report to write
    if task.get('Kind') == aisetup.KIND: return aisetup.finish(store, tid, actor)
    # General work already has a durable, turn-by-turn record in task comments. It does not need a
    # coding-transcript summarizer or a synthetic CODER REPORT; close the shared session and the
    # task, leaving that conversation intact.
    # The CONVERSATION is the record, not the provider session: an API turn's session is over the
    # moment it answers, and wrapping up then fell through to the coding path below and refused
    # with "no session transcript" while the whole answer sat on screen (owner, 2026-09-07).
    session = general.session_for(tid)
    if general.handles(task) and (session or general.chat_rows(store, tid)):
        if session: term.close(session.sid)
        store.audit('terminal', tid, 'wrap', actor, detail={'sid': sid or getattr(session, 'sid', None), 'close': close, 'mode': 'assistant'})
        last = next((m['content'][0]['text'] for m in reversed(general.history(store, tid)) if m['role'] == 'assistant'), '')
        # ...and then the SAME ending every other worker gets. This branch used to return
        # `drafting: False` without ever calling finish(), so a task somebody WROTE IN about closed
        # with them unanswered - while selfclose.CHAT_LINE promises the assistant that ending it
        # "drafts the answer the person who asked will get". Told that and given no drafter, the
        # assistant wrote the reply into the chat itself, in its own voice, where STYLE.md never
        # touched it and no button could send it (TQ-0443; TQ-0440/0441 closed answering nobody).
        # The conversation IS this worker's transcript, so it is what the responder drafts from.
        fin = {}
        if close and task.get('Status') not in ('done', 'dropped'):
            fin = finish(store, tid, {'summary': last}, None, 'assistant',
                         reply_source(general.conversation_text(store, tid), final_message or last),
                         owner_done=actor == 'owner') or {}
            from . import selfclose; selfclose.unclaim(store, tid, actor)
        store.add_comment(tid, actor, 'human', ('Closed the general-work session.' if session else 'Closed out the assistant conversation.')
                          + (' The reply to whoever asked is drafted for you to approve.' if fin.get('drafting')
                             else ' Marked the task done.' if close else ''))
        return {'wrap': 'done', 'taskId': tid, 'report': last, 'proposed': [],
                'drafting': bool(fin.get('drafting')), 'can_send': bool(fin.get('can_send')),
                'send_block': fin.get('send_block') or '', 'freshness': fin.get('freshness') or 'unchecked'}
    live = term.session_for(tid)
    # The agent's OWN final answer, matched to the run (PW-230): the explicit `--done` sentence recorded as the
    # run's Finished event first, then the Stop hook's last message the witness kept - never a second AI's
    # reconstruction from scrollback when the agent said it itself.
    from . import workerstate as ws
    word = ws.status(store, tid)
    spoken = str(word.get('result') or '') if word.get('state') == 'finished' and (not live or str(word.get('sid')) == str(getattr(live, 'sid', ''))) else ''
    witnessed = str(getattr(getattr(live, 'witness', None), 'said', '') or '')
    final_message = str(final_message or spoken or witnessed).strip()
    text, agent, found = term.transcript_for(store, tid)
    if not text.strip(): raise ValueError('nothing to wrap up - this task has no session transcript')
    rep = report_from_transcript(store, tid, text, agent)
    report = resolution_text(rep)
    # SAVE FIRST, close after (PW-231/233): the result, the final answer and the checklist items the agent
    # reported land before the pty goes. A save that fails raises here - the session stays, the report is
    # not written, nothing reads as finalised - and the caller may retry.
    from . import session_artifacts
    try:
        artifact = session_artifacts.coding(store, tid, report, text, agent or actor, final_message=final_message)
    except Exception as e:
        raise ValueError(f'the result could not be saved ({str(e)[:160]}) - the session was left open; try again')
    tick_reported_checklist(store, tid, final_message + '\n' + text, agent or actor)
    store.add_comment(tid, agent, 'agent', f'CODER REPORT\n{report}' + (f'\n\nLAST MESSAGE\n{final_message}' if final_message else ''))
    if found: term.close(found)              # done means done - the pty and its shells go too, once the result is safe
    store.add_comment(tid, actor, 'human', 'Closed the session - wrapped up from what was on screen.')
    # anything the agent PROPOSED becomes a pending review here, at the one moment its whole
    # transcript is in hand - and refusals are recorded rather than dropped (proposals.py)
    proposed = []
    if store.get_settings().get('proposals_enabled', '1') == '1':
        try: proposed = proposals.collect(store, tid, text, agent)
        except Exception as e: logger.warning(f'proposal collection failed for task {tid}: {e}')
    # ...and the one question worth asking the transcript that is NOT about this task: did the
    # session work out anything still true next month? Usually not, and "not" is the answer it
    # is told to give (handbook.py). A failure here never stops a task closing.
    from . import handbook
    if handbook.enabled(store):
        try: handbook.learn_from_session(store, tid, text, agent, repo=term.repo_tag(task) or '')
        except Exception as e: logger.debug(f'handbook: nothing filed for task {tid} - {e}')
    # 'drafting' must be what finish() ACTUALLY did, not a second guess at it: recomputing it from
    # reply_target alone skipped the can-this-channel-even-reply rule, so a GitHub task with
    # replies off closed with no draft while the card still promised one in Review.
    fin = {}
    if close and (store.get_task(tid) or {}).get('Status') not in ('done', 'dropped'):
        fin = finish(store, tid, rep, None, agent, reply_source(text, final_message), owner_done=actor == 'owner') or {}
        from . import selfclose; selfclose.unclaim(store, tid, actor)   # the owner ended it; the mark that kept it open has done its job
    # ...and the last question, once the report and the reply are in hand: was this a KIND of job that
    # will recur, done here for the first time? The answer is a proposal in Review, never a file
    # (playbooks.py) - the second such job matches it. Last on purpose: the receipt and the sender's
    # answer are what a close is for, and this call must never be the one the drafter's AI budget goes to.
    from . import playbooks
    pbd = playbooks.draft(store, tid, text, agent)
    if pbd: proposed.append(pbd)
    store.audit('terminal', tid, 'wrap', actor, detail={'sid': sid or found, 'close': close})
    return {'wrap': 'done', 'taskId': tid, 'report': report, 'proposed': proposed,
            'drafting': bool(fin.get('drafting')), 'can_send': bool(fin.get('can_send')), 'send_block': fin.get('send_block') or '',
            'freshness': fin.get('freshness') or 'unchecked', 'artifacts': [artifact] if artifact else []}


_TICKED = re.compile(r'^\s*(?:[-*]\s*)?\[(x|X|✓|done)\]\s*(.+?)\s*$', re.M)


def tick_reported_checklist(store, tid: int, text: str, actor: str = 'coder') -> list:
    """Tick the checklist items the agent itself reported done - a `- [x] item` line in its result or transcript
    that matches an item's words - and nothing else (PW-231). Item identities are kept; nothing is added, moved
    or blindly completed; an item the agent did not name stays open."""
    if not hasattr(store, 'task_checklist'): return []
    items = store.task_checklist(tid)
    if not items: return []
    said = {' '.join(m.group(2).split()).lower().rstrip('.') for m in _TICKED.finditer(str(text or ''))}
    ticked = []
    for it in items:
        if it.get('done'): continue
        words = ' '.join(str(it.get('text') or '').split()).lower().rstrip('.')
        if words and any(words == s or words in s or s in words for s in said):
            try: store.tick_checklist_item(tid, it['id'], True, actor); ticked.append(it['text'])
            except Exception as e: logger.debug(f'checklist tick skipped: {e}')
    if ticked: store.add_comment(tid, actor, 'agent', 'Reported done:\n' + '\n'.join(f'- [x] {t}' for t in ticked))
    return ticked


def raise_reply(store, task_id: int, mid: int, run_id: int, rep: dict,
                complete_result: str = None, fresh: dict = None) -> None:
    """The session reported; the responder writes what the sender actually reads. One voice for
    every reply the owner sends - and no coding CLI drafting prose from inside a repo. A draft
    that fails to write still leaves the review standing: 'Draft with AI' retries it.

    A reply triage already drafted from the mail alone was HELD when the session started - it
    promised what the agent had not looked at yet. That same review comes back here and is
    rewritten from the report, so the sender gets one answer, and it is the true one."""
    from . import responder
    fresh = fresh or {}
    why = 'the agent finished - the reply is rewritten from what it found'
    if fresh.get('state') == 'changed': why = 'the agent finished, and the thread moved on after the work began - the reply answers the newest message; reread it before sending'
    if fresh.get('state') == 'unresolved': why = f"the agent finished, but the conversation could not be refreshed ({fresh.get('error')}) - drafted from the saved result; refresh it before sending"
    held = store.held_review(task_id, mid) or store.held_review(task_id)
    # one review per answer (PW-236): the held triage draft, else the pending one an earlier completion
    # event already raised - a repeated completion rewrites it, never duplicates it
    live = None if held else (store.pending_review(task_id, 'draft_reply', live_only=False) or store.pending_review(task_id, 'draft', live_only=False))
    if held:
        rid = held['ReviewId']
        store.unhold_review(rid, why)
        store.update_review_reason(rid, why, run_id)
    elif live:
        rid = live['ReviewId']
        store.update_review_reason(rid, why, run_id)
    else:
        rid = store.add_review({'TaskId': task_id, 'MessageId': mid, 'RunId': run_id, 'Kind': 'draft_reply', 'Status': 'pending',
                                'Reason': why if fresh.get('state') in ('changed', 'unresolved') else 'coder finished the work - reply awaiting approval'})
    if (held or live) and (held or live).get('MessageId') != mid: store.update_review_message(rid, mid)
    src = complete_result or resolution_text(rep)
    if fresh.get('state') == 'changed' and fresh.get('latest'):
        l = fresh['latest']
        src += (f"\n\nTHE THREAD MOVED ON after the work began. Newest message from {l.get('FromName') or l.get('FromEmail') or 'them'} ({l.get('SentAt')}):\n"
                f"{str(l.get('BodyText') or '')[:800]}\nAnswer what is asked NOW; say plainly if the result above does not cover it.")
    # The report is intentionally compact UI copy. Draft from the complete final response (or
    # transcript fallback), so every question the session answered remains available here.
    try:
        try: deliver = json.loads((held or {}).get('Deliver') or '{}') or {}
        except (TypeError, ValueError): deliver = {}
        if deliver.get('channel') and deliver.get('kind') != 'zoho_invoice':
            from . import outbox
            outbox.redraft_review(store, store.get_review(rid), src)
        else:
            responder.write_draft(store, task_id, rid, src, 'coder')
    except Exception as e: logger.warning(f'reply draft failed for task {task_id}: {e}')
    # a refresh that failed is an unresolved freshness state the owner sees: the draft waits, stale, for one that succeeds
    if fresh.get('state') == 'unresolved': store.mark_review_stale(rid)
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
