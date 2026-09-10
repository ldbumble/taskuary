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
    # "I can't suggest times by email alone; the owner will need to handle scheduling directly." -
    # signed by the owner. Third person about the sender, first person about a tool's limitations, over
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
EMAIL = ('This is EMAIL. Use the greeting, sign-off, and exact recurring signature STYLE.md '
         'specifies; include the signature once, at the end. If STYLE.md has no learned signature, '
         'use the sign-off SOUL.md specifies. Nothing else ceremonial.')

# This line used to say "the owner will turn it into a task", and the model answered in kind:
# a sentence about what someone ELSE would have to do. Say it the way a person would.
NOT_YET = ('If the request cannot be answered by a reply alone - it needs work doing - say in one '
           'line that you will pick it up, and stop. Not who will do it, not how, and never that '
           'you are unable to.')
# the coder has already closed the thread: this reply reports an outcome, never promises one
# the assistant's chase: you wrote last, heard nothing, and are nudging - never a reproach
NUDGE = ('This reply is a FOLLOW-UP: you wrote last on this thread, asked for or promised something, and have '
         'heard nothing since. Nudge in one or two sentences: restate in a line what you need or are waiting on, '
         'make it easy to answer, and assume they are busy rather than ignoring you. No reproach, no "just '
         'checking in", no recap of the whole thread.\n')
DONE = ('The work this thread asked for is FINISHED - the complete result below says what was done. '
        'Answer EVERY distinct question, request, and issue in the sender\'s thread that the result '
        'addresses. Check them one by one before writing: never omit an item merely to make the reply '
        'short. When there are several items, a compact plain-text numbered or bulleted list is clearer '
        'than squeezing them into a sentence. Claim nothing the result does not support; if an item could '
        'NOT be done, say that and why. Never mention agents, tasks, tickets, '
        'repositories or tooling: YOU did this.\n'
        # the report is written for the owner's records and reads like it. Copied straight out, it
        # went to a vendor's mailer as "not an engineering or repo issue, so I closed it as FYI" -
        # a sentence about our own filing, addressed to somebody who filed nothing (TQ-0252).
        'The report is an INTERNAL record in internal words: it may call the message an FYI, a '
        'ticket, a repo issue, something closed, filed or triaged. NONE of that goes to the sender - '
        'they did not file anything and none of those words mean anything to them. Write only the '
        'part that is news to THEM, about THEIR message, in the words they used. If the honest answer '
        'is that nothing was needed, that is a sentence about their thing, never about our handling '
        'of it.')

CHAT_CHANNELS = ('teams', 'slack', 'telegram', 'whatsapp', 'imessage')
REPLY_TOKENS = 300          # ordinary reply-only mail should remain quick and short
COMPLETE_REPLY_TOKENS = 1200  # completed multi-item work must have room to answer every item

# SOUL.md tells the model how to sign off, and it obeys - in a chat window too, where it reads
# like a form letter. Belt and braces: the prompt says not to, and this takes it off anyway.
_SIGNOFF = re.compile(r'^(best|thanks|thank you|regards|cheers|kind regards|best regards|sincerely)[\s,!.]*$', re.I)
_COMMENT = re.compile(r'<!--.*?-->', re.S)
_TEMPLATE_LINES = re.compile(r'^.*(not generated yet|Write your own rules here).*$', re.M)

WRITING_SOURCE = 'writing'     # a memory note that is an explicit instruction about HOW to write (PW-060)
OWNER_NOTES = '## Owner notes'


def writing_notes(store, budget: int = 1500) -> list:
    """The standing notes a reply may read: explicit writing instructions and nothing else (PW-060). Triage's
    verdicts - not a task, not ours, who to defer to - are how mail is ROUTED; they used to ride into every
    draft as if they were style."""
    out, used = [], 0
    for n in store.list_memories():
        if str(n.get('Source') or '') != WRITING_SOURCE: continue
        note = ' '.join(str(n.get('Note') or '').split())
        if not note or used + len(note) > budget: continue
        out.append(note); used += len(note)
    return out


def style_feedback(store, note: str, actor: str = 'owner') -> bool:
    """An edited draft's note is a writing instruction: it goes into STYLE.md under Owner notes (outside the
    generated block, so a regenerate keeps it), not into triage's LEARNED.md (PW-061)."""
    line = ' '.join(str(note or '').split())
    if not line: return False
    from datetime import datetime
    doc = store.get_doc('style') or ''
    entry = f'- {datetime.now().strftime("%Y-%m-%d")}: {line[:400]}'
    if OWNER_NOTES in doc:
        head, rest = doc.split(OWNER_NOTES, 1)
        # the section runs to the next heading; the new line joins its end
        parts = rest.split('\n## ', 1)
        body = parts[0].rstrip('\n') + '\n' + entry + '\n'
        doc = head + OWNER_NOTES + body + ('\n## ' + parts[1] if len(parts) > 1 else '')
    else:
        doc = doc.rstrip('\n') + f'\n\n{OWNER_NOTES}\n<!-- what you told the drafter after editing its replies; yours to prune -->\n{entry}\n'
    store.save_doc('style', doc, actor)
    store.audit('doc', 0, 'style_feedback', actor, detail={'note': line[:200]})
    return True


