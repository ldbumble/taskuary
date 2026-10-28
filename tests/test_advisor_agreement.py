"""THE AGREEMENT RATE (the owner, 2026-10-28: "measure that agreement rate after each release and treat it as the number that matters"):
tools/advisor_agreement.py pairs each lit button with what the owner then did and replays today's fixes on the record. Invented data only -
Northwind stand-ins (CLAUDE.md); the store is a scratch file, opened read-only by the tool."""
import importlib.util, json, sqlite3
from pathlib import Path
import pytest
from taskuary import advisor
from taskuary.store import MemoryStore, SQLiteStore

_P = Path(__file__).resolve().parent.parent / 'tools' / 'advisor_agreement.py'
_spec = importlib.util.spec_from_file_location('advisor_agreement', _P); A = importlib.util.module_from_spec(_spec); _spec.loader.exec_module(A)
DAY = '2026-10-20'


@pytest.fixture
def home(tmp_path):
    s = SQLiteStore(str(tmp_path / 'taskuary.db'))
    n = iter(range(1, 10_000))
    def press(tid, lit, pressed, at, live=('next',), rev='r1', kind='todo', choice=1, tk='task', key=None, state=None, by=None):
        s._exec('INSERT INTO advice_press (Key,TargetKind,TargetId,Revision,Advised,Pressed,Match,ItemKind,CreatedAt,Surface,Lit,Live,Choice,State,By) '
                'VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)', (key or f'{tk}:{tid}', tk, tid, rev, lit or None, pressed, int(lit == pressed), kind,
                                                          f'{DAY} {at}', 'desk', lit, json.dumps(list(live)), choice, state, by))
    def outcome(tid, kind, at, actor='owner', **facts):
        s._exec('INSERT INTO outcome (Kind,TargetKind,TargetId,Actor,At,FactsJson) VALUES (?,?,?,?,?,?)', (kind, 'task', tid, actor, f'{DAY} {at}', json.dumps(facts)))
    def model(tid, verb, line='', kind='other', rev='r1'):
        s._exec('INSERT INTO advice (TargetKind,TargetId,Key,Event,Revision,Tier,Line,Verb,Label,Model,CreatedAt,Kind) VALUES (?,?,?,?,?,?,?,?,?,?,?,?)',
                ('task', tid, f'task:{tid}', 'item.shown', rev, 1, line, verb, verb, 'light', f'{DAY} 00:00:00', kind))
    return type('H', (), {'dir': tmp_path, 's': s, 'press': staticmethod(press), 'outcome': staticmethod(outcome), 'model': staticmethod(model),
                          'ds': staticmethod(lambda: A.decisions(A.connect(tmp_path), DAY))})


def test_the_lit_button_pressed_is_right_another_is_wrong_and_walking_past_is_unclear(home):
    home.press(1, 'close', 'close', '09:00:00', live=['continue'])
    home.press(2, 'continue', 'close', '09:01:00', live=['continue'])
    home.press(3, 'approve', 'next', '09:02:00', live=['approve'])
    home.press(4, 'next', 'next', '09:03:00', live=['close'])
    home.press(5, 'let_go', 'close', '09:04:00', live=['defer'])             # Let go and Mark done are one act
    home.press(6, 'close', 'close', '09:05:00', live=[], choice=0)           # one button, no choice: no evidence
    home.press(7, '', 'close', '09:06:00', live=['continue'])                # nothing lit: no decision of the Advisor's
    ds = home.ds()
    assert [(d['target'][1], A.score(d)) for d in ds] == [(1, 'right'), (2, 'wrong'), (3, 'unclear'), (4, 'right'), (5, 'right'), (6, 'unclear')]
    assert A.tally(ds) == {'decisions': 6, 'right': 3, 'wrong': 1, 'unclear': 2, 'pct': 75}
    assert A.line(A.tally(ds), DAY).startswith('Advisor agreement: 75% (3 right, 1 wrong, 2 unclear of 6 decisions')


