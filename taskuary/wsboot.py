"""THE OWNER'S WORKSTREAMS, READ FROM THEIR MAIL (the design's S6, 2026-11-01; the owner: "six months", a one-screen confirm at first
setup, after that an Advisor card; a new connector or GitHub project whose traffic shows another hat is noticed - suggested, or added
when sure).

1. GATHER six months of what came and went - every channel the app holds - as threads: who was on each, the chat group or mailbox,
   the repository, and whether the OWNER wrote on it (what they do weighs more than what lands on them).
2. CLUSTER WITHOUT A MODEL: people, chat groups and repositories that share the owner's threads are linked, the owner's own threads
   counting three times; label propagation splits the graph into groups. Machine senders (triage's own `automated`/`bulk`) are never
   people. Cheap and deterministic - it finds sister companies under one domain, which splitting by mailbox domain could not.
3. NAME EACH GROUP WITH THE MODEL: it reads a sample of the owner's own sent words in each group and answers which groups are one
   workstream, its name, a line about it, whether it is personal, and its JOB.md section. It may merge groups; it may not invent one.
4. PROPOSE: the result is kept as proposed workstreams (workstreams.KEY, status 'proposed') - at first setup the confirm screen shows
   them; later each comes as an Advisor card. Nothing proposed places an item until the owner confirms it, unless the model was SURE
   about a hat a new source brought, which is then added and said."""
import json, re
from collections import Counter, defaultdict
from datetime import datetime, timedelta
from loguru import logger
from . import workstreams as W

DAYS = 180                 # six months (the owner, 2026-11-01)
OWN_W, IN_W = 3, 1         # what an owner's thread weighs against one that only landed on them
MIN_OWN = 2                # a group is a candidate only with this many threads the owner wrote on
MAX_GROUPS = 8             # the model names at most this many - the largest by the owner's own threads
SAMPLE = 12                # the owner's own lines per group the model reads
NAME_TOKENS = 4000         # the naming answer: a section per workstream
REFRESH_DAYS, QUIET_DAYS, RECENT_DAYS = 7, 60, 14
SOURCE_MIN = 5             # a new source is judged once this many messages came in by it
NEW_DAYS = 45              # ...and only a source whose first message the app holds is this recent (a new connector or project)
STATE_KEY = 'workstreams_boot'


def _now(): return datetime.now()
def _ago(days): return (_now() - timedelta(days=days)).strftime('%Y-%m-%d %H:%M:%S')
def _mine(store) -> set:
    from .ingest import own_addresses, owner_addresses
    return {a.lower() for a in own_addresses(store) | owner_addresses(store) if a}


def _recipients(m) -> list:
    try: rs = json.loads(m.get('RecipientsJson') or '[]') or []
    except ValueError: rs = []
    if isinstance(rs, dict): rs = [*(rs.get('to') or []), *(rs.get('cc') or [])]
    return [str(r.get('email') if isinstance(r, dict) else r or '').strip().lower() for r in rs if r]


def _own(m) -> bool:
    return (m.get('Direction') or 'in') == 'out' or m.get('Status') == 'context' or m.get('FromName') == 'You'


