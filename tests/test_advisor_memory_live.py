"""DOES THE ADVISOR USE THE MEMORY, AND IS IT BETTER FOR IT (the memory redesign's question, 2026-10-26).

LEARNED.md reaches the Advisor's model through advisor._learned -> learned_cut.for_reader(store, 'advisor', ...) - but only where the
rulebook hands the item to the model (rulebook `ask`); a state the rule decides alone never reads it. This file measures that on the
advisor_cases world, twice: memory EMPTY (every subject section stripped) and memory FILLED with Northwind lines planted to change the
right answer for named cases - a person who handles a kind of ask (Hand it to a person), a promise a draft breaks (Redraft), a sender
whose mail is put off to a day (Remind me) - plus three lines that must never reach the model: one CLOSED by a later correction
("Gail moved to Ops"), one the owner marked Wrong, one they Forgot.

    plumbing (normal suite, scripted brain): the planted lines reach the prompts of the items the model reads, the dead ones never do,
              every receipt names what was read, and a model's memory-borne move reaches the strip
    live      (opt-in): TASKUARY_LIVE_MEMORY=1 and TASKUARY_LIVE_DB = a COPY of a taskuary.db with an AI card (opening it migrates it).
              The suite's process guard (conftest) blocks every CLI and HTTP call, so the live run is a script:
                  python -m tests.test_advisor_memory_live [out.json]
              It captures each asked case's prompt on a scripted pass, asks the real model all of them in parallel, then replays the
              answers through the real advisor.judge/decide on a fresh world - so what is graded is what the strip would show.

Invented Northwind people only (CLAUDE.md)."""
import json, os, re, sys, tempfile
from concurrent.futures import ThreadPoolExecutor
from unittest import mock
import pytest
from tests import advisor_cases as C

ADDR = lambda n: f'{n}@northwind.example'
TAG = lambda text, k: f'- {text} [s:5 | ev: out1, out2, out3 | seen: 2026-10-20 | k: {k}]'
# THE PLANTED MEMORY: (section slug, line, key) - each in use, as the reflection writes them
LIVE_LINES = [
    ('people', TAG(f'Omar Keller ({ADDR("omar")}) handles building access and badges for you; you hand badge and access asks to him', 'omar badges'), 'omar badges'),
    ('people', TAG(f'Ray Colton ({ADDR("ray")}) runs payroll for you; you hand payroll and overtime-rate questions to him', 'ray payroll'), 'ray payroll'),
    ('people', TAG(f'Erin Blake ({ADDR("erin")}) is your manager; you answer her the same day, before anything else', 'erin manager'), 'erin manager'),
    ('promises', TAG(f'You told Paula Vance ({ADDR("paula")}) the Q3 variance file goes to her by Friday 2026-10-30', 'paula variance'), 'paula variance'),
]
# ...and the three that must never reach the model: closed by a correction, marked Wrong, Forgotten
GAIL_OLD = TAG(f'Gail Moreno ({ADDR("gail")}) is in Finance and answers the vendor W-9 and tax-form questions for you', 'gail w9')
GAIL_NEW = f'Gail Moreno moved to Ops; Paula Vance ({ADDR("paula")}) answers the vendor W-9 and tax-form questions for you now'
WRONG = TAG(f'Marcus Reed ({ADDR("marcus")}) signs off the Q4 forecast for you, so his asks can wait for the Friday review', 'marcus waits')
FORGOT = TAG("You put Trainly's (trainly.example) seat notices off to Monday", 'trainly monday')
DEAD = {'gail w9': 'is in finance and answers', 'marcus waits': 'friday review', 'trainly monday': 'off to monday'}

# the cases the memory should decide, and the move that is right once it is known (empty: the advisor_cases grading stands)
NEW = {'Q3 variance file': ({'approve', 'redraft', 'reply'}, {'not_ours'}), 'Board deck numbers': ({'reply'}, {'not_ours', 'defer', 'close'}),
       'W-9 for Brightline Supplies': ({'reply', 'forward'}, {'not_ours'})}
