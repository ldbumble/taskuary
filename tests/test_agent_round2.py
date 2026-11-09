"""THE GENERAL AGENT, ROUND TWO (the owner, 2026-11-05: adapt the best of the open-source assistants - Hermes' skills and session_search,
OpenClaw's cron).

5. Playbooks learn: a turn's lesson reaches its playbook as an amend_playbook proposal on the task - the card a drafted playbook already
   has - and a lesson no playbook takes goes to LEARNED.md. The model says whether there is one.
6. Playbooks are a menu: every one's `when` and its file, read by the agent itself; code no longer hands it one.
7. Search before asking: the search an agent already has also reads what earlier tasks settled (their own endings).
8. Check-backs: the agent wakes on its own task at a time it set, on the reminders' clock, with its note as the turn.
"""
import json, shutil, unittest
from datetime import datetime, timedelta
from unittest import mock

from fastapi.testclient import TestClient
from taskuary import agenttools, checkback, config, general, guard, playbooks, proposals, remind, search, selfclose, server
from taskuary.store import MemoryStore
from tests.test_general_turn_ends_short import a_claude, turn

BILL = """# Post a card transaction as an AP bill
when:      a transaction line from the card feed
uses:      quickbooks (write: bills, vendors)
steps:     match the merchant to a vendor -> create the bill
alone:     bills under $500 to a vendor seen before
ask first: a new vendor
done when: the bill exists in QuickBooks
"""
W9 = BILL.replace('Post a card transaction as an AP bill', 'Collect a vendor W-9').replace('a transaction line from the card feed', 'a new vendor needs a W-9')


def fresh_books(*pages):
    d = playbooks.folder()
    if d.is_dir(): shutil.rmtree(d)
    return [playbooks.write(slug, text) for slug, text in pages]


def owner_task(s, title='Post the Payworth card charge', **kw):
    return s.create_task({'Title': title, 'Kind': 'general', 'Status': 'open', 'OriginBase': 'owner', **kw}, 'owner')


def summary(**extra):
    return selfclose.SUMMARY_OPEN + json.dumps({'about': 'a card charge', 'did': 'Posted the bill', 'on_you': [], 'nothing_left': False, **extra}) + selfclose.SUMMARY_CLOSE