# ── 1. GATHER ─────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────
def gather(store, days: int = DAYS, rows=None) -> list:
    """[{id, people:set, sources:set, repos:set, own:bool, lines:[the owner's own words], subjects}] - one per thread of the window."""
    rows = rows if rows is not None else store._rows(
        "SELECT MessageId, ConversationId, Channel, SourceName, Subject, FromName, FromEmail, RecipientsJson, Direction, Status, SenderClass, SentAt, "
        "substr(BodyText, 1, 300) BodyText FROM message WHERE SentAt>=? AND IFNULL(Channel,'') NOT IN ('assistant','own') ORDER BY SentAt", (_ago(days),))
    me, auto = _mine(store), defaultdict(Counter)
    for m in rows:
        if m.get('FromEmail'): auto[m['FromEmail'].lower()][m.get('SenderClass') or 'person'] += 1
    machine = {a for a, c in auto.items() if c['automated'] + c['bulk'] > c['person']}
    th = {}
    for m in rows:
        ch, src = str(m.get('Channel') or '').lower(), str(m.get('SourceName') or '').strip().lower()
        t = th.setdefault(m.get('ConversationId') or f"m{m['MessageId']}", {'id': m.get('ConversationId') or f"m{m['MessageId']}", 'people': set(),
                                                                          'sources': set(), 'repos': set(), 'own': False, 'days': set(), 'lines': [], 'subjects': set()})
        # ...A CHAT IS ITS CONVERSATION, not the account it came by: a WhatsApp or Teams connection's name is the same on every chat of
        # every hat (a live run, 2026-11-01: all of one owner's chats sat under one account name)
        if ch == 'github': t['repos'].add(src)
        elif ch and ch != 'email' and m.get('ConversationId'): t['sources'].add(str(m['ConversationId']).lower())
        own = _own(m)
        who = _recipients(m) if own else [str(m.get('FromEmail') or '').lower()]
        # ...a person is an address, or a chat's own sender id (`whatsapp:...`) - never the owner, never a machine
        t['people'] |= {a for a in who if a and ('@' in a or ':' in a) and a not in me and a not in machine}
        if own:
            t['own'] = True
            t['days'].add(str(m.get('SentAt') or '')[:10])          # a chat is one long conversation: the days the owner wrote in it count
            if (w := ' '.join(str(m.get('BodyText') or '').split())[:200]): t['lines'].append(w)
        if m.get('Subject'): t['subjects'].add(re.sub(r'^\s*((re|fw|fwd)\s*:\s*)+', '', str(m['Subject']), flags=re.I)[:80])
    return [t for t in th.values() if t['people'] or t['sources'] or t['repos']]


# ── 2. CLUSTER ────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────
def _nodes(t) -> list: return [f'p|{x}' for x in sorted(t['people'])] + [f'c|{x}' for x in sorted(t['sources'])] + [f'r|{x}' for x in sorted(t['repos'])]
def _of(c, kind) -> list: return sorted(n[2:] for n in c if n.startswith(kind + '|'))


def cluster(threads: list, rounds: int = 12) -> list:
    """Groups of nodes (people, chat groups/mailboxes as `channel:name`, repos as `repo:name`) by weighted label propagation over the
    threads they share. Deterministic: ties go to the smaller label. Only nodes the owner wrote to, or that share an owner's thread,
    are placed - a sender who only ever wrote in is no evidence of a hat."""
    w = defaultdict(Counter)
    owned = set()
    for t in threads:
        ns, k = _nodes(t), OWN_W if t['own'] else IN_W
        if t['own']: owned |= set(ns)
        for a in ns:
            for b in ns:
                if a != b: w[a][b] += k
            w[a][a] += 0
    nodes = sorted(n for n in w if n in owned)
    lab = {n: n for n in nodes}
    for _ in range(rounds):
        moved = False
        for n in nodes:
            score = Counter()
            for m, x in w[n].items():
                if m in lab: score[lab[m]] += x
            if not score: continue
            best = min(score.items(), key=lambda kv: (-kv[1], kv[0]))[0]
            if best != lab[n] and score[best] > score.get(lab[n], 0): lab[n], moved = best, True
        if not moved: break
    g = defaultdict(set)
    for n, l in lab.items(): g[l].add(n)
    return sorted(g.values(), key=lambda s: (-len(s), min(s)))


def groups(threads: list) -> list:
    """[{id, people, sources, repos, domains, own, lines, subjects}] - the clusters the owner wrote in at least MIN_OWN threads of."""
    out = []
    for i, c in enumerate(cluster(threads)):
        ts = [t for t in threads if set(_nodes(t)) & c]
        own = [t for t in ts if t['own']]
        n_own = sum(max(1, len(t.get('days') or ())) for t in own)
        if n_own < MIN_OWN: continue
        people = _of(c, 'p')
        dom = Counter(p.split('@')[1] for p in people if '@' in p)
        out.append({'id': f'g{i + 1}', 'people': people, 'sources': _of(c, 'c'),
                    'repos': _of(c, 'r'), 'domains': [d for d, k in dom.most_common() if k >= 2],
                    'own': n_own, 'lines': [l for t in own for l in t['lines']][:SAMPLE], 'subjects': sorted({s for t in own for s in t['subjects']})[:SAMPLE]})
    out.sort(key=lambda g: -g['own'])
    # ...a domain belongs to one group only: shared by two, it decides nothing (workstreams.by_signals reads only a unique one too)
    seen = Counter(d for g in out for d in g['domains'])
    for g in out: g['domains'] = [d for d in g['domains'] if seen[d] == 1]
    return out[:MAX_GROUPS]


