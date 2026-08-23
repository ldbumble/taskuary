"""One door for review verdicts: the API endpoint and the phone road both decide HERE.
Approving IS sending - the answer goes back on the channel it arrived on - and a send that
FAILS returns the review to the queue wearing the error, so nothing looks finished that
never left the machine. The corrections feed LEARNED.md (an edit shows how the owner
writes, a reject what should never have been drafted).
"""
from loguru import logger

VERB2STATUS = {'approve': 'approved', 'edit': 'edited', 'reject': 'rejected', 'no_reply': 'no_reply'}


def decide(store, rv: dict, verb_in: str, final_text: str = None, note: str = None,
           actor: str = 'owner', learn_async=None) -> dict:
    """Land one verdict on a pending review. learn_async(fn, *args) defers the learning
    call (the API hands FastAPI's background task runner in); None runs it inline."""
    from . import learn, outbound
    rid = rv['ReviewId']
    # ONE approve: if the text differs from the draft, it was edited - no need to declare it
    if verb_in in ('approve', 'edit'):
        final = final_text if (final_text or '').strip() else rv.get('DraftText')
        verb = 'edit' if (final or '').strip() != (rv.get('DraftText') or '').strip() else 'approve'
    else:
        final, verb = None, verb_in
    store.decide_review(rid, VERB2STATUS[verb], final, actor, note)
    if final and rv.get('TaskId'): store.add_comment(rv['TaskId'], actor, 'human', f'Reviewed draft ({verb}):\n{final}')
    sent, send_err = None, None
    if final and rv.get('MessageId'):
        msg = store.get_message(rv['MessageId'])
        try:
            sent = outbound.reply_to_message(store, msg, final)
            if rv.get('TaskId'):
                store.add_comment(rv['TaskId'], actor, 'human',
                                  f"Sent by {sent['channel']} to {', '.join(sent.get('to') or []) or 'the chat'}.")
        except Exception as e:
            send_err = str(e)[:300]
            logger.warning(f'reply send failed for review {rid}: {send_err}')
            if rv.get('TaskId'):
                store.add_comment(rv['TaskId'], actor, 'human', f'NOT SENT - {send_err}. The approved text is above.')
            # an approved reply that never LEFT is not done: back to the queue wearing the
            # error, the approved text becomes the draft, approving again retries the send
            store.update_review_draft(rid, final, rv.get('RunId'))
            store.unhold_review(rid, f'approved, but sending FAILED: {send_err} - fix the channel and approve again')
    if verb == 'no_reply' and rv.get('TaskId'): store.update_task(rv['TaskId'], {'Status': 'done'}, actor)
    # reply-only items are not real tasks: answering them IS the work, so close on decision
    if verb in ('approve', 'edit') and rv.get('TaskId') and not send_err:
        t = store.get_task(rv['TaskId'])
        if ((t or {}).get('Kind') == 'reply' or rv.get('Kind') == 'draft_reply') and t.get('Status') not in ('done', 'dropped'):
            store.update_task(rv['TaskId'], {'Status': 'done'}, actor)
    store.audit('review', rid, verb, actor, detail={'kind': rv.get('Kind'), 'sent': bool(sent)})
    if verb in ('edit', 'reject', 'no_reply'):
        m = (store.get_message(rv['MessageId']) if rv.get('MessageId') else None) or {}
        ev = (f"rv{rid}: owner verdict '{verb}' on a drafted reply to \"{(m.get('Subject') or rv.get('Kind') or '')[:80]}\" "
              f"from {m.get('FromEmail') or '?'}" + (f"; their note: {note[:200]}" if note else ''))
        if verb == 'edit': ev += f"\nDRAFT:\n{(rv.get('DraftText') or '')[:700]}\nSENT INSTEAD:\n{(final or '')[:700]}"
        if learn_async: learn_async(learn.learn_from, store, ev)
        else: learn.learn_from(store, ev)
    return {'ok': True, 'status': 'pending' if send_err else VERB2STATUS[verb], 'sent': sent, 'send_error': send_err}
