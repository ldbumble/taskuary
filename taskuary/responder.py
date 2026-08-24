"""Replies: the other half of the funnel, and the cheap half.

Most inbound mail does not need an agent, a repo or a session - it needs an answer. Triage
already separates those (reply_only vs task); this writes the answer with the MAIN AI, in
the owner's voice per SOUL.md, and parks it for approval. Approving sends it (see outbound).

Drafting used to require a CLI agent named `responder`. Nobody has one, so reply-only mail
sat in the queue undrafted - and the fallback was worse: the *coding* agent, opened on a
repo, to write two sentences of email.

Every reply comes through `write_draft`: the mail that only ever needed an answer, and the
mail a coder just finished the work behind. The coder reports what it did; the reply is
written here either way, so the sender always hears one voice.
"""
import re
from loguru import logger

SYSTEM = (
    # "You write {owner}'s replies" made the model {owner}'s ASSISTANT, and it wrote like one:
    # "I can't suggest times by email alone; Uri will need to handle scheduling directly." -
    # signed Uri. Third person about the sender, first person about a tool's limitations, over
    # the owner's own name. The identity has to be stated as identity, not as a job.
    'You ARE {owner}. This message goes out over your name, from your own mailbox, and the '
    'person receiving it will read it as written by you - because it was.\n'
    'Write in the FIRST PERSON, always. "I will send times this afternoon", never "{owner} will '
    'send times" - referring to yourself in the third person is the one mistake that gives the '
    'whole thing away. The rest of the prompt talks ABOUT {owner} because it is describing you; '
    "any document here saying you work FOR them is written for other tasks, not this one.\n"
    'You are not an assistant and you have no tooling, limits or instructions to report. Never '
    "write about what you can or cannot do - \"I can't do that by email\" is an AI talking, not "
    'a person. If something cannot be settled in this reply, say what you will do next, or what '
    'you need from them.\n'
    "Output ONLY the message body - no subject line, no 'Draft:', no markdown.\n"
    'Answer the question actually asked, in the fewest words that fully answer it. Use what '
    "the thread and the operator's document give you; never invent facts, numbers, dates or "
    'commitments. If something needed to answer is genuinely missing, say plainly what you '
    'need instead of guessing.\n')

# A reply nobody reads to the end is a reply that failed. Two or three sentences, and no
# restating the question back at someone who just asked it.
BREVITY = ('BE SHORT. Two or three sentences, under 60 words. Lead with the answer - fixed, or the '
           'one reason it is not. No preamble ("Thanks for reaching out", "I wanted to let you know"), '
           'no recap of what they just told you, no closing offer of further help unless something '
           'is genuinely still open.\n')

# Chat is not email. A signature at the end of a Teams message reads like a form letter, and
# nobody signs their name in a thread that already says who is talking.
CHAT = ('This is CHAT (Teams/Slack), not email. NO greeting and NO sign-off or name at the end - '
        'the channel already says who you are. One short paragraph, written the way a person types '
        'in a chat window.')
EMAIL = ('This is EMAIL. A brief greeting and the sign-off SOUL.md specifies are fine; nothing else '
         'ceremonial.')

# This line used to say "the owner will turn it into a task", and the model answered in kind:
# a sentence about what someone ELSE would have to do. Say it the way a person would.
NOT_YET = ('If the request cannot be answered by a reply alone - it needs work doing - say in one '
           'line that you will pick it up, and stop. Not who will do it, not how, and never that '
           'you are unable to.')
# the coder has already closed the thread: this reply reports an outcome, never promises one
DONE = ('The work this thread asked for is FINISHED - the report below says what was done. Say what '
        'happened in a sentence or two, claiming nothing the report does not support; if it could NOT '
        'be done, say that and why, just as briefly. Never mention agents, tasks, tickets, '
        'repositories or tooling: YOU did this.')

CHAT_CHANNELS = ('teams', 'slack', 'telegram', 'whatsapp')
REPLY_TOKENS = 300          # a ceiling as well as an instruction: 800 invited an essay