# ── 3. NAME ───────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────
SYSTEM = (
    "You read groups of an owner's correspondence - each group is the people, chat groups and repositories that share the threads the "
    "owner wrote on, with a sample of the owner's own sent words and subjects - and say which WORKSTREAMS the owner has: separate bodies "
    "of work, each with its own people and purpose (a day job at one or more companies, a side product, a board seat, a client, their "
    "personal life). Several groups may be one workstream: merge them. Never invent a workstream no group shows. Mark one personal when "
    "it is the owner's own life - family, friends, home - not work.\n"
    "For each workstream write `section`: 3-8 markdown bullets in the owner's first person - what this work is and my role in it; who "
    "the people are TO ME (by name or address, with their role); the systems, chats and repositories it runs on; what is live THIS "
    "SEASON with a date where the mail gives one; the cadence. Never quote a message; never name a customer, patient or resident. A "
    "personal workstream gets no section. `sure`: true only when the groups leave no doubt this is a distinct workstream.\n"
    'Answer JSON: {"workstreams": [{"groups": ["g1", ...], "name": "...", "about": "one line", "personal": false, "sure": true, '
    '"section": "- ...\\n- ..."}]}')
WANT = {'name': 'workstreams', 'schema': {'type': 'object', 'additionalProperties': False, 'required': ['workstreams'], 'properties': {
    'workstreams': {'type': 'array', 'items': {'type': 'object', 'additionalProperties': False,
                    'required': ['groups', 'name', 'about', 'personal', 'sure', 'section'], 'properties': {
                        'groups': {'type': 'array', 'items': {'type': 'string'}}, 'name': {'type': 'string'}, 'about': {'type': 'string'},
                        'personal': {'type': 'boolean'}, 'sure': {'type': 'boolean'}, 'section': {'type': 'string'}}}}}}}


def _evidence(gs: list) -> str:
    return '\n\n'.join(f"GROUP {g['id']} - the owner wrote on {g['own']} threads\npeople: {', '.join(g['people'][:15]) or '-'}\n"
                       f"chats and mailboxes: {', '.join(g['sources']) or '-'}\nrepositories: {', '.join(g['repos']) or '-'}\n"
                       f"subjects: {' | '.join(g['subjects']) or '-'}\nthe owner's own words:\n" + '\n'.join(f'- {l}' for l in g['lines'])
                       for g in gs)


def name(llm, gs: list, owner: str = '') -> list:
    """The model's workstreams over the groups: [{name, about, personal, sure, section, people, domains, mailboxes, channels, repos}] -
    each carrying the signals of the groups it named, only groups it was shown."""
    from .llm import ask_json
    if not gs: return []
    from .triage import takes_tokens
    # ...room for a section per workstream: at the default the answer was cut mid-section and parsed as nothing (a live run, 2026-11-01)
    a = ask_json(llm, SYSTEM, (f'The owner: {owner}\n\n' if owner else '') + _evidence(gs), want=WANT, need=('workstreams',),
                 **({'max_tokens': NAME_TOKENS} if takes_tokens(llm) else {}))
    if a.data is None: logger.warning(f'workstreams: the model named none - {a.error}')
    by, out = {g['id']: g for g in gs}, []
    for w in ((a.data or {}).get('workstreams') or []):
        mine = [by[i] for i in w.get('groups') or [] if i in by]
        if not mine or not str(w.get('name') or '').strip(): continue
        out.append({'name': w['name'], 'about': w.get('about') or '', 'personal': bool(w.get('personal')), 'sure': bool(w.get('sure')),
                    'section': '' if w.get('personal') else str(w.get('section') or '').strip(),
                    'people': sorted({p for g in mine for p in g['people']}), 'domains': sorted({d for g in mine for d in g['domains']}),
                    'channels': sorted({s for g in mine for s in g['sources']}), 'repos': sorted({r for g in mine for r in g['repos']})})
    return out


