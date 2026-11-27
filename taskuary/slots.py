"""What a task owes: output slots on its checklist (docs/superpowers/specs/2026-10-05-task-close-slots-design.md).

A task's ending used to be implied by where it came from - one reply to its sender. An ask whose result is several
messages to several people had nowhere to live, and the first send closed the task and superseded the rest. A slot is
a checklist item that names one output. Sending or dropping one ticks it and closes nothing: only the owner's Mark done
closes the task (the owner, 2026-10-18: "sending and closing are two steps, never automatic").

Its draft is a review of kind `slot`, never `draft_reply`: every "the task's reply" lookup (pending_review, hold_reviews,
agent_reply, the close-out redirect) reads draft kinds, so a slot can never be mistaken for the reply or overwritten by it.
"""
import json
import re
from email.utils import parseaddr
from .timewords import plural
from loguru import logger

# what a slot can be - a new kind is a new entry here, never a branch elsewhere. A chat (the owner, 2026-10-09: "teams/chat
# too") is one message into one chat id, sent by outbound.send_out like any of these: no CC, no files, no subject.
KINDS = ('email', 'teams', 'whatsapp', 'telegram', 'imessage', 'discord')
CHAT_NAMES = {'teams': 'Teams', 'whatsapp': 'WhatsApp', 'telegram': 'Telegram', 'imessage': 'Messages', 'discord': 'Discord'}
KIND = 'slot'                 # the review kind of a slot's draft


def clean(outputs) -> list:
    """Model or caller outputs -> checklist items. Unknown kinds and slots with nobody to send to are dropped."""
    out = []
    for o in outputs if isinstance(outputs, (list, tuple)) else []:
        if not isinstance(o, dict): continue
        to, about, kind = ' '.join(str(o.get('to') or '').split())[:200], ' '.join(str(o.get('about') or '').split())[:200], o.get('kind') or 'email'
        if not to or kind not in KINDS: continue
        name, to = split(to) if kind == 'email' else (' '.join(str(o.get('name') or '').split())[:120], to)
        # `by: agent` - an address the agent added on its own: never swept up by Approve all (a prompt-injected agent
        # must not get an email out under one bulk press)
        verb = 'Email' if kind == 'email' else f'Message on {CHAT_NAMES[kind]}'
        out.append({'text': f'{verb} {name or to}' + (f' - {about}' if about else ''),
                    'out': {'kind': kind, 'to': to, 'subject': str(o.get('subject') or '')[:200], **({'name': name} if name else {}),
                            **({'by': 'agent'} if o.get('by') == 'agent' else {})}})
    return out


# ONE ADDRESS, by its shape (a regex may parse structure): "a@x.example, b@y.example" stood as one recipient the provider refused at Send
ADDRESS = re.compile(r'[^@\s,;<>]+@[^@\s,;<>]+\.[^@\s,;<>]+')
def is_address(a) -> bool: return bool(ADDRESS.fullmatch(str(a or '').strip()))


def split(to: str) -> tuple:
    """('Ray Colton', 'ray@x.example') out of 'Ray Colton <ray@x.example>' - the recipient is the ADDRESS: the provider was
    handed the whole string as one and an agent writes them that way (TQ-0957). A bare name or address: ('', it)."""
    to = re.sub(r'^\s*mailto:', '', str(to or ''), flags=re.I)          # ...a mailto: link copied as the address is the address
    name, addr = parseaddr(to)
    return (name.strip(), addr.strip()) if '@' in addr and '<' in to else ('', ' '.join(to.split()))


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


