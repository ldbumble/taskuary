"""DOES THE RAIL ADVISOR USE THE MEMORY? (2026-10-26) The clock Advisor (assistant.run) reads LEARNED.md through the `learned` block
(assistantblocks._learned -> learned_cut.for_reader(store, 'assistant'), every section), on by default: the seeded Advisor saves no
cards, so resolve() hands it every block's declaration and `learned` is default_on. tests/rail_advisor_cases.py measures the CODE with
a brain that says every candidate; this measures the MODEL's taste with and without the memory.

    A/B       the rail cases' worlds (its builders) plus four worlds a memory line should change - "What to bring up" (the Q4 budget,
              no newsletters), a person who matters (their silence raised, a stranger's not), a promise the sent-words judge missed -
              each checked by a real model with memory EMPTY and FILLED, graded hit / miss / quiet / noise like the rail cases
    stale     a line closed by a correction, one marked Wrong and one Forgotten (memoryedit, the owner's own road) never reach the
              prompt nor an idea - and a machine write that brings them back is held off by learnedlines.guard
    noise     every line the real model raised, held to rail_advisor_cases.noise_of plus: about automated or bulk mail, whatever its kind

Only the Advisor's own pass goes to the real model; the sent-words judge and the triage of ideas stay scripted (rail_advisor_cases.brain)
so each world is the same in both arms. Live runs are opt-in: TASKUARY_LIVE_MEMORY=1, TASKUARY_LIVE_DB = a COPY of a taskuary.db with an
AI card (opening a store migrates it, so never the live one), TASKUARY_HOME a scratch dir. TASKUARY_LIVE_ARMS=empty or filled runs one arm
(two processes, two db copies, half the wall time); TASKUARY_LIVE_OUT writes the results as JSON. Invented Northwind people only."""
import json, os, re, time
from unittest import mock
import pytest
from tests import rail_advisor_cases as C

HEAD = 'WHAT YOU KNOW ABOUT HOW THE OWNER WORKS'
PAULA, DANA, RAY = ('Paula Vance', 'paula@northwind.example'), ('Dana Whitlock', 'dana@outreach.example'), ('Ray Colton', 'ray@northwind.example')
# the memory the FILLED arm reads in every world - the owner's own lines (memoryedit.remember), so in use from the moment they are said
FILLED = (('people', f'{PAULA[0]} ({PAULA[1]}) is your CFO; when you ask her for something you chase her within a day'),
          ('promises', f'You owe {RAY[0]} ({RAY[1]}) the vendor accruals before the month-end close'),
          ('bring', 'Bring up anything about the Q4 budget, even when nobody asks you anything'),
          ('bring', "Don't bring up newsletters, or ideas to unsubscribe from them"))
# ...and three that stopped being true, each put down by its own road - a marker per line that no prompt or idea may carry
STALE = {'closed': 'runs headcount in Finance', 'wrong': 'is your boss', 'forgot': 'every vendor invoice flagged'}


def fill(s):
    from taskuary import memoryedit as me
    for sec, t in FILLED: me.remember(s, t, section=sec)


def stale(s, down=True):
    """A fact closed by a correction ("Gail moved to Ops"), a machine line marked Wrong, an owner's line Forgotten - or, `down` False,
    the three still standing: the control that shows the markers would be read if nothing put them down."""
    from taskuary import memoryedit as me
    from taskuary.learn import _under
    from taskuary.learned_cut import PEOPLE
    gone = me.remember(s, 'Gail Moreno (gail@northwind.example) runs headcount in Finance; bring up her sheet every Monday', section='people')
    me.remember(s, 'Gail Moreno (gail@northwind.example) moved to Ops this month', section='people', replaces=me._key(gone['text']) if down else '')
    doc = s.get_doc('learned') or ''
    s.save_doc('learned', _under(doc, PEOPLE, '- Omar Keller (omar@northwind.example) is your boss; raise everything he sends first '
                                            '[s:4 | ev: msg1, msg2, msg3 | seen: 2026-10-20 | k: omar-boss]'), 'reflect')
    f = me.remember(s, 'Marcus Reed (marcus@northwind.example) wants every vendor invoice flagged to him', section='people')
    if down: me.mark(s, 'omar-boss', 'wrong'); me.mark(s, me._key(f['text']), 'forget')