# ── 4. PROPOSE, CONFIRM ───────────────────────────────────────────────────────────────────────────────────────────────────────────────
def _mailbox_rows(store, days: int) -> list:
    """A fresh install holds little history yet: the connected mailboxes' own six months (histgen.sent_mail - Graph, Gmail, IMAP), as
    message rows. [] when nothing is connected or the read fails."""
    try:
        from .histgen import sent_mail, cut_quoted
        sent, inbox, _n, _how = sent_mail(store, days)
    except Exception as e:
        logger.info(f'workstreams: no mailbox history read - {e}'); return []
    def addr(p): return (((p or {}).get('emailAddress') or {}).get('address') or '').lower()
    rows = [{'MessageId': f's{i}', 'ConversationId': m.get('conversationId'), 'Channel': 'email', 'SourceName': m.get('mailbox'),
             'Subject': m.get('subject'), 'Direction': 'out', 'Status': 'context', 'RecipientsJson': json.dumps([addr(r) for r in m.get('toRecipients') or []]),
             'BodyText': cut_quoted(str((m.get('body') or {}).get('content') or ''))[:300]} for i, m in enumerate(sent)]
    rows += [{'MessageId': f'i{i}', 'ConversationId': m.get('conversationId'), 'Channel': 'email', 'SourceName': m.get('mailbox'),
              'Subject': m.get('subject'), 'Direction': 'in', 'FromEmail': addr(m.get('from'))} for i, m in enumerate(inbox)]
    return rows


def propose(store, llm, days: int = DAYS, rows=None) -> list:
    """Read the window, name its workstreams, keep them as PROPOSED (the confirm screen and the Advisor's cards read them). An existing
    workstream with the same slug is merged, never duplicated or overwritten. Returns the proposals. The app's own record is read; where
    it holds little of the owner's own mail yet (a fresh install), the connected mailboxes' six months are read as well."""
    if rows is None:
        rows = store._rows(
            "SELECT MessageId, ConversationId, Channel, SourceName, Subject, FromName, FromEmail, RecipientsJson, Direction, Status, SenderClass, SentAt, "
            "substr(BodyText, 1, 300) BodyText FROM message WHERE SentAt>=? AND IFNULL(Channel,'') NOT IN ('assistant','own') ORDER BY SentAt", (_ago(days),))
        if sum(1 for r in rows if _own(r)) < 50: rows = rows + _mailbox_rows(store, days)
    gs = groups(gather(store, days, rows))
    got = name(llm, gs, store.owner().get('owner') or '')
    have = {w['slug'] for w in W.streams(store, True)}
    out = []
    for w in got:
        slug = W.slugify(w['name'])
        W.upsert(store, {**w, 'slug': slug, 'status': 'active' if slug in have else 'proposed'}, 'wsboot')
        store.set_setting(f'workstream_draft:{slug}', w['section'], 'wsboot')
        out.append({**w, 'slug': slug})
    store.set_setting(STATE_KEY, json.dumps({'at': _now().strftime('%Y-%m-%d %H:%M:%S'), 'days': days, 'groups': len(gs), 'named': len(got)}), 'wsboot')
    return out


def proposals(store) -> list:
    return [{**w, 'section': store.get_setting(f'workstream_draft:{w["slug"]}') or ''} for w in W.streams(store, True) if w['status'] == 'proposed']


def confirm(store, items: list, actor: str = 'owner') -> list:
    """The owner's answer on the setup screen (or an Advisor card): each item {slug, name?, personal?, keep}. A kept one is active, renamed
    as they typed it, its section written into JOB.md; one not kept is removed. Returns the active workstreams."""
    xs = {w['slug']: w for w in W.streams(store, True)}
    for it in items or []:
        w = xs.get(it.get('slug'))
        if not w: continue
        if not it.get('keep', True): W.remove(store, w['slug'], actor); continue
        # ...one already kept, answered again from About you, keeps its status (a quiet one stays put by) and its section as JOB.md has
        # it: the draft written at setup would go over the owner's own edits there
        had = W.section(store, w['slug'])
        new = w['status'] == 'proposed'
        w = {**w, 'name': ' '.join(str(it.get('name') or w['name']).split()) or w['name'], 'status': 'active' if new else w['status'],
             'personal': bool(it.get('personal', w['personal']))}
        xs2 = [x if x['slug'] != w['slug'] else w for x in W.streams(store, True)]
        W.save(store, xs2, actor)
        sec = store.get_setting(f"workstream_draft:{w['slug']}") or ''
        if sec and not w['personal'] and not had: W.write_section(store, w['slug'], sec, actor)
    return W.streams(store)


# ── KEPT CURRENT: the weekly refresh, quiet workstreams, and new sources ─────────────────────────────────────────────────────────────
REFRESH = ("You keep one section of an owner's JOB.md current. You are given the section as it is and the owner's own recent words in "
           "this workstream. Rewrite the section: keep what still holds, add new people (with their role to the owner) and what is live "
           "THIS SEASON with dates, and drop goals whose date has passed. 3-8 markdown bullets, the owner's first person. Never quote a "
           "message; never name a customer, patient or resident. Answer only the section.")


