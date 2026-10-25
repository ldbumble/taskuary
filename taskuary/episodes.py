"""EPISODES - what the owner DID, written out with its context, for the reflection to learn from (the memory redesign, 2026-10-25).

The memory learned which button was pressed and called it a habit: "On asks from X, presses Next (1 of 1)" (the owner: "a button press
is not a fact about a person"). An episode is one act of the owner's with what surrounded it - who wrote, what they are to the owner,
what it was about, what triage made of it, what the owner did and how soon, and what came of it:

    msg455 2026-10-20 · erin@northwind.example (your manager) · "Q3 budget numbers" · triage: task · you: replied 38 min after it arrived
    fs88 2026-10-21 · renewals@payworth.example · "Renewal notice" · you: put it off to Fri 2026-10-24 09:00, 2h after it arrived
    task91 2026-10-21 · east.manager@northwind.example · "Payroll correction" · you: handed it to ray@northwind.example, the sender on copy

Code builds them from rows that already exist and cites them by their ids, so every line the reflection writes can be traced to what
happened. Parsing addresses, times and weekdays is fact, not meaning: no word list decides anything here. What counts:

    acts       a reply (and how soon), a draft edited or rejected, a put-off with its day, a hand-off, a close, Not ours / Not a task,
               an idea taken up or dismissed, a promise in the owner's sent mail
    never      navigation - Next, open, focus: "Next" is "not now, in this walk", never a judgement (Shown is not acted on)
    excluded   personal mailboxes (presses.personal), agents' own acts, auto-replies

Evidence ids: msg (a reply to an inbound message, by its id), rv (a review decision), fs (a task put off, by the task's id), task (an
owner act on a task), idea (an Advisor idea's fate), sv (a promise in sent mail, by the sent message's id), out (an outcome row)."""
import json, re
from datetime import datetime
from loguru import logger

CAP_N, CAP_CHARS = 40, 5000          # what one reflection reads; the rest is counted, never silently cut
ACTS = ('msg', 'rv', 'fs', 'task', 'idea', 'sv', 'out', 'mem')   # evidence of something the OWNER did (or said: mem is a verdict note)


def _dt(s):
    try: return datetime.strptime(str(s or '')[:19].replace('T', ' '), '%Y-%m-%d %H:%M:%S')
    except ValueError:
        try: return datetime.strptime(str(s or '')[:10], '%Y-%m-%d')
        except ValueError: return None


