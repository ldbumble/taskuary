"""What closes a task: output slots on its checklist (docs/superpowers/specs/2026-10-05-task-close-slots-design.md).

A task's ending used to be implied by where it came from - one reply to its sender. An ask whose result is several
messages to several people had nowhere to live, and the first send closed the task and superseded the rest. A slot is
a checklist item that names one output; the task stays open until every slot is sent or dropped (proposals.closed_out).

Its draft is a review of kind `slot`, never `draft_reply`: every "the task's reply" lookup (pending_review, hold_reviews,
agent_reply, the close-out redirect) reads draft kinds, so a slot can never be mistaken for the reply or overwritten by it.
"""
import json

KINDS = ('email',)            # what a slot can be - a new kind is a new entry here, never a branch elsewhere
KIND = 'slot'                 # the review kind of a slot's draft


def clean(outputs) -> list:
    """Model or caller outputs -> checklist items. Unknown kinds and slots with nobody to send to are dropped."""
    out = []
    for o in outputs if isinstance(outputs, (list, tuple)) else []:
        if not isinstance(o, dict): continue
        to, about, kind = ' '.join(str(o.get('to') or '').split())[:200], ' '.join(str(o.get('about') or '').split())[:200], o.get('kind') or 'email'
        if not to or kind not in KINDS: continue
        # `by: agent` - an address the agent added on its own: never swept up by Approve all (a prompt-injected agent
        # must not get an email out under one bulk press)
        out.append({'text': f'Email {to}' + (f' - {about}' if about else ''),
                    'out': {'kind': kind, 'to': to, 'subject': str(o.get('subject') or '')[:200], **({'by': 'agent'} if o.get('by') == 'agent' else {})}})
    return out


def add(store, tid: int, outputs, actor: str) -> list:
    """Append these outputs as slots; one already open to the same person is not added twice. A person named, not
    addressed, takes their address when exactly one person in the owner's own mail matches (people.resolve); several
    are kept on the slot to pick from; none leaves the name and its '?'."""
    from . import people
    have = {str(i['out'].get('to')).casefold() for i in open_(store, tid)}
    new = []
    for i in clean(outputs):
        if '@' not in i['out']['to']:
            found = people.resolve(store, i['out']['to'])
            if found.get('address'): i['out']['to'] = found['address']
            elif found.get('candidates'): i['out']['candidates'] = found['candidates']
        if i['out']['to'].casefold() not in have: new.append(i)
    return store.add_checklist_items(tid, new, actor) if new else []


def all_(store, tid: int) -> list: return [i for i in store.task_checklist(tid) if isinstance(i.get('out'), dict)]
def open_(store, tid: int) -> list: return [i for i in all_(store, tid) if not i.get('done')]


def of_review(rv) -> str | None:
    """The slot a review fills, or None for every other review."""
    if not rv or rv.get('Kind') != KIND: return None
    try: return (json.loads(rv.get('Deliver') or '{}') or {}).get('slot')
    except (TypeError, ValueError): return None


def settled(store, rv: dict, sent: bool, actor: str) -> bool:
    """A slot's draft was sent (or dropped): tick the slot, then close the task if nothing else of it waits.
    The same gate the reply goes through (proposals.closed_out) - whichever lands last closes it."""
    sid, tid = of_review(rv), rv.get('TaskId')
    if not (sid and tid): return False
    mark(store, tid, sid, done=True, actor=actor)
    return _close_if_settled(store, tid, f"{'Sent' if sent else 'Dropped'}: {rv.get('Reason') or 'one of its emails'}.", actor)


def _close_if_settled(store, tid: int, said: str, actor: str) -> bool:
    """Close only past every guard the reply's own send keeps (verdicts._settle_task_after_sent_reply): an email left,
    the reply (pending or held while an agent works), an agent still on it, a close-out the owner has not answered."""
    if (store.get_task(tid) or {}).get('Status') in ('done', 'dropped'): return False
    from . import funnel, proposals
    left = len(open_(store, tid))
    reply = store._one("SELECT 1 x FROM review WHERE TaskId=? AND Status IN ('pending','held') AND Kind NOT IN ('action', ?) LIMIT 1", (tid, KIND))
    why = (f"{left} email{'s' if left != 1 else ''} still to go" + (' and the reply' if reply else '') if left or reply
           else 'the agent is still working on it' if tid in funnel.working_tids(store)
           else 'its close-out still waits on you' if proposals.closeout_pending(store, tid) else '')
    if why:
        store.add_comment(tid, actor, 'human', f'{said} The task stays open - {why}.')
        return False
    return proposals.closed_out(store, tid, actor, said)


