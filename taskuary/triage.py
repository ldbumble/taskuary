"""Intent triage: is a message a TASK (something to DO), a quick REPLY_ONLY question, or
FYI noise? Heuristic by default; pass any `llm(system, user) -> str-json` callable to
upgrade (provider-agnostic - wire your own OpenAI/Anthropic/local call in config).
"""
import json, re

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


def classify_intent(msg: dict, llm=None, soul: str = None, notes: list = None, images=None) -> dict:
    """`notes` are the owner's standing memory notes that apply to this sender - the verdicts
    they've already given ("this kind of mail isn't ours"). Injecting them here is what makes
    'Not our task' stick: the next message like it is classified with that lesson in hand.

    `images` are the attached screenshots, for a model that can see them. Half of "see below"
    mail says nothing in its body - triage read three words and filed it as informational."""
    if llm:
        try:
            system = INTENT_SYSTEM + (f"\n\nOperator's document:\n{soul[:2500]}" if soul else '')
            if notes:
                system += ('\n\nStanding notes from the owner - these are VERDICTS they already gave on '
                           'mail like this, and they outrank your own reading:\n'
                           + '\n'.join(f'- {n}' for n in notes[:20])[:2000])
            user = json.dumps({'from': msg.get('from_email'), 'subject': msg.get('subject'),
                               'body': str(msg.get('body') or '')[:1500]})
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
