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
            'agent': 'coding', 'tail': ['Which branch?'], 'choices': ['main', 'release']}
    story, move = ra.story_block(s, item), ra.move_block(s, item)
    assert f'{ra.DOT_TASK} **Erin Blake** asked' in story          # 1 the task - slate
    assert f'{ra.DOT_AGENT} **Coding agent**' in story             # 2 the agent - sage
    assert f'{ra.DOT_YOU} **You** · answer the agent' in move       # 3 you - tan


def test_a_held_strangers_card_says_it_is_held_and_does_not_lead_with_send_to_agent():
    """F8: a first mail from an unknown address read "waiting to start" over "handed over, not started", led with Send to agent,
    and printed the short body under the title that already was it."""
    from taskuary import concierge, ingest
    s = MemoryStore()
    tid = s.create_task({'Title': 'Please wire the deposit today', 'Kind': 'general', 'Status': 'open', 'Tags': ingest.HOLD_TAG}, 'router')
    mid = s.add_message({'TaskId': tid, 'Channel': 'email', 'Subject': 'Deposit', 'FromName': 'Sam Stranger', 'FromEmail': 'sam@vendor.example',
                         'BodyText': 'Please wire the deposit today.', 'Status': 'open'})
    item = {'key': f'task:{tid}', 'kind': 'todo', 'lane': 'queued', 'tid': tid, 'mid': mid, 'ref': 'TQ-0001', 'who': 'Sam Stranger',
            'channel': 'email', 'title': 'Please wire the deposit today', 'why_idle': 'a first message from this address'}
    chips = [{'verb': 'regular_agent', 'label': 'Send to agent'}, {'verb': 'reply', 'label': 'Reply'},
             {'verb': 'not_ours', 'label': 'Not ours'}, {'verb': 'next', 'label': 'Next'}]
    text = ra.turn_text({'say': 'x', 'item': item, 'chips': chips}, store=s)
    assert text.count(ra.HOLD_LINE) == 1, text
    assert text.count('Please wire the deposit today') == 1, text
    assert 'handed over, not started' not in text and 'Why it has not started' not in text
    # ...and offers no hand-off at all until the sender is trusted: Trust them, then Not ours (A3, 2026-10-22)
    assert 'Reply with one of:\n1 · Trust them\n2 · Not ours\n' in text, text
    assert 'Send to agent\n' not in text.split('Reply with one of:')[1], text


def test_a_teams_draft_says_it_cannot_be_sent_from_the_phone():
    """F20: a Teams review card said "it goes when you send it" - a Teams reply cannot be sent from here."""
    s = MemoryStore()
    tid = s.create_task({'Title': 'Shift cover', 'Kind': 'reply', 'Status': 'open'}, 'o')
    mid = s.add_message({'TaskId': tid, 'Channel': 'teams', 'FromName': 'Gail Moreno', 'FromEmail': 'gail@northwind.example',
                         'Subject': 'Shift cover', 'BodyText': 'Can you cover Saturday?', 'Status': 'open'})
    rid = s.add_review({'TaskId': tid, 'MessageId': mid, 'Kind': 'draft', 'Status': 'pending', 'DraftText': 'Yes, I can cover Saturday.'})
    item = {'key': f'review:{rid}', 'kind': 'review', 'lane': 'approve', 'rid': rid, 'mid': mid, 'tid': tid, 'who': 'Gail Moreno', 'channel': 'teams',
            'title': 'Shift cover'}
    text = ra.turn_text({'say': 'x', 'item': item, 'chips': [{'verb': 'approve', 'label': 'Send the reply'}, {'verb': 'next', 'label': 'Next'}]}, store=s)
    assert "Teams replies can't be sent from here - copy it into Teams, then Mark done" in text, text
    assert 'it goes when you send it' not in text and 'sends the draft above' not in text
    assert 'Yes, I can cover Saturday.' in text


def test_a_general_run_with_no_session_mode_is_a_general_agent():
    """F6: a headless or saved general run carries no session `mode`, and its card said "Coding agent"."""
    s = MemoryStore()
    tid = s.create_task({'Title': 'Summarise the vendor contract', 'Kind': 'general', 'Status': 'in_progress'}, 'owner')
    text = ra.story_block(s, {'kind': 'agent', 'lane': 'working', 'tid': tid, 'ref': 'TQ-0001', 'agent': 'claude', 'working': 'claude',
                              'who': 'claude', 'channel': ''})
    assert f'{ra.DOT_AGENT} **General agent**' in text, text


def test_a_finished_agents_card_names_who_asked_never_the_agent_or_the_task():
    s = MemoryStore()
    tid = s.create_task({'Title': 'Summarise the vendor contract', 'Kind': 'general', 'Status': 'open'}, 'owner')
    mid = s.add_message({'TaskId': tid, 'Channel': 'email', 'Subject': 'Vendor contract', 'FromName': 'Gail Moreno',
                         'FromEmail': 'gail@northwind.example', 'BodyText': 'Can someone summarise this?', 'Status': 'open'})
    item = {'kind': 'agentdone', 'lane': 'report', 'tid': tid, 'mid': mid, 'ref': 'TQ-0001', 'who': 'claude', 'channel': 'email',
            'title': 'Summarise the vendor contract'}
    story, move = ra.story_block(s, item), ra.move_block(s, item)
    assert '**The task**' not in story
    assert f'{ra.DOT_TASK} **Gail Moreno** asked' in story, story
    assert 'to Gail Moreno with what it found' in move and 'claude with' not in move, move