def refresh(store, llm, days: int = RECENT_DAYS) -> dict:
    """Each active workstream's section rewritten from its last `days`; one with no owner activity in QUIET_DAYS goes quiet (its index
    line stays, its section leaves readers' prompts until it wakes), a quiet one with activity wakes. {slug: 'refreshed'|'quiet'|'woke'}."""
    out, xs = {}, W.streams(store)
    for w in xs:
        if w['personal']: continue
        own = store._rows("SELECT substr(BodyText,1,240) b FROM message WHERE Workstream=? AND (Direction='out' OR Status='context') AND SentAt>=? "
                          "ORDER BY SentAt DESC LIMIT 20", (w['slug'], _ago(QUIET_DAYS)))
        if not own:
            if w['status'] == 'active': w['status'] = 'quiet'; out[w['slug']] = 'quiet'
            continue
        if w['status'] == 'quiet': w['status'] = 'active'; out[w['slug']] = 'woke'
        recent = store._rows("SELECT substr(BodyText,1,240) b FROM message WHERE Workstream=? AND (Direction='out' OR Status='context') AND SentAt>=? "
                             "ORDER BY SentAt DESC LIMIT 15", (w['slug'], _ago(days)))
        if not recent or llm is None: continue
        try:
            new = str(llm(REFRESH, f"THE SECTION:\n{W.section(store, w['slug'])}\n\nTHE OWNER'S RECENT WORDS:\n"
                                   + '\n'.join(f"- {' '.join(str(r['b'] or '').split())}" for r in recent)) or '').strip()
        except Exception as e:
            logger.warning(f"workstream {w['slug']} not refreshed: {e}"); continue
        if new and '<!--' not in new and len(new) < 4000: W.write_section(store, w['slug'], new, 'wsrefresh'); out[w['slug']] = 'refreshed'
        # ...and how the owner writes there, where it differs from the shared style (stylews, S9 - an option the owner can switch off)
        from . import stylews
        if stylews.on(store): stylews.write(store, llm, w['slug'])
    if out: W.save(store, xs, 'wsrefresh')
    return out


def new_sources(store) -> list:
    """Sources (a mailbox, a chat group, a report, a repository) with SOURCE_MIN messages in the last month, never judged before, whose
    messages no workstream places: what a new connector or GitHub project brought. [(channel, name)]."""
    try: seen = set(json.loads(store.get_setting('workstreams_sources_seen') or '[]'))
    except ValueError: seen = set()
    xs, out = W.streams(store, True), []
    # ...NEW: its first message is recent - a mailbox or chat that has always been here was read by the bootstrap, and the owner's main
    # mailbox, which serves every hat, must never become one hat's
    for r in store._rows("SELECT Channel, SourceName, COUNT(*) n, MIN(CreatedAt) first FROM message WHERE IFNULL(SourceName,'')<>'' AND "
                         "IFNULL(Channel,'') NOT IN ('assistant','own') GROUP BY Channel, SourceName HAVING n>=? AND first>=?",
                         (SOURCE_MIN, _ago(NEW_DAYS))):
        k = f"{str(r['Channel']).lower()}:{str(r['SourceName']).lower()}"
        if k in seen: continue
        ms = store._rows('SELECT * FROM message WHERE Channel=? AND SourceName=? ORDER BY MessageId DESC LIMIT 30', (r['Channel'], r['SourceName']))
        placed = sum(1 for m in ms if W.by_signals(xs, m)[0])
        if placed * 2 < len(ms): out.append((r['Channel'], r['SourceName']))
    return out


