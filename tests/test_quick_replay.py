import importlib.util, json, pathlib
from datetime import datetime
from unittest import mock
from taskuary import browserview, llm
from taskuary.store import MemoryStore

spec = importlib.util.spec_from_file_location('quick_replay', pathlib.Path(__file__).parents[1] / 'tools' / 'quick_replay.py')
qr = importlib.util.module_from_spec(spec); spec.loader.exec_module(qr)

def test_counts_only_by_depth_and_reason():
    s = MemoryStore()
    a, b, c = (s.create_task({'Title': f'Northwind job {i}', 'Kind': 'general', 'OriginBase': 'owner'}, 'triage') for i in range(3))
    s.judge_task(a, {'difficulty': 'quick'}, 'triage'); s.judge_task(b, {'difficulty': 'hard'}, 'triage')
    s.judge_task(c, {'difficulty': 'quick'}, 'triage'); s.tag_task(c, browserview.WANTS, actor='triage')
    out = qr.replay(s, now=datetime.now())
    assert {k: v for k, v in out.items() if v} == {'general': 3, 'quick': 1, 'deep:difficulty': 1, 'deep:browser': 1}
    assert all(isinstance(v, int) for v in out.values())                    # counts, never text

def test_asking_counts_escalations_and_files_nothing():
    s = MemoryStore()
    a = s.create_task({'Title': 'Northwind job', 'Kind': 'general', 'OriginBase': 'owner'}, 'triage')
    s.judge_task(a, {'difficulty': 'quick'}, 'triage')
    brain = lambda *x, **k: json.dumps({'report': '', 'draft': None, 'question': None, 'done': False, 'escalate': True, 'why': 'files'})
    brain.takes_web, brain.takes_want = False, True
    before = len(s.list_comments(a))
    with mock.patch.object(llm, 'build_llm', return_value=brain): out = qr.replay(s, now=datetime.now(), ask=5)
    assert (out['asked'], out['escalated']) == (1, 1) and len(s.list_comments(a)) == before

def test_window_and_dock_are_left_out():
    s = MemoryStore()
    a = s.create_task({'Title': 'Old job', 'Kind': 'general', 'OriginBase': 'owner'}, 'triage')
    s.judge_task(a, {'difficulty': 'quick'}, 'triage')
    assert qr.replay(s, now=datetime(2030, 1, 1))['general'] == 0
