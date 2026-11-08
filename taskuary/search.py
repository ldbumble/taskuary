"""ONE SEARCH OVER EVERYTHING (the owner, 2026-10-13: "i want to be able to search for anything so search would bring up
tasks/emails/chats/pr etc etc with little pill on it"). The rail's box found tasks by their words and the filter found
a source by its name; a mail no task holds - filed, fyi, a thread between other people - was findable from nowhere.

Three readers, one answer: tasks by their own words (store.list_tasks, the same match the Tasks tab makes), every
arrived message by the full-text index (store.message_search: subject, sender and body, best match first), and the
connected sources by name. Each hit says what it IS (`type`, the pill) and how to open it - a task by its id, a message
by its own id (with the task holding it, when one does), a source as the rail's filter.

...and THE APP'S OWN PLACES (the 2026-10-19 UI walk, G9): "Gmail" and "model" found nothing, though a Connections card and four
settings are called that. The setting schema and the connector catalogue are the registry - the same files those pages draw
from - and a hit carries the link (`href`) that opens the page at it, the road every in-app link takes (appLinks.js).

Each answer says how much there was (`totals` by type, past the caps; `capped` when the mail index stopped counting) - the
footer said "15 of 15" over a list cut at eight tasks - and a hit says WHY it matched (`why`) when nothing it shows does:
"Ruth Bennett" listed six tasks with no Ruth anywhere on them."""
import json, re
from datetime import datetime
from urllib.parse import quote
from . import connectorcatalog, settings_schema, wanames
from .store import _fold, task_ref

CHAT = {'teams', 'slack', 'whatsapp', 'telegram', 'imessage', 'discord'}
TICKET = {'jira', 'asana', 'monday', 'linear', 'clickup', 'todoist', 'trello', 'notion', 'azdo', 'sentry', 'pagerduty'}
CLOSED = ('done', 'dropped')
N_TASKS, N_MSGS, N_SRCS, N_PLACES = 8, 30, 6, 6


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


def _where(m: dict, store=None) -> str:
    ch = m.get('Channel') or ''
    if ch == 'whatsapp' and store is not None:
        jid = str(m.get('ConversationId') or '').removeprefix('whatsapp:')
        if wanames.is_jid(jid):
            return wanames.name_of(store, jid) or (m.get('SourceName') if wanames.is_group(jid) else '') or wanames.label(jid)
    if ch == 'email':
        try: to = ', '.join((json.loads(m.get('RecipientsJson') or '{}') or {}).get('to') or [])
        except (ValueError, AttributeError): to = ''
        return f'to {to[:60]}' if to else m.get('SourceName') or ''
    return m.get('SourceName') or ch


def _in(text, w) -> bool: return _fold(w) in _fold(text)          # the store's own match: a LIKE %word%, folded


def _ids(words) -> set:
    """The task ids typed outright - TQ-0004, tq-4, or a bare 4 - which put that task first: "4" listed TQ-0004 fourth."""
    return {int(m[1] or m[2]) for w in words if (m := re.fullmatch(r'(?i)tq-?0*(\d+)|0*(\d+)', w))}


def _holder(a: str) -> str:
    """An assignee as the owner reads it: the address or the agent, not the store's 'person:' / 'agent:' key (verify, 2026-10-20)."""
    kind, _, who = str(a or '').partition(':')
    return f'the {who} agent' if kind == 'agent' and who else who if kind == 'person' and who else str(a or '')


def _clip(s, n: int = 70) -> str: s = str(s or ''); return s if len(s) <= n else s[:n - 1] + '…'


