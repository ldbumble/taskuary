"""The session listing and a new agent's peer list asked git for the checkout's status once per SESSION, one spawn after
another, though every session in a checkout reads the same tree - six sessions, six copies of one answer, 0.1-4.9 s each
on Windows. One read asks once per checkout now. Nothing is cached past the read: the next listing asks git again."""
from unittest import mock
from taskuary import agents, blackboard as bb, terminal

ONE, TWO = '/work/northwind-ledger', '/work/northwind-portal'
STATUS = {ONE: ' M ledger.py\n?? notes.txt', TWO: ' M portal.js'}


class Session:
    alive, subs, ended, agent, label, started = True, [], None, 'coding', 'coding', '2026-10-20 08:00:00'
    def __init__(self, i, cwd): self.sid, self.task_id, self.cwd = f's{i}', 500 + i, cwd
    def info(self, tail=0): return {'sid': self.sid, 'files': sorted(bb.dirty(self.cwd))}
    def files(self): return sorted(bb.dirty(self.cwd))


class Store:
    def get_task(self, tid): return {'Title': f'Invented task {tid}'}
    def running_runs(self): return []


def _sessions(monkeypatch):
    calls = []
    def git(cwd, *args): calls.append(cwd); return STATUS[cwd]
    monkeypatch.setattr(agents, '_git', git)
    ss = {s.sid: s for s in [Session(i, ONE if i < 6 else TWO) for i in range(8)]}
    monkeypatch.setattr(terminal, 'SESSIONS', ss)
    return calls


def test_the_listing_asks_git_once_per_checkout(monkeypatch):
    calls = _sessions(monkeypatch)
    rows = terminal.listing()
    assert sorted(calls) == sorted([ONE, TWO])
    assert [r['files'] for r in rows[:6]] == [['ledger.py', 'notes.txt']] * 6     # every session reads what its own git said
    assert rows[6]['files'] == rows[7]['files'] == ['portal.js']


def test_nothing_outlives_the_read(monkeypatch):
    calls = _sessions(monkeypatch)
    terminal.listing()
    STATUS[ONE] = ' M ledger.py'
    try:
        assert terminal.listing()[0]['files'] == ['ledger.py']                     # the next read sees the tree as it is now
        assert len(calls) == 4
        bb.dirty(ONE); bb.dirty(ONE)
        assert len(calls) == 6                                                     # outside a read, every ask is its own
    finally: STATUS[ONE] = ' M ledger.py\n?? notes.txt'


def test_a_new_agents_peer_list_asks_once(monkeypatch):
    calls = _sessions(monkeypatch)
    ps = bb.peers(Store(), ONE, exclude_tid=500)
    assert [p['tid'] for p in ps] == [501, 502, 503, 504, 505]
    assert all(p['files'] == ['ledger.py', 'notes.txt'] for p in ps)
    assert calls == [ONE]


def test_a_failed_status_is_not_kept(monkeypatch):
    calls = []
    def git(cwd, *args):
        calls.append(cwd)
        if len(calls) == 1: raise OSError('git went away')
        return STATUS[cwd]
    monkeypatch.setattr(agents, '_git', git)
    with bb.one_status():
        with mock.patch.object(agents, '_git', git):
            try: bb.dirty(ONE)
            except OSError: pass
            assert bb.dirty(ONE) == {'ledger.py', 'notes.txt'}
    assert len(calls) == 2
