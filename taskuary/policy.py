"""Deterministic policy engine: what is skipped, ignored, or escalated.

Pure - policies and the message come in as dicts, a decision comes out - so every rule is
unit-testable offline and the engine is reusable outside this repo. Fixed precedence
(no confidence score can override it, Basware autonomy-gate pattern):
    skip > ignore > escalate
'skip' is for senders that flood you (hundreds of automated notifications): the message
is deduped and stored but never appears on the timeline at all - 'ignore' still shows.
Within one action tier, lowest SortOrder wins. auto_answer, draft and task_only were accepted here and
honoured nowhere, with a default_action setting beside them (the owner, 2026-09-25: remove them) - a rule
that says one of those now simply matches nothing.
"""
import re

PRECEDENCE = ('skip', 'ignore', 'escalate')
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


# the kinds that judge a message by its envelope alone - no body, no sender history
BODYLESS = ('sender', 'sender_domain', 'noreply')


def dropped_unseen(msg: dict, policies: list) -> bool:
    """Is this message thrown away on its envelope alone? Then its body is never worth downloading.

    'skip' and 'ignore' are the top two tiers, so nothing a later rule says can put the message back
    on the timeline - and a rule that reads the body can only ever agree to drop it harder. A shared
    log mailbox is almost entirely this: 622 of 630 messages in one 3-day catch-up, each carrying a
    full body through the folder page for a row nobody will ever open.
    """
    return any(p.get('Active', 1) and p['Kind'] in BODYLESS and p['Action'] in ('skip', 'ignore')
               and matches(p, msg) for p in policies)


def apply_retroactively(store, policy: dict) -> int:
    """A skip rule works BACKWARDS too: muting a flood sender shouldn't leave 200 of their
    old rows sitting on the timeline. Turning the rule off puts that history back (as
    'ignored', or 'routed' where the message is on a task - the pre-skip state isn't
    recorded, and both mean "visible, no work"). Only 'skip' changes visibility, so it is
    the only action applied backwards; 'context' messages (your own replies) never move."""
    if policy.get('Action') != 'skip': return 0
    on = bool(policy.get('Active', 1))
    # ...and a flood sender's rows still WAITING for triage, or whose triage failed: with no keyword rule filing their
    # "automated, no action required" before a model reads them (2026-09-25), those are where a flood sits
    froms = ('routed', 'ignored', 'filed', 'error', 'triaging') if on else ('skipped',)
    kind = policy.get('Kind')
    scan = {'statuses': froms}
    # only the kinds whose SQL is EXACTLY matches() get an envelope pre-filter - 'noreply' is a regex
    # no LIKE list reproduces faithfully, and a prefilter that misses is a row stranded off the timeline
    if kind == 'sender': scan['from_email'] = _split(policy.get('Pattern'))
    elif kind == 'sender_domain': scan['from_domains'] = _split(policy.get('Pattern'))
    if kind in BODYLESS: scan['include_body'] = False      # judged on the envelope: never pay for the body
    n = 0
    for m in store.scan_messages(**scan):
        if not matches(policy, {'from_email': m.get('FromEmail'), 'subject': m.get('Subject'), 'body': m.get('BodyText')}):
            continue
        store.set_message_status(m['MessageId'], 'skipped' if on else ('routed' if m.get('TaskId') else 'ignored'))
        n += 1
    return n


def evaluate(msg: dict, policies: list, known_sender: bool = True) -> dict:
    """Decide the action for a message. Returns {action, rule, reason} - rule/reason name
    the winning policy, or 'default' when nothing matched."""
    hits = [p for p in policies if p.get('Active', 1) and matches(p, msg, known_sender)]
    for action in PRECEDENCE:
        tier = sorted([p for p in hits if p['Action'] == action], key=lambda p: p.get('SortOrder', 100))
        if tier: return {'action': action, 'rule': tier[0]['Name'], 'reason': tier[0]['Reason']}
    return {'action': 'none', 'rule': 'default', 'reason': 'no rule matched'}
