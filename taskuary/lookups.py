"""The assistant's look-ups past the first ten (concierge.read_op): open work, one message in full, a
sender at a glance, and the docs. Each reads what is already stored and changes nothing - the
assistant stays light because it asks for what it needs instead of carrying a memory in its prompt
(the owner, 2026-09-24: "it should be able to search ... using lookup tools")."""
import math, re
from datetime import datetime, timedelta
from pathlib import Path
from .routing import tokens
from .store import task_ref

NL = chr(10)
ACTIVE = ('open', 'in_progress', 'waiting')
# the help pages the website is built from; present in a checkout, absent from a wheel
SITE_DOCS = Path(__file__).resolve().parent.parent / 'docs' / 'site'
_H2 = re.compile(r'^## ', re.M)

def _cut(s, n):
    # a short field reads as one line; a body keeps its own lines
    s = ' '.join(str(s or '').split()) if n < 600 else str(s or '').strip()
    return s if len(s) <= n else s[:n] + ' […]'

def _day(s): return str(s or '')[:16]

def tasks_list(store, p: dict) -> str:
    status, limit = str(p.get('status') or 'open').strip().lower(), max(1, min(int(p.get('limit') or 25), 60))
    rows = store.list_tasks(status=None if status in ('open', 'all') else status, q=str(p.get('contains') or '').strip() or None)
    if status == 'open': rows = [t for t in rows if t.get('Status') in ACTIVE]
    if not rows: return f'No {"" if status == "all" else status + " "}tasks match that.'
    run = lambda t: f" - agent {t['RunAgent']} {t['RunStatus']}" if t.get('RunStatus') in ('running', 'queued') else ''
    out = [f"{task_ref(t['TaskId'])} [{t.get('Status')}/{t.get('Kind')}] {_cut(t.get('Title'), 120)} - updated {_day(t.get('UpdatedAt') or t.get('CreatedAt'))}{run(t)}"
           for t in rows[:limit]]
    return NL.join(out + ([f'…and {len(rows) - limit} more - narrow it with contains.'] if len(rows) > limit else []))

def message_read(store, p: dict) -> str:
    m = re.search(r'\d+', str(p.get('mid') or p.get('id') or ''))
    r = store.get_message(int(m.group())) if m else None
    if not r: return f"There is no message {p.get('mid') or p.get('id')}."
    head = (f"m{r['MessageId']} {r.get('Channel')} from {r.get('FromName') or ''} <{r.get('FromEmail') or ''}> at {_day(r.get('SentAt'))}"
            f"{' on ' + task_ref(r['TaskId']) if r.get('TaskId') else ''} [{r.get('Status')}]{NL}subject: {r.get('Subject') or ''}")
    own = str(r.get('OwnText') or '').strip()
    body = (f'their own words:{NL}{_cut(own, 2500)}{NL}' if own else '') + f"the message as received:{NL}{_cut(r.get('BodyText'), 4000 if not own else 1500)}"
    return head + NL + body

def sender_read(store, p: dict) -> str:
    who = str(p.get('who') or p.get('sender') or '').strip()
    hits = store.senders_like(who) if who else []
    if not hits: return f'Nobody by "{who}" has written in.'
    s = next((h for h in hits if h['Email'] == who.lower()), hits[0])
    em, since = s['Email'], (datetime.now() - timedelta(days=3650)).isoformat(' ', 'seconds')
    out = [f"{s['Name'] or em} <{em}> - {s['N']} messages, first {_day(s['First'])}, last {_day(s['Last'])}"]
    recent = store.messages_from(em, since, 8)
    if recent: out += ['recent:'] + [f"  m{r['MessageId']} {_day(r.get('SentAt'))} {task_ref(r['TaskId']) if r.get('TaskId') else '-'} "
                                     f"[{r.get('Status')}] {_cut(r.get('Subject'), 110)}" for r in recent]
    tasks = store.open_tasks_from(em)
    out.append('open tasks: ' + ('; '.join(f"{task_ref(t['TaskId'])} {_cut(t['Title'], 80)} ({t['Status']})" for t in tasks) if tasks else 'none'))
    replies = store.own_replies_to(em, since, 3)
    if replies: out.append('you last wrote back ' + _day(replies[0].get('SentAt')))
    notes = [m['Note'] for m in store.list_memories() if str(m.get('ScopeKey') or '').lower() == em]
    if notes: out += ['what you told me about them:'] + [f'  - {_cut(n, 300)}' for n in notes[:8]]
    others = [h for h in hits if h['Email'] != em]
    if others: out.append('also matching: ' + ', '.join(f"{h['Name'] or h['Email']} <{h['Email']}> ({h['N']})" for h in others))
    return NL.join(out)

_COMMENT = re.compile(r'<!--.*?-->', re.S)
CHUNK = 1200

def _stem(w): return w[:-1] if len(w) > 4 and w.endswith('s') else w
def _words(text): return {_stem(w) for w in tokens(text) if len(w) > 2}

def _sections(name: str, text: str):
    """A doc cut at its `##` headings, and a long section at its paragraphs - a passage is what an answer quotes."""
    parts = _H2.split(_COMMENT.sub('', text))
    for n, part in enumerate(parts):
        where = name if n == 0 else f"{name} > {part.splitlines()[0].strip()}"
        body, buf = ('## ' + part) if n else part, ''
        for para in re.split(r'\n\s*\n', body):
            if buf and len(buf) + len(para) > CHUNK: yield where, buf; buf = ''
            buf += para + NL * 2
        if buf.strip(): yield where, buf

def _corpus(store):
    if SITE_DOCS.is_dir():
        for f in sorted(SITE_DOCS.glob('*.md')): yield from _sections(f'help/{f.stem}', f.read_text(encoding='utf-8'))
    for n in store.doc_names(): yield from _sections(f'your doc {n}', store.doc(n) or '')

def docs_search(store, p: dict) -> str:
    q = str(p.get('query') or '')
    want = _words(q)
    if not want: return 'docs.search needs the words to look for.'
    chunks = [(w, t, _words(t)) for w, t in _corpus(store)]
    # a word most passages share says little about which one is meant; a rare one says a lot
    df = {w: sum(w in have for _, _, have in chunks) for w in want}
    idf = {w: math.log((len(chunks) + 1) / (df[w] + 0.5)) for w in want if df[w]}
    scored = sorted(((sum(idf[w] for w in idf if w in have), where, t) for where, t, have in chunks if want & have), key=lambda s: -s[0])
    if not scored: return f'Nothing in the help pages or your docs mentions "{q}".'
    return (NL * 2).join(f'[{w}]{NL}{_cut(t, CHUNK)}' for sc, w, t in scored[:4] if sc >= scored[0][0] / 2)

READ = {'tasks.list': tasks_list, 'message.read': message_read, 'sender.read': sender_read, 'docs.search': docs_search}

def read(store, kind: str, p: dict) -> str:
    f = READ.get(kind)
    return f(store, p or {}) if f else f'{kind} is not a look-up this app has.'
