"""Routines (the owner, 2026-10-29): a coding routine's skill is the coding CLI's own, typed as its slash command in the repository; a
run due while the last one still works is skipped and said on that task; a run missed while the app was closed runs once at the next start."""
import json, pathlib, tempfile, unittest
from datetime import datetime, timedelta
from unittest import mock

from taskuary import reports, terminal, workflows
from taskuary.store import MemoryStore


def store():
    s = MemoryStore()
    s.upsert_agent('coding', 'coding', 'cli', json.dumps({'cmd': 'claude'}))
    return s


def routine(s, **cfg):
    base = {'type': 'agent', 'access': 'write', 'title': 'Weekly review', 'agent': 'coding', 'prompt': 'Review the open pull requests.', 'cron': '0 12 * * 1'}
    base.update(cfg)
    return s.save_source({'Channel': 'report', 'Address': base['title'], 'Owner': 'o', 'Active': 1, 'ConfigJson': json.dumps(base)}, 'o')


def run_task(s, sid):
    return s.create_task({'Title': 'Weekly review - now', 'Summary': 'x', 'Kind': 'coding', 'Status': 'open', 'Priority': 'normal',
                          'Source': 'workflow', 'SourceRef': f'workflow:{sid}', 'Tags': 'workflow-trigger:schedule'}, 'o')


class SkillTests(unittest.TestCase):
    def test_a_coding_routine_opens_on_its_skill_as_a_slash_command_and_pastes_nothing(self):
        home = pathlib.Path(tempfile.mkdtemp()); (home / 'skills' / 'weekly-review').mkdir(parents=True)
        (home / 'skills' / 'weekly-review' / 'SKILL.md').write_text('TASKUARY COPY OF THE STEPS', encoding='utf-8')
        s = store(); sid = routine(s, skill='/weekly-review', cwd=tempfile.mkdtemp())
        with mock.patch('taskuary.config.home', return_value=home):
            d = workflows.definition(s, s.get_source(sid))
            self.assertEqual((d['runs_on'], d['skill'], d['steps']), ('coding', 'weekly-review', ''))      # the CLI resolves it, not Taskuary
            tid = run_task(s, sid)
            self.assertEqual(workflows.slash_of(s, s.get_task(tid)), 'weekly-review')
            seed = terminal.seed_text(s, tid, cli='claude')
        self.assertTrue(seed.startswith('/weekly-review TASK '), seed[:80])
        self.assertNotIn('TASKUARY COPY OF THE STEPS', workflows.brief(d, 'schedule', 'now'))

    def test_a_general_routine_still_reads_the_skill_from_taskuarys_folder(self):
        home = pathlib.Path(tempfile.mkdtemp()); (home / 'skills' / 'weekly-review').mkdir(parents=True)
        (home / 'skills' / 'weekly-review' / 'SKILL.md').write_text('THE STEPS', encoding='utf-8')
        s = store(); sid = routine(s, skill='weekly-review', agent='')
        with mock.patch('taskuary.config.home', return_value=home):
            d = workflows.definition(s, s.get_source(sid))
            self.assertEqual((d['runs_on'], d['steps']), ('general', 'THE STEPS'))
            self.assertEqual(workflows.slash_of(s, s.get_task(run_task(s, sid))), '')

    def test_a_cli_with_no_slash_skills_is_not_handed_one(self):
        s = store(); sid = routine(s, skill='weekly-review', runs_on='coding')
        with mock.patch('taskuary.config.home', return_value=pathlib.Path(tempfile.mkdtemp())):
            self.assertFalse(terminal.seed_text(s, run_task(s, sid), cli='codex').startswith('/'))

    def test_the_forms_repository_and_skill_lie_over_the_draft(self):
        cfg = {'type': 'agent', 'title': 't', 'prompt': 'p'}
        self.assertEqual(workflows.with_runs(cfg, {'coding': True, 'cwd': 'C:/code/ledger', 'skill': '/weekly-review'}),
                         {**cfg, 'runs_on': 'coding', 'cwd': 'C:/code/ledger', 'skill': 'weekly-review'})
        self.assertEqual(workflows.with_runs(cfg, {'coding': False, 'cwd': 'x'}), cfg)
        self.assertEqual(workflows.with_runs({'type': 'zoho_monthly_invoices'}, {'coding': True}), {'type': 'zoho_monthly_invoices'})