def _task_why(t: dict, words, mail: list) -> str:
    """Where the words matched that the row does not show: the title, summary, kind, source and ref are on it already.
    ...and WHAT it matched, every time: "a link on its mail" named no link - the mail's id and link are said as they are."""
    seen = ' '.join(str(t.get(k) or '') for k in ('Title', 'Summary', 'Kind', 'Source')) + f" {task_ref(t['TaskId'])} {t['TaskId']}"
    def on_mail(k, say): return next((say(m[k]) for m in mail if _in(m.get(k), w)), '')
    out = []
    for w in (w for w in words if not _in(seen, w)):
        said = (f"tagged {t['Tags']}" if _in(t.get('Tags'), w) else f"assigned to {_holder(t['Assignee'])}" if _in(t.get('Assignee'), w) else
                next((f"a mail on it is from {m.get('FromName') or m.get('FromEmail')}" for m in mail
                      if _in(m.get('FromName'), w) or _in(m.get('FromEmail'), w)), '') or
                on_mail('Subject', lambda v: f"a mail on it: {_clip(v)}") or
                next((f"it came in on {m.get('SourceName') or m.get('Channel')}" for m in mail
                      if _in(m.get('SourceName'), w) or _in(m.get('Channel'), w)), '') or
                (f"its source reference {_clip(t['SourceRef'])}" if _in(t.get('SourceRef'), w) else '') or
                on_mail('SourceLink', lambda v: f"a mail on it links to {_clip(re.sub(r'^https?://(www[.])?', '', v))}") or
                on_mail('ExternalId', lambda v: f"the id of a mail on it: {_clip(v)}") or 'a mail on it')
        if said not in out: out.append(said)
    return '; '.join(out)


# DONE TODAY (the owner, 2026-11-06): the tasks closed today, a filter of the search box only - never on the rail. Asked as `done:today`
# (the box's chip types it), with words or without; newest closed first, more of them than a word search shows
DONE_TODAY, N_DONE = 'done:today', 40


def _tasks(store, q: str, words, status: str = '', today: bool = False) -> tuple:
    ts = store.list_tasks('done' if today else None, q=q, shown=True)
    if status: ts = [t for t in ts if _fold(t.get('Status')).startswith(status)]
    if today:
        d = datetime.now().strftime('%Y-%m-%d')
        ts = sorted((t for t in ts if str(t.get('ClosedAt') or '')[:10] == d), key=lambda t: str(t.get('ClosedAt')), reverse=True)
    lw, ids = [w.lower() for w in words], _ids(words)
    # the id typed first, then open before closed, a title naming every word before one matched only through its mail, newest first
    ts.sort(key=lambda t: str(t.get('UpdatedAt') or t.get('CreatedAt') or ''), reverse=True)
    ts.sort(key=lambda t: (t['TaskId'] not in ids, t.get('Status') in CLOSED, not all(w in (t.get('Title') or '').lower() for w in lw)))
    top, mail = ts[:N_DONE if today else N_TASKS], {}
    for r in store._rows(f"SELECT TaskId, Channel, SourceName, Subject, FromName, FromEmail, ExternalId, SourceLink FROM message WHERE TaskId IN "
                         f"({','.join('?' * len(top))})", [t['TaskId'] for t in top]) if top else []:
        mail.setdefault(r['TaskId'], []).append(r)
    return [{'type': 'task', 'id': f"task:{t['TaskId']}", 'tid': t['TaskId'], 'ref': task_ref(t['TaskId']), 'title': t.get('Title') or '',
             'sub': ' · '.join(x for x in (t.get('Kind'), t.get('Source')) if x), 'when': t.get('ClosedAt') or t.get('UpdatedAt') or t.get('CreatedAt'),
             'status': t.get('Status'), 'snippet': snippet(t.get('Summary'), words, 120),
             'why': _task_why(t, words, mail.get(t['TaskId'], []))} for t in top], len(ts)


def _who(store, m: dict) -> str:
    """A WhatsApp sender by name, else by number - the bare number the poller signs a nameless line with is not a name."""
    who = m.get('FromName') or m.get('FromEmail') or ''
    if m.get('Channel') != 'whatsapp' or not str(m.get('FromEmail') or '').startswith('whatsapp:'): return who
    jid = str(m['FromEmail'])[9:] + '@s.whatsapp.net'
    return (wanames.name_of(store, jid) or ('' if wanames.bare(m.get('FromName'), jid) else m['FromName'])
            or wanames.phone(jid) or who)


