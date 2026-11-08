"""One door for review verdicts: the API endpoint and the phone road both decide HERE.
Approving IS sending - the answer goes back on the channel it arrived on - and a send that
FAILS returns the review to the queue wearing the error, so nothing looks finished that
never left the machine. The corrections feed LEARNED.md (an edit shows how the owner
writes, a reject what should never have been drafted).
"""
import hashlib, json, re
from pathlib import Path

from loguru import logger

from . import buttons

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
    # ...nor does a calendar answer (calwrite.py): it answers the invite, not the newest mail on the thread
    if _envelope(rv).get('kind') == 'calendar': return False, None
    if tid and (mine := _own_lines(store, rv)) is not None:
        # ...and a reply moves only with ITS conversation: a line on another thread of the task, from somebody it does not go to, is
        # theirs - Send on an agent's question to one requester redrafted it as an answer to a second one's "Perfect!" (2026-11-02)
        seen = operations.seen_upto(store, tid, rv['ContextRevision']) if rv.get('ContextRevision') else None
        # ...and a line triage read as an aside - a "thanks", a "got it" - is no news the draft is behind (2026-11-04)
        aside = store.aside_mids(tid)
        later = [m for m in mine if m['MessageId'] > max(rv['MessageId'], seen or 0) and m['MessageId'] not in aside]
        latest, moved = (later[-1] if later else None), bool(later)
    elif tid:
        # ...an aside here is no news either: the newest line that is not one, and a revision that moved only by asides has not moved
        aside = store.aside_mids(tid); latest = store.last_material_inbound_on_task(tid, skip=aside)
        if rv.get('ContextRevision'):
            moved = operations.message_revision(store, tid) != rv['ContextRevision']
            if moved and aside and (seen := operations.seen_upto(store, tid, rv['ContextRevision'])) is not None:
                moved = any(i > seen and i not in aside for i, _ in operations._material(store, tid))
        # a draft pinned to an aside (the thanks it last saw) has seen everything up to it: only a later line moves it
        elif rv.get('MessageId') in aside: moved = bool(latest and latest['MessageId'] > rv['MessageId'])
        else: moved = bool(latest and latest.get('MessageId') != rv.get('MessageId'))
    else:
        m = store.get_message(rv.get('MessageId')) if rv.get('MessageId') else None
        latest = store.last_inbound_in(m['ConversationId']) if m and m.get('ConversationId') else None
        moved = bool(latest and latest.get('MessageId') != rv.get('MessageId'))
    return bool(rv.get('Stale') or moved), latest


def _own_lines(store, rv: dict):
    """The task's material inbound lines (store.last_material_inbound_on_task's rule) that bear on this reply - on the thread of the
    message it answers, or from someone it goes to - oldest first. None where the reply has no thread to measure by."""
    m = store.get_message(rv['MessageId']) if rv.get('MessageId') else None
    if not (m and m.get('ConversationId')): return None
    env = _envelope(rv)
    them = {str(a).strip().lower() for a in [m.get('FromEmail'), *(env.get('to') or []), *(env.get('cc') or [])] if a}
    return [x for x in store._rows("SELECT * FROM message WHERE TaskId=? AND Status NOT IN ('context','history','skipped','filed') "
                                   "AND IFNULL(Direction,'in')<>'out' AND IFNULL(Channel,'')<>'report' ORDER BY MessageId", (rv['TaskId'],))
            if x.get('ConversationId') == m['ConversationId'] or str(x.get('FromEmail') or '').strip().lower() in them]


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
        d = {k: v for k, v in _envelope(r).items() if k not in ('delivery', 'attempted_at', 'fix')}     # how a send went is not what it says
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
    name = _safe(name)
    if not data: raise ValueError('that file is empty')
    from . import outbound
    if len(data) > outbound.ATTACH_MAX:
        raise ValueError(f'that file is over {outbound.ATTACH_MAX // (1024 * 1024)}MB, which no mailbox will accept')
    env = _envelope(rv)
    files = [f for f in (env.get('attachments') or []) if f.get('name') != name]
    # ...and one that fits alone but not beside the files already on: refused here, by its name, not at Send with the draft half-made
    if len(data) + sum(int(f.get('size') or 0) for f in files) > outbound.ATTACH_MAX:
        raise ValueError(f'with the files already on this reply it would come to more than {outbound.ATTACH_MAX // (1024 * 1024)}MB, '
                         'which no mailbox will accept - send a link instead')
    path = outbox_dir(rid) / name
    path.write_bytes(data)
    files.append({'name': name, 'path': str(path), 'size': len(data), 'sha256': hashlib.sha256(data).hexdigest()})
    env['attachments'] = files
    # ...a file said not attached earlier (refused) is attached now: its line comes off the card
    if env.get('not_attached'): env['not_attached'] = [f for f in env['not_attached'] if _safe(f.get('name')) != name]
    if not store.set_review_deliver(int(rid), json.dumps(env)):
        raise ValueError('the reply changed before its attachment could be saved')
    store.audit('review', int(rid), 'attached', actor, detail={'name': name, 'size': len(data)})
    return {'attachments': files}


