"""What closes a task: output slots on its checklist (docs/superpowers/specs/2026-10-05-task-close-slots-design.md).

A task's ending used to be implied by where it came from - one reply to its sender. An ask whose result is several
messages to several people had nowhere to live, and the first send closed the task and superseded the rest. A slot is
a checklist item that names one output; the task stays open until every slot is sent or dropped (proposals.closed_out).

Its draft is a review of kind `slot`, never `draft_reply`: every "the task's reply" lookup (pending_review, hold_reviews,
agent_reply, the close-out redirect) reads draft kinds, so a slot can never be mistaken for the reply or overwritten by it.
"""
import json
import re
from email.utils import parseaddr

KINDS = ('email',)            # what a slot can be - a new kind is a new entry here, never a branch elsewhere
KIND = 'slot'                 # the review kind of a slot's draft


def clean(outputs) -> list:
    """Model or caller outputs -> checklist items. Unknown kinds and slots with nobody to send to are dropped."""
    out = []
    for o in outputs if isinstance(outputs, (list, tuple)) else []:
        if not isinstance(o, dict): continue
        to, about, kind = ' '.join(str(o.get('to') or '').split())[:200], ' '.join(str(o.get('about') or '').split())[:200], o.get('kind') or 'email'
        if not to or kind not in KINDS: continue
        name, to = split(to)
        # `by: agent` - an address the agent added on its own: never swept up by Approve all (a prompt-injected agent
        # must not get an email out under one bulk press)
        out.append({'text': f'Email {name or to}' + (f' - {about}' if about else ''),
                    'out': {'kind': kind, 'to': to, 'subject': str(o.get('subject') or '')[:200], **({'name': name} if name else {}),
                            **({'by': 'agent'} if o.get('by') == 'agent' else {})}})
    return out


def split(to: str) -> tuple:
    """('JD Hancock', 'jd@x.example') out of 'JD Hancock <jd@x.example>' - the recipient is the ADDRESS: the provider was
    handed the whole string as one and an agent writes them that way (TQ-0957). A bare name or address: ('', it)."""
    name, addr = parseaddr(str(to or ''))
    return (name.strip(), addr.strip()) if '@' in addr and '<' in str(to) else ('', ' '.join(str(to or '').split()))


def is_sender(sender, to: str, name: str = '') -> bool:
    """An output to the person who wrote IS the task's reply, never an email of its own. The triage prompt says so and a
    model wrote one anyway - on a chat message, so the close-out held the reply twice, the second as an email opening
    "Hi ..," (2026-10-06; both triage slots ever made were this). Matched as a person: the same address, or every word of
    the name inside the sender's ("Last, First at Company" is the same person as "First Last")."""
    if not sender: return False
    addr, who = str(sender.get('address') or '').casefold(), str(sender.get('name') or '')
    if addr and str(to).casefold() == addr: return True
    words = lambda x: set(re.findall(r'[a-z]{2,}', str(x).casefold()))
    want = words(name or ('' if '@' in str(to) else to))
    return bool(want) and want <= words(who)


def add(store, tid: int, outputs, actor: str, sender: dict = None) -> list:
    """Append these outputs as slots; one already open to the same person is not added twice, and one to `sender` (the
    message's own {name, address}) is never added - that is the reply (is_sender). A person named, not addressed, takes
    their address when exactly one person in the owner's own mail matches (people.resolve); several are kept on the slot
    to pick from; none leaves the name and its '?'."""
    from . import people
    # every email the task has owed - sent and dropped ones too: an email already sent is not owed again because a later
    # message words it differently
    have = {str(i['out'].get('to')).casefold() for i in all_(store, tid)}
    new = []
    for i in clean(outputs):
        if is_sender(sender, i['out']['to'], i['out'].get('name', '')): continue
        if '@' not in i['out']['to']:
            found = people.resolve(store, i['out']['to'])
            if found.get('address'): i['out']['to'] = found['address']
            elif found.get('candidates'): i['out']['candidates'] = found['candidates']
            if is_sender(sender, i['out']['to']): continue        # the name resolved to the sender's own address
        if i['out']['to'].casefold() not in have: new.append(i)
    return store.add_checklist_items(tid, new, actor) if new else []


def all_(store, tid: int) -> list: return [i for i in store.task_checklist(tid) if isinstance(i.get('out'), dict)]
def open_(store, tid: int) -> list: return [i for i in all_(store, tid) if not i.get('done')]
def written(store, tid: int) -> list:
    """The open slots the agent already wrote, each waiting on the owner's yes."""
    rvs = (store.get_review(i['rid']) for i in open_(store, tid) if i.get('rid'))
    return [r for r in rvs if r and r.get('Status') == 'pending' and str(r.get('DraftBy') or '').startswith('agent:')]


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
    if (store.get_task(tid) or {}).get('Status') in ('done', 'dropped'): return {'ok': False, 'why': 'that task is closed'}
    to = split(to)[1]
    want = ' '.join(str(to or '').split()).casefold()
    hit = next((i for i in all_(store, tid) if slot and i['id'] == slot), None) or \
          next((i for i in open_(store, tid) if want and str(i['out'].get('to')).casefold() == want), None)
    added = False
    if hit and hit.get('done'): return {'ok': False, 'why': f"the email to {hit['out'].get('to')} was already sent or dropped"}
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
                                'Reason': f"{agent} wrote this email - approve to send"})       # who it goes to is on the card once
        mark(store, tid, hit['id'], rid=rid, actor=f'agent:{agent}')
    store.update_review_draft(rid, text, None, by=f'agent:{agent}')
    return {'ok': True, 'review_id': rid, 'slot': hit['id'], 'added': added}


def readdress(store, rv: dict, to: list, actor: str = 'owner') -> dict:
    """The owner corrects who one of the task's emails goes to: the slot's `to` and its draft's Deliver, both - the card
    said "Devorah Cohn ?" with no way to give the address the agent never found (2026-10-06)."""
    to = [a for a in (' '.join(str(x or '').split()).lower() for x in to or []) if '@' in a]
    if not to: raise ValueError('give at least one email address')
    try: d = json.loads(rv.get('Deliver') or '{}') or {}
    except ValueError: d = {}
    d['to'] = to
    if not store.set_review_deliver(rv['ReviewId'], json.dumps(d)): raise ValueError('that email is already being sent')
    tid, sid = rv.get('TaskId'), d.get('slot') or of_review(rv)
    if tid and sid:
        items = store.task_checklist(tid)
        for i in items:
            if i.get('id') == sid and isinstance(i.get('out'), dict): i['out'] = {**i['out'], 'to': ', '.join(to)}
        store._write_checklist(tid, items, actor)
    return {'kind': 'slot', 'to': to, 'cc': d.get('cc') or []}


def mark(store, tid: int, slot_id: str, rid: int = None, done: bool = None, actor: str = 'owner') -> bool:
    items = store.task_checklist(tid)
    hit = next((i for i in items if i.get('id') == slot_id and isinstance(i.get('out'), dict)), None)
    if not hit: return False
    if rid is not None: hit['rid'] = int(rid)
    if done is not None: hit['done'] = bool(done)
    store._write_checklist(tid, items, actor)
    return True