def _wa_ids(store, q: str) -> list:
    """WhatsApp lines found by WHO they are with - a person's name or number, a group's name (wanames.matches) - never the JID
    typed. Newest first, ahead of the index's matches, which know only the name each line was signed with."""
    q = str(q or '').strip()
    if not q: return []
    jids = [j for j, n in wanames.names(store).items() if wanames.matches(q, j, n)]
    conds, p = [], []
    if jids: conds.append(f"ConversationId IN ({','.join('?' * len(jids))})"); p += [f'whatsapp:{j}' for j in jids]
    if wanames.is_phone_query(q):
        d = wanames.digits(q); d = d[2:] if d.startswith('00') else d.lstrip('0') or d
        conds.append("(ConversationId LIKE ? AND ConversationId LIKE '%@s.whatsapp.net') OR FromEmail LIKE ?"); p += [f'whatsapp:%{d}%'] * 2
    if not conds: return []
    return [r['MessageId'] for r in store._rows(f"SELECT MessageId FROM message WHERE Channel='whatsapp' AND ({' OR '.join(conds)}) "
                                                'ORDER BY SentAt DESC LIMIT ?', (*p, N_MSGS * 6))]


def _message_ids(store, words) -> list:
    ids = store.message_search(words, limit=N_MSGS * 6, prefix=True)
    if ids is not None: return ids
    # no full-text index on this SQLite: the subject and the sender, scanned - slower, never nothing
    pat = [f'%{w.lower()}%' for w in words]
    cond = ' AND '.join("lower(IFNULL(Subject,'') || ' ' || IFNULL(FromName,'') || ' ' || IFNULL(FromEmail,'')) LIKE ?" for _ in pat)
    return [r['MessageId'] for r in store._rows(f'SELECT MessageId FROM message WHERE {cond} ORDER BY SentAt DESC LIMIT ?', (*pat, N_MSGS * 6))]


def _messages(store, words, first=()) -> tuple:
    had = set(first)
    ids = [*first, *(i for i in _message_ids(store, words) if i not in had)]
    # every match is counted, by thread and kind, from one light read - only the rows shown are read whole
    rows = {r['MessageId']: r for r in store._rows(
        f"SELECT MessageId, ConversationId, Channel, SourceLink FROM message WHERE MessageId IN ({','.join('?' * len(ids))})", ids)} if ids else {}
    out, seen, totals = [], {}, {}
    for mid in ids:
        r = rows.get(mid)
        if not r: continue
        conv = r.get('ConversationId') or f'mid:{mid}'
        # one row per thread - its best-matching message - with how many more in it matched
        if conv in seen:
            if seen[conv]: seen[conv]['more'] += 1
            continue
        seen[conv] = None
        m = store.get_message(mid) if len(out) < N_MSGS else None
        k = kind_of(m or r); totals[k] = totals.get(k, 0) + 1
        if not m: continue
        t = store.get_task(m['TaskId']) if m.get('TaskId') else None
        hit = {'type': k, 'id': f'msg:{mid}', 'mid': mid, 'title': _title(m), 'who': _who(store, m),
               'where': _where(m, store), 'channel': m.get('Channel'), 'when': m.get('SentAt') or m.get('CreatedAt'), 'link': m.get('SourceLink'),
               'snippet': snippet(m.get('OwnText') or m.get('BodyText'), words), 'more': 0,
               'tid': t['TaskId'] if t else None, 'ref': task_ref(t['TaskId']) if t else None, 'status': t.get('Status') if t else None}
        shows = f"{hit['title']} {hit['who']} {hit['where']} {hit['snippet']}"
        hit['why'] = next((f"from {m['FromEmail']}" for w in words if not _in(shows, w) and _in(m.get('FromEmail'), w)), '')
        seen[conv] = hit; out.append(hit)
    # the index was asked for so many: a list that filled it may have more behind it
    return out, totals, len(ids) >= N_MSGS * 6


