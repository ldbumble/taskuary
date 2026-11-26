"""One door for review verdicts: the API endpoint and the phone road both decide HERE.
Approving IS sending - the answer goes back on the channel it arrived on - and a send that
FAILS returns the review to the queue wearing the error, so nothing looks finished that
never left the machine. The corrections feed LEARNED.md (an edit shows how the owner
writes, a reject what should never have been drafted).
"""
import contextvars, hashlib, json, re, threading
from .say import said as _said            # a failure written to the chat is said in his words (say.py)
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
        # ...worked out as the send works it out (outbound.review_envelope: the mail that ASKED, AnswersMid - this hashed MessageId's)
        from . import outbound
        return outbound.review_envelope(store, {**r, 'Deliver': '', 'DeliveryEnvelope': ''})
    basis = [(r.get('ReviewId'), str(r.get('DraftText') or '').strip(), env(r)) for r in rows]
    return hashlib.sha1(json.dumps(basis, sort_keys=True, default=str).encode()).hexdigest()[:16]


def _now_iso() -> str:
    from datetime import datetime, timezone
    return datetime.now(timezone.utc).strftime('%Y-%m-%dT%H:%M:%SZ')


SAFE_NAME = re.compile(r'[^A-Za-z0-9._ -]+')


def attach(store, rid: int, name: str, data: bytes, actor: str = 'owner', source: int = None) -> dict:
    with store.review_delivery_edit(int(rid)):
        return _attach(store, rid, name, data, actor, source)


def _attach(store, rid: int, name: str, data: bytes, actor: str = 'owner', source: int = None) -> dict:
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
    files.append({'name': name, 'path': str(path), 'size': len(data), 'sha256': hashlib.sha256(data).hexdigest(),
                  **({'attachment': int(source)} if source else {})})        # a file from the task's own mail: checked again at Send
    env['attachments'] = files
    # ...a file said not attached earlier (refused) is attached now: its line comes off the card
    if env.get('not_attached'): env['not_attached'] = [f for f in env['not_attached'] if _safe(f.get('name')) != name]
    if not store.set_review_deliver(int(rid), json.dumps(env)):
        raise ValueError('the reply changed before its attachment could be saved')
    store.audit('review', int(rid), 'attached', actor, detail={'name': name, 'size': len(data)})
    # ...HIS FILE ON A CARD IS HIS PRESS, AND THE AGENT'S TO HAVE (a walk, 2026-11-18): the bar's Attach put a sheet on the agent's draft, he
    # typed a line, the draft greyed - and the agent, never told, recreated the sheet from the mail and attached its own copy. Kept in the
    # task's folder (outputs.take_in, the chat box's road), where the propose tools take it by name, and said like every press (general.PRESSES)
    from .processing_unread import OWNER_ACTORS
    if actor in OWNER_ACTORS and rv.get('TaskId'):
        from . import outputs
        kept = outputs.take_in(int(rv['TaskId']), [path])
        store.audit('task', int(rv['TaskId']), 'reply_file_attached', actor, detail={'name': Path(kept[0]).name if kept else name})
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


_RUNNING, _RUNNING_LOCK = set(), threading.Lock()   # action reviews whose act is running right now (one server process per home)


# AN ACT A RESTART CUT IS SAID ON ITS CARD (the timeline stress round, 2026-11-18): the claim above lives in the process, so the next start drew
# a card whose comment or push was going up as never pressed - Approve lit, a second press ran it twice, and its agent heard nothing. The
# press is written down when it starts and when it ends; one started and never ended is told at start-up, its card left for his press
ACT_STARTED, ACT_ENDED = 'act_started', 'act_ended'
def cut_acts(store) -> list:
    "At start-up: every pressed act the last run did not see end, kept on its card as cut (general.ACT_CUT): [review ids]."
    from . import general
    out = []
    for r in store._rows("SELECT ReviewId FROM review WHERE Kind='action' AND Status IN ('pending','held')"):
        last = store._one("SELECT Action, Actor FROM audit WHERE EntityType='review' AND EntityId=? AND Action IN (?,?) ORDER BY Id DESC LIMIT 1",
                          (r['ReviewId'], ACT_STARTED, ACT_ENDED))
        if not last or last['Action'] != ACT_STARTED: continue
        store.review_act_failed(r['ReviewId'], general.ACT_CUT, last['Actor'])
        store.audit('review', r['ReviewId'], ACT_ENDED, 'startup', 'system', {'cut': True})
        out.append(r['ReviewId'])
    return out


def _claim_act(store, rid) -> bool:
    """This press may run the act: no other press is running it and its row still waits. A reply's send is claimed in the store before it
    leaves (claim_review_delivery); an action ran first and was marked answered after, so a double click - or the desk and the phone -
    ran one post, push or merge twice."""
    with _RUNNING_LOCK:
        if rid in _RUNNING or (store.get_review(rid) or {}).get('Status') not in ('pending', 'held'): return False
        _RUNNING.add(rid); return True


def _act_busy(store, rid):
    "The answer to a press that lost the claim: already answered says so, still running says nothing ran again."
    out = _delivery_busy(store, rid)
    return out if out.get('already') else {**out, 'send_error': 'This is already being done; nothing was run again.'}


# A PRESS THAT LOST TO AN ANSWER says what that answer was in words, one sentence on every road (the stress round, 2026-11-18: a phone pick
# of an email its agent had taken back read "already closed_unsent" - the store's own word)
STATUS_WORDS = {'approved': 'approved', 'edited': 'approved with changes', 'rejected': 'turned down', 'no_reply': 'marked as needing no reply',
                'closed_unsent': 'taken back unsent', 'superseded': 'replaced'}