def test_next_leaves_a_decision_open_and_the_owners_later_act_answers_it(home):
    home.press(1, 'continue', 'next', '09:00:00', live=['continue', 'close'])
    home.press(1, 'continue', 'close', '10:00:00', live=['continue'])        # came back to it and marked it done
    home.press(2, 'continue', 'next', '09:00:00', live=['continue'])
    home.outcome(2, 'agent.continued', '09:30:00')                            # typed to the agent in its pane: the ledger has it
    home.press(3, 'continue', 'next', '09:00:00', live=['continue'])
    home.outcome(3, 'task.closed', '09:30:00', actor='coding')                # an agent's own close is not the owner's answer
    ds = {d['target'][1]: d for d in home.ds()}
    assert (ds[1]['action'], ds[1]['ids'], A.score(ds[1])) == ('close', [1, 2], 'wrong')
    assert (ds[2]['action'], ds[2]['via'], A.score(ds[2])) == ('continue', 'outcome', 'right')
    assert (ds[3]['action'], A.score(ds[3])) == ('next', 'unclear')


def test_a_new_lit_button_on_the_same_item_is_a_new_decision_and_the_same_press_twice_is_one(home):
    home.press(1, 'approve', 'next', '09:00:00', live=['approve'], rev='r1')
    home.press(1, 'close', 'close', '09:05:00', live=['continue'], rev='r2')   # the draft went elsewhere; the close-out lit Mark done
    home.press(2, 'next', 'run_another', '09:00:00', live=['close'])
    home.press(2, 'next', 'run_another', '09:00:05', live=['close'])         # pressed again on the same screen
    ds = home.ds()
    assert [(d['target'][1], d['lit'], d['action']) for d in ds] == [(1, 'approve', 'next'), (2, 'next', 'run_another'), (1, 'close', 'close')]
    assert next(d for d in ds if d['target'][1] == 2)['ids'] == [3, 4]


def test_a_reply_that_went_is_the_answer_as_drafted_or_in_the_owners_words(home):
    home.press(1, 'approve', 'close', '09:00:10', live=['approve', 'reply'])  # Send in the draft (not logged), then Mark done
    home.outcome(1, 'reply.sent', '09:00:05', verb='approve')
    home.press(2, 'reply', 'approve', '09:00:10', live=['reply'])             # Reply lit over a draft; sent as drafted: Reply was wrong
    home.outcome(2, 'reply.sent', '09:00:11', verb='approve')
    home.press(3, 'reply', 'close', '09:00:10', live=['close'])               # no draft yet: Reply wrote it, the owner sent it
    home.outcome(3, 'reply.sent', '09:00:05', verb='approve')
    home.press(4, 'approve', 'close', '09:00:10', live=['approve'])           # sent in their own words agrees with Send
    home.outcome(4, 'reply.sent', '09:00:05', verb='edit')
    home.press(5, 'approve', 'close', '09:00:10', live=['approve'])           # the draft dropped, nothing sent: Send was wrong
    ds = {d['target'][1]: d for d in home.ds()}
    assert {t: (d['action'], A.score(d)) for t, d in ds.items()} == {1: ('sent', 'right'), 2: ('sent', 'wrong'), 3: ('sent', 'right'),
                                                                      4: ('edited', 'right'), 5: ('close', 'wrong')}


def test_the_window_and_the_breakdown(home):
    home.press(1, 'continue', 'close', '09:00:00', live=['continue'], state='stopped', by='rule')
    home.press(2, 'continue', 'close', '11:00:00', live=['continue'])
    home.model(3, 'reply', line='Gail asked twice.')
    home.press(3, 'reply', 'reply', '11:00:00', live=['close'])
    ds = A.decisions(A.connect(home.dir), f'{DAY} 10:00:00')
    assert [d['target'][1] for d in ds] == [2, 3]
    assert [d['target'][1] for d in A.decisions(A.connect(home.dir), DAY, f'{DAY} 10:00:00')] == [1]
    every = {d['target'][1]: d for d in home.ds()}
    assert (every[1]['state'], every[1]['by']) == ('stopped', 'rule'), 'the decision kept at the press is read as it was'
    assert (every[2]['state'], every[3]['by']) == ('~stopped', 'model'), 'else read off the button, marked as a guess; a model row names who lit it'
    out = A.report(home.ds(), DAY)
    assert 'continue (rule)' in out and 'reply (model)' in out and '2  continue (rule, stopped) -> close   e.g. task:1 #1, task:2 #2' in out