def judge_sources(store, llm) -> list:
    """Each new source's traffic, named the same way: a workstream the model is SURE of is added and said in an Advisor idea; one it
    is not sure of is proposed as an Advisor card (Add it / No). A source whose traffic is an existing workstream's is placed there."""
    srcs = new_sources(store)
    if not srcs: return []
    try: seen = set(json.loads(store.get_setting('workstreams_sources_seen') or '[]'))
    except ValueError: seen = set()
    done = []
    for ch, src in srcs:
        seen.add(f'{str(ch).lower()}:{str(src).lower()}')
        rows = store._rows("SELECT MessageId, ConversationId, Channel, SourceName, Subject, FromName, FromEmail, RecipientsJson, Direction, Status, "
                           "SenderClass, SentAt, substr(BodyText,1,300) BodyText FROM message WHERE Channel=? AND SourceName=? AND SentAt>=?", (ch, src, _ago(DAYS)))
        gs = groups(gather(store, DAYS, rows)) or [{'id': 'g1', 'people': [], 'sources': [f'{str(ch).lower()}:{str(src).lower()}'] if ch not in ('email', 'github') else [],
                                                   'repos': [str(src).lower()] if ch == 'github' else [], 'domains': [], 'own': 0, 'lines': [],
                                                   'subjects': sorted({str(r.get('Subject') or '')[:80] for r in rows})[:SAMPLE]}]
        if ch == 'email': gs = [{**g, 'sources': g['sources']} for g in gs]
        for w in name(llm, gs, store.owner().get('owner') or ''):
            slug = W.slugify(w['name'])
            if ch == 'email': w = {**w, 'mailboxes': [str(src).lower()]}
            existing = W.get(store, slug)
            status = 'active' if existing and existing['status'] != 'proposed' else 'active' if w['sure'] else 'proposed'
            W.upsert(store, {**w, 'slug': slug, 'status': status}, 'wsboot')
            store.set_setting(f'workstream_draft:{slug}', w['section'], 'wsboot')
            if status == 'active' and not existing and w['section'] and not w['personal']: W.write_section(store, slug, w['section'], 'wsboot')
            card(store, slug, added=status == 'active' and not existing)
            done.append((slug, status))
    store.set_setting('workstreams_sources_seen', json.dumps(sorted(seen)), 'wsboot')
    return done


def card(store, slug: str, added: bool = False) -> dict | None:
    """The Advisor's card for a workstream it found (the owner, 2026-11-01: after setup, confirmed through an Advisor card, no extra
    screen): `added` says it was sure and added it - Undo is No; else it asks - Add it / No. Never repeated after No."""
    w = W.get(store, slug)
    if not w: return None
    key = f'idea:workstream-{slug}'
    old = store._one('SELECT Status FROM idea WHERE Key=?', (key,))
    if old and old['Status'] == 'dismissed': return None
    text = (f"New workstream added: {w['name']}" if added else f"Is {w['name']} a separate workstream of yours?") + (f" - {w['about']}" if w['about'] else '')
    return store.upsert_idea({'key': key, 'kind': 'workstream', 'text': text, 'sig': f"{slug}:{'added' if added else 'ask'}",
                              'action': {'type': 'workstream', 'slug': slug, 'added': added, 'whose': 'the owner',
                                         'suggest': 'Keep it' if added else 'Add it as a workstream'}}, _now().strftime('%Y-%m-%d %H:%M:%S'))


def answer_card(store, idea: dict, yes: bool, actor: str = 'owner') -> dict:
    """The owner's Add it (yes) or No on a workstream card: yes activates it and writes its section; No removes a proposed one, or one the
    Advisor added on its own. Returns {slug, kept}."""
    try: a = json.loads(idea.get('ActionJson') or '{}') or {}
    except ValueError: a = {}
    slug = a.get('slug')
    w = W.get(store, slug) if slug else None
    if not w: return {'slug': slug, 'kept': False}
    if yes:
        confirm(store, [{'slug': slug, 'keep': True}], actor)
        return {'slug': slug, 'kept': True}
    if w['status'] == 'proposed' or a.get('added'): W.remove(store, slug, actor)
    return {'slug': slug, 'kept': False}


def tick(store, llm=None, force: bool = False) -> dict:
    """Each section refreshed once a week at most (or `force`), and any NEW SOURCE judged whenever one has traffic - the clock Advisor
    calls this every pass, so a connector added this morning is noticed once its mail is in. Never raises."""
    try:
        if not W.streams(store, True): return {}
        last = store.get_setting('workstreams_refreshed_at') or ''
        due = force or not last or last <= _ago(REFRESH_DAYS)
        fresh = new_sources(store)
        if not due and not fresh: return {}
        if llm is None:
            from .llm import build_llm
            llm = build_llm(store, job='summary')
        if llm is None: return {}
        out = {'sources': judge_sources(store, llm) if fresh else []}
        if due:
            out['refresh'] = refresh(store, llm)
            store.set_setting('workstreams_refreshed_at', _now().strftime('%Y-%m-%d %H:%M:%S'), 'wsboot')
        return out
    except Exception as e:
        logger.warning(f'workstreams not kept current: {e}'); return {}
