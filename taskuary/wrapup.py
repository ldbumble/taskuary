"""How a coding task ENDS. The work itself happens in a live session you watch (terminal.py);
this closes the loop: the transcript becomes the report, the responder drafts the reply the
sender gets, and the task waits on you to send it.
"""
import json, re, threading
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


def report_from_transcript(store, task_id: int, transcript: str, agent: str = '', final_message: str = '') -> dict:
    """The report, written from what is already on screen. The agent is never asked for prose:
    by the time you click Done you are done talking to it, and a transcript cannot argue. No AI
    configured (or a bad answer) files the agent's own last word, or says plainly that there is no summary - never the screen
    itself: "Summary: ● Bash(cd ...; gh pr view ..." was filed as a report (TQ-1112 shape, 2026-10-16). The record does not
    disappear for it - the transcript is kept with the session (terminal's transcript row)."""
    from .llm import build_llm
    blank = dict.fromkeys(FIELDS, '')
    if not (transcript or '').strip(): return blank | {'summary': '(the session ended with nothing on screen)'}
    try:
        llm = build_llm(store, job='summary')
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
        last = ' '.join(str(final_message or '').split())
        return blank | {'summary': last[:1200] if last else
                        f'No summary could be written ({str(e)[:120]}) - the session transcript is kept with the task.'}


# The note a finished session files. It was named for one special profile, and no profile is special (the owner, 2026-10-15);
# databases still hold the old marker, so every reader takes both.
REPORT = 'AGENT REPORT'
REPORTS = (REPORT, 'CODER REPORT')
REPORT_RE = re.compile(r'^(?:AGENT|CODER) REPORT')
def is_report(body) -> bool: return str(body or '').startswith(REPORTS)
def report_body(body) -> str: return REPORT_RE.sub('', str(body or ''), count=1).strip()

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
        llm = build_llm(store, job='summary')
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
    the chain as 'context', and answering that would mail ourselves; a chat app's mail copy of a
    chat line rides as 'skipped', and answering that mails its no-reply address. And the last one SOMEBODY sent: a report
    joined onto the task (the End of day checkup) became the newest row, so the session's reply to the colleague who had
    written again went to "nobody" and was filed as a result (2026-10-13). Only a task with nobody behind any row gets one."""
    rows = [m for m in reversed(store.list_messages(task_id)) if m.get('Status') not in ('context', 'skipped')]
    return next((m['MessageId'] for m in rows if not no_one_behind(m.get('Channel'))), rows[0]['MessageId'] if rows else None)


# ── the agent's own words ───────────────────────────────────────────────────────────────
# The agent that did the work often writes the better answer: it knows what it found, and a second
# model redrafting from its transcript loses the nuance (the owner, 2026-09-23: "sometimes the agent
# that did the work is better for response than another ai generating it based off of transcript").
# It used to have no way to hand that answer over - it asked "should I draft the reply?", wrote it
# on its own screen, and the task's reply stayed empty until the responder wrote a different one.
# Now it says so: `taskuary --reply` (a shell) or a [[TASKUARY-REPLY]] block (the general chat), the
# text becomes the task's pending reply as written, and the end of the run keeps it.
AGENT_DRAFT = 'agent:'

def agent_drafted(rv) -> bool:
    return bool(rv) and str(rv.get('DraftBy') or '').startswith(AGENT_DRAFT) and bool(str(rv.get('DraftText') or '').strip())


def own_draft(store, task_id: int):
    """The pending reply the agent wrote itself, if there is one."""
    return next((r for r in (store.pending_review(task_id, 'draft_reply', live_only=False),
                             store.pending_review(task_id, 'draft', live_only=False)) if agent_drafted(r)), None)


def attach_files(store, rid: int, files, agent: str = 'agent') -> dict:
    """The files the agent hands over with its words (`--attach PATH`) ride on that same review.

    A session rebuilt a workbook, wrote "the list is attached (….xlsx)" and the card said nothing was
    attached: `--reply` carried words only, so the file it made stayed on its disk and the promise went
    out empty. Each file goes through verdicts.attach - the owner's own Attach button - so the size cap
    and the delivery lock hold, and a file that cannot ride says why instead of vanishing."""
    from . import verdicts
    done, why = [], []
    for name, data in files or []:
        try: verdicts.attach(store, rid, name, data, agent); done.append(name)
        except ValueError as e: why.append(f'{name}: {e}')
    return {'attached': done, 'not_attached': why}


def _words(t) -> str: return re.sub(r'\s+', ' ', str(t or '')).strip().lower()
def _at(rv) -> str: return f" at {str(rv.get('DecidedAt'))[11:16]} on {str(rv.get('DecidedAt'))[:10]}" if rv.get('DecidedAt') else ''


def already_sent(store, task_id: int, text: str):
    """The reply on this task that went out with these very words (spacing aside), if one did."""
    w = _words(text)
    return next((r for r in store._rows("SELECT * FROM review WHERE TaskId=? AND Status IN ('approved','edited','sent') "
                                        "ORDER BY ReviewId DESC", (task_id,))
                 if w and w in (_words(r.get('FinalText')), _words(r.get('DraftText')))), None)


# ── one answer per message ──────────────────────────────────────────────────────────────
# The agent drafted the reply, the owner sent it, the owner pressed Continue, and the agent drafted ANOTHER reply to the same
# sender - nothing had come from them since, so it sat in Close out as if the first message were still unanswered (the owner,
# 2026-10-20: "I replied with what the agent created, then reran the agent and it recreated some reply???"). A message the
# work's answer already went to is answered; a second letter to it is a follow-up, said so, and only when the owner asked.
FOLLOW_UP = 'a follow-up to your '
def is_follow_up(rv) -> bool: return str((rv or {}).get('Reason') or '').startswith(FOLLOW_UP)


def answered_by_work(store, task_id: int, mid):
    """The reply already sent to `mid` that carried the work's answer - the agent wrote it, or it went after the agent had
    reported - else None. An acknowledgement the owner sent BEFORE any work ("looking into it") answers nothing yet."""
    rv = store.sent_reply(message_id=mid) if mid else None
    if not rv: return None
    if agent_drafted(rv): return rv
    at = str(rv.get('DecidedAt') or rv.get('CreatedAt') or '')
    worked = lambda c: c.get('ActorType') == 'assistant_agent' or str(c.get('Body') or '').startswith((*REPORTS, PAUSE_MARKER))
    return rv if any(worked(c) and str(c.get('CreatedAt') or '') <= at for c in store.list_comments(task_id)) else None


def owner_asked_since(store, task_id: int, at: str) -> bool:
    """Did the owner write to this task's agent after `at` - their own words in its conversation, never a canned prompt?"""
    from .general import USER_TYPE
    return any(c.get('ActorType') == USER_TYPE and str(c.get('CreatedAt') or '') > str(at or '') for c in store.list_comments(task_id))