def already(rv: dict) -> str:
    "'already turned down by you' - what became of a review no longer waiting, and whose answer it was."
    st, by = str(rv.get('Status') or ''), str(rv.get('DecidedBy') or '')
    word = 'sent' if rv.get('DeliveryState') == 'sent' else STATUS_WORDS.get(st, st.replace('_', ' ') or 'gone')
    return f"already {word}" + (f" by {'you' if by == 'owner' else by}" if by else '')


def _delivery_busy(store, rid):
    current = store.get_review(rid) or {}
    state = current.get('DeliveryState')
    if current.get('Status') != 'pending':
        return {'ok': False, 'status': current.get('Status'), 'sent': None, 'already': True, 'send_error': f"this one was {already(current)}"}
    return {'ok': False, 'status': 'pending', 'sent': None, 'delivery': state or 'pending',
            'send_error': ('A delivery check or send is already in progress; nothing was sent again.'
                           if current.get('DeliveryClaim') else 'This draft changed before approval; review it and approve again.')}


def _more(env, *keys) -> dict:
    "The envelope's optional fields that are set - a sender that never had them is never handed them."
    return {k: env[k] for k in keys if env.get(k)}


def _send_snapshot(store, snapshot):
    """Only the durable approved payload crosses the provider boundary."""
    from . import demo, outbound
    env, body = snapshot['envelope'], snapshot['body']
    if demo.enabled(): return demo.pretend_sent(snapshot)             # ...and in the demo nothing does: its Send is played
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


def _drafted(rv) -> str:
    """The draft the owner's words are measured against: what was DRAFTED - never the words a refused Send left in the box
    (finish_review_delivery keeps the attempted text as the draft so the box shows it), while the box still holds them."""
    if rv.get('DeliveryState') == 'failed':
        try: snap = json.loads(rv.get('DeliveryEnvelope') or '{}') or {}
        except (TypeError, ValueError): snap = {}
        if isinstance(snap.get('drafted'), str) and snap.get('body') == rv.get('DraftText'): return snap['drafted']
    return rv.get('DraftText')


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
    outgoing = outbound.new_mail(env)
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
    # ...A FILE THAT CAME ON THE TASK'S MAIL GOES ONLY WHILE THAT MAIL IS STILL THE TASK'S (agenttools.mail_file): checked at the door it was
    # attached by, and here again, before anything is claimed (an attempt already made is reconciled as it was, never refused here)
    for f in (env.get('attachments') or []) if rv.get('DeliveryState') not in ('sending', 'unknown') else []:
        if not f.get('attachment'): continue
        from .agenttools import mail_file
        try: mail_file(store, rv.get('TaskId'), f['attachment'], kept=False)
        except ValueError as e:
            return {'ok': False, 'status': 'pending', 'sent': None, 'send_error': f"Nothing was sent: {f.get('name')} - {e}. Take it off and Send again."}
    snapshot ={'envelope': env, 'message': msg, 'body': final, 'status': VERB2STATUS[verb], 'drafted': _drafted(rv),
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
        # ...and the letter is on its task as it goes - whom it reached, its thread - not only once its sent-folder copy comes back
        from .channels import record_sent
        try: record_sent(store, rv, attempted['body'], {**sent, 'to': sent.get('to') or attempted['envelope'].get('to')},
                             None if outgoing else msg, attempted['envelope'])
        except Exception as e: logger.warning(f'review {rid}: the sent letter was not recorded on its task - {e}')
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
                              + f"Sent by {sent.get('channel') or 'the channel'} to {', '.join(_went_to(store, rv, attempted) or sent.get('to') or []) or 'the chat'}{copied}{files}.")
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
                                   'chase': rv.get('Origin') == 'chase'})      # task.chase's own mark (review.Origin)
        except Exception as e: logger.warning(f'review {rid}: the outcome row was not written - {e}')
        # A reply that ASKED them something keeps watching for the answer, even once the task is marked done (asks.py) - and a new mail that
        # did waits for their input - whether it asked is the model's to read, off this thread: the button never waits on it
        if rv.get('Kind') != 'action':
            from . import asks
            new = outgoing or rv.get('Kind') == 'slot'
            try: asks.watch_reply(store, rv, attempted['body'], to=(_went_to(store, rv, attempted) or list(sent.get('to') or [])) if new else None)
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
        except Exception as e:
            if isinstance(e, outbound.UNKNOWN_ERRORS) and outbound.delivery_uncertain(e):
                checked = _reconcile_snapshot(store, attempted)
                if checked['state'] == 'sent': return confirmed(checked['sent'], True)
                return unknown(f'the provider did not answer ({str(e)[:120]}); {checked.get("reason") or "no delivery receipt is available"}')
            if outbound.delivery_uncertain(e):
                checked = _reconcile_snapshot(store, attempted)
                if checked['state'] == 'sent': return confirmed(checked['sent'], True)
                return unknown(f'the provider did not establish delivery ({str(e)[:120]})')
            # said in words, once (failures.classify): a mail server's raw answer is its bookkeeping, not the owner's sentence
            from . import failures
            error, fix = failures.classify(e, act='review.approve')['sentence'][:300], outbound.fix_of(e)
            # ...a channel that refused because it is not connected is fixed on its own card: reconnect, then Send again (2026-11-08)
            ch = str((msg or {}).get('Channel') or attempted['envelope'].get('channel') or '').lower()
            if not fix and ch and outbound.refused_before_send(e): fix = {'label': f'Reconnect {ch.replace("_", " ").title()}', 'href': f'#connector={ch}'}
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


