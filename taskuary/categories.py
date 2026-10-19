"""What a message IS, in one word - the tag on every Timeline row.

Triage's verdict (task / reply_only / fyi) plus where the message ended up (a task, the list,
filed, ignored) collapses to one category, so a row can be read at a glance and the same word
means the same thing in the feed, the digest and the task page:

  coding    - sent to the coding agent            todo   - real work, on your own list
  review    - a reply is drafted for you to send  info   - a PERSON told you something; nothing to do
  automated - a system told you something          promo  - marketing / newsletter; safe to skim past
  filed     - kept, no verdict beyond "not work"   ignored - a policy or you said no
  report / feed / yours / mine / triaging         - not verdicts: a scheduled report, a feed-only
                                                    connection, your own reply, a note you left
                                                    yourself, or still deciding

The info / automated / promo split is the point (owner, 2026-08-27): "info from a team member
is more important than an FYI from a vendor's marketing team". Both are 'fyi' to the
classifier - nothing to do - but one is a colleague keeping you in the loop and the other is
a mailing list, and they must not wear the same tag.
"""
# WHO SENT IT - a person, a system or a mailing list - is the triage model's to say (`sender_class` on its verdict,
# kept on the message by store.add_route), and before a verdict exists only the mail PROTOCOL may say it: the list and
# auto-submission headers the sending system writes about itself (header_class, written at ingest). Five regexes over
# the address and the body decided it before, so a colleague writing from info@ or hello@ was "promo", one whose
# footer said "please do not reply" was "automated", and the Advisor never spoke about either (the owner, 2026-10-11:
# "everything should be ai"). No verdict and no header is a PERSON - a robot is never assumed, because a person filed
# as one is never looked at again.
import re

from . import kinds

SENDER_CLASSES = ('person', 'automated', 'bulk')

# THE ROUTE RECORD LEADS WITH WHOSE IT IS. It led with the classifier's label - "triage: task - ..." - and "task" reads
# as "on you" on work triage had handed to the assistant or the coding agent (the owner, 2026-10-16). Rows written
# before keep the old label, so every reader goes through route_intent, which knows both.
from .kinds import worker as agent_word   # kinds.json's `worker`: 'the coding agent', or 'the assistant'

def route_head(intent, kind='', repo='') -> str:
    "'nothing to do' | 'needs a reply' | 'work for the coding agent in org/app' | 'work for the assistant' | 'yours to do'."
    if intent == 'fyi': return 'nothing to do'
    if intent == 'reply_only': return 'needs a reply'
    if kind in kinds.AGENT: return f'work for {agent_word(kind)}' + (f' in {repo}' if repo and kind == 'coding' else '')
    return 'yours to do'

_HEAD = re.compile(r'triage: (task|reply_only|fyi|yours to do|work for |needs a reply|nothing to do)')
_HEAD_INTENT = {'yours to do': 'task', 'work for ': 'task', 'needs a reply': 'reply_only', 'nothing to do': 'fyi'}

def route_intent(reason) -> str:
    "'task' | 'reply_only' | 'fyi' | '' - the verdict a route reason records, in either wording."
    m = _HEAD.search(str(reason or ''))
    return _HEAD_INTENT.get(m.group(1), m.group(1)) if m else ''

def route_why(reason) -> str:
    "Triage's own reason with the head taken off: 'triage: yours to do - she asks for X · ...' -> 'she asks for X · ...'."
    return re.sub(r'^triage:\s*[^·]*?\s-\s', '', str(reason or ''), count=1)
CHAT = {'teams', 'slack', 'telegram', 'whatsapp', 'imessage', 'discord',
        'mattermost', 'rocketchat', 'matrix', 'google_chat'}


def _domain(email): return (email or '').rsplit('@', 1)[-1].lower().strip()


def header_class(h) -> str | None:
    """'automated' | 'bulk' | None from the headers a sending system writes about itself (any case-insensitive
    .get(name): an email.message.Message, or autoreply.headers() over Graph's list). Parsing, not reading: RFC 3834
    Auto-Submitted and Exchange's X-Auto-Response-Suppress say a system sent it, a null Return-Path is the bounce
    envelope; RFC 2369/2919 List-* and Precedence: bulk/list say a list did. A notifier that also carries an
    unsubscribe link is the system - its own statement is the more explicit one."""
    g = lambda k: str(h.get(k) or '').strip().lower()
    auto = g('Auto-Submitted')
    if (auto and not auto.startswith('no')) or g('X-Auto-Response-Suppress') or g('Return-Path') == '<>': return 'automated'
    if g('List-Unsubscribe') or g('List-Id') or g('Precedence') in ('bulk', 'list', 'junk'): return 'bulk'
    return None


def sender_class(r: dict, team_domains=()) -> str:
    """'person' | 'automated' | 'bulk' for a message row: a chat line is always a person; otherwise the row's
    SenderClass (the verdict's, else the headers') - and nothing at all is a person. `team_domains` is kept for
    the callers; the address no longer decides anything."""
    if (r.get('Channel') or '') in CHAT: return 'person'
    sc = str(r.get('SenderClass') or '').lower()
    return sc if sc in SENDER_CLASSES else 'person'


def category_of(r: dict, team_domains=()) -> str:
    """One category for a feed row (store.feed columns: MsgStatus, RouteReason, TaskKind…)."""
    st, reason = r.get('MsgStatus') or r.get('Status') or '', (r.get('RouteReason') or '').lower()
    if r.get('Channel') == 'report': return 'report'
    if r.get('Channel') == 'assistant': return 'assistant'         # the assistant's own post (assistant.py)
    # a row nothing sent you: a note you left yourself, or a task you started from the Board
    # (ownwork.py). It is the one kind of row that is yours rather than something that happened
    # to you, and it must never wear a verdict - nothing judged it, because nothing arrived.
    if r.get('Channel') == 'own': return 'mine' if (r.get('TaskKind') or '') == 'note' else 'todo'
    if r.get('Direction') == 'out' or 'your reply' in reason or 'your sent reply' in reason: return 'yours'
    if st == 'feed': return 'feed'
    if st == 'triaging': return 'triaging'
    if st == 'error': return 'error'                  # triage failed: not a verdict, shown with a retry (PW-036)
    if st in ('ignored', 'skipped'): return 'ignored'
    if st == 'filed':
        # only an fyi verdict earns a "nothing to do, here is who said it" tag; a message filed
        # because triage failed, or because you already ruled on the thread, is just filed
        if not (reason.startswith('triage:') and route_intent(reason) == 'fyi'): return 'filed'
        return {'person': 'info', 'automated': 'automated', 'bulk': 'promo'}[sender_class(r, team_domains)]
    kind = r.get('TaskKind') or ''
    if kind == 'reply': return 'review'
    if kind == 'coding': return 'coding'
    if r.get('TaskId'): return 'todo'
    return 'filed'


def team_domains_of(settings: dict) -> set:
    """Your organisation: the owner's own domain plus Settings → team_domains (csv)."""
    out = {_domain(settings.get('owner_email'))} | {d.strip().lower() for d in (settings.get('team_domains') or '').split(',')}
    return {d for d in out if d}