def agent_reply(store, task_id: int, text: str, agent: str = 'agent', run_id: int = None, files=None, follow_up: bool = False) -> dict:
    """Put the agent's reply on the task as the pending draft - the same review the responder would
    write into (held, live or new; one per answer, PW-236), marked as the agent's. Nothing is sent:
    the owner approves it like every other reply. `files` are (name, bytes) pairs to attach; with no
    text they go on the reply already pending - an agent that forgot the file adds it afterwards.
    A message the work's answer already went to takes another only as a follow-up: `follow_up` (the agent says the owner
    asked for it) or the owner's own words in the conversation since the send."""
    text = str(text or '').strip()
    if not text and files:
        rv = store.pending_review(task_id, 'draft_reply', live_only=False) or store.pending_review(task_id, 'draft', live_only=False)
        if not rv: return {'ok': False, 'why': 'there is no pending reply to attach to - save one with --reply first'}
        return {'ok': True, 'review_id': rv['ReviewId'], **attach_files(store, rv['ReviewId'], files, agent)}
    if not text: return {'ok': False, 'why': 'no reply text'}
    # THE SAME LETTER TWICE IS A MISTAKE, never a new draft: a resumed session saved its first session's reply again after the
    # owner had sent it, and it went back on the table aimed at the sender's "Thanks!" (2026-10-16) - one press from a resend
    if (sent := already_sent(store, task_id, text)):
        store.add_comment(task_id, agent, 'agent', f'{agent} saved a reply that already went out{_at(sent)} - nothing new was put on the table.')
        return {'ok': False, 'already_sent': True, 'review_id': sent['ReviewId'],
                'why': f'that reply already went out{_at(sent)} - nothing new was saved. Write a new one only if there is something new to say.'}
    held = store.held_review(task_id) or {}
    mid = reply_target(store, task_id) or held.get('MessageId')
    # work the owner started here (a brief typed in the chat) has only their own words behind it: the agent's
    # answer IS the result, and filing it as a reply "waiting on your approval" addressed it to them (2026-09-23).
    # Refusing it outright threw the answer away - a whole review the owner asked for, gone (2026-10-06) - so keep it.
    if not mid or (not held and no_one_behind((store.get_message(mid) or {}).get('Channel'))):
        from . import session_artifacts
        art = session_artifacts.result(store, task_id, text, agent)
        store.add_comment(task_id, agent, 'agent', f'{agent} saved its answer on the task as the result - nobody is waiting on a reply, so nothing will be sent.')
        return {'ok': True, 'saved': 'result', 'artifact_id': art.get('ArtifactId'),
                'not_attached': [f'{n}: nobody is waiting on a reply, so there is nothing to attach it to' for n, _ in files or []]}
    sent = answered_by_work(store, task_id, mid)
    if sent and not (follow_up or owner_asked_since(store, task_id, sent.get('DecidedAt'))):
        from .continuity import clock, sent_to
        to, at = sent_to(store, sent), clock(sent.get('DecidedAt'))
        store.add_comment(task_id, agent, 'agent', f'{agent} tried to save another reply to {to}, but yours went at {at} and nothing new came from them since - '
                                                   'nothing was put on the table.')
        return {'ok': False, 'already_answered': True, 'review_id': sent['ReviewId'],
                'why': f'a reply to {to} already went at {at}, and nothing new has come from them since - nothing was saved. '
                       'Draft another only if the owner asked you to, and then say so: `taskuary --follow-up --reply "<text>"`.'}
    live = None if held else (store.pending_review(task_id, 'draft_reply', live_only=False) or store.pending_review(task_id, 'draft', live_only=False))
    why = f'{agent} wrote this reply in its session - approve to send'
    if sent:
        from .continuity import clock
        why = f'{FOLLOW_UP}{clock(sent.get("DecidedAt"))} reply - {agent} wrote it in its session; approve to send'
    if held:
        rid = held['ReviewId']; store.unhold_review(rid, why)
    elif live:
        rid = live['ReviewId']; store.update_review_reason(rid, why, run_id)
    else:
        rid = store.add_review({'TaskId': task_id, 'MessageId': mid, 'RunId': run_id, 'Kind': 'draft_reply', 'Status': 'pending', 'Reason': why})
    rv = store.get_review(rid) or {}
    if rv.get('MessageId') != mid: store.update_review_message(rid, mid)
    store.update_review_draft(rid, text, run_id or rv.get('RunId'), by=AGENT_DRAFT + agent)
    store.add_comment(task_id, agent, 'agent', f'{agent} drafted the reply itself - it is on the task, waiting on your approval.')
    return {'ok': True, 'review_id': rid, 'message_id': mid, **attach_files(store, rid, files, agent)}