# A REPLY NO LONGER NEEDED IS GONE (the owner, 2026-11-09, said ~40 times: "if we respond show on left side and then agent reevaluates if
# action still required"): the owner answered it themselves, or a colleague did, and the agent re-planning on that says so in its turn. The
# draft it no longer needs is retired like a withdrawn one - closed unsent, its words kept under Close out's "Not sent", Bring it back still
# sends it. It was once kept on the card as "Not needed - <why>" with Send under it (Task 4.5, 2026-11-04): that drew a reply nobody owed,
# with a Send, under the turn that said none was owed. Never deleted, never sent; a redraft is a new draft.
def not_needed(store, tid: int, why: str, by: str) -> dict:
    "Retire the task's pending reply as not needed, for `why`. {'ok': False, 'why': ...} when there is none or no reason was given."
    from .wrapup import WITHDRAWN
    why = ' '.join(str(why or '').split())
    if not why: return {'ok': False, 'why': 'say why the reply is not needed - who answered it, or what changed'}
    from .proposals import SET_ASIDE
    # ...the reply his own answer greyed is the one it retires (walk 11: he answered outside the app, his mail set the draft aside, and the
    # agent was told "no reply is waiting" - it said so to him, over the greyed letter that stood there)
    rv = (store.pending_review(tid, kind='draft') or store.pending_review(tid, kind='draft_reply')
          or store._one("SELECT * FROM review WHERE TaskId=? AND Kind IN ('draft','draft_reply') AND Status='superseded' AND DecideNote=? "
                        "AND IFNULL(DraftText,'')<>'' ORDER BY ReviewId DESC LIMIT 1", (tid, SET_ASIDE)))
    if not rv: return {'ok': False, 'why': 'no reply is waiting on this task, so there is nothing to mark'}
    store.set_review_not_needed(rv['ReviewId'], why)
    if not store.decide_review(rv['ReviewId'], 'closed_unsent', None, by, note=WITHDRAWN + why[:300], was=('pending', 'held', 'superseded')):
        return {'ok': False, 'why': 'that reply is being sent or already went - it cannot be put down'}
    store.add_comment(tid, by, 'agent', f"The drafted reply is not needed: {why.rstrip('.')}. It is kept under Not sent - Bring it back still sends it.")
    promotion_ended(store, tid, why)
    return {'ok': True, 'review_id': rv['ReviewId']}


def promotion_ended(store, tid: int, why: str) -> None:
    """A TASK HIS PROMOTION STARTED ENDED WITH NOTHING SENT: what that says is taught too, weighed against the line the press taught at once
    (server._learn_promotion's made_task) - the model may rewrite it, keep it or say nothing (the walk, 2026-11-22: a cold pitch sent to an
    agent and then "just ignore him" stood in memory as "you review these pitches yourself"). Only where that press taught a line."""
    from . import learning, memory
    for m in store.list_messages(int(tid)):
        src = f"msg{m['MessageId']}"
        if not memory.taught_on(store, src, 'made_task'): continue
        learning.teach_soon(store, 'made_task_ended', src,
                               f"The owner had sent this mail to an agent as work (the line learned then is above). It ended with nothing sent: "
                               f"{' '.join(str(why or '').split())[:300]}. From {m.get('FromName') or m.get('FromEmail') or 'its sender'}: "
                               f"{str(m.get('Subject') or '')[:120]}")


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
    # ...SEVERAL BY THEIR IDS, as a bulk card is named to its agent ("rv1 + rv2 + ...", cardqueue.says): each taken back, one call for the card
    if re.fullmatch(r'\d+(?:\s*[,+]\s*(?:rv)?\d+)+', which):
        got = [(x, withdraw(store, tid, why, by, x, keep)) for x in dict.fromkeys(re.findall(r'\d+', which))]
        done, bad = [g['review_id'] for _, g in got if g.get('ok')], [f"rv{x}: {g.get('why')}" for x, g in got if not g.get('ok')]
        return {'ok': bool(done), 'review_id': done[0] if done else None, 'review_ids': done, **({'why': '; '.join(bad)[:600]} if bad else {})}
    left = [r for r in unsent(store, tid) if r['rid'] != keep]
    if not left: return {'ok': False, 'why': 'nothing unsent is waiting on this task, so there is nothing to withdraw'}
    if which.isdigit(): hit = [r for r in left if r['rid'] == int(which)]
    elif which: hit = [r for r in left if which in r['to'].casefold() or which in r['what'].casefold()]
    else: hit = [r for r in left if r['kind'] in ('draft', 'draft_reply')][:1] or (left if len(left) == 1 and not left[0].get('handed') else [])
    if len(hit) != 1:
        return {'ok': False, 'why': ('several match - ' if hit else 'name which one - ' if not which else f'nothing unsent matches {which!r} - ') +
                'give its review id: ' + '; '.join(f"{r['rid']}: {r['what']}" for r in (hit or left))}
    r = hit[0]
    # ...an act his press handed to its agent, dropped on his word, ends with that press (cardqueue.handed): the line behind it moves on
    if not (store.review_unhanded(r['rid'], 'closed_unsent', None, WITHDRAWN + why[:300]) if r.get('handed')
            else store.decide_review(r['rid'], 'closed_unsent', None, by, note=WITHDRAWN + why[:300])):
        return {'ok': False, 'why': 'that one is being sent or already went - it cannot be withdrawn'}
    if r['kind'] == slots.KIND and (sid := slots.of_review(store.get_review(r['rid']))): slots.mark(store, tid, sid, done=True, actor=by)
    back = '' if r['kind'] == 'action' else ' It is kept under Not sent - Bring it back still sends it.'
    store.add_comment(tid, by, 'agent', f"Withdrew {r['what']}: {why.rstrip('.')}.{back}")
    return {'ok': True, 'review_id': r['rid']}


