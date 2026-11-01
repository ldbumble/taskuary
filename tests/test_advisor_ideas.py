"""THE IDEA GRADER (the 2026-11-01 design, S0): tools/advisor_ideas.py grades each Advisor idea by what the owner did with it. Invented
Northwind data only (CLAUDE.md); the store is a scratch file, opened read-only by the tool."""
import importlib.util, json
from pathlib import Path
from taskuary.store import SQLiteStore

_P = Path(__file__).resolve().parent.parent / 'tools' / 'advisor_ideas.py'
_spec = importlib.util.spec_from_file_location('advisor_ideas', _P); I = importlib.util.module_from_spec(_spec); _spec.loader.exec_module(I)
DAY = '2026-10-20'


def test_each_idea_is_graded_by_the_owners_own_act(tmp_path):
    s = SQLiteStore(str(tmp_path / 'taskuary.db'))
    def idea(n, status='open', by=None, kind='idea', tid=None, at=f'{DAY} 09:00:00'):
        s._exec('INSERT INTO idea (IdeaId, Key, Kind, Text, ActionJson, Status, FirstSeen, LastSaid, SaidCount, DecidedBy) VALUES (?,?,?,?,?,?,?,?,1,?)',
                (n, f'idea:{n}', kind, f'Paula asked twice ({n})', json.dumps({'tid': tid} if tid else {}), status, at, at, by))
    idea(1, 'done', 'owner'); s.audit('idea', 1, 'task', 'owner')                      # made a task of it
    idea(2, 'done', 'owner')                                                              # put down with Done
    idea(3, 'dismissed', 'owner', kind='promise')                                         # said no
    idea(4, 'done', 'sweep')                                                              # something else put it down
    idea(5, 'open', tid=40)                                                               # ...a reply went on its task that afternoon
    s._exec("INSERT INTO outcome (Kind,TargetKind,TargetId,Actor,At,FactsJson) VALUES ('reply.sent','task',40,'owner',?,'{}')", (f'{DAY} 15:00:00',))
    idea(6, 'open', at='2999-01-01 00:00:00')                                             # raised just now: not graded yet
    xs = I.ideas(I.connect(tmp_path), DAY)
    assert {i['IdeaId']: i['grade'] for i in xs} == {1: 'taken', 2: 'handled', 3: 'wrong', 4: 'walked', 5: 'taken', 6: 'pending'}
    t = I.tally(xs)
    assert (t['taken'], t['handled'], t['wrong'], t['walked'], t['pending'], t['pct']) == (2, 1, 1, 1, 1, 60)
    out = I.report(xs, DAY)
    assert out.startswith('Advisor ideas: 60% useful') and 'promise' in out


def test_the_tool_never_writes_to_the_home_it_measures(tmp_path):
    SQLiteStore(str(tmp_path / 'taskuary.db'))
    before = (tmp_path / 'taskuary.db').stat().st_mtime_ns
    assert I.main(['--home', str(tmp_path), '--since', DAY, '--line']) == 0
    assert (tmp_path / 'taskuary.db').stat().st_mtime_ns == before