class RunTests(unittest.TestCase):
    def test_a_run_due_while_the_last_one_works_is_skipped_and_said_on_that_task(self):
        s = store(); sid = routine(s)
        busy = run_task(s, sid)
        with mock.patch.object(workflows, 'running', return_value=s.get_task(busy)):
            out = workflows.run(s, s.get_source(sid), background=False)
        self.assertEqual((out['busy'], out['task_id']), (True, busy))
        self.assertEqual(len([t for t in s.dock_tasks(f'workflow:{sid}', limit=9)]), 1)                     # no second run
        self.assertTrue(any('not started: this run is still working' in c['Body'] for c in s.list_comments(busy)))

    def test_a_run_missed_while_the_app_was_closed_runs_once_at_the_next_start(self):
        now = datetime.now()
        # a weekly slot passed while closed: due on the first poll after, and only once
        last = (now - timedelta(days=8)).isoformat(sep=' ', timespec='seconds')
        cfg = {'type': 'agent', 'access': 'write', 'cron': f'{now.minute} {now.hour} * * *'}
        self.assertTrue(reports.is_due(cfg, last, startup=True))
        self.assertFalse(reports.is_due(cfg, now.isoformat(sep=' ', timespec='seconds'), startup=True))
        # ...and a daily routine whose slot is still ahead today catches up yesterday's missed one
        later = (now + timedelta(minutes=30))
        if later.date() == now.date():
            daily = {'type': 'agent', 'access': 'write', 'daily_at': f'{later.hour}:{later.minute:02d}'}
            self.assertTrue(reports.is_due(daily, (now - timedelta(days=3)).isoformat(sep=' ', timespec='seconds'), startup=True))
            self.assertFalse(reports.is_due(daily, (now - timedelta(minutes=1)).isoformat(sep=' ', timespec='seconds'), startup=True))
            # a REPORT keeps its own clock: today's slot serves it
            self.assertFalse(reports.is_due({'daily_at': daily['daily_at']}, (now - timedelta(days=3)).isoformat(sep=' ', timespec='seconds')))

    def test_two_presses_at_once_start_one_run_not_two(self):
        # Run now pressed on the desktop and the phone in the same second: each request checked "is a run working?" before either had
        # made its task, so both said no and two agents went to work on the same job
        import threading, time
        s = store(); sid = routine(s); real, outs = workflows.running, []
        def slow(*a, **k):
            got = real(*a, **k); time.sleep(0.2); return got
        with mock.patch.object(workflows, 'running', side_effect=slow), mock.patch.object(workflows, '_spawn', lambda fn: None):
            ts = [threading.Thread(target=lambda: outs.append(workflows.run(s, s.get_source(sid), trigger='manual'))) for _ in range(2)]
            for t in ts: t.start()
            for t in ts: t.join()
        workflows._STARTING.clear()
        self.assertEqual(len(s.dock_tasks(f'workflow:{sid}', limit=9)), 1)
        self.assertEqual(sorted(bool(o.get('busy')) for o in outs), [False, True])