def unsent(store, tid: int) -> list:
    """What the agent may still take back on task `tid`, newest first: its reply draft, its emails (slots), its posts and other proposals -
    each {rid, kind, to, what}. Never a close-out or what Taskuary's own ledger put on a skill (theirs, not the agent's), and never
    anything already sent. A skill the agent proposed, or lessons it added to one, is its own to take back (the owner, 2026-11-10) - and so
    is an act his press handed it that has not been done (cardqueue.handed: walk 7, "nothing unsent" held the X post's line for good)."""
    from . import cardqueue, proposals
    def gave(r):
        t = str(cardqueue._p(r).get('type') or '')
        return {'rid': r['ReviewId'], 'kind': 'action', 'handed': True, 'to': t,
                'what': f"the {proposals.POSTS[t]} post handed to the browser" if t in proposals.POSTS else 'the step handed to the browser'}
    out = [gave(r) for r in store._rows("SELECT * FROM review WHERE TaskId=? AND Kind='action' AND Status IN ('approved','edited') ORDER BY ReviewId DESC",
                                        (int(tid),)) if cardqueue.handed(r)]
    for rv in store._rows("SELECT * FROM review WHERE TaskId=? AND Status IN ('pending','held') AND DeliveryClaim IS NULL "
                          "AND IFNULL(DeliveryState,'')<>'sent' ORDER BY ReviewId DESC", (int(tid),)):
        k = rv.get('Kind')
        try: d = json.loads((rv.get('DraftText') if k == 'action' else rv.get('Deliver')) or '{}') or {}
        except (TypeError, ValueError): d = {}
        if not isinstance(d, dict): d = {}
        if k == 'action':
            if d.get('closeout') or d.get('action') in proposals.CLOSEOUT or d.get('block') or str(rv.get('Reason') or '').startswith('the workflow'): continue
            to, what = str(d.get('type') or d.get('action') or ''), f"the proposal ({' '.join(str(rv.get('Reason') or d.get('action')).split())[:160]})"
        elif k in ('draft', 'draft_reply', 'slot'):
            # ...one nobody has written is nothing set up: a reply owed at arrival was told to the agent as "ALSO SET UP AND NOT SENT" (the audit)
            if not str(rv.get('DraftText') or '').strip(): continue
            to =', '.join(d.get('to') or []) if isinstance(d.get('to'), list) else str(d.get('to') or '')
            if not to and rv.get('MessageId'): to = str((store.get_message(rv['MessageId']) or {}).get('FromEmail') or '')
            what = f"the {'email' if k == 'slot' else 'reply'}" + (f' to {to}' if to else '')
        else: continue
        out.append({'rid': rv['ReviewId'], 'kind': k, 'to': to, 'what': what, **({} if k == 'action' else {'text': rv.get('DraftText') or ''})})
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
    # It used to close here past a list of guards (an agent still on it, a newer message, a close-out or skill waiting).


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
        url = github.comment_issue(_conn(store, repo)['Secret'], repo, num, snapshot['body'])
        return {'channel': 'github', 'to': [f'{repo}#{num}'], 'url': url}
    verb = 'edit' if body != str(reply.get('DraftText') or '').strip() else 'approve'
    return _deliver_review(store, reply, body, verb, actor, f'posted on {repo}#{num} with the close-out',
                           envelope=envelope, send_fn=post)


# ...ONE OF A BULK CARD'S ROWS (bulkcard.run): its agent hears the whole run once, at its end - never once a row
QUIET = contextvars.ContextVar('verdicts_quiet', default=False)


