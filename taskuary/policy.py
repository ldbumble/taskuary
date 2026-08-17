"""Deterministic policy engine: what gets auto-answered, drafted, escalated, or ignored.

Pure - policies and the message come in as dicts, a decision comes out - so every rule is
unit-testable offline and the engine is reusable outside this repo. Fixed precedence
(no confidence score can override it, Basware autonomy-gate pattern):
    skip > ignore > escalate > auto_answer > task_only > default_action
'skip' is for senders that flood you (hundreds of automated notifications): the message
is deduped and stored but never appears on the timeline at all - 'ignore' still shows.
Within one action tier, lowest SortOrder wins. 'draft' policies act like targeted
default overrides and are considered in the task_only tier's place when matched.
"""
import re

PRECEDENCE = ('skip', 'ignore', 'escalate', 'auto_answer', 'draft', 'task_only')
_NOREPLY = re.compile(r'(no-?reply|do-?not-?reply|donotreply|notifications?@|automated|mailer-daemon|postmaster)', re.I)


def _split(pattern): return [p.strip().lower() for p in (pattern or '').split('|') if p.strip()]


def matches(policy: dict, msg: dict, known_sender: bool = True) -> bool:
    """Does one policy rule hit this message? msg keys: subject, body, from_email."""
    kind, addr = policy['Kind'], (msg.get('from_email') or '').lower()
    text = f"{msg.get('subject') or ''} {msg.get('body') or ''}".lower()
    if kind == 'keyword': return any(t in text for t in _split(policy.get('Pattern')))
    if kind == 'sender': return addr in _split(policy.get('Pattern'))
    if kind == 'sender_domain': return addr.rsplit('@', 1)[-1] in _split(policy.get('Pattern'))
    if kind == 'noreply': return bool(_NOREPLY.search(addr))
    if kind == 'first_time_sender': return not known_sender
    return False


def evaluate(msg: dict, policies: list, known_sender: bool = True, default_action: str = 'draft') -> dict:
    """Decide the action for a message. Returns {action, rule, reason} - rule/reason name
    the winning policy, or 'default' when nothing matched."""
    hits = [p for p in policies if p.get('Active', 1) and matches(p, msg, known_sender)]
    for action in PRECEDENCE:
        tier = sorted([p for p in hits if p['Action'] == action], key=lambda p: p.get('SortOrder', 100))
        if tier: return {'action': action, 'rule': tier[0]['Name'], 'reason': tier[0]['Reason']}
    return {'action': default_action, 'rule': 'default', 'reason': f'no policy matched - default action ({default_action})'}
