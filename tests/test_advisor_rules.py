"""The Advisor's rules for the moments the deep dive found it getting wrong (2026-10-20): an agent's failed run is a failure, a send
refused for its address is fixed at the address, a draft promising what nothing shows is not sent, work an agent can do goes to an
agent, someone quiet past their day is chased - in the system prompt, and the same in the demo's scripted Advisor."""
import json
from taskuary import advisor, buttons, demo, workerstate
from taskuary.store import MemoryStore


def ask(verbs, *extra, item=None):
    text = '\n\n'.join(['EVENT: item.shown', 'THE ITEM: ' + json.dumps(item or {'channel': 'email'}), f'VERBS OFFERED: {verbs}', *extra])
    return json.loads(demo.brain()('Answer with JSON only', text))


def test_the_system_prompt_carries_each_rule():
    for words in ("AN AGENT'S RUN THAT FAILED", 'REFUSED FOR ITS ADDRESS', 'never Redraft', 'PROMISES WHAT NOTHING HERE SHOWS',
                  'WORK AN AGENT CAN DO', 'QUIET PAST THEIR DAY', buttons.label('chase'), buttons.label('regular_agent')):
        assert words in advisor.SYSTEM


def test_an_agents_failed_run_is_what_failed_and_offers_the_task_to_fix_it():
    s = MemoryStore(); t = s.create_task({'Title': 'Fix the export', 'Status': 'in_progress', 'Kind': 'coding'}, 'owner')
    workerstate.record(s, t, 'r1', 'working'); workerstate.record(s, t, 'r1', 'failed', text='the test database was not reachable')
    item = {'key': f'agent:{t}', 'kind': 'agent', 'lane': 'stopped', 'tid': t, 'title': 'Fix the export'}
    f = advisor.failure(s, item)
    assert f['what'] == "the agent's run failed" and 'not reachable' in f['why']
    assert 'new_task' in [v['verb'] for v in advisor.offered(s, item)]
    workerstate.record(s, t, 'r2', 'working'); workerstate.record(s, t, 'r2', 'finished', text='done')
    assert advisor.failure(s, item) is None, 'a run that finished since is no failure'


def test_the_scripted_advisor_never_continues_a_failed_run():
    got = ask('new_task (New task to fix this), continue (Continue), stop_agent (Stop and save)',
              "WHAT FAILED: the agent's run failed - the test database was not reachable")
    assert got['verb'] == 'new_task' and 'not reachable' in got['line']


def test_a_bounced_address_is_fixed_never_redrafted():
    bounce = 'WHAT FAILED: the reply was not sent - the mail server refused erin@northwind.example (5.1.1 no such user)'
    assert ask('new_task (New task to fix this), approve (Send), redraft (Redraft)', bounce)['verb'] == 'new_task'
    assert ask('fix (Open the address book), approve (Send), redraft (Redraft)', bounce)['verb'] == 'fix'


def test_a_draft_promising_what_nothing_shows_is_redrafted_not_sent():
    verbs = 'approve (Send), redraft (Redraft), close (Mark done)'
    promise = 'THE DRAFT WAITING FOR THE OWNER\'S YES: "Sending the Q3 pack now."\nATTACHED TO THE DRAFT: nothing'
    assert ask(verbs, promise)['verb'] == 'redraft'
    assert ask(verbs, promise.replace('nothing', 'q3-pack.xlsx'))['verb'] == 'approve', 'the file is attached: it can go'
    assert ask(verbs, 'THE DRAFT WAITING FOR THE OWNER\'S YES: "Thursday still works."\nATTACHED TO THE DRAFT: nothing')['verb'] == 'approve'


