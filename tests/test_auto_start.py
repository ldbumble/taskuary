"""Both worker kinds start by themselves, by default, and the owner can switch either off (PW-069 to PW-073).

Only coding self-dispatched; a `general` task landed on the Board and waited for a click, which
for the owner meant every non-coding job was a job they had to start by hand. Now a general task
opens its own assistant session the moment triage says so, coding opens its CLI as before, and a
personal `task` stays the owner's to-do. Each kind has its own Settings switch (default on; an
install that had switched coding off keeps unattended starts off for both). The same gates apply
to both: the stranger hold, a configured worker, a repository choice for coding - and a start that
is blocked or fails says so on the task instead of looking like nobody got round to it. One item
starts once: a later message on the same task reuses what is live.
"""
import json, pathlib, unittest
from unittest import mock

from taskuary import general, ingest, senders
from taskuary.ingest import auto_start_ok, ingest_message
from taskuary.store import MemoryStore

ASK = 'Can you sit in on the board meeting Thursday and take the minutes?'


def llm_says(kind, **extra):
    return lambda sy, u, **k: json.dumps({'intent': 'task', 'kind': kind, 'why': 'w', **extra})


def mail(**kw):
    base = {'external_id': 'x1', 'channel': 'email', 'subject': 'board meeting', 'body': ASK, 'from_email': 'sam@northwind.example',
            'from_name': 'Sam', 'conversation_id': 'AAQk-board', 'sent_at': '2026-09-06 09:00', 'source_name': 'dana@northwind.example'}
    return {**base, **kw}


def store(**settings):
    s = MemoryStore()
    s.set_setting('owner_email', 'dana@northwind.example', 't')
    for k, v in settings.items(): s.set_setting(k, v, 't')
    return s


def ingested(s, m, kind, providers=({'pick': 'cli:claude', 'type': 'cli'},), **extra):
    with mock.patch('taskuary.ingest._spawn') as spawn, mock.patch.object(senders, 'wrote_to', return_value=True), \
         mock.patch.object(general, 'provider_options', return_value=list(providers)):
        out = ingest_message(s, m, llm=llm_says(kind, **extra))
    return out, [getattr(c[0][0], '__name__', '') for c in spawn.call_args_list]


def last_reason(s): return s._rows('SELECT * FROM route ORDER BY RouteId DESC')[0]['Reason']
def comments(s, tid): return [c['Body'] for c in s.list_comments(tid)]


