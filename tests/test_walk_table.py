"""THE WALK TABLE, in process (docs/superpowers/specs/2026-10-30-walk-one-owner-design.md, 6.2): every case of
tests/fixtures/walk_table.json replayed against railwalk on the demo world laid out as the table names it (tests/walkworld.py).
The browser runner (website/browser/walk-table.test.mjs) reads the same file and clicks the same moves."""
import json
from contextlib import ExitStack
from datetime import datetime, timedelta
from pathlib import Path
from unittest import mock

import pytest

import walkworld


CASES = json.loads((Path(__file__).parent / 'fixtures' / 'walk_table.json').read_text(encoding='utf-8'))['cases']


class Walk:
    """The page, as far as the walk goes: the row it has on screen, and the moves it sends."""

    def __init__(self, store, src):
        self.s, self.src, self.out, self.on, self.page = store, src, None, None, []

    def key(self, sym):
        if '-' in sym and sym.startswith('F'):
            a, b = (int(x[1:]) for x in sym.split('-'))
            return 'fyis:' + ','.join(self.key(f'F{n}') for n in range(a, b + 1))
        return walkworld.key_of(self.s, self.src, sym)

    def land(self, out):
        self.out = out
        if out.get('item'): self.on = out['item']['key']
        elif out.get('over'): self.on = None
        return out

    def lines(self):
        from taskuary import concierge, general
        return len(concierge.history(self.s, general.dock_task(self.s, 'owner')[0]['TaskId']))

    def do(self, step: str):
        from taskuary import concierge, funnel, railwalk
        words = step.split()
        verb, args = words[0], words[1:]
        press = next((a[6:] for a in args if a.startswith('press=')), None)
        args = [a for a in args if not a.startswith('press=')]
        if verb == 'start': return self.land(railwalk.start(self.s, press=press))
        if verb == 'next':
            read, self.page = [self.key(x) for x in self.page], []
            return self.land(railwalk.next(self.s, self.on, press=press, read=read))
        if verb == 'next-to-end':
            for _ in range(40):
                if self.do('next').get('item') is None: return self.out
            raise AssertionError('the walk never reached its end')
        if verb == 'back': return self.land(railwalk.back(self.s, self.on, press=press))
        if verb == 'open': return self.land(railwalk.open(self.s, self.key(args[0]), press=press))
        if verb == 'heading': return self.land(railwalk.section(self.s, args[0], press=press))
        if verb == 'leave':
            how = args[1]
            until = (datetime.now() + timedelta(days=3)).strftime('%Y-%m-%d 08:00') if how == 'remind' else None
            note = 'Sorted with the floor team.' if how == 'note' else None
            return self.land(railwalk.leave(self.s, self.key(args[0]), how, press=press, note=note, until=until))
        if verb == 'send':
            sym, closes = args[0], args[1] == 'closes'
            if closes and 'rid' in self.src[sym]: self.s.decide_review(self.src[sym]['rid'], 'approved', 'Sent.', 'owner')
            return self.land(railwalk.leave(self.s, self.key(sym), 'sent', press=press))
        if verb == 'arrive': return walkworld.arrive(self.s, self.src, args[0])
        if verb == 'close-elsewhere': return walkworld.close_elsewhere(self.s, self.src, args[0])
        if verb == 'agent-closes': return walkworld.agent_closes(self.s, self.src, args[0])
        if verb == 'read':
            funnel.settle(self.s, self.key(args[0]), 'surfaced', 'owner', read=True); return walkworld.reconcile(self.s)
        if verb == 'new-chat': funnel.reset_walk(self.s); self.on = None; return None
        if verb == 'phone':
            # the phone's own roads - its Walk pick and its Next tap - and the desk then reads the one walk they share (Q5)
            from taskuary import remote_assistant
            if args[0] == 'start': remote_assistant.walk(self.s, 'owner', opener=False)
            else:
                with concierge.delivering(concierge.PHONE):
                    remote_assistant.run_act(self.s, {'t': 'next'}, {'key': railwalk.on(self.s)} if railwalk.on(self.s) else None, 'owner')
            on = railwalk.on(self.s)
            return self.land({'item': {'key': on} if on else None, 'walk': railwalk.peek(self.s)})
        if verb == 'reload':
            walk = railwalk.peek(self.s)
            self.on = walk['on']
            self.out = {'item': {'key': walk['on']} if walk['on'] else None, 'walk': walk}
            return self.out
        if verb == 'reports-page': self.page.append(args[0]); return None
        if verb == 'peek':
            below = (railwalk.peek(self.s).get('below') or {}).get('item') or {}
            assert below.get('key') == self.key(args[0]), f'prepared {below.get("key")}, wanted {args[0]}'
            return None
        raise ValueError(f'unknown step: {step}')


@pytest.fixture
def world():
    from loguru import logger
    from taskuary import demo, funnel, server, terminal
    from taskuary.processing_startup import initialize
    from taskuary.store import MemoryStore
    from taskuary import assistant
    with ExitStack() as st:
        st.enter_context(mock.patch.object(terminal, 'live_sessions', return_value=[]))
        st.enter_context(mock.patch.dict(assistant._AGENDA))          # M1 lives in the agenda cache: never past this test
        funnel.invalidate(); funnel.forget_states()
        s = MemoryStore()
        st.enter_context(mock.patch.object(server, 'store', s))
        demo.seed(s)
        initialize(s, live_state=[])
        src = walkworld.build(s)
        yield s, src
        funnel.invalidate()