# a quoted sign-off may span lines (Best, / name / company); an unquoted one is the rest of its line
_SIGN_QUOTED = re.compile(r'(?:sign[- ]?off|signature)\s*:\s*"([^"]+)"', re.I | re.S)
_SIGN_LINE = re.compile(r'^\s*-?\s*(?:sign[- ]?off|signature)\s*:\s*(.+?)\s*$', re.I | re.M)


def signature_for(store) -> str:
    """The owner's email signature: the `email_signature` setting when set, else the `Sign off:` / `Signature:`
    line in STYLE.md (quotes stripped, literal newlines honoured). '' when neither says anything (PW-065)."""
    sig = str(store.get_settings().get('email_signature') or '').strip()
    if sig: return sig.replace('\\n', '\n')
    doc = store.doc('style') or ''
    q = _SIGN_QUOTED.search(doc)
    if q: return q.group(1).strip().replace('\\n', '\n')
    m = _SIGN_LINE.search(doc)
    if not m: return ''
    return m.group(1).strip().strip('"\'').replace('\\n', '\n').strip()


def with_signature(text: str, sig: str) -> str:
    """Append the signature once - not when the text already ends with it (the model signed, or the owner did)."""
    text = str(text or '').rstrip()
    if not sig or not text: return text
    first = sig.strip().splitlines()[0].strip().lower()
    tail = text[-max(400, len(sig) + 40):].lower()
    if sig.strip().lower() in tail or (first and first in tail and sig.strip().splitlines()[-1].strip().lower() in tail): return text
    return text + '\n\n' + sig.strip()


def style_doc(store) -> str:
    """STYLE.md as prompts read it: comments and template placeholders stripped, owner tokens
    rendered - and empty until the doc says something REAL (headers alone are not a style),
    so the untouched template never rides into a prompt as noise. The doc is the owner's
    voice distilled from their own sent mail (Docs → STYLE.md → Generate from history)."""
    t = _TEMPLATE_LINES.sub('', _COMMENT.sub('', store.doc('style') or ''))
    meat = '\n'.join(l for l in t.splitlines() if l.strip() and not l.strip().startswith('#'))
    return t.strip() if len(meat) > 40 else ''

def history_block(store, m: dict) -> str:
    """What this mailbox already knows about the sender and the topic BEYOND this thread - their
    other recent mail, what you last wrote them, the same matter elsewhere, open tasks. The draft
    used to see six thread messages and nothing else, and answered last week's question as if it
    had never been asked (counsel.dossier; the thread itself is excluded - it is in the prompt)."""
    from .counsel import dossier
    try:
        dos = dossier(store, {'from_email': m.get('FromEmail'), 'from_name': m.get('FromName'), 'subject': m.get('Subject'),
                              'conversation_id': m.get('ConversationId')}, exclude_mid=m.get('MessageId'), skip_conv=True)
    except Exception as e:
        logger.debug(f'history block skipped: {e}'); return ''
    return ('\n\nWHAT YOU ALREADY KNOW - your recent history with this sender and this topic, outside this '
            'thread. Use it: never contradict what you already told them, never ask what they already answered, '
            'and mention an open matter only when it bears on this reply.\n' + dos[:2500]) if dos else ''


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


