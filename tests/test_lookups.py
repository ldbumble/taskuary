"""The assistant's look-ups over the whole store: body search, open work, one message, one sender, the docs."""
import unittest
from unittest import mock
from taskuary import concierge, ingest, lookups, toolcatalog
import tests.test_assistant_reactions as T


def world():
    s = T.store()
    with mock.patch.object(ingest, '_spawn'):
        T.arrive(s, subject='Can you fix the export?', body='The nightly export drops inter-company rows.', llm=T.brain('task', 'coding'))
        T.arrive(s, subject='Quarterly numbers', body='Attached are the figures; the freight line looks off.', who='Gail Moreno',
                 email='gail@northwind.example', hours=3, llm=T.brain('task', 'general'))
    return s

def read(s, kind, **p): return concierge.read_op(s, kind, p)


class LookupTests(unittest.TestCase):
    def test_every_new_read_is_offered_and_validated(self):
        b = toolcatalog.block() + toolcatalog.bucket_list('look')    # reachable: the index, then its bucket (2026-09-25)
        for k in lookups.READ:
            self.assertIn(k, b); self.assertTrue(toolcatalog.is_read(k))
        self.assertTrue(toolcatalog.valid('message.read', {}))
        self.assertEqual(toolcatalog.valid('tasks.list', {}), '')

    def test_timeline_search_reaches_the_body_and_prints_the_message_number(self):
        s = world()
        out = read(s, 'timeline.search', contains='freight')
        self.assertIn('Quarterly numbers', out); self.assertRegex(out, r'^m\d+ ')
        self.assertNotIn('export', out)
        self.assertIn('Nothing in the history', read(s, 'timeline.search', contains='zzzz'))

    def test_the_index_follows_edits_and_deletes(self):
        s = world()
        mid = s.message_search(['freight'])[0]
        s._exec('UPDATE message SET BodyText=? WHERE MessageId=?', ('now about pallets', mid))
        self.assertEqual(s.message_search(['freight']), [])
        self.assertEqual(s.message_search(['pallets']), [mid])
        s._exec('DELETE FROM message WHERE MessageId=?', (mid,))
        self.assertEqual(s.message_search(['pallets']), [])

    def test_message_read_opens_one_in_full(self):
        s = world()
        mid = s.message_search(['freight'])[0]
        out = read(s, 'message.read', mid=f'm{mid}')
        self.assertIn('gail@northwind.example', out); self.assertIn('freight line looks off', out)
        self.assertIn('There is no message', read(s, 'message.read', mid='m99999'))

    def test_tasks_list_shows_open_work_and_narrows_by_words(self):
        s = world()
        out = read(s, 'tasks.list')
        self.assertIn('TQ-0001', out); self.assertIn('TQ-0002', out)
        self.assertNotIn('TQ-0001', read(s, 'tasks.list', contains='quarterly'))
        s.update_task(1, {'Status': 'done'}, 't')
        self.assertNotIn('TQ-0001', read(s, 'tasks.list'))
        self.assertIn('TQ-0001', read(s, 'tasks.list', status='done'))

    def test_sender_read_gathers_one_person(self):
        s = world()
        s.add_memory({'Scope': 'sender', 'ScopeKey': 'gail@northwind.example', 'Note': 'She owns the freight budget.', 'Active': 1})
        out = read(s, 'sender.read', who='gail')
        for want in ('Gail Moreno', '1 messages', 'Quarterly numbers', 'TQ-0002', 'freight budget'):
            self.assertIn(want, out)
        self.assertIn('Nobody by', read(s, 'sender.read', who='nobody-at-all'))

    def test_docs_search_finds_the_help_pages_and_the_owners_docs(self):
        s = world()
        s.save_doc('COUNSEL.md', '# Counsel\n\n## Tone\n\nKeep replies to two sentences.\n', 't')
        self.assertIn('your doc COUNSEL.md > Tone', read(s, 'docs.search', query='what tone should replies take'))
        if lookups.SITE_DOCS.is_dir():
            self.assertIn('help/', read(s, 'docs.search', query='connect whatsapp phone'))
        self.assertIn('Nothing in the help', read(s, 'docs.search', query='zzzqqq'))


