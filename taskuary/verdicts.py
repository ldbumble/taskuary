"""One door for review verdicts: the API endpoint and the phone road both decide HERE.
Approving IS sending - the answer goes back on the channel it arrived on - and a send that
FAILS returns the review to the queue wearing the error, so nothing looks finished that
never left the machine. The corrections feed LEARNED.md (an edit shows how the owner
writes, a reject what should never have been drafted).
"""
import json, re
from pathlib import Path

from loguru import logger

VERB2STATUS = {'approve': 'approved', 'edit': 'edited', 'reject': 'rejected', 'no_reply': 'no_reply',
               'close_unsent': 'closed_unsent'}   # the owner's explicit close when sending is unavailable (PW-145) - never 'sent'


def context_moved(store, rv: dict):
    """Has the thread materially moved since this draft was pinned (PW-240)? A stale mark triage set, or an
    inbound message set that differs from the pinned revision - never a polling timestamp, never an FYI filed
    with nothing to do. Returns (moved, the newest material inbound message or None)."""
    from . import operations
    if rv.get('Kind') == 'action': return False, None
    tid = rv.get('TaskId')
    if tid:
        latest = store.last_material_inbound_on_task(tid)
        if rv.get('ContextRevision'): moved = operations.message_revision(store, tid) != rv['ContextRevision']
        else: moved = bool(latest and latest.get('MessageId') != rv.get('MessageId'))
    else:
        m = store.get_message(rv.get('MessageId')) if rv.get('MessageId') else None
        latest = store.last_inbound_in(m['ConversationId']) if m and m.get('ConversationId') else None
        moved = bool(latest and latest.get('MessageId') != rv.get('MessageId'))
    return bool(rv.get('Stale') or moved), latest


def _now_iso() -> str:
    from datetime import datetime, timezone
    return datetime.now(timezone.utc).strftime('%Y-%m-%dT%H:%M:%SZ')


SAFE_NAME = re.compile(r'[^A-Za-z0-9._ -]+')


def attach(store, rid: int, name: str, data: bytes, actor: str = 'owner') -> dict:
    """Put a file on a pending reply: copied into the review's own folder, named in its envelope.

    The draft said "attached are the PTO accrual files" and the envelope carried nothing, because
    nothing in Taskuary could attach anything (the owner, 2026-09-14: "otherwise it looks like it
    sends without attachment"). This is the other half of the fix - the card's half is showing it."""
    from .artifacts import outbox_dir
    rv = store.get_review(int(rid))
    if not rv: raise ValueError('no such reply')
    if rv.get('Status') not in ('pending', 'held'): raise ValueError('this reply has already been decided')
    name = SAFE_NAME.sub('_', str(name or '').strip())[:120] or 'attachment'
    if not data: raise ValueError('that file is empty')
    from . import outbound
    if len(data) > outbound.ATTACH_MAX:
        raise ValueError(f'that file is over {outbound.ATTACH_MAX // (1024 * 1024)}MB, which no mailbox will accept')
    path = outbox_dir(rid) / name
    path.write_bytes(data)
    env = _envelope(rv)
    files = [f for f in (env.get('attachments') or []) if f.get('name') != name]
    files.append({'name': name, 'path': str(path), 'size': len(data)})
    env['attachments'] = files
    store.set_review_deliver(int(rid), json.dumps(env))
    store.audit('review', int(rid), 'attached', actor, detail={'name': name, 'size': len(data)})
    return {'attachments': files}


def detach(store, rid: int, name: str, actor: str = 'owner') -> dict:
    """Take a file back off a reply - the copy goes too, so nothing lingers addressed to somebody."""
    rv = store.get_review(int(rid))
    if not rv: raise ValueError('no such reply')
    env = _envelope(rv)
    keep = [f for f in (env.get('attachments') or []) if f.get('name') != name]
    gone = next((f for f in (env.get('attachments') or []) if f.get('name') == name), None)
    env['attachments'] = keep
    store.set_review_deliver(int(rid), json.dumps(env))
    if gone:
        try: Path(gone['path']).unlink(missing_ok=True)
        except OSError as e: logger.debug(f'could not remove {gone.get("path")}: {e}')
    store.audit('review', int(rid), 'detached', actor, detail={'name': name})
    return {'attachments': keep}


def _envelope(rv: dict) -> dict:
    try: return json.loads(rv.get('Deliver') or '{}') or {}
    except (TypeError, ValueError): return {}