# ── the worlds a memory line should change ───────────────────────────────────────────────────────────────────────────────────────
def _q4(s):
    s.add_message({'ConversationId': 'email:q4', 'Channel': 'email', 'Subject': 'Q4 budget - draft numbers', 'FromName': 'Gail Moreno',
                   'FromEmail': 'gail@northwind.example', 'SentAt': C.at(h=4), 'Status': 'filed', 'SenderClass': 'person',
                   'BodyText': 'Sharing the draft Q4 budget numbers: travel is 18% over plan, the headcount line is flat. FYI, nothing needed.'})
def _two_silences(s):
    """The owner asked two people for something three days ago, neither answered: the CFO, and a stranger whose cold pitch they answered once."""
    C._thread(s, 'email:forecast', PAULA, 'Forecast sign-off', theirs_d=5, mine_d=3)
    s.add_message({'ConversationId': 'email:pitch', 'Channel': 'email', 'Subject': 'Quick question about your AP process', 'FromName': DANA[0],
                   'FromEmail': DANA[1], 'SentAt': C.at(d=5), 'Status': 'filed', 'SenderClass': 'person',
                   'BodyText': 'Hi Alex, we help finance teams cut AP time in half. Worth a 15-minute call?'})
    mid = s.add_message({'ConversationId': 'email:pitch', 'Channel': 'email', 'Subject': 'Re: Quick question about your AP process', 'FromName': 'Alex Doyle',
                         'FromEmail': C.OWNER, 'SentAt': C.at(d=3, m=1), 'BodyText': 'Could you send a one-pager with pricing?', 'Status': 'context', 'Direction': 'out'})
    s.put_sent_verdict(mid, 'email:pitch', True, False, '', None, 'eval')
def _ray(s):
    """Ray asked for the accruals yesterday and the owner said "Will do." - no "I'll", so the judge filed no promise: only memory knows."""
    s.add_message({'ConversationId': 'email:accruals', 'Channel': 'email', 'Subject': 'Vendor accruals', 'FromName': RAY[0], 'FromEmail': RAY[1],
                   'SentAt': C.at(h=26), 'Status': 'filed', 'SenderClass': 'person', 'BodyText': 'Can you get me the vendor accruals before close on Thursday?'})
    mid = s.add_message({'ConversationId': 'email:accruals', 'Channel': 'email', 'Subject': 'Re: Vendor accruals', 'FromName': 'Alex Doyle', 'FromEmail': C.OWNER,
                         'SentAt': C.at(h=25), 'BodyText': 'Will do.', 'Status': 'context', 'Direction': 'out'})
    s.put_sent_verdict(mid, 'email:accruals', False, False, '', None, 'eval')
def _stale_world(s):
    """Mail from each person a stale line names - where a leaked line would show."""
    for who, em, subj, body in (('Omar Keller', 'omar@northwind.example', 'Lunch order Friday', 'Ordering lunch for Friday - reply by Thursday if you want in.'),
                                ('Marcus Reed', 'marcus@northwind.example', 'INV-204 for your records', 'Vendor invoice INV-204 attached for your records. Already approved.'),
                                ('Gail Moreno', 'gail@northwind.example', 'New seat', 'I am on floor 3 with Ops from Monday.')):
        s.add_message({'ConversationId': f'email:{em}', 'Channel': 'email', 'Subject': subj, 'FromName': who, 'FromEmail': em, 'SentAt': C.at(h=3),
                       'Status': 'filed', 'SenderClass': 'person', 'BodyText': body})


# (world name, build, between, [(case, kind or None, should, pattern a line must match to be about it)])
# kind None: any line whose text or why matches - a memory line can surface as a candidate's line or as the model's own idea
MEMORY = [('q4', _q4, None, [('bring: Q4 budget numbers arrive, nobody asks anything', None, True, r'Q4|budget')]),
          ('newsletter', C._newsletter, None, [('bring: a newsletter arrives', None, False, r'newsletter|Payworth|unsubscribe')]),
          ('silences', _two_silences, None, [('people: the CFO has not answered in three days', None, True, r'Paula|forecast'),
                                             ("people: a stranger's cold pitch, one question asked", None, False, r'Dana|pitch|one-pager|AP process')]),
          ('ray', _ray, None, [('promises: "Will do." to Ray about the accruals', None, True, r'Ray|accrual'),])]
# the rail cases where the model's taste decides (health and rule rows post with no model; connect lines are the model's own, untested here)
PICK = ('asked a vendor 3 days ago, no answer', 'they answered', 'the last word was to an automated address', 'promised a budget by Friday, not sent',
        'the budget went', 'open task untouched for six days', 'touched yesterday', 'an agent has been on it for six days',
        "the model's own line about a mail", 'about a task closed yesterday', 'the same thought again after a No',
        'a fourth newsletter idea after three were said no to')