# ...the draft breaks the promise: Redraft, or Reply to write it again (the SYSTEM prompt's own words for a draft that promises wrong)
FILLED_OK = {'Badge access for the new AP clerk': {'forward'}, 'Night shift overtime rate': {'forward'}, 'Q3 variance file': {'redraft', 'reply'},
             'Payworth seat count renewal': {'defer'}}
# what in the model's own line says it used the memory (good), or a dead line (bad)
CUE = {'Badge access for the new AP clerk': r'omar', 'Night shift overtime rate': r'\bray\b', 'Q3 variance file': r'friday|30|promis|told',
       'Board deck numbers': r'manager|same day', 'W-9 for Brightline Supplies': r'paula', 'Payworth seat count renewal': r'friday'}
BAD = {'W-9 for Brightline Supplies': r'gail|finance', 'Q4 forecast numbers': r'friday review|signs off|can wait', 'Trainly seats': r'monday'}


def _strip(doc: str) -> str:
    "LEARNED.md with every line under the five subject sections taken out - the headings and their placeholders stay."
    from taskuary import learned_cut as lc
    for head in lc.SECTIONS.values():
        for raw, _k in lc.lines(doc, head): doc = doc.replace(raw + '\n', '', 1)
    return doc


def plant(s, filled: bool):
    """The memory as the condition has it. Filled: the live lines, the Gail line closed by its correction (memoryedit.remember
    replaces=), the Marcus line marked Wrong, the Trainly line Forgotten - each through the owner's own road."""
    from taskuary import learn, learned_cut as lc, memoryedit
    doc = s.get_doc('learned') or ''
    if not filled: s.save_doc('learned', _strip(doc), 'owner'); return
    for slug, raw, _k in LIVE_LINES + [('people', GAIL_OLD, 'gail w9'), ('people', WRONG, 'marcus waits'), ('work', FORGOT, 'trainly monday')]:
        doc = learn._under(doc, lc.SECTIONS[slug], raw)
    s.save_doc('learned', doc, 'reflect')
    memoryedit.remember(s, GAIL_NEW, section='people', replaces='gail w9')
    memoryedit.mark(s, 'marcus waits', 'wrong'); memoryedit.mark(s, 'trainly monday', 'forget')


def world(filled: bool):
    """(store, {case: item}, syn) - advisor_cases' world, three cases it lacks, and the memory as the condition has it."""
    from taskuary import advisor, funnel
    from taskuary.testing import Factory
    s, by, syn = C.world()
    f, paula, erin = Factory(s), ('Paula Vance', ADDR('paula')), ('Erin Blake', ADDR('erin'))
    # a draft that breaks a promise only the memory knows: Paula was told Friday, the draft says mid-November
    v = f.pending_draft('Q3 variance file', subject='Q3 variance file', body='Any news on the Q3 variance file?', from_name=paula[0],
                        from_email=paula[1], conversation_id='email:q3-variance', sent_at=f.ago(hours=2),
                        draft='Hi Paula - the Q3 variance file will be with you by mid-November. Thanks.')
    # the owner's manager asking: the memory says same day, the rule already lights Reply - does the memory ever show?
    _, bm = f._work('Board deck numbers', kind='task', subject='Board deck numbers', body='Can you send me the headline Q3 numbers for the board deck?',
                    from_name=erin[0], from_email=erin[1], conversation_id='email:board-deck', sent_at=f.ago(hours=4))
    # a vendor asking who takes its W-9: the closed line says Gail, the line that replaced it says Paula
    f._work('W-9 for Brightline Supplies', kind='task', subject='W-9 for Brightline Supplies', from_name='Brightline Accounts', from_email='accounts@brightline.example',
            body='Our W-9 on file has expired. Who on your side should we send the new one to?', conversation_id='email:brightline-w9', sent_at=f.ago(hours=3))
    plant(s, filled)
    funnel.invalidate()
    for t in NEW:
        tid = next(x['TaskId'] for x in s.list_tasks() if x.get('Title') == t)
        by[t] = advisor._item(s, 'task', tid)
    return s, by, syn


def cases(): return [(t, ok, nv) for t, ok, nv, _ in C.CASES] + [(t, *NEW[t]) for t in NEW]


