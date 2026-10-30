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
    s.judge_task(a, {'difficulty': 'standard'}, 'triage'); s.judge_task(b, {'difficulty': 'hard'}, 'triage')
    s.judge_task(c, {'difficulty': 'quick'}, 'triage'); s.tag_task(c, browserview.WANTS, actor='triage')
    out = qr.replay(s, now=datetime.now())
    assert {k: v for k, v in out.items() if v} == {'general': 3, 'quick': 1, 'deep:hard': 1, 'deep:browser': 1}
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

def test_asking_counts_answers_questions_and_closes():
    s = MemoryStore()
    ts = [s.create_task({'Title': f'Northwind job {i}', 'Kind': 'general', 'OriginBase': 'owner'}, 'triage') for i in range(3)]
    said = iter([{'report': 'Go.', 'draft': 'Yes.', 'question': None, 'done': False}, {'report': 'Which day?', 'question': 'Friday or Saturday?', 'done': True},
                 {'report': 'Nothing owed.', 'question': None, 'done': True}])
    brain = lambda *x, **k: json.dumps({'draft': None, 'escalate': False, 'why': 'w', **next(said)})
    brain.takes_web, brain.takes_want = False, True
    with mock.patch.object(llm, 'build_llm', return_value=brain): out = qr.replay(s, now=datetime.now(), ask=5)
    assert {k: out[k] for k in ('asked', 'answered', 'question', 'closed', 'escalated')} == {'asked': 3, 'answered': 1, 'question': 1, 'closed': 1, 'escalated': 0}

def test_window_and_dock_are_left_out():
    s = MemoryStore()
    a = s.create_task({'Title': 'Old job', 'Kind': 'general', 'OriginBase': 'owner'}, 'triage')
    s.judge_task(a, {'difficulty': 'quick'}, 'triage')
    assert qr.replay(s, now=datetime(2030, 1, 1))['general'] == 0

def test_a_stranger_task_says_which_road_made_it_one():
    """63 of 132 general tasks read as a stranger's in a replay (2026-10-30). A colleague at the owner's own domain is trusted; what makes
    a task a stranger's is the WORST sender on it - an outside reply on a colleague's thread - or Taskuary's own words. The replay says
    which, by key and count only."""
    s = MemoryStore(); s.set_setting('owner_email', 'alex@northwind.example', 't')
    def task(*senders, **f):
        tid = s.create_task({'Title': 'Northwind job', 'Kind': 'general', **f}, 'triage'); s.judge_task(tid, {'difficulty': 'standard'}, 'triage')
        for i, a in enumerate(senders):
            s.add_message({'TaskId': tid, 'ExternalId': f'{tid}-{i}', 'Channel': 'email', 'FromEmail': a, 'SourceName': 'alex@northwind.example',
                           'Subject': 's', 'BodyText': 'b', 'SentAt': f'{datetime.now():%Y-%m-%d} 09:0{i}:00', 'Status': 'routed'})
        return tid
    task('erin@northwind.example')                                            # a colleague: trusted, quick
    task('erin@northwind.example', 'rep@vendor.example')                      # an outside reply on her thread
    task('rep@vendor.example')
    task(Source='report')
    out = qr.replay(s, now=datetime.now())
    assert (out['quick'], out['deep:stranger']) == (1, 3)
    assert {k: v for k, v in out.items() if k.startswith('stranger:')} == {'stranger:later': 1, 'stranger:opener': 1, 'stranger:taskuary-wrote': 1}
