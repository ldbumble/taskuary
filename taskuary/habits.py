"""A HABIT THE ADVISOR IS SURE OF IS ADOPTED; ONE IT IS NOT SURE OF IS ASKED, ONCE (the owner, 2026-11-01: "when the Advisor is SURE,
it adopts the habit without asking; it asks (Adopt / No, once, never repeated after No) only for really useful ones it is unsure about").

The reflection proposes a rule it has inferred under "Proposed rules - your call" and it waited there for a click - the audit found eleven,
one resting on 31 of the owner's own acts, that would have spared most of the side-product and personal misses. After each reflection:

  sure     its strength is SURE_S or more, resting on SURE_EV or more distinct acts of the owner's (episodes.is_act: never a press, never
           what a sender wrote) -> adopted, and listed on the one habits row with Not right, which takes it back (memoryedit Wrong)
  useful   strength USEFUL_S or more, short of sure -> listed with Adopt / No; No leaves it where it was and never asks again. At most
           WEEK_ASKS of these a week - the rest wait in LEARNED.md, proposed, for a later week
  the rest wait, as before

ONE ROW FOR ALL OF THEM (the owner, 2026-11-01: "how many advisor ideas do i have now? it's too many. what does keep it/remind me do here?
doesn't make much sense"): each habit was its own idea card - seven on the first run, with {{owner_first}} raw in the text and the idea
buttons (Put it on my list, Keep it, Remind me, Not ours) that mean nothing for a habit. Now one Advisor row, "Learned 3 habits · 2 to
check", lists each habit as a sentence to the owner - what was seen and what changes - with its own buttons. What the row holds is kept in
the setting SAID ({line key: {adopted, say, n, asked, state}}, state open|seen|yes|no|wrong|gone); the row goes once nothing in it is open,
and a later adoption brings it back with only the new ones.

Counted, never thought: the same evidence the books already keep. A rule never reaches triage from a press: _books drops press-only lines.
LEARNED.md's own lines are untouched - the sentence the owner reads is written beside them (phrase), never into the doc."""
import json, re
from datetime import datetime, timedelta
from loguru import logger

SURE_S, SURE_EV, USEFUL_S = 10, 6, 5
KEY, KIND, SAID, WEEK_ASKS = 'habit:all', 'habit', 'advisor_habits', 2      # not idea:...: a model idea's key reopens as it was (store.is_model_idea)
LEGACY = 'idea:habit-%'          # the one-card-per-habit rows before 2026-11-01, folded into KEY

PLAIN = ('Each numbered line is a habit Taskuary learned about its owner, written about them in the third person ({{owner_first}} is '
         'their name). Rewrite each as ONE plain sentence spoken to the owner ("You ..."): what they do, and what Taskuary does differently '
         'because of it - for a line marked ASKING, what it would do if they agree. For example: "You close sign-in help requests yourself, '
         'so I won\'t draft replies to them." Under 30 words, everyday words, no button names, nothing the line does not say, no counts. '
         'Return JSON only: {"lines": ["...", ...]}, one per numbered line, in order.')


def _now(): return datetime.now().strftime('%Y-%m-%d %H:%M:%S')
def _said(store) -> dict:
    try: d = json.loads(store.get_setting(SAID) or '{}')
    except ValueError: d = {}
    return d if isinstance(d, dict) else {}
def _keep(store, d: dict, actor='advisor'): store.set_setting(SAID, json.dumps(d), actor)
def _seen(n, s: str) -> str:
    from .timewords import plural
    s = s.strip().rstrip('.'); return f"{s[:1].upper()}{s[1:]} (seen {plural(n, 'time')})."


def _named(store, text: str) -> str:
    """The line with the owner's name where LEARNED.md keeps {{owner_first}} - the fallback when no model phrased it."""
    from .store import render_doc
    return re.sub(r'\{\{[^}]*\}\}', 'you', render_doc(text, store.owner())).strip()        # ...and no {{...}} the owner can read, ever