def _safe(name) -> str: return SAFE_NAME.sub('_', str(name or '').strip())[:120] or 'attachment'


# A FILE THAT DID NOT RIDE IS SAID ON THE CARD (2026-11-04): an agent handed over three reports with long, near-identical names; the third
# was over the mailbox's cap and was refused - said in a comment under the agent's pane, while Close out showed two chips and nothing else,
# under a draft that said "here are the three". The refusal is kept on the envelope beside the files, by the name the agent gave and why,
# and the card draws it where the files are. Attaching a file of that name takes it off (_attach).
def refused(store, rid: int, name: str, why: str) -> bool:
    with store.review_delivery_edit(int(rid)):
        rv = store.get_review(int(rid)) or {}
        if rv.get('DeliveryClaim') or rv.get('DeliveryState') in ('sending', 'unknown'): return False
        env = _envelope(rv)
        env['not_attached'] = [f for f in (env.get('not_attached') or []) if f.get('name') != name] + [{'name': str(name), 'why': str(why)}]
        return store.set_review_deliver(int(rid), json.dumps(env))


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


def _more(env, *keys) -> dict:
    "The envelope's optional fields that are set - a sender that never had them is never handed them."
    return {k: env[k] for k in keys if env.get(k)}


def _send_snapshot(store, snapshot):
    """Only the durable approved payload crosses the provider boundary."""
    from . import outbound
    env, body = snapshot['envelope'], snapshot['body']
    if env.get('kind') == 'reply':
        return outbound.reply_to_message(store, snapshot['message'], body, to=env.get('to') or None,
                                         cc=env.get('cc'), attachments=env.get('attachments'), **_more(env, 'bcc', 'subject'))
    if env.get('kind') == 'zoho_invoice':
        from . import scopes, zoho
        c = store.get_connector(int(env.get('connector_id') or 0), with_secret=True)
        if not c: raise RuntimeError('the Zoho Invoice connector no longer exists')
        scopes.require(c, 'zoho_invoice_send')
        return zoho.send_invoice(zoho.connection(store, c['ConnectorId']), env.get('invoice_id'),
                                 env.get('to'), env.get('subject'), body)
    if env.get('kind') == 'calendar':                 # an invite answered or a meeting booked: the note is the comment
        from . import calwrite
        return calwrite.deliver(store, env, body)
    # a shared result (sharing.email) goes as HTML too - rendered from the text as approved, so the owner's edits are in both parts
    html = None
    if env.get('format') == 'html' and str(env.get('channel') or 'email').lower() == 'email':
        from .sharing import email_html
        html = email_html(env.get('subject') or '', body)
    return outbound.send_out(store, env.get('channel'), env.get('to'), env.get('subject'), body, cc=env.get('cc'), **_more(env, 'bcc'),
                             attachments=env.get('attachments'), mailbox=env.get('mailbox'), **({'html': html} if html else {}))


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


