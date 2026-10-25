"""THE TRACK RECORD (the owner, 2026-10-25: "show the earned-trust track record, but NEVER send without approval for now"): what
became of the drafts, by kind and by the recipient's domain - sent as drafted, edited first, or rejected. Counts read off rows the
app already keeps (the outcome ledger's reply.sent, the review's own status), no model. It is evidence only: nothing reads it to
send, to skip a press or to light a button, and the Assistant is told so with it. Auto mode for chosen recipients is maybe later -
when it comes, this is what it would stand on, one pattern at a time."""
import json
from datetime import datetime, timedelta

KIND_WORDS = {'draft': 'reply', 'draft_reply': 'reply', 'outbound': 'new email', 'clarification': 'question to the sender',
              'action': "an agent's proposed action"}
HEADING = ("TRACK RECORD (the last {days} days of drafts by kind and the recipient's domain: sent as drafted / edited first / "
           "rejected. Evidence of how the drafts are landing - never a reason to send: nothing goes without the owner's press)")


def _domain(addr: str, channel: str = '') -> str:
    a = str(addr or '').strip().lower()
    return a.rsplit('@', 1)[1] if '@' in a else (channel or 'a chat')


def _to(rv: dict) -> str:
    try: d = json.loads(rv.get('Deliver') or '{}') or {}
    except (TypeError, ValueError): d = {}
    to = d.get('to') if isinstance(d, dict) else None
    return (to[0] if isinstance(to, list) and to else to) or ''


def _key(store, rv: dict, who: str = '') -> tuple:
    m = store.get_message(rv['MessageId']) if rv.get('MessageId') else None
    return KIND_WORDS.get(rv.get('Kind'), str(rv.get('Kind') or 'draft')), _domain(who or (m or {}).get('FromEmail') or _to(rv), (m or {}).get('Channel') or '')


def patterns(store, days: int = 30, now: datetime = None) -> list:
    """[{kind, domain, as_drafted, edited, rejected, total}], the busiest pattern first."""
    since = ((now or datetime.now()) - timedelta(days=int(days))).strftime('%Y-%m-%d %H:%M:%S')
    tally = {}
    def add(k, col):
        t = tally.setdefault(k, {'kind': k[0], 'domain': k[1], 'as_drafted': 0, 'edited': 0, 'rejected': 0})
        t[col] += 1
    for r in store._rows("SELECT FactsJson f FROM outcome WHERE Kind='reply.sent' AND At>=?", (since,)):
        f = json.loads(r['f'] or '{}')
        rv = store._one('SELECT * FROM review WHERE ReviewId=?', (int(f['review']),)) if str(f.get('review') or '').isdigit() else None
        add(_key(store, rv, f.get('who') or '') if rv else ('reply', _domain(f.get('who'))), 'as_drafted' if f.get('verb') == 'approve' else 'edited')
    for rv in store._rows("SELECT * FROM review WHERE Status='rejected' AND Kind<>'slot' AND DecidedAt>=?", (since,)):
        add(_key(store, rv), 'rejected')
    out = [{**t, 'total': t['as_drafted'] + t['edited'] + t['rejected']} for t in tally.values()]
    return sorted(out, key=lambda t: (-t['total'], t['kind'], t['domain']))


def lines(rows: list, cap: int = 20) -> list:
    return [f"- {t['kind']} to {t['domain']}: {t['as_drafted']} sent as drafted, {t['edited']} edited first, {t['rejected']} rejected"
            for t in rows[:cap]]


def block(store, days: int = 30, cap: int = 20) -> str:
    """The Assistant's read-only section body: '' when nothing was drafted in the window."""
    return '\n'.join(lines(patterns(store, days), cap))
