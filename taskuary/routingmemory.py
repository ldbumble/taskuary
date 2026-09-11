"""What triage decided, what the owner made of it, and what the next verdict is told.

Triage answers about ten things - intent, kind, title, summary, checklist, profile, playbook,
repository, and a chat line's relationship - and until now exactly ONE of them ever learned from
being corrected. Picking a repository writes a weighted, task-keyed edge into the project graph
(projects.learn_task_repository): one owner choice is a visible hypothesis at .72, two independent
ones reach .86 and may route on their own. Every other field was overwritten in place and the
lesson thrown away - TQ-0501 went to a coding agent in a bank-feeds checkout because nothing had
ever recorded that clocking in and out lives in a system this install has no code for.

So this is that same loop, for the rest of the verdict. Deliberately the same shape, the same
thresholds and the same evidence curve as the project graph, because it is the same idea; a second
vocabulary for "we have seen this twice now" would only be a second thing to keep in step.

Two halves, and the first is what makes the second possible:
- route.VerdictJson keeps the verdict itself - the BEFORE half of every correction diff. A
  rewritten summary teaches nothing if nothing remembers what it was rewritten from.
- routing_fact keeps the LESSON, keyed to a signal the NEXT message can carry.

What a correction is worth depends on the field. `kind`, `profile` and `playbook` are ROUTING - a
correction generalises straight to the next message like it. `system` is the one the owner types
("this is ADP, not FanApp"): the fact that was missing entirely, because the only map triage had
was a list of git repositories. Title, summary and checklist are deliberately NOT here - correcting
those teaches style, not routing, and style is LEARNED.md's, which already learns it from drafts.
"""
from loguru import logger

from .projects import CONTEXT_CONFIDENCE, PUBLIC_MAIL, ROUTE_CONFIDENCE

FIELDS = ('kind', 'profile', 'playbook', 'system')
# A chat's "subject" is the ROOM ("Teams chat with Mindy Gorelick"), so a topic key made from it
# says "chats with Mindy", which is wrong in both directions: it would not fire on the same ask
# from anyone else, and it would damp a real bug she reports tomorrow. Chat learns by sender only.
from .ingest import CHAT_CHANNELS


def signals_of(msg: dict) -> list:
    """[(signal, key)] this message can be recognised by later. Deliberately few and cheap: who
    wrote it, the company they wrote from, and what it was about when that is a real subject."""
    from .routing import subject_topic
    out, em = [], str(msg.get('FromEmail') or msg.get('from_email') or '').strip().lower()
    if em:
        out.append(('sender', em))
        dom = em.rsplit('@', 1)[-1] if '@' in em else ''
        if dom and dom not in PUBLIC_MAIL: out.append(('sender_domain', dom))
    if str(msg.get('Channel') or msg.get('channel') or '').lower() not in CHAT_CHANNELS:
        topic = subject_topic(str(msg.get('Subject') or msg.get('subject') or ''))
        if topic: out.append(('subject', topic))
    return out


def task_signals(store, task_id: int) -> list:
    """The signals of a task's INBOUND messages - what arrived, never what we sent back."""
    out = []
    for m in store.list_messages(task_id):
        if str(m.get('Direction') or 'in') == 'out' or m.get('Status') == 'context': continue
        for s in signals_of(m):
            if s not in out: out.append(s)
    return out


def learn_correction(store, task_id: int, field: str, value: str, actor: str = 'owner',
                     reason: str = None, confirmed: bool = None) -> int:
    """One correction, against every signal the task arrived by. Returns how many lessons gained
    evidence from it - 0 when this task already counted (a re-press must not inflate a guess).

    `confirmed` marks a lesson the owner STATED rather than one inferred from their click: a typed
    answer is their word and routes at once, where a reclassification is one episode of evidence.
    """
    if field not in FIELDS: raise ValueError(f'{field} is not a routing field')
    value = str(value or '').strip()
    if not value: return 0
    owned = confirmed if confirmed is not None else (actor == 'owner' and field == 'system')
    changed = 0
    for signal, key in task_signals(store, task_id):
        try:
            fid = store.upsert_routing_fact(field, signal, key, value, confirmed=owned,
                                            source=f'correction:{actor}')
            changed += int(store.add_routing_evidence(fid, task_id, reason or f'owner set {field}={value}'))
        except Exception as e:
            logger.debug(f'routing memory: {field}={value} on {signal}:{key} not learned - {e}')
    if changed: store.audit('task', task_id, 'routing_learned', actor, detail={'field': field, 'value': value})
    return changed


# What a signal has to clear before triage hears about it. A COMPANY is not a person: one
# colleague's correction must not speak for everyone who shares their domain, so the domain tier
# needs two independent corrections (.86) where a named sender needs one (.72). This is the bar
# projects._identity_links already sets on repository edges - learned the same way, by a single
# repo choice on one address branding the whole of mfa.net.
FLOOR = {'sender': CONTEXT_CONFIDENCE, 'subject': CONTEXT_CONFIDENCE, 'sender_domain': ROUTE_CONFIDENCE}
TIERS = ('sender', 'subject', 'sender_domain')      # most specific first; a weaker tier never overrules