def add(store, tid: int, outputs, actor: str, sender: dict = None, again: bool = False, twice: bool = False) -> list:
    """Append these outputs as slots; one already open to the same person is not added twice, and one to `sender` (the
    message's own {name, address}) is never added - that is the reply (is_sender). A person named, not addressed, takes
    their address when exactly one person in the owner's own mail matches (people.resolve); several are kept on the slot
    to pick from; none leaves the name and its '?'."""
    from . import people
    # every email the task has owed - sent and dropped ones too: an email already sent is not owed again because a later
    # message words it differently (one taken back unsent is owed again: draft reopens it, _reopen)
    # ...`again`: the email its agent or the owner writes NOW (draft) - to someone whose earlier email on this task went is a new letter,
    # never "could not add an email" (recorded on the real CLI, 2026-11-13: a second ask joined the task, and the agent told the owner
    # the email "would not save, though I tried four ways"); what triage lists (not `again`) is never owed twice
    have = {str(i['out'].get('to')).casefold() for i in (open_ if again else all_)(store, tid)}
    new = []
    for i in clean(outputs):
        if is_sender(sender, i['out']['to'], i['out'].get('name', '')): continue
        if i['out']['kind'] == 'email' and '@' not in i['out']['to']:      # a chat id is never a person's name to look up
            found = people.resolve(store, i['out']['to'])
            if found.get('address'): i['out']['to'] = found['address']
            elif found.get('candidates'): i['out']['candidates'] = found['candidates']
            if is_sender(sender, i['out']['to']): continue        # the name resolved to the sender's own address
        if twice or i['out']['to'].casefold() not in have: new.append(i)      # ...`twice`: a second letter to them, asked for (draft)
    # ...and a second letter about the same thing is still a second line of the list: the list keeps one line per text, so it was dropped
    # unsaid and its agent told "`to` must be one address" (walk 22, 2026-11-25) - numbered, as the second it is
    said = {i['text'] for i in store.task_checklist(tid)} if twice else set()
    for i in new:
        base, n = i['text'], 2
        while i['text'] in said: i['text'], n = f'{base} ({n})', n + 1
        said.add(i['text'])
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
    """A slot's draft was sent (or dropped): tick the slot and say what is left. The last one closes nothing (2026-10-18)."""
    sid, tid = of_review(rv), rv.get('TaskId')
    if not (sid and tid): return False
    mark(store, tid, sid, done=True, actor=actor)
    # ...said by whom it was to, never by the card's Reason: that is the card's prompt ("approve to send"), and after a failed press the
    # failure itself - a second press that went read "Sent: Not sent: 550 ..." (the stress round, 2026-11-18)
    from .cardqueue import what
    return _left(store, tid, f"{'Sent' if sent else 'Dropped'}: {what(store, {'rids': [rv['ReviewId']], 'rows': [rv]})}.", actor)


def _left(store, tid: int, said: str, actor: str) -> bool:
    """Say on the task what one email's send or drop leaves. False always: the task stays open - it used to close on the
    last one, past the reply's own guards; now only the owner's Mark done closes it."""
    if (store.get_task(tid) or {}).get('Status') in ('done', 'dropped'): return False
    from . import buttons, workflows
    n = len(open_(store, tid))
    # ...a routine's steps still walking close their own task when nothing waits (flow._walk): "Mark done when the task is finished" was
    # said over a run that closed itself the moment after
    if not n and workflows.at_work(tid): store.add_comment(tid, actor, 'human', said); return False
    store.add_comment(tid, actor, 'human', f"{said} " + (f"{plural(n, 'email')} still to go." if n
                                                       else f"Every email is sent or dropped - {buttons.label('close')} when the task is finished."))
    return False


DROPPED = 'dropped - this email is not owed'
def drop(store, tid: int, slot_id: str, actor: str) -> bool:
    """The owner lets one email go: its waiting draft is rejected (never sent) and the slot ticked - the task stays open.
    Not taught as a rejected reply - nothing about the sender's mail was judged. A press of theirs like any other: a line in the
    chat, heard by the task's agent with their next one (general.PRESSES) - drafted or not, by who it was to."""
    hit = next((i for i in all_(store, tid) if i['id'] == slot_id), None)
    if not hit: return False
    rv = store.get_review(hit['rid']) if hit.get('rid') else None
    if rv and rv.get('Status') == 'pending': store.decide_review(rv['ReviewId'], 'rejected', None, actor, DROPPED)
    mark(store, tid, slot_id, done=True, actor=actor)
    store.audit('task', tid, 'slot_dropped', actor, detail={'to': hit['out'].get('name') or hit['out'].get('to'), 'kind': hit['out'].get('kind') or 'email'})
    return _left(store, tid, f"Dropped: {hit['text']}.", actor)


