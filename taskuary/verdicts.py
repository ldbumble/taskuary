"""One door for review verdicts: the API endpoint and the phone road both decide HERE.
Approving IS sending - the answer goes back on the channel it arrived on - and a send that
FAILS returns the review to the queue wearing the error, so nothing looks finished that
never left the machine. The corrections feed LEARNED.md (an edit shows how the owner
writes, a reject what should never have been drafted).
"""
import hashlib, json, re
from pathlib import Path

from loguru import logger

VERB2STATUS = {'approve': 'approved', 'edit': 'edited', 'reject': 'rejected', 'no_reply': 'no_reply',
               'close_unsent': 'closed_unsent',   # the owner's explicit close when sending is unavailable (PW-145) - never 'sent'
               'close_pr': 'rejected',            # a merge close-out answered "close it unmerged": the merge was turned down
               'merge_anyway': 'approved'}        # a merge refused for red checks, overruled by the owner


def context_moved(store, rv: dict):
    """Has the thread materially moved since this draft was pinned (PW-240)? A stale mark triage set, or an
    inbound message set that differs from the pinned revision - never a polling timestamp, never an FYI filed
    with nothing to do. Returns (moved, the newest material inbound message or None)."""
    from . import operations
    if rv.get('Kind') == 'action': return False, None
    tid = rv.get('TaskId')
    # one of the task's emails (slots.py) never goes stale: the stale road REWRITES the draft as a reply to the sender,
    # which would put an answer to someone else under this email's address. The owner sends the words they see.
    if rv.get('Kind') == 'slot': return False, None
    if tid:
        latest = store.last_material_inbound_on_task(tid)
        if rv.get('ContextRevision'): moved = operations.message_revision(store, tid) != rv['ContextRevision']
        else: moved = bool(latest and latest.get('MessageId') != rv.get('MessageId'))
    else:
        m = store.get_message(rv.get('MessageId')) if rv.get('MessageId') else None
        latest = store.last_inbound_in(m['ConversationId']) if m and m.get('ConversationId') else None
        moved = bool(latest and latest.get('MessageId') != rv.get('MessageId'))
    return bool(rv.get('Stale') or moved), latest


def draft_revision(store, rv) -> str:
    """What a yes on this review would send: its words, where they go and the files riding with them - and, on a close-out,
    the reply that goes with the merge. A card pins this when it is SHOWN: the session's `taskuary --reply` rewrote a draft
    between the phone showing it and the owner's "1", and the new words went out under the old yes."""
    rv = rv if isinstance(rv, dict) else store.get_review(int(rv)) if rv else None
    if not rv: return ''
    rows = [rv]
    if rv.get('Kind') == 'action' and rv.get('TaskId'):
        reply = store._one("SELECT * FROM review WHERE TaskId=? AND Status='pending' AND Kind IN ('draft','draft_reply') "
                           "ORDER BY ReviewId DESC LIMIT 1", (rv['TaskId'],))
        if reply: rows.append(reply)
    def env(r):
        d = {k: v for k, v in _envelope(r).items() if k not in ('delivery', 'attempted_at')}     # how a send went is not what it says
        # an empty envelope means the reply _deliver_review resolves - and a failed send writes that resolution into
        # Deliver, so hashing the raw field refused Try again with "the draft changed" when nothing the owner saw had moved
        if d: return d
        from . import outbound
        msg = store.get_message(r.get('MessageId')) if r.get('MessageId') else None
        return outbound.reply_envelope(store, msg) or {'kind': 'reply'}
    basis = [(r.get('ReviewId'), str(r.get('DraftText') or '').strip(), env(r)) for r in rows]
    return hashlib.sha1(json.dumps(basis, sort_keys=True, default=str).encode()).hexdigest()[:16]


def _now_iso() -> str:
    from datetime import datetime, timezone
    return datetime.now(timezone.utc).strftime('%Y-%m-%dT%H:%M:%SZ')


SAFE_NAME = re.compile(r'[^A-Za-z0-9._ -]+')


def attach(store, rid: int, name: str, data: bytes, actor: str = 'owner') -> dict:
    with store.review_delivery_edit(int(rid)):
        return _attach(store, rid, name, data, actor)


