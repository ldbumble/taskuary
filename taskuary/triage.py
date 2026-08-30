"""Intent triage: is a message a TASK (something to DO), a quick REPLY_ONLY question, or
FYI noise? Heuristic by default; pass any `llm(system, user) -> str-json` callable to
upgrade (provider-agnostic - wire your own OpenAI/Anthropic/local call in config).
"""
import json, re
import re as _re

# What each verdict COSTS is part of the judgement, so it is in the prompt: a task starts a
# real agent in a real repo; a reply is one cheap draft the owner approves. Defaulting to
# "task" turned questions into background work nobody asked for.
# This text also ships as templates/triage.md - the editable TRIAGE.md doc that overrides it
# (see classify_intent's `system` param). It stays here too as the fallback for a blanked doc.
INTENT_SYSTEM = (
    'Classify one inbound work message. Answer JSON only: '
    '{"intent": "task|reply_only|fyi", "kind": "coding|general", "why": "<one concrete sentence: what you saw in the message '
    'and which rule it hit - the owner reads this to judge the verdict, 25 words max>"}.\n'
    'Almost everything that asks for anything is a task, and every task goes to the coding agent automatically: it '
    'does what can be done from a keyboard or says "nothing to do here" and stops - a cheap ending. kind is a label, '
    'coding by default; say general ONLY when the owner\'s past verdicts say this kind of work is not for the agent, '
    'or it plainly cannot be done from a computer.\n'
    'task = someone must DO something beyond writing back: change a system, fix or build something, produce or '
    'chase something, look something up that takes more than a sentence.\n'
    'reply_only = the answer is a sentence the owner already knows - "what time are you free", "are you around '
    'Tuesday", "which file did you mean". Nothing to look up, change or produce; a question with a lookup or a fix '
    'behind it is a task. The reply is drafted for the owner to approve.\n'
    'fyi = informational only: automated notices, reports, newsletters, thanks, threads the owner is '
    'merely copied on.\n'
    'Chat is not mail (no subject, no recipient lines) but an ask in chat is still an ask - a task for the agent. '
    'reply_only is for what a sentence settles with nothing to do behind it; fyi is thanks, status, and threads '
    'between other people where the owner is neither asked nor named.\n'
    'addressed_to_you and recipients are SIGNALS to weigh, never rules to obey. "to" = the mail was aimed at the owner; "cc" = they were copied, which OFTEN means somebody else owns the work; "not named" = it arrived through a group alias or a shared mailbox the owner is responsible for - their own address is not on it, and the people on the To line own the matter. But a cc can absolutely be theirs: one that names them, asks them something directly, or that only they can answer is their work, and being on the cc line counts for nothing against that. recipients counts everyone on the mail - a note to thirty people is more likely a broadcast than a job. Weigh these with everything else in the message; never decide on them alone. Both fields are absent on channels with no recipient lines.\n'
    'others_replied names people - other than you and the sender - who have already SENT a message on '
    'this thread, and last_on_thread is whoever spoke most recently. Somebody else answering is the '
    'strongest everyday sign that a request is not waiting on you: when a colleague has replied and the '
    'ask is not aimed at you specifically, prefer fyi. Weigh it, do not obey it - a question that names '
    'you, or that only you can answer, is still yours however many colleagues are on the thread. Absent '
    'fields mean nobody else has spoken, which is not evidence either way.\n'
    'Torn between task and reply_only? Choose task. Torn between task and fyi? Choose task unless the mail plainly asks '
    'nobody for anything. The agent looks and says "nothing to do here" if there is nothing to do; a job that only '
    'got a drafted reply is a job nobody did.')