def test_an_issue_with_a_traceback_goes_to_an_agent_and_a_slipped_person_is_chased():
    issue = ask('reply (Reply), regular_agent (Send to agent), not_ours (Not ours)', 'PREVIEW: Traceback: manager_id is null', item={'channel': 'github'})
    assert issue['verb'] == 'regular_agent'
    assert ask('reply (Reply), regular_agent (Send to agent)', 'PREVIEW: can you approve badge access?')['verb'] == 'reply'
    assert ask('chase (Chase them), let_go (Let it go), defer (Remind me)', 'PREVIEW: ')['verb'] == 'chase'


def test_an_idea_is_a_target_of_its_own_and_its_prompt_says_what_it_is():
    from datetime import datetime, timedelta
    s = MemoryStore()
    ago = lambda d: (datetime.now() - timedelta(days=d)).strftime('%Y-%m-%d %H:%M:%S')
    t = s.create_task({'Title': 'Budget', 'Status': 'open'}, 'owner')
    mid = s.add_message({'ConversationId': 'c1', 'Channel': 'email', 'Subject': 'Budget', 'FromEmail': 'ray@northwind.example', 'SentAt': ago(12), 'BodyText': 'q', 'Status': 'filed', 'TaskId': t})
    i = s.upsert_idea({'key': 'followup:c1', 'kind': 'followup', 'text': 'No answer from Ray on "Budget"', 'sig': 'x',
                       'action': {'type': 'followup', 'mid': mid, 'tid': t, 'who_email': 'ray@northwind.example', 'asked_at': ago(10)}}, ago(0))['IdeaId']
    assert advisor.target_of(s, f'idea:{i}') == ('idea', i) and advisor.key_of('idea', i) == f'idea:{i}'
    a = advisor.revision(s, 'idea', i)
    s.set_idea_status(i, 'done', 'owner')
    assert advisor.revision(s, 'idea', i) != a, 'an idea put down is a new moment'
    item = {'key': f'idea:{i}', 'kind': 'idea', 'lane': 'forgotten', 'idea': i, 'tid': t, 'mid': mid, 'title': 'No answer from Ray'}
    p = advisor._prompt(s, advisor.SHOWN, item, [{'verb': 'chase', 'label': 'Chase them'}], 2, 'idea', i)
    assert 'THE IDEA (the assistant raised it; followup)' in p and 'ray@northwind.example quiet 10 days - late for them after 5' in p


def test_a_goal_says_which_step_is_late_and_when_anything_last_moved():
    from datetime import datetime, timedelta
    s = MemoryStore()
    g = s.create_task({'Title': 'Move payroll', 'Status': 'open', 'DoneWhen': 'payroll runs on the new system'}, 'owner')
    s.set_task_checklist(g, ['Export the pay rules', 'Sign-off'], 'owner')
    k = s.create_task({'Title': 'Sign-off', 'Status': 'waiting', 'Assignee': 'person:gail@northwind.example', 'ParentId': g,
                       'DueAt': (datetime.now() - timedelta(days=3)).strftime('%Y-%m-%d')}, 'owner')
    s.link_step(g, s.checklist_id('Sign-off'), k, 'owner')
    line = advisor.goal_line(s, s.get_task(g))
    assert 'THE GOAL: done when payroll runs on the new system; 0 of 2 steps done' in line
    assert 'step 2 "Sign-off" held by Gail, due' in line and '3 days late' in line
    quiet = s.create_task({'Title': 'Quiet goal', 'Status': 'open', 'DoneWhen': 'x'}, 'owner')
    assert 'no news since it was set' in advisor.goal_line(s, s.get_task(quiet))
    got = ask('close (Mark done), defer (Remind me)', line)
    assert got['verb'] == 'defer' and 'Sign-off is 3 days late' in got['line']
    assert ask('close (Mark done), defer (Remind me)', advisor.goal_line(s, s.get_task(quiet)))['verb'] == 'defer'
    assert ask('mine (Put it on my list), not_ours (Not ours), defer (Remind me)', 'THE IDEA (the assistant raised it; idea): "a rule?"')['verb'] == 'mine'