def _attach(store, rid: int, name: str, data: bytes, actor: str = 'owner') -> dict:
    """Put a file on a pending reply: copied into the review's own folder, named in its envelope.

    The draft said "attached are the PTO accrual files" and the envelope carried nothing, because
    nothing in Taskuary could attach anything (the owner, 2026-09-14: "otherwise it looks like it
    sends without attachment"). This is the other half of the fix - the card's half is showing it."""
    from .artifacts import outbox_dir
    rv = store.get_review(int(rid))
    if not rv: raise ValueError('no such reply')
    if rv.get('Status') not in ('pending', 'held'): raise ValueError('this reply has already been decided')
    if rv.get('DeliveryClaim') or rv.get('DeliveryState') in ('sending', 'unknown'):
        raise ValueError('the attempted attachments must be kept while delivery is in progress or unknown')
    name = SAFE_NAME.sub('_', str(name or '').strip())[:120] or 'attachment'
    if not data: raise ValueError('that file is empty')
    from . import outbound
    if len(data) > outbound.ATTACH_MAX:
        raise ValueError(f'that file is over {outbound.ATTACH_MAX // (1024 * 1024)}MB, which no mailbox will accept')
    path = outbox_dir(rid) / name
    path.write_bytes(data)
    env = _envelope(rv)
    files = [f for f in (env.get('attachments') or []) if f.get('name') != name]
    files.append({'name': name, 'path': str(path), 'size': len(data), 'sha256': hashlib.sha256(data).hexdigest()})
    env['attachments'] = files
    if not store.set_review_deliver(int(rid), json.dumps(env)):
        raise ValueError('the reply changed before its attachment could be saved')
    store.audit('review', int(rid), 'attached', actor, detail={'name': name, 'size': len(data)})
    return {'attachments': files}


def detach(store, rid: int, name: str, actor: str = 'owner') -> dict:
    with store.review_delivery_edit(int(rid)):
        return _detach(store, rid, name, actor)


def _detach(store, rid: int, name: str, actor: str = 'owner') -> dict:
    """Take a file back off a reply - the copy goes too, so nothing lingers addressed to somebody."""
    rv = store.get_review(int(rid))
    if not rv: raise ValueError('no such reply')
    if rv.get('DeliveryClaim') or rv.get('DeliveryState') in ('sending', 'unknown'):
        raise ValueError('the attempted attachments must be kept while delivery is in progress or unknown')
    env = _envelope(rv)
    keep = [f for f in (env.get('attachments') or []) if f.get('name') != name]
    gone = next((f for f in (env.get('attachments') or []) if f.get('name') == name), None)
    env['attachments'] = keep
    # Keep the SQLite write reservation until the file mutation is complete.
    # The envelope setter commits: unlinking afterwards could remove a replacement
    # another process has already attached and claimed for sending.
    if gone:
        try: Path(gone['path']).unlink(missing_ok=True)
        except OSError as e: logger.debug(f'could not remove {gone.get("path")}: {e}')
    if not store.set_review_deliver(int(rid), json.dumps(env)):
        raise ValueError('the reply changed before its attachment could be removed')
    store.audit('review', int(rid), 'detached', actor, detail={'name': name})
    return {'attachments': keep}


def _envelope(rv: dict) -> dict:
    try: return json.loads(rv.get('Deliver') or '{}') or {}
    except (TypeError, ValueError): return {}


def _delivery_busy(store, rid):
    current = store.get_review(rid) or {}
    state = current.get('DeliveryState')
    if current.get('Status') != 'pending':
        return {'ok': False, 'status': current.get('Status'), 'sent': None, 'already': True,
                'send_error': f"this one was already {current.get('Status')}"}
    return {'ok': False, 'status': 'pending', 'sent': None, 'delivery': state or 'pending',
            'send_error': ('A delivery check or send is already in progress; nothing was sent again.'
                           if current.get('DeliveryClaim') else 'This draft changed before approval; review it and approve again.')}