# SOUL.md tells the model how to sign off, and it obeys - in a chat window too, where it reads
# like a form letter. Belt and braces: the prompt says not to, and this takes it off anyway.
_SIGNOFF = re.compile(r'^(best|thanks|thank you|regards|cheers|kind regards|best regards|sincerely)[\s,!.]*$', re.I)
_COMMENT = re.compile(r'<!--.*?-->', re.S)
_TEMPLATE_LINES = re.compile(r'^.*(not generated yet|Write your own rules here).*$', re.M)

def style_doc(store) -> str:
    """STYLE.md as prompts read it: comments and template placeholders stripped, owner tokens
    rendered - and empty until the doc says something REAL (headers alone are not a style),
    so the untouched template never rides into a prompt as noise. The doc is the owner's
    voice distilled from their own sent mail (Docs → STYLE.md → Generate from history)."""
    t = _TEMPLATE_LINES.sub('', _COMMENT.sub('', store.doc('style') or ''))
    meat = '\n'.join(l for l in t.splitlines() if l.strip() and not l.strip().startswith('#'))
    return t.strip() if len(meat) > 40 else ''

def strip_signoff(text: str) -> str:
    lines = [l for l in (text or '').rstrip().splitlines()]
    while lines:
        last = lines[-1].strip()
        # a closing word, or a bare name/initials on its own line at the end
        if not last or _SIGNOFF.match(last) or (len(last.split()) <= 3 and len(last) <= 28
                                                and last.rstrip('.').replace('-', ' ').replace(',', '').replace(' ', '').isalpha()):
            lines.pop(); continue
        break
    return '\n'.join(lines).strip()


def draft_reply(store, task_id: int, llm=None, resolution: str = None) -> str:
    """The reply this task needs, as text. Uses the owner's own brain (the AI connector, or
    whichever brain `triage_ai` names), the standing memory notes, and the thread itself."""
    from .llm import build_llm
    from .ingest import notes_for
    llm = llm or build_llm(store)
    if not llm: raise RuntimeError('no AI connector is set up to write replies')
    t = store.get_task(task_id) or {}
    msgs = [m for m in store.list_messages(task_id) if m.get('Status') != 'context']
    if not msgs: raise RuntimeError('nothing to reply to on this task')
    last = msgs[-1]
    soul = store.doc('soul') or ''
    owner = (soul.split('You work for **')[1].split('**')[0] if 'You work for **' in soul else 'the owner')
    notes = notes_for(store, {'from_email': last.get('FromEmail')})
    chat = str(last.get('Channel') or '').lower() in CHAT_CHANNELS
    from .learn import injectable
    lrn = injectable(store.doc('learned') or '')
    sty = style_doc(store)
    system = (SYSTEM.format(owner=owner) + BREVITY + (CHAT if chat else EMAIL) + '\n'
              + (DONE if resolution else NOT_YET)
              # every block below describes YOU. They are written in the third person because
              # the same documents serve agents working FOR the owner - said once, here, so the
              # model does not read its own biography as notes about somebody else.
              + (f"\n\nYOUR OWN document - your voice, your rules, your responsibilities. Where it "
                 f"says you work for {owner}, it is addressing an agent on other tasks; on this "
                 f"one it is describing you:\n{soul[:4000]}" if soul else '')
              + (f'\n\nYour own style, distilled from mail you have actually sent - write like '
                 f'this:\n{sty[:2500]}' if sty else '')
              + (f'\n\nYour learned profile - how you write and work, distilled from your own '
                 f'verdicts on past drafts:\n{lrn[:2000]}' if lrn else ''))
    if notes:
        system += '\n\nYour own standing notes:\n' + '\n'.join(f'- {n}' for n in notes[:20])[:1500]
    from .triage import strip_boilerplate
    thread = '\n\n'.join(
        f"--- {'YOU' if m.get('Status') == 'context' else (m.get('FromName') or m.get('FromEmail'))}"
        f" · {m.get('SentAt')} · {m.get('Channel')}\n{strip_boilerplate(str(m.get('BodyText') or ''))[:4000]}"
        for m in store.list_messages(task_id)[-6:])
    user = f"Subject: {last.get('Subject') or t.get('Title') or ''}\nFrom: {last.get('FromName')} <{last.get('FromEmail')}>\n\n{thread}"
    if resolution: user += f'\n\n--- WHAT WAS DONE (your source of truth; the sender has not seen it)\n{resolution}'
    out = (llm(system, user, max_tokens=REPLY_TOKENS) or '').strip()
    if not out: raise RuntimeError('the AI returned an empty reply')
    return (strip_signoff(out) or out) if chat else out    # never strip a reply down to nothing