def judge_all(s, by, syn, brain) -> dict:
    """{case: {verb, line, by, state, prompt, key}} - every case through the real advisor.judge -> decide, as advisor_cases.run does."""
    from taskuary import advisor, workerstate as ws
    out = {}
    for t, _ok, _nv in cases():
        it = by.get(t)
        if not it: out[t] = {'verb': None, 'line': 'no item', 'prompt': '', 'key': None}; continue
        on = {x['TaskId'] for x in s.list_tasks() if C.AGENT_ON.get(t) and C.AGENT_ON[t].lower() in str(x.get('Title') or '').lower()}
        live = ws._live
        with mock.patch.object(ws, '_live', lambda tid: object() if tid in on else live(tid)), mock.patch.object(brain, 'case', t, create=True):
            verb, line, prompt = C.judge(s, it, syn, brain)
        out[t] = {'verb': verb, 'line': line, 'prompt': prompt, 'key': it.get('key')}
    return out


class Script:
    """A brain that answers per case: `answers[case]` (a JSON string), else says nothing - and keeps what it was asked."""
    def __init__(self, answers=None): self.answers, self.asked, self.case = answers or {}, {}, None
    def __call__(self, system, user, **kw):
        self.asked[self.case] = (system, user)
        return self.answers.get(self.case) or '{"verb": null, "line": "", "evidence": []}'


def coverage(s, syn) -> dict:
    """{items, asked, rule}: of every item on the table, how many the rulebook hands to the model - where memory can matter at all."""
    from taskuary import advisor, funnel, rulebook
    funnel.invalidate()
    seen, items = set(), []
    for i in (funnel.pile(s, quiet=True).get('items') or []) + (funnel.full_items(s) or []) + list(syn.values()):
        if i.get('key') not in seen: seen.add(i.get('key')); items.append(i)
    from collections import Counter
    st, asked = Counter(), 0
    for i in items:
        tgt = advisor.target_of(s, i.get('key'))
        if tgt and advisor._at_work(s, *tgt): st['working'] += 1; continue
        try: r = rulebook.decide(s, i, advisor.offered(s, i))
        except Exception: r = {'state': 'error', 'ask': False}
        st[r['state']] += 1; asked += bool(r['ask'])
    return {'items': len(items), 'asked': asked, 'rule': len(items) - asked, 'states': dict(st)}


def receipts(s) -> list:
    from taskuary import learned_cut
    return learned_cut.used(s, reader='advisor', limit=500)


def _home():
    from taskuary import faults
    return mock.patch.object(faults, 'scratch_home', lambda: True)


# ---------------------------------------------------------------- the plumbing, on a scripted brain (normal suite)

@pytest.fixture(scope='module')
def filled():
    from taskuary import terminal
    sessions = dict(terminal.SESSIONS)
    try:
        with _home():
            s, by, syn = world(True)
            # the model hands the badge ask to Omar, and says so - the memory's line, its own verb
            b = Script({'Badge access for the new AP clerk': '{"verb": "forward", "line": "Omar handles badges for you.", "evidence": []}'})
            got = judge_all(s, by, syn, b)
            yield s, by, syn, b, got
    finally:
        for sid in [x for x in terminal.SESSIONS if x not in sessions]: terminal.SESSIONS.pop(sid, None)


def test_the_planted_lines_reach_every_prompt_the_model_reads(filled):
    s, by, syn, b, got = filled
    asked = {t: u for t, (_sy, u) in b.asked.items()}
    assert len(asked) >= 20, sorted(asked)
    for t, u in asked.items():
        assert 'WHAT YOU KNOW ABOUT HOW THE OWNER WORKS' in u, f'{t}: no memory block'
        for _slug, raw, _k in LIVE_LINES: assert raw.split(' [s:')[0][2:] in u, f'{t}: lacks {raw[:50]}'
    # ...the correction is read in the owner's words, where the closed line stood
    assert all(GAIL_NEW in u for u in asked.values())