def _send_snapshot(store, snapshot):
    """Only the durable approved payload crosses the provider boundary."""
    from . import outbound
    env, body = snapshot['envelope'], snapshot['body']
    if env.get('kind') == 'reply':
        return outbound.reply_to_message(store, snapshot['message'], body, to=env.get('to') or None,
                                         cc=env.get('cc'), attachments=env.get('attachments'))
    if env.get('kind') == 'zoho_invoice':
        from . import scopes, zoho
        c = store.get_connector(int(env.get('connector_id') or 0), with_secret=True)
        if not c: raise RuntimeError('the Zoho Invoice connector no longer exists')
        scopes.require(c, 'zoho_invoice_send')
        return zoho.send_invoice(zoho.connection(store, c['ConnectorId']), env.get('invoice_id'),
                                 env.get('to'), env.get('subject'), body)
    return outbound.send_out(store, env.get('channel'), env.get('to'), env.get('subject'), body, cc=env.get('cc'),
                             attachments=env.get('attachments'), mailbox=env.get('mailbox'))


def _reconcile_snapshot(store, snapshot):
    from . import outbound
    env = snapshot['envelope']
    try:
        if env.get('kind') == 'reply':
            result = outbound.reconcile_sent(store, snapshot['message'], snapshot['body'], since=snapshot.get('attempted_at'),
                                             to=env.get('to'), cc=env.get('cc'))
        else:
            result = outbound.reconcile_outbound(store, env, snapshot['body'], since=snapshot.get('attempted_at'))
        return outbound.reconciliation_result(result)
    except Exception as e:
        return {'state': 'unknown', 'reason': f'the provider could not verify delivery ({str(e)[:160]})'}