# ── the cheap ending ────────────────────────────────────────────────────────────────────
# Almost everything a keyboard can do goes to the coding agent (the owner's rule), and the
# whole bargain is that an agent with nothing to do says "nothing to do here" and stops CHEAPLY.
# It did not stop cheaply: finish() drafted a reply whatever the session found, so a PhishGuard
# training reminder came back as mail to the vendor's training bot reading "Done. This was just a
# PhishGuard training reminder, not an engineering or repo issue, so I closed it as FYI with no
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
    from .ingest import is_ack, is_ours
    latest = store.last_inbound_on_task(task_id) or msg
    cut = max(str(msg.get('SentAt') or ''), str(latest.get('SentAt') or ''))
    # ...and Taskuary's own "On it - I'll get back to you here." is a promise that an answer is COMING, never the
    # answer. Counted as one, every chat task read as already answered: the agent's finished reply was dropped and
    # the task closed with the sender waiting (TQ-0731, the owner, 2026-09-24: "this task closed and did not
    # create pending reply?")
    own = [m for m in store.thread_messages(conv)
           if same_source(m) and is_ours(m) and not is_ack(store, m) and str(m.get('SentAt') or '') > cut]
    return own[-1] if own else None


def _owners_own(store, m: dict) -> bool:
    """The message is the owner writing, on a channel that names its author by login (GitHub today)."""
    if str(m.get('Channel') or '').lower() != 'github': return False
    from .whoami import github_logins
    return str(m.get('FromName') or '').strip().lower() in github_logins(store)


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