def tick(store, llm=None) -> dict:
    """Adopt the sure ones and list the useful ones on the habits row. {adopted: [keys], asked: [keys]}. Never raises."""
    from . import learn, learnedgraph as lg
    from .episodes import is_act
    out, d = {'adopted': [], 'asked': []}, None
    try:
        fold(store)
        d = _said(store)
        week = (datetime.now() - timedelta(days=7)).strftime('%Y-%m-%d %H:%M:%S')
        room = WEEK_ASKS - sum(1 for e in d.values() if e.get('ask') and str(e.get('asked') or '') >= week)
        for l in lg.lines(store.get_doc(learn.DOC) or ''):
            if l['status'] != 'proposed': continue
            k, e, acts, n = l['key'], d.get(l['key']) or {}, {x for x in l['ev'] if is_act(x)}, len(set(l['ev']))
            if e.get('state') in ('no', 'wrong'): continue            # the owner said No: never asked again, never adopted behind their back
            if l['score'] >= SURE_S and len(acts) >= SURE_EV and len(acts) == len(set(l['ev'])):
                try: learn.adopt(store, k, 'advisor-sure')
                except ValueError: continue
                d[k] = e | {'adopted': True, 'say': _seen(n, _named(store, l['text'])), 'text': l['text'], 'n': n, 'asked': e.get('asked') or _now(),
                            'state': 'open', 'plain': False}
                out['adopted'].append(k)
            elif l['score'] >= USEFUL_S and acts and not e and room > 0:
                d[k] = {'adopted': False, 'ask': True, 'say': _seen(n, _named(store, l['text'])), 'text': l['text'], 'n': n, 'asked': _now(), 'state': 'open'}
                out['asked'].append(k); room -= 1
        _keep(store, d)
        if llm and (out['adopted'] or out['asked']): phrase(store, llm)
        draw(store)
    except Exception as e: logger.warning(f'habits not weighed: {e}')
    return out


def unphrased(store) -> list: return [k for k, e in _said(store).items() if e.get('state') == 'open' and not e.get('plain') and e.get('text')]


def phrase(store, llm) -> int:
    """Each open habit the model has not yet said plainly, as one sentence to the owner - what they do and what changes - with the count
    the books keep after it. A line the model cannot phrase keeps the name-filled one. Returns how many it phrased. Never raises."""
    d, todo = _said(store), unphrased(store)
    if not todo: return 0
    try:
        got = llm(PLAIN, '\n'.join(f"{i}. {'ADOPTED' if d[k]['adopted'] else 'ASKING'}: {d[k]['text']}" for i, k in enumerate(todo, 1)), max_tokens=900)
        m = re.search(r'\{.*\}', str(got or ''), re.S)
        lines = (json.loads(m.group(0)) if m else {}).get('lines') or []
    except Exception as e:
        logger.info(f'habits not phrased: {e}'); return 0
    n = 0
    for k, s in zip(todo, lines):
        s = str(s or '').strip()
        if not s or '{{' in s or len(s) > 240: continue
        d[k] |= {'say': _seen(d[k].get('n') or 1, s), 'plain': True}; n += 1
    if n: _keep(store, d); draw(store)
    return n


def fold(store) -> int:
    """The habit cards of before 2026-11-01 (one idea row each, Key idea:habit-<slug>) folded into the one row: an open one joins it, a
    No on one is remembered as No, one answered or kept is done with. Each old row is closed. Returns how many folded."""
    from . import learn, learnedgraph as lg
    d, doc, n_ = _said(store), None, 0
    for i in store._rows('SELECT * FROM idea WHERE Key LIKE ?', (LEGACY,)):
        try: a = json.loads(i.get('ActionJson') or '{}') or {}
        except ValueError: a = {}
        k, live = a.get('line'), i.get('Status') in ('open', 'snoozed')
        if not live and (not k or k in d): continue                 # folded already
        if k and k not in d:
            doc = doc if doc is not None else {l['key']: l for l in lg.lines(store.get_doc(learn.DOC) or '')}
            m, l = re.search(r'"(.*)"', i.get('Text') or '', re.S), doc.get(k) or {}
            text, n = l.get('text') or (m.group(1) if m else (i.get('Text') or k)), len(set(l.get('ev') or [])) or 1
            state = 'open' if live else 'no' if i.get('Status') == 'dismissed' and not a.get('adopted') else 'seen'
            d[k] = {'adopted': bool(a.get('adopted')), 'ask': not a.get('adopted'), 'say': _seen(n, _named(store, text)), 'text': text, 'n': n,
                    'asked': i.get('FirstSeen') or _now(), 'state': state}
        if live: store.set_idea_status(i['IdeaId'], 'done', 'habits')
        n_ += 1
    if not n_: return 0
    _keep(store, d); draw(store)
    logger.info(f'habits: {n_} habit card(s) folded into one row')
    return n_


