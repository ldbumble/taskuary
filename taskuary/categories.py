"""What a message IS, in one word - the tag on every Timeline row.

Triage's verdict (task / reply_only / fyi) plus where the message ended up (a task, the list,
filed, ignored) collapses to one category, so a row can be read at a glance and the same word
means the same thing in the feed, the digest and the task page:

  coding    - sent to the coding agent            todo   - real work, on your own list
  review    - a reply is drafted for you to send  info   - a PERSON told you something; nothing to do
  automated - a system told you something          promo  - marketing / newsletter; safe to skim past
  filed     - kept, no verdict beyond "not work"   ignored - a policy or you said no
  report / feed / yours / triaging                - not verdicts: a scheduled report, a feed-only
                                                    connection, your own reply, or still deciding

The info / automated / promo split is the point (owner, 2026-08-27): "info from a team member
is more important than an FYI from a vendor's marketing team". Both are 'fyi' to the
classifier - nothing to do - but one is a colleague keeping you in the loop and the other is
a mailing list, and they must not wear the same tag.
"""
import re

FROM_AUTOMATED = re.compile(r'^(no-?reply|do-?not-?reply|notifications?|alerts?|reports?|system|mailer-daemon|postmaster|'
                            r'bounce|automated|auto|noreply-[\w.-]+|[\w.-]*-noreply|[\w.-]*-alerts?|[\w.-]*-notifications?)@', re.I)
FROM_PROMO = re.compile(r'^(news(letter)?s?|marketing|promo(tions)?|offers?|deals?|hello|hi|team|updates?|community|digest|'
                        r'insights?|events?|webinars?|info|contact|success|growth|product|announcements?)@', re.I)
BODY_PROMO = re.compile(r'unsubscribe|manage (your )?(email )?preferences|view (this )?(email )?in (your )?browser|'
                        r'opt[ -]out|you are receiving this (email )?because|update your (email )?preferences', re.I)
# a robot sender that ALSO carries mailing-list furniture is marketing (noreply@vendor.com with
# "manage preferences"); a bare "unsubscribe" is not enough there - GitHub's own notifications
# end with "or unsubscribe", and those are automated, not promo
BODY_PROMO_STRONG = re.compile(r'manage (your )?(email )?preferences|view (this )?(email )?in (your )?browser|'
                               r'you are receiving this (email )?because|update your (email )?preferences', re.I)
BODY_AUTOMATED = re.compile(r'this is an automated (message|email|notification)|do not reply to this (message|email)|'
                            r'automatically generated|please do not reply', re.I)
CHAT = {'teams', 'slack', 'telegram', 'whatsapp', 'imessage', 'discord'}


def _domain(email): return (email or '').rsplit('@', 1)[-1].lower().strip()


def sender_class(r: dict, team_domains=()) -> str:
    """'person' | 'automated' | 'promo' from the sender address and the first screen of body.
    A chat message is always a person. Your own organisation's mail is a person unless the
    address itself says it is a robot (noreply-securityapp@ is a system, whoever runs it)."""
    if (r.get('Channel') or '') in CHAT: return 'person'
    em, body = (r.get('FromEmail') or '').strip().lower(), (r.get('Preview') or r.get('BodyText') or '')[:4000]
    if FROM_AUTOMATED.match(em): return 'promo' if BODY_PROMO_STRONG.search(body) else 'automated'
    if _domain(em) in {d.lower() for d in team_domains if d}: return 'person'
    if BODY_PROMO.search(body) or FROM_PROMO.match(em): return 'promo'
    if BODY_AUTOMATED.search(body): return 'automated'
    return 'person'


def category_of(r: dict, team_domains=()) -> str:
    """One category for a feed row (store.feed columns: MsgStatus, RouteReason, TaskKind…)."""
    st, reason = r.get('MsgStatus') or r.get('Status') or '', (r.get('RouteReason') or '').lower()
    if r.get('Channel') == 'report': return 'report'
    if r.get('Channel') == 'assistant': return 'assistant'         # the assistant's own post (assistant.py)
    if r.get('Direction') == 'out' or 'your reply' in reason or 'your sent reply' in reason: return 'yours'
    if st == 'feed': return 'feed'
    if st == 'triaging': return 'triaging'
    if st in ('ignored', 'skipped'): return 'ignored'
    if st == 'filed':
        # only an fyi verdict earns a "nothing to do, here is who said it" tag; a message filed
        # because triage failed, or because you already ruled on the thread, is just filed
        if not reason.startswith('triage: fyi'): return 'filed'
        return {'person': 'info', 'automated': 'automated', 'promo': 'promo'}[sender_class(r, team_domains)]
    kind = r.get('TaskKind') or ''
    if kind == 'reply': return 'review'
    if kind == 'coding': return 'coding'
    if r.get('TaskId'): return 'todo'
    return 'filed'


def team_domains_of(settings: dict) -> set:
    """Your organisation: the owner's own domain plus Settings → team_domains (csv)."""
    out = {_domain(settings.get('owner_email'))} | {d.strip().lower() for d in (settings.get('team_domains') or '').split(',')}
    return {d for d in out if d}