def check(w: Walk, case: dict, out, before: int):
    from taskuary import lanes, railwalk
    s, src = w.s, w.src
    items = walkworld.rows(s)
    want, rid = case['expect'], case['id']
    shown = (out or {}).get('item') or ({'key': w.on} if w.on and want != 'END' else {})   # Back at the top moves nothing
    trail = walkworld.dump(s, src)
    if want == 'END':
        assert not shown and (out.get('walk') or {}).get('ended'), f'{rid}: wanted the end, got {shown.get("key")} - rail {trail}'
    elif want == 'NEW':
        tids = {v.get('tid') for v in src.values()}
        assert shown.get('tid') and shown['tid'] not in tids, f'{rid}: wanted a new task, got {shown.get("key")}'
    elif '-' in want:
        assert shown.get('key') == w.key(want), f'{rid}: wanted {want}, got {shown.get("key")} - rail {trail}'
    else:
        got = walkworld.symbol_of(s, src, shown.get('key') or '', walkworld.rows(s, full=True)) if shown else None
        got = got or (walkworld.symbol_of(s, src, shown['key']) if shown else None)
        assert got == want, f'{rid}: wanted {want}, got {got} ({shown.get("key")}) - rail {trail}'
    for sym in case.get('read') or ():
        assert not any(walkworld.matches(r, src[sym]) for r in items), f'{rid}: {sym} should have been read off the rail - {trail}'
    for sym in (case.get('rail') or {}).get('has') or ():
        assert any(walkworld.matches(r, src[sym]) for r in items), f'{rid}: {sym} should be on the rail - {trail}'
    for sym in (case.get('rail') or {}).get('not') or ():
        assert not any(walkworld.matches(r, src[sym]) for r in items), f'{rid}: {sym} should be off the rail - {trail}'
    for sym in case.get('later') or ():
        row = next((r for r in items if walkworld.matches(r, src[sym])), None)
        assert row and lanes.level_of(row) == 'later', f'{rid}: {sym} should be under For later - {trail}'
    for sym in case.get('reports') or ():
        row = next((r for r in items if walkworld.matches(r, src[sym])), None)
        assert row and lanes.level_of(row) == 'reports' and row.get('kind') == 'agentdone', f'{rid}: {sym} should be a result under Reports - {trail}'
    if case.get('urgent'):
        row = next(r for r in items if walkworld.matches(r, src[case['urgent']]))
        assert lanes.is_urgent(row) and lanes.level_of(row) == 'task', f'{rid}: {case["urgent"]} is urgent, walked in its place'
    if 'lines' in case: assert w.lines() - before == case['lines'], f'{rid}: {w.lines() - before} new chat lines'
    if case.get('opens'):
        opens = [c.get('key') for c in out.get('chips') or [] if c.get('verb') == 'open']
        assert opens == [w.key(x) for x in case['opens']], f'{rid}: the end offered {opens}'
    if case.get('desk'): assert railwalk.on(s) == w.key(case['desk']), f'{rid}: the desk is on {railwalk.on(s)}'
    walk = railwalk.peek(s)
    if 'back' in case: assert (walk.get('above') is not None) == case['back'], f'{rid}: Back {"on" if walk.get("above") else "off"} - above {walk.get("above")}'
    # ONE ORDER: the walk's line is the rail's own drawing order, For later and rows still settling taken out
    assert [r['key'] for r in railwalk.line(items)] == [r['key'] for r in items if lanes.level_of(r) != 'later' and not r.get('settling')]


@pytest.mark.parametrize('case', CASES, ids=[c['id'] for c in CASES])
def test_walk_table(world, case):
    s, src = world
    w = Walk(s, src)
    for step in case['steps']: w.do(step)
    before = w.lines()
    out = w.do(case['action'])
    check(w, case, out, before)
    if case.get('then'):
        out = w.do(case['then']['action'])
        check(w, {'id': case['id'] + '+', **case['then']}, out, w.lines())


def test_the_world_is_the_table():
    """The world itself, in the table's order - what every case stands on."""
    from loguru import logger
    from taskuary import assistant, demo, funnel, lanes, terminal
    from taskuary.processing_startup import initialize
    from taskuary.store import MemoryStore
    with mock.patch.object(terminal, 'live_sessions', return_value=[]), mock.patch.dict(assistant._AGENDA):
        funnel.invalidate()
        s = MemoryStore(); demo.seed(s); initialize(s, live_state=[])
        src = walkworld.build(s)
        assert [sym for _, sym in walkworld.dump(s, src)] == list(walkworld.ORDER)
        assert [lv for lv, _ in walkworld.dump(s, src)] == ['task'] * 6 + ['later'] + ['reports'] * 3 + ['ideas'] + ['fyi'] * 7
        funnel.invalidate()