IDEA_RE = {"the model's own line about a mail": r'lease', 'about a task closed yesterday': r'vendor loop|loop',
           'the same thought again after a No': r'lease', 'a fourth newsletter idea after three were said no to': r'newsletter|Payworth|unsubscribe'}


def worlds():
    out = [(n, b, between, cs) for n, b, between, cs in MEMORY]
    for kind, name, should, build, between in C.CASES:
        if name in PICK: out.append((name, build, between, [(name, kind if name not in IDEA_RE else None, should, IDEA_RE.get(name))]))
    return out


# ── the brain: the Advisor's pass to the real model, everything else scripted ────────────────────────────────────────────────────
class Router:
    def __init__(self, real):
        self.real, self.script, self.calls, self.seen = real, C.brain(), 0, []
    def __call__(self, system, user, max_tokens=None, **kw):
        if not str(system or '').startswith('YOUR INSTRUCTION'): return self.script(system, user, max_tokens, **kw)
        self.calls += 1
        t = time.time()
        out = self.real(system, user, max_tokens=max_tokens)
        self.seen.append({'system': system, 'user': user, 'answer': str(out), 'secs': round(time.time() - t, 1)})
        return out


def check(s, router) -> list:
    from taskuary import assistant, funnel
    with mock.patch('taskuary.llm.build_llm', return_value=router):
        out = assistant.run(s, llm=router, force=True)
    funnel.invalidate()
    if out.get('failed'): raise RuntimeError(out.get('error'))
    return out.get('lines') or []


# what each planted line is about - a line raising it in a world with no mail or task about it was said from memory alone
ABOUT = {'Paula': r'Paula|paula@', 'Ray': r'\bRay\b|accrual', 'Q4': r'Q4', 'newsletter': r'newsletter|unsubscribe'}


def noise(s, l, rail) -> str:
    """rail_advisor_cases.noise_of, automated or bulk mail whatever the line's kind - the model's own ideas included - and a line
    that rests on a memory line alone: round one raised "you owe Ray the accruals" in worlds with no word from Ray in them."""
    if (why := C.noise_of(s, l['kind'], l, rail)): return why
    world = ' '.join(f"{r['Subject']} {r['BodyText']} {r['FromEmail']}" for r in s._rows("SELECT Subject, BodyText, FromEmail FROM message WHERE Channel='email'"))
    world += ' '.join(str(t['Title']) for t in s._rows('SELECT Title FROM task'))
    for k, p in ABOUT.items():
        if re.search(p, l['text'], re.I) and not re.search(p, world, re.I): return f'from memory alone - nothing here is about {k}'
    mid = (l.get('action') or {}).get('mid')
    m = s.get_message(mid) if mid else None
    if m and str(m.get('SenderClass') or '').lower() in ('automated', 'bulk'): return f"about automated mail ({m.get('FromEmail')})"
    return ''


def grade(lines, kind, should, pat, why) -> tuple:
    about = lambda l: (kind is None or l['kind'] == kind) and (not pat or re.search(pat, f"{l['text']} {l.get('why') or ''}", re.I))
    mine = [l for l in lines if about(l)]
    if mine and not should: return 'noise', f"fired: {mine[0]['text'][:110]}"
    if mine and why.get(mine[0]['key']): return 'noise', why[mine[0]['key']]
    if mine: return 'hit', mine[0]['text'][:110]
    return ('miss', 'nothing raised') if should else ('quiet', '')


def one(world, router, arm) -> dict:
    name, build, between, cases = world
    s = C.store(); build(s)
    if arm != 'empty': fill(s)
    if arm == 'stale': stale(s)
    n0 = len(router.seen)
    lines = check(s, router)
    if between:
        (C.put_all_down if between == 'dismiss' else between)(s, lines)
        lines = check(s, router)
    rail = C.rail_rows(s)
    why = {l['key']: w for l in lines if (w := noise(s, l, rail))}
    prompts = router.seen[n0:]
    return {'world': name, 'arm': arm, 'memory_in_prompt': any(HEAD in p['user'] for p in prompts),
            'cases': [dict(zip(('case', 'out', 'why'), (c, *grade(lines, k, sh, p, why)))) for c, k, sh, p in cases],
            'lines': [{'kind': l['kind'], 'key': l['key'], 'text': l['text'], 'why': l.get('why'), 'noise': why.get(l['key'], '')} for l in lines],
            'stale_in_prompt': sorted(k for k, m in STALE.items() for p in prompts if m in p['user'] or m in p['system']),
            'stale_in_lines': sorted(k for k, m in STALE.items() for l in lines if m.lower() in f"{l['text']} {l.get('why')}".lower()),
            'secs': sum(p['secs'] for p in prompts)}