# ── 5. playbooks learn ──────────────────────────────────────────────────────────────────────
class PlaybooksLearnTests(unittest.TestCase):
    def setUp(self): fresh_books(('bill', BILL))

    def test_the_summary_carries_the_lesson_and_the_check_back_off_the_page(self):
        text, summ = selfclose.summary_marker('Done.\n' + summary(lesson={'playbook': 'bill', 'text': 'Payworth is vendor 4471'},
                                                                 check_back={'when': 'tomorrow 9am', 'what': 'the bill posted'}))
        self.assertEqual(text, 'Done.')
        self.assertEqual(summ['lesson']['text'], 'Payworth is vendor 4471'); self.assertEqual(summ['check_back']['what'], 'the bill posted')
        self.assertNotIn('lesson', selfclose.summary_marker(summary(lesson={'playbook': 'bill', 'text': ' '}))[1])

    def test_a_lesson_goes_to_learned_md_named_for_its_playbook_and_no_card_is_made(self):
        """The owner, 2026-11-05: "i thought we were using same memory learned.md" - one memory; the playbook page is theirs alone."""
        s = MemoryStore(); tid = owner_task(s)
        with mock.patch('taskuary.learn.learn_from') as lf:
            self.assertEqual(playbooks.take_lesson(s, tid, {'playbook': 'bill', 'text': 'Payworth is vendor 4471 in QuickBooks'}), {'learned': True})
        said = lf.call_args[0][1]
        self.assertIn('Payworth is vendor 4471', said); self.assertIn(playbooks.parse(BILL)['title'], said)
        self.assertEqual([r for r in s.list_reviews('pending') if r['TaskId'] == tid], [])
        self.assertEqual(playbooks.read('bill'), BILL, 'the page is untouched')

    def test_a_lesson_no_playbook_takes_goes_to_learned_md_and_a_secret_goes_nowhere(self):
        s = MemoryStore(); tid = owner_task(s)
        with mock.patch('taskuary.learn.learn_from') as lf:
            self.assertEqual(playbooks.take_lesson(s, tid, {'playbook': None, 'text': 'The Trainly portal signs in through the company SSO'}), {'learned': True})
            self.assertEqual(playbooks.take_lesson(s, tid, {'playbook': 'no-such-book', 'text': 'Spendly exports as CSV only'}), {'learned': True})
            self.assertIsNone(playbooks.take_lesson(s, tid, {'playbook': 'bill', 'text': 'password: hunter2-Secret!9 for the portal'}))
        self.assertEqual(lf.call_count, 2); self.assertIn('company SSO', lf.call_args_list[0][0][1])
        self.assertEqual([r for r in s.list_reviews('pending') if r['TaskId'] == tid], [])

    def test_a_strangers_task_teaches_nothing_and_schedules_nothing(self):
        s = MemoryStore(); tid = owner_task(s)
        with mock.patch('taskuary.origin.of_task', return_value=('stranger', 'unknown sender')), mock.patch.object(playbooks, 'take_lesson') as tl:
            general.take_lesson_and_check(s, tid, {'playbook': 'bill', 'text': 'x'}, {'when': 'tomorrow', 'what': 'y'})
        tl.assert_not_called(); self.assertFalse(s.get_task(tid).get('CheckBackAt'))

    def test_a_real_turn_leaves_its_lesson_and_its_check_back(self):
        s = MemoryStore(); a_claude(self); tid = owner_task(s)
        reply = 'Posted the bill as Payworth (vendor 4471).\n' + summary(lesson={'playbook': 'bill', 'text': 'Payworth is vendor 4471'},
                                                                          check_back={'when': 'in 2 days', 'what': 'the bill shows paid'})
        with mock.patch('taskuary.learn.learn_from') as lf: seen = turn(s, tid, reply)
        self.assertIn(general.LESSON_LINE, seen['prompt']); self.assertIn(general.CHECK_BACK_LINE, seen['prompt'])
        self.assertTrue(any('Payworth is vendor 4471' in c[0][1] for c in lf.call_args_list), 'the lesson went to LEARNED.md')
        t = s.get_task(tid); self.assertEqual(t['CheckBackWhat'], 'the bill shows paid'); self.assertTrue(t['CheckBackAt'])
        kept = [json.loads(c['Body']) for c in s.list_comments(tid, internal=True) if c['ActorType'] == general.SUMMARY_TYPE]
        self.assertTrue(kept and not any('lesson' in k or 'check_back' in k for k in kept))     # taken off the summary, never drawn


# ── 6. playbooks as a menu ──────────────────────────────────────────────────────────────────
class PlaybookMenuTests(unittest.TestCase):
    def setUp(self): fresh_books(('bill', BILL), ('w9', W9))

    def test_every_playbook_is_one_line_with_its_file_and_no_text_is_handed_over(self):
        s = MemoryStore(); tid = owner_task(s, Tags='playbook:bill')
        system = general._prompt(s, tid)[0]
        self.assertIn(f"- bill: when a transaction line from the card feed -> {playbooks.path_of('bill')} (triage read this task as one)", system)
        self.assertIn(f"- w9: when a new vendor needs a W-9 -> {playbooks.path_of('w9')}", system)
        self.assertNotIn('PROCEDURE FOR THIS JOB', system); self.assertNotIn('bills under $500', system)        # read whole on its own say
        self.assertIn('as the work turns into it', system)

    def test_a_menu_is_short_and_absent_when_off(self):
        s = MemoryStore()
        self.assertLess(len(playbooks.agent_menu(None, s)), 700)
        playbooks.set_on('w9', False); self.assertNotIn('w9', playbooks.agent_menu(None, s))
        s.set_setting('playbooks_enabled', '0', 't'); self.assertNotIn('PLAYBOOKS - ', general._prompt(s, owner_task(s))[0])

    def test_a_brain_with_no_hands_is_handed_the_matched_one_whole(self):
        s = MemoryStore(); a_claude(self); tid = owner_task(s, Tags='playbook:bill')
        s.set_setting('general_agent_hands', 'look', 't')
        seen = turn(s, tid, 'Done.')
        self.assertIn('PLAYBOOKS - ', seen['prompt']); self.assertIn('PROCEDURE FOR THIS JOB', seen['prompt'])
        self.assertIn('bills under $500', seen['prompt'])

    def test_a_strangers_task_still_gets_only_triages_match(self):
        s = MemoryStore(); tid = owner_task(s, Tags='playbook:bill')
        with mock.patch('taskuary.origin.of_task', return_value=('stranger', 'unknown sender')):
            system = general._prompt(s, tid)[0]
        self.assertNotIn('PLAYBOOKS - ', system); self.assertIn('PROCEDURE FOR THIS JOB', system)


