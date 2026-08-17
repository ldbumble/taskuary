"""Intent triage: is a message a TASK (something to DO), a quick REPLY_ONLY question, or
FYI noise? Heuristic by default; pass any `llm(system, user) -> str-json` callable to
upgrade (provider-agnostic - wire your own OpenAI/Anthropic/local call in config).
"""
import json, re

INTENT_SYSTEM = ('Classify one inbound work message. Answer JSON only: '
                 '{"intent": "task|reply_only|fyi", "why": "<8 words max>"}. '
                 'task = the owner must DO something beyond replying. '
                 'reply_only = it just needs an answer, even one requiring a quick lookup. '
                 'fyi = informational only - nothing to do, nothing to answer.')

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


def classify_intent(msg: dict, llm=None, soul: str = None) -> dict:
    if llm:
        try:
            system = INTENT_SYSTEM + (f"\n\nOperator's document:\n{soul[:2500]}" if soul else '')
            user = json.dumps({'from': msg.get('from_email'), 'subject': msg.get('subject'),
                               'body': str(msg.get('body') or '')[:1500]})
            j = json.loads(re.sub(r'^```(json)?|```$', '', llm(system, user).strip(), flags=re.M))
            if j.get('intent') in ('task', 'reply_only', 'fyi'):
                return {'intent': j['intent'], 'why': str(j.get('why') or '')[:200]}
        except Exception:
            pass
    return heuristic_intent(msg)