def table(res) -> str:
    by = {}
    for r in res:
        for c in r['cases']: by.setdefault(c['case'], {})[r['arm']] = c['out']
    rows = [f"{'case':62} {'empty':>6} {'filled':>7}"] + [f"{c[:62]:62} {v.get('empty', '-'):>6} {v.get('filled', '-'):>7}" for c, v in by.items()]
    for arm in ('empty', 'filled'):
        n = {}
        for r in res:
            if r['arm'] == arm:
                for c in r['cases']: n[c['out']] = n.get(c['out'], 0) + 1
        ls = [l for r in res if r['arm'] == arm for l in r['lines']]
        rows.append(f'{arm}: ' + ' '.join(f'{k} {n.get(k, 0)}' for k in ('hit', 'miss', 'quiet', 'noise'))
                    + f" | lines raised {len(ls)}, noisy {sum(1 for l in ls if l['noise'])}")
    return '\n'.join(rows)


# ── the plumbing, every run of the suite: no model ───────────────────────────────────────────────────────────────────────────────
class Silent:
    def __init__(self): self.seen = []
    def __call__(self, system, user, max_tokens=None, **kw): self.seen.append({'system': system, 'user': user, 'secs': 0}); return '{"say": [], "notes": ""}'


def test_the_filled_memory_reaches_the_advisors_prompt_and_the_empty_one_says_nothing():
    r = Router(Silent())
    e, f = one(MEMORY[0], r, 'empty'), one(MEMORY[0], r, 'filled')
    assert not e['memory_in_prompt'], 'a fresh LEARNED.md is placeholders - no head with nothing under it'
    assert f['memory_in_prompt'] and r.calls == 2
    user = r.real.seen[-1]['user']
    # every planted line, under its own section, inside the memory card ([taskuary.memory] in the seeded prompt)
    assert all(t in user for _, t in FILLED) and '## What to bring up' in user and '## Promises' in user
    assert user.index(HEAD) > user.index('6. WHAT I ALREADY KNOW')


def test_a_closed_a_wrong_and_a_forgotten_line_never_reach_the_prompt():
    r = Router(Silent())
    got = one(('stale', _stale_world, None, []), r, 'stale')
    assert got['memory_in_prompt'] and not got['stale_in_prompt'], got['stale_in_prompt']
    assert 'moved to Ops this month' in r.real.seen[-1]['user']                   # the correction itself is read


def test_a_machine_write_does_not_bring_a_put_down_line_back():
    """The reflection rewrites LEARNED.md from evidence; one that writes the Wrong line back is held off (learnedlines.guard), and so is
    the closed one on the same evidence - the Forgotten one waits for GROW-fold evidence."""
    from taskuary import learnedlines
    from taskuary.learn import _under
    from taskuary.learned_cut import PEOPLE, for_reader
    s = C.store(); fill(s); stale(s, down=False)
    assert all(m in for_reader(s, 'assistant') for m in STALE.values()), 'the control: standing, all three are read'
    s = C.store(); fill(s); stale(s)
    back = _under(s.get_doc('learned') or '', PEOPLE, '- Omar Keller (omar@northwind.example) is your boss; raise everything he sends first '
                                                      '[s:5 | ev: msg1, msg2, msg3, msg4 | seen: 2026-10-26 | k: omar-boss]')
    assert 'is your boss' not in learnedlines.guard(s, back)
    s.save_doc('learned', learnedlines.guard(s, back), 'reflect')
    assert not any(m in for_reader(s, 'assistant') for m in STALE.values())


# ── the real model: opt-in, OUTSIDE pytest ───────────────────────────────────────────────────────────────────────────────────────
# tests/conftest.py's P0-ISOLATION blocks every unreviewed subprocess and socket and points HOME at a scratch dir, so a CLI brain (or an
# API card) cannot answer inside the suite - the live run is `python -m tests.test_rail_advisor_memory_live`, with the real HOME.
LIVE = os.environ.get('TASKUARY_LIVE_MEMORY') == '1'