# ── 7. search before asking ─────────────────────────────────────────────────────────────────
def settled_task(s, title, did, status='done'):
    tid = s.create_task({'Title': title, 'Kind': 'general', 'Status': 'open', 'OriginBase': 'owner'}, 'owner')
    s.add_comment(tid, 'assistant', general.ASSISTANT_TYPE, did)
    s.add_comment(tid, 'assistant', general.SUMMARY_TYPE, json.dumps({'about': title, 'did': did, 'on_you': [], 'nothing_left': True}))
    if status != 'open': s.update_task(tid, {'Status': status}, 'owner')
    return tid


class SearchBeforeAskingTests(unittest.TestCase):
    def test_an_earlier_tasks_ending_is_found_by_its_words(self):
        s = MemoryStore()
        old = settled_task(s, 'Pay the Spendly invoice', 'Paid through the vendor portal - Spendly is vendor id V-2231, billed to the Ops card')
        settled_task(s, 'Gone', 'Spendly vendor V-2231 again', status='dropped')
        now = owner_task(s, 'Spendly renewal')
        hits = search.outcomes(s, 'spendly vendor', skip=now)
        self.assertEqual([h['tid'] for h in hits], [old]); self.assertIn('V-2231', hits[0]['settled'])
        self.assertIn(f"TQ-{old:04d} (done", search.says_outcomes(hits))
        self.assertEqual(search.outcomes(s, 'spendly vendor', skip=old), [])          # never the task asking
        self.assertEqual(search.outcomes(s, 'spendly portugal'), [])                  # an agent's words: all of them

    def test_a_report_is_an_ending_too(self):
        s = MemoryStore(); tid = owner_task(s, 'Trainly seats')
        s.add_comment(tid, 'agent', 'agent', 'AGENT REPORT\nTrainly signs in through the company SSO at the /sso route')
        self.assertIn('/sso route', search.outcomes(s, 'trainly sso')[0]['settled'])

    def test_the_tools_and_the_brief_read_them(self):
        s = MemoryStore()
        settled_task(s, 'Pay the Spendly invoice', 'Spendly is vendor id V-2231')
        tid = owner_task(s, 'Spendly invoice for November')
        srv, c = config.load()['server'], TestClient(server.app)
        hdr = {'X-Taskuary-Token': srv['agent_token'], guard.TASK_HDR: guard.task_proof(srv, tid)}
        with mock.patch.object(server, 'store', s):
            r = c.post(f'/api/mcp?task={tid}', headers=hdr, json={'jsonrpc': '2.0', 'id': 1, 'method': 'tools/call',
                                                                   'params': {'name': 'search_tasks', 'arguments': {'words': 'spendly vendor'}}})
            self.assertIn('WHAT EARLIER TASKS SETTLED', r.json()['result']['content'][0]['text'])
            got = c.get('/api/agent/messages', params={'task_id': tid, 'words': 'spendly vendor'}, headers=hdr).json()
            self.assertIn('V-2231', got['says'])
        self.assertIn('SEARCH BEFORE YOU ASK', general.HISTORY_LINE); self.assertIn('SEARCH BEFORE YOU ASK', general.SEARCHED_LINE)
        said, prior = general.history_brief(s, tid, hands=False)                        # a brain with no search is handed them
        self.assertIn('V-2231', prior); self.assertIn('WHAT EARLIER TASKS SETTLED', said)