def finish(store, task_id: int, rep: dict, run_id: int = None, actor: str = 'agent',
           complete_result: str = None, owner_done: bool = False, keep_open: bool = False, no_reply: bool = False) -> dict:
    """The end of finished work: the conversation is refreshed, the ask reassessed, and the responder
    drafts the reply the sender gets from the saved result and the thread as it stands; the task waits
    on you to send it. Nothing to reply to means nothing to wait for, so it just closes.

    `keep_open` is ENDING THE RUN without ending the task: everything here still happens - the
    refresh, the reassessment, the draft - and the task's own status is left exactly as it was. The
    session's end is not a verdict on the work."""
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
                if not keep_open: store.update_task(task_id, {'Status': 'waiting'}, actor)
                return {'drafting': True, 'message_id': mid, 'can_send': True, 'send_block': '', 'freshness': 'unchecked'}
            # the always-draft rule (PW-237): a channel that cannot CARRY the reply hides Send and says why -
            # it does not hide the answer. Only a row nobody sent has nobody to answer.
            if no_one_behind(m.get('Channel')): mid = None
            else: can_send, block = False, send_block(store, m.get('Channel'))
    # the owner pressed Done (2026-09-07: "Done did not close it"): a reply that CAN go out still waits for
    # their send - dismissing it closes the task too, now that the stay-open mark comes off - but a draft
    # nobody can send does not hold a task the owner just closed
    if owner_done and mid and not can_send: mid = None
    # ...and when its pull request ended it (merged or closed), nobody is owed an answer (A21, 2026-09-25)
    if no_reply: mid = None
    # ...nor when the ask is the OWNER's own: an issue they opened on their own repository came back from the agent with
    # a reply drafted to themselves (the owner, 2026-09-25: "why is there reply on issue?")
    if mid and _owners_own(store, store.get_message(mid) or {}):
        store.add_comment(task_id, actor, 'agent', 'You opened this yourself - the result is filed with the report, no reply drafted.')
        mid = None
    # ...nor when the agent already WROTE the email this needed (slots.draft): "hand it off to her" came back as that email AND,
    # seconds later, a reply-all to the original sender beside it - two drafts on one task (the owner, 2026-10-08: "why is there
    # 2 emails??"). A held triage draft still stands: that is somebody waiting.
    from . import slots
    if mid and not held and slots.written(store, task_id):
        store.add_comment(task_id, actor, 'agent', 'The agent wrote the email this needed - no reply to the original sender drafted.')
        mid = None
    # a held draft is proof somebody IS waiting on an answer, so it is never quietly dropped here
    if mid and not held and not own_draft(store, task_id) and nobody_waiting(store, mid, rep):
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
    # ...and a message the work's answer already WENT to, with nothing new from them since, is owed nothing more: a Continue
    # after the owner sent the agent's reply ended with a second reply to the same sender waiting in Close out (2026-10-20)
    if mid and not held and not own_draft(store, task_id) and (sent := answered_by_work(store, task_id, mid)):
        from .continuity import clock, sent_to
        store.add_comment(task_id, actor, 'agent', f'Your reply to {sent_to(store, sent)} already went at {clock(sent.get("DecidedAt"))} and nothing '
                                                   'new came from them since - the result is filed with the report, no second reply drafted.')
        mid = None
    # The terminal and report are already closed at this point. Publish that truth BEFORE the
    # reply-writing AI call: it can take seconds (or fail), and during that time the task used to
    # remain `in_progress` with no live agent. A pending review is already durable, so `waiting`
    # is honest even while its draft text is being filled in.
    # THE CLOSE-OUT (the owner, 2026-09-27: "it's not closed until then"): a task whose work is an open pull request
    # is finished by merging it, one from an issue by closing it - each waits for the owner's yes like the reply does.
    # Not on an upstream that already ended it, or the owner's own Mark done (that IS the close) - nor on a session only
    # saved, UNLESS it wrote the answer: a drafted reply says the work is done, and it comes with its merge (TQ-0767).
    from . import proposals
    due = None if ((keep_open and not mid) or no_reply or owner_done) else proposals.closeout_due(store, task_id)
    # ...and its emails (slots.py): `done` supersedes every pending draft, so a run that leaves some owed waits instead
    from . import slots
    # ...and its proposals: `done` supersedes every pending review, so a bill the agent proposed for the owner's yes was
    # cancelled by the agent's own finish before anyone saw it (the AP portal workflow, live, 2026-10-08). The owner's Mark
    # done is still the owner's decision and closes as it always did; the last proposal answered puts it back on them (settle).
    asks = not owner_done and not keep_open and proposals.owed(store, task_id)
    if asks: store.audit('task', task_id, 'awaits_proposals', actor)
    if not keep_open: store.update_task(task_id, {'Status': 'waiting' if (mid or due or asks or slots.open_(store, task_id)) else 'done'}, actor)
    # the newest pending review is the one shown first: a merge leads its reply (the reply can then say it is merged),
    # a comment on an issue leads its close - and when a reply carries the comment, the close adds none
    if due and due['action'] == 'close_issue': proposals.closeout(store, task_id, due, '' if mid else resolution_text(rep), actor)
    if mid: raise_reply(store, task_id, mid, run_id, rep, complete_result, fresh=fresh)
    if due and due['action'] == 'merge_pr': proposals.closeout(store, task_id, due, '' if due.get('theirs') else resolution_text(rep), actor)
    return {'drafting': bool(mid), 'message_id': mid, 'can_send': bool(mid) and can_send,
            'send_block': block if mid else '', 'freshness': fresh['state'], 'closeout': (due or {}).get('action')}


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
                                     f"what we found looking into the \"{tgt['subject']}\" report", resolution_text(rep), mailbox=tgt.get('mailbox'))
        store.update_review_draft(rid, draft, run_id)
    except Exception as e:
        logger.warning(f'findings draft failed for task {task_id}: {e}')


def _ended(store, tid: int, close: bool, actor: str):
    """The session is over by the owner's (or the agent's) decision. With the task kept open that is `session saved`: its
    result is written, nobody is working it, and it is not "left without finishing" (A1/A2, 2026-09-25). The pty's own
    end no longer reopens the task (terminal.close is on purpose), so the status is set here."""
    from . import terminal as term
    if close: return
    store.tag_task(tid, term.SAVED, True, actor)
    if (store.get_task(tid) or {}).get('Status') == 'in_progress': store.update_task(tid, {'Status': 'open'}, actor)