class AutoStartTests(unittest.TestCase):
    def test_a_general_task_opens_its_own_assistant_session_by_default(self):
        s = store()
        out, spawned = ingested(s, mail(), 'general')
        self.assertEqual(spawned, ['_auto_general'])
        self.assertIn('sent to the assistant', last_reason(s))
        self.assertEqual(s.get_task(out['task_id'])['Kind'], 'general')

    def test_coding_still_opens_its_cli(self):
        s = store()
        _out, spawned = ingested(s, mail(subject='importer down', body='the importer throws in jobs/import.py'), 'coding')
        self.assertEqual(spawned, ['_auto_code'])

    def test_a_personal_task_starts_nothing(self):
        s = store()
        _out, spawned = ingested(s, mail(), 'task')
        self.assertEqual(spawned, []); self.assertIn('yours to do', last_reason(s))

    def test_each_kind_has_its_own_switch_and_off_keeps_the_work_visible_for_a_click(self):
        s = store(general_auto_enabled='0')
        out, spawned = ingested(s, mail(), 'general')
        self.assertEqual(spawned, [])
        self.assertEqual(s.get_task(out['task_id'])['Status'], 'open')
        self.assertIn('auto-start is off for the assistant (Settings)', last_reason(s))
        s2 = store(coder_auto_enabled='0')
        _out, spawned = ingested(s2, mail(external_id='c1'), 'coding')
        self.assertEqual(spawned, []); self.assertIn('auto-dispatch is off (Settings)', last_reason(s2))
        _out, spawned = ingested(s2, mail(external_id='g1', conversation_id='AAQk-2'), 'general')    # the other switch is untouched
        self.assertEqual(spawned, ['_auto_general'])

    def test_a_stranger_holds_both_kinds_with_the_reason_on_the_task(self):
        for kind in ('general', 'coding'):
            s = store()
            with mock.patch('taskuary.ingest._spawn') as spawn, mock.patch.object(senders, 'wrote_to', return_value=False), \
                 mock.patch.object(general, 'provider_options', return_value=[{'pick': 'cli:claude'}]):
                out = ingest_message(s, mail(from_email='stranger@evil.example'), llm=llm_says(kind))
            self.assertEqual(spawn.call_args_list, [], kind)
            self.assertTrue(s.task_has_tag(out['task_id'], ingest.HOLD_TAG), kind)
            self.assertTrue(any('not auto-started' in c and 'first message from' in c for c in comments(s, out['task_id'])), kind)
            self.assertIn('not auto-worked: first message from stranger@evil.example', last_reason(s))

    def test_no_configured_assistant_provider_is_a_visible_hold_not_a_crash(self):
        s = store()
        out, spawned = ingested(s, mail(), 'general', providers=())
        self.assertEqual(spawned, [])
        self.assertIn('no assistant provider is configured', last_reason(s))
        self.assertTrue(any('not auto-started' in c for c in comments(s, out['task_id'])))

    def test_coding_with_no_repository_anyone_can_name_goes_to_the_agent_that_needs_none(self):
        """Coding is triage's default and the only kind that needs a checkout, so a job with no
        repository was an open task nobody could ever start (the owner, 2026-09-07: "It should be
        general agent that does not need a repo no?"). The assistant takes it and actually starts."""
        s = store()
        with mock.patch.object(ingest, 'repo_candidates', return_value=[{'repo': 'org/a', 'about': 'a'}, {'repo': 'org/b', 'about': 'b'}]):
            out, spawned = ingested(s, mail(subject='fix the thing', body='fix the export in the thing'), 'coding',
                                    needs_repo_choice=True, repo_reason='two repositories are plausible')
        self.assertEqual(spawned, ['_auto_general'])
        self.assertEqual(s.get_task(out['task_id'])['Kind'], 'general')
        self.assertTrue(s.task_has_tag(out['task_id'], ingest.NEEDS_REPO_TAG), 'the record stays: a later hand-off still asks')
        self.assertTrue(any('which repository' in c and 'needs none' in c for c in comments(s, out['task_id'])))
        self.assertIn('sent to the assistant', last_reason(s))

    def test_a_github_item_keeps_its_own_repository_and_its_hand_promotion(self):
        """PW-093: a pull request belongs to the repository it came from, and github work queues for
        the owner to promote - the no-repository reroute must not touch either."""
        s = store()
        with mock.patch.object(ingest, 'repo_candidates', return_value=[{'repo': 'org/a', 'about': 'a'}, {'repo': 'org/b', 'about': 'b'}]):
            out, spawned = ingested(s, mail(channel='github', source_name='org/a', no_auto=True,
                                            subject='PR: fix the export', body='fix the export'), 'coding',
                                    needs_repo_choice=True, repo_reason='two repositories are plausible')
        self.assertEqual(spawned, [])
        self.assertEqual(s.get_task(out['task_id'])['Kind'], 'coding')
        self.assertTrue(s.task_has_tag(out['task_id'], ingest.NEEDS_REPO_TAG))

    def test_a_second_message_on_the_task_does_not_start_a_second_worker(self):
        s = store()
        out, spawned = ingested(s, mail(), 'general')
        self.assertEqual(spawned, ['_auto_general'])
        out2, spawned2 = ingested(s, mail(external_id='x2', body='Also - can you bring the Q2 numbers?', sent_at='2026-09-06 09:05'), 'general')
        self.assertEqual((out2['task_id'], spawned2), (out['task_id'], []))

    def test_a_start_that_was_held_or_failed_leaves_the_task_as_untouched_work(self):
        """The router's own notes are pipeline state, not an agent's work: filing such a task deletes it
        as it would any task nothing ran on."""
        from fastapi.testclient import TestClient
        from taskuary import server
        s = store()
        with mock.patch.object(server, 'store', s):
            out, _spawned = ingested(s, mail(), 'general', providers=())     # held: no provider
            self.assertTrue(any('not auto-started' in c for c in comments(s, out['task_id'])))
            r = TestClient(server.app).post(f"/api/messages/{out['message_id']}/file", json={'learn': False}).json()
        self.assertTrue(r['taskDeleted']); self.assertIsNone(s.get_task(out['task_id']))