def _deliver_review(store, rv, final, verb, actor, note=None, cc=None, envelope=None, send_fn=None, anyway=False, bcc=None, subject=None):
    """Claim, send or reconcile, persist the outcome, then settle the task.

    Review status stays pending until delivery is confirmed. The durable claim and
    immutable attempt survive a process interruption without granting a second send.
    """
    from . import outbound
    rid = rv['ReviewId']
    env = dict(envelope if envelope is not None else _envelope(rv))
    # the reply goes to the mail that ASKED (AnswersMid); MessageId is the newest line it saw, which may be a "thanks" (2026-11-04)
    to_mid = rv.get('AnswersMid') or rv.get('MessageId')
    msg = store.get_message(to_mid) if to_mid else None
    # FILES ARE NOT AN ADDRESS. A reply's envelope stays empty until the send works out who it goes to, and attaching
    # to it wrote {"attachments": [...]} alone - which read as new outbound mail with no recipient (2026-10-07: a
    # session's `--attach`; the owner's Attach button did the same). Only a destination makes it outgoing - not files,
    # not a cc, not the bookkeeping a failed attempt leaves behind, which is how a retry kept failing the same way.
    outgoing = env.get('kind') not in (None, '', 'reply') or (not env.get('kind') and bool(env.get('to') or env.get('channel')))
    if not outgoing and env.get('kind') != 'reply':
        files = env.get('attachments')
        env = {**(outbound.reply_envelope(store, msg) or {'kind': 'reply'}), **({'attachments': files} if files else {})}
    if cc is not None: env['cc'] = list(cc)
    # ...and BCC and the subject as the card has them (the owner, 2026-11-08: one email card, every field editable, edits go out with Send)
    if bcc is not None: env['bcc'] = list(bcc)
    if subject is not None and ' '.join(str(subject).split()): env['subject'] = ' '.join(str(subject).split())[:200]
    # a NEW email on a task leaves from the mailbox the task's mail came in on - not the first Outlook card, which sent a
    # second mailbox's business out under the first one's address. Nothing came in by mail: send_out's own fallback, as before
    if outgoing and not env.get('kind') and str(env.get('channel') or '').lower() == 'email' and not env.get('mailbox'):
        box = outbound.task_mailbox(store, rv.get('TaskId'))
        if box: env['mailbox'] = box
    snapshot ={'envelope': env, 'message': msg, 'body': final, 'status': VERB2STATUS[verb],
                'actor': actor, 'note': note, 'attempted_at': _now_iso()}
    claim = store.claim_review_delivery(rid, snapshot, rv)
    if not claim: return _delivery_busy(store, rid)
    token, attempted = claim['token'], claim['snapshot']
    finished = False

    def unknown(why):
        nonlocal finished
        error = f"delivery unknown - {str(why).rstrip('.')}; nothing was sent again. Check with the provider before retrying."
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
        for m in {rv.get('MessageId'), rv.get('AnswersMid')} - {None}: store.set_message_status(m, 'sent')
        if attempted['envelope'].get('kind') == 'zoho_invoice':
            from . import invoice_workflow
            invoice_workflow.mark_sent(store, int(attempted['envelope'].get('item_id')),
                                        attempted['envelope'].get('subject'), attempted['body'])
        if rv.get('TaskId') and attempted['envelope'].get('kind') == 'calendar':
            from . import calwrite
            store.add_comment(rv['TaskId'], actor, 'human', calwrite.done_line(attempted['envelope'], attempted['body']))
        elif rv.get('TaskId'):
            copied = f", copied {', '.join(sent.get('cc') or [])}" if sent.get('cc') else ''
            files = f" with {', '.join(sent.get('attached') or [])}" if sent.get('attached') else ''
            store.add_comment(rv['TaskId'], actor, 'human', f"Reviewed draft ({verb}):\n{attempted['body']}")
            store.add_comment(rv['TaskId'], actor, 'human',
                              ('The earlier send was confirmed with the provider; nothing was sent again. ' if reconciled else '')
                              + f"Sent by {sent.get('channel') or 'the channel'} to {', '.join(sent.get('to') or []) or 'the chat'}{copied}{files}.")
        store.audit('review', rid, 'reconciled_sent' if reconciled else 'sent_outbound' if outgoing else verb, actor,
                    detail={'kind': rv.get('Kind'), 'sent': True, 'channel': sent.get('channel'), 'to': sent.get('to')})
        _settle_task_after_sent_reply(store, rv, actor, True)
        try:                                            # the ledger: did the thread go quiet, or did it take more rounds? (outcomes.py)
            from . import outcomes
            tid = rv.get('TaskId'); closed = bool(tid and (store.get_task(tid) or {}).get('Status') in ('done', 'dropped'))
            outcomes.record(store, 'reply.sent', 'task' if tid else 'message', tid or rv.get('MessageId') or 0, actor,
                            facts={'cid': (msg or {}).get('ConversationId'), 'mid': rv.get('MessageId'), 'review': rid, 'verb': verb, 'closed': closed,
                                   # the person facts (build step 4): whom, who was copied, and whether this was a chase (task.chase marks its review)
                                   'who': str((msg or {}).get('FromEmail') or '').lower(), 'cc': [str(a).lower() for a in (sent.get('cc') or [])],
                                   'chase': str(rv.get('Reason') or '').startswith('chase:')})   # task.chase's own mark, with its colon
        except Exception as e: logger.warning(f'review {rid}: the outcome row was not written - {e}')
        # A reply that ASKED them something keeps watching for the answer, even once the task is marked done (asks.py) -
        # whether it asked is the model's to read, off this thread: the button never waits on it
        if not outgoing and rv.get('Kind') not in ('action', 'slot'):
            from . import asks
            try: asks.watch_reply(store, rv, attempted['body'])
            except Exception as e: logger.warning(f'the reply watch did not start on review {rid}: {e}')
        return {'ok': True, 'status': attempted['status'], 'sent': sent, 'send_error': None,
                'delivery': 'reconciled' if reconciled else 'sent'}

    try:
        if claim['previous'] in ('unknown', 'sending'):
            checked = _reconcile_snapshot(store, attempted)
            if checked['state'] == 'sent': return confirmed(checked['sent'], True)
            # SEND ANYWAY (2026-10-18): a provider that keeps no receipt (plain SMTP) never answers "absent", and every press of Send
            # or Try again answered "nothing was sent again" - a loop with no way out. Only the owner's own Send anyway goes past it.
            if checked['state'] != 'absent' and not anyway: return unknown(checked.get('reason') or 'the earlier delivery cannot be verified')
            if checked['state'] != 'absent': store.audit('review', rid, 'send_anyway', actor, detail={'checked': checked.get('state')})
            # Only an explicit provider-confirmed absence permits another attempt.
            moved, _latest = context_moved(store, rv)
            if moved:
                store.mark_review_stale(rid)
                finished = store.finish_review_delivery(rid, token, 'failed',
                                                        reason=f"The earlier attempt was confirmed absent, but the conversation changed - {buttons.label('redraft')} before sending.")
                # the way on is the draft's own button, by its one name (buttons.json) - never a description of what to do
                return {'ok': False, 'status': 'pending', 'sent': None, 'delivery': 'failed', 'stale': True,
                        'send_error': f"The earlier attempt was not delivered, and new messages arrived since - {buttons.label('redraft')} before sending."}
            if not store.start_review_delivery(rid, token, snapshot): return _delivery_busy(store, rid)
            attempted = snapshot
        if not outgoing:
            block = outbound.send_block(store, (msg or {}).get('Channel'))
            if block:
                error = f'not sent - {block}'
                fix = outbound.block_fix(store, (msg or {}).get('Channel'))
                finished = store.finish_review_delivery(rid, token, 'failed', reason=f'Not sent: {block}.', fix=fix)
                if rv.get('TaskId'): store.add_comment(rv['TaskId'], actor, 'human', f'NOT SENT - {block}. The approved text is kept as the draft.')
                store.audit('review', rid, verb, actor, detail={'kind': rv.get('Kind'), 'sent': False, 'blocked': block})
                return {'ok': False, 'status': 'pending', 'sent': None, 'send_error': error, 'send_fix': fix, 'delivery': 'failed'}
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
            # said in words, once (failures.classify): a mail server's raw answer is its bookkeeping, not the owner's sentence
            from . import failures
            error, fix = failures.classify(e, act='review.approve')['sentence'][:300], outbound.fix_of(e)
            # ONE sentence, said once: the reason, the comment and the card each said it again in their own words (2026-10-17)
            finished = store.finish_review_delivery(rid, token, 'failed', reason=f'Not sent: {error}.', fix=fix)
            if attempted['envelope'].get('kind') == 'zoho_invoice' and attempted['envelope'].get('item_id'):
                from . import invoice_workflow
                invoice_workflow.mark_send_error(store, int(attempted['envelope']['item_id']), error)
            if rv.get('TaskId'): store.add_comment(rv['TaskId'], actor, 'human', f'NOT SENT - {error}. The approved text is kept as the draft.')
            store.audit('review', rid, 'delivery_failed', actor, detail={'error': error[:200]})
            return {'ok': not outgoing, 'status': 'pending', 'sent': None, 'send_error': error, 'send_fix': fix, 'delivery': 'failed'}
        return confirmed(sent)
    finally:
        if not finished:
            # KeyboardInterrupt, cancellation and failed bookkeeping cannot turn an
            # interrupted attempt into a fresh send. SIGKILL is recovered from SQLite.
            store.finish_review_delivery(rid, token, 'unknown', reason='Delivery unknown after an interrupted attempt; verify with the provider before retrying.')