def decide(store, rv: dict, verb_in: str, *a, closes: bool = False, always: bool = False, **kw) -> dict:
    """_decide, and a yes that went wakes the task's agent where its last turn said it waits on that Send (general.follow_up).
    `closes`: Send and close - the task's close, through its one gate, as the send went (out['shut']).
    `always`: his "Always approve this step" on a routine's write card - it runs now, and that step of that routine as saved runs unpressed
    from then on (flow.grant). Only a routine's own step carries one; on any other card it is refused before anything runs."""
    from .proposals import _draft
    fr = _draft(rv).get('flow_run') if always else None
    if always and (verb_in != 'approve' or not isinstance(fr, dict) or not fr.get('key')):
        return {'ok': False, 'status': rv.get('Status'), 'sent': None, 'send_error': 'only a routine\'s own write step can be always approved - nothing was run'}
    out = _decide(store, rv, verb_in, *a, **kw)
    if always and out.get('ok'):
        from . import flow
        out['always'] = flow.grant(store, fr, a[2] if len(a) > 2 else kw.get('actor', 'owner'))
    # ...his answer on a proposed card is written down for the one rule (gate): the same card raised again after his no is refused as his.
    # A held act's own gate writes its own (perform, declined)
    if out.get('ok') and rv.get('Kind') == 'action' and rv.get('TaskId') and verb_in in ('approve', 'edit', 'reject'):
        from . import gate, proposals
        if proposals._action(rv) not in proposals.HELD_ACTS:
            gate.remember(store, rv['TaskId'], [gate.card_key(proposals._draft(rv))], 'dismissed' if verb_in == 'reject' else 'approved')
    # ...and a yes that WENT is recorded by Taskuary itself - the to-do its card does is ticked (card.went) - one of a bulk card's rows too
    went = verb_in in ('approve', 'edit', 'merge_anyway') and out.get('ok') and not out.get('send_error') and rv.get('TaskId')
    if went:
        from . import card
        try: card.went(store, rv)
        except Exception as e: logger.warning(f"rv{rv.get('ReviewId')}: it went, and its to-do was not ticked - {e}")
    if QUIET.get(): return out
    if went:
        from . import cardqueue, general, proposals
        actor = a[2] if len(a) > 2 else kw.get('actor', 'owner')
        # SEND AND CLOSE CLOSES BEFORE ITS AGENT IS TOLD (the agent walk, 2026-11-10): the close came a beat after the send, by the page's
        # own call - and by then the send had woken the agent parked on the task, so the gate found it working and kept the task open:
        # "Sent. Kept open: The agent session on it is still open", every time an agent had run. The owner said close: its agent, at
        # work or at rest, is stopped (concierge.close_after_send), never woken to be; a task kept open by something else that waits
        # on his press hears the send as before
        if closes and (out.get('reply') or {'ok': rv.get('Kind') != 'action'}).get('ok'):
            from . import concierge
            try: out['shut'] = concierge.close_after_send(store, rv['TaskId'], actor)
            except Exception as e: logger.warning(f"rv{rv.get('ReviewId')}: the send went, its close did not run - {e}")
        # ...EVERY yes that went, not only one its turn said it waits on (the owner, 2026-11-09) - a held step's own road tells its agent
        # ...where the agents are recordings (the demo) there is none to tell: the line one would say next is written instead - a wake there
        # ended the played Send on "No AI is connected" under a turn marked failed
        from . import demo
        if demo.enabled(): demo.after_send(store, rv['TaskId'])
        # ...ONCE FOR A ROW (the owner, 2026-11-23): a press with cards still waiting behind it is recorded on its card and wakes nobody; the
        # one that ends the row tells the agent, its screen fact naming every card of it (cardqueue.row_over)
        elif proposals._action(rv) not in proposals.HELD_ACTS and not (out.get('shut') or {}).get('closed') and cardqueue.row_over(store, rv['TaskId']):
            try: general.approved(store, rv['TaskId'], *pressed(store, rv, out), actor, review=rv.get('ReviewId')) or _row_ended(store, rv['TaskId'], actor)
            except Exception as e: logger.warning(f"rv{rv.get('ReviewId')}: the agent was not told it went - {e}")
    # ...AND EVERY ONE THAT RAN AND FAILED (general.failed): an act's error, a send that did not go or may have - never a refusal before it
    # ran (stale, a blank, already answered), and never a held turn's steps, whose card tells its agent once for all (shellgate.approve_steps)
    elif verb_in in ('approve', 'edit', 'merge_anyway', 'close_pr') and rv.get('TaskId') and (out.get('act_failed') or out.get('delivery') in ('failed', 'unknown')):
        from . import demo, general, shellgate
        if not demo.enabled() and shellgate._batch.get() is None:
            try:
                if general.failed(store, rv['TaskId'], rv['ReviewId'], a[2] if len(a) > 2 else kw.get('actor', 'owner')): out['told'] = True
            except Exception as e: logger.warning(f"rv{rv.get('ReviewId')}: the agent was not told it failed - {e}")
    # ...HIS NO NEVER WAKES THE AGENT (the owner, 2026-11-26: a click on a card wakes its agent only where it failed or the agent has something
    # to do next - Dismiss on two posts of three woke it twice, and it wrote under the one still waiting): it is on its card, and its card's
    # event tells the agent whose no it was with its next turn. Only a yes of the same row whose card named a step after it is still owed its
    # one wake, once the no has left nothing waiting (_row_ended) - Close without sending closes the task instead
    elif verb_in in ('reject', 'no_reply', 'close_pr') and out.get('ok') and rv.get('TaskId'):
        from . import demo
        if not demo.enabled():
            try: _row_ended(store, rv['TaskId'], a[2] if len(a) > 2 else kw.get('actor', 'owner'))
            except Exception as e: logger.warning(f"rv{rv.get('ReviewId')}: the row ended, and its agent was not told - {e}")
    return out


def _row_ended(store, tid: int, actor: str) -> str:
    """NOTHING ON THE TASK WAITS FOR HIS PRESS ANY MORE (cardqueue.row_over): a yes of the row whose card names its agent's own step after it
    (card.carries_on), pressed while cards still stood behind it, woke nobody then - it is owed that one wake now. '' while a card still
    waits, and where no such yes went unheard."""
    from . import card, cardqueue, general
    if not cardqueue.row_over(store, tid): return ''
    owed = next((r for r in cardqueue.unheard(store, tid) if card.carries_on(r, store)), None)
    return general.approved(store, tid, '', '', actor, review=owed['ReviewId']) if owed else ''


def _reply_waiting(store, tid):
    "The task's newest reply still waiting for a Send - never an act or one of its emails."
    return store._one("SELECT * FROM review WHERE TaskId=? AND Status='pending' AND Kind NOT IN ('action','slot') ORDER BY ReviewId DESC LIMIT 1", (tid,))


