"""THE LEDGER: one record of what EXISTS because an act landed - a mail that went, an act that went live, an account a site took, an address
the owner gave or mailed to, a file he attached, a promise he made in his sent mail.

Nothing kept this before (the design review, 2026-11-23): every tool re-derived "what exists" from its own store - the vault's LastUsed, his
lines scanned for an address, the review rows read with one predicate in five places - and the same failure ("the next task did not know")
was patched one door at a time. Here it is written ONCE, by the act that confirmed it, and every reader asks this.

A row: Kind (KINDS), Subject (whom or what it is about: an address, a site, a file, the recipients), Value (what it says: a subject line, the
line he gave an address in, a link), Act (what wrote it), Ref (the act's own id - rv12, c40, t7), TaskId, Thread (the conversation it is on),
At, Detail (JSON). Written only by a confirmed act: a send whose provider receipt came back, a sign-in or sign-up the site let past, a line he
typed, a promise task the reading made. A sign-up that failed writes nothing; one whose form the site took but has not yet let in writes
act 'made' (signin.MADE), which confirms no saved sign-in. One row per (Kind, Subject, Act, Ref): an act told twice is one row.
"""
import json, re
from .store import _now, task_ref

KINDS = ('sent', 'act', 'address', 'account', 'file', 'promise')
ADDR = re.compile(r'[\w.+-]+@[\w-]+(?:\.[\w-]+)+')
_SENT = ("(DeliveryState='sent' OR (DeliveryState IS NULL AND Status IN ('approved','edited','sent'))) "
         "AND COALESCE(NULLIF(FinalText,''), DraftText, '')<>''")


def _table(store):
    if getattr(store, '_ledger_ok', None) is store.cx: return
    with store.lock:
        new = not store.cx.execute("SELECT 1 FROM sqlite_master WHERE type='table' AND name='ledger'").fetchone()
        store.cx.execute('CREATE TABLE IF NOT EXISTS ledger (LedgerId INTEGER PRIMARY KEY, Kind TEXT, Subject TEXT, Value TEXT, Act TEXT, Ref TEXT, '
                         'TaskId INTEGER, Thread TEXT, At TEXT, Detail TEXT, UNIQUE(Kind, Subject, Act, Ref))')
        for c in ('Kind, Subject', 'TaskId', 'Thread'): store.cx.execute(f"CREATE INDEX IF NOT EXISTS ledger_{c.split(',')[0].lower()} ON ledger({c})")
        store.cx.commit()
    store._ledger_ok = store.cx
    if new: _backfill(store)


def write(store, kind, subject, value='', act='', ref='', task=None, thread=None, detail=None, at=None, fresh=False) -> bool:
    """One row for an act that landed. False where it was already written - or, `fresh`, the row brought up to this act (a sign-in that went
    in again is the newest word on its account). An unknown kind is a programming error."""
    if kind not in KINDS: raise ValueError(f'not a ledger kind: {kind}')
    _table(store)
    on = ' ON CONFLICT(Kind, Subject, Act, Ref) DO UPDATE SET Value=excluded.Value, TaskId=COALESCE(excluded.TaskId, TaskId), At=excluded.At' if fresh else ''
    with store.lock:
        cur = store.cx.execute(f"INSERT{'' if fresh else ' OR IGNORE'} INTO ledger (Kind,Subject,Value,Act,Ref,TaskId,Thread,At,Detail) VALUES (?,?,?,?,?,?,?,?,?){on}",
                               (kind, str(subject or '').strip().lower() if kind in ('address', 'account') else str(subject or '').strip(),
                                str(value or '')[:600], act, str(ref or ''), int(task) if str(task or '').isdigit() else None,
                                str(thread) if thread else None, at or _now(), json.dumps(detail) if detail else None))
        store.cx.commit()
    return bool(cur.rowcount)


def rows(store, kind=None, subject=None, task=None, thread=None, since=None, act=None, limit=400) -> list:
    "The rows that match, newest first. `task`/`thread`/`subject` may each be one value or several."
    _table(store)
    where, args = [], []
    def any_of(col, v):
        vs = [x for x in (v if isinstance(v, (list, tuple, set)) else [v]) if x not in (None, '')]
        where.append(f"{col} IN ({','.join('?' * len(vs))})" if vs else '0'); args.extend(vs)
    for col, v in (('Kind', kind), ('Subject', subject), ('TaskId', task), ('Thread', thread), ('Act', act)):
        if v is not None: any_of(col, v)
    if since: where.append('At>=?'); args.append(str(since))
    out = store._rows(f"SELECT * FROM ledger{' WHERE ' + ' AND '.join(where) if where else ''} ORDER BY At DESC, LedgerId DESC LIMIT ?", (*args, limit))
    for r in out:
        try: r['detail'] = json.loads(r.get('Detail') or '{}') or {}
        except ValueError: r['detail'] = {}
    return out


