"""Intent triage: is a message a TASK (something to DO), a quick REPLY_ONLY question, or
FYI noise? Heuristic by default; pass any `llm(system, user) -> str-json` callable to
upgrade (provider-agnostic - wire your own OpenAI/Anthropic/local call in config).
"""
import json, re
import re as _re

# What each verdict COSTS is part of the judgement, so it is in the prompt: a task starts a
# real agent in a real repo; a reply is one cheap draft the owner approves. Defaulting to
# "task" turned questions into background work nobody asked for.
INTENT_SYSTEM = (
    'Classify one inbound work message. Answer JSON only: '
    '{"intent": "task|reply_only|fyi", "why": "<8 words max>"}.\n'
    'task = someone must DO something beyond writing back: change a system, fix or build something, '
    'produce or chase something. This starts a coding agent on a repository, so choose it only when '
    'work has to happen.\n'
    'reply_only = answering IS the work - a question, a status check, a scheduling note, anything you '
    'can settle in a message, even one needing a quick lookup. The reply is drafted for the owner to '
    'approve, so nothing is dropped by choosing this.\n'
    'fyi = informational only: automated notices, reports, newsletters, thanks, threads the owner is '
    'merely copied on.\n'
    'Torn between task and reply_only? Choose reply_only. The owner can turn a reply into a task in '
    'one click, and a wrongly-started agent costs far more than a draft.')

_ASK = re.compile(r'\b(can you|could you|are you|do you|would you|let me know|please confirm|any update)\b', re.I)
_ACT = re.compile(r'\b(please (add|send|update|fix|remove|create|set up)|need you to|action required|please complete)\b', re.I)
_FYI = re.compile(r'\b(fyi|for your (records|reference)|no action (needed|required)|auto-?generated|this is an automated|do not reply)\b', re.I)


def heuristic_intent(msg: dict) -> dict:
    body = (msg.get('body') or '').strip()
    low = f"{msg.get('subject') or ''} {body[:600]}"
    if _FYI.search(low) and not body.rstrip().endswith('?'): return {'intent': 'fyi', 'why': 'automated/informational'}
    if _ACT.search(low): return {'intent': 'task', 'why': 'asks the owner to do something'}
    if body.rstrip().endswith('?') or _ASK.search(low): return {'intent': 'reply_only', 'why': 'question needing only an answer'}
    return {'intent': 'task', 'why': 'default'}


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


def classify_intent(msg: dict, llm=None, soul: str = None, notes: list = None, images=None,
                    learned: str = None) -> dict:
    """`notes` are the owner's standing memory notes that apply to this sender - the verdicts
    they've already given ("this kind of mail isn't ours"). Injecting them here is what makes
    'Not our task' stick: the next message like it is classified with that lesson in hand.

    `images` are the attached screenshots, for a model that can see them. Half of "see below"
    mail says nothing in its body - triage read three words and filed it as informational."""
    if llm:
        try:
            system = INTENT_SYSTEM + (f"\n\nOperator's document:\n{soul[:2500]}" if soul else '')
            # `learned` is LEARNED.md's active sections: the profile distilled from the owner's
            # past verdicts. It refines the operator's document; explicit notes still outrank it.
            if learned:
                system += ("\n\nLearned profile - patterns distilled from the owner's past verdicts "
                           '(the document above outranks it where they disagree):\n' + learned[:1500])
            if notes:
                system += ('\n\nStanding notes from the owner - these are VERDICTS they already gave on '
                           'mail like this, and they outrank your own reading:\n'
                           + '\n'.join(f'- {n}' for n in notes[:20])[:2000])
            user = json.dumps({'from': msg.get('from_email'), 'subject': msg.get('subject'),
                               'body': strip_boilerplate(str(msg.get('body') or ''))[:1500]})
            if images:
                system += ('\n\nImages from the message are attached. They are part of the ask - a '
                           'screenshot of the error IS the request. Read them before deciding.')
            out = llm(system, user, images=images) if images else llm(system, user)
            j = json.loads(re.sub(r'^```(json)?|```$', '', out.strip(), flags=re.M))
            if j.get('intent') in ('task', 'reply_only', 'fyi'):
                return {'intent': j['intent'], 'why': str(j.get('why') or '')[:200]}
        except Exception:
            pass
    return heuristic_intent(msg)
