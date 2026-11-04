"""A question asked in a report's, an FYI's or a dashboard's own box is answered from it - it never files a task, starts an agent or
presses anything (the owner, 2026-11-04: "question on report should not start task"). The brain is a lambda, so a failure is Taskuary's."""
import json
from taskuary import concierge, general
from taskuary.store import MemoryStore
from taskuary.testing import Factory

def box(kind, key): return {'area': 'item', 'title': 'x', 'item': {'kind': kind, 'id': key, 'section': 'ask'}}
def runs(s): return s._one('SELECT COUNT(*) AS n FROM run')['n']
ACT = ('\nCALL: {"kind": "task.create_from_text", "params": {"kind": "general", "text": "look into it"}}'
       '\nVIEW: {"op": "press", "button": "regular_agent"}')


def test_a_question_on_a_report_is_answered_from_it_and_files_nothing():
    s = MemoryStore(); f = Factory(s); general.dock_task(s, 'owner')
    pic = f.report_row('Nightly headcount')                   # {"site": "Lakeview", "headcount": 112}
    seen = []
    def llm(system, user, **k):
        seen.append(user)
        return ('Lakeview is at 112.' if '"headcount": 112' in user else 'I could not see it.') + ACT
    before, ran = s.list_tasks(), runs(s)
    out = concierge.say(s, 'what is the Lakeview headcount?', key=f'report:{pic.mid}', llm=llm, view=box('report', f'report:{pic.mid}'))
    assert out['say'] == 'Lakeview is at 112.', out
    assert s.list_tasks() == before and runs(s) == ran and not out.get('view_ops') and not out.get('decision')
    assert len(seen) == 1 and 'what is the Lakeview headcount?' in seen[0]


def test_an_fyi_question_reads_triage_and_its_links():
    s = MemoryStore(); f = Factory(s); general.dock_task(s, 'owner')
    mid = f.message(task_id=None, status='filed', subject='Regional newsletter', body='Sharing for visibility.', from_name='Erin Blake',
                    MailMetaJson=json.dumps({'links': [['the agenda', 'https://intranet.example/agenda']]}))
    s.add_route(mid, None, 'file', None, 'triage: fyi', [], 'triage', verdict={'intent': 'fyi', 'thread': {'asking': 'Erin shares the newsletter',
                'your_part': 'The Lakeview move is in it', 'others': [], 'asks': [], 'aside': [], 'on_you': []}})
    seen, before = [], s.list_tasks()
    out = concierge.say(s, 'anything for me in it?', key=f'msg:{mid}', llm=lambda sy, u, **k: (seen.append(u), 'Only the Lakeview move.')[1],
                        view=box('fyi', f'msg:{mid}'))
    assert out['say'] == 'Only the Lakeview move.'
    assert 'Erin shares the newsletter' in seen[0] and 'The Lakeview move is in it' in seen[0] and 'https://intranet.example/agenda' in seen[0]
    assert s.list_tasks() == before


def test_a_dock_turn_is_not_the_item_box():
    assert concierge.asked_on_item(None) is None and concierge.asked_on_item({'area': 'task', 'item': {'kind': 'report'}}) is None
    assert concierge.asked_on_item(box('dashboard', 'report:7')) == 'dashboard' and concierge.asked_on_item(box('task', 'task:1')) is None