# ── the writers: each is called by the one act that confirms it ─────────────────────────────────────────────────────────────
def _env(raw) -> dict:
    try: d = json.loads(raw or '{}') or {}
    except (TypeError, ValueError): d = {}
    return d if isinstance(d, dict) else {}


def sent(store, rid, at=None) -> None:
    """A review whose send came back with a receipt (store.finish_review_delivery 'sent'): the mail - or the act - that went, the people it
    reached, the files it carried, and an act's link where its receipt gave one."""
    rv = store.get_review(int(rid))
    if not rv: return
    env = {**_env(rv.get('Deliver')), **(_env(rv.get('DeliveryEnvelope')).get('envelope') or {})}
    got = _env(rv.get('DeliveryReceipt'))
    m = store.get_message(rv.get('AnswersMid') or rv.get('MessageId')) if (rv.get('AnswersMid') or rv.get('MessageId')) else None
    to = [str(a).strip().lower() for a in (got.get('to') or env.get('to') or ([m.get('FromEmail')] if m and m.get('FromEmail') else [])) if a]
    cc = [str(a).strip().lower() for a in (got.get('cc') or env.get('cc') or []) if a]
    tid, ref, when = rv.get('TaskId'), f"rv{rv['ReviewId']}", at or rv.get('DecidedAt') or _now()
    thread = (m or {}).get('ConversationId') or got.get('conversation_id') or got.get('thread')
    files = [str(f) for f in got.get('attached') or [f.get('name') for f in env.get('attachments') or [] if isinstance(f, dict)] if f]
    if rv.get('Kind') == 'action': return                       # an act's record is went's, written where it ran
    subj = ' '.join(str(env.get('subject') or (m or {}).get('Subject') or '').split())[:200]
    write(store, 'sent', ', '.join(to) or str(got.get('channel') or env.get('channel') or ''), subj, 'sent', ref, tid, thread,
          {'to': to, 'cc': cc, 'kind': rv.get('Kind'), 'channel': got.get('channel') or env.get('channel'), 'files': files}, at=when)
    for a in dict.fromkeys(to + cc):
        if '@' in a: write(store, 'address', a, subj, 'mailed', ref, tid, thread, at=when)
    for f in files: write(store, 'file', f, subj, 'sent', ref, tid, thread, at=when)


def _link(out) -> str:
    "The place an act landed, by its executor's own answer: a link on it, or on its first row."
    if not isinstance(out, dict): return ''
    rs = out.get('rows') if isinstance(out.get('rows'), list) else []
    for d in (out, out.get('result') if isinstance(out.get('result'), dict) else {}, rs[0] if rs and isinstance(rs[0], dict) else {}):
        if (u := next((str(d[k]) for k in ('url', 'link', 'permalink', 'href') if d.get(k)), '')): return u
    return ''


def went(store, rid, out=None, at=None) -> bool:
    "An act the owner approved that RAN (verdicts: its executor answered) - a post, a payment, an order - with its link where it gave one."
    rv = store.get_review(int(rid)) or {}
    if not rv: return False
    try: p = json.loads(rv.get('FinalText') or rv.get('DraftText') or '{}') or {}
    except ValueError: p = {}
    p = p if isinstance(p, dict) else {}
    link, what = _link(out if out is not None else p.get('result')), ' '.join(str(rv.get('Reason') or p.get('type') or p.get('action') or 'an act').split())[:300]
    return write(store, 'act', link or what, link, 'went', f"rv{rv['ReviewId']}", rv.get('TaskId'), None,
                 {'what': what, 'type': p.get('type') or p.get('action') or ''}, at=at or rv.get('DecidedAt'))


def account(store, site, user='', act='signed_in', task=None, by='agent') -> bool:
    "An account that exists at `site`: one a site let a sign-in or sign-up past, or the owner's own he saved (act 'given')."
    return write(store, 'account', site, user, act, site, task, detail={'by': by}, fresh=True)


def his_line(store, tid, body, files=None, at=None) -> None:
    """A line the owner typed (on any door that keeps one: the chat, New, the phone, a coding note): the addresses he gave in it and the files
    he attached - one row each per task. Reading an address out of a line is its structure, not its meaning."""
    if not tid: return
    for line in str(body or '').splitlines():
        for a in ADDR.findall(line): write(store, 'address', a.lower(), line.strip()[:300], 'given', f't{tid}', tid, at=at)
    from pathlib import Path
    for f in files or []: write(store, 'file', str(f), Path(str(f)).name, 'attached', f't{tid}', tid, at=at)