def in_words(got, n: int = 300) -> str:
    """What an act gave back, in words for its agent (the owner, 2026-11-11: the agent was handed the raw JSON, a path under his home in it):
    each plain value by its name, a file by its name alone, anything nested left out."""
    from pathlib import PurePosixPath, PureWindowsPath
    if not isinstance(got, dict): return ' '.join(str(got or '').split())[:n]
    name = lambda v: next((P(v).name for P in (PureWindowsPath, PurePosixPath) if isinstance(v, str) and P(v).is_absolute()), v)
    # ...AND A TOOL'S ROWS AS THE LINKS IN THEM, never the rows (the owner's live post, 2026-11-18): a connector's output came as a JSON string,
    # and the agent was handed its ids and account names whole - a note its provider's safety check then refused, and every turn after it
    def rows(v):
        try: j = json.loads(v) if isinstance(v, str) and v.strip()[:1] in '[{' else None
        except ValueError: j = None
        if j is None: return v
        found = []
        def walk(o):
            if isinstance(o, dict): [walk(x) for x in o.values()]
            elif isinstance(o, list): [walk(x) for x in o]
            elif isinstance(o, str) and o.startswith(('http://', 'https://')) and o not in found: found.append(o)
        walk(j)
        return ' '.join(found)
    return ', '.join(f"{str(k).replace('_', ' ')}: {' '.join(str(name(w)).split())}" for k, v in got.items()
                     if isinstance(v, (str, int, float)) and not isinstance(v, bool) and str(w := rows(v)).strip())[:n]


def _went_to(store, rv: dict, attempted: dict) -> list:
    "Whom a send went to, as its card says it (outbound.review_envelope over the envelope it went out on) - one answer for the card, the line and the agent."
    from .outbound import review_envelope
    try: to = review_envelope(store, {**rv, 'DeliveryEnvelope': json.dumps({'envelope': attempted.get('envelope') or {}})}).get('to') or []
    except Exception: return []
    return [to] if isinstance(to, str) else list(to)


def pressed(store, rv: dict, out: dict) -> tuple:
    "(the press, what it did) of an answered review, in words for its agent."
    if rv.get('Kind') == 'action':
        # ...by the card's own press and name (the owner's live post, 2026-11-18): "pressed Approve ... run tool - headline: 1 row" for what
        # the owner saw as "Post to LinkedIn" on "write linkedin post on LinkedIn"
        from .cardqueue import _p, what
        from .connectorcatalog import action_for
        press = (action_for(_p(rv).get('type')) or {}).get('press') or 'Approve'
        return press, ' - '.join(x for x in (what(store, {'rids': [rv['ReviewId']], 'rows': [rv]}), in_words(out.get('result'))) if x)
    # ...a calendar answer is no reply: "the reply was sent" told the agent of an accepted invite (the stress round, 2026-11-10)
    if (env := _envelope(rv)).get('kind') == 'calendar':
        from .calwrite import head_of
        return 'Send', f'the calendar was told: {head_of(env)}'
    # ...the card by its number and in the owner's words, as a No names it: with two emails out, "the message was sent"
    # left its agent guessing which one went (the stress round, 2026-11-18) - and to whom it went where that is not whom the card named (he
    # readdressed it, or copied someone): "the reply was sent" let its next turn tell him it had answered the person it drafted it for
    from .cardqueue import what
    named, got = what(store, {'rids': [rv['ReviewId']], 'rows': [rv]}), out.get('sent')
    # ...whom it went to is the ONE answer the card reads (outbound.review_envelope: the envelope it went out on), never the send's own guess
    # of it - walk 2, 2026-11-19: the card said "Sent to Erin Blake" and the agent was told it went to Gail
    from .outbound import review_envelope
    went = review_envelope(store, store.get_review(rv['ReviewId']) or rv)
    to, cc = (went.get('to') or [], went.get('cc') or []) if isinstance(went, dict) else ([], [])
    to, cc = [to] if isinstance(to, str) else list(to), [cc] if isinstance(cc, str) else list(cc)
    to = [str(a) for a in to if str(a).lower() not in named.lower()]
    whom = ' - it went' + (f" to {', '.join(to)}" if to else '') + (f", copying {', '.join(map(str, cc))}" if cc else '') if to or cc else ''
    return 'Send', f"rv{rv['ReviewId']} ({named}) was sent{whom}" + (f" ({got})" if isinstance(got, str) else '')


# ONE HOLD, WHOEVER CALLS (design round 2, 2026-11-18): a routine run's agent used the draft tool, "and this run sent it before you could approve
# it" - the hold hung on what the act was called. Every send and act goes through this door, and a yes no person pressed here sends or runs
# nothing - save a routine's email to what the owner saved into the routine: himself, or an address in its own saved words (his Save was that
# press; one its agent or an earlier step chose is not - flow._draft keeps that one for his Send the same way)
UNPRESSED = ('routine', 'workflow', 'agent', 'assistant')
HELD = "it waits for the owner's press - nothing was sent"
ADDRESS = re.compile(r"[\w.+'-]+@[\w-]+(?:\.[\w-]+)+")
def unpressed(actor) -> bool: return str(actor or '').split(':')[0].strip().lower() in UNPRESSED


