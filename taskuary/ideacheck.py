"""THE SECOND LOOK BEFORE AN IDEA IS RAISED (the design's S7, 2026-11-01: quiet unless sure). The audit graded the last 32 rail ideas:
19 useful - each joined threads, people or a promise - 11 obvious, a third of them one report row said again, and 2 stale, about work
the owner was steering that very day. So before the model's own lines post:

  quiet kind   a kind of line the owner's record says is under 80% useful (ideagrade.quiet_kinds) is not raised
  touched      a line about a task or mail the owner acted on in the last day is not raised: they know
  known        the model reads each line again beside the workstream it is under and what the owner last did on it, and answers
               whether the owner would ALREADY KNOW it - a line they would know is not raised

The app's own lines (health, report, connect, rule, workstream, habit) are counted facts and pass untouched. A check that cannot run -
no AI, a failed call - holds nothing back: the post is what it was before this check existed."""
import json
from datetime import datetime, timedelta
from loguru import logger
from . import aiusage, ideagrade

TOUCHED_H = 24
# ...asked as JOIN OR RESTATE (a live replay over the 32 graded ideas, 2026-11-01): "would the owner already know this?" held half the
# useful lines and kept most of the obvious ones - a model cannot know what a person knows. What separated them in the audit is checkable
# in the note itself: every useful one joined two things, every obvious one said one thing again.
SYSTEM = ("You check an assistant's notes to a busy owner before they are shown. For each note you get what it says, why, the "
          "workstream it is under and what the owner last did on the item. A note EARNS its place only when it JOINS things the owner "
          "could not see in one place: two threads or two people asking about the same thing, an answer in one thread that settles "
          "another, the same failure across several runs or days, a promise or ask against a date or a meeting, a date a message "
          "named that has now passed or is about to, a second ask buried "
          "beside a reply, a draft that leaves part of an ask out, two commitments that collide. A note RESTATES when it tells one "
          "thing a single message, report row, auto-reply or failure notice already says - however it is worded, and whatever it "
          "suggests doing about it. A note about something the owner ASKED to be brought up (listed first, when there is any) never "
          "only restates. Answer which notes only restate. "
          'Answer JSON: {"known": [<the numbers of the notes that only restate one thing>]}')
WANT = {'name': 'known', 'schema': {'type': 'object', 'additionalProperties': False, 'required': ['known'],
                                    'properties': {'known': {'type': 'array', 'items': {'type': 'integer'}}}}}


def _ago(h): return (datetime.now() - timedelta(hours=h)).strftime('%Y-%m-%d %H:%M:%S')


def _model(s) -> bool: return str(s.get('key') or '').startswith('idea:') and (s.get('kind') or 'idea') in ideagrade.MODEL_KINDS


def touched(store, act: dict, hours: int = TOUCHED_H) -> str:
    """What the owner did on the line's task or mail in the last `hours` ('' when nothing): a press, a reply, a close, a typed turn."""
    tid, mid = act.get('tid'), act.get('mid')
    if not tid and mid: tid = (store.get_message(int(mid)) or {}).get('TaskId')
    if not tid: return ''
    since = _ago(hours)
    r = store._one("SELECT Kind FROM outcome WHERE TargetKind='task' AND TargetId=? AND Actor IN ('owner','you') AND At>=? ORDER BY Id DESC LIMIT 1",
                   (int(tid), since))
    if r: return r['Kind']
    r = store._one("SELECT Pressed FROM advice_press WHERE TargetKind='task' AND TargetId=? AND CreatedAt>=? AND Pressed NOT IN ('next','back') "
                   "ORDER BY Id DESC LIMIT 1", (int(tid), since))
    return f"pressed {r['Pressed']}" if r else ''


def _last_acts(store, act: dict, n: int = 4) -> str:
    tid = act.get('tid') or ((store.get_message(int(act['mid'])) or {}).get('TaskId') if act.get('mid') else None)
    if not tid: return 'nothing recorded'
    rows = store._rows("SELECT Kind, At FROM outcome WHERE TargetKind='task' AND TargetId=? AND Actor IN ('owner','you') ORDER BY Id DESC LIMIT ?", (int(tid), n))
    return '; '.join(f"{r['Kind']} at {str(r['At'])[:16]}" for r in rows) or 'nothing recorded'