def owner_line(store, tid, actor, actor_type, body, files=None, at=None) -> None:
    """store.add_comment's door: a comment that is a line of HIS (never a brief Taskuary handed the agent in his voice) is his_line - on the
    Assistant's chat too, and on the task that chat's turn was about (concierge._mirror): a photo sent from the phone is his file there."""
    from .general import BRIEF_ACTOR, USER_TYPE, WAITING_TYPE, line_said
    from .concierge import DISCUSSION_USER_TYPE
    # ...as he typed it (general.line_said): a line kept for a turn is its JSON, and its row read `{"text": ..., "after": 2}` (walk 10, 2026-11-23)
    if actor_type in (USER_TYPE, WAITING_TYPE) and not (actor_type == USER_TYPE and actor == BRIEF_ACTOR):
        his_line(store, tid, line_said({'ActorType': actor_type, 'Body': body})['text'], files, at)
    # ...the mirror's line may be a press's label over the row's title, not his words: only what he attached is his there
    elif actor_type == DISCUSSION_USER_TYPE and files: his_line(store, tid, '', files, at)


def promise(store, tid, mid, what, due=None) -> bool:
    "A promise the owner made in his sent mail (store.task_for_promise - the reading found it): to whom, on which thread, by when."
    m = store.get_message(int(mid)) or {}
    other = store.last_inbound_in(m['ConversationId']) if m.get('ConversationId') else None
    return write(store, 'promise', str((other or {}).get('FromEmail') or '').lower(), what, 'promised', f'm{mid}', tid, m.get('ConversationId'),
                 {'due': due} if due else None)


def _backfill(store):
    """A home from before the ledger: its record written once, from the acts its stores already confirm - the same facts the readers
    read before they read this."""
    from . import general
    for r in store._rows(f'SELECT ReviewId, DecidedAt FROM review WHERE {_SENT}'):
        try: sent(store, r['ReviewId'], at=r.get('DecidedAt'))
        except Exception: continue
    from .cardqueue import handed                       # ...an act his press handed to its agent and not yet done has not gone
    for r in store._rows("SELECT * FROM review WHERE Kind='action' AND Status IN ('approved','edited')"):
        try: handed(r) or went(store, r['ReviewId'], at=r.get('DecidedAt'))
        except Exception: continue
    if store._one("SELECT 1 AS x FROM sqlite_master WHERE type='table' AND name='signin_vault'"):
        for r in store._rows("SELECT Site, SavedBy, LastUsed, Task FROM signin_vault WHERE LastUsed IS NOT NULL OR IFNULL(SavedBy,'owner') NOT IN ('taskuary','agent')"):
            account(store, r['Site'], act='signed_in' if r.get('LastUsed') else 'given', task=r.get('Task'), by='owner' if r.get('SavedBy') not in ('taskuary', 'agent') else 'agent')
    from .store import files_of
    for c in store._rows("SELECT TaskId, Actor, ActorType, Body, Files, CreatedAt FROM comment WHERE ActorType IN (?,?) AND (Body LIKE '%@%' OR Files IS NOT NULL)",
                         (general.USER_TYPE, general.WAITING_TYPE)):
        owner_line(store, c['TaskId'], c['Actor'], c['ActorType'], c['Body'], files_of(c), c.get('CreatedAt'))
    for t in store._rows("SELECT TaskId, Summary, Files, OriginBase, CreatedAt FROM task WHERE OriginBase='owner' OR Files IS NOT NULL"):
        his_line(store, t['TaskId'], t['Summary'] if t.get('OriginBase') == 'owner' else '', files_of(t), at=t.get('CreatedAt'))
    for t in store._rows("SELECT TaskId, Title, SourceRef, DueAt FROM task WHERE SourceRef LIKE 'promise:%'"):
        try: promise(store, t['TaskId'], int(t['SourceRef'].split(':', 1)[1]), t['Title'], t.get('DueAt'))
        except (ValueError, TypeError): continue


# ── the readers ────────────────────────────────────────────────────────────────────────────────────────────────────────
def given(store, tid=None) -> list:
    "(address, the line it stands in) for every address the owner gave in his own words - on task `tid`, else on any task, newest first."
    return [(r['Subject'], r['Value']) for r in rows(store, 'address', task=tid, act='given')]


def mailed(store) -> dict:
    "{address: (times, last)} of everyone mail Taskuary sent reached - read back before the provider's copy of it is ever ingested."
    out = {}
    for r in rows(store, 'address', act='mailed', limit=3000):
        n, last = out.get(r['Subject'], (0, ''))
        out[r['Subject']] = (n + 1, max(last, str(r['At'] or '')))
    return out