class ChangeTests(unittest.TestCase):
    """THE AGENT CAN CHANGE ITS OWN ROUTINE (the design round, 2026-11-18): asked to make tomorrow's run do more, it had no tool and said
    "I can't". A run asks with change_routine; it is one card the owner presses - a run's repair card - saved by the editor's own save."""
    def setUp(self):
        from taskuary import origin
        self.s = store(); self.sid = routine(self.s); self.tid = run_task(self.s, self.sid)
        p = mock.patch.object(origin, 'of_task', return_value=('owner', '')); p.start(); self.addCleanup(p.stop)

    def test_a_run_asks_once_and_the_press_saves_its_new_instructions(self):
        from taskuary import proposals
        rv = proposals.queue(self.s, self.tid, {'action': 'change_routine', 'prompt': 'Review the open pull requests and list the stale ones.',
                                                'why': 'you asked for the stale ones every week'})
        self.assertTrue(rv, 'queued as one card')
        row = self.s.get_review(rv['reviewId'])
        self.assertIn('change the routine "Weekly review"', row['Reason'])
        self.assertEqual(json.loads(self.s.get_source(self.sid)['ConfigJson'])['prompt'], 'Review the open pull requests.', 'nothing before the press')
        with mock.patch('taskuary.docsync.sync_connections') as synced:
            proposals.execute(self.s, row, 'owner')
        cfg = json.loads(self.s.get_source(self.sid)['ConfigJson'])
        self.assertEqual(cfg['prompt'], 'Review the open pull requests and list the stale ones.')
        self.assertEqual(cfg['flow'][0]['prompt'], cfg['prompt'])
        synced.assert_called()                    # ...by the editor's own save (workflows.save), its tail and all

    def test_the_card_holds_the_new_words_and_his_edit_of_them_is_what_is_saved(self):
        # the owner's live card, 2026-11-24: its box held "Agent works it: changed / prompt: <whole old> -> <whole new>" - "to edit text it should
        # show the edited text?". The card's box is the new words, beside what they were; what he leaves in it is what the press saves
        from taskuary import proposals
        rv = proposals.queue(self.s, self.tid, {'action': 'change_routine', 'prompt': 'Keep each post short.', 'why': 'he wants short posts'})
        row = self.s.get_review(rv['reviewId']); p = json.loads(row['DraftText'])
        self.assertEqual(p['texts'], [{'key': 'flow.s1.prompt', 'label': 'The routine will say', 'was': 'Review the open pull requests.', 'now': 'Keep each post short.'}])
        self.assertNotIn('->', p['texts'][0]['now'])
        with self.assertRaises(ValueError): proposals.execute(self.s, row, 'owner', fields={'flow.s1.agent': 'other'})       # only a box the card drew
        with self.assertRaises(ValueError): proposals.execute(self.s, row, 'owner', fields={'flow.s1.prompt': '  '})
        with mock.patch('taskuary.docsync.sync_connections'):
            out = proposals.execute(self.s, row, 'owner', fields={'flow.s1.prompt': 'Keep each post under 80 words.'})
        self.assertEqual(json.loads(self.s.get_source(self.sid)['ConfigJson'])['flow'][0]['prompt'], 'Keep each post under 80 words.')
        self.assertEqual(out['changed'], 'The routine will say: Keep each post under 80 words.', 'its agent is told what was saved, his edit')
        self.assertEqual(json.loads(proposals.receipt(row, None, out, {'flow.s1.prompt': 'Keep each post under 80 words.'}))['texts'][0]['now'],
                         'Keep each post under 80 words.')

    def test_a_change_card_waiting_from_before_is_drawn_as_its_new_words(self):
        from taskuary import flow, proposals
        was = flow.steps_of(json.loads(self.s.get_source(self.sid)['ConfigJson'])); new = [{**was[0], 'prompt': 'Keep each post short.'}]
        rid = self.s.add_review({'TaskId': self.tid, 'Kind': 'action', 'Status': 'pending', 'Reason': 'x', 'DraftText': json.dumps(
            {'action': 'repair_workflow', 'source_id': self.sid, 'title': 'Weekly review', 'flow': new, 'was': was, 'changes': 'Agent works it: changed\n  prompt: a -> b'})})
        self.assertEqual(proposals.cards_waiting(self.s), 1)
        self.assertEqual(json.loads(self.s.get_review(rid)['DraftText'])['texts'][0]['now'], 'Keep each post short.')
        self.assertEqual(proposals.cards_waiting(self.s), 0, 'once')

    def test_a_task_that_is_no_run_of_a_routine_is_told_so(self):
        from taskuary import proposals
        own = self.s.create_task({'Title': 'Something else', 'Kind': 'general', 'Status': 'open'}, 'o')
        why = []
        self.assertIsNone(proposals.queue(self.s, own, {'action': 'change_routine', 'prompt': 'x', 'why': 'y'}, refused=why))
        self.assertIn('did not come from a routine', why[0])

    def test_any_routine_he_names_changes_its_instructions_and_clock_on_one_card(self):
        # the owner's live task, 2026-11-20: asked to rewrite his routine's instructions, the agent wrote them into a .txt and said "save them
        # from your signed-in app" - a routine is changed by its card from any of his tasks, its instructions and its clock alike
        from taskuary import proposals
        own = self.s.create_task({'Title': 'Make the weekly review better', 'Kind': 'general', 'Status': 'open'}, 'o')
        rv = proposals.queue(self.s, own, {'action': 'change_routine', 'routine': 'weekly review', 'prompt': 'List the stale pull requests first.',
                                           'daily_at': '07:30', 'why': 'you asked for it'})
        self.assertTrue(rv, 'queued as one card')
        p = json.loads(self.s.get_review(rv['reviewId'])['DraftText'])
        self.assertIn('Runs:', p['changes']); self.assertIn('07:30', p['changes'])
        self.assertIn('List the stale pull requests first.', json.dumps(p['flow']))
        with mock.patch('taskuary.docsync.sync_connections'): proposals.execute(self.s, self.s.get_review(rv['reviewId']), 'owner')
        cfg = json.loads(self.s.get_source(self.sid)['ConfigJson'])
        self.assertEqual((cfg['prompt'], cfg['daily_at']), ('List the stale pull requests first.', '07:30'))
        why = []
        self.assertIsNone(proposals.queue(self.s, own, {'action': 'change_routine', 'routine': 'nothing called this', 'prompt': 'x', 'why': 'y'}, refused=why))
        self.assertIn('no routine is called that', why[0])

    def test_a_report_and_a_dashboard_change_by_the_same_one_card(self):
        # the owner, 2026-11-20: a report's question, schedule or name is changed by its card too, saved by its editor's own save
        from taskuary import proposals
        rep = self.s.save_source({'Channel': 'report', 'Address': 'Cash on hand', 'Owner': 'o', 'Active': 1, 'ConfigJson': json.dumps(
            {'type': 'quickbooks', 'title': 'Cash on hand', 'ai_prompt': 'Sum the bank balances.', 'daily_at': '08:00'})}, 'o')
        own = self.s.create_task({'Title': 'Report changes', 'Kind': 'general', 'Status': 'open'}, 'o')
        rv = proposals.queue(self.s, own, {'action': 'change_routine', 'routine': 'Cash on hand', 'prompt': 'Sum the bank balances by account.',
                                           'daily_at': '07:00', 'why': 'you asked'})
        self.assertTrue(rv)
        row = self.s.get_review(rv['reviewId']); p = json.loads(row['DraftText'])
        self.assertEqual(p['action'], 'change_setup'); self.assertIn('change the report "Cash on hand"', row['Reason'])
        self.assertEqual([(t['key'], t['was'], t['now']) for t in p['texts']], [('ai_prompt', 'Sum the bank balances.', 'Sum the bank balances by account.')]); self.assertIn('Runs:', p['changes'])
        with mock.patch('taskuary.docsync.sync_connections'): proposals.execute(self.s, row, 'owner')
        cfg = json.loads(self.s.get_source(rep)['ConfigJson'])
        self.assertEqual((cfg['ai_prompt'], cfg['daily_at'], cfg['type']), ('Sum the bank balances by account.', '07:00', 'quickbooks'))

    def test_a_new_routine_or_report_is_built_from_its_instructions_and_cites_its_source(self):
        # the owner, 2026-11-20: a setup for a general job is built from the best-regarded skill or template found online, named on its card
        from taskuary import proposals
        own = self.s.create_task({'Title': 'Set up social posting', 'Kind': 'general', 'Status': 'open'}, 'o')
        for kind in ('routine', 'report'):
            rv = proposals.queue(self.s, own, {'action': 'save_routine', 'title': f'Social {kind}', 'kind': kind, 'daily_at': '09:00',
                                               'prompt': 'Write one useful, non-promotional post per network, each with its own picture.',
                                               'based_on': 'https://github.com/example/social-content-skill', 'why': 'you asked'})
            self.assertTrue(rv); row = self.s.get_review(rv['reviewId'])
            self.assertIn(f'create the {kind} "Social {kind}"', row['Reason']); self.assertIn('built from https://github.com/example/social-content-skill', row['Reason'])
            with mock.patch('taskuary.docsync.sync_connections'): out = proposals.execute(self.s, row, 'owner')
            cfg = json.loads(self.s.get_source(out['source'])['ConfigJson'])
            self.assertEqual((cfg['prompt'][:20], cfg['daily_at'], cfg['based_on'], bool(workflows.is_workflow(cfg))),
                             ('Write one useful, no', '09:00', 'https://github.com/example/social-content-skill', kind == 'routine'))

    def test_a_routine_whose_words_ask_for_drafts_by_hand_has_its_goal_and_done_when_changed_by_its_card(self):
        # the owner's live routine, 2026-11-20: its goal said "drafts ... for manual posting" and its done-when "three labeled drafts", so each
        # run left a text file - its own words are changed by the same card
        from taskuary import proposals
        rv = proposals.queue(self.s, self.tid, {'action': 'change_routine', 'goal': 'One post card per network, each with its own picture.',
                                                'done_when': 'Each network has its post card waiting for his press.', 'why': 'posts, not files'})
        self.assertTrue(rv); p = json.loads(self.s.get_review(rv['reviewId'])['DraftText'])
        self.assertIn(('goal', '', 'One post card per network, each with its own picture.'), [(t['key'], t['was'], t['now']) for t in p['texts']]); self.assertIn('Done when:', p['changes'])
        with mock.patch('taskuary.docsync.sync_connections'): proposals.execute(self.s, self.s.get_review(rv['reviewId']), 'owner')
        cfg = json.loads(self.s.get_source(self.sid)['ConfigJson'])
        self.assertEqual(cfg['done_when'], 'Each network has its post card waiting for his press.')

    def test_the_editor_saves_by_the_same_road(self):
        with self.assertRaises(ValueError): workflows.save(self.s, {'SourceId': self.sid, 'ConfigPatch': {'flow': [{'id': 's1', 'kind': 'nope'}]}}, 'o')


if __name__ == '__main__': unittest.main()