# A REPLY NO LONGER NEEDED IS SAID, NOT DELETED (Task 4.5, the owner 2026-11-04): a colleague on the thread answered what the owner was
# asked, and the drafted reply kept sitting there "ready to send". The agent, re-planning on the change, says so on the draft - the card
# shows "Not needed - <why>" with Send still under it. Nothing is sent, deleted or closed: the owner decides, and a redraft clears it.
def not_needed(store, tid: int, why: str, by: str) -> dict:
    "Mark the task's pending reply not needed, for `why`. {'ok': False, 'why': ...} when there is none or no reason was given."
    why = ' '.join(str(why or '').split())
    if not why: return {'ok': False, 'why': 'say why the reply is not needed - who answered it, or what changed'}
    rv = store.pending_review(tid, kind='draft') or store.pending_review(tid, kind='draft_reply')
    if not rv: return {'ok': False, 'why': 'no reply is waiting on this task, so there is nothing to mark'}
    store.set_review_not_needed(rv['ReviewId'], why)
    store.add_comment(tid, by, 'agent', f"The drafted reply is not needed: {why.rstrip('.')}. It stays on the task - Send still sends it.")
    return {'ok': True, 'review_id': rv['ReviewId']}


# ...AND ONE THAT NO LONGER ANSWERS IS WITHDRAWN (the owner, 2026-11-06: corrected, the agent left its earlier draft standing under the newest
# turn as if it answered the correction): the agent takes it off the table itself, with why. Closed unsent like a superseded draft - its words
# kept under Close out's "Not sent", Bring it back still sends it - never deleted
def withdraw(store, tid: int, why: str, by: str, which='', keep: int = 0) -> dict:
    """Withdraw one unsent draft on the task, for `why`: `which` is its review id or who it was to; none means the reply draft (or the one
    unsent thing, when there is only one). {'ok': False, 'why': ...} when there is none, several match, or no reason was given.
    `keep`: a review never taken back - the new draft that `replaces` this one, which may be the same person's own slot."""
    from . import slots
    from .wrapup import WITHDRAWN
    why, which = ' '.join(str(why or '').split()), ' '.join(str(which or '').split()).casefold().removeprefix('rv')
    if not why: return {'ok': False, 'why': 'say in one line why the draft no longer answers - what the newest message changed'}
    left = [r for r in unsent(store, tid) if r['rid'] != keep]
    if not left: return {'ok': False, 'why': 'nothing unsent is waiting on this task, so there is nothing to withdraw'}
    if which.isdigit(): hit = [r for r in left if r['rid'] == int(which)]
    elif which: hit = [r for r in left if which in r['to'].casefold() or which in r['what'].casefold()]
    else: hit = [r for r in left if r['kind'] in ('draft', 'draft_reply')][:1] or (left if len(left) == 1 else [])
    if len(hit) != 1:
        return {'ok': False, 'why': ('several match - ' if hit else 'name which one - ' if not which else f'nothing unsent matches {which!r} - ') +
                'give its review id: ' + '; '.join(f"{r['rid']}: {r['what']}" for r in (hit or left))}
    r = hit[0]
    if not store.decide_review(r['rid'], 'closed_unsent', None, by, note=WITHDRAWN + why[:300]):
        return {'ok': False, 'why': 'that one is being sent or already went - it cannot be withdrawn'}
    if r['kind'] == slots.KIND and (sid := slots.of_review(store.get_review(r['rid']))): slots.mark(store, tid, sid, done=True, actor=by)
    back = '' if r['kind'] == 'action' else ' It is kept under Not sent - Bring it back still sends it.'
    store.add_comment(tid, by, 'agent', f"Withdrew {r['what']}: {why.rstrip('.')}.{back}")
    return {'ok': True, 'review_id': r['rid']}