def _sources(store, words, q: str = '') -> list:
    lw, known, q = [w.lower() for w in words], wanames.names(store), q or ' '.join(words)
    out = []
    for s in store.list_sources():
        # named as the rail's filter names it (FeedView's source picker): a report by its title, the scheduled Advisor
        # under the channel its posts arrive on - so a picked source lands on a filter that exists
        try: cfg = json.loads(s.get('ConfigJson') or '{}') or {}
        except ValueError: cfg = {}
        ch = 'assistant' if s.get('Channel') == 'report' and cfg.get('type') == 'assistant' else s.get('Channel') or ''
        name = (cfg.get('title') or s.get('Address') or '') if s.get('Channel') == 'report' else s.get('Address') or ''
        if ch == 'whatsapp' and wanames.is_jid(name):
            # a WhatsApp chat by its name or number - its JID is the small line under it, never what finds it
            title = wanames.label(name, wanames.name_of(store, name, known))
            if wanames.matches(q, name, title) or all(w in f'{title} {ch}'.lower() for w in lw):
                out.append({'type': 'source', 'id': f"src:{ch}:{name}", 'title': title, 'sub': name, 'channel': ch, 'pick': f'src:{ch}:{name}'})
            continue
        if all(w in f'{name} {ch}'.lower() for w in lw):
            out.append({'type': 'source', 'id': f"src:{ch}:{name}", 'title': name, 'channel': ch, 'pick': f'src:{ch}:{name}'})
    return out


# the Settings page keeps these two rows hidden (SettingsView HIDDEN): the values are kept, nothing reads them
_UNSHOWN = {'funnel_hours', 'funnel_max'}


def _words_in(text: str, words) -> bool:
    """Every word starts a word of the text - the mail index's own prefix match, so "mail" is not found inside "Gmail"."""
    t = _fold(text)
    return all(re.search(r'(?<![^\W_])' + re.escape(_fold(w)), t) for w in words)


def _settings(words) -> list:
    out = []
    for k, m in settings_schema.knobs().items():
        if k in _UNSHOWN or not _words_in(f"{m['label']} {m['group']} {m.get('desc') or ''} {m.get('help') or ''}", words): continue
        out.append({'type': 'setting', 'id': f'set:{k}', 'title': m['label'], 'where': f"Settings · {m['group']}",
                    'snippet': snippet(m.get('desc') or m.get('help'), words, 120), 'rank': not _words_in(m['label'], words),
                    'href': f"#settings=config&group={quote(m['group'], safe='')}&key={quote(k, safe='')}"})
    return sorted(out, key=lambda h: h.pop('rank'))


def _connectors(store, words) -> list:
    on = {str(c.get('Type') or '') for c in store.list_connectors() if c.get('Active')}
    out = []
    for c in connectorcatalog.cards():
        title = c.get('title') or c['type']
        if not _words_in(' '.join([c['type'], title, c.get('group') or '', c.get('desc') or '', *(c.get('match') or [])]), words): continue
        out.append({'type': 'connector', 'id': f"con:{c['type']}", 'title': title, 'where': ' · '.join(x for x in ('Connections', c.get('group')) if x),
                    'sub': 'connected' if c['type'] in on else 'planned' if c.get('planned') else 'not connected',
                    'snippet': snippet(c.get('desc'), words, 120), 'href': f"#connector={quote(c['type'], safe='')}",
                    'rank': (not _words_in(f"{title} {c['type']}", words), c['type'] not in on, bool(c.get('planned')))})
    return sorted(out, key=lambda h: h.pop('rank'))