def seen(store, tid: int):
    """The newest inbound message a slot draft was written against - a newer one makes it stale (verdicts.context_moved)."""
    return (store.last_material_inbound_on_task(tid) or {}).get('MessageId')


# A CHAT ID IS NO MAILBOX, whoever named it - the agent or triage's slot (the night run, 2026-11-09: "emails" went to whatsapp:1555...)
_NO_MAILBOX = "{to} is a chat, not a mailbox - answer them in that chat (propose kind reply, `answers` their line) or give their email address as `to`"
NO_WORDS = "the email has no words, so nothing was filed - write the email in `text`, or ask the owner what it should say"
def _chat_id(to) -> bool:
    from .ingest import CHAT_CHANNELS
    return str(to or '').split(':')[0].strip().lower() in CHAT_CHANNELS

def draft(store, tid: int, text: str, to: str = '', subject: str = '', slot: str = '', agent: str = 'agent',
          channel: str = 'email', name: str = '', cc=(), mailbox: str = '', guessed=(), sends: bool = True) -> dict:
    """The agent that did the work writes one output itself - the slot named by id, else the open one to the same person,
    else a slot it adds (said on the task: the owner sees the list grow). Nothing is sent: the owner approves it. `cc`: who
    else is copied - kept on the envelope, so the card shows what the agent said it did (it said "Gail on cc" and dropped her).
    `mailbox`: the connected mailbox it leaves FROM - a + New task has no mail in to answer from, so "send it from my JOIN
    Gmail" fell to the first Outlook card, and the agent, with no way to say it, tried the Gmail card as a tool (TQ-1354).
    `guessed`: the addresses on it the agent guessed (no address on record) - the card says so, and the owner's Send is the check.
    `sends`: False keeps a routine's email for his Send (flow._draft: an address a step read, not one fixed at setup)."""
    text = str(text or '').strip()
    # ...a recipient with no words is no email (the owner, 2026-11-10: "it created reply with nothing in it ... if you have nothing to reply just
    # ask what should i reply?"): nothing is filed, and the agent is told its two ways on
    if not text: return {'ok': False, 'why': NO_WORDS}
    from .wrapup import blank_why
    if agent != 'owner' and (why := blank_why(text, store)): return {'ok': False, 'why': why}       # a blank left to fill is no letter (wrapup.blanks)
    mailbox = str(mailbox or '').strip()
    if mailbox:
        from . import outbound
        if channel != 'email': return {'ok': False, 'why': f'{channel} has no From - only an email leaves from a mailbox'}
        box = outbound._box(store, mailbox)
        if not box:
            have = ', '.join(m['address'] for m in outbound.mailboxes(store)) or 'none is connected'
            return {'ok': False, 'why': f'{mailbox} is not a connected mailbox - send from one of: {have}'}
        if agent != 'owner':                # ...and one of another profile is the card that moves the task there (workstreams.may_use)
            from . import workstreams
            if (mv := workstreams.move_card(store, tid, box['address'], f"email {to} from {box['address']}"[:200])): return {'ok': False, 'why': mv['says']}
        mailbox = box['address']
    cc = [a for a in (split(x)[1] for x in ([cc] if isinstance(cc, str) else cc or [])) if a]
    if cc and channel != 'email': return {'ok': False, 'why': f'{channel} has no cc - only an email can copy somebody in'}
    if bad := [a for a in cc if not is_address(a)]: return {'ok': False, 'why': f"cc is a list of email addresses, one to an entry - {', '.join(bad)} is not one"}
    cc = [a.lower() for a in cc]
    if (store.get_task(tid) or {}).get('Status') in ('done', 'dropped'): return {'ok': False, 'why': 'that task is closed'}
    # ...more than one address in To is refused as written, before it is parsed: "Name <a@x>, b@x" parsed as the first alone, the second dropped
    if channel == 'email' and str(to or '').count('@') > 1:
        return {'ok': False, 'why': f"{' '.join(str(to).split())} is not one email address - `to` takes one; copy the others with `cc`, or give each its own email. Nothing was drafted."}
    to = split(to)[1] if channel == 'email' else ' '.join(str(to or '').split())
    if channel == 'email' and _chat_id(to): return {'ok': False, 'why': _NO_MAILBOX.format(to=to)}
    if channel == 'email' and '@' in to and not is_address(to):
        return {'ok': False, 'why': f"{to} is not one email address - `to` takes one; copy the others with `cc`, or give each its own email. Nothing was drafted."}
    want = ' '.join(str(to or '').split()).casefold()
    # A GUESS WHERE HIS MAIL KNOWS THE COMPANY IS NOT MADE (the owner, 2026-11-17: an email to a made-up address at a bank bounced while the
    # bank's contact had written three months before - "give it tool to search emails"): refused before anything stands, with the people at
    # that company his mail knows, so the agent drafts to one of them or asks him. A company his mail never saw still takes a marked guess
    # ...and one his mail knows is no guess, whatever the agent called it: it was refused for the others at its company, itself unlisted
    # ...AND NEVER A GO-BETWEEN (a walk, 2026-11-18): refused a guessed accounts-payable mailbox, told "draft to the one this is for", the
    # agent sent the payment note to the colleague who had shared a vendor sheet, "as the route to AP". Who it is for, or the one question
    guessed = [a.lower() for a in (split(x)[1] for x in ([guessed] if isinstance(guessed, str) else guessed or [])) if a]
    if channel == 'email' and agent != 'owner':
        from .people import at_domain, said_by_owner
        his = said_by_owner(store, tid)
        # ...EVERY ADDRESS ON IT, called a guess or not (walk 5, 2026-11-22: the agent wrote "I guessed her address" in its answer and passed none as
        # guessed - gail.moreno@ stood on a Send card 20 seconds after Gail wrote from gail@): one his mail never saw, at a company it knows
        # - is refused where that PERSON writes from another address: their name is the address's own words (structure, never meaning)
        for g in [a for a in dict.fromkeys([str(to or '').lower(), *cc]) if '@' in a and a not in guessed and a not in his]:
            known = at_domain(store, g.rpartition('@')[2])
            if g in {a.lower() for a, _ in known}: continue
            local = set(re.findall(r'[a-z]+', g.partition('@')[0]))
            same = next(((a, n) for a, n in known if n and (ws := set(re.findall(r'[a-z]+', n.lower()))) and len(ws) > 1 and ws <= local), None)
            if same: return {'ok': False, 'why': f"{g} is in none of the owner's mail, and {same[1]} writes from {same[0]} - draft to that address, "
                                                  'or ask the owner in one question if this is someone else. Nothing was drafted.'}
        for g in [a for a in dict.fromkeys(guessed) if '@' in a]:
            if g in his: guessed = [a for a in guessed if a != g]; continue        # ...an address he gave is no guess (people.owner_lines)
            known = at_domain(store, g.rpartition('@')[2])
            if g in {a.lower() for a, _ in known}: guessed = [a for a in guessed if a != g]; continue
            if known: return {'ok': False, 'why': f"{g} is your guess, and the owner's mail knows {g.rpartition('@')[2]}: "
                                                    + ', '.join(f'{a} ({n})' if n else a for a, n in known[:5])
                                                    + ' - draft to one of them only where their mail shows this is theirs (search_messages and '
                                                      'person tell you who each is), never one as a go-between; else ask the owner in one '
                                                      f'question with {g} as the answer you recommend. Nothing was drafted.'}
    # ...A SECOND LETTER TO ONE PERSON IS ITS OWN EMAIL WHEN ASKED FOR (the owner, 2026-11-13: two different letters to one person are legit, a
    # duplicate copy is not): saved again to them in its turn, a letter is rewritten in place - and the agent is told so, with the way to a second
    # one (`slot: "new"`). Told nothing, it said two were ready over the one card that stood (the card audit, 2026-11-22)
    second = str(slot or '').strip().lower() == NEW_SLOT
    hit = None if second else next((i for i in all_(store, tid) if slot and i['id'] == slot), None) or \
          next((i for i in open_(store, tid) if want and str(i['out'].get('to')).casefold() == want), None) or \
          (want and _reopen(store, tid, want, agent))
    r0 = store.get_review(hit['rid']) if hit and hit.get('rid') and not slot else None
    rewrote = r0['ReviewId'] if agent != 'owner' and r0 and r0.get('Status') == 'pending' and str(r0.get('DraftBy') or '').startswith('agent:') \
              and not _written_before(store, tid, r0) else None
    added = False
    if hit and hit.get('done'): return {'ok': False, 'why': f"the email to {hit['out'].get('to')} was already sent or dropped - for another letter "
                                                                "to them, call it again with `slot: \"new\"`"}
    if hit and want and '@' in want and str(hit['out'].get('to')).casefold() != want:
        # a slot that named a person: the address the agent found is where this one goes (never guessed by us)
        hit = _point(store, tid, hit, ' '.join(str(to).split()), agent)
    if not hit:
        if not want: return {'ok': False, 'why': 'name the slot (--slot) or who it goes to (--to)'}
        made = add(store, tid, [{'to': to, 'about': subject, 'kind': channel, **({} if agent == 'owner' else {'by': 'agent'}), **({'name': name} if name else {})}], f'agent:{agent}', again=True,
                   twice=second)
        # ...NEVER A BARE NO (walk 6, CLI F9: "could not add an email to paula@..." and no next step): what stands in its way, and the way on
        if not made:
            same = [i for i in open_(store, tid) if str(i['out'].get('to')).casefold() == want]
            return {'ok': False, 'why': f"no email to {to} was added - " + (
                f"one to them is already this task's (slot {same[0]['id']}): rewrite it with `slot` set to that id, or `slot: \"new\"` for a second letter"
                if same else "`to` must be one address or one person's name; to answer someone who wrote on this task, propose kind reply with `to`")}
        hit, added = made[0], True
        store.add_comment(tid, agent, 'agent', f'{agent} added an email to {to} to what this task owes.')
    o = hit['out']; kind = o.get('kind') or 'email'
    if kind == 'email' and _chat_id(o.get('to')): return {'ok': False, 'why': _NO_MAILBOX.format(to=o.get('to'))}
    missing, found = '', False
    if kind == 'email' and '@' not in str(o.get('to') or ''):
        who = ' '.join(str(o.get('to') or '').split())
        addr, found = address_for(store, tid, who)
        if addr: hit = _point(store, tid, hit, addr, agent, name=o.get('name') or who); o = hit['out']
        else: missing = who or 'them'
    subj = subject_of(store, tid, hit, subject) if kind == 'email' else ''
    rv = store.get_review(hit['rid']) if hit.get('rid') else None
    # a rewrite that names no From keeps the one already picked - the owner's, or the agent's first draft's
    try: was = (json.loads(rv.get('Deliver') or '{}') or {}).get('mailbox') if rv and rv.get('Status') == 'pending' else None
    except (TypeError, ValueError): was = None
    box = (mailbox or was) if kind == 'email' else None
    if found and o['to'].lower() not in guessed: guessed.append(o['to'].lower())
    # ...an email's To holds addresses only: none found is an EMPTY To the card asks the owner to fill, never the name
    deliver = json.dumps({'channel': kind, 'to': [] if missing else [o['to']], 'cc': cc, 'subject': subj, 'slot': hit['id'], 'seen': seen(store, tid),
                          **({'mailbox': box} if box else {}), **({'guessed': guessed} if guessed else {}), **({'needs': missing} if missing else {})})
    # ...and one the owner has prompted past is old news (the owner, 2026-11-10: "The second you write ptompt on email action it should go gray and
    # then it should generate new email action box under it with new email.."): the agent's letter is a new card in its turn, the old one its
    # record, as a reply's is (wrapup.agent_reply); saved twice in its own turn it is rewritten in place
    # ...AND ONE HE HAS TYPED HIS OWN WORDS INTO IS HIS (store.hold_review_edit; wrapup.agent_reply's rule for a reply): never rewritten under
    # him - his version is closed as replaced with his words on it, the agent's letter is a new card, and the agent is told what he had left
    his = ''
    if rv and rv.get('Status') == 'pending' and agent != 'owner':
        from . import wrapup
        from .store import his_words
        # ...only where the agent wrote OTHER words (the owner, 2026-11-26): the same letter saved again is no rewrite - his version stands
        from .signatures import agent_signed
        same = wrapup._words(rv.get('DraftText')) == wrapup._words(agent_signed(store, rv, text) or text)
        his = '' if same else his_words(rv)
        if his or wrapup._turn_after(store, tid, rv): store.decide_review(rv['ReviewId'], 'closed_unsent', his or None, agent, note=wrapup.REPLACED); rv = None
    if rv and rv.get('Status') == 'pending':
        rid = rv['ReviewId']
        if not store.set_review_deliver(rid, deliver): return {'ok': False, 'why': 'that email is already being sent'}
    else:
        rid = store.add_review({'TaskId': tid, 'Kind': KIND, 'Status': 'pending', 'Deliver': deliver,
                                'Reason': 'your email - approve to send' if agent == 'owner' else f"{agent} wrote this email - approve to send"})       # who it goes to is on the card once
        mark(store, tid, hit['id'], rid=rid, actor=f'agent:{agent}')
    was = str((store.get_review(rid) or {}).get('Reason') or '')
    if (agent != 'owner' and guessed) or found or missing or GUESSED in was or NEEDS in was: store.update_review_reason(rid, with_guess(was, guessed, missing))
    if agent != 'owner':                          # the agent's sign-off off, the saved block on once (signatures.agent_signed)
        from .signatures import agent_signed
        text = agent_signed(store, store.get_review(rid), text) or text
    store.update_review_draft(rid, text, None, by=f'agent:{agent}')
    return {'ok': True, 'review_id': rid, 'slot': hit['id'], 'added': added, **(routine_sends(store, tid, rid, agent, missing) if sends else {}),
            **({'to_missing': to_missing(missing)} if missing else {}), **({'replaced_the_owners_version': his} if his else {}),
            **({'rewrote': rid, 'says': f"This rewrote your earlier email to {to} in this turn - one card stands, holding these words. For a second, "
                                        f"separate email to them, call again with slot=\"{NEW_SLOT}\"."} if rewrote == rid else {})}