def addressed_to_you(msg: dict, mine=()) -> str:
    """'to', 'cc', 'not named', or '' when the channel carries no recipient lines at all (chat) -
    the one fact that separates "this is mine" from "I am watching someone else's thread", and it
    was never collected, so no classifier could ever weigh it. The ADDRESSES are deliberately not
    returned: what reaches a prompt is the relationship, never the mailbox (0.2.1, no addresses in
    prompts)."""
    # EVERY address that is the owner, not just the mailbox this copy landed in. Mail to a
    # shared or journal mailbox is still addressed to them when their own address is on the Cc
    # line - and comparing only the arrival mailbox called that 'not named', which is exactly
    # backwards for the case the whole signal exists to catch.
    # `mine` is the owner's OWN address(es) (ingest.own_addresses). When the caller knows them,
    # the mailbox this copy arrived in is NOT added: a shared or journal mailbox Taskuary polls
    # receives everybody's mail, and counting it as "me" made every message to it read as
    # aimed at the owner (2026-08-27: a refund question to devteam-logs@ came out as 'to').
    # With no `mine` at all, the arrival mailbox is the only "me" there is.
    me = {str(a).lower() for a in mine if a} or {a for a in {(msg.get('source_name') or '').strip().lower()} if a}
    to = {str(a).lower() for a in (msg.get('to') or [])}
    cc = {str(a).lower() for a in (msg.get('cc') or [])}
    if not me or not (to or cc): return ''
    return 'to' if me & to else 'cc' if me & cc else 'not named'


_ASK = re.compile(r'\b(can you|could you|are you|do you|would you|let me know|please confirm|any update)\b', re.I)
_ACT = re.compile(r'\b(please (add|send|update|fix|remove|create|set up)|need you to|action required|please complete)\b', re.I)
_FYI = re.compile(r'\b(fyi|for your (records|reference)|no action (needed|required)|auto-?generated|this is an automated|do not reply)\b', re.I)


def heuristic_intent(msg: dict, mine=()) -> dict:
    body = (msg.get('body') or '').strip()
    low = f"{msg.get('subject') or ''} {body[:600]}"
    if _FYI.search(low) and not body.rstrip().endswith('?'):
        return {'intent': 'fyi', 'why': 'carries automated/no-action markers and asks no question (keyword heuristic)'}
    if _ACT.search(low): return {'intent': 'task', 'why': 'explicitly asks for something to be done (keyword heuristic)'}
    if body.rstrip().endswith('?') or _ASK.search(low):
        return {'intent': 'reply_only', 'why': 'reads as a question an answer settles (keyword heuristic)'}
    # A cc used to be FILED here, by keyword, before any model saw it - which is the one thing
    # the To/Cc signal must not do. Plenty of cc'd mail is genuinely yours: the sender put the
    # owner in cc and addressed them in the body, or they are the only person who can answer.
    # Deciding that from the header alone is a guess wearing a rule's clothing, so the fields
    # are handed to the classifier as evidence and the classifier decides. It costs one AI call
    # on quiet cc mail that this used to settle for free; being right is worth more.
    return {'intent': 'task', 'why': 'no fyi markers and no plain question - assumed real work (keyword heuristic, no AI read this)'}


# ── the message, minus the wrapper ──────────────────────────────────────────────────────
# Corporate mail arrives half signature: name, title, phone block, an inspirational quote,
# and a confidentiality NOTICE longer than the ask. All of it rode into every AI call - the
# triage, the seeded session, the reply drafts - spending context on boilerplate. The STORED
# body stays whole (the panel shows the real mail); only what is fed to an AI is trimmed,
# and always conservatively: when in doubt, keep.
_LEGAL = _re.compile(r'^\s*(NOTICE|DISCLAIMER|CONFIDENTIALITY( NOTICE)?|LEGAL NOTICE)[:\s]'
                     r'|this (e-?mail|message|communication)[^.]{0,120}(confidential|privileged|intended (solely|only))'
                     r'|if you (are not the intended|have received this[^.]{0,40}in error)'
                     r'|unauthorized (use|review|disclosure|distribution)', _re.I)
