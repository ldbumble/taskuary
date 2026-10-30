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


if __name__ == '__main__': unittest.main()