NEW_SLOT = 'new'                 # propose (kind email)'s `slot` for a second letter to someone this turn already wrote to


def _written_before(store, tid: int, rv: dict) -> bool:
    "Was this card written in an earlier turn of its agent - one the owner prompted past (wrapup._turn_after)?"
    from . import wrapup
    return bool(wrapup._turn_after(store, tid, rv))


# A ROUTINE'S OWN EMAIL GOES (the owner, 2026-11-17: "routines should send on their own too" - approval is only for what answers input from
# outside): a routine run is his own work, so its agent's email to what he saved into the routine - himself, an address in its words - is sent
# at once through the one door his Send takes (verdicts.decide, which holds any other), quietly - the agent is mid-turn, it hears the send in
# what this returns. One with no address, or to someone the run chose, waits for him.
ROUTINE = 'routine'
def routine_sends(store, tid: int, rid: int, agent: str, missing: str = '') -> dict:
    "{'sent': True} where the task is a routine's run and its email went; {'send_error': why} where it did not; {} for any other task."
    if agent == 'owner' or missing or (store.get_task(tid) or {}).get('Source') != 'workflow': return {}
    from . import verdicts
    tok = verdicts.QUIET.set(True)
    try: out = verdicts.decide(store, store.get_review(rid), 'approve', actor=ROUTINE)
    except Exception as e: out = {'ok': False, 'error': str(e)}
    finally: verdicts.QUIET.reset(tok)
    if out.get('held'): return {}                 # ...one the owner did not save into the routine is its card (verdicts.saved_for)
    try: to = ', '.join((json.loads((store.get_review(rid) or {}).get('Deliver') or '{}') or {}).get('to') or []) or 'them'
    except (TypeError, ValueError): to = 'them'
    # ...and said to the agent as it happened: told the card "waits and nothing went", it reported a sent email as waiting for a press
    if out.get('ok') and not out.get('send_error'):
        return {'sent': True, 'says': f"Sent to {to} at once - a routine's email to what its owner saved into it goes without a press; say it went. No card waits on it."}
    why = out.get('send_error') or out.get('error') or 'it did not go'
    return {'send_error': why, 'says': f"Not sent to {to}: {str(why).rstrip(' .')}. Its card waits on the task for the owner's Send."}