def _workstream(store, act: dict) -> str:
    from . import workstreams as W
    ws = W.of_task(store, int(act['tid'])) if act.get('tid') else (W.of_message(store, store.get_message(int(act['mid'])) or {}) if act.get('mid') else '')
    if not ws: return 'not placed'
    w = W.get(store, ws)
    return f"{w['name']}: {(W.section(store, ws) or w['about'])[:600]}" if w else ws


@aiusage.named('advisor.idea')
def check(store, say: list, llm=None, memo: str = None) -> tuple:
    """(the lines to raise, [(key, why it was held)]). The model's own lines only; everything else passes. `memo`: where a clocked look
    keeps its last verdict - never on Run now."""
    held, keep, ask = [], [], []
    if not store.get_setting(ideagrade.SINCE_KEY):           # the kinds' record starts with the second look (ideagrade.quiet_kinds)
        store.set_setting(ideagrade.SINCE_KEY, datetime.now().strftime('%Y-%m-%d %H:%M:%S'), 'advisor')
    try: quiet = ideagrade.quiet_kinds(store)
    except Exception as e: logger.debug(f'idea record not read: {e}'); quiet = set()
    for s in say:
        if not _model(s): keep.append(s); continue
        a = s.get('action') or {}
        if (s.get('kind') or 'idea') in quiet: held.append((s['key'], f"its kind ({s.get('kind') or 'idea'}) is under 80% useful lately")); continue
        if (t := touched(store, a)): held.append((s['key'], f'the owner acted on it in the last day ({t})')); continue
        # ...a line the OWNER'S OWN MEMORY asks for (a What to bring up or a Promises line it rests on) and an unkept promise are
        # raised on that word, never second-guessed (the live rail A/B, 2026-11-01: the second look held "bring up the Q4 budget")
        if a.get('memory') or s.get('kind') == 'promise': keep.append(s); continue
        ask.append(s)
    if ask and llm is None:
        try:
            from .llm import build_llm
            llm = build_llm(store, job='advisor')
        except Exception as e: logger.debug(f'no brain for the second look: {e}'); llm = None
    if ask and llm is not None:
        try:
            from .llm import ask_json
            from . import learned_cut as lc
            bring = [raw for raw, _k in lc.lines(store.doc('learned') or '', lc.BRING)]
            user = ('WHAT THE OWNER ASKED TO BE BROUGHT UP:\n' + '\n'.join(bring) + '\n\n' if bring else '') + '\n\n'.join(f"NOTE {n}: {s['text']}\nwhy: {s.get('why') or '-'}\nworkstream: {_workstream(store, s.get('action') or {})}\n"
                               f"the owner last did on it: {_last_acts(store, s.get('action') or {})}" for n, s in enumerate(ask, 1))
            # THE SAME NOTES, THE SAME LOOK (`memo`, a clocked run's - llm.standing): a line held here is never posted, so the clock's next
            # look raised it again and the second look was asked about it again, every half hour all night (2026-11-12)
            from .llm import standing
            def look(u): return ask_json(llm, SYSTEM, u, want=WANT, need=('known',)).data
            got = standing(store, memo, SYSTEM, user, look, small=False)[0] if memo else look(user)
            known = {int(x) for x in ((got or {}).get('known') or []) if str(x).lstrip('-').isdigit()} if got is not None else set()
            for n, s in enumerate(ask, 1):
                if n in known: held.append((s['key'], 'the owner would already know it'))
                else: keep.append(s)
            ask = []
        except Exception as e: logger.info(f'the second look did not run - every line stands: {e}')
    keep += ask
    order = {s['key']: i for i, s in enumerate(say)}
    return sorted(keep, key=lambda s: order.get(s['key'], 0)), held