_VALEDICTION = _re.compile(r'^\s*(thank(s| you)|best( regards| wishes)?|kind(est)? regards|regards|'
                           r'sincerely|respectfully|warm(ly| regards)?|cheers|v/?r)\s*[,!.]*\s*$', _re.I)
_CONTACT = _re.compile(r'^\s*(phone|tel|mobile|cell|fax|office|direct|email|e-?mail|web|www\.|address)'
                       r'|^\s*\+?[\d(][\d\s().x-]{6,}$'
                       r'|^[^@\s]+@[^@\s]+\.[a-z]{2,}\s*$', _re.I)
_KEEP_MIN = 30          # never trim a message down past this - when in doubt, keep
NL = chr(10)


def strip_boilerplate(text: str) -> str:
    """The words the sender actually typed: the legal footer and the signature block go,
    everything before them stays byte-for-byte."""
    lines = (text or '').splitlines()
    # 1. the legal footer: from the first legalese line to the end
    for i, l in enumerate(lines):
        if _LEGAL.search(l) and len(NL.join(lines[:i]).strip()) >= _KEEP_MIN:
            lines = lines[:i]
            break
    # 2. the signature: a closing valediction in the tail, followed by the name/title/phone block
    tail_from = max(1, len(lines) - 14)
    for i in range(len(lines) - 1, tail_from - 1, -1):
        if _VALEDICTION.match(lines[i]) and len(NL.join(lines[:i]).strip()) >= _KEEP_MIN:
            lines = lines[:i]
            break
    # 3. stray contact lines left at the very end (a block with no valediction above it)
    while lines and (_CONTACT.match(lines[-1]) or not lines[-1].strip()):
        if len(NL.join(lines[:-1]).strip()) < _KEEP_MIN: break
        lines.pop()
    out = NL.join(lines).rstrip()
    return out if out.strip() else (text or '')


_VERDICT_MARK = re.compile(r'\b(NOT OURS|NOT A TASK|NOT A CODING TASK)\b')

def _agreement(notes) -> tuple:
    """(verdict, n) when two or more retrieved notes carry a verdict mark and they all agree;
    () otherwise. The owner's own free-text notes carry no mark and stay advice."""
    marks = [m.group(1) for n in notes for m in [_VERDICT_MARK.search(n or '')] if m]
    return (marks[0], len(marks)) if len(marks) >= 2 and len(set(marks)) == 1 else ()