# ...said to the agent in the same words whichever road the draft took: the tool or `taskuary --draft` returns it at once; a draft MARKER in an
# API-backed answer (the HIPAA AI's) is read after the turn ends, so its next turn hears it with what is waiting (events.py)
def to_missing(who: str) -> str:
    return (f"no address for {who} in the owner's mail or directory - the card's To is empty and waits for the owner; "
            "find one (someone at that organisation in the owner's mail) and draft again with it as `to`")
def needs_address(store, tid: int) -> list:
    "[(review id, who)] of the task's unsent emails whose To is still empty for want of an address."
    out = []
    for r in store._rows("SELECT ReviewId, Deliver FROM review WHERE TaskId=? AND Kind=? AND Status IN ('pending','held') ORDER BY ReviewId", (int(tid), KIND)):
        try: d = json.loads(r.get('Deliver') or '{}') or {}
        except (TypeError, ValueError): d = {}
        if isinstance(d, dict) and d.get('needs') and not d.get('to'): out.append((r['ReviewId'], str(d['needs'])))
    return out


def _point(store, tid: int, hit: dict, to: str, agent: str, name: str = '') -> dict:
    "The slot's `to` re-pointed at an address - the name it said kept as its label."
    items = store.task_checklist(tid)
    for i in items:
        if i.get('id') == hit['id']: i['out'] = {**i['out'], 'to': to, **({'name': name} if name and not i['out'].get('name') else {})}; hit = i
    store._write_checklist(tid, items, f'agent:{agent}')
    return hit


