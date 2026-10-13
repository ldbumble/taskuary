"""ONE SEARCH OVER EVERYTHING (the owner, 2026-10-13: "i want to be able to search for anything so search would bring up
tasks/emails/chats/pr etc etc with little pill on it"). The rail's box found tasks by their words and the filter found
a source by its name; a mail no task holds - filed, fyi, a thread between other people - was findable from nowhere.

Three readers, one answer: tasks by their own words (store.list_tasks, the same match the Tasks tab makes), every
arrived message by the full-text index (store.message_search: subject, sender and body, best match first), and the
connected sources by name. Each hit says what it IS (`type`, the pill) and how to open it - a task by its id, a message
by its own id (with the task holding it, when one does), a source as the rail's filter."""
import json, re
from .store import task_ref

CHAT = {'teams', 'slack', 'whatsapp', 'telegram', 'imessage', 'discord'}
TICKET = {'jira', 'asana', 'monday', 'linear', 'clickup', 'todoist', 'trello', 'notion', 'azdo', 'sentry', 'pagerduty'}
CLOSED = ('done', 'dropped')
N_TASKS, N_MSGS, N_SRCS = 8, 30, 6


def kind_of(m: dict) -> str:
    """The pill a message wears: what the owner would call it, not the connector it came through."""
    ch, link = m.get('Channel') or '', m.get('SourceLink') or ''
    if ch in ('github', 'gitlab'): return 'pr' if '/pull/' in link or '/merge_requests/' in link else 'issue'
    if ch == 'email': return 'email'
    if ch in CHAT: return 'chat'
    if ch == 'assistant': return 'advisor'
    if ch == 'report': return 'report'
    if ch == 'own': return 'note'
    return 'ticket' if ch in TICKET else 'item'


def _first_line(t: str) -> str: return next((l.strip() for l in str(t or '').splitlines() if l.strip()), '')


def _title(m: dict) -> str:
    s = (m.get('Subject') or '').strip()
    # a code host's subject leads with "owner/repo#123 " - the repository is the subtitle's to say; the number stays
    if m.get('Channel') in ('github', 'gitlab'): s = re.sub(r'^\S+/\S+(#\d+)\s+', r'\1 ', s)
    return s or (m.get('TriageTitle') or '').strip() or _first_line(m.get('OwnText') or m.get('BodyText'))[:140] or '(no subject)'


def snippet(text: str, words, width: int = 150) -> str:
    """The passage around the first word that matched, on one line - or the start, when none is in the body."""
    t = re.sub(r'\s+', ' ', str(text or '')).strip()
    if not t: return ''
    low = t.lower()
    at = min((i for i in (low.find(w.lower()) for w in words) if i >= 0), default=-1)
    if at < 0: return t[:width] + ('…' if len(t) > width else '')
    lo = max(0, at - width // 3)
    lo = t.rfind(' ', 0, lo) + 1 if lo else 0       # start on a word, not inside one
    return ('…' if lo else '') + t[lo:lo + width].strip() + ('…' if lo + width < len(t) else '')


def _where(m: dict) -> str:
    ch = m.get('Channel') or ''
    if ch == 'email':
        try: to = ', '.join((json.loads(m.get('RecipientsJson') or '{}') or {}).get('to') or [])
        except (ValueError, AttributeError): to = ''
        return f'to {to[:60]}' if to else m.get('SourceName') or ''
    return m.get('SourceName') or ch


def _tasks(store, q: str, words) -> list:
    ts = store.list_tasks(None, q=q)
    lw = [w.lower() for w in words]
    # open before closed, a title naming every word before one matched only through its mail, newest first
    ts.sort(key=lambda t: str(t.get('UpdatedAt') or t.get('CreatedAt') or ''), reverse=True)
    ts.sort(key=lambda t: (t.get('Status') in CLOSED, not all(w in (t.get('Title') or '').lower() for w in lw)))
    return [{'type': 'task', 'id': f"task:{t['TaskId']}", 'tid': t['TaskId'], 'ref': task_ref(t['TaskId']), 'title': t.get('Title') or '',
             'sub': ' · '.join(x for x in (t.get('Kind'), t.get('Source')) if x), 'when': t.get('ClosedAt') or t.get('UpdatedAt') or t.get('CreatedAt'),
             'status': t.get('Status'), 'snippet': snippet(t.get('Summary'), words, 120)} for t in ts[:N_TASKS]]


def _message_ids(store, words) -> list:
    ids = store.message_search(words, limit=N_MSGS * 6, prefix=True)
    if ids is not None: return ids
    # no full-text index on this SQLite: the subject and the sender, scanned - slower, never nothing
    pat = [f'%{w.lower()}%' for w in words]
    cond = ' AND '.join("lower(IFNULL(Subject,'') || ' ' || IFNULL(FromName,'') || ' ' || IFNULL(FromEmail,'')) LIKE ?" for _ in pat)
    return [r['MessageId'] for r in store._rows(f'SELECT MessageId FROM message WHERE {cond} ORDER BY SentAt DESC LIMIT ?', (*pat, N_MSGS * 6))]


def _messages(store, words) -> list:
    out, seen = [], {}
    for mid in _message_ids(store, words):
        m = store.get_message(mid)
        if not m: continue
        conv = m.get('ConversationId') or f'mid:{mid}'
        # one row per thread - its best-matching message - with how many more in it matched
        if conv in seen: seen[conv]['more'] += 1; continue
        t = store.get_task(m['TaskId']) if m.get('TaskId') else None
        hit = {'type': kind_of(m), 'id': f'msg:{mid}', 'mid': mid, 'title': _title(m), 'who': m.get('FromName') or m.get('FromEmail') or '',
               'where': _where(m), 'channel': m.get('Channel'), 'when': m.get('SentAt') or m.get('CreatedAt'), 'link': m.get('SourceLink'),
               'snippet': snippet(m.get('OwnText') or m.get('BodyText'), words), 'more': 0,
               'tid': t['TaskId'] if t else None, 'ref': task_ref(t['TaskId']) if t else None, 'status': t.get('Status') if t else None}
        seen[conv] = hit; out.append(hit)
        if len(out) >= N_MSGS: break
    return out


def _sources(store, words) -> list:
    lw = [w.lower() for w in words]
    out = []
    for s in store.list_sources():
        # named as the rail's filter names it (FeedView's source picker): a report by its title, the scheduled Advisor
        # under the channel its posts arrive on - so a picked source lands on a filter that exists
        try: cfg = json.loads(s.get('ConfigJson') or '{}') or {}
        except ValueError: cfg = {}
        ch = 'assistant' if s.get('Channel') == 'report' and cfg.get('type') == 'assistant' else s.get('Channel') or ''
        name = (cfg.get('title') or s.get('Address') or '') if s.get('Channel') == 'report' else s.get('Address') or ''
        if all(w in f'{name} {ch}'.lower() for w in lw):
            out.append({'type': 'source', 'id': f"src:{ch}:{name}", 'title': name, 'channel': ch, 'pick': f'src:{ch}:{name}'})
    return out[:N_SRCS]


def everything(store, q: str) -> dict:
    words = [w for w in re.findall(r'[\w@.\-]+', str(q or '')) if len(w) > 1 or w.isdigit()]
    if not words: return {'q': q, 'hits': []}
    return {'q': q, 'hits': _tasks(store, q, words) + _messages(store, words) + _sources(store, words)}