def draft_reply(store, task_id: int, llm=None, resolution: str = None, nudge: str = None) -> str:
    """The reply this task needs, as text. Uses the owner's own brain (the AI connector, or
    whichever brain `triage_ai` names), the standing memory notes, and the thread itself."""
    from .llm import build_llm
    from .ingest import notes_for
    llm = llm or build_llm(store)
    if not llm: raise RuntimeError('no AI connector is set up to write replies')
    t = store.get_task(task_id) or {}
    # Redraft/open-reply callers do not pass the completed result again. Recover the durable final
    # response or transcript here so a second draft cannot fall back to a generic promise.
    if resolution is None:
        resolution = resolution_of(store, task_id)
    msgs = [m for m in store.list_messages(task_id) if m.get('Status') != 'context']
    if not msgs: raise RuntimeError('nothing to reply to on this task')
    last = msgs[-1]
    soul = store.doc('soul') or ''
    owner = (soul.split('You work for **')[1].split('**')[0] if 'You work for **' in soul else 'the owner')
    # the mail's own words rank the notes, so pass them: a note quoting this subject is the
    # one most likely to change how the reply should read
    # only explicit writing instructions ride into a reply (PW-060); the routing verdicts stay with triage
    notes = writing_notes(store)
    chat = str(last.get('Channel') or '').lower() in CHAT_CHANNELS
    sty = style_doc(store)
    # The 60-word rule is useful for ordinary mail, but destructive for a completed eight-part
    # request. DONE supplies its own completeness/shape rules, so do not put BREVITY in conflict.
    length_rule = '' if resolution else BREVITY
    system = (SYSTEM.format(owner=owner) + length_rule + (CHAT if chat else EMAIL) + '\n'
              + (NUDGE if nudge else DONE if resolution else NOT_YET)
              # every block below describes YOU. They are written in the third person because
              # the same documents serve agents working FOR the owner - said once, here, so the
              # model does not read its own biography as notes about somebody else.
              + (f"\n\nYOUR OWN document - your voice, your rules, your responsibilities. Where it "
                 f"says you work for {owner}, it is addressing an agent on other tasks; on this "
                 f"one it is describing you:\n{soul[:4000]}" if soul else '')
              + (f'\n\nYour own style, distilled from mail you have actually sent - write like '
                 f'this:\n{sty[:2500]}' if sty else ''))
    # LEARNED.md is triage's document (PW-058): what deserves a task is not how to write a reply
    if notes: system += '\n\nYour own writing instructions:\n' + '\n'.join(f'- {n}' for n in notes)
    from .triage import strip_boilerplate
    # the writer reads the same assembled conversation triage reads (PW-054): the whole chain, history
    # included, cleaned and de-quoted under one budget, with the cut said out loud - not the last six
    # messages chopped at 4,000 characters each and nothing said about the rest
    from .ingest import exchange_lines
    lines = exchange_lines(store, {'conversation_id': last.get('ConversationId'), 'subject': last.get('Subject'), 'sent_at': None})
    thread = '\n\n'.join(lines) if lines else f"--- {last.get('FromName') or last.get('FromEmail')} · {last.get('SentAt')} · {last.get('Channel')}\n{strip_boilerplate(str(last.get('BodyText') or ''))[:4000]}"
    user = f"Subject: {last.get('Subject') or t.get('Title') or ''}\nFrom: {last.get('FromName')} <{last.get('FromEmail')}>\n\n{thread}"
    if resolution: user += f'\n\n--- WHAT WAS DONE (your source of truth; the sender has not seen it)\n{resolution}'
    if nudge: user += f'\n\n--- WHY YOU ARE WRITING AGAIN (the assistant\'s note to you, not for the reader)\n{nudge}'
    from . import calendar as cal
    calendar = cal.context_for(store, f"{last.get('Subject') or ''} {thread}")     # "Tuesday at 1 works" only if Tuesday at 1 is free
    from . import knowledge
    system += calendar + history_block(store, last) + knowledge.block(store, f"{last.get('Subject') or ''} {thread}")
    if calendar:   # said on the task, so the Review row can be trusted on what the draft knew
        store.add_comment(task_id, 'responder', 'agent', 'Checked your calendar before drafting'
                          + (' - it could not be read, so the draft does not promise a time.' if 'COULD NOT READ' in calendar else '.'))
    out = (llm(system, user, max_tokens=COMPLETE_REPLY_TOKENS if resolution else REPLY_TOKENS) or '').strip()
    if not out: raise RuntimeError('the AI returned an empty reply')
    return (strip_signoff(out) or out) if chat else out    # never strip a reply down to nothing


def draft_for_review(store, task_id: int, review_id: int, llm=None, resolution: str = None, nudge: str = None) -> str:
    """Write the draft and park it on its review, ready for approve / edit / no-reply."""
    # what this wording is ABOUT is fixed before the model runs (PW-048): a line that lands during
    # generation was not in its input, so it is never labelled as seen - the draft is marked behind instead
    from . import operations
    saw = store.last_inbound_on_task(task_id)
    revision = operations.message_revision(store, task_id)
    text = draft_reply(store, task_id, llm, resolution, nudge)
    if saw and str(saw.get('Channel') or '').lower() == 'email':
        # the signature rides in the draft the owner reviews, once (PW-065); the recipients it will go to are pinned
        # with it, Reply all by default (PW-063/064) - an envelope the owner already set is kept
        text = with_signature(text, signature_for(store))
        from . import outbound as _ob
        if not store.review_envelope(review_id):
            env = _ob.reply_envelope(store, saw)
            if env: store.set_review_envelope(review_id, env)
    store.update_review_draft(review_id, text, None)
    if saw: store.pin_review_context(review_id, saw['MessageId'], revision)
    if operations.message_revision(store, task_id) != revision:
        store.mark_review_stale(review_id)
        logger.info(f'draft for task {task_id} is behind the thread already - a line landed while it was written')
    logger.info(f'drafted reply for task {task_id} ({len(text)} chars)')
    return text


