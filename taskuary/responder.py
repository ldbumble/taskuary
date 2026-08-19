"""Replies: the other half of the funnel, and the cheap half.

Most inbound mail does not need an agent, a repo or a session - it needs an answer. Triage
already separates those (reply_only vs task); this writes the answer with the MAIN AI, in
the owner's voice per SOUL.md, and parks it for approval. Approving sends it (see outbound).

Drafting used to require a CLI agent named `responder`. Nobody has one, so reply-only mail
sat in the queue undrafted - and the fallback was worse: the *coding* agent, opened on a
repo, to write two sentences of email.

Every reply comes through `write_draft`: the mail that only ever needed an answer, and the
mail a coder just finished the work behind. The coder reports what it did; the reply is
written here either way, so the sender always hears one voice.
"""
from loguru import logger

SYSTEM = (
    "You write {owner}'s replies. Output ONLY the message body - no subject line, no "
    "'Draft:', no markdown, no sign-off other than the one SOUL.md specifies.\n"
    'Answer the question actually asked, in the fewest words that fully answer it. Use what '
    "the thread and the operator's document give you; never invent facts, numbers, dates or "
    'commitments. If something needed to answer is genuinely missing, say plainly what you '
    'need instead of guessing.\n')
NOT_YET = ('If the request cannot be answered by a reply alone - it needs work doing - say so in one '
           'line and stop; the owner will turn it into a task.')
# the coder has already closed the thread: this reply reports an outcome, never promises one
DONE = ('The work this thread asked for is FINISHED - the report below says what was done. Tell them '
        'what happened and what it means for them, claiming nothing the report does not support. '
        'Never mention agents, tasks, tickets, repositories or tooling: the owner did this.')


def draft_reply(store, task_id: int, llm=None, resolution: str = None) -> str:
    """The reply this task needs, as text. Uses the owner's own brain (the AI connector, or
    whichever brain `triage_ai` names), the standing memory notes, and the thread itself."""
    from .llm import build_llm
    from .ingest import notes_for
    llm = llm or build_llm(store)
    if not llm: raise RuntimeError('no AI connector is set up to write replies')
    t = store.get_task(task_id) or {}
    msgs = [m for m in store.list_messages(task_id) if m.get('Status') != 'context']
    if not msgs: raise RuntimeError('nothing to reply to on this task')
    last = msgs[-1]
    soul = store.get_doc('soul') or ''
    owner = (soul.split('You work for **')[1].split('**')[0] if 'You work for **' in soul else 'the owner')
    notes = notes_for(store, {'from_email': last.get('FromEmail')})
    system = (SYSTEM.format(owner=owner) + (DONE if resolution else NOT_YET)
              + (f"\n\nOperator's document (voice and rules):\n{soul[:4000]}" if soul else ''))
    if notes:
        system += '\n\nStanding notes from the owner:\n' + '\n'.join(f'- {n}' for n in notes[:20])[:1500]
    thread = '\n\n'.join(
        f"--- {'YOU' if m.get('Status') == 'context' else (m.get('FromName') or m.get('FromEmail'))}"
        f" · {m.get('SentAt')} · {m.get('Channel')}\n{str(m.get('BodyText') or '')[:4000]}"
        for m in store.list_messages(task_id)[-6:])
    user = f"Subject: {last.get('Subject') or t.get('Title') or ''}\nFrom: {last.get('FromName')} <{last.get('FromEmail')}>\n\n{thread}"
    if resolution: user += f'\n\n--- WHAT WAS DONE (your source of truth; the sender has not seen it)\n{resolution}'
    out = (llm(system, user, max_tokens=800) or '').strip()
    if not out: raise RuntimeError('the AI returned an empty reply')
    return out


def draft_for_review(store, task_id: int, review_id: int, llm=None, resolution: str = None) -> str:
    """Write the draft and park it on its review, ready for approve / edit / no-reply."""
    text = draft_reply(store, task_id, llm, resolution)
    store.update_review_draft(review_id, text, None)
    logger.info(f'drafted reply for task {task_id} ({len(text)} chars)')
    return text


def resolution_of(store, task_id: int):
    """The coder's own report on this task, if one closed it - so hitting Redraft says what
    was done instead of reverting to "this needs work doing"."""
    return next((c['Body'] for c in reversed(store.list_comments(task_id))
                 if str(c.get('Body') or '').startswith('CODER REPORT')), None)


def write_draft(store, task_id: int, review_id: int, resolution: str = None, actor: str = 'system', llm=None) -> str:
    """The one door every reply comes through. A CLI agent named `responder` takes over only
    if the owner deliberately configured one; otherwise the main AI writes it."""
    from . import agents as hub_agents
    resolution = resolution or resolution_of(store, task_id)
    if store.get_agent('responder'):
        ask = 'Draft the reply this message needs.' + (
            f'\nThe work is already done - report it, do not promise it:\n{resolution}' if resolution else '')
        out = hub_agents.dispatch(store, task_id, 'responder', ask, actor)
        if out['status'] != 'done': raise RuntimeError('the responder agent failed - see the run log')
        store.update_review_draft(review_id, out['result'], out['run_id'])
        return out['result']
    return draft_for_review(store, task_id, review_id, llm, resolution)