# NO NAME IN TO (the owner, 2026-11-09: an agent's email read "To: <a bank's name>" - "it needs to be email address"): triage's slot
# named an organisation and the draft copied the name onto the envelope. A name becomes an address when the draft is saved: the person
# it names in the owner's mail or directory, else someone at that organisation (marked guessed), else none - and To stays empty
_ORG = {'bank', 'inc', 'llc', 'ltd', 'plc', 'gmbh', 'co', 'corp', 'corporation', 'company', 'group', 'holdings', 'services', 'team', 'the', 'of', 'and'}
def address_for(store, tid: int, who: str) -> tuple:
    """(address, guessed) for the name on an email: a person found by every word of their name is known; a hit by company or domain
    is someone AT it, a guess. Those who wrote on this task come first. ('', False) when nobody can be put to it."""
    from . import peoplesearch as ps
    q = ' '.join(str(who or '').split())[:120]
    if '@' in q: return split(q)[1].lower(), False
    ws = ps._words(q)
    if not ws: return '', False
    here = {str(r.get('e') or '') for r in store._rows("SELECT DISTINCT LOWER(FromEmail) e FROM message WHERE TaskId=?", (tid,))}
    first = lambda hs: sorted((h for h in hs if '@' in str(h.get('to'))), key=lambda h: str(h['to']).lower() not in here)
    if hits := first(ps.search(store, q, 'email').get('data') or []):
        h = hits[0]; return h['to'].lower(), not set(ws) <= set(ps._words(h.get('name')))
    core = ' '.join(w for w in ws if w not in _ORG)
    if core and core != ' '.join(ws) and (hits := first(ps.plain(ps.known(store, 'email'), core))): return hits[0]['to'].lower(), True
    return '', False