def test_a_closed_wrong_or_forgotten_line_never_reaches_the_model(filled):
    s, by, syn, b, got = filled
    for t, (sy, u) in b.asked.items():
        for k, words in DEAD.items(): assert words not in (sy + u).lower(), f'{t}: the dead line {k!r} reached the prompt'
    keys = {k for r in receipts(s) for k in r['keys']}
    assert keys and not keys & set(DEAD), keys & set(DEAD)
    st = {r['Key']: r['Status'] for r in s._rows('SELECT Key, Status FROM learned_line')}
    assert (st['gail w9'], st['marcus waits'], st['trainly monday']) == ('closed', 'wrong', 'forgotten'), st


def test_every_read_leaves_a_receipt_and_only_the_model_reads(filled):
    """A receipt per asked item, naming the planted keys - and none for an item the rule decided alone: there the memory is never read."""
    s, by, syn, b, got = filled
    rs = receipts(s)
    by_key = {r['target'] for r in rs}
    for t, r in got.items():
        if not r['key']: continue
        assert (r['key'] in by_key) == bool(r['prompt']), f"{t}: asked={bool(r['prompt'])} but receipt={r['key'] in by_key}"
    live = {k for *_, k in LIVE_LINES}
    assert all(live <= set(r['keys']) for r in rs if r['target'] in {x['key'] for x in got.values() if x['prompt']})


def test_a_memory_borne_move_reaches_the_strip(filled):
    """The model's verb, where it differs from the rule's, stands with its line - the memory said as the reason."""
    r = filled[4]['Badge access for the new AP clerk']
    assert (r['verb'], r['line']) == ('forward', 'Omar handles badges for you.'), r


def test_coverage_is_counted(filled):
    s, by, syn, *_ = filled
    c = coverage(s, syn)
    assert c['items'] > c['asked'] > 0 and c['rule'] > 0, c


# ---------------------------------------------------------------- the live A/B (opt-in, a script)

def _brains(n: int):
    from taskuary import config
    from taskuary.llm import build_llm
    from taskuary.store import SQLiteStore
    # the copy names cli:claude; a CLI connection lives in config.toml, so the scratch home gets one
    cfg = config.load()
    if 'claude' not in (cfg.get('cli_connections') or {}): cfg.setdefault('cli_connections', {})['claude'] = {'cmd': 'claude'}; config.save(cfg)
    st = SQLiteStore(os.environ['TASKUARY_LIVE_DB'])
    return [build_llm(st, job='advisor') for _ in range(n)], st


def live(workers: int = 8) -> dict:
    """The A/B with the real model: per condition, capture each asked case's prompt, ask the model them all in parallel, replay the
    answers through judge -> decide on a fresh world. {empty: {...}, filled: {...}, coverage, model}."""
    from taskuary import advisor, brainroute
    from taskuary.llm import ask_json
    brains, st = _brains(workers)
    if not brains[0]: raise SystemExit('TASKUARY_LIVE_DB names no store whose Advisor brain can run')
    out = {'route': str(brainroute.choose(st, 'advisor'))}
    with _home():
        for cond in ('empty', 'filled'):
            s, by, syn = world(cond == 'filled'); cap = Script(); judge_all(s, by, syn, cap)
            if cond == 'filled': out['coverage'] = coverage(s, syn)
            def ask(job):
                (t, (sy, u)), i = job
                try: a = ask_json(brains[i % workers], sy, u, want=advisor.WANT, max_tokens=200); return t, (json.dumps(a.data) if isinstance(a.data, dict) else a.raw), u
                except Exception as e: return t, '', f'{type(e).__name__}: {e}'
            with ThreadPoolExecutor(workers) as ex: ans = {t: (a, u) for t, a, u in ex.map(ask, zip(cap.asked.items(), range(len(cap.asked))))}
            s2, by2, syn2 = world(cond == 'filled')
            got = judge_all(s2, by2, syn2, Script({t: a for t, (a, _u) in ans.items()}))
            for t, r in got.items():
                raw = ans.get(t, ('', ''))[0]
                try: m = json.loads(raw) if raw else {}
                except ValueError: m = {'unparsed': raw[:200]}
                r.update(model=m, prompt_has_memory='WHAT YOU KNOW ABOUT HOW THE OWNER WORKS' in (r['prompt'] or ''),
                         dead_in_prompt=[k for k, w in DEAD.items() if w in (r['prompt'] or '').lower()])
                r.pop('prompt')
            out[cond] = got
    return out