# ── 8. check-backs ──────────────────────────────────────────────────────────────────────────
class CheckBackTests(unittest.TestCase):
    def test_set_says_it_on_the_task_and_refuses_what_it_cannot_read(self):
        s = MemoryStore(); tid = owner_task(s)
        out = checkback.set_check(s, tid, 'tomorrow 9am', 'the refund cleared on the card')
        self.assertTrue(out['ok']); self.assertEqual(s.get_task(tid)['CheckBackAt'][11:], '09:00:00')
        self.assertIn('The agent will check back', s.list_comments(tid)[-1]['Body'])
        for when, what in (('someday', 'x'), ('tomorrow', ''), ('tomorrow', 'password: hunter2-Secret!9')):
            with self.assertRaises(ValueError): checkback.set_check(s, tid, when, what)
        s.update_task(tid, {'Status': 'done'}, 'owner')
        self.assertFalse(s.get_task(tid).get('CheckBackAt'))                         # a closed task is checked back on by nobody

    def test_the_owner_cancels_it_and_a_session_cannot(self):
        s = MemoryStore(); tid = owner_task(s); checkback.set_check(s, tid, 'tomorrow 9am', 'the refund cleared on the card')
        srv, c = config.load()['server'], TestClient(server.app)
        hdr = {'X-Taskuary-Token': srv['agent_token'], guard.TASK_HDR: guard.task_proof(srv, tid)}
        with mock.patch.object(server, 'store', s):
            self.assertEqual(c.delete(f'/api/tasks/{tid}/check-back', headers=hdr).status_code, 403)   # never the agent's own press
            self.assertTrue(s.get_task(tid)['CheckBackAt'])
            self.assertEqual(c.delete(f'/api/tasks/{tid}/check-back').json(), {'ok': True, 'cancelled': True})
            self.assertFalse(s.get_task(tid).get('CheckBackAt')); self.assertFalse(s.get_task(tid).get('CheckBackWhat'))
            self.assertEqual(c.delete(f'/api/tasks/{tid}/check-back').json()['cancelled'], False)
            self.assertEqual(c.delete('/api/tasks/99999/check-back').status_code, 404)

    def test_it_comes_due_on_the_reminders_clock_once(self):
        s = MemoryStore(); tid = owner_task(s)
        checkback.set_check(s, tid, 'in 2 hours', 'Erin Blake answered the invite')
        fired = []
        with mock.patch.object(checkback, 'fire', side_effect=lambda st, t, what: fired.append((t, what))), \
             mock.patch('taskuary.ingest._spawn', lambda fn, *a: fn(*a)), mock.patch('taskuary.ingest.has_room', return_value=True):
            remind.tick(s, datetime.now() + timedelta(minutes=30)); self.assertEqual(fired, [])
            remind.tick(s, datetime.now() + timedelta(hours=3)); remind.tick(s, datetime.now() + timedelta(hours=4))
        self.assertEqual(fired, [(tid, 'Erin Blake answered the invite')])
        self.assertEqual(s.get_task(tid)['Status'], 'open')                             # the task stays where it was

    def test_with_every_slot_full_it_waits_for_the_next_tick(self):
        s = MemoryStore(); tid = owner_task(s); checkback.set_check(s, tid, 'in 1 hour', 'the form was accepted')
        with mock.patch('taskuary.ingest.has_room', return_value=False):
            self.assertEqual(checkback.due(s, datetime.now() + timedelta(hours=2), spawn=lambda *a: None), 0)
        self.assertTrue(s.get_task(tid)['CheckBackAt'])

    def test_the_same_tasks_agent_wakes_with_its_note_as_a_taskuary_line(self):
        s = MemoryStore(); a_claude(self); tid = owner_task(s)
        seen = turn(s, tid, 'Nothing yet.')
        sess = seen['session']
        prompts = []
        with mock.patch.object(type(sess), 'send_prompt', lambda self, text, **k: prompts.append((text, k))):
            checkback.set_check(s, tid, 'in 1 hour', 'the payment to Payworth cleared')
            with mock.patch.object(general, 'session_for', return_value=sess):
                checkback.due(s, datetime.now() + timedelta(hours=2), spawn=lambda fn, *a: fn(*a))
        self.assertEqual(len(prompts), 1); self.assertTrue(prompts[0][1].get('brief'))
        self.assertIn('the payment to Payworth cleared', prompts[0][0]); self.assertTrue(prompts[0][0].startswith('TASKUARY: the check-back'))

    def test_the_door_the_tool_and_the_cli_flag(self):
        s = MemoryStore(); tid = owner_task(s)
        srv, c = config.load()['server'], TestClient(server.app)
        hdr = {'X-Taskuary-Token': srv['agent_token'], guard.TASK_HDR: guard.task_proof(srv, tid)}
        self.assertIn('check_back', agenttools.TOOLS); self.assertEqual(agenttools.TOOLS['check_back'][0], 'own')
        with mock.patch.object(server, 'store', s):
            r = c.post(f'/api/mcp?task={tid}', headers=hdr, json={'jsonrpc': '2.0', 'id': 1, 'method': 'tools/call',
                        'params': {'name': 'check_back', 'arguments': {'when': 'in 2 days', 'what': 'the W-9 came back signed'}}})
            self.assertIn('"ok": true', r.json()['result']['content'][0]['text'])
            bad = c.post('/api/agent/check-back', headers=hdr, json={'task_id': tid, 'when': 'whenever', 'what': 'x'})
            self.assertEqual(bad.status_code, 422)
        self.assertEqual(s.get_task(tid)['CheckBackWhat'], 'the W-9 came back signed')
        from taskuary import cli
        self.assertIn('check_back', cli.AGENT_ACTS); self.assertNotIn('check_back', cli.STRANGER_ACTS)
        self.assertIn('CHECK BACK LATER', general.FINISH_LINE)