# ── THE APP, INDEXED (the owner, 2026-10-20: "index the entire app so it can pull up anything from connectors/settings or anything
# correctly") ──────────────────────────────────────────────────────────────────────────────────────────────────────────────────────
# One list of everything the app can bring up, each with the link that opens it - the same registries the pages draw from: the places
# (words.json), every setting (the schema, held in view by its &key), every catalogue card and the owner's own cards by name, the
# reports and workflows, the documents. The Assistant asks it (app.find) and links what it picked; nothing is pasted into a turn.
# Ranked, not filtered: a word in a NAME counts three times what it does anywhere else, and a word counts by how RARE it is in the
# index (log N/df) - so "turn off the sound" finds the sound knob by "sound", and "the" and "off", in half the rows, weigh nearly nothing.
def _stem(w: str) -> str: w = _fold(w); return w[:-2] if len(w) >= 7 else w.rstrip('s') if len(w) > 3 else w      # "signature" is never Signal
# a short word is a whole word ("my" is never MySQL, "ap" is AP ageing); a longer one starts a word, the mail index's prefix match
def _hit(w: str, t: str) -> bool: return re.search(r'(?<![^\W_])' + re.escape(w) + (r'(?![^\W_])' if len(w) <= 3 else ''), t) is not None
# the pages words.json has no sentence for, by the links the canvas opens (canvasLinks.js)
PAGES = (('the Hub', '#hub', 'hub company knowledge handbook'), ('Reports', '#report=', 'reports'), ('New report', '#report=new', 'new report'),
         ('New workflow', '#report=new-agent', 'new workflow'))


def _app_rows(store) -> list:
    from . import words as places
    # ...a page by what it holds too (words.json `does`): "install the new version" named no page, and Updates was found only by "update"
    rows = [{'type': 'place', 'title': p['name'], 'rest': f"{k} {p.get('does') or ''}", 'href': p['href'], 'key': k} for k, p in places.PLACES.items() if p.get('href')]
    rows += [{'type': 'place', 'title': t, 'rest': w, 'href': h, 'key': w.split()[0]} for t, h, w in PAGES]
    rows += [{'type': 'setting', 'title': m['label'], 'where': f"{places.name('settings')} → {m['group']}", 'rest': f"{m['group']} {m.get('desc') or ''} {m.get('help') or ''} {k}",
              'href': f"#settings=config&group={quote(m['group'], safe='')}&key={quote(k, safe='')}"}
             for k, m in settings_schema.knobs().items() if k not in _UNSHOWN]
    mine = [c for c in store.list_connectors()]
    on = {str(c.get('Type') or '') for c in mine if c.get('Active')}
    rows += [{'type': 'connector', 'title': c.get('title') or c['type'], 'where': 'Connections', 'boost': c['type'] in on, 'key': c['type'],
              'sub': 'connected' if c['type'] in on else 'planned' if c.get('planned') else 'not connected',
              'rest': ' '.join([c['type'], c.get('group') or '', c.get('desc') or '', *(c.get('match') or [])]),
              'href': f"#connector={quote(c['type'], safe='')}"} for c in connectorcatalog.cards()]
    # ...and the owner's own cards, by the name and account they were given ("my work Outlook"): the card of that type opens
    rows += [{'type': 'connector', 'title': str(c.get('Name') or c.get('Type')), 'where': f"Connections · your {c.get('Type')} card", 'boost': True,
              'sub': 'connected' if c.get('Active') else 'off', 'rest': f"{c.get('Type')} {c.get('Account') or ''} {c.get('Scope') or ''}",
              'href': f"#connector={quote(str(c.get('Type') or ''), safe='')}"} for c in mine if c.get('Name')]
    # A REPORT OPENS AS SEARCH OPENS IT (the owner, 2026-11-03: "open the report should open the report like search"): its newest run, the
    # report itself (#msg=, the card a Search pick puts on the table - read or not, on the rail or off it), its page only when it never ran.
    # The run's own words are part of what finds it, so "the report about overdue invoices" finds the one that says so
    runs = {r['ConversationId']: r for r in store._rows("SELECT m.MessageId, m.ConversationId, m.Subject, m.BodyText, m.SentAt FROM message m JOIN "
                                                         "(SELECT ConversationId c, MAX(MessageId) n FROM message WHERE Channel='report' GROUP BY ConversationId) x "
                                                         "ON m.MessageId = x.n")} if hasattr(store, '_rows') else {}
    for s in store.list_sources():
        if s.get('Channel') != 'report': continue
        try: cfg = json.loads(s.get('ConfigJson') or '{}') or {}
        except ValueError: cfg = {}
        run = runs.get(f"report:{s['SourceId']}")
        rows.append({'type': 'report', 'title': cfg.get('title') or s.get('Address') or 'report', 'where': 'Reports',
                     'rest': f"report workflow {cfg.get('type') or ''} {(run or {}).get('Subject') or ''} {str((run or {}).get('BodyText') or '')[:400]}",
                     'href': f"#msg={run['MessageId']}" if run else f"#report={s['SourceId']}", 'page': f"#report={s['SourceId']}",
                     **({'sub': f"last run {str(run.get('SentAt') or '')[:16]}"} if run else {})})
    try: docs = store.doc_names()
    except Exception: docs = []
    rows += [{'type': 'document', 'title': d.upper() + '.md' if re.fullmatch(r'[a-z]+', d) else d, 'where': places.name('docs'), 'rest': f'{d} document doc', 'key': d,
              # ...LEARNED.md is About you's Memory, read as sentences (2026-11-06)
              'href': places.href('memory') if d == 'learned' else places.href('docs') + (f'&doc={d}' if re.fullmatch(r'\w+', d) else '')} for d in docs]
    return rows