def lag(a, b) -> str:
    """How long from `a` to `b`, in the words a person uses: "38 min", "3h", "2 days"."""
    x, y = _dt(a), _dt(b)
    if not x or not y or y < x: return ''
    m = int((y - x).total_seconds() // 60)
    return f'{m} min' if m < 90 else f'{round(m / 60)}h' if m < 36 * 60 else f'{round(m / 1440)} days'


def _day(s) -> str:
    d = _dt(s)
    return d.strftime('%a %Y-%m-%d %H:%M') if d else str(s or '')


def _relation(store, email: str) -> str:
    try:
        from . import orgchart
        r = orgchart.relation_of(store, email)
        return f' ({r})' if r else ''
    except Exception: return ''


def _mine(store) -> set:
    from .ingest import owner_addresses
    own = (store.get_setting('owner_email') or '').strip().lower()
    return ({own} if own else set()) | owner_addresses(store)


def _skip(store, m: dict) -> bool:
    """Personal mail, an auto-reply: nothing is learned from either."""
    from .autoreply import is_auto
    from .presses import personal
    return bool(not m or is_auto(m) or personal(store, None, m))


def _triage(store, mid) -> str:
    from .categories import route_intent
    r = store._one("SELECT Reason FROM route WHERE MessageId=? AND RoutedBy!='owner' ORDER BY RouteId LIMIT 1", (mid,))
    return route_intent((r or {}).get('Reason') or '') or ''


def _head(m: dict, store) -> str:
    who = str(m.get('FromEmail') or m.get('FromName') or '?').lower()
    return f"{who}{_relation(store, who)} · \"{' '.join(str(m.get('Subject') or '').split())[:70]}\""


def build(store, since: str) -> list:
    """[(id, when, who, line)] - every episode since `since`, oldest first. `who` is the address it is about (people lines are held
    back by it, learn._fit). Never raises: an episode that cannot be read is one fewer, not a failed reflection."""
    out, me = [], _mine(store)
    try:
        ins = store._rows("SELECT * FROM message WHERE IFNULL(Direction,'in')<>'out' AND Status NOT IN ('context','skipped','history') "
                          "AND SentAt>=? ORDER BY SentAt", (since,))
        outs = store._rows("SELECT * FROM message WHERE (Direction='out' OR Status='context' OR FromName='You') AND SentAt>=? ORDER BY SentAt", (since,))
        by_conv = {}
        for o in outs: by_conv.setdefault(o.get('ConversationId'), []).append(o)
        for m in ins:
            if _skip(store, m) or str(m.get('FromEmail') or '').lower() in me: continue
            nxt = next((o for o in by_conv.get(m.get('ConversationId')) or [] if str(o.get('SentAt') or '') > str(m.get('SentAt') or '')), None)
            if not nxt: continue
            tri = _triage(store, m['MessageId'])
            out.append((f"msg{m['MessageId']}", m['SentAt'], str(m.get('FromEmail') or '').lower(),
                        f"{_head(m, store)}" + (f' · triage: {tri}' if tri else '') + f" · you: replied {lag(m['SentAt'], nxt['SentAt'])} after it arrived"))
        for r in store._rows("SELECT * FROM review WHERE DecidedBy='owner' AND Status IN ('edited','rejected','no_reply') AND IFNULL(DecidedAt,CreatedAt)>=?", (since,)):
            m = store.get_message(r['MessageId']) if r.get('MessageId') else None
            if m and _skip(store, m): continue
            did = {'edited': 'edited the draft before it went', 'rejected': 'threw the draft away', 'no_reply': 'sent no reply'}[r['Status']]
            words = ''
            if r['Status'] == 'edited': words = f" ({len(str(r.get('DraftText') or ''))} chars drafted, {len(str(r.get('FinalText') or ''))} sent)"
            out.append((f"rv{r['ReviewId']}", r.get('DecidedAt') or r.get('CreatedAt'), str((m or {}).get('FromEmail') or '').lower(),
                        f"{_head(m, store) if m else 'a draft'} · you: {did}{words}"))
        for t in store._rows("SELECT TaskId, Title, RemindAt, CreatedAt FROM task WHERE IFNULL(RemindAt,'')<>'' AND CreatedAt>=?", (since,)):
            m = next(iter(store.list_messages(t['TaskId'])), None)
            if m and _skip(store, m): continue
            st = store._one('SELECT At, Until, By FROM funnel_state WHERE Key=?', (f"task:{t['TaskId']}",)) or {}
            if st.get('By') not in (None, 'owner'): continue
            when = st.get('At') or t['CreatedAt']
            out.append((f"fs{t['TaskId']}", when, str((m or {}).get('FromEmail') or '').lower(),
                        f"{_head(m, store) if m else repr(t['Title'])} · you: put it off to {_day(st.get('Until') or t['RemindAt'])}"
                        + (f", {lag((m or {}).get('SentAt') or t['CreatedAt'], when)} after it arrived" if lag((m or {}).get('SentAt') or t['CreatedAt'], when) else '')))
        for a in store._rows("SELECT * FROM audit WHERE Action IN ('handoff','not_mine_delete','not_a_task_delete','create_from_message') "
                             "AND IFNULL(ActorType,'human')<>'agent' AND CreatedAt>=? ORDER BY Id", (since,)):
            try: d = json.loads(a.get('Detail') or '{}') or {}
            except ValueError: d = {}
            m = next(iter(store.list_messages(a['EntityId'])), None) if a['EntityType'] == 'task' else store.get_message(a['EntityId'])
            if m and _skip(store, m): continue
            did = {'handoff': f"handed it to {d.get('to') or 'someone'}" + (', the sender on copy' if (m or {}).get('FromEmail') and str(m['FromEmail']).lower() in [str(x).lower() for x in d.get('cc') or []] else ''),
                   'not_mine_delete': 'said Not ours', 'not_a_task_delete': 'said Not a task', 'create_from_message': 'made it a task by hand'}[a['Action']]
            out.append((f"task{a['EntityId']}" if a['EntityType'] == 'task' else f"msg{a['EntityId']}", a['CreatedAt'], str((m or {}).get('FromEmail') or '').lower(),
                        f"{_head(m, store) if m else a['EntityType']} · you: {did}"))
        for i in store._rows("SELECT * FROM idea WHERE DecidedBy='owner' AND Status IN ('dismissed','done','taken','accepted') AND DecidedAt>=?", (since,)):
            out.append((f"idea{i['IdeaId']}", i['DecidedAt'], '', f"Advisor idea \"{' '.join(str(i.get('Text') or '').split())[:90]}\" · you: "
                        + ('dismissed it' if i['Status'] == 'dismissed' else 'took it up') + (f" (raised {i['SaidCount']} times)" if int(i.get('SaidCount') or 0) > 1 else '')))
        for v in store._rows("SELECT v.*, m.SentAt, m.RecipientsJson FROM sent_verdict v JOIN message m ON m.MessageId=v.MessageId "
                             "WHERE v.Promise=1 AND m.SentAt>=? ORDER BY m.SentAt", (since,)):
            try: to = (json.loads(v.get('RecipientsJson') or '{}') or {}).get('to') or []
            except ValueError: to = []
            who = str(to[0] if to else '').lower()
            out.append((f"sv{v['MessageId']}", v['SentAt'], who, f"you promised {who or 'them'}{_relation(store, who)} \"{v.get('What') or 'something'}\""
                        + (f" by {v['Due']}" if v.get('Due') else '') + f" ({_day(v['SentAt'])[:3]})" + (' · then: delivered' if v.get('DeliveredBy') else '')))
        from . import outcomes
        for r in store._rows("SELECT * FROM outcome WHERE ResolvedAt IS NOT NULL AND Verdict!='unknown' AND At>=? AND IFNULL(Actor,'') NOT LIKE 'agent%' ORDER BY Id", (since,)):
            who = str((json.loads(r.get('FactsJson') or '{}') or {}).get('who') or '').lower()
            out.append((f"out{r['Id']}", r['At'], who, f"{who + ' · ' if who else ''}{outcomes._sentence(store, r)}"))
    except Exception as e:
        logger.warning(f'episodes: some not read - {e}')
    return sorted(out, key=lambda e: str(e[1] or ''))


def block(store, since: str, cap_n: int = CAP_N, cap_chars: int = CAP_CHARS) -> tuple:
    """(the EPISODES block, the addresses it is about, how many did not fit) - grouped by person, newest people first, within the caps;
    what was left out is counted in the block's last line ("12 more episodes not shown")."""
    eps = build(store, since)
    by = {}
    for e in eps: by.setdefault(e[2] or '', []).append(e)
    order = sorted(by, key=lambda w: max(str(e[1]) for e in by[w]), reverse=True)
    lines, used, shown, who = [], 0, 0, set()
    for w in order:
        for eid, at, _, line in by[w]:
            row = f'{eid} {str(at or "")[:10]} · {line}'
            if shown >= cap_n or used + len(row) + 1 > cap_chars: continue
            lines.append(row); used += len(row) + 1; shown += 1
            if w: who.add(w)
    left = len(eps) - shown
    return '\n'.join(lines + ([f'({left} more episodes not shown)'] if left else [])), who, left


def count(store, since: str) -> int: return len(build(store, since))


def is_act(ev_id: str) -> bool:
    """An evidence id of something the owner did or said - never a press, never what a sender wrote."""
    return bool(re.match(rf"^({'|'.join(ACTS)})\d+$", str(ev_id or '')))