def _count(n, one, many=None): return f"{n} {one if n == 1 else (many or one + 's')}"


def title(d: dict) -> str:
    """"Learned 3 habits · 2 to check" - the adopted ones not yet seen, and the ones that wait on the owner."""
    new = sum(1 for e in d.values() if e.get('state') == 'open' and e.get('adopted'))
    ask = sum(1 for e in d.values() if e.get('state') == 'open' and not e.get('adopted'))
    return ' · '.join(x for x in (f"Learned {_count(new, 'habit')}" if new else '', (f'{ask} to check' if new else f"{_count(ask, 'habit')} to check") if ask else '') if x)


def draw(store) -> dict | None:
    """The one habits row, from what is open: drawn in place while it is up (its place on the rail never moves), raised again when a new
    habit comes, closed when nothing in it is open. A line taken out of LEARNED.md some other way leaves it."""
    from . import learn, learnedgraph as lg
    d, now = _said(store), {l['key']: l['status'] for l in lg.lines(store.get_doc(learn.DOC) or '')}
    gone = [k for k, e in d.items() if e.get('state') == 'open' and now.get(k) != ('live' if e.get('adopted') else 'proposed')]
    for k in gone: d[k]['state'] = 'gone'
    if gone: _keep(store, d)
    items = [{'line': k, 'adopted': bool(e.get('adopted')), 'say': e.get('say') or ''} for k, e in d.items() if e.get('state') == 'open']
    old = store._one('SELECT * FROM idea WHERE Key=?', (KEY,))
    if not items:
        if old and old.get('Status') in ('open', 'snoozed'): store.set_idea_status(old['IdeaId'], 'done', 'habits'); _woke(store)
        return None
    act, text = json.dumps({'type': 'habits', 'habits': items}), title(d)
    sig = ','.join(f"{i['line']}:{int(i['adopted'])}" for i in items)
    if old and old.get('Status') == 'open':
        if (old['Text'], old.get('ActionJson')) == (text, act): return old
        store._exec('UPDATE idea SET Text=?, ActionJson=?, Sig=? WHERE IdeaId=?', (text, act, sig, old['IdeaId']))
        r = store._one('SELECT * FROM idea WHERE Key=?', (KEY,))
    else: r = store.upsert_idea({'key': KEY, 'kind': KIND, 'text': text, 'sig': sig, 'action': json.loads(act)}, _now())
    _woke(store)
    return r


def _woke(store):
    """The rail reads the row again at once - its words, or that it went - as the fixture's own writes do."""
    try:
        from . import funnel
        store.reconcile_processing_membership(); funnel.invalidate(); store._poke('feed-changed')
    except Exception as e: logger.debug(f'habits row not re-read: {e}')


def answer(store, line: str, yes: bool, actor: str = 'owner') -> dict:
    """One habit's button on the row: Adopt (yes) or No on one it asked about - No leaves it proposed and it is never asked again; Not right
    (no) on one the Advisor adopted takes it back for good (Wrong). {line, adopted, open} - open is how many the row still holds."""
    from . import learn, memoryedit
    d = _said(store)
    e = d.get(line)
    if not e or e.get('state') != 'open': raise ValueError('that habit is not waiting on you')
    if e.get('adopted') and not yes:
        try: memoryedit.mark(store, line, 'wrong')
        except (ValueError, LookupError) as x: logger.info(f'habit {line} not taken back: {x}')
        e['state'] = 'wrong'
    elif not e.get('adopted') and yes:
        try: learn.adopt(store, line, actor)
        except ValueError: pass
        e |= {'state': 'yes', 'adopted': True}
    else: e['state'] = 'seen' if yes else 'no'
    _keep(store, d, actor)
    draw(store)
    return {'line': line, 'adopted': bool(e.get('adopted')) and e['state'] != 'wrong', 'open': sum(1 for x in d.values() if x.get('state') == 'open')}


def seen(store, actor: str = 'owner', unsure: str = None) -> dict:
    """The owner opened the row and moved on: the adopted ones are seen. `unsure` puts down the asked ones too - 'no' (Not ours on the row:
    never asked again) or 'seen' (done with it some other way). {open}"""
    d = _said(store)
    for e in d.values():
        if e.get('state') == 'open' and (e.get('adopted') or unsure): e['state'] = 'seen' if e.get('adopted') else unsure
    _keep(store, d, actor)
    draw(store)
    return {'open': sum(1 for x in d.values() if x.get('state') == 'open')}