def wrap(store, tid: int, close: bool = True, actor: str = 'owner', sid: str = None,
         final_message: str = '', no_reply: bool = False, harvested: dict = None, on_harvest=None) -> dict:
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
    if task.get('SourceRef') == aisetup.WALK_REF: return aisetup.finish_walk(store, tid, actor)      # a card's walk: its Test was the report
    # General work already has a durable, turn-by-turn record in task comments. It does not need a
    # coding-transcript summarizer or a synthetic AGENT REPORT; close the shared session and the
    # task, leaving that conversation intact.
    # The CONVERSATION is the record, not the provider session: an API turn's session is over the
    # moment it answers, and wrapping up then fell through to the coding path below and refused
    # with "no session transcript" while the whole answer sat on screen (owner, 2026-09-07).
    session = general.session_for(tid)
    if general.handles(task) and (session or general.chat_rows(store, tid)):
        if session: term.close(session.sid)
        store.audit('terminal', tid, 'wrap', actor, detail={'sid': sid or getattr(session, 'sid', None), 'close': close, 'mode': 'assistant'})
        last = next((m['content'][0]['text'] for m in reversed(general.history(store, tid)) if m['role'] == 'assistant'), '')
        # THE RESULT IS FILED, NOT JUST HANDED BACK. This branch returned `report: last` to whoever
        # called it and wrote nothing but a human note, so pressing save on a conversation (now "Stop and save")
        # left no result anywhere: the card still read `in conversation`, the button was still on
        # offer, and every reader of a task's outcome - the pipe's line, the responder's draft, the
        # next session's context - looks for an AGENT REPORT comment and found none (the owner,
        # 2026-09-17: "save the conversation result does nothing?").
        # It is still not a SUMMARY: nothing is asked of a model here, and no transcript is boiled
        # down. The answer the assistant already gave is filed verbatim, under the one marker every
        # reader shares, which is exactly what the button's words promise.
        general.report_note(store, tid)          # ...the same note a chat that ends any other way files (general.close)
        # ...and then the SAME ending every other worker gets. This branch used to return
        # `drafting: False` without ever calling finish(), so a task somebody WROTE IN about closed
        # with them unanswered - while selfclose.CHAT_LINE promises the assistant that ending it
        # "drafts the answer the person who asked will get". Told that and given no drafter, the
        # assistant wrote the reply into the chat itself, in its own voice, where STYLE.md never
        # touched it and no button could send it (TQ-0443; TQ-0440/0441 closed answering nobody).
        # The conversation IS this worker's transcript, so it is what the responder drafts from.
        fin = {}
        if task.get('Status') not in ('done', 'dropped'):
            _stage(tid, 'reply')
            fin = finish(store, tid, {'summary': last}, None, 'assistant',
                         reply_source(general.conversation_text(store, tid), final_message or last),
                         owner_done=close and actor == 'owner', keep_open=not close, no_reply=no_reply) or {}
            if close:
                from . import selfclose; selfclose.unclaim(store, tid, actor)
        store.add_comment(tid, actor, 'human', ('Closed the general-work session.' if session else 'Closed out the assistant conversation.')
                          # the draft is only ASKED FOR here; its writer runs after this line and may find nothing needs to go back.
                          # "is drafted for you to approve" was said over three closes that drafted nothing (the owner, 2026-10-14)
                          + (' The reply to whoever asked is being written - it waits for your approval, or the task says why none is needed.'
                             if fin.get('drafting')
                             # say what the task IS: a proposal left for the owner keeps it waiting (finish), not done
                             else ' The task waits for your answer to what the agent proposed.' if close and (store.get_task(tid) or {}).get('Status') == 'waiting'
                             else ' Marked the task done.' if close else ''))
        # ...and the playbook question, asked of THIS worker too. Only the coding ending asked it, so the jobs playbooks are for -
        # a bill, a W-9, a month-end reconciliation, all general work - never drafted one: "the first real one is drafted for you
        # when an agent finishes a kind of job for the first time" held for code alone (walk 2026-10-21). Last, as there.
        from . import playbooks
        # a playbook-authoring conversation already proposed its playbook, by hand (playbooks.setup_task): never a second draft of it
        # ...and it reads what ARRIVED beside what was said: a playbook's `when` is the arriving message, which the conversation
        # opens on only as triage's one-line title - and the chat alone of a crisp answer fell under playbooks.MIN_SESSION, so a
        # month-end reconciliation was never even put to the model (walk 2026-10-21)
        arrived = '\n\n'.join(f"ARRIVED from {m.get('FromName') or m.get('FromEmail') or 'someone'}: {m.get('Subject') or ''}\n"
                              f"{str(m.get('BodyText') or '')[:3000]}" for m in ((store.task_detail(tid) or {}).get('messages') or [])[:3])
        job = '\n\n'.join(x for x in (arrived, general.conversation_text(store, tid)) if x)
        pbd = None if task.get('SourceRef') == 'assistant:playbook' else playbooks.draft(store, tid, job, 'assistant')
        if proposals.playbook_pending(store, tid): proposals.hold_for_playbook(store, tid, 'assistant')     # always in sight
        _ended(store, tid, close, actor)
        return {'wrap': 'done', 'taskId': tid, 'report': last, 'proposed': [pbd] if pbd else [],
                'drafting': bool(fin.get('drafting')), 'can_send': bool(fin.get('can_send')),
                'send_block': fin.get('send_block') or '', 'freshness': fin.get('freshness') or 'unchecked'}
    if harvested:          # harvested already - by a write-up that was interrupted (writeup.resume): the session is gone
        text, agent, found, final_message, cut = (harvested[k] for k in ('text', 'agent', 'found', 'final_message', 'cut'))
    else: text, agent, found, final_message, cut = _harvest(store, tid, final_message)
    if not text.strip(): raise ValueError('nothing to wrap up - this task has no session transcript')
    if on_harvest: on_harvest({'text': text, 'agent': agent, 'found': found, 'final_message': final_message, 'cut': cut})
    # ONE SESSION, ONE ENDING (TQ-1112 shape): a settle retried while the first ending was still writing wrapped the same session
    # again, and twice more - two AGENT REPORTs, the second from a screen already gone. A wrap of a session being wrapped now does
    # nothing; one wrapped before only closes the task, if this caller asks for that and it is still open.
    return _wrap_once(store, tid, task, close, actor, sid, final_message, no_reply, text, agent, found, cut)