def test_the_tool_never_writes_to_the_home_it_measures(home):
    home.press(1, 'close', 'close', '09:00:00', live=['continue'])
    cx = A.connect(home.dir)
    with pytest.raises(sqlite3.OperationalError): cx.execute("DELETE FROM advice_press")
    assert A.main(['--home', str(home.dir), '--since', DAY, '--line']) == 0


# ── the replay of today's fixes ───────────────────────────────────────────────────────────────────────────────────────────────────────
def test_replay_send_over_a_draft_unless_the_reason_is_a_caution_about_it(home):
    home.model(1, 'reply', line='Erin wants it today.', kind='late')
    home.press(1, 'reply', 'approve', '09:00:00', live=['reply'])
    home.model(2, 'reply', line='The draft promises Friday.', kind='draft_caution')
    home.press(2, 'reply', 'redraft', '09:00:00', live=['approve', 'reply'])
    home.model(3, 'reply', line='', kind='draft_caution')                     # a silent caution is no reason shown
    home.press(3, 'reply', 'approve', '09:00:00', live=['reply'])
    cx = A.connect(home.dir); ds = {d['target'][1]: d for d in A.replay(cx, home.ds())}
    # ...and a model's Reply with no reason said lights nothing now (NO DEFAULT VERB, the owner, 2026-10-28): silent, neither right nor wrong
    assert {t: (d['today'], d['how']) for t, d in ds.items()} == {1: ('approve', 'draft'), 2: ('reply', ''), 3: ('', 'quiet')}
    t = A.tally(list(ds.values()), 'today')
    assert (t['right'], t['wrong'], t['silent']) == (1, 1, 1) and A.tally(list(ds.values()))['right'] == 0


def test_replay_mark_done_on_a_stopped_agent_that_left_its_work_finished_by_then(home):
    s = home.s
    t1, t2, t3 = (s.create_task({'Title': f'Export job {i}', 'Status': 'in_progress', 'Kind': 'code'}, 'owner') for i in range(3))
    s._exec("INSERT INTO boardnote (TaskId, Agent, Kind, Body, CreatedAt) VALUES (?,?,?,?,?)", (t1, 'coding', 'done', 'shipped', f'{DAY} 08:00:00'))
    for tid, kind, text, at in ((t2, 'working', '', '07:00:00'), (t2, 'finished', 'The export moved.', '08:00:00'),
                                (t3, 'finished', 'The export moved.', '08:00:00'), (t3, 'working', '', '08:30:00')):
        s._exec('INSERT INTO worker_event (TaskId, Sid, Kind, Text, CreatedAt) VALUES (?,?,?,?,?)', (tid, 's1', kind, text, f'{DAY} {at}'))
    s._exec("INSERT INTO boardnote (TaskId, Agent, Kind, Body, CreatedAt) VALUES (?,?,?,?,?)", (t3, 'coding', 'done', 'later', f'{DAY} 10:00:00'))
    for tid in (t1, t2, t3): home.press(tid, 'continue', 'close', '09:00:00', live=['continue'])
    ds = {d['target'][1]: d for d in A.replay(A.connect(home.dir), home.ds())}
    assert (ds[t1]['today'], ds[t2]['today']) == ('close', 'close'), 'a done note, a finished event no later prompt took up'
    # ...picked up again after it finished, and the done note came after the press: a plain stop, which lights nothing now (NO DEFAULT VERB)
    assert (ds[t3]['today'], ds[t3]['how']) == ('', 'quiet')


def test_replay_a_silent_remind_me_leaves_the_rules_button(home):
    home.model(1, 'defer', line='')
    home.press(1, 'defer', 'reply', '09:00:00', live=['reply', 'close'])
    home.model(2, 'defer', line='Erin is away until Monday.')
    home.press(2, 'defer', 'defer', '09:00:00', live=['reply'])
    ds = {d['target'][1]: d for d in A.replay(A.connect(home.dir), home.ds())}
    assert (ds[1]['today'], ds[1]['how'], A.score(ds[1], 'today')) == ('reply', 'silent', 'right')
    assert (ds[2]['today'], A.score(ds[2], 'today')) == ('defer', 'right'), 'said with its reason, the override stands'