def _mark_delivery(store, rid: int, env: dict, state: str, attempted_at: str = None) -> None:
    """The send's own state on the review's envelope: sent | failed | unknown (PW-144) - and when it was tried."""
    env = dict(env or {}); env.setdefault('kind', 'reply')
    env['delivery'] = state
    if attempted_at: env['attempted_at'] = attempted_at
    env['attempts'] = int(env.get('attempts') or 0) + (1 if state != 'sent' or attempted_at else 0)
    try: store.set_review_envelope(rid, env)
    except Exception as e: logger.debug(f'delivery mark skipped: {e}')


def _settle_task_after_sent_reply(store, rv: dict, actor: str, was_sent: bool):
    """Reconcile task/agent state after its reviewed reply really left the machine."""
    task_id = rv.get('TaskId')
    if not task_id:
        return
    task = store.get_task(task_id)
    if not task:
        return

    kind = rv.get('Kind')
    if kind == 'action': return                        # a proposed action is not a reply
    # A free-standing draft can be reviewed for learning/editing without having a channel
    # destination. Only a confirmed channel send gets to finish a normal task.
    if not was_sent and task.get('Kind') != 'reply':
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

    # The reply that went out IS the task's ending (the owner, 2026-09-03: "replying should close it") -
    # whatever kind of review carried it: the coder's own draft after a job, one you opened by hand, one
    # triage queued. The one exception is an agent still WORKING the task: its result and its own
    # close-out come first, and the task closes when that lands.
    from .funnel import working_tids
    if task_id in working_tids(store):
        store.add_comment(task_id, actor, 'human', 'Reply sent; the agent still has this task, so it stays open until the agent is done.')
        return
    from . import terminal
    session = terminal.session_for(task_id)
    stopped = bool(session and getattr(session, 'alive', False) and terminal.close(session.sid))
    if task.get('Status') not in ('done', 'dropped'):
        store.update_task(task_id, {'Status': 'done'}, actor)
        store.add_comment(task_id, actor, 'human', 'Closed - the reply went out.')
        # ...and the item leaves Unread with it (PW-149). Canonical Unread empties on read receipts, and
        # nobody writes one for a reply approved from the Review page - so the answered thread sat in the
        # pile as 'a person asked you for something' with its task already closed. All keeps the whole thread.
        from . import funnel
        try: funnel.settle(store, f'task:{task_id}', 'done', actor, note='the reply went out')
        except Exception as e: logger.debug(f'the sent reply did not settle its item: {e}')
    if stopped:
        store.add_comment(task_id, actor, 'human', 'Stopped the parked agent because the task reply was sent.')