def _stage(tid, name):
    "The background write-up running this ending says where it is (writeup.stage); any other caller says nothing."
    from . import writeup; writeup.stage(tid, name)


def _harvest(store, tid, final_message) -> tuple:
    """(transcript, agent, session id, final message, cut off) - everything a wrap reads off the live session, taken before the
    session is closed."""
    from . import terminal as term
    live = term.session_for(tid)
    # The agent's OWN final answer, matched to the run (PW-230): the explicit `--done` sentence recorded as the
    # run's Finished event first, then the Stop hook's last message the witness kept - never a second AI's
    # reconstruction from scrollback when the agent said it itself.
    from . import workerstate as ws
    word = ws.status(store, tid)
    spoken = str(word.get('result') or '') if word.get('state') == 'finished' and (not live or str(word.get('sid')) == str(getattr(live, 'sid', ''))) else ''
    # ...never a turn the owner has moved past: closed while it worked on the next prompt, the session's "last message" was the
    # turn BEFORE it, and the record contradicted its own report (witness.said_now / cut_off, TQ-1112 shape)
    wit = getattr(live, 'witness', None)
    now_, cut_ = getattr(wit, 'said_now', None), getattr(wit, 'cut_off', None)
    witnessed = now_() if callable(now_) else getattr(wit, 'said', '')
    witnessed = witnessed if isinstance(witnessed, str) else ''
    # ...live or not: a session that died on its own mid-turn was cut off just the same, and its object (kept until reaped) still
    # holds the witness that says so (batch: a close waiting on the turn when the CLI crashed)
    cut = live is not None and callable(cut_) and cut_() is True and not spoken
    # ...and the whole final TURN beside it (witness.turn_text): a `--done` sentence is a summary, and the reply the agent wrote
    # just before it was in neither - the drafter wrote a placeholder from "the reply above is ready" (2026-10-13)
    spoken, witnessed = spoken.strip(), witnessed.strip()
    turn = witnessed + (f'\n\n{spoken}' if spoken and spoken not in witnessed else '') if witnessed else spoken
    if cut and not final_message: turn = (turn + '\n\n' if turn else '') + CUT_OFF
    final_message = str(final_message or turn).strip()
    text, agent, found = term.transcript_for(store, tid)
    return text, agent, found, final_message, cut


def _wrap_once(store, tid, task, close, actor, sid, final_message, no_reply, text, agent, found, cut) -> dict:
    key = (id(store), str(found)) if found else None
    if key:
        with _WRAP_LOCK:
            if key in _ACTIVE: return {'wrap': 'already', 'taskId': tid, 'report': '', 'proposed': []}
            before = _wrapped_before(store, tid, key[1])
            if not before: _ACTIVE[key] = tid
        if before: return _close_again(store, tid, close, actor, agent, text, no_reply)
    try: out = _wrap_session(store, tid, task, close, actor, sid, final_message, no_reply, text, agent, found, cut)
    except BaseException:
        with _WRAP_LOCK: _ACTIVE.pop(key, None)
        raise
    with _WRAP_LOCK: _ACTIVE.pop(key, None)
    return out


# THE THREE QUESTIONS AT ONCE, THE ANSWERS IN ORDER (2026-10-20): a wrap asked the report, then the handbook, then the playbook
# question one after another - 18 s of a Mark done with a 6-second brain. The handbook and playbook questions do not depend on
# the report: each is asked AHEAD, beside it, exactly as it will be asked (the real function is run up to its question, which
# is caught and not answered - _question). At its own place in the ending each function runs as it always did, and when it
# asks the very question that was asked ahead it gets that answer; anything it asks differently - the state moved - is asked
# then, as before. So what is written, and in what order, is today's. At most two are asked ahead at a time (with the report
# beside them, three at once for a CLI brain).
_AHEAD = None
_AHEAD_LOCK = threading.Lock()


class _Asked(BaseException):
    """A question caught before it is put: BaseException, so the functions' own `except Exception` lets it through."""


def _question(fn, *args, **kwargs):
    """(system, user, kwargs) of the question fn would put to the brain now - or None when it would put none."""
    asked = []
    def record(system, user, **kw):
        asked.append((system, user, tuple(sorted(kw.items())))); raise _Asked()
    try: fn(*args, llm=record, **kwargs)
    except _Asked: pass
    return asked[0] if asked else None