def sites(store) -> dict:
    "{site: newest account row} - the sites an account is known to exist on."
    out = {}
    for r in rows(store, 'account', limit=2000): out.setdefault(r['Subject'], r)
    return out


def accounts(store) -> str:
    """The accounts its browser can sign in to, as an agent is told them (docsync.agent_systems): every saved sign-in by site and user name,
    who made it and whether a site has taken it yet - so the next task knows the inbox an earlier one made. Never a password."""
    from . import signin
    saved = signin.listing(store)
    if not saved: return ''
    def say(r):
        made = f"made by the agent on {r['ref']}" if r.get('ref') else 'made by an agent' if r['by'] == 'agent' else "the owner's own"
        return f"{r['site']}" + (f" as {r['user']}" if r['user'] else '') + f" ({made}{'' if r['confirmed'] else ', not signed in with yet'})"
    return 'SAVED SIGN-INS (Taskuary types the password - hand_over with the site signs in; you never see one): ' + '; '.join(map(say, saved[:30]))


def review_of(store, r) -> dict | None:
    "The review a sent row's mail went out on - its words are the send's own, kept there."
    ref = str(r.get('Ref') or '')
    return store.get_review(int(ref[2:])) if ref.startswith('rv') and ref[2:].isdigit() else None


def _people_of(store, tid) -> set:
    return {str(m.get('FromEmail') or '').lower() for m in store.list_messages(int(tid)) if m.get('FromEmail') and m.get('Status') != 'context'} - {''}


def sent_here(store, tid, limit=6) -> list:
    """The mail that went on this task, and on its thread or to its people from ANY task - newest first. A mail sent from one task is the
    next task's fact too: its agent on the same thread must not write the same letter again (the review, 2026-11-23)."""
    threads = {m['ConversationId'] for m in store.list_messages(int(tid)) if m.get('ConversationId')}
    who, out = _people_of(store, tid), []
    for r in rows(store, 'sent', limit=400):
        on = r.get('TaskId') == int(tid) or (r.get('Thread') and r['Thread'] in threads) or bool(who & set(r['detail'].get('to') or []))
        if on: out.append(r)
        if len(out) >= limit: break
    return out


def of_task(store, tid) -> list:
    "What this task MADE and was given, as lines: mail it sent, acts that went live, accounts its agent made, files he attached, addresses he gave."
    return [said(r) for r in rows(store, task=int(tid), limit=60)]
# ONE ROW, SAID ONE WAY wherever it is read (the task's record, the owner's memory): an address row says the address and how it is known -
# never the line or subject it was found under (walk 10, 2026-11-23: memory read `gail@... <Q3 board pack>` as a fact about her)
SAY = {'sent': lambda r: f"sent \"{r['Value'] or 'a mail'}\" to {r['Subject']} ({r['At']})",
       'act': lambda r: f"went live: {r['detail'].get('what') or r['Subject']}" + (f" - {r['Value']}" if r['Value'] else '') + f" ({r['At']})",
       'account': lambda r: f"an account on {r['Subject']}" + (f" as {r['Value']}" if r['Value'] else '') + f" ({r['Act'].replace('_', ' ')})",
       'file': lambda r: f"file {r['Value'] or r['Subject']} ({r['Act']})",
       'address': lambda r: f"address {r['Subject']} ({'he gave it' if r['Act'] == 'given' else 'mailed'})",
       'promise': lambda r: f"he promised {r['Subject'] or 'them'}: {r['Value']}"}
def said(r) -> str: return SAY[r['Kind']](r)


def person(store, address: str, limit=8) -> list:
    "What the record holds on one person: the mail that went to them, from which task, the addresses he gave for them, his promises to them."
    a = str(address or '').strip().lower()
    out = []
    for r in rows(store, ('address', 'promise'), subject=a, limit=limit * 3):
        on = f" on {task_ref(r['TaskId'])}" if r.get('TaskId') else ''
        out.append(f"he gave this address{on}: {r['Value']}" if r['Act'] == 'given' else f"he promised them{on}: {r['Value']}" if r['Kind'] == 'promise'
                   else f"mailed{on} ({r['At']}): \"{r['Value'] or '(no subject)'}\"")
    return list(dict.fromkeys(out))[:limit]


def find(store, words, limit=12) -> list:
    "Rows whose subject or value holds every word - for an agent's search of what exists."
    ws = [w.lower() for w in words if w]
    if not ws: return []
    hits = [r for r in rows(store, limit=2000) if all(w in f"{r['Subject']} {r['Value']}".lower() for w in ws)]
    return [f"{r['Kind']}: {r['Subject']}" + (f" - {r['Value']}" if r['Value'] and r['Value'] != r['Subject'] else '')
            + (f" ({task_ref(r['TaskId'])})" if r.get('TaskId') else '') for r in hits[:limit]]