def unsent(store, tid: int) -> list:
    """What the agent may still take back on task `tid`, newest first: its reply draft, its emails (slots), its posts and other proposals -
    each {rid, kind, to, what}. Never a close-out or a playbook (Taskuary's, not the agent's), and never anything already sent."""
    from . import proposals
    out = []
    for rv in store._rows("SELECT * FROM review WHERE TaskId=? AND Status IN ('pending','held') AND DeliveryClaim IS NULL "
                          "AND IFNULL(DeliveryState,'')<>'sent' ORDER BY ReviewId DESC", (int(tid),)):
        k = rv.get('Kind')
        try: d = json.loads((rv.get('DraftText') if k == 'action' else rv.get('Deliver')) or '{}') or {}
        except (TypeError, ValueError): d = {}
        if not isinstance(d, dict): d = {}
        if k == 'action':
            if d.get('closeout') or d.get('action') in (*proposals.PLAYBOOKS, *proposals.CLOSEOUT) or str(rv.get('Reason') or '').startswith('the workflow'): continue
            to, what = str(d.get('type') or d.get('action') or ''), f"the proposal ({' '.join(str(rv.get('Reason') or d.get('action')).split())[:160]})"
        elif k in ('draft', 'draft_reply', 'slot'):
            to = ', '.join(d.get('to') or []) if isinstance(d.get('to'), list) else str(d.get('to') or '')
            if not to and rv.get('MessageId'): to = str((store.get_message(rv['MessageId']) or {}).get('FromEmail') or '')
            what = f"the {'email' if k == 'slot' else 'reply'}" + (f' to {to}' if to else '')
        else: continue
        out.append({'rid': rv['ReviewId'], 'kind': k, 'to': to, 'what': what})
    return out


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
    if kind == 'slot':                                 # one of the task's emails: it ticks itself, and closes nothing
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
    # SENDING IS NOT CLOSING (the owner, 2026-10-18: "sending and closing are two steps, never automatic"): the reply went
    # out and the task stays open - on the table with its receipt - until the owner's own Mark done (concierge.close_task).
    # It used to close here past a list of guards (an agent still on it, a newer message, a close-out or playbook waiting).