def _ask_ahead(store, questions: list) -> dict:
    """{question: future answer} for each question, asked on the shared pool."""
    global _AHEAD
    from .llm import build_llm
    from concurrent.futures import ThreadPoolExecutor
    with _AHEAD_LOCK:
        if _AHEAD is None: _AHEAD = ThreadPoolExecutor(max_workers=2, thread_name_prefix='wrap-ahead')
    out = {}
    # ...a brain built only for a question there is: the functions build theirs only once they ask, and asking ahead is never
    # what fails an ending - a brain that cannot be built here is built (and its failure handled) at the function's own place
    for q in questions:
        if q is None or q in out: continue
        try: brain = build_llm(store, job='summary')
        except Exception as e: logger.debug(f'wrap: not asked ahead - {e}'); continue
        if brain: out[q] = _AHEAD.submit(lambda b=brain, q=q: b(q[0], q[1], **dict(q[2])))
    return out


def _answered(store, ahead: dict):
    """The brain a function asks at its place in the ending: a question asked ahead is answered from there."""
    from .llm import build_llm
    if not ahead: return None                                   # nothing asked ahead: the function builds its own, as it always did
    def llm(system, user, **kw):
        f = ahead.get((system, user, tuple(sorted(kw.items()))))
        if f is not None: return f.result()
        brain = build_llm(store, job='summary')                                # ...and one asked differently builds its brain then, as before
        return brain(system, user, **kw) if brain else None
    return llm


CUT_OFF = '(The session was closed while the agent was still working on this turn - it had not finished, so there is no final message.)'
_WRAP_LOCK = threading.Lock()
_ACTIVE = {}                            # (store, session id) -> task id, while that session is being wrapped; once wrapped, the audit says so


def forget(tid) -> None:
    "A clean slate for one task's sessions (tests)."
    with _WRAP_LOCK:
        for k in [k for k, v in _ACTIVE.items() if v == tid]: _ACTIVE.pop(k, None)


def _wrapped_before(store, tid, sid) -> bool:
    "The audit says this session was wrapped (wrap's own last word) - before a restart, too."
    for r in store.list_audit('terminal', tid, 50) or []:
        if r.get('Action') != 'wrap': continue
        try: d = json.loads(r.get('Detail') or '{}') or {}
        except (TypeError, ValueError): continue
        if str(d.get('sid') or '') == sid: return True
    return False


def _close_again(store, tid, close, actor, agent, text, no_reply) -> dict:
    "The session's ending is on the task already: Done on a saved session still closes the task, and files nothing more."
    fin = {}
    if close and (store.get_task(tid) or {}).get('Status') not in ('done', 'dropped'):
        fin = finish(store, tid, {}, None, agent, reply_source(text), owner_done=actor == 'owner', no_reply=no_reply) or {}
        from . import selfclose; selfclose.unclaim(store, tid, actor)
    return {'wrap': 'already', 'taskId': tid, 'report': '', 'proposed': [], 'drafting': bool(fin.get('drafting')),
            'can_send': bool(fin.get('can_send')), 'send_block': fin.get('send_block') or '', 'freshness': fin.get('freshness') or 'unchecked'}