class AppAtWorkTests(unittest.TestCase):
    """What the agents are doing, what waits on a yes, the calendar, what happened, what failed."""

    def test_agents_now_names_the_task_and_what_the_session_is_asking(self):
        s = world()
        live = [{'taskId': 1, 'agent': 'coder', 'cli': 'claude', 'started': '2026-09-24 09:00', 'phase': 'parked',
                 'line': 'coder asked you: which branch?', 'request': {'text': 'which branch?'}}]
        with mock.patch('taskuary.terminal.live_sessions', return_value=live):
            out = read(s, 'agents.now')
            self.assertIn('TQ-0001', out); self.assertIn('which branch?', out); self.assertIn('claude', out)
        s.start_run(2, 'researcher', 'look into it', 't')
        with mock.patch('taskuary.terminal.live_sessions', return_value=[]):
            self.assertIn('TQ-0002', read(s, 'agents.now'))
            self.assertIn('running in the background', read(s, 'agents.now'))

    def test_approvals_list_shows_drafts_and_proposals(self):
        s = world()
        self.assertIn('Nothing is waiting', read(s, 'approvals.list'))
        s.add_review({'TaskId': 2, 'Kind': 'draft_reply', 'Status': 'pending', 'DraftText': 'Thanks, on it.'})
        s.add_review({'TaskId': 1, 'Kind': 'action', 'Status': 'pending', 'DraftText': '{"action": "open_pr"}', 'Reason': 'the fix is ready'})
        out = read(s, 'approvals.list')
        self.assertIn('draft reply', out); self.assertIn('open_pr', out); self.assertIn('the fix is ready', out)

    def test_pipe_list_names_everything_on_the_rail_not_only_approvals(self):
        s = world()
        out = read(s, 'pipe.list')
        self.assertIn('Can you fix the export?', out); self.assertIn('Quarterly numbers', out)
        self.assertIn('Nothing is waiting', read(s, 'approvals.list'))     # the approvals read alone says nothing waits

    def test_calendar_read_reads_the_days_asked(self):
        s = world()
        ag = {'events': [{'start': '2026-09-25 10:00', 'end': '2026-09-25 10:30', 'subject': 'Budget review', 'all_day': False,
                          'where': 'Room 2', 'who': ['Erin Blake']}], 'errors': [], 'sources': ['outlook: alex@northwind.example'],
              'start': '2026-09-25T00:00', 'end': '2026-09-26T00:00', 'tz': 'UTC'}
        s.set_setting('calendar_enabled', '1', 't')
        with mock.patch('taskuary.calendar.agenda', return_value=ag) as agenda:
            out = read(s, 'calendar.read', **{'from': 'tomorrow', 'days': 1})
        self.assertIn('Budget review', out); self.assertIn('Erin Blake', out)
        self.assertEqual(agenda.call_args.kwargs['days'], 1)
        s.set_setting('calendar_enabled', '0', 't')
        self.assertIn('switched off', read(s, 'calendar.read'))

    def test_activity_list_keeps_the_owner_and_the_agents_apart(self):
        s = world()
        s.audit('task', 2, 'close_from_assistant', 'owner')
        s.audit('lore', 5, 'post', 'coder', actor_type='agent')
        out = read(s, 'activity.list')
        self.assertIn('you: 1 x task close from assistant', out); self.assertIn('agents: 1 x lore post', out)
        self.assertNotIn('lore post', read(s, 'activity.list', who='you'))

    def test_errors_list_gathers_every_failure_written_down(self):
        import pathlib, tempfile
        s = world()
        self.assertIn('Nothing is failing', read(s, 'errors.list'))
        rid = s.start_run(1, 'coder', 'fix it', 't')
        s.update_run(rid, {'Status': 'error', 'LastError': 'the checkout is dirty'}, finished=True)
        s.add_report_run(1, {'at': '2099-01-01 00:00:00', 'title': 'Nightly export check', 'failed': True, 'error': 'HTTP 500'})
        # a log of its own: the real one may be held open by the app's logger, and Windows will not let go of it
        with tempfile.TemporaryDirectory() as d:
            log = pathlib.Path(d) / 'taskuary.log'
            log.write_text('2026-09-24 09:00:00 ERROR   taskuary.outbox:193 the send was refused\n', encoding='utf-8')
            with mock.patch.object(lookups, 'log_path', return_value=log): out = read(s, 'errors.list')
        for want in ('AGENT RUNS THAT FAILED', 'the checkout is dirty', 'Nightly export check', 'HTTP 500', 'the send was refused'):
            self.assertIn(want, out)


class KeptAndFilteredTests(unittest.TestCase):
    """What is kept about the owner, and the rules that filter their mail."""

    def test_memory_list_shows_saved_notes_and_what_learned_md_learned(self):
        from taskuary import learn
        s = world()
        s.add_memory({'Scope': 'sender', 'ScopeKey': 'gail@northwind.example', 'Note': 'She owns the freight budget.', 'Source': 'manual', 'Active': 1})
        s.add_memory({'Scope': 'subject', 'ScopeKey': 'weekly spend report', 'Note': 'NOT A TASK', 'Source': 'verdict', 'Active': 1})
        s.save_doc(learn.DOC, '# Learned\n\n## What becomes a task\n\n- Vendor statements are fyi.\n\n## Hypotheses\n' + learn.HYP_START
                   + '\n- Maybe spend reports are fyi too.\n' + learn.HYP_END + '\n', 't')
        out = read(s, 'memory.list')
        for want in ('SAVED NOTES (2)', 'freight budget', 'weekly spend report', 'Vendor statements are fyi', 'STILL BEING TESTED', 'spend reports are fyi too'):
            self.assertIn(want, out)
        narrow = read(s, 'memory.list', about='freight')
        self.assertIn('freight budget', narrow); self.assertNotIn('weekly spend', narrow)

    def test_rules_list_shows_mutes_and_policies_by_what_they_do(self):
        from taskuary import funnel
        s = world()
        funnel.remember_mute(s, {'sender': 'reports@vendor.example', 'words': ['statement'], 'why': 'finance handles these'})
        for pat in ('alerts@vendor.example', 'alerts@vendor.example'):
            s.save_policy({'Name': f'skip:{pat}', 'Kind': 'sender', 'Pattern': pat, 'Action': 'skip', 'Active': 1}, 't')
        s.save_policy({'Name': 'not-a-task', 'Kind': 'sender_domain', 'Pattern': 'news.example', 'Action': 'ignore', 'Active': 0}, 't')
        out = read(s, 'rules.list')
        for want in ('QUEUE MUTES (1)', 'finance handles these', 'skip (never shown at all): 1', 'alerts@vendor.example', '1 off'):
            self.assertIn(want, out)
        self.assertEqual(out.count('alerts@vendor.example'), 1, 'the same rule twice reads as one')
        self.assertNotIn('news.example', out, 'a rule that is off filters nothing')


if __name__ == '__main__': unittest.main()
