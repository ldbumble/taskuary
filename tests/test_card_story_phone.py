"""The phone tells a task card in the task page's three colours, and names who asked (the owner, 2026-09-28: "make sure
whatsapp/telegram matches this new color scheme"; "why does advisor say YOU in the task? it's the advisor").
"""
from taskuary import remote_assistant as ra
from taskuary.store import MemoryStore


def _task(s, **fields):
    return s.create_task({'Title': 'Investigate the export failures', 'Kind': 'coding', 'Status': 'open',
                          'Summary': 'The Advisor wants the owner to investigate the export failures.', **fields}, 'assistant')


def test_a_task_the_advisor_made_is_the_advisors_ask_never_yours():
    s = MemoryStore(); tid = _task(s, Source='assistant', SourceRef='assistant:idea:7')
    text = ra.story_block(s, {'kind': 'todo', 'lane': 'queued', 'tid': tid, 'ref': 'TQ-0001', 'who': 'owner', 'channel': 'own'})
    assert '🔵 **Advisor** raised · an idea' in text
    assert '**You**' not in text.split('\n')[1]


def test_the_three_parts_wear_the_task_pages_three_colours():
    s = MemoryStore(); tid = _task(s)
    item = {'kind': 'agent', 'lane': 'blocked', 'asking': True, 'tid': tid, 'ref': 'TQ-0001', 'who': 'Erin Blake', 'channel': 'email',
            'agent': 'coder', 'tail': ['Which branch?'], 'choices': ['main', 'release']}
    story, move = ra.story_block(s, item), ra.move_block(s, item)
    assert f'{ra.DOT_TASK} **Erin Blake** asked' in story          # 1 the task - slate
    assert f'{ra.DOT_AGENT} **Coding agent**' in story             # 2 the agent - sage
    assert f'{ra.DOT_YOU} **You** · answer the agent' in move       # 3 you - tan