def _wrap_session(store, tid, task, close, actor, sid, final_message, no_reply, text, agent, found, cut) -> dict:
    """wrap's coding ending, once per session: the report, the result, the pty closed, proposals, the reply."""
    from . import proposals, terminal as term, handbook, playbooks
    # the handbook's and the playbook's questions, asked now beside the report's - answered at their own places below (_AHEAD)
    ahead = _ask_ahead(store, [
        _question(handbook.learn_from_session, store, tid, text, agent, repo=term.repo_tag(task) or '') if handbook.enabled(store) else None,
        _question(playbooks.draft, store, tid, text, agent)])
    _stage(tid, 'report')
    rep = report_from_transcript(store, tid, text, agent, final_message='' if cut else final_message)
    report = resolution_text(rep)
    # SAVE FIRST, close after (PW-231/233): the result and the final answer land before the pty goes. A save that fails raises here - the session stays, the report is
    # not written, nothing reads as finalised - and the caller may retry.
    from . import session_artifacts
    try:
        artifact = session_artifacts.coding(store, tid, report, text, agent or actor, final_message=final_message)
    except Exception as e:
        raise ValueError(f'the result could not be saved ({str(e)[:160]}) - the session was left open; try again')
    # NO BOX IS TICKED FROM PROSE (2026-10-11, "everything should be ai"): a `- [x] ...` line anywhere in the transcript
    # ticked whichever item's words it contained or was contained by - "- [x] Fix it" ticked "Fix it" and also "Fix it
    # tomorrow after the review". Nothing in the brief gives the agent an item id to report, so there is no honest match;
    # a close ticks every box (store.update_task, done-ticks-every-box) and a wrap that leaves the task open leaves them.
    store.add_comment(tid, agent, 'agent', f'{REPORT}\n{report}' + (f'\n\nLAST MESSAGE\n{final_message}' if final_message else ''))
    if found: term.close(found)              # done means done - the pty and its shells go too, once the result is safe
    store.add_comment(tid, actor, 'human', 'Closed the session - wrapped up from what was on screen.')
    # anything the agent PROPOSED becomes a pending review here, at the one moment its whole
    # transcript is in hand - and refusals are recorded rather than dropped (proposals.py)
    proposed = []
    if store.get_setting('proposals_enabled', '1') == '1':
        try: proposed = proposals.collect(store, tid, text, agent)
        except Exception as e: logger.warning(f'proposal collection failed for task {tid}: {e}')
    # 'drafting' must be what finish() ACTUALLY did, not a second guess at it: recomputing it from
    # reply_target alone skipped the can-this-channel-even-reply rule, so a GitHub task with
    # replies off closed with no draft while the card still promised one on the task.
    # THE RUN ENDING IS WHEN THE ANSWER IS WRITTEN, whoever ended it. Only `close` decided this, so
    # an agent that finished by itself drafted the reply and the owner pressing Stop and save
    # got the report filed and nothing to send - on the one road where they had just read the work
    # and knew it was done (the owner, 2026-09-22). The draft is written either way now; what `close`
    # still decides is whether the TASK ends with the run (finish's keep_open).
    fin = {}
    if (store.get_task(tid) or {}).get('Status') not in ('done', 'dropped'):
        _stage(tid, 'reply')
        fin = finish(store, tid, rep, None, agent, reply_source(text, '' if cut else final_message),
                     owner_done=close and actor == 'owner', keep_open=not close, no_reply=no_reply) or {}
        if close:
            from . import selfclose; selfclose.unclaim(store, tid, actor)   # the owner ended it; the mark that kept it open has done its job
    # ...and the one question worth asking the transcript that is NOT about this task: did the
    # session work out anything still true next month? Usually not, and "not" is the answer it
    # is told to give (handbook.py). A failure here never stops a task closing - and it waits until the task's status is set:
    # run between the pty closing and finish(), its AI call left the task in_progress with no session (TQ-1112 shape).
    _stage(tid, 'learning')           # ...the reply is filed: Close out draws it now, while the two last questions are asked
    if handbook.enabled(store):
        try: handbook.learn_from_session(store, tid, text, agent, repo=term.repo_tag(task) or '', llm=_answered(store, ahead))
        except Exception as e: logger.debug(f'handbook: nothing filed for task {tid} - {e}')
    # ...and the last question, once the report and the reply are in hand: was this a KIND of job that
    # will recur, done here for the first time? The answer is a proposal on the task, never a file
    # (playbooks.py) - the second such job matches it. Last on purpose: the receipt and the sender's
    # answer are what a close is for, and this call must never be the one the drafter's AI budget goes to.
    pbd = playbooks.draft(store, tid, text, agent, llm=_answered(store, ahead))
    # ...and one the agent proposed itself (TASKUARY-PROPOSE, collected above) is held in sight the same way (proposals.HELD)
    if proposals.playbook_pending(store, tid): proposals.hold_for_playbook(store, tid, agent)
    if pbd: proposed.append(pbd)
    store.audit('terminal', tid, 'wrap', actor, detail={'sid': found or sid, 'close': close})
    _ended(store, tid, close, actor)
    return {'wrap': 'done', 'taskId': tid, 'report': report, 'proposed': proposed,
            'drafting': bool(fin.get('drafting')), 'can_send': bool(fin.get('can_send')), 'send_block': fin.get('send_block') or '',
            'freshness': fin.get('freshness') or 'unchecked', 'artifacts': [artifact] if artifact else []}


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
        # ...a follow-up keeps saying it is one (agent_reply): these lines would make it the answer to the message again
        if not is_follow_up(live): store.update_review_reason(rid, why, run_id)
    else:
        rid = store.add_review({'TaskId': task_id, 'MessageId': mid, 'RunId': run_id, 'Kind': 'draft_reply', 'Status': 'pending',
                                'Reason': why if fresh.get('state') in ('changed', 'unresolved') else 'the agent finished the work - reply awaiting approval'})
    if (held or live) and (held or live).get('MessageId') != mid: store.update_review_message(rid, mid)
    rv = store.get_review(rid) or {}
    if agent_drafted(rv):
        # the agent that did the work wrote this reply itself (agent_reply): its words stand and no second
        # model rewrites them - only a thread that moved on (or could not be checked) is flagged for a reread
        who = str(rv.get('DraftBy'))[len(AGENT_DRAFT):] or 'the agent'
        if not is_follow_up(rv):
            store.update_review_reason(rid, f"{who}'s own reply from the session - approve to send"
                                       + (' (the thread moved on after it was written - reread it)' if fresh.get('state') == 'changed' else ''), run_id)
        if fresh.get('state') in ('changed', 'unresolved'): store.mark_review_stale(rid)
        return
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
            responder.write_draft(store, task_id, rid, src, 'agent')
    except Exception as e: logger.warning(f'reply draft failed for task {task_id}: {e}')
    # a refresh that failed is an unresolved freshness state the owner sees: the draft waits, stale, for one that succeeds
    if fresh.get('state') == 'unresolved': store.mark_review_stale(rid)