def test_an_unchanged_item_is_replayed_exactly_by_todays_decide(home, monkeypatch):
    home.press(1, 'continue', 'close', '09:00:00', live=['continue'], rev='r1')
    home.press(2, 'continue', 'close', '09:00:00', live=['continue'], rev='r1')
    monkeypatch.setattr(advisor, 'revision', lambda store, k, i: 'r1' if i == 1 else 'r9')
    monkeypatch.setattr(advisor, 'decide', lambda store, key, preread=True: {'state': 'stopped_done', 'verb': 'close'})
    ds = {d['target'][1]: d for d in A.replay(A.connect(home.dir), home.ds(), store=object())}
    assert (ds[1]['today'], ds[1]['how']) == ('close', 'exact') and ds[2]['how'] != 'exact', 'a moved item is never replayed against today\'s store'


# ── the press log keeps the decision it answered ──────────────────────────────────────────────────────────────────────────────────────
def test_a_press_keeps_the_state_and_who_lit_it_from_the_decision_at_its_revision():
    s = MemoryStore()
    t = s.create_task({'Title': 'Offsite agenda', 'Status': 'open', 'Kind': 'reply'}, 'owner')
    s.add_message({'ConversationId': f'c{t}', 'Channel': 'email', 'Subject': 'Offsite agenda', 'FromEmail': 'erin@northwind.example', 'FromName': 'Erin Blake',
                   'SentAt': '2026-10-20 08:00:00', 'BodyText': 'Can you check the agenda?', 'Status': 'routed', 'TaskId': t})
    advisor.kept(s, {'key': f'task:{t}', 'revision': 'r1', 'state': 'asked', 'by': 'model', 'verb': 'reply'})
    i = advisor.press(s, f'task:{t}', None, 'reply', rev='r1', lit='reply', live=['close'])
    j = advisor.press(s, f'task:{t}', None, 'close', rev='r0', lit='reply', live=['reply'])
    rows = {r['Id']: r for r in s._rows('SELECT Id, State, By FROM advice_press')}
    assert (rows[i]['State'], rows[i]['By']) == ('asked', 'model')
    assert (rows[j]['State'], rows[j]['By']) == (None, None), 'a decision kept at another revision is not the one this press answered'


# ── a lit button the owner could not press (trust audit A4, 2026-10-28) ──────────────────────────────────────────────────────────────
def test_a_press_keeps_which_buttons_were_greyed():
    from taskuary import presses
    s = MemoryStore()
    t = s.create_task({'Title': 'Offsite agenda', 'Status': 'open', 'Kind': 'reply'}, 'owner')
    s.add_message({'ConversationId': f'c{t}', 'Channel': 'email', 'Subject': 'Offsite agenda', 'FromEmail': 'erin@northwind.example', 'FromName': 'Erin Blake',
                   'SentAt': '2026-10-20 08:00:00', 'BodyText': 'Can you check the agenda?', 'Status': 'routed', 'TaskId': t})
    i = advisor.press(s, f'task:{t}', None, 'done', lit='regular_agent', live=['reply'], greyed=['regular_agent', 'nat'])
    assert json.loads(s._one('SELECT Greyed FROM advice_press WHERE Id=?', (i,))['Greyed']) == ['regular_agent', 'remove']
    assert presses.rows(s)[-1]['greyed'] == ['regular_agent', 'remove']


def test_the_tool_flags_a_decision_whose_lit_button_was_greyed(home):
    home.press(1, 'regular_agent', 'close', '09:00:00', live=['close'])
    home.press(2, 'close', 'close', '09:01:00', live=['next'])
    home.s._exec("UPDATE advice_press SET Greyed=? WHERE TargetId=1", (json.dumps(['regular_agent']),))
    ds = home.ds()
    assert [d['target'][1] for d in A.lit_greyed(ds)] == [1]
    out = A.report(ds, DAY)
    assert 'lit but greyed (the lit button was disabled at a press): 1' in out and 'regular_agent' in out.split('lit but greyed')[1]


