"""One door for review verdicts: the API endpoint and the phone road both decide HERE.
Approving IS sending - the answer goes back on the channel it arrived on - and a send that
FAILS returns the review to the queue wearing the error, so nothing looks finished that
never left the machine. The corrections feed LEARNED.md (an edit shows how the owner
writes, a reject what should never have been drafted).
"""
import json
from loguru import logger

VERB2STATUS = {'approve': 'approved', 'edit': 'edited', 'reject': 'rejected', 'no_reply': 'no_reply'}


def _settle_task_after_sent_reply(store, rv: dict, actor: str, was_sent: bool):
    """Reconcile task/agent state after its reviewed reply really left the machine."""
    task_id = rv.get('TaskId')
    if not task_id:
        return
    task = store.get_task(task_id)
    if not task:
        return

    kind = rv.get('Kind')
    if kind not in ('clarification', 'draft', 'draft_reply') and task.get('Kind') != 'reply':
        return
    # A free-standing draft can be reviewed for learning/editing without having a channel
    # destination. Only a confirmed channel send gets to finish a normal task.
    if not was_sent and kind in ('clarification', 'draft') and task.get('Kind') != 'reply':
        return

    # A clarification is not completion: stop the blocked session and keep the task visibly
    # waiting for the person who has the missing fact.
    if kind == 'clarification':
        from . import terminal
        session = terminal.session_for(task_id)
        stopped = bool(session and getattr(session, 'alive', False) and terminal.close(session.sid))
        if task.get('Status') not in ('done', 'dropped'):
            store.update_task(task_id, {'Status': 'waiting'}, actor)
        if stopped:
            store.add_comment(task_id, actor, 'human',
                              'Stopped the agent after sending the clarification; waiting for the sender.')
        return

    # Sending a message is not the same as completing an owner-controlled task. It may be an
    # update halfway through a long task, and its agent session may still be useful. Routed work
    # keeps the automatic "answer sent = complete" behavior.
    from . import selfclose
    if selfclose.stays_open(store, task_id):
        store.add_comment(task_id, actor, 'human',
                          'Reply sent. This owner-controlled task remains open.')
        return

    # A normal reviewed reply is the answer to this task. It cannot coexist with an agent
    # still working the same task after the channel confirms the send.
    if task.get('Kind') == 'reply' or kind in ('draft', 'draft_reply'):
        from . import terminal
        session = terminal.session_for(task_id)
        stopped = bool(session and getattr(session, 'alive', False) and terminal.close(session.sid))
        if task.get('Status') not in ('done', 'dropped'):
            store.update_task(task_id, {'Status': 'done'}, actor)
        if stopped:
            store.add_comment(task_id, actor, 'human',
                              'Stopped the agent because the task reply was sent.')


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
    # a PROPOSAL is not a draft reply: approving it RUNS the action the agent asked for
    # (proposals.execute re-validates - the approval never grants the permission), and
    # nothing is ever sent to a sender for it
    if rv.get('Kind') == 'action':
        from . import proposals
        if verb in ('approve', 'edit'):
            try:
                out = proposals.execute(store, rv, actor, final)
            except Exception as e:
                store.add_comment(rv['TaskId'], actor, 'human', f'PROPOSAL FAILED: {str(e)[:300]}')
                return {'ok': False, 'status': 'pending', 'sent': None, 'send_error': str(e)[:300]}
            store.decide_review(rid, VERB2STATUS['approve'], rv.get('DraftText'), actor, note)
            return {'ok': True, 'status': 'approved', 'sent': None, 'send_error': None, 'result': out}
        store.decide_review(rid, VERB2STATUS[verb], None, actor, note)
        store.add_comment(rv['TaskId'], actor, 'human', f'Proposal {VERB2STATUS[verb]} - nothing was done.')
        return {'ok': True, 'status': VERB2STATUS[verb], 'sent': None, 'send_error': None}
    store.decide_review(rid, VERB2STATUS[verb], final, actor, note)
    if final and rv.get('TaskId'): store.add_comment(rv['TaskId'], actor, 'human', f'Reviewed draft ({verb}):\n{final}')
    sent, send_err = None, None
    # an OUTBOUND draft carries its own destination: there is no message it is answering, so the
    # review row says where it goes. Same door, same approval, same audit - the only difference
    # is which way the work is travelling.
    deliver = {}
    if rv.get('Deliver'):
        try: deliver = json.loads(rv['Deliver']) or {}
        except (TypeError, ValueError): deliver = {}
    if final and deliver:
        try:
            sent = outbound.send_out(store, deliver.get('channel'), deliver.get('to'),
                                     deliver.get('subject'), final)
            if rv.get('MessageId'):
                store.set_message_status(rv['MessageId'], 'sent')
        except Exception as e:
            send_err = str(e)[:300]
            logger.warning(f'outbound send failed for review {rid}: {send_err}')
            store.update_review_draft(rid, final, rv.get('RunId'))
            store.decide_review(rid, 'pending', final, actor, note)
            return {'ok': False, 'status': 'pending', 'sent': None, 'send_error': send_err}
        store.audit('review', rid, 'sent_outbound', actor,
                    detail={'channel': sent.get('channel'), 'to': sent.get('to')})
        return {'ok': True, 'status': VERB2STATUS[verb], 'sent': sent, 'send_error': None}
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
    if verb == 'no_reply' and rv.get('TaskId'):
        from . import selfclose
        if not selfclose.stays_open(store, rv['TaskId']):
            store.update_task(rv['TaskId'], {'Status': 'done'}, actor)
    # Sending is the lifecycle boundary. A final/manual answer closes the task and its live
    # terminal; a clarification stops the blocked terminal but deliberately leaves it waiting.
    if verb in ('approve', 'edit') and rv.get('TaskId') and not send_err:
        _settle_task_after_sent_reply(store, rv, actor, sent is not None)
    store.audit('review', rid, verb, actor, detail={'kind': rv.get('Kind'), 'sent': bool(sent)})
    if verb in ('edit', 'reject', 'no_reply'):
        m = (store.get_message(rv['MessageId']) if rv.get('MessageId') else None) or {}
        ev = (f"rv{rid}: owner verdict '{verb}' on a drafted reply to \"{(m.get('Subject') or rv.get('Kind') or '')[:80]}\" "
              f"from {m.get('FromEmail') or '?'}" + (f"; their note: {note[:200]}" if note else ''))
        if verb == 'edit': ev += f"\nDRAFT:\n{(rv.get('DraftText') or '')[:700]}\nSENT INSTEAD:\n{(final or '')[:700]}"
        if learn_async: learn_async(learn.learn_from, store, ev)
        else: learn.learn_from(store, ev)
    return {'ok': True, 'status': 'pending' if send_err else VERB2STATUS[verb], 'sent': sent, 'send_error': send_err}