def saved_for(store, rv: dict) -> bool:
    "May this card go with no press: a routine run's email whose every recipient the owner saved into the routine, or is himself."
    from . import senders, workflows
    env, task = _envelope(rv), store.get_task(rv.get('TaskId')) if rv.get('TaskId') else None
    src = workflows.source_of(store, task) if rv.get('Kind') != 'action' else None
    who = [str(x).strip().lower() for k in ('to', 'cc', 'bcc') for x in (env.get(k) or []) if str(x).strip()]
    if not src or not who: return False
    ok = senders.own_addresses(store) | {a.lower() for a in ADDRESS.findall(json.dumps(workflows.cfg_of(src), ensure_ascii=False))}
    return all(x in ok for x in who)


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
    from . import learning, outbound
    reviewed = rv
    store.recover_review_deliveries(rv['ReviewId'])
    rv = store.get_review(rv['ReviewId']) or rv
    if rv.get('DeliveryClaim'): return _delivery_busy(store, rv['ReviewId'])
    # A CARD THE CONVERSATION MOVED PAST presses nothing, from any page or phone however stale (proposals.move_on, the owner 2026-11-10)
    from . import proposals
    # ...nor one it moved past that no agent has heard yet (written_past): greyed on every surface from the moment the input came
    # ...refused with the one sentence its greyed card reads (passed_why, 2026-11-17), never a fixed "set aside when you moved on"
    if proposals.passed(rv) or rv.get('Status') == 'pending' and rv.get('TaskId') and rv['ReviewId'] in proposals.written_past(store, rv['TaskId']):
        return {'ok': False, 'status': rv['Status'], 'sent': None, 'passed': True, 'send_error': proposals.passed_why(store, rv) or 'Nothing was done - it is over.'}
    if unpressed(actor) and verb_in in ('approve', 'edit', 'merge_anyway', 'close_pr') and not saved_for(store, rv):
        return {'ok': False, 'status': rv.get('Status'), 'sent': None, 'held': True, 'send_error': HELD}
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
        from .card import pending as pending_card
        co = pending_card(store, rv['TaskId'], 'closeout')
        if co: return decide(store, co, 'approve', None, note, actor, learn_async, cc,
                             reply_text=final_text if (final_text or '').strip() else '', blanks_ok=blanks_ok)
    if reply_text is not None and rv.get('Kind') == 'action' and verb_in in ('approve', 'edit', 'close_pr', 'merge_anyway'):
        # ...and a reply still holding a blank stops the press BEFORE the merge: "Done on GitHub, but the reply was not sent" over a
        # [REASON] left in it is half an act the owner never meant (blanks.py, the owner, 2026-10-30)
        if rv.get('TaskId'):
            if waiting := _reply_waiting(store, rv['TaskId']):
                from . import signatures
                typed = signatures.unsigned(reply_text, signatures.for_review(store, waiting)).strip()
                gap = None if blanks_ok else _blanked(reply_text if typed else waiting.get('DraftText'))
                if gap: return gap
        out = decide(store, rv, verb_in, final_text, note, actor, learn_async)
        if not out.get('ok') or not rv.get('TaskId'): return out
        if reply := _reply_waiting(store, rv['TaskId']):
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
                'send_error': f"this one was {already(rv)}"}
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
        # THE SIGNATURE IS NOT ADDED HERE (signatures.py): it went on when the draft was made and the box shows it, so a box holding only
        # the signature is an empty box, the owner's words are compared with the draft above it, and what goes is what the box held -
        # signing again here put the block under his own "Thanks, Alex" (2026-11-17)
        from . import signatures
        sig = signatures.for_review(store, rv)
        if sig and (final_text or '').strip() and not signatures.unsigned(final_text, sig).strip(): final_text = ''
        if sig and not (final_text or '').strip() and not signatures.unsigned(rv.get('DraftText'), sig).strip():
            return {'ok': False, 'status': 'pending', 'sent': None, 'empty': True,
                    'send_error': 'there is only your signature in the box - write the reply (or let the AI draft it) and send that'}
        final = final_text if (final_text or '').strip() or (cal and final_text is not None) else rv.get('DraftText')
        bare = lambda t: signatures.unsigned(t, sig).strip()
        verb = 'edit' if bare(final) != bare(_drafted(rv)) else 'approve'
        if final is not None: final = signatures.as_sent(store, rv, final)     # ...an email as plain text (chatformat.plain_text)
    else:
        final, verb = None, verb_in
    # a PROPOSAL is not a draft reply: approving it RUNS the action the agent asked for
    # (proposals.execute re-validates - the approval never grants the permission), and
    # nothing is ever sent to a sender for it
    if verb in ('close_pr', 'merge_anyway') and rv.get('Kind') != 'action':
        return {'ok': False, 'status': 'pending', 'sent': None, 'send_error': 'only a pull request close-out can be closed or merged that way'}
    if rv.get('Kind') == 'action':
        from . import proposals
        # ...A HELD STEP ITS AGENT IS STILL WORKING BESIDE is not run, and not failed (shellgate.mid_turn): it waits, lit, for the press it asks
        # for - raised inside the act, it was settled as failed under "press it again" and its agent, mid-turn, was woken with "IT FAILED"
        # ...a read let in runs nothing in that folder, so it never waits on the turn (readgate)
        if verb in ('approve', 'edit') and proposals._action(rv) == 'shell_act' and (p_ := json.loads(rv.get('DraftText') or '{}') or {}).get('command'):
            from . import shellgate
            if (busy := shellgate.mid_turn(store, rv['TaskId'], p_.get('sid'))):
                return {'ok': False, 'status': 'pending', 'sent': None, 'busy': busy, 'send_error': busy}
        # ...AN ACT ON A NETWORK NOT CONNECTED runs nothing (the walk, 2026-11-18): Post to LinkedIn on a card never connected went out to LinkedIn
        # and came back in developer words, the card set aside. Refused before it runs, in the card's own Connect words; the card waits with its Connect
        from . import outbound
        if verb in ('approve', 'edit') and (fix := outbound.review_connect(store, rv)):
            return {'ok': False, 'status': 'pending', 'sent': None, 'connect': fix,
                    'send_error': f"{fix['says']} - press {fix['label']} on this card first. Nothing was sent."}
        if not _claim_act(store, rid): return _act_busy(store, rid)   # every verb: a No over a running Yes would mark a merged pull request rejected
        runs = verb in ('approve', 'edit', 'merge_anyway', 'close_pr')
        if runs: store.audit('review', rid, ACT_STARTED, actor)      # ...and written down before it runs, so a restart under it is known (cut_acts)
        try:
            if verb == 'close_pr':
                try: out = proposals.close_pr(store, rv, actor)
                except Exception as e:
                    store.add_comment(rv['TaskId'], 'taskuary', 'agent', f'Closing the pull request did not go: {_said(e)}')   # Taskuary's line, never his
                    store.review_act_failed(rid, str(e), actor)
                    return {'ok': False, 'status': 'pending', 'sent': None, 'send_error': str(e)[:300], 'act_failed': True}
                if not store.decide_review(rid, 'rejected', None, actor, 'closed the pull request without merging'): return _delivery_busy(store, rid)
                proposals.settle(store, rv, 'approve', actor)       # answered, like a merge - the task stays open for Mark done
                return {'ok': True, 'status': 'rejected', 'sent': None, 'send_error': None, 'result': out}
            if verb in ('approve', 'edit', 'merge_anyway'):
                try:
                    out = proposals.execute(store, rv, actor, final, skip_checks=verb == 'merge_anyway', fields=fields)
                except Exception as e:
                    store.add_comment(rv['TaskId'], 'taskuary', 'agent', f'It did not go: {_said(e)}')                # Taskuary's line, never his
                    store.review_act_failed(rid, str(e), actor)     # the card says it after a reload, and its agent hears it (general.failed)
                    # ...AND IS OVER (the owner, 2026-11-16: no Try again): what the agent set up failed and is its again - the card keeps
                    # the error, the agent is woken with it (decide) and sets up what goes next. A close-out is Taskuary's own, and a
                    # refusal before it ran (the owner's own edit, a switch off, ChecksRed) has its own way on: those still wait
                    if getattr(e, 'ran', False) and not isinstance(e, proposals.ChecksRed) and proposals._action(rv) not in proposals.CLOSEOUT:
                        store.decide_review(rid, 'superseded', None, actor, proposals.FAILED_NOTE)
                    return {'ok': False, 'status': (store.get_review(rid) or {}).get('Status') or 'pending', 'sent': None, 'send_error': str(e)[:300], 'act_failed': True,
                            **({'offers': e.offers, 'refused': True} if isinstance(e, proposals.ChecksRed) else {}),
                            # a grant the token lacks (github.Refused.needs): the owner's to add - a retry only repeats it
                            **({'needs': e.needs} if getattr(e, 'needs', '') else {})}
                if not store.decide_review(rid, VERB2STATUS['approve'], proposals.receipt(rv, final, out, fields), actor, note): return _delivery_busy(store, rid)
                from . import ledger
                try: ledger.went(store, rid, out)                       # ...on the record: what went live, and where (ledger.py)
                except Exception as e: logger.warning(f'review {rid}: the act ran, and was not written to the ledger - {e}')
                proposals.settle(store, rv, 'approve' if verb == 'merge_anyway' else verb, actor)   # runs only the act: the task stays open
                return {'ok': True, 'status': 'approved', 'sent': None, 'send_error': None, 'result': out}
            if not store.decide_review(rid, VERB2STATUS[verb], None, actor, note): return _delivery_busy(store, rid)
            store.add_comment(rv['TaskId'], actor, 'human', f'Proposal {VERB2STATUS[verb]} - nothing was done.')
            proposals.settle(store, rv, verb, actor)
            return {'ok': True, 'status': VERB2STATUS[verb], 'sent': None, 'send_error': None}
        finally:
            _RUNNING.discard(rid)
            if runs: store.audit('review', rid, ACT_ENDED, actor)
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
        promotion_ended(store, rv['TaskId'], note or 'he said no reply is needed')
    # a clarification stops the blocked terminal and leaves the task waiting; any other answer leaves it open for Mark done
    if result is None and verb in ('approve', 'edit') and rv.get('TaskId') and not send_err:
        _settle_task_after_sent_reply(store, rv, actor, False)
    store.audit('review', rid, verb, actor, detail={'kind': rv.get('Kind'), 'sent': bool(sent)})
    from .episodes import personal as _personal
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
        if verb == 'edit': ev += f"\nDRAFT:\n{(_drafted(rv) or '')[:700]}\nSENT INSTEAD:\n{(final or '')[:700]}"
        if learn_async: learn_async(learning.learn_from, store, ev, f'rv{rid}')
        else: learning.learn_from(store, ev, f'rv{rid}')
    return result or {'ok': True, 'status': VERB2STATUS[verb], 'sent': sent, 'send_error': None}