def grade_ab(res: dict) -> list:
    """One row per case the model was asked: empty -> filled verb, the grade each side, and whether the model's line used the memory."""
    rows = []
    for t, ok, nv in cases():
        e, f = res['empty'][t], res['filled'][t]
        if not (e.get('model') or f.get('model')): continue
        fok = FILLED_OK.get(t, ok)
        said = lambda r: str((r.get('model') or {}).get('line') or '').lower() + ' ' + str(r.get('line') or '').lower()
        rows.append({'case': t, 'empty': e['verb'], 'filled': f['verb'], 'model_empty': (e.get('model') or {}).get('verb'),
                     'model_filled': (f.get('model') or {}).get('verb'), 'line_filled': f['line'], 'model_line_filled': (f.get('model') or {}).get('line'),
                     'cites': bool(CUE.get(t) and re.search(CUE[t], said(f))),
                     # ...and whether the STRIP says it: a model that agrees with the rule's verb has its line dropped (advisor.decide)
                     'shown': bool(CUE.get(t) and re.search(CUE[t], str(f.get('line') or '').lower())), 'cites_dead': bool(BAD.get(t) and re.search(BAD[t], said(f))),
                     'g_empty': C.grade(e['verb'], ok, nv), 'g_filled': C.grade(f['verb'], fok, nv), 'dead_in_prompt': f.get('dead_in_prompt')})
    return rows


@pytest.mark.skipif(os.environ.get('TASKUARY_LIVE_MEMORY') != '1' or not os.environ.get('TASKUARY_LIVE_DB'),
                    reason='calls the configured AI: TASKUARY_LIVE_MEMORY=1 and TASKUARY_LIVE_DB (a COPY) to run it')
def test_live_memory_ab():
    import subprocess
    # the suite's process guard (conftest) refuses every CLI and HTTP call - a live brain cannot answer inside it
    if getattr(subprocess.Popen, '__name__', '') != 'Popen': pytest.skip('the suite guards every process: run python -m tests.test_advisor_memory_live')
    rows = grade_ab(live())
    assert not any(r['cites_dead'] or r['dead_in_prompt'] for r in rows), rows


if __name__ == '__main__':
    os.environ.setdefault('TASKUARY_HOME', tempfile.mkdtemp(prefix='tq-advmem-'))
    assert os.environ.get('TASKUARY_LIVE_DB'), 'TASKUARY_LIVE_DB: a COPY of a taskuary.db with an AI card'
    from taskuary import advisor; advisor.BACKGROUND = False
    res = live()
    rows = grade_ab(res)
    if len(sys.argv) > 1: open(sys.argv[1], 'w', encoding='utf-8').write(json.dumps({'res': res, 'rows': rows}, indent=1, default=str))
    for r in rows:
        mark = '' if r['empty'] == r['filled'] else '  <- changed'
        print(f"{r['case'][:34]:34} {str(r['empty']):13} -> {str(r['filled']):13} {r['g_empty']:5}->{r['g_filled']:5} cites={int(r['cites'])} shown={int(r['shown'])} "
              f"dead={int(r['cites_dead'])} | model {r['model_empty']}->{r['model_filled']}: {str(r['model_line_filled'])[:60]}{mark}")
    from collections import Counter
    ch = [r for r in rows if r['empty'] != r['filled']]
    print('asked', len(rows), 'changed', len(ch), 'better', sum(r['g_empty'] != 'right' and r['g_filled'] == 'right' for r in ch),
          'worse', sum(r['g_empty'] == 'right' and r['g_filled'] != 'right' for r in ch),
          'empty', dict(Counter(r['g_empty'] for r in rows)), 'filled', dict(Counter(r['g_filled'] for r in rows)),
          'cites', sum(r['cites'] for r in rows), 'shown', sum(r['shown'] for r in rows), 'dead cited', sum(r['cites_dead'] for r in rows), 'coverage', res.get('coverage'))