if __name__ == '__main__':
    unittest.main()


def test_the_general_agent_reads_the_learned_lines_nearest_its_task():
    """The owner, 2026-11-05: "what learned.md goes to the general agent?" - none reached it; now the trusted lines, small, and the rest on ask."""
    from taskuary import learn
    s = MemoryStore(); tid = s.create_task({'Title': 'Pay the Payworth bill', 'Kind': 'general', 'Status': 'open'}, 'o')
    s.save_doc(learn.DOC, '# LEARNED.md\n\n## How you work\n- Payworth is vendor 4471 in QuickBooks\n- Vendor replies are short, signed Alex\n', 't')
    system = general._prompt(s, tid)[0]
    assert 'WHAT TASKUARY HAS LEARNED ABOUT THE OWNER' in system and 'Payworth is vendor 4471' in system and '--memory' in system
    # ...counted in learned lines, not characters: the head now says how to lean on them too (2026-11-09)
    assert general.learned_block(s, 'x', budget=10).count('\n- ') == 1, 'held to its budget: the first line, never the whole doc'
    with mock.patch('taskuary.origin.of_task', return_value=('stranger', 'unknown sender')):
        assert 'WHAT TASKUARY HAS LEARNED' not in general._prompt(s, tid)[0], "a stranger's task is never told who the owner is"


def test_a_message_that_changes_nothing_is_said_so_in_one_line():
    """The owner, 2026-11-05: "the agent gets new message which is new input it can just say this is the same result nothing changed"."""
    from taskuary import ingest
    assert 'changes nothing' in ingest.REPLAN and 'Nothing new here' in ingest.REPLAN and 'the earlier draft stays' in ingest.REPLAN
