"""Starting a message instead of answering one.

Every send in this app has been a REPLY: something arrived, triage judged it, a draft came
back, the owner approved and it went out on the channel it came in on. There was no door for
"I need to tell Marcus the census moved" - the owner had to go to Outlook, which is the app
Taskuary exists to keep them out of, and whatever they wrote there was invisible here.

So: ＋ New on the Timeline, and two forks that both end in the same place.

- SAY IT NOW: the AI writes the message from your ask, in your voice (the same SOUL/STYLE/
  LEARNED documents every reply uses - one voice, whichever direction the mail is travelling),
  and parks it in Review. You read it and press send. Nothing leaves on its own.
- FIND OUT FIRST: it becomes a task like any other and an agent works it. When the agent
  finishes it drafts the message from what it actually found, and THAT lands in Review. Same
  lifecycle, same buttons, same one approval at the end.

The row on the Timeline is created either way, at the moment you pressed the button, marked
outbound - so the day's record includes what you started, not only what happened to you.

Nothing here can send. `send_out` is reached from exactly one place (verdicts.decide, on an
approved review carrying `Deliver`), which is what keeps "the owner approves everything that
leaves" true no matter how many doors open onto the drafting.
"""
import json
from datetime import datetime
from loguru import logger

MODES = ('draft', 'task')
DRAFT_TOKENS = 400


COMPOSE_SYSTEM = (
    'You are writing a message the owner is about to send. It is NOT a reply - nothing arrived; '
    'they are starting this conversation, and the brief below is what they told you it is about.\n'
    'Turn the brief into the actual message. The brief is shorthand between the owner and you '
    '("the census numbers he asked for, plus why Ashgrove moved") - the recipient must never see '
    'the shorthand, only the message it stands for.\n'
    'Output ONLY the message body: no subject line, no "Draft:", no markdown, no notes about '
    'what you did.\n'
    'Say the thing and stop. Never invent a number, a date, a name or a commitment that is not in '
    'the brief or the material below - if the brief implies a fact you were not given, ask for it '
    'in the message rather than making one up.')

SUBJECT_SYSTEM = ('Write the subject line for this email: under nine words, specific, no "Re:", no '
                  'quotes, no trailing full stop. Answer with the line and nothing else.')


def _voice(store) -> str:
    """The same three documents every outgoing reply is written from, so a message the owner
    starts and a message the owner answers sound like the same person. Assembled here rather
    than imported from responder because that module's blocks are all about a thread."""
    from .learn import injectable
    from .responder import BREVITY, CHAT, EMAIL, SYSTEM, style_doc
    soul = store.doc('soul') or ''
    owner = soul.split('You work for **')[1].split('**')[0] if 'You work for **' in soul else 'the owner'
    return (SYSTEM.format(owner=owner), soul, style_doc(store), injectable(store.doc('learned') or ''), BREVITY, CHAT, EMAIL)


def draft_message(store, channel: str, to, about: str, resolution: str = None, llm=None,
                  cc: list = None) -> str:
    """The message itself. `resolution` is what an agent found, when one was sent to find out
    first - the brief says what to write about, the resolution says what is true."""
    from .knowledge import block as kb_block
    from .llm import build_llm
    llm = llm or build_llm(store)
    if not llm: raise RuntimeError('no AI connector is set up to write messages')
    ident, soul, sty, lrn, brevity, chat, email = _voice(store)
    is_chat = str(channel or '').lower() in ('teams', 'slack', 'telegram', 'whatsapp', 'imessage', 'discord')
    system = (ident + brevity + (chat if is_chat else email) + '\n' + COMPOSE_SYSTEM
              + (f'\n\nYOUR OWN document - your voice, your rules, your responsibilities:\n{soul[:4000]}' if soul else '')
              + (f'\n\nYour own style, distilled from mail you have actually sent - write like this:\n{sty[:2500]}' if sty else '')
              + (f'\n\nYour learned profile:\n{lrn[:2000]}' if lrn else ''))
    recipients = ', '.join(to) if isinstance(to, (list, tuple)) else str(to)
    copies = ', '.join(cc or [])
    user = f'TO: {recipients}' + (f'\nCC: {copies}' if copies else '') + \
           f'\nCHANNEL: {channel}\n\nWHAT THIS IS ABOUT (the owner\'s own words to you):\n{about}'
    if resolution: user += f'\n\nWHAT WAS ACTUALLY FOUND (an agent looked into this first - write from THESE facts):\n{resolution}'
    # what the company already has written down on this subject: quoted as facts to draw on,
    # never as instructions (knowledge.block says so in the block itself)
    kb = kb_block(store, f'{about} {resolution or ""}')
    if kb: user += kb
    out = str(llm(system, user, max_tokens=DRAFT_TOKENS) or '').strip()
    if not out: raise RuntimeError('the AI returned an empty message')
    from .responder import strip_signoff
    return strip_signoff(out) if is_chat else out