def decide(store, rv: dict, verb_in: str, final_text: str = None, note: str = None,
           actor: str = 'owner', learn_async=None, cc: list = None) -> dict:
    """Land one verdict on a pending review. learn_async(fn, *args) defers the learning
    call (the API hands FastAPI's background task runner in); None runs it inline.

    `cc` loops somebody in on this answer. Replies get the list chosen at approval; a new outbound
    email starts with the list deliberately saved in its delivery envelope, which remains visible
    and editable on the task."""
    from . import learn, outbound
    rid = rv['ReviewId']
    # A verdict lands ONCE. There was no guard at all, so "approve" typed and the Approve button
    # clicked - or one double click - sent the same mail twice (2026-09-03).
    if str(rv.get('Status') or 'pending') != 'pending':
        return {'ok': False, 'status': rv.get('Status'), 'sent': None, 'already': True,
                'send_error': f"this one was already {rv.get('Status')}" + (f" by {rv['DecidedBy']}" if rv.get('DecidedBy') else '')}
    # ...and approving an EMPTY draft sent nothing, marked the review approved and closed the task
    # anyway: the person never got an answer and nothing was left in the pipe to say so.
    if verb_in in ('approve', 'edit') and not (final_text or '').strip() and not (rv.get('DraftText') or '').strip():
        return {'ok': False, 'status': 'pending', 'sent': None, 'empty': True,
                'send_error': 'there is no draft to send - write the reply (or let the AI draft it) and approve that'}
    # the draft is checked against the thread AS IT IS NOW before anything leaves (PW-055): a stale mark, or an
    # inbound message set that moved since the draft was pinned, refuses the send here - the Review button and
    # the phone road land through this one door, so neither can send yesterday's wording
    if verb_in in ('approve', 'edit') and rv.get('Kind') != 'action' and rv.get('TaskId'):
        moved, _latest = context_moved(store, rv)
        if moved:
            if not rv.get('Stale'): store.mark_review_stale(rid)
            return {'ok': False, 'status': 'pending', 'sent': None, 'stale': True,
                    'send_error': 'New messages arrived after this draft was written - nothing was sent. Redraft it with the latest context and approve again.'}
    # Close without sending (PW-145): the owner's own word that no reply will go out - the unsent draft stays,
    # the closure and its reason are recorded, the reply obligation ends, and nothing here ever reads as Sent
    if verb_in == 'close_unsent':
        why = str(note or '').strip() or (outbound.send_block(store, (store.get_message(rv['MessageId']) or {}).get('Channel')) if rv.get('MessageId') else '') or 'the owner chose not to send a reply'
        store.decide_review(rid, 'closed_unsent', rv.get('DraftText'), actor, why)
        if rv.get('TaskId'):
            store.add_comment(rv['TaskId'], actor, 'human', f'Closed without sending - no reply went out: {why}. The unsent draft is kept on the review.')
            from . import selfclose
            if not selfclose.stays_open(store, rv['TaskId']) and (store.get_task(rv['TaskId']) or {}).get('Status') not in ('done', 'dropped'):
                store.update_task(rv['TaskId'], {'Status': 'done'}, actor)
        store.audit('review', rid, 'close_unsent', actor, detail={'why': why[:200]})
        return {'ok': True, 'status': 'closed_unsent', 'sent': None, 'send_error': None}
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
    if deliver.get('kind') == 'zoho_invoice' and verb in ('reject', 'no_reply') and deliver.get('item_id'):
        from . import invoice_workflow
        invoice_workflow.mark_skipped(store, int(deliver['item_id']))
    if final and deliver and deliver.get('kind') != 'reply':
        try:
            if deliver.get('kind') == 'zoho_invoice':
                from . import invoice_workflow, scopes, zoho
                c = store.get_connector(int(deliver.get('connector_id') or 0), with_secret=True)
                if not c: raise RuntimeError('the Zoho Invoice connector no longer exists')
                scopes.require(c, 'zoho_invoice_send')
                sent = zoho.send_invoice(zoho.connection(store, c['ConnectorId']), deliver.get('invoice_id'),
                                         deliver.get('to'), deliver.get('subject'), final)
                invoice_workflow.mark_sent(store, int(deliver.get('item_id')), deliver.get('subject'), final)
            else:
                sent = outbound.send_out(store, deliver.get('channel'), deliver.get('to'),
                                         deliver.get('subject'), final,
                                         cc=cc if cc is not None else deliver.get('cc'))
            if rv.get('MessageId'):
                store.set_message_status(rv['MessageId'], 'sent')
        except Exception as e:
            send_err = str(e)[:300]
            if deliver.get('kind') == 'zoho_invoice' and deliver.get('item_id'):
                from . import invoice_workflow
                invoice_workflow.mark_send_error(store, int(deliver['item_id']), send_err)
            logger.warning(f'outbound send failed for review {rid}: {send_err}')
            store.update_review_draft(rid, final, rv.get('RunId'))
            store.decide_review(rid, 'pending', final, actor, note)
            return {'ok': False, 'status': 'pending', 'sent': None, 'send_error': send_err}
        store.audit('review', rid, 'sent_outbound', actor,
                    detail={'channel': sent.get('channel'), 'to': sent.get('to')})
        if rv.get('TaskId') and sent is not None: _settle_task_after_sent_reply(store, rv, actor, True)
        return {'ok': True, 'status': VERB2STATUS[verb], 'sent': sent, 'send_error': None}
    if final and rv.get('MessageId'):
        msg = store.get_message(rv['MessageId'])
        # the server's own check, whatever a surface showed (PW-045): a channel that cannot carry
        # the reply refuses BEFORE any send is attempted, keeps the text as the draft, and says why
        block = outbound.send_block(store, (msg or {}).get('Channel'))
        if block:
            send_err = f'not sent - {block}'
            if rv.get('TaskId'):
                store.add_comment(rv['TaskId'], actor, 'human', f'NOT SENT - {block}. The approved text is kept as the draft.')
            store.update_review_draft(rid, final, rv.get('RunId'))
            store.unhold_review(rid, f'approved, but it cannot be sent from here: {block}')
            store.audit('review', rid, verb, actor, detail={'kind': rv.get('Kind'), 'sent': False, 'blocked': block})
            return {'ok': False, 'status': 'pending', 'sent': None, 'send_error': send_err}
        # the recipients the owner reviewed (PW-064): the pinned envelope, unless this click named a CC list itself
        env = deliver if deliver.get('kind') == 'reply' else {}
        # an earlier attempt whose delivery is UNKNOWN is reconciled with the provider before anything is sent
        # again (PW-144): found = it went out, settle it; not found = the retry is safe
        if env.get('delivery') == 'unknown':
            found = outbound.reconcile_sent(store, msg, final, since=env.get('attempted_at'))
            if found:
                sent = found; _mark_delivery(store, rid, env, 'sent')
                if rv.get('TaskId'): store.add_comment(rv['TaskId'], actor, 'human', 'The earlier send did go out - confirmed with the provider; nothing was sent again.')
                store.audit('review', rid, 'reconciled_sent', actor, detail={'id': found.get('id')})
                _settle_task_after_sent_reply(store, rv, actor, True)
                store.audit('review', rid, verb, actor, detail={'kind': rv.get('Kind'), 'sent': True})
                return {'ok': True, 'status': VERB2STATUS[verb], 'sent': sent, 'send_error': None, 'delivery': 'reconciled'}
        attempted_at = _now_iso()
        try:
            # what the owner saw on the card rides with the words: the files are part of the reply
            sent = outbound.reply_to_message(store, msg, final, to=env.get('to') or None,
                                             cc=cc if cc is not None else env.get('cc'),
                                             attachments=env.get('attachments'))
            if rv.get('TaskId'):
                copied = f", copied {', '.join(sent.get('cc') or [])}" if sent.get('cc') else ''
                files = f" with {', '.join(sent.get('attached') or [])}" if sent.get('attached') else ''
                store.add_comment(rv['TaskId'], actor, 'human',
                                  f"Sent by {sent['channel']} to {', '.join(sent.get('to') or []) or 'the chat'}{copied}{files}.")
        except outbound.UNKNOWN_ERRORS as e:
            # the provider did not answer: the mail may well have gone out. Delivery UNKNOWN is its own state
            # (PW-144) - not a failure, not a send - reconciled now, and again before any retry
            send_err = f'delivery unknown - the provider did not answer ({str(e)[:120]}); checking whether it went out before anything is retried'
            logger.warning(f'reply send uncertain for review {rid}: {e}')
            store.update_review_draft(rid, final, rv.get('RunId'))
            _mark_delivery(store, rid, env, 'unknown', attempted_at)
            found = outbound.reconcile_sent(store, msg, final, since=attempted_at)
            if found:
                _mark_delivery(store, rid, env, 'sent')
                store.decide_review(rid, VERB2STATUS[verb], final, actor, note)
                if rv.get('TaskId'): store.add_comment(rv['TaskId'], actor, 'human', f"Sent by email to {', '.join(found.get('to') or []) or 'the thread'} - confirmed with the provider after a slow answer.")
                _settle_task_after_sent_reply(store, rv, actor, True)
                store.audit('review', rid, verb, actor, detail={'kind': rv.get('Kind'), 'sent': True, 'reconciled': True})
                return {'ok': True, 'status': VERB2STATUS[verb], 'sent': found, 'send_error': None, 'delivery': 'reconciled'}
            if rv.get('TaskId'):
                store.add_comment(rv['TaskId'], actor, 'human', 'DELIVERY UNKNOWN - the provider did not answer and the Sent folder does not show the reply yet. Nothing was retried; approve again to check and, only if it is not there, send once.')
            store.unhold_review(rid, 'approved - delivery UNKNOWN: the provider did not answer; approve again to check the Sent folder and send only if it is not there')
            store.audit('review', rid, 'delivery_unknown', actor, detail={'error': str(e)[:200]})
            return {'ok': True, 'status': 'pending', 'sent': None, 'send_error': send_err, 'delivery': 'unknown'}
        except Exception as e:
            send_err = str(e)[:300]
            logger.warning(f'reply send failed for review {rid}: {send_err}')
            if rv.get('TaskId'):
                store.add_comment(rv['TaskId'], actor, 'human', f'NOT SENT - {send_err}. The approved text is above.')
            # an approved reply that never LEFT is not done: back to the queue wearing the
            # error, the approved text becomes the draft, approving again retries the send
            store.update_review_draft(rid, final, rv.get('RunId'))
            _mark_delivery(store, rid, env, 'failed')
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
        # an EDIT's note is about the wording - it goes to STYLE.md as a writing instruction (PW-061); a rejection's
        # or no-reply's note is about whether a reply was owed at all, which is triage's to learn
        if verb == 'edit' and note:
            from . import responder
            try: responder.style_feedback(store, note, actor)
            except Exception as e: logger.warning(f'style feedback not saved: {e}')
        ev = (f"rv{rid}: owner verdict '{verb}' on a drafted reply to \"{(m.get('Subject') or rv.get('Kind') or '')[:80]}\" "
              f"from {m.get('FromEmail') or '?'}" + (f"; their note: {note[:200]}" if note and verb != 'edit' else ''))
        if verb == 'edit': ev += f"\nDRAFT:\n{(rv.get('DraftText') or '')[:700]}\nSENT INSTEAD:\n{(final or '')[:700]}"
        if learn_async: learn_async(learn.learn_from, store, ev)
        else: learn.learn_from(store, ev)
    return {'ok': True, 'status': 'pending' if send_err else VERB2STATUS[verb], 'sent': sent, 'send_error': send_err, **({'delivery': 'failed'} if send_err else {})}