def resolution_of(store, task_id: int):
    """The complete durable work result, if a coding session closed this task.

    Prefer the exact final agent response saved in the long-form artifact. Older sessions do not
    have that section, so their filed transcript is the fallback; only legacy records with neither
    retain the compact CODER REPORT. This is also what makes Review -> Redraft lossless.
    """
    report = next((c['Body'] for c in reversed(store.list_comments(task_id))
                   if str(c.get('Body') or '').startswith('CODER REPORT')), None)
    if not report:
        return None
    try:
        from . import session_artifacts
        # the NEWEST session: an agent that ran twice leaves two, and the first one's transcript is
        # what it knew before it corrected itself (the owner, 2026-09-03: "it was run twice")
        sessions = [a for a in store.list_task_artifacts(task_id) if a.get('Kind') == 'coding_session']
        artifact = max(sessions, key=lambda a: (str(a.get('CreatedAt') or ''), a.get('ArtifactId') or 0), default=None)
        path = session_artifacts.confined((artifact or {}).get('Path'))
        if path:
            body = path.read_text(encoding='utf-8')
            marker, end = '## Final agent response\n\n', '\n\n## Full session transcript'
            if marker in body:
                final = body.split(marker, 1)[1].split(end, 1)[0].strip()
                if final:
                    return 'COMPLETE FINAL RESPONSE FROM THE WORK SESSION:\n' + final
    except Exception as e:
        logger.debug(f'could not recover final response artifact for task {task_id}: {e}')
    transcript = store.last_transcript(task_id) or {}
    if str(transcript.get('Text') or '').strip():
        return ('COMPLETE WORK SESSION TRANSCRIPT (the final response is near the end):\n'
                + str(transcript['Text']).strip())
    return report


def write_draft(store, task_id: int, review_id: int, resolution: str = None, actor: str = 'system', llm=None, nudge: str = None) -> str:
    """The one door every reply comes through - and there is only one road behind it now.

    An agent named `responder` used to take this over and run HEADLESS: a CLI opened, worked
    and closed where nobody could watch it, interrupt it or answer it. That is the thing this
    app exists to replace, so it is gone. Coding work goes to a real session you can see
    (terminal.start_on_task); a reply is two sentences and belongs to the main AI, which
    writes it here in under a second and parks it for approval."""
    return draft_for_review(store, task_id, review_id, llm, resolution, nudge)


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
    sty = style_doc(store)
    system = (SYSTEM.format(owner=owner) + BREVITY + (CHAT if chat else EMAIL) + '\n' + NOT_YET
              # every block below describes YOU. They are written in the third person because
              # the same documents serve agents working FOR the owner - said once, here, so the
              # model does not read its own biography as notes about somebody else.
              + (f"\n\nYOUR OWN document - your voice, your rules, your responsibilities. Where it "
                 f"says you work for {owner}, it is addressing an agent on other tasks; on this "
                 f"one it is describing you:\n{soul[:4000]}" if soul else '')
              + (f'\n\nYour own style, distilled from mail you have actually sent - write like '
                 f'this:\n{sty[:2500]}' if sty else ''))
    notes = writing_notes(store)                                     # explicit writing instructions only (PW-060)
    if notes: system += '\n\nYour own writing instructions:\n' + '\n'.join(f'- {n}' for n in notes)
    user = (f"Subject: {m.get('Subject') or ''}\nFrom: {m.get('FromName')} <{m.get('FromEmail')}>\n\n"
            f"{strip_boilerplate(str(m.get('BodyText') or ''))[:4000]}")
    from . import calendar as cal
    calendar = cal.context_for(store, f"{m.get('Subject') or ''} {m.get('BodyText') or ''}")
    from . import knowledge
    system += calendar + history_block(store, m) + knowledge.block(store, f"{m.get('Subject') or ''} {m.get('BodyText') or ''}")
    out = (llm(system, user, max_tokens=REPLY_TOKENS) or '').strip()
    if not out: raise RuntimeError('the AI returned an empty reply')
    out = (strip_signoff(out) or out) if chat else with_signature(out, signature_for(store))
    if not chat and not store.review_envelope(review_id):
        from . import outbound as _ob
        env = _ob.reply_envelope(store, m)
        if env: store.set_review_envelope(review_id, env)
    store.update_review_draft(review_id, out, None)
    store.update_review_message(review_id, m['MessageId'])
    return out