def subject_for(store, about: str, llm=None) -> str:
    """A subject line, for the channels that have one. A failure here is not a failure to
    send: the brief's own first words are a serviceable subject."""
    fallback = ' '.join(str(about or 'No subject').split())[:78]
    try:
        from .llm import build_llm
        llm = llm or build_llm(store)
        if not llm: return fallback
        line = ' '.join(str(llm(SUBJECT_SYSTEM, about, max_tokens=40) or '').split()).strip('"\'. ')
        return line[:120] or fallback
    except Exception as e:
        logger.debug(f'subject line fell back to the brief: {e}')
        return fallback


def redraft_review(store, review: dict, resolution: str = None, llm=None) -> str:
    """Rewrite a new outbound message from its saved envelope, including all To/CC recipients."""
    try: deliver = json.loads(review.get('Deliver') or '{}') or {}
    except (TypeError, ValueError): deliver = {}
    if not deliver.get('channel'): raise ValueError('this review has no outbound destination')
    task = store.get_task(review.get('TaskId')) or {}
    message = store.get_message(review.get('MessageId')) or {}
    about = task.get('Summary') or message.get('BodyText') or task.get('Title') or ''
    if resolution is None:
        from .responder import resolution_of
        resolution = resolution_of(store, review.get('TaskId')) if review.get('TaskId') else None
    draft = draft_message(store, deliver['channel'], deliver.get('to'), about,
                          resolution=resolution, llm=llm, cc=deliver.get('cc'))
    store.update_review_draft(review['ReviewId'], draft, review.get('RunId'))
    return draft