# A GUESSED ADDRESS IS SAID ON THE CARD (the owner, 2026-11-09): with none on record one agent held its emails back and another put a
# firstname@ guess on the draft - the guess is allowed, the card says it, and the owner's Send is the check
GUESSED, NEEDS = ' - guessed, check before Send: ', ' - needs an email address for '
def with_guess(reason: str, guessed, missing: str = '') -> str:
    base = str(reason or '').partition(GUESSED)[0].partition(NEEDS)[0]
    return f"{base}{GUESSED + ', '.join(guessed) if guessed else ''}{NEEDS + missing if missing else ''}"


def _reopen(store, tid: int, want: str, agent: str):
    """The slot to this person whose email was taken back unsent (withdrawn or dropped), owed again: the corrected email goes
    in its place - add() refused it, so after a withdraw the owner was told to send the fix by hand (the product audit, 2026-11-08).
    Never one whose email went: what was sent is not owed again."""
    for i in reversed(all_(store, tid)):
        rv = store.get_review(i['rid']) if i.get('done') and i.get('rid') else None
        if rv and str(i['out'].get('to')).casefold() == want and rv.get('Status') in ('closed_unsent', 'rejected') and rv.get('DeliveryState') != 'sent':
            mark(store, tid, i['id'], done=False, actor=f'agent:{agent}')
            return {**i, 'done': False}
    return None