# ── precision, coverage and dropped balls (the design rev 2, 2026-10-28: NO DEFAULT VERB) ─────────────────────────────────────────────
def test_silence_is_counted_apart_and_precision_is_agreement_on_what_was_lit(home):
    home.press(1, 'close', 'close', '09:00:00', live=['continue'], state='answered', by='rule')
    home.press(2, 'continue', 'continue', '09:01:00', live=['close'], state='stopped', by='check')
    home.press(3, 'continue', 'close', '09:02:00', live=['close'], state='stopped', by='check')
    home.press(4, '', 'close', '09:03:00', live=['continue'])                # nothing lit: a silent decision
    home.press(5, '', 'next', '09:04:00', live=['reply'])
    every = A.decisions(A.connect(home.dir), DAY, silent=True)
    assert [d['target'][1] for d in home.ds()] == [1, 2, 3], 'the scored decisions are the lit ones, as before'
    assert {d['target'][1]: d['by'] for d in every if not d['lit']} == {4: 'silent', 5: 'silent'}
    p = A.precision(every)
    assert (p['all']['pct'], p['check']['pct'], p['check']['right'] + p['check']['wrong'], p['rest']['pct']) == (67, 50, 2, 100)
    assert A.coverage(every) == {'decisions': 5, 'silent': 2, 'pct': 40}
    assert A.score(next(d for d in every if d['target'][1] == 4)) == 'silent'


def test_a_dropped_ball_is_a_silent_decision_answered_by_picking_the_work_up_with_nothing_fired(home):
    home.press(1, '', 'redraft', '09:00:00', live=['approve', 'redraft'])
    home.press(2, '', 'stop_agent', '09:00:00', live=['stop_agent'])
    home.press(3, '', 'try_again', '09:00:00', live=['close'])               # Try again is Continue
    home.press(4, '', 'close', '09:00:00', live=['continue'])                # put down: no ball dropped
    home.press(5, '', 'continue', '09:00:00', live=['continue'])
    home.model(5, 'continue', line='Attach the export it said it would.', kind='work_gap')
    home.s._exec("UPDATE advice SET CreatedAt=?, Event='agent.check' WHERE TargetId=5", (f'{DAY} 08:30:00',))   # the check fired: no miss
    cx = A.connect(home.dir)
    every = A.decisions(cx, DAY, silent=True)
    assert sorted(d['target'][1] for d in A.dropped_balls(cx, every)) == [1, 2, 3]
    assert '3 dropped-ball misses' in A.three(cx, every) and 'silent 100% of 5' in A.three(cx, every)


def test_a_lit_decision_from_the_finish_checks_row_is_the_checks(home):
    home.model(1, 'continue', line='Attach the export it said it would.', kind='work_gap')
    home.s._exec("UPDATE advice SET Event='agent.check' WHERE TargetId=1")
    home.press(1, 'continue', 'continue', '09:00:00', live=['continue', 'close'])
    assert home.ds()[0]['by'] == 'check'


def test_the_release_line_carries_all_three(home, capsys):
    home.press(1, 'close', 'close', '09:00:00', live=['continue'])
    home.press(2, '', 'redraft', '09:01:00', live=['approve'])
    assert A.main(['--home', str(home.dir), '--since', DAY, '--line']) == 0
    out = capsys.readouterr().out
    assert out.startswith('Advisor agreement: 100%') and 'precision 100% on 1 lit' in out and 'silent 50% of 2 decisions' in out
    assert '1 dropped-ball miss' in out


def test_replay_the_reasonless_lights_go_dark(home):
    home.press(1, 'continue', 'close', '09:00:00', live=['continue', 'close'], state='stopped', by='rule')
    home.press(2, 'defer', 'close', '09:00:00', live=['defer', 'close'], state='waiting', by='rule')
    home.press(3, 'regular_agent', 'close', '09:00:00', live=['regular_agent', 'close'], state='asked', by='model')
    home.press(4, 'chase', 'chase', '09:00:00', live=['chase'], state='waiting_late', by='rule')
    ds = {d['target'][1]: d for d in A.replay(A.connect(home.dir), home.ds())}
    assert {t: (d['today'], d['how']) for t, d in ds.items()} == {1: ('', 'quiet'), 2: ('', 'quiet'), 3: ('', 'quiet'), 4: ('chase', '')}
    t = A.tally(list(ds.values()), 'today')
    assert (t['right'], t['wrong'], t['silent'], t['pct']) == (1, 0, 3, 100)