def classify_intent(msg: dict, llm=None, soul: str = None, notes: list = None, images=None,
                    learned: str = None, system: str = None, notes_left: int = 0, mine=(),
                    thread: dict = None) -> dict:
    """`notes` are the owner's past verdicts that may bear on this message - each one dated,
    with the sender and subject it was given on - selected by sender and topic overlap
    (ingest.relevant_notes). They are EVIDENCE: the model judges how alike this message is,
    which a keyed rule could not (the same topic can arrive asking something new).

    `images` are the attached screenshots, for a model that can see them. Half of "see below"
    mail says nothing in its body - triage read three words and filed it as informational.

    `thread` is what the messages AROUND this one say - chiefly whether a colleague has already
    replied. Supplied as a signal for the same reason as the To/Cc lines: the code's job is to
    put the fact in front of the model, and how much it counts for is a judgement that belongs
    in TRIAGE.md where the owner can argue with it.

    `system` is TRIAGE.md, the owner-editable classifier instructions - HTML comments are
    stripped (the doc's own how-to-edit note is for the owner, not the model), and a blanked
    doc falls back to the shipped default. An edit that breaks the JSON contract degrades to
    the keyword heuristics, never to a crash."""
    if llm:
        try:
            base = re.sub(r'<!--.*?-->', '', system or '', flags=re.S).strip() or INTENT_SYSTEM
            system = base + (f"\n\nOperator's document:\n{soul[:2500]}" if soul else '')
            # `learned` is LEARNED.md's active sections: the profile distilled from the owner's
            # past verdicts. It refines the operator's document; explicit notes still outrank it.
            if learned:
                system += ("\n\nLearned profile - patterns distilled from the owner's past verdicts "
                           '(the document above outranks it where they disagree):\n' + learned[:1500])
            if notes:
                # already ranked and budgeted by ingest.relevant_notes - re-cutting here is what
                # used to throw away whichever verdicts happened to sit past the 2000th character.
                # When EVERY retrieved verdict says the same thing, that is not a hint to weigh - a
                # refund thread with two NOT OURS on file still opened a reply task while the model
                # "judged likeness". No topic is named here: it counts the verdicts it was handed.
                agree = _agreement(notes)
                if agree: system += (f'\n\nSETTLED BY YOUR OWNER: all {agree[1]} past verdicts on this sender or topic say '
                                     f'{agree[0]}. Answer fyi - no exceptions. A question in the message does not reopen '
                                     'it: mail on a settled topic always asks somebody something, and that somebody is '
                                     'whoever does this work - not the owner, who is copied on it. The owner reads the '
                                     'timeline and will say so if a thread has become theirs.')
                system += ('\n\nEVIDENCE - verdicts the owner gave on earlier mail that looks related '
                           '(pulled by sender and by topic; each names the sender and subject it was given on). '
                           'Judge how alike THIS message really is: the same sender asking the same kind of '
                           'thing makes a verdict binding, a shared word does not, and a thread that is now '
                           'asking the owner something new is new. Where a verdict plainly fits, follow it:\n'
                           + '\n'.join(f'- {n}' for n in notes)
                           + (f'\n({notes_left} further note(s) also apply to this sender but did not fit. '
                              'Say so in your reason if the verdict feels underdetermined - do not claim '
                              'nothing is on file.)' if notes_left else ''))
            # No rule about the To/Cc lines is appended here any more. The code's job is to
            # SUPPLY the signal; how much it counts for is a judgement, and judgement belongs in
            # TRIAGE.md where the owner can argue with it. An untouched document tracks the
            # shipped template, so the paragraph reaches existing installs that way.
            how = addressed_to_you(msg, mine)
            user = json.dumps({'from': msg.get('from_email'), 'subject': msg.get('subject'),
                               **({'addressed_to_you': how,
                                   'recipients': len(msg.get('to') or []) + len(msg.get('cc') or [])} if how else {}),
                               **(thread or {}),
                               'body': strip_boilerplate(str(msg.get('body') or ''))[:1500]})
            if images:
                system += ('\n\nImages from the message are attached. They are part of the ask - a '
                           'screenshot of the error IS the request. Read them before deciding.')
            out = llm(system, user, images=images) if images else llm(system, user)
            j = json.loads(re.sub(r'^```(json)?|```$', '', out.strip(), flags=re.M))
            if j.get('intent') in ('task', 'reply_only', 'fyi'):
                # `kind` is the model's SECOND verdict - coding or general - and only means anything
                # on a task. It used to be a regex over the body (routing.draft_task_fields), which
                # is how a Teams line about someone's job scope opened a coding session; the model
                # has read the whole message and TRIAGE.md's definition, so its word wins when given.
                out = {'intent': j['intent'], 'why': str(j.get('why') or '')[:240]}
                if j['intent'] == 'task' and j.get('kind') in ('coding', 'general'): out['kind'] = j['kind']
                return out
        except Exception:
            pass
    # An LLM was supplied, answered, and the answer was not usable (bad JSON, an intent outside
    # the contract). That is NOT "no AI configured": heuristic_intent's last branch assumes real
    # work and reads none of the owner's standing notes, so a garbled answer opened a task the
    # owner had already refused - repeatedly, since every retry garbled the same way. Say the
    # verdict is degraded and let the caller file instead of guessing.
    out = heuristic_intent(msg, mine)
    return {**out, 'degraded': True} if llm else out