def _deliver_review(store, rv, final, verb, actor, note=None, cc=None, envelope=None, send_fn=None):
    """Claim, send or reconcile, persist the outcome, then settle the task.

    Review status stays pending until delivery is confirmed. The durable claim and
    immutable attempt survive a process interruption without granting a second send.
    """
    from . import outbound
    rid = rv['ReviewId']
    env = dict(envelope if envelope is not None else _envelope(rv))
    msg = store.get_message(rv.get('MessageId')) if rv.get('MessageId') else None
    # FILES ARE NOT AN ADDRESS. A reply's envelope stays empty until the send works out who it goes to, and attaching
    # to it wrote {"attachments": [...]} alone - which read as new outbound mail with no recipient (2026-10-07: a
    # session's `--attach`; the owner's Attach button did the same). Only a destination makes it outgoing - not files,
    # not a cc, not the bookkeeping a failed attempt leaves behind, which is how a retry kept failing the same way.
    outgoing = env.get('kind') not in (None, '', 'reply') or (not env.get('kind') and bool(env.get('to') or env.get('channel')))
    if not outgoing and env.get('kind') != 'reply':
        files = env.get('attachments')
        env = {**(outbound.reply_envelope(store, msg) or {'kind': 'reply'}), **({'attachments': files} if files else {})}
    if cc is not None: env['cc'] = list(cc)
    snapshot = {'envelope': env, 'message': msg, 'body': final, 'status': VERB2STATUS[verb],
                'actor': actor, 'note': note, 'attempted_at': _now_iso()}
    claim = store.claim_review_delivery(rid, snapshot, rv)
    if not claim: return _delivery_busy(store, rid)
    token, attempted = claim['token'], claim['snapshot']
    finished = False

    def unknown(why):
        nonlocal finished
        error = f'delivery unknown - {why}; nothing was sent again. Check with the provider before retrying.'
        finished = store.finish_review_delivery(rid, token, 'unknown', reason=error)
        if rv.get('TaskId'): store.add_comment(rv['TaskId'], actor, 'human', f'DELIVERY UNKNOWN - {error}')
        store.audit('review', rid, 'delivery_unknown', actor, detail={'error': why[:200]})
        return {'ok': False, 'status': 'pending', 'sent': None, 'send_error': error, 'delivery': 'unknown'}

    def confirmed(sent, reconciled=False):
        nonlocal finished
        if not isinstance(sent, dict) or not isinstance(sent.get('channel'), str) or not sent['channel']:
            return unknown('the provider returned no usable delivery receipt')
        finished = store.finish_review_delivery(rid, token, 'sent', receipt=sent)
        if not finished: raise RuntimeError('the provider receipt could not be saved; verify delivery before retrying')
        if rv.get('MessageId'): store.set_message_status(rv['MessageId'], 'sent')
        if attempted['envelope'].get('kind') == 'zoho_invoice':
            from . import invoice_workflow
            invoice_workflow.mark_sent(store, int(attempted['envelope'].get('item_id')),
                                        attempted['envelope'].get('subject'), attempted['body'])
        if rv.get('TaskId'):
            copied = f", copied {', '.join(sent.get('cc') or [])}" if sent.get('cc') else ''
            files = f" with {', '.join(sent.get('attached') or [])}" if sent.get('attached') else ''
            store.add_comment(rv['TaskId'], actor, 'human', f"Reviewed draft ({verb}):\n{attempted['body']}")
            store.add_comment(rv['TaskId'], actor, 'human',
                              ('The earlier send was confirmed with the provider; nothing was sent again. ' if reconciled else '')
                              + f"Sent by {sent.get('channel') or 'the channel'} to {', '.join(sent.get('to') or []) or 'the chat'}{copied}{files}.")
        store.audit('review', rid, 'reconciled_sent' if reconciled else 'sent_outbound' if outgoing else verb, actor,
                    detail={'kind': rv.get('Kind'), 'sent': True, 'channel': sent.get('channel'), 'to': sent.get('to')})
        _settle_task_after_sent_reply(store, rv, actor, True)
        # A reply that ASKED them something keeps watching for the answer, though the send closed the task (asks.py)
        watching = None
        if not outgoing and rv.get('Kind') not in ('action', 'slot'):
            from . import asks
            try: watching = asks.watch_reply(store, rv, attempted['body'])
            except Exception as e: logger.warning(f'the reply watch did not start on review {rid}: {e}')
        return {'ok': True, 'status': attempted['status'], 'sent': sent, 'send_error': None,
                'delivery': 'reconciled' if reconciled else 'sent', **({'watching': watching} if watching else {})}

    try:
        if claim['previous'] in ('unknown', 'sending'):
            checked = _reconcile_snapshot(store, attempted)
            if checked['state'] == 'sent': return confirmed(checked['sent'], True)
            if checked['state'] != 'absent': return unknown(checked.get('reason') or 'the earlier delivery cannot be verified')
            # Only an explicit provider-confirmed absence permits another attempt.
            moved, _latest = context_moved(store, rv)
            if moved:
                store.mark_review_stale(rid)
                finished = store.finish_review_delivery(rid, token, 'failed',
                                                        reason='The earlier attempt was confirmed absent, but the conversation changed; redraft before sending.')
                return {'ok': False, 'status': 'pending', 'sent': None, 'delivery': 'failed', 'stale': True,
                        'send_error': 'The earlier attempt was not delivered. New messages arrived; redraft with the latest context before sending.'}
            if not store.start_review_delivery(rid, token, snapshot): return _delivery_busy(store, rid)
            attempted = snapshot
        if not outgoing:
            block = outbound.send_block(store, (msg or {}).get('Channel'))
            if block:
                error = f'not sent - {block}'
                finished = store.finish_review_delivery(rid, token, 'failed', reason=f'approved, but it cannot be sent from here: {block}')
                if rv.get('TaskId'): store.add_comment(rv['TaskId'], actor, 'human', f'NOT SENT - {block}. The approved text is kept as the draft.')
                store.audit('review', rid, verb, actor, detail={'kind': rv.get('Kind'), 'sent': False, 'blocked': block})
                return {'ok': False, 'status': 'pending', 'sent': None, 'send_error': error, 'delivery': 'failed'}
        try:
            sent = send_fn(attempted) if send_fn is not None else _send_snapshot(store, attempted)
        except outbound.UNKNOWN_ERRORS as e:
            checked = _reconcile_snapshot(store, attempted)
            if checked['state'] == 'sent': return confirmed(checked['sent'], True)
            return unknown(f'the provider did not answer ({str(e)[:120]}); {checked.get("reason") or "no delivery receipt is available"}')
        except Exception as e:
            if outbound.delivery_uncertain(e):
                checked = _reconcile_snapshot(store, attempted)
                if checked['state'] == 'sent': return confirmed(checked['sent'], True)
                return unknown(f'the provider did not establish delivery ({str(e)[:120]})')
            error = str(e)[:300]
            finished = store.finish_review_delivery(rid, token, 'failed', reason=f'approved, but sending FAILED: {error} - fix the channel and approve again')
            if attempted['envelope'].get('kind') == 'zoho_invoice' and attempted['envelope'].get('item_id'):
                from . import invoice_workflow
                invoice_workflow.mark_send_error(store, int(attempted['envelope']['item_id']), error)
            if rv.get('TaskId'): store.add_comment(rv['TaskId'], actor, 'human', f'NOT SENT - {error}. The approved text is kept as the draft.')
            store.audit('review', rid, 'delivery_failed', actor, detail={'error': error[:200]})
            return {'ok': not outgoing, 'status': 'pending', 'sent': None, 'send_error': error, 'delivery': 'failed'}
        return confirmed(sent)
    finally:
        if not finished:
            # KeyboardInterrupt, cancellation and failed bookkeeping cannot turn an
            # interrupted attempt into a fresh send. SIGKILL is recovered from SQLite.
            store.finish_review_delivery(rid, token, 'unknown', reason='Delivery unknown after an interrupted attempt; verify with the provider before retrying.')


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
    if kind == 'slot':                                 # one of the task's emails: it ticks itself, the last one closes
        from . import slots
        if was_sent: slots.settled(store, rv, True, actor)
        return
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

    # SEND, THEN MARK DONE - the one close every door takes (concierge.close_task: done, drafts retired, the agent
    # stopped, off the rail). It used to keep the task open while an agent still worked it, and before that while the
    # owner had opened a session on it (the owner, 2026-09-24: "send the reply should send then close").
    # ...unless the work is still going (the owner, 2026-09-24: "if session still going, i don't think we should force
    # close it... if new message comes in while sending reply, it should stay on"). Mark done is the owner's own word
    # and always closes; a send only closes what nothing is still happening on.
    from .funnel import working_tids
    if task_id in working_tids(store):
        store.add_comment(task_id, actor, 'human', 'Reply sent. The agent is still working on it, so the task stays open.')
        return
    if _newer_inbound(store, task_id, rv):
        store.add_comment(task_id, actor, 'human', 'Reply sent. A new message came in meanwhile, so the task stays open.')
        return
    # ...nor while its close-out waits: closing here would dismiss the merge (or the issue's close) the owner has not answered
    from . import proposals
    if proposals.closeout_pending(store, task_id):
        store.add_comment(task_id, actor, 'human', 'Reply sent. The task closes when you answer its close-out.')
        return
    # ...nor while its playbook is undecided: the close-out is done, the playbook is the other half (the owner, 2026-10-01)
    if proposals.closed_out(store, task_id, actor, 'Reply sent.'):
        store.add_comment(task_id, actor, 'human', 'Closed - the reply went out.')