class GateTests(unittest.TestCase):
    def _mid(self, s, frm):
        return s.add_message({'ExternalId': 'x', 'Channel': 'email', 'Subject': 's', 'FromEmail': frm, 'SentAt': '2026-09-06 09:00', 'BodyText': ASK, 'Status': 'routed'})

    def test_the_gate_reads_the_kind_then_its_switch_then_the_sender(self):
        s = store()
        with mock.patch.object(general, 'provider_options', return_value=[{'pick': 'p'}]), mock.patch.object(senders, 'wrote_to', return_value=True):
            self.assertEqual(auto_start_ok(s, mail(), self._mid(s, 'sam@northwind.example'), 'task')[0], False)
            self.assertEqual(auto_start_ok(s, mail(), self._mid(s, 'sam@northwind.example'), 'general')[0], True)
            self.assertEqual(auto_start_ok(s, mail(), self._mid(s, 'sam@northwind.example'), 'coding')[0], True)
        s.set_setting('general_auto_enabled', '0', 't')
        ok, why = auto_start_ok(s, mail(), self._mid(s, 'sam@northwind.example'), 'general')
        self.assertEqual((ok, 'Settings' in why), (False, True))

    def test_a_blocked_general_start_never_pays_for_the_sent_items_search(self):
        s = store(general_auto_enabled='0')
        with mock.patch.object(senders, 'wrote_to') as wrote:
            auto_start_ok(s, mail(from_email='new@else.example'), self._mid(s, 'new@else.example'), 'general')
        wrote.assert_not_called()


class WorkerTests(unittest.TestCase):
    def test_the_assistant_session_gets_the_task_as_its_first_ask_once(self):
        s = store()
        tid = s.create_task({'Title': 'board meeting', 'Summary': ASK, 'Kind': 'general'}, 'triage')
        session = mock.Mock()
        with mock.patch.object(general, 'start_session', return_value=session) as start, mock.patch.object(general, 'history', return_value=[]):
            ingest._auto_general(s, tid)
        start.assert_called_once(); session.send_prompt.assert_called_once()
        self.assertIn('board meeting', session.send_prompt.call_args[0][0])
        self.assertTrue(any('auto-started the assistant' in c for c in comments(s, tid)))
        with mock.patch.object(general, 'start_session', return_value=session), mock.patch.object(general, 'history', return_value=[{'role': 'owner'}]):
            ingest._auto_general(s, tid)                                          # a live conversation is reused, not re-asked
        session.send_prompt.assert_called_once()

    def test_a_failed_start_is_written_on_the_task_as_a_failure(self):
        s = store()
        tid = s.create_task({'Title': 'board meeting', 'Summary': ASK, 'Kind': 'general'}, 'triage')
        with mock.patch.object(general, 'start_session', side_effect=RuntimeError('no CLI login')):
            ingest._auto_general(s, tid)
        self.assertTrue(any('Assistant start failed: no CLI login' in c for c in comments(s, tid)))
        self.assertEqual(s.get_task(tid)['Status'], 'open')

    def test_a_full_house_queues_the_general_task_like_a_coding_one(self):
        from taskuary import terminal
        s = store(auto_sessions='1')
        tid = s.create_task({'Title': 'board meeting', 'Summary': ASK, 'Kind': 'general'}, 'triage')
        live = mock.Mock(alive=True)
        with mock.patch.dict(terminal.SESSIONS, {'busy': live}, clear=True), mock.patch.object(general, 'start_session') as start:
            ingest._auto_general(s, tid)
        start.assert_not_called()
        self.assertTrue(any(q['TaskId'] == tid for q in s.queued_dispatches()))


class SettingsTests(unittest.TestCase):
    def test_fresh_installs_default_both_on_and_an_old_opt_out_is_kept_for_both(self):
        s = MemoryStore()
        self.assertEqual((s.get_settings().get('coder_auto_enabled'), s.get_settings().get('general_auto_enabled')), ('1', '1'))
        s2 = MemoryStore()
        s2.set_setting('coder_auto_enabled', '0', 'owner')
        s2._exec("DELETE FROM setting WHERE Name='general_auto_enabled'")     # an install from before the switch existed
        s2.upgrade_auto_start()
        self.assertEqual(s2.get_settings().get('general_auto_enabled'), '0')
        s3 = MemoryStore(); s3.set_setting('general_auto_enabled', '1', 'owner'); s3.set_setting('coder_auto_enabled', '0', 'owner')
        s3.upgrade_auto_start()
        self.assertEqual(s3.get_settings().get('general_auto_enabled'), '1')  # an explicit choice is never overwritten

    def test_settings_exposes_both_switches(self):
        src = pathlib.Path(__file__).resolve().parents[1].joinpath('website', 'src', 'SettingsView.jsx').read_text(encoding='utf-8')
        self.assertIn('general_auto_enabled', src); self.assertIn('coder_auto_enabled', src)


if __name__ == '__main__':
    unittest.main()