def drop(store, tid: int, slot_id: str, actor: str) -> bool:
    """The owner lets one email go: its waiting draft is rejected (never sent), the slot ticked, the task closed if that
    was the last thing it owed. Not taught as a rejected reply - nothing about the sender's mail was judged."""
    hit = next((i for i in all_(store, tid) if i['id'] == slot_id), None)
    if not hit: return False
    rv = store.get_review(hit['rid']) if hit.get('rid') else None
    if rv and rv.get('Status') == 'pending': store.decide_review(rv['ReviewId'], 'rejected', None, actor, 'dropped - this email is not owed')
    mark(store, tid, slot_id, done=True, actor=actor)
    return _close_if_settled(store, tid, f"Dropped: {hit['text']}.", actor)


def seen(store, tid: int):
    """The newest inbound message a slot draft was written against - a newer one makes it stale (verdicts.context_moved)."""
    return (store.last_material_inbound_on_task(tid) or {}).get('MessageId')


def draft(store, tid: int, text: str, to: str = '', subject: str = '', slot: str = '', agent: str = 'agent') -> dict:
    """The agent that did the work writes one output itself - the slot named by id, else the open one to the same person,
    else a slot it adds (said on the task: the owner sees the list grow). Nothing is sent: the owner approves it."""
    text = str(text or '').strip()
    if not text: return {'ok': False, 'why': 'no email text'}
    want = ' '.join(str(to or '').split()).casefold()
    hit = next((i for i in all_(store, tid) if slot and i['id'] == slot), None) or \
          next((i for i in open_(store, tid) if want and str(i['out'].get('to')).casefold() == want), None)
    added = False
    if hit and want and '@' in want and str(hit['out'].get('to')).casefold() != want:
        # a slot that named a person: the address the agent found is where this one goes (never guessed by us)
        items = store.task_checklist(tid)
        for i in items:
            if i.get('id') == hit['id']: i['out'] = {**i['out'], 'to': ' '.join(str(to).split())}; hit = i
        store._write_checklist(tid, items, f'agent:{agent}')
    if not hit:
        if not want: return {'ok': False, 'why': 'name the slot (--slot) or who it goes to (--to)'}
        made = add(store, tid, [{'to': to, 'about': subject, 'by': 'agent'}], f'agent:{agent}')
        if not made: return {'ok': False, 'why': f'could not add an email to {to}'}
        hit, added = made[0], True
        store.add_comment(tid, agent, 'agent', f'{agent} added an email to {to} to what closes this task.')
    o = hit['out']; subj = str(subject or o.get('subject') or (store.get_task(tid) or {}).get('Title') or '')[:200]
    deliver = json.dumps({'channel': 'email', 'to': [o['to']], 'cc': [], 'subject': subj, 'slot': hit['id'], 'seen': seen(store, tid)})
    rv = store.get_review(hit['rid']) if hit.get('rid') else None
    if rv and rv.get('Status') == 'pending':
        rid = rv['ReviewId']
        if not store.set_review_deliver(rid, deliver): return {'ok': False, 'why': 'that email is already being sent'}
    else:
        rid = store.add_review({'TaskId': tid, 'Kind': KIND, 'Status': 'pending', 'Deliver': deliver,
                                'Reason': f"{agent}'s email to {o['to']} - approve to send"})
        mark(store, tid, hit['id'], rid=rid, actor=f'agent:{agent}')
    store.update_review_draft(rid, text, None, by=f'agent:{agent}')
    return {'ok': True, 'review_id': rid, 'slot': hit['id'], 'added': added}


def mark(store, tid: int, slot_id: str, rid: int = None, done: bool = None, actor: str = 'owner') -> bool:
    items = store.task_checklist(tid)
    hit = next((i for i in items if i.get('id') == slot_id and isinstance(i.get('out'), dict)), None)
    if not hit: return False
    if rid is not None: hit['rid'] = int(rid)
    if done is not None: hit['done'] = bool(done)
    store._write_checklist(tid, items, actor)
    return True