def _blanked(text):
    """The refusal for a draft still holding a slot like "[REASON]" (blanks.py) - None when it can go. `blanks` names them, so
    the card marks the ones its box holds."""
    from . import blanks
    found = blanks.find(text or '')
    return {'ok': False, 'status': 'pending', 'sent': None, 'blanks': found, 'send_error': blanks.refusal(text)} if found else None


def _carried(store, closeout: dict, reply: dict) -> bool:
    """Does the close-out itself carry this reply? A reply to a GitHub PR or issue IS a comment on it, so it goes WITH
    the merge/close the owner approved - not as a separate send that the GitHub card's replies switch refuses (the
    owner, 2026-09-27: "it should be close pr with message not separate section")."""
    to_mid = reply.get('AnswersMid') or reply.get('MessageId')      # the mail that asked, as _deliver_review sends it
    msg = store.get_message(to_mid) if to_mid else {}
    return str((msg or {}).get('Channel') or '').lower() == 'github'


def _post_with_closeout(store, closeout: dict, reply: dict, text: str, actor: str, blanks_ok: bool = False) -> dict:
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
    if not blanks_ok and (gap := _blanked(body)): return gap
    envelope = {'kind': 'closeout_comment', 'channel': 'github', 'to': [f'{repo}#{num}']}
    def post(snapshot):
        url = github.comment_issue(_conn(store)['Secret'], repo, num, snapshot['body'])
        return {'channel': 'github', 'to': [f'{repo}#{num}'], 'url': url}
    verb = 'edit' if body != str(reply.get('DraftText') or '').strip() else 'approve'
    return _deliver_review(store, reply, body, verb, actor, f'posted on {repo}#{num} with the close-out',
                           envelope=envelope, send_fn=post)


