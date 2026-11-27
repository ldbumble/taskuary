"""Starting a message instead of answering one.

Every send in this app has been a REPLY: something arrived, triage judged it, a draft came
back, the owner approved and it went out on the channel it came in on. There was no door for
"I need to tell Marcus the census moved" - the owner had to go to Outlook, which is the app
Taskuary exists to keep them out of, and whatever they wrote there was invisible here.

So: ＋ New on the Timeline. It becomes a task like any other and its agent works it (compose): it finds out what it needs,
writes the message and raises its card - one approval at the end (the owner, 2026-11-27: "side model should never work in
agent canvas"). The row on the Timeline is created at the moment you pressed the button, holding your ask (ask_row) - so the
day's record includes what you started, not only what happened to you.

draft_message stays for the roads outside a task's canvas that still use it (a routine's email step, flow.py).

Nothing here can send. `send_out` is reached from exactly one place (verdicts.decide, on an
approved review carrying `Deliver`), which is what keeps "the owner approves everything that
leaves" true no matter how many doors open onto the drafting.
"""
import json
from .say import said as _said            # a failure written to the chat is said in his words (say.py)
import re
from datetime import datetime
from loguru import logger
from . import capabilities

DRAFT_TOKENS = 400


COMPOSE_SYSTEM = (
    'You are writing a message the owner is about to send. It is NOT a reply - nothing arrived; '
    'they are starting this conversation, and the brief below is what they told you it is about.\n'
    'Turn the brief into the actual message. The brief is shorthand between the owner and you '
    '("the census numbers he asked for, plus why Site 7 moved") - the recipient must never see '
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
    from .responder import BREVITY, CHAT, EMAIL, SYSTEM, owner_of, signature_line, style_doc
    soul = store.doc('soul') or ''
    # STYLE for voice and the owner's writing instructions (its Owner notes), SOUL for identity - and no LEARNED.md, which is triage's
    # (PW-058/059). The fourth slot was the notes table's writing notes; they live in STYLE.md now (2026-10-27)
    return (SYSTEM.format(owner=owner_of(store, soul)) + signature_line(store), soul, style_doc(store), '', BREVITY, CHAT, EMAIL)


def draft_message(store, channel: str, to, about: str, resolution: str = None, llm=None,
                  cc: list = None, attached: list = None, mailbox: str = None) -> str:
    """The message itself. `resolution` is what an agent found, when one was sent to find out
    first - the brief says what to write about, the resolution says what is true. An email is signed
    as the `mailbox` it leaves from, like a reply: a new email used to sign as STYLE.md's one learned
    signature, so mail from a second mailbox went out under the first one's hat."""
    from .knowledge import block as kb_block
    from .llm import build_llm
    from .responder import chat_said, email_rule, own_names, signature_for, signed
    llm = llm or build_llm(store, job='draft')
    if not llm: raise RuntimeError('no AI connector is set up to write messages')
    ident, soul, sty, lrn, brevity, chat, _ = _voice(store)
    from .routing import CHAT_CHANNELS
    is_chat = str(channel or '').lower() in CHAT_CHANNELS
    system = (ident + brevity + (chat if is_chat else email_rule(store, mailbox)) + '\n' + COMPOSE_SYSTEM
              + (f'\n\nYOUR OWN document - your voice, your rules, your responsibilities:\n{soul[:4000]}' if soul else '')
              + (f'\n\nYour own style, distilled from mail you have actually sent - write like this:\n{sty[:2500]}' if sty else '')
              + (f'\n\nYour own writing instructions:\n{lrn[:2000]}' if lrn else ''))
    from .responder import voice_line          # ...and how the owner writes to these people (STYLE.md "By recipient", byrecipient.py)
    system += voice_line(store, list(to) if isinstance(to, (list, tuple)) else [to])
    recipients = ', '.join(to) if isinstance(to, (list, tuple)) else str(to)
    copies = ', '.join(cc or [])
    user = f'TO: {recipients}' + (f'\nCC: {copies}' if copies else '') + \
           f'\nCHANNEL: {channel}\n\nWHAT THIS IS ABOUT (the owner\'s own words to you):\n{about}'
    if resolution: user += f'\n\nWHAT WAS ACTUALLY FOUND (an agent looked into this first - write from THESE facts):\n{resolution}'
    # what really rides on it: a draft wrote "the attached template" over an email with nothing attached (2026-10-09)
    if attached is not None:
        user += (f"\n\nATTACHED TO THIS MESSAGE: {', '.join(attached)}" if attached
                 else '\n\nNOTHING IS ATTACHED to this message - never say or imply that something is attached.')
    # what the company already has written down on this subject: quoted as facts to draw on,
    # never as instructions (knowledge.block says so in the block itself)
    kb = kb_block(store, f'{about} {resolution or ""}')
    if kb: user += kb
    out = str(llm(system, user, max_tokens=DRAFT_TOKENS) or '').strip()
    if not out: raise RuntimeError('the AI returned an empty message')
    return chat_said(store, out) if is_chat else signed(out, signature_for(store, mailbox), own_names(store))


def subject_for(store, about: str, llm=None) -> str:
    """A subject line, for the channels that have one. A failure here is not a failure to
    send: the brief's own first words are a serviceable subject."""
    fallback = ' '.join(str(about or 'No subject').split())[:78]
    try:
        from .llm import build_llm
        llm = llm or build_llm(store, job='summary')          # a line off a brief: the quick model's, like every other summary (it was a 'draft')
        if not llm: return fallback
        line = ' '.join(str(llm(SUBJECT_SYSTEM, about, max_tokens=40) or '').split()).strip('"\'. ')
        return line[:120] or fallback
    except Exception as e:
        logger.debug(f'subject line fell back to the brief: {e}')
        return fallback


# THE ASK IS HIS INSTRUCTION, NOT MAIL HE SENT (2026-11-17): it was filed outbound with its recipient as its source - the page drew it as
# "Sent by you", and the agent read "FROM You" with nobody named, as his own reply on the thread, beside a draft "to You", and asked him whom
# it was for. Now it is his line as typed, from him (wrapup.from_owner), its recipients where every message keeps them, said as `asked`.
# It wears the TARGET channel: can_reply and the send path read a real channel behind the row.
ASK = 'outbox:'
def is_ask(m) -> bool: return str((m or {}).get('ExternalId') or '').startswith(ASK)

def ask_row(store, tid: int, channel: str, to, cc, subject: str, body: str) -> int:
    "File the owner's ask on task `tid` - his words `body`, for `to`/`cc` on `channel` - and return its message id."
    to = list(to) if isinstance(to, (list, tuple)) else [to]
    return store.add_message({'TaskId': tid, 'ExternalId': f'{ASK}{tid}', 'ConversationId': f'{ASK}{tid}', 'Channel': channel,
                              'Subject': subject, 'FromName': 'You', 'BodyText': body, 'Status': 'routed',
                              'RecipientsJson': json.dumps({'to': to, 'cc': list(cc or [])}),
                              'SentAt': datetime.now().strftime('%Y-%m-%d %H:%M:%S')})

def asked(m) -> str:
    "'You asked to email a@x (cc b@y)' for the owner's ask - every surface's one label for it - '' for any other row."
    if not is_ask(m): return ''
    try: r = json.loads(m.get('RecipientsJson') or '{}') or {}
    except (TypeError, ValueError): r = {}
    to, cc = ', '.join(r.get('to') or []) or 'someone', ', '.join(r.get('cc') or [])
    ch = str(m.get('Channel') or '').lower()
    return (f'You asked to email {to}' if ch == 'email' else f'You asked to message {to} on {ch}') + (f' (cc {cc})' if cc else '')


def compose(store, channel: str, to, about: str, subject: str = None, actor: str = 'owner', cc: list = None, files=None) -> dict:
    """Start something outbound: a task holding his ask (ask_row), and his ask as his line to its agent (general.to_agent) - the agent finds
    out what it needs, writes the message and raises its card for his Send (the owner, 2026-11-27: "side model should never work in agent
    canvas"). `files`: what he attached to his ask, the task's Files. Returns {taskId, ref, messageId, subject, asked}. Nothing is sent here."""
    from . import general, outbound
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
    no = capabilities.send_refusal(store, channel)
    if no: raise ValueError(no)
    given = (subject or '').strip()
    subject = given or ' '.join(about.split())[:120]
    tid = store.create_task({'Title': subject[:300], 'Summary': about, 'Files': list(files or []), 'Kind': 'general', 'Status': 'open',
                             'Priority': 'normal', 'Source': 'outbox'}, actor)
    # ...a file he attached is the task's own, in its folder, named under his words (outputs.take_in_ask, general.with_files)
    from . import outputs
    told = general.with_files(about, outputs.take_in_ask(store, tid, actor))
    to_text = ', '.join(to) if isinstance(to, list) else to
    mid = ask_row(store, tid, channel, to, cc, subject, about)
    store.add_route(mid, tid, 'outbox', None, 'you started this from Taskuary - its agent writes it for you to approve, then it sends', [], actor)
    store.audit('task', tid, 'outbox', actor, detail={'channel': channel, 'to': to, 'cc': cc})
    said = (f'Email {to_text}' if channel == 'email' else f'Message {to_text} on {channel}') + (f", cc {', '.join(cc)}" if cc else '') \
        + (f', subject "{given}"' if given else '') + f': {told}'
    try: how = general.to_agent(store, tid, said, actor, frm='owner', wait=False)
    except (ValueError, RuntimeError) as e:
        logger.warning(f'outbox could not reach the agent on {task_ref(tid)} for {to_text}: {e}')
        store.add_comment(tid, 'router', 'agent', f'Could not start the agent ({_said(e)}) - start it from the task.'); how = ''
    return {'taskId': tid, 'ref': task_ref(tid), 'messageId': mid, 'subject': subject, 'asked': bool(how)}


def work_of(store, tid: int) -> str:
    """What was actually done on a task, for a message about it: the coding session's final word, else the newest answer
    an agent saved (session_artifacts.result), else nothing - the brief alone, and the drafter asks for what it lacks."""
    from .responder import resolution_of
    from . import session_artifacts as sa
    done = resolution_of(store, tid)
    if done: return str(done)[:6000]
    ans = [a for a in store.list_task_artifacts(tid) if a.get('Kind') == 'agent_result']
    path = sa.confined(max(ans, key=lambda a: (str(a.get('CreatedAt') or ''), a.get('ArtifactId') or 0)).get('Path')) if ans else None
    if not path: return ''
    # its '# TQ-0001 - <title>' heading is the task's title, not a finding: a title quoting the ask is not a result
    return re.sub(r'^# .*\n+', '', path.read_text(encoding='utf-8', errors='replace'), count=1)[:6000]