def compose(store, channel: str, to, about: str, mode: str = 'draft', subject: str = None,
            repo: str = None, actor: str = 'owner', llm=None, cc: list = None) -> dict:
    """Start something outbound. Returns {taskId, messageId, reviewId, mode, draft, subject}.

    Both modes leave the same shape behind - a task, a Timeline row marked outbound, and a
    review carrying WHERE it goes - so the approve button, the audit trail and the reply-pending
    tag on the Timeline are the ones that already exist."""
    from . import outbound, terminal as term
    from .store import task_ref
    channel, about = str(channel or '').strip().lower(), str(about or '').strip()
    if not about: raise ValueError('say what the message is about')
    if channel == 'email':
        def parts(values):
            values = values if isinstance(values, (list, tuple)) else [values]
            return [part.strip() for value in values
                    for part in str(value or '').replace(';', ',').split(',') if part.strip()]
        raw_to, raw_cc = parts(to), parts(cc or [])
        to = outbound.addrs(raw_to)
        cc = [a for a in outbound.addrs(raw_cc) if a.lower() not in {x.lower() for x in to}]
        bad = [a for a in raw_to + raw_cc if not outbound.addrs([a])]
        if bad: raise ValueError(f"not a valid email address: {', '.join(bad)}")
        if not to: raise ValueError('add at least one email recipient')
    else:
        to = str(to[0] if isinstance(to, (list, tuple)) and to else to or '').strip()
        cc = []
        if not to: raise ValueError('say who it goes to')
    if mode not in MODES: raise ValueError(f"mode must be one of {', '.join(MODES)}")
    if not outbound.can_reply(store, channel):
        raise ValueError(f'{channel or "that channel"} cannot send from here - turn its replies on '
                         'in Connections, or pick another channel')
    subject = (subject or '').strip() or (subject_for(store, about, llm) if channel == 'email' else about[:120])

    tid = store.create_task({'Title': subject[:300], 'Summary': about,
                             'Kind': 'coding' if mode == 'task' else 'reply',
                             'Status': 'open', 'Priority': 'normal', 'Source': 'outbox',
                             'Tags': f'repo:{repo}' if repo else None}, actor)
    # the Timeline row. It wears the TARGET channel, not a synthetic one: Direction 'out' is
    # already how the feed renders something we sent, and can_reply / the send path both need a
    # real channel behind the row.
    to_text = ', '.join(to) if isinstance(to, list) else to
    mid = store.add_message({'TaskId': tid, 'ExternalId': f'outbox:{tid}', 'ConversationId': f'outbox:{tid}',
                             'Channel': channel, 'SourceName': to_text, 'Subject': subject, 'FromName': 'You',
                             'Direction': 'out', 'BodyText': about, 'Status': 'routed',
                             'SentAt': datetime.now().strftime('%Y-%m-%d %H:%M:%S')})
    deliver = json.dumps({'channel': channel, 'to': to, 'cc': cc, 'subject': subject})
    store.add_route(mid, tid, 'outbox', None,
                    f'you started this from the Timeline - ' +
                    ('an agent is finding out first, then it drafts the message'
                     if mode == 'task' else 'drafted for you to approve, then it sends'), [], actor)

    if mode == 'task':
        # the review is created NOW and held: coder.raise_reply finds it when the agent finishes
        # and has the responder rewrite it from what was actually found. Without it, finishing an
        # outbound task would look for a message to answer, find only ours, and draft nothing.
        rid = store.add_review({'TaskId': tid, 'MessageId': mid, 'Kind': 'draft_reply', 'Status': 'pending',
                                'Reason': f'you asked for this to be looked into first - {to_text} hears back when it is',
                                'Deliver': deliver})
        store.hold_reviews(tid, 'held while an agent finds out - the message is written from what it finds')
        try:
            ses = term.start_on_task(store, tid, instruction=f'Find out what is needed to send this message to {to_text}: {about}', actor=actor)
        except Exception as e:
            logger.warning(f'outbox could not start an agent on {task_ref(tid)}: {e}')
            store.add_comment(tid, 'router', 'agent', f'Could not start the agent ({str(e)[:200]}) - start it from the task.')
            ses = None
        return {'taskId': tid, 'ref': task_ref(tid), 'messageId': mid, 'reviewId': rid,
                'mode': mode, 'subject': subject, 'draft': None, 'session': ses}

    draft = ''
    try:
        draft = draft_message(store, channel, to, about, llm=llm, cc=cc)
    except Exception as e:
        # a review with no draft is still the right row: "Draft with AI" retries it, and the
        # owner can simply type the message themselves. Losing the row would lose the intent.
        logger.warning(f'outbox draft failed for {task_ref(tid)}: {e}')
        store.add_comment(tid, 'router', 'agent', f'Could not draft this ({str(e)[:200]}) - write it yourself, or retry the draft.')
    rid = store.add_review({'TaskId': tid, 'MessageId': mid, 'Kind': 'draft_reply', 'Status': 'pending',
                            'DraftText': draft, 'Deliver': deliver,
                            'Reason': f'a message to {to_text} you started - approve to send it'})
    store.audit('task', tid, 'outbox', actor, detail={'channel': channel, 'to': to, 'cc': cc, 'mode': mode})
    return {'taskId': tid, 'ref': task_ref(tid), 'messageId': mid, 'reviewId': rid,
            'mode': mode, 'subject': subject, 'draft': draft}