def places(store, q: str, n: int = 8) -> list:
    """The app's places that best answer `q`, best first, each with its link."""
    import math
    said = [_fold(w) for w in re.findall(r'[\w@.\-]+', str(q or '')) if len(w) > 1 or w.isdigit()]
    words = list(dict.fromkeys(_stem(w) for w in said))
    # the app's own name says which app, not which place in it: "reinstall taskuary" is Updates, not the built-in dashboard that
    # wears the name (Taskuary at a glance) - unless it is all that was asked
    words = [w for w in words if w != _stem('taskuary')] or words
    rows = _app_rows(store)
    if not words or not rows: return []
    texts = [(_fold(r['title']), _fold(f"{r['title']} {r.get('where') or ''} {r['rest']}")) for r in rows]
    weight = {w: math.log((len(rows) + 1) / (1 + sum(_hit(w, t) for _, t in texts))) for w in words}
    score = lambda nt: sum(weight[w] * (3 if _hit(w, nt[0]) else 1 if _hit(w, nt[1]) else 0) for w in words)
    seen = set()      # one row per thing: the catalogue lists a few cards twice, and a place two names for one link
    rows_ = [(nt, r) for nt, r in zip(texts, rows) if not ((r['href'], r['title']) in seen or seen.add((r['href'], r['title'])))]
    # ...and a word that IS a thing's own key - a card's type ("database", "imap"), a document's name ("learned"), a page's ("hub") - names it
    exact = lambda r: r.get('key') in said
    # ...and on a tie the app's own place before a catalogue card that shares its name ("the Hub" is the Hub, not the Company Hub connector)
    order = {'place': 0, 'setting': 1, 'report': 2, 'document': 3, 'connector': 4}
    scored = sorted(((score(nt) + (1 if exact(r) else 0), r) for nt, r in rows_),
                    key=lambda x: (-round(x[0], 6), not x[1].get('boost'), order.get(x[1]['type'], 5), len(x[1]['title'])))
    top = scored[0][0] if scored else 0
    # what is near the best - a weak echo of one common word is no candidate
    return [{k: v for k, v in r.items() if k not in ('rest', 'boost', 'key')} for s, r in scored[:n] if top > 0 and s >= top * 0.35]


# THE AGENT CHAT, SEARCHED (F28, the owner, 2026-11-08): a word only in a line the owner typed, an agent's answer or a draft it left found nothing.
# The conversation only - never a tool's log, never Taskuary's own machinery (store.is_internal, the filter list_comments keeps). A task whose title
# hit is listed already is not listed again; each other task once, by its newest line holding every word, tagged and opened at that line
# (`line`: the chat's own 'comment-<id>', GeneralWorkspace data-tq-chat-line - a draft's is the turn that left it, draft_snapshot)
CHAT_TAG, DRAFTS = 'in agent chat', ('draft_reply', 'draft', 'clarification', 'slot')