def _newer_inbound(store, task_id: int, rv: dict) -> bool:
    """A message from someone else on this task, newer than the one this reply answered."""
    from .ingest import is_ours
    answered = store.get_message(rv['MessageId']) if rv.get('MessageId') else None
    since = str((answered or {}).get('SentAt') or rv.get('CreatedAt') or '')
    return any(str(m.get('SentAt') or '') > since and not is_ours(m) and m.get('MessageId') != rv.get('MessageId')
               for m in store.list_messages(task_id) or [])


def _carried(store, closeout: dict, reply: dict) -> bool:
    """Does the close-out itself carry this reply? A reply to a GitHub PR or issue IS a comment on it, so it goes WITH
    the merge/close the owner approved - not as a separate send that the GitHub card's replies switch refuses (the
    owner, 2026-09-27: "it should be close pr with message not separate section")."""
    msg = store.get_message(reply['MessageId']) if reply.get('MessageId') else {}
    return str((msg or {}).get('Channel') or '').lower() == 'github'


def _post_with_closeout(store, closeout: dict, reply: dict, text: str, actor: str) -> dict:
    """Post the reply as the comment on the PR/issue the close-out just acted on, and file it as sent."""
    from . import github, proposals
    from .ci import _conn
    p = json.loads(closeout.get('DraftText') or '{}')
    if p.get('action') == 'merge_pr': repo, num = p['repo'], int(p['number'])
    else:
        m = proposals._ISSUE.search(str((store.get_task(closeout['TaskId']) or {}).get('SourceRef') or ''))
        if not m: return {'ok': False, 'send_error': 'no issue to comment on'}
        repo, num = m.group(1), int(m.group(2))
    body = (text or '').strip() or str(reply.get('DraftText') or '').strip()
    if not body: return {'ok': False, 'send_error': 'the reply is empty'}
    envelope = {'kind': 'closeout_comment', 'channel': 'github', 'to': [f'{repo}#{num}']}
    def post(snapshot):
        url = github.comment_issue(_conn(store)['Secret'], repo, num, snapshot['body'])
        return {'channel': 'github', 'to': [f'{repo}#{num}'], 'url': url}
    verb = 'edit' if body != str(reply.get('DraftText') or '').strip() else 'approve'
    return _deliver_review(store, reply, body, verb, actor, f'posted on {repo}#{num} with the close-out',
                           envelope=envelope, send_fn=post)