def decide(store, rv: dict, verb_in: str, *a, **kw) -> dict:
    """_decide, and a yes that went wakes the task's agent where its last turn said it waits on that Send (general.follow_up)."""
    out = _decide(store, rv, verb_in, *a, **kw)
    if verb_in in ('approve', 'edit') and out.get('ok') and not out.get('send_error') and rv.get('TaskId'):
        from . import general
        general.follow_up(store, rv['TaskId'], 'send', a[2] if len(a) > 2 else kw.get('actor', 'owner'))
    return out


def _decide(store, rv: dict, verb_in: str, final_text: str = None, note: str = None,
           actor: str = 'owner', learn_async=None, cc: list = None, reply_text: str = None, anyway: bool = False, fields: dict = None,
           blanks_ok: bool = False, bcc: list = None, subject: str = None) -> dict:
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
                             reply_text=final_text if (final_text or '').strip() else '', blanks_ok=blanks_ok)
    if reply_text is not None and rv.get('Kind') == 'action' and verb_in in ('approve', 'edit', 'close_pr', 'merge_anyway'):
        # ...and a reply still holding a blank stops the press BEFORE the merge: "Done on GitHub, but the reply was not sent" over a
        # [REASON] left in it is half an act the owner never meant (blanks.py, the owner, 2026-10-30)
        if rv.get('TaskId'):
            waiting = store._one("SELECT * FROM review WHERE TaskId=? AND Status='pending' AND Kind NOT IN ('action','slot') ORDER BY ReviewId DESC LIMIT 1",
                                 (rv['TaskId'],))
            if waiting:
                from . import signatures
                typed = signatures.unsigned(reply_text, signatures.for_review(store, waiting)).strip()
                gap = None if blanks_ok else _blanked(reply_text if typed else waiting.get('DraftText'))
                if gap: return gap
        out = decide(store, rv, verb_in, final_text, note, actor, learn_async)
        if not out.get('ok') or not rv.get('TaskId'): return out
        reply = store._one("SELECT * FROM review WHERE TaskId=? AND Status='pending' AND Kind NOT IN ('action','slot') ORDER BY ReviewId DESC LIMIT 1",
                           (rv['TaskId'],))
        if reply:
            from . import signatures         # the signature alone in the box is no reply text: the filed draft goes, as with an empty box
            if not signatures.unsigned(reply_text, signatures.for_review(store, reply)).strip(): reply_text = ''
            sent =(_post_with_closeout(store, rv, reply, reply_text, actor, blanks_ok) if _carried(store, rv, reply)
                    else decide(store, reply, 'approve', reply_text, None, actor, learn_async, cc, blanks_ok=blanks_ok))
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
    # A CALENDAR ANSWER NEEDS NO WORDS (calwrite.py): its note is optional, and an emptied box is "no note", never the line it held
    cal = _envelope(rv).get('kind') == 'calendar'
    if verb_in in ('approve', 'edit') and not cal and not (final_text or '').strip() and not (rv.get('DraftText') or '').strip():
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
                    'send_error': 'New messages arrived after this draft was written - nothing was sent. '
                                  f"Press {buttons.label('redraft')} for one written from the latest message, then {buttons.label('approve')}."}
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
        # THE SIGNATURE GOES ON ONCE, HERE (signatures.py): the box shows it, so a box holding only the signature is an empty box,
        # and the owner's words are compared with the draft above it - adding the block is not an edit the drafter learns from
        from . import signatures
        sig = signatures.for_review(store, rv)
        if sig and (final_text or '').strip() and not signatures.unsigned(final_text, sig).strip(): final_text = ''
        if sig and not (final_text or '').strip() and not signatures.unsigned(rv.get('DraftText'), sig).strip():
            return {'ok': False, 'status': 'pending', 'sent': None, 'empty': True,
                    'send_error': 'there is only your signature in the box - write the reply (or let the AI draft it) and send that'}
        final = final_text if (final_text or '').strip() or (cal and final_text is not None) else rv.get('DraftText')
        bare = lambda t: signatures.unsigned(t, sig).strip()
        verb = 'edit' if bare(final) != bare(rv.get('DraftText')) else 'approve'
        if sig or final is not None: final = signatures.sign(store, rv, final)     # ...and an email goes as plain text (chatformat.plain_text)
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
            proposals.settle(store, rv, 'approve', actor)       # answered, like a merge - the task stays open for Mark done
            return {'ok': True, 'status': 'rejected', 'sent': None, 'send_error': None, 'result': out}
        if verb in ('approve', 'edit', 'merge_anyway'):
            try:
                out = proposals.execute(store, rv, actor, final, skip_checks=verb == 'merge_anyway', fields=fields)
            except Exception as e:
                store.add_comment(rv['TaskId'], actor, 'human', f'PROPOSAL FAILED: {str(e)[:300]}')
                return {'ok': False, 'status': 'pending', 'sent': None, 'send_error': str(e)[:300],
                        **({'offers': e.offers, 'refused': True} if isinstance(e, proposals.ChecksRed) else {}),
                        # a grant the token lacks (github.Refused.needs): the owner's to add - a retry only repeats it
                        **({'needs': e.needs} if getattr(e, 'needs', '') else {})}
            if not store.decide_review(rid, VERB2STATUS['approve'], proposals.receipt(rv, final, out, fields), actor, note): return _delivery_busy(store, rid)
            proposals.settle(store, rv, 'approve' if verb == 'merge_anyway' else verb, actor)   # runs only the act: the task stays open
            return {'ok': True, 'status': 'approved', 'sent': None, 'send_error': None, 'result': out}
        if not store.decide_review(rid, VERB2STATUS[verb], None, actor, note): return _delivery_busy(store, rid)
        store.add_comment(rv['TaskId'], actor, 'human', f'Proposal {VERB2STATUS[verb]} - nothing was done.')
        proposals.settle(store, rv, verb, actor)
        return {'ok': True, 'status': VERB2STATUS[verb], 'sent': None, 'send_error': None}
    # A BLANK LEFT IN IT (the owner, 2026-10-30): "[REASON]" went out as written. The one door refuses it, so the phone and the
    # assistant meet the same "Fill in [REASON] first" the Send button does - nothing is decided, the draft stays as it is
    # ...but a send already attempted is checked as attempted (Check delivery), its text frozen - never a new refusal over it
    # ...and the owner's own Send anyway (`blanks_ok`, the owner 2026-11-08: the press asks once, "This still has [ROOM]. Send anyway?") goes
    if verb in ('approve', 'edit') and not blanks_ok and rv.get('DeliveryState') not in ('unknown', 'sending') and (gap := _blanked(final)): return gap
    deliver = _envelope(rv)
    if (final or (cal and verb in ('approve', 'edit'))) and (rv.get('MessageId') or deliver):
        result = _deliver_review(store, rv, final, verb, actor, note, cc, anyway=anyway, bcc=bcc, subject=subject)
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
    # a clarification stops the blocked terminal and leaves the task waiting; any other answer leaves it open for Mark done
    if result is None and verb in ('approve', 'edit') and rv.get('TaskId') and not send_err:
        _settle_task_after_sent_reply(store, rv, actor, False)
    store.audit('review', rid, verb, actor, detail={'kind': rv.get('Kind'), 'sent': bool(sent)})
    from .presses import personal as _personal
    m0 = (store.get_message(rv['MessageId']) if rv.get('MessageId') else None) or {}
    # ...a draft to someone in a PERSONAL workstream teaches neither voice nor memory (the owner, 2026-11-01)
    if verb in ('edit', 'reject', 'no_reply') and not cal and not _personal(store, {'tid': rv.get('TaskId')}, m0):   # a calendar note's one line teaches no voice
        m = m0
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
