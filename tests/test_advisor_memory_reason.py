"""THE MEMORY'S REASON REACHES THE STRIP, AND ONLY WHERE THE ITEM IS ABOUT IT (the live memory A/B, 2026-10-26). The Advisor read LEARNED.md
and used it - "You answer Erin the same day", "Paula takes W-9s now" - and the strip never said it: a model agreeing with the lit button had
its line dropped. A state the rule decided alone never read the memory at all, colleagues tied in the people lines' ranking, and a hand-off
count stood over another verb. Since 2026-11-02 every state is the model's and reads the memory; its line stands as it said it (no rule to
agree with). Invented Northwind people only (CLAUDE.md)."""
import json
from datetime import datetime, timedelta
from unittest import mock
import pytest
from taskuary import advisor, funnel, learn, learned_cut as lc, rulebook, terminal
from taskuary.testing import Factory
from tests import memory_cases as C

ERIN = C.ERIN_LINE
GAIL_PROMISE = '- You told Gail Moreno (gail@northwind.example) the headcount sheet reaches her every Monday [s:4 | ev: out60, out71 | seen: 2026-10-18 | k: gail monday sheet]'
RAY = '- Ray Colton (ray@northwind.example) runs payroll for you; you hand payroll asks to him [s:5 | ev: out12, out13 | seen: 2026-10-19 | k: ray payroll]'


@pytest.fixture
def w():
    with mock.patch.object(terminal, 'live_sessions', lambda tail=0: []), mock.patch.object(funnel, '_agenda', lambda _s, **kw: []), \
         mock.patch.object(advisor, 'notice', lambda *a, **k: None):
        s, facts = C.world(); funnel.invalidate()
        yield s, facts
        funnel.invalidate()


def plant(s, slug, raw):
    s.save_doc('learned', learn._under(s.get_doc('learned') or '', lc.SECTIONS[slug], raw), 'reflect')


def ask(s, who, title, body, hours=0.3):
    f, at = Factory(s), (datetime.now() - timedelta(hours=hours)).strftime('%Y-%m-%d %H:%M:%S')
    t = f.task(title=title, kind='task')
    f.message(task_id=t, subject=title, body=body, from_name=C.P[who][0], from_email=C.P[who][1], conversation_id=f'email:{title}', sent_at=at)
    funnel.invalidate()
    return t


def judged(s, t, answer: dict) -> tuple:
    """(decision, prompt) - the model's answer through the real judge, then the one decision every surface reads."""
    seen = []
    def brain(system, user, **kw): seen.append(user); return json.dumps(answer)
    advisor.judge(s, advisor.SHOWN, 'task', t, advisor.revision(s, 'task', t), tier=2, llm=brain, key=f'task:{t}')
    return advisor.decide(s, f'task:{t}', preread=False), (seen[-1] if seen else '')


def test_a_forgotten_line_rests_on_nothing(w):
    s, _ = w
    plant(s, 'people', ERIN)
    t = ask(s, 'erin', 'Offsite agenda', 'Can you check the offsite agenda before Thursday?')
    judged(s, t, {'verb': 'reply', 'line': 'You answer Erin the same morning.', 'memory_says': 'You answer Erin, your manager, the same morning', 'evidence': [lc.cite_of('erin blake manager answer')]})
    s.save_doc('learned', s.get_doc('learned').replace(ERIN + '\n', ''), 'owner')
    assert advisor.decide(s, f'task:{t}', preread=False)['line'] == '', 'the line it rested on is gone, so the reason goes with it'


def test_the_prompt_says_a_memory_line_counts_only_for_what_is_current(w):
    s, _ = w
    assert 'counts only when something CURRENT in this item is about it' in advisor.SYSTEM
    assert f"is the reason for {advisor.L('forward')} and nothing else" in advisor.SYSTEM


def waiting_on_gail(s) -> dict:
    t = s.create_task({'Title': 'Headcount sheet sign-off', 'Status': 'waiting', 'WaitingOn': 'person:gail@northwind.example'}, 'owner')
    s.add_message({'ConversationId': 'email:sheet', 'Channel': 'email', 'Subject': 'Headcount sheet sign-off', 'FromEmail': C.OWNER[1], 'FromName': C.OWNER[0],
                   'Direction': 'out', 'Status': 'sent', 'TaskId': t, 'BodyText': 'Can you sign the sheet off?', 'RecipientsJson': json.dumps({'to': ['gail@northwind.example']}),
                   'SentAt': (datetime.now() - timedelta(days=1)).strftime('%Y-%m-%d %H:%M:%S')})
    # ...Gail has written before, on another thread: her name is known by her address
    s.add_message({'ConversationId': 'email:rota', 'Channel': 'email', 'Subject': 'Rota', 'FromEmail': 'gail@northwind.example', 'FromName': 'Gail Moreno',
                   'Status': 'filed', 'BodyText': 'The rota is up.', 'SentAt': (datetime.now() - timedelta(days=9)).strftime('%Y-%m-%d %H:%M:%S')})
    return {'key': f'task:{t}', 'tid': t, 'lane': 'theirs', 'kind': 'task', 'title': 'Headcount sheet sign-off'}


def test_a_wait_reads_the_memory_like_every_state(w):
    """A state the rule decided alone never read the memory (the memory audit, 2026-10-26); since 2026-11-02 every state is the model's, so
    a promise to the person a wait is on is in what it reads - no gate on whether a line names someone."""
    s, _ = w
    it = waiting_on_gail(s); funnel.invalidate()
    plant(s, 'promises', GAIL_PROMISE)
    assert rulebook.facts(s, it, [{'verb': 'defer'}, {'verb': 'chase'}])['state'] == 'waiting'
    d, prompt = judged(s, it['tid'], {'verb': None, 'line': '', 'evidence': []})
    # ...the rail draws this task as its close-out card (the reply went), and whatever its state the promise is read
    assert 'THE STATE (' in prompt and f"(id {lc.cite_of('gail monday sheet')})" in prompt, prompt[:600]
    assert not hasattr(rulebook, 'MEMORY_ASKS') and not hasattr(rulebook, 'memory_on')


def test_people_lines_rank_by_who_is_on_the_item_then_its_subject():
    ls = [(RAY, 'ray payroll'), (C.ERIN_LINE, 'erin blake manager answer'), (GAIL_PROMISE, 'gail monday sheet')]
    one = max(len(r) for r, _ in ls) + 1
    # every colleague shares the domain: by domain alone, the document's first line won the budget
    assert lc.cut(ls, one, {'domain': 'northwind.example'})[0] == [RAY]
    assert lc.cut(ls, one, {'domain': 'northwind.example', 'people': ['gail@northwind.example']})[0] == [GAIL_PROMISE]
    assert lc.cut(ls, one, {'domain': 'northwind.example', 'people': ['erin blake']})[0] == [C.ERIN_LINE]
    assert lc.cut(ls, one, {'topic': 'Weekly headcount sheet for Monday'})[0] == [GAIL_PROMISE]
    assert lc.cut(ls, one, {'sender_name': 'erin blake', 'people': ['gail@northwind.example']})[0] == [C.ERIN_LINE], 'the sender first'