def facts_for(store, msg: dict) -> list:
    """What to tell triage about messages like this one. Each row says how sure we are and where it
    came from, because a lesson learned once must inform a verdict without dictating it - the same
    contract projects.context_for_message keeps with its tentative repository links.

    One field is answered by ONE tier: the most specific that has anything to say. A fact about
    this sender stands on its own; the company they write from only speaks when nothing more
    specific does, and then only once it has been corrected twice."""
    rows, spoken = [], set()
    facts = store.routing_facts(signals=signals_of(msg))
    for tier in TIERS:
        for f in facts:
            if f['Signal'] != tier or f['Field'] in spoken: continue
            conf = float(f['Confidence'] or 0)
            # A stated fact is certain about ITSELF, never about its reach: "clocking in is ADP"
            # being the owner's own words says nothing about whether everyone at their company
            # writes about clocking in. So the owner's word clears the bar for the person they
            # said it about, and the company tier still has to earn its scope from evidence.
            if not (f['Confirmed'] and tier != 'sender_domain') and conf < FLOOR.get(tier, ROUTE_CONFIDENCE): continue
            rows.append({'field': f['Field'], 'value': f['Value'], 'seen_on': tier,
                         'times': int(f['EvidenceCount'] or 0), 'confidence': round(conf, 2),
                         'owner_stated': bool(f['Confirmed']),
                         'tentative': not f['Confirmed'] and conf < ROUTE_CONFIDENCE})
        # a field is settled by the first tier that could speak for it, so the next tier is only
        # consulted for the fields still unanswered - never to add a second opinion on one
        spoken |= {r['field'] for r in rows}
    return rows[:8]


# What each verdict MEANT, so the lesson says what changed rather than naming a field and a token.
# "kind: coding -> task" is a diff; "the owner took it off the agent onto their own list" is a
# lesson, and the hot pass can only generalise the second.
MEANS = {'kind': {'coding': 'a coding agent working in a checkout',
                  'general': "a conversation with the assistant, which needs no repository",
                  'general_': '', 'task': "the owner's own list, with nothing working it",
                  'reply': 'a drafted reply and nothing else'}}


def lesson(store, task_id: int, field: str, value: str, belongs_to: str = None, ev: str = None) -> str:
    """One correction as the sentence LEARNED.md's hot pass reads (learn.learn_from).

    It can finally say what triage ACTUALLY ANSWERED, because the verdict is on file now
    (route.VerdictJson): "triage said coding, the owner made it their own" is a lesson, where
    "kind is now task" was only ever a field. Five corrections used to reach this document as one
    vague line about coding or as nothing at all - a reassigned worker, a rerouted repository and
    a move to the assistant all taught it precisely nothing.
    """
    t, v = store.get_task(task_id) or {}, store.task_verdict(task_id) or {}
    title = ' '.join(str(t.get('Title') or '').split())[:80]
    was, head = str(v.get(field) or '').strip(), (ev or f'task{task_id}')
    # a task routed before the verdict was kept has no BEFORE, and the lesson has to read as a
    # sentence either way - "triage and the owner made it task" is neither English nor a lesson
    if field == 'kind':
        what = MEANS['kind'].get(value, value)
        line = (f'triage said {was} and the owner made it {value}' if was
                else f'the owner made it {value}') + f' - {what}'
    elif field == 'profile':
        line = (f'triage said {was} would work it and the owner handed it to the {value} agent instead' if was
                else f'the owner put the {value} agent on it')
    elif field == 'repository':
        line = (f'triage chose {was} and the owner moved the work to {value}' if was
                else f'the owner put the work in {value}')
    elif field == 'system':
        line = f'the owner says this belongs to {value}, which is not a repository here'
    else:
        line = f'the owner set {field} to {value}'
    extra = f' - it belongs to {belongs_to.strip()}' if (belongs_to or '').strip() and field != 'system' else ''
    return f'{head}: "{title}" - {line}{extra}'


PROMPT = (
    '\n\nWHAT THE OWNER HAS CORRECTED BEFORE is in routing_history: verdicts like this one that they '
    'changed afterwards, each with the field they changed, what they changed it to, how many times, '
    'and how sure we are.\n'
    '- owner_stated true is their own typed answer - treat it as fact. A `system` row is the one that '
    'matters most: it names where this kind of work actually lives, and if that is a system this '
    'install holds no code or credentials for, the kind is `task`, not `coding`.\n'
    '- tentative true is ONE correction, not a rule: weigh it, say so in your reason if it decided '
    'you, and never let it outrank what the message plainly says.\n'
    '- Nothing here forces a verdict. It is what happened last time, not an instruction.')