def decide(store, rv: dict, verb_in: str, final_text: str = None, note: str = None,
           actor: str = 'owner', learn_async=None, cc: list = None, reply_text: str = None) -> dict:
    """Land one verdict on a pending review. learn_async(fn, *args) defers the learning
    call (the API hands FastAPI's background task runner in); None runs it inline.

    `cc` loops somebody in on this answer. Replies get the list chosen at approval; a new outbound
    email starts with the list deliberately saved in its delivery envelope, which remains visible
    and editable on the task.

    `reply_text` on a close-out is ONE press for the task's last two acts (the owner, 2026-09-27: "shouldn't we
    combine this? meaning reply on close?"): the merge/close runs first, and only when it succeeded does the task's
    pending reply go out with this text - a refused merge sends nothing. Each lands through its own verdict below."""
    from . import learn, outbound
    reviewed = rv
    store.recover_review_deliveries(rv['ReviewId'])
    rv = store.get_review(rv['ReviewId']) or rv
    if rv.get('DeliveryClaim'): return _delivery_busy(store, rv['ReviewId'])
    if rv.get('Status') == 'pending' and verb_in in ('approve', 'edit'):
        def content_envelope(row):
            return {k: v for k, v in _envelope(row).items() if k not in ('delivery', 'attempted_at', 'attempts')}
        if (any(reviewed.get(k) != rv.get(k) for k in ('DraftText', 'ContextRevision', 'Stale', 'TaskId', 'MessageId', 'Kind'))
                or content_envelope(reviewed) != content_envelope(rv)):
            return _delivery_busy(store, rv['ReviewId'])
    # ONE CLOSE OUT, WHICHEVER CARD IT WAS PRESSED ON (the owner, 2026-09-27): the phone and the walk put the task's REPLY
    # on the table, and its yes sent the reply alone - on GitHub with replies off a dead end, and never the merge
    if (verb_in in ('approve', 'edit') and reply_text is None and rv.get('Kind') not in ('action', 'clarification', 'slot')
            and rv.get('TaskId') and str(rv.get('Status') or 'pending') == 'pending'
            and rv.get('DeliveryState') not in ('unknown', 'sending')):
        from . import proposals
        co = proposals.closeout_pending(store, rv['TaskId'])
        if co: return decide(store, co, 'approve', None, note, actor, learn_async, cc,
                             reply_text=final_text if (final_text or '').strip() else '')
    if reply_text is not None and rv.get('Kind') == 'action' and verb_in in ('approve', 'edit', 'close_pr', 'merge_anyway'):
        out = decide(store, rv, verb_in, final_text, note, actor, learn_async)
        if not out.get('ok') or not rv.get('TaskId'): return out
        reply = store._one("SELECT * FROM review WHERE TaskId=? AND Status='pending' AND Kind NOT IN ('action','slot') ORDER BY ReviewId DESC LIMIT 1",
                           (rv['TaskId'],))
        if reply:
            sent = (_post_with_closeout(store, rv, reply, reply_text, actor) if _carried(store, rv, reply)
                    else decide(store, reply, 'approve', reply_text, None, actor, learn_async, cc))
            out['reply'] = sent
            if not sent.get('ok'): out['send_error'] = f"Done on GitHub, but the reply was not sent: {sent.get('send_error') or 'it was refused'}"
        return out
    rid = rv['ReviewId']
    # A verdict lands ONCE. There was no guard at all, so "approve" typed and the Approve button
    # clicked - or one double click - sent the same mail twice (2026-09-03).
    if str(rv.get('Status') or 'pending') != 'pending':
        return {'ok': False, 'status': rv.get('Status'), 'sent': None, 'already': True,
                'send_error': f"this one was already {rv.get('Status')}" + (f" by {rv['DecidedBy']}" if rv.get('DecidedBy') else '')}
    # ...and approving an EMPTY draft sent nothing, marked the review approved and closed the task
    # anyway: the person never got an answer and nothing was left in the pipe to say so.
    # ...and an email to a name nobody has resolved to an address goes nowhere: the provider is never handed a bare name
    # (a chat message's recipient is a chat id, never an address - slots.KINDS)
    if verb_in in ('approve', 'edit') and rv.get('Kind') == 'slot' and (_envelope(rv).get('channel') or 'email') == 'email' \
            and not all('@' in str(x) for x in (_envelope(rv).get('to') or [''])):
        return {'ok': False, 'status': 'pending', 'sent': None,
                'send_error': 'this email has no address yet - the agent fills it with --to, or drop it'}
    if verb_in in ('approve', 'edit') and not (final_text or '').strip() and not (rv.get('DraftText') or '').strip():
        return {'ok': False, 'status': 'pending', 'sent': None, 'empty': True,
                'send_error': 'there is no draft to send - write the reply (or let the AI draft it) and approve that'}
    # the draft is checked against the thread AS IT IS NOW before anything leaves (PW-055): a stale mark, or an
    # inbound message set that moved since the draft was pinned, refuses the send here - the Review button and
    # the phone road land through this one door, so neither can send yesterday's wording
    if (verb_in in ('approve', 'edit') and rv.get('Kind') != 'action' and rv.get('TaskId')
            and rv.get('DeliveryState') not in ('unknown', 'sending')):
        moved, _latest = context_moved(store, rv)
        if moved:
            if not rv.get('Stale'): store.mark_review_stale(rid)
            return {'ok': False, 'status': 'pending', 'sent': None, 'stale': True,
                    'send_error': 'New messages arrived after this draft was written - nothing was sent. Redraft it with the latest context and approve again.'}
    # Close without sending (PW-145): the owner's own word that no reply will go out - the unsent draft stays,
    # the closure and its reason are recorded, the reply obligation ends, and nothing here ever reads as Sent
    if verb_in == 'close_unsent' and rv.get('Kind') == 'slot':
        # one of the task's emails not sent: THAT email is dropped, the task is not closed (slots.settled)
        if not store.decide_review(rid, 'closed_unsent', rv.get('DraftText'), actor, str(note or '').strip() or 'not sent'): return _delivery_busy(store, rid)
        from . import slots
        slots.settled(store, rv, False, actor)
        return {'ok': True, 'status': 'closed_unsent', 'sent': None, 'send_error': None}
    if verb_in == 'close_unsent':
        why = str(note or '').strip() or (outbound.send_block(store, (store.get_message(rv['MessageId']) or {}).get('Channel')) if rv.get('MessageId') else '') or 'the owner chose not to send a reply'
        if not store.decide_review(rid, 'closed_unsent', rv.get('DraftText'), actor, why): return _delivery_busy(store, rid)
        if rv.get('TaskId'):
            store.add_comment(rv['TaskId'], actor, 'human', f'Closed without sending - no reply went out: {why}. The unsent draft is kept on the review.')
            # Close without sending IS Mark done (the owner, 2026-09-24): the one close, whoever opened a session on it
            from . import concierge
            concierge.close_task(store, rv['TaskId'], actor)
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
    if verb in ('close_pr', 'merge_anyway') and rv.get('Kind') != 'action':
        return {'ok': False, 'status': 'pending', 'sent': None, 'send_error': 'only a pull request close-out can be closed or merged that way'}
    if rv.get('Kind') == 'action':
        from . import proposals
        if verb == 'close_pr':
            try: out = proposals.close_pr(store, rv, actor)
            except Exception as e:
                store.add_comment(rv['TaskId'], actor, 'human', f'CLOSING THE PULL REQUEST FAILED: {str(e)[:300]}')
                return {'ok': False, 'status': 'pending', 'sent': None, 'send_error': str(e)[:300]}
            if not store.decide_review(rid, 'rejected', None, actor, 'closed the pull request without merging'): return _delivery_busy(store, rid)
            proposals.settle(store, rv, 'approve', actor)       # answered: the task ends like a merge ends it
            return {'ok': True, 'status': 'rejected', 'sent': None, 'send_error': None, 'result': out}
        if verb in ('approve', 'edit', 'merge_anyway'):
            try:
                out = proposals.execute(store, rv, actor, final, skip_checks=verb == 'merge_anyway')
            except Exception as e:
                store.add_comment(rv['TaskId'], actor, 'human', f'PROPOSAL FAILED: {str(e)[:300]}')
                return {'ok': False, 'status': 'pending', 'sent': None, 'send_error': str(e)[:300],
                        **({'offers': e.offers, 'refused': True} if isinstance(e, proposals.ChecksRed) else {}),
                        # a grant the token lacks (github.Refused.needs): the owner's to add - a retry only repeats it
                        **({'needs': e.needs} if getattr(e, 'needs', '') else {})}
            if not store.decide_review(rid, VERB2STATUS['approve'], rv.get('DraftText'), actor, note): return _delivery_busy(store, rid)
            proposals.settle(store, rv, 'approve' if verb == 'merge_anyway' else verb, actor)   # a close-out's yes closes the task
            return {'ok': True, 'status': 'approved', 'sent': None, 'send_error': None, 'result': out}
        if not store.decide_review(rid, VERB2STATUS[verb], None, actor, note): return _delivery_busy(store, rid)
        store.add_comment(rv['TaskId'], actor, 'human', f'Proposal {VERB2STATUS[verb]} - nothing was done.')
        proposals.settle(store, rv, verb, actor)
        return {'ok': True, 'status': VERB2STATUS[verb], 'sent': None, 'send_error': None}
    deliver = _envelope(rv)
    if final and (rv.get('MessageId') or deliver):
        result = _deliver_review(store, rv, final, verb, actor, note, cc)
        if not result.get('ok') or result.get('send_error'): return result
        sent, send_err = result.get('sent'), None
        # A confirmed edit still teaches the owner's voice below.
    else:
        if not store.decide_review(rid, VERB2STATUS[verb], final, actor, note): return _delivery_busy(store, rid)
        if final:
            store._exec("UPDATE review SET DeliveryState='not_required' WHERE ReviewId=?", (rid,))
        sent, send_err = None, None
        result = None
    if deliver.get('kind') == 'zoho_invoice' and verb in ('reject', 'no_reply') and deliver.get('item_id'):
        from . import invoice_workflow
        invoice_workflow.mark_skipped(store, int(deliver['item_id']))
    if rv.get('Kind') == 'slot' and verb in ('reject', 'no_reply'):
        from . import slots
        slots.settled(store, rv, False, actor)
    elif verb == 'no_reply' and rv.get('TaskId'):
        # the owner's word that nothing goes back IS Mark done - the one close, whoever opened a session on it
        from . import concierge
        concierge.close_task(store, rv['TaskId'], actor)
    # Sending is the lifecycle boundary. A final/manual answer closes the task and its live
    # terminal; a clarification stops the blocked terminal but deliberately leaves it waiting.
    if result is None and verb in ('approve', 'edit') and rv.get('TaskId') and not send_err:
        _settle_task_after_sent_reply(store, rv, actor, False)
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
    return result or {'ok': True, 'status': VERB2STATUS[verb], 'sent': sent, 'send_error': None}