def _chat(store, words, skip) -> tuple:
    from .general import ASSISTANT_TYPE, USER_TYPE
    from .quickwork import report_of
    from .store import is_internal
    TEXT = "COALESCE(rv.FinalText, rv.DraftText, '')"
    lk = lambda col: ' AND '.join(f"tq_fold({col}) LIKE ? ESCAPE '\\'" for _ in words)
    pat = [store._like_pat(w) for w in words]
    said = [{**c, 'line': f"comment-{c['CommentId']}", 'Body': report_of(c['Body']) if c['ActorType'] == ASSISTANT_TYPE else c['Body']}
            for c in store._rows(f"SELECT CommentId, TaskId, Actor, ActorType, Body, CreatedAt FROM comment WHERE ActorType IN (?,?) AND {lk('Body')} "
                                 "ORDER BY CommentId DESC LIMIT 200", (USER_TYPE, ASSISTANT_TYPE, *pat)) if not is_internal(c)]
    drafts = store._rows(f"SELECT rv.TaskId, {TEXT} Body, rv.CreatedAt, (SELECT 'comment-' || s.CommentId FROM draft_snapshot s "
                         f"WHERE s.ReviewId=rv.ReviewId ORDER BY s.Id DESC LIMIT 1) line FROM review rv WHERE rv.Kind IN ({','.join('?' * len(DRAFTS))}) "
                         f"AND rv.Status IN ('pending','approved','edited') AND {lk(TEXT)} ORDER BY rv.ReviewId DESC LIMIT 50",
                         (*DRAFTS, *pat))
    best = {}
    for c in sorted([*said, *({**d, 'ActorType': 'draft'} for d in drafts)], key=lambda c: str(c.get('CreatedAt') or ''), reverse=True):
        if c['TaskId'] not in skip and c['TaskId'] not in best and all(_in(c['Body'], w) for w in words): best[c['TaskId']] = c
    out = []
    for tid, c in list(best.items())[:N_TASKS]:
        t = store.get_task(tid)
        if not t: continue
        who = 'you' if c['ActorType'] == USER_TYPE else 'a draft' if c['ActorType'] == 'draft' else 'the agent'
        out.append({'type': 'task', 'id': f"chat:{tid}", 'tid': tid, 'ref': task_ref(tid), 'title': t.get('Title') or '', 'status': t.get('Status'),
                    'sub': t.get('Kind') or '', 'tag': CHAT_TAG, 'who': who, 'line': c.get('line'), 'when': c.get('CreatedAt'),
                    'snippet': snippet(c['Body'], words, 120), 'why': ''})
    return out, len(best)


def everything(store, q: str) -> dict:
    toks = str(q or '').split()
    # a task's status is asked for by name - `status:open` - and never matched as a word (store._search_where `shown`)
    status = next((_fold(t[7:]) for t in toks if _fold(t).startswith('status:') and len(t) > 7), '')
    today = any(_fold(t) == DONE_TODAY for t in toks)
    rest = ' '.join(t for t in toks if not _fold(t).startswith('status:') and _fold(t) != DONE_TODAY)
    words = [w for w in re.findall(r'[\w@.\-]+', rest) if len(w) > 1 or w.isdigit()]
    if not words and not status and not today: return {'q': q, 'hits': [], 'totals': {}, 'capped': False}
    # +1 (555) 010-0123 is one phone number, not four words to find in a body
    if wanames.is_phone_query(rest): words = [wanames.digits(rest)]
    tasks, n_tasks = _tasks(store, rest, words, status, today)
    if status or today: return {'q': q, 'hits': tasks, 'totals': {'task': n_tasks}, 'capped': False}
    chat, n_chat = _chat(store, words, {t['tid'] for t in tasks})
    msgs, totals, capped = _messages(store, words, _wa_ids(store, rest))
    srcs, sets, cons = _sources(store, words, rest), _settings(words), _connectors(store, words)
    totals.update(task=n_tasks + n_chat, source=len(srcs), setting=len(sets), connector=len(cons))
    return {'q': q, 'hits': tasks + chat + msgs + srcs[:N_SRCS] + sets[:N_PLACES] + cons[:N_PLACES], 'totals': totals, 'capped': capped}