def subject_of(store, tid: int, hit: dict, subject: str = '') -> str:
    """The subject an email goes out with: the one written for its reader, else the slot's, else "Re:" the mail its person
    sent on this task, else what the slot is about. Never the task's title - that is the owner's own label, and three poll
    emails went out headed with it (agent-flow audit, 2026-11-07)."""
    from .outbound import re_subject
    o, to = hit['out'], str(hit['out'].get('to') or '').casefold()
    theirs = store._one("SELECT Subject FROM message WHERE TaskId=? AND LOWER(IFNULL(FromEmail,''))=? AND IFNULL(Subject,'')<>'' "
                        "ORDER BY SentAt DESC, MessageId DESC LIMIT 1", (tid, to)) if '@' in to else None
    about = str(hit.get('text') or '').partition(' - ')[2].strip()
    s = ' '.join(str(subject or o.get('subject') or (theirs and re_subject(theirs['Subject'])) or about[:1].upper() + about[1:]).split())
    return s[:200]


def readdress(store, rv: dict, to: list, actor: str = 'owner') -> dict:
    """The owner corrects who one of the task's emails goes to: the slot's `to` and its draft's Deliver, both - the card
    said "Devorah Cohn ?" with no way to give the address the agent never found (2026-10-06)."""
    to = [a for a in (' '.join(str(x or '').split()).lower() for x in to or []) if '@' in a]
    if not to: raise ValueError('give at least one email address')
    try: d = json.loads(rv.get('Deliver') or '{}') or {}
    except ValueError: d = {}
    d['to'] = to; d.pop('needs', None)
    # ...and an address the owner typed is no guess: only those still on it stay marked
    if d.get('guessed'): d['guessed'] = [a for a in d['guessed'] if a in to + [str(c).lower() for c in d.get('cc') or []]]
    if not store.set_review_deliver(rv['ReviewId'], json.dumps(d)): raise ValueError('that email is already being sent')
    if GUESSED in str(rv.get('Reason') or '') or NEEDS in str(rv.get('Reason') or ''): store.update_review_reason(rv['ReviewId'], with_guess(rv['Reason'], d.get('guessed')))
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