def real_brain():
    from pathlib import Path
    home = Path(os.environ.get('TASKUARY_HOME') or '').resolve()
    assert os.environ.get('TASKUARY_HOME') and home != (Path.home() / '.taskuary').resolve(), 'set TASKUARY_HOME to a scratch dir'
    from taskuary import config, brainroute
    from taskuary.llm import build_llm
    from taskuary.store import SQLiteStore
    db = SQLiteStore(os.environ['TASKUARY_LIVE_DB'])
    # a CLI brain is a connection in the home's config.toml, not in the db - a scratch home has none, so name the one the card picks
    pick = brainroute.choose(db, 'report').pick
    if pick.startswith('cli:') and pick[4:] not in (config.load().get('cli_connections') or {}):
        c = config.load(); c.setdefault('cli_connections', {})[pick[4:]] = {'cmd': pick[4:]}; config.save(c)
    # the scheduled Advisor is handed the REPORT brain (reports.run_due -> run_report_source), not job='advisor'
    return build_llm(db, job='report')


def live(real, arms=('empty', 'filled')) -> dict:
    from taskuary import assistant, faults, terminal
    r, res = Router(real), []
    sessions, agenda = dict(terminal.SESSIONS), dict(assistant._AGENDA)
    try:
        with mock.patch.object(faults, 'scratch_home', lambda: True):
            for w in worlds():
                for arm in arms:
                    try: res.append(one(w, r, arm))
                    except Exception as e: res.append({'world': w[0], 'arm': arm, 'error': str(e)[:300], 'cases': [], 'lines': []})
            if 'filled' in arms: res.append(one(('stale', _stale_world, None, []), r, 'stale'))
    finally:
        for sid, x in list(terminal.SESSIONS.items()):
            if sid not in sessions:
                try: x.alive = False
                except Exception: pass
                terminal.SESSIONS.pop(sid, None)
        assistant._AGENDA.clear(); assistant._AGENDA.update(agenda)
    return {'calls': r.calls, 'results': res, 'prompts': r.seen}


def problems(got) -> list:
    """What must never happen whatever the model's taste: a failed check, memory read in the wrong arm, a put-down line read or cited."""
    res = got['results']
    return ([f"{x['world']}/{x['arm']}: {x['error']}" for x in res if x.get('error')]
            + [f"{x['world']}/{x['arm']}: memory {'missing' if x['arm'] != 'empty' else 'read'}" for x in res
               if 'error' not in x and x['memory_in_prompt'] != (x['arm'] != 'empty')]
            + [f"{x['world']}/{x['arm']}: put-down line {x['stale_in_prompt'] + x['stale_in_lines']}" for x in res
               if x.get('stale_in_prompt') or x.get('stale_in_lines')]
            + ([f"{got['calls']} model calls"] if got['calls'] > 120 else []))


@pytest.mark.skipif(not LIVE, reason='calls the configured AI: TASKUARY_LIVE_MEMORY=1 python -m tests.test_rail_advisor_memory_live')
def test_live_memory_ab_on_the_rail_advisor():
    pytest.skip("the suite's isolation blocks the brain's subprocess and sockets - run python -m tests.test_rail_advisor_memory_live")


if __name__ == '__main__':
    import sys
    if not (LIVE and os.environ.get('TASKUARY_LIVE_DB')): sys.exit('TASKUARY_LIVE_MEMORY=1 and TASKUARY_LIVE_DB (a COPY of a taskuary.db) to run it')
    brain = real_brain()
    if brain is None: sys.exit('TASKUARY_LIVE_DB names no store with an AI connected')
    got = live(brain, tuple(a for a in os.environ.get('TASKUARY_LIVE_ARMS', 'empty,filled').split(',') if a))
    if (out := os.environ.get('TASKUARY_LIVE_OUT')):
        with open(out, 'w', encoding='utf-8') as f: json.dump(got, f, indent=1, default=str)
    print(f"{got['calls']} model calls, {sum(x['secs'] for x in got['prompts']):.0f}s\n" + table(got['results']))
    for x in got['results']:
        for l in x['lines']: print(f"  [{x['arm']:6}] {x['world'][:30]:30} {l['kind']:8} {('NOISE ' + l['noise']) if l['noise'] else '':40.40} {l['text'][:100]}")
    bad = problems(got)
    print('\n'.join(bad) or 'no invariant broken')
    sys.exit(1 if bad else 0)