# ── WHAT EARLIER TASKS SETTLED (the owner, 2026-11-05, from Hermes' session_search: search before asking) ─────────────────────────────
# An agent asked the owner for a vendor id, a login route or the account they prefer that an earlier task had already found. Each task's
# ENDING is kept already - its turn summaries' `did` (general.SUMMARY_TYPE) and an agent's filed report (wrapup.REPORTS) - so this reads
# those; nothing new is stored. `loose`: the words of a task's title (any two of its longer words), not words an agent typed (all of them).
N_OUTCOMES, OUTCOME_CHARS = 8, 320


def _settled(row) -> str:
    from .general import SUMMARY_TYPE
    from .wrapup import report_body
    if row['ActorType'] != SUMMARY_TYPE: return report_body(row['Body']).split('\n\nLAST MESSAGE', 1)[0]
    try: j = json.loads(row['Body'] or '{}') or {}
    except ValueError: return ''
    return str(j.get('did') or j.get('about') or '') if isinstance(j, dict) else ''


def outcomes(store, words, skip=None, limit: int = N_OUTCOMES, loose: bool = False) -> list:
    """Earlier tasks whose own words or ending match `words`, each with what it settled - its newest ending. Best match first, then newest;
    never the task asking (`skip`) nor one dropped as no task at all."""
    from .general import SUMMARY_TYPE
    from .routing import tokens
    ws = list(dict.fromkeys(w for w in tokens(' '.join(words) if isinstance(words, (list, tuple)) else words) if not loose or len(w) >= 4))[:8]
    if not ws: return []
    need = min(2, len(ws)) if loose else len(ws)
    hay = "lower(IFNULL(t.Title,'') || ' ' || IFNULL(t.Summary,'') || ' ' || IFNULL(c.Body,''))"
    rows = store._rows(f"SELECT c.CommentId, c.TaskId, c.ActorType, c.Body, c.CreatedAt, t.Title, t.Summary, t.Status, t.ClosedAt FROM comment c "
                       f"JOIN task t ON t.TaskId=c.TaskId WHERE (c.ActorType=? OR c.Body LIKE 'AGENT REPORT%' OR c.Body LIKE 'CODER REPORT%') "
                       f"AND t.Status<>'dropped' AND c.TaskId<>? AND ({' OR '.join(f'{hay} LIKE ?' for _ in ws)}) ORDER BY c.CommentId DESC LIMIT 400",
                       (SUMMARY_TYPE, int(skip or 0), *[f'%{w}%' for w in ws]))
    best = {}
    for r in rows:
        if r['TaskId'] in best: continue
        said = ' '.join(_settled(r).split())
        if not said: continue
        text = f"{r.get('Title') or ''} {r.get('Summary') or ''} {said}".lower()
        n = sum(w in text for w in ws)
        if n >= need: best[r['TaskId']] = (n, r, said)
    top = sorted(best.values(), key=lambda x: (-x[0], -x[1]['CommentId']))[:limit]
    return [{'tid': r['TaskId'], 'ref': task_ref(r['TaskId']), 'title': r.get('Title') or '', 'status': r.get('Status') or '',
             'when': str(r.get('ClosedAt') or r.get('CreatedAt') or '')[:10],
             'settled': said[:OUTCOME_CHARS] + ('…' if len(said) > OUTCOME_CHARS else '')} for _, r, said in top]


def says_outcomes(hits: list) -> str:
    "The outcomes as an agent reads them: one line each, the task first - '' with none."
    if not hits: return ''
    return ("WHAT EARLIER TASKS SETTLED (each one's own ending - what it found and did):\n"
            + '\n'.join(f"- {h['ref']} ({h['status']}, {h['when']}) {h['title']}: {h['settled']}" for h in hits))