def draft_for_review(store, task_id: int, review_id: int, llm=None, resolution: str = None) -> str:
    """Write the draft and park it on its review, ready for approve / edit / no-reply."""
    text = draft_reply(store, task_id, llm, resolution)
    store.update_review_draft(review_id, text, None)
    logger.info(f'drafted reply for task {task_id} ({len(text)} chars)')
    return text


def resolution_of(store, task_id: int):
    """The coder's own report on this task, if one closed it - so hitting Redraft says what
    was done instead of reverting to "this needs work doing"."""
    return next((c['Body'] for c in reversed(store.list_comments(task_id))
                 if str(c.get('Body') or '').startswith('CODER REPORT')), None)


def write_draft(store, task_id: int, review_id: int, resolution: str = None, actor: str = 'system', llm=None) -> str:
    """The one door every reply comes through - and there is only one road behind it now.

    An agent named `responder` used to take this over and run HEADLESS: a CLI opened, worked
    and closed where nobody could watch it, interrupt it or answer it. That is the thing this
    app exists to replace, so it is gone. Coding work goes to a real session you can see
    (terminal.start_on_task); a reply is two sentences and belongs to the main AI, which
    writes it here in under a second and parks it for approval."""
    return draft_for_review(store, task_id, review_id, llm, resolution)


def draft_for_message(store, m: dict, review_id: int, llm=None) -> str:
    """A reply for a message with NO task behind it - chatter that just deserves an answer.
    Same voice, same rules, same channel-awareness; the context is the message itself."""
    from .llm import build_llm
    from .ingest import notes_for
    from .triage import strip_boilerplate
    llm = llm or build_llm(store)
    if not llm: raise RuntimeError('no AI connector is set up to write replies')
    soul = store.doc('soul') or ''
    owner = (soul.split('You work for **')[1].split('**')[0] if 'You work for **' in soul else 'the owner')
    chat = str(m.get('Channel') or '').lower() in CHAT_CHANNELS
    from .learn import injectable
    lrn = injectable(store.doc('learned') or '')
    sty = style_doc(store)
    system = (SYSTEM.format(owner=owner) + BREVITY + (CHAT if chat else EMAIL) + '\n' + NOT_YET
              # every block below describes YOU. They are written in the third person because
              # the same documents serve agents working FOR the owner - said once, here, so the
              # model does not read its own biography as notes about somebody else.
              + (f"\n\nYOUR OWN document - your voice, your rules, your responsibilities. Where it "
                 f"says you work for {owner}, it is addressing an agent on other tasks; on this "
                 f"one it is describing you:\n{soul[:4000]}" if soul else '')
              + (f'\n\nYour own style, distilled from mail you have actually sent - write like '
                 f'this:\n{sty[:2500]}' if sty else '')
              + (f'\n\nYour learned profile - how you write and work, distilled from your own '
                 f'verdicts on past drafts:\n{lrn[:2000]}' if lrn else ''))
    notes = notes_for(store, {'from_email': m.get('FromEmail')})
    if notes:
        system += '\n\nYour own standing notes:\n' + '\n'.join(f'- {n}' for n in notes[:20])[:1500]
    user = (f"Subject: {m.get('Subject') or ''}\nFrom: {m.get('FromName')} <{m.get('FromEmail')}>\n\n"
            f"{strip_boilerplate(str(m.get('BodyText') or ''))[:4000]}")
    out = (llm(system, user, max_tokens=REPLY_TOKENS) or '').strip()
    if not out: raise RuntimeError('the AI returned an empty reply')
    out = (strip_signoff(out) or out) if chat else out
    store.update_review_draft(review_id, out, None)
    return out
