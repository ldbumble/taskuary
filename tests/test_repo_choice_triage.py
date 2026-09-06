"""Which repository, decided once, in triage, from evidence (PW-092 to PW-096).

Coding startup guessed the checkout from word overlap after the fact, so a reimbursement task
opened in the integrations repository and a report failure in an unrelated one. The one triage
verdict now sees the known repositories (the SOUL map and the learned project graph) with the
sender's project associations, and answers `repository`, `needs_repo_choice` and `repo_reason` -
validated against those candidates only. The decision is persisted on the task so startup uses it
instead of guessing again. An explicit owner choice (the `repo:` tag) still wins; a GitHub item's
own repository is authoritative; ambiguity asks the owner instead of forcing a match; and a
checkout whose path is gone is a visible repository choice, never a silent fallback.
"""
import json, unittest
from unittest import mock
from fastapi.testclient import TestClient

from taskuary import ingest, projects, server, terminal, triage
from taskuary.store import MemoryStore

PROFILE = {'cwd_map': {'acme/payroll': 'C:/src/payroll', 'acme/integrations': 'C:/src/integrations', 'acme/portal': 'C:/src/portal'}}
MSG = {'external_id': 'e1', 'channel': 'email', 'from_email': 'dana@acme.example', 'from_name': 'Dana', 'conversation_id': 'AAQk-payroll',
       'subject': 'Payroll import', 'body': 'The payroll import drops the last row of every file. Can you fix it?', 'sent_at': '2026-09-06 09:00:00'}


def store():
    s = MemoryStore()
    s.set_setting('coder_auto_enabled', '0', 't')
    for repo, about in (('acme/payroll', 'payroll import and portal sync'), ('acme/integrations', 'vendor integrations'), ('acme/portal', 'the customer portal')):
        projects.ensure_repository(s, repo, about, actor='test')
    return s


def verdict(repository='acme/payroll', needs=False, reason='the request names the payroll import', kind='coding', seen=None):
    def llm(system, user, **k):
        if seen is not None: seen.append({'system': system, 'user': json.loads(user)})
        j = {'intent': 'task', 'kind': kind, 'why': 'a bug report', 'repo_reason': reason, 'needs_repo_choice': needs}
        if repository is not None: j['repository'] = repository
        return json.dumps(j)
    return llm


class TriagePicksTests(unittest.TestCase):
    def test_the_verdict_sees_the_known_repositories_and_the_senders_project_context(self):
        s, seen = store(), []
        with mock.patch.object(ingest, '_spawn'): ingest.ingest_message(s, dict(MSG), llm=verdict(seen=seen))
        repos = seen[0]['user']['known_repositories']
        self.assertEqual(sorted(r['repo'] for r in repos), ['acme/integrations', 'acme/payroll', 'acme/portal'])
        self.assertTrue(any('payroll import' in (r.get('about') or '') for r in repos))
        self.assertIn('repository', seen[0]['system']); self.assertIn('needs_repo_choice', seen[0]['system'])

    def test_a_validated_pick_is_persisted_and_startup_uses_it(self):
        s = store()
        with mock.patch.object(ingest, '_spawn'): out = ingest.ingest_message(s, dict(MSG), llm=verdict())
        tid = out['task_id']
        repo, why = terminal.guess_repo(s, tid, PROFILE)
        self.assertEqual(repo, 'acme/payroll'); self.assertIn('triage', why.lower()); self.assertIn('payroll import', why)
        self.assertTrue(any('acme/payroll' in c['Body'] for c in s.list_comments(tid)))

    def test_an_unknown_repository_is_ignored_and_the_owner_is_asked(self):
        s = store()
        with mock.patch.object(ingest, '_spawn'): out = ingest.ingest_message(s, dict(MSG), llm=verdict(repository='acme/does-not-exist'))
        repo, why = terminal.guess_repo(s, out['task_id'], PROFILE)
        self.assertIsNone(repo); self.assertIn('choose', why.lower())

    def test_ambiguity_asks_the_owner_rather_than_forcing_a_match(self):
        s = store()
        with mock.patch.object(ingest, '_spawn'): out = ingest.ingest_message(s, dict(MSG), llm=verdict(repository=None, needs=True, reason='payroll or portal - both plausible'))
        repo, why = terminal.guess_repo(s, out['task_id'], PROFILE)
        self.assertIsNone(repo); self.assertIn('both plausible', why)
        with self.assertRaises(ValueError): terminal.start_on_task(s, out['task_id'], 'coder')


class PrecedenceTests(unittest.TestCase):
    def test_the_owners_explicit_repository_wins(self):
        s = store()
        with mock.patch.object(ingest, '_spawn'): out = ingest.ingest_message(s, dict(MSG), llm=verdict())
        s.tag_task(out['task_id'], 'repo:acme/portal', actor='owner')
        self.assertEqual(terminal.guess_repo(s, out['task_id'], PROFILE), ('acme/portal', 'tagged on the task'))

    def test_a_github_items_own_repository_is_authoritative(self):
        s = store()
        gh = {'external_id': 'gh:acme/portal#7', 'channel': 'github', 'conversation_id': 'gh:acme/portal#7', 'subject': 'acme/portal#7 payroll import broken',
              'body': '[issue by kai - association: NONE]\nthe payroll import drops rows', 'from_email': 'kai@users.noreply.github.com',
              'source_name': 'acme/portal', 'no_auto': True}
        with mock.patch.object(ingest, '_spawn'): out = ingest.ingest_message(s, gh, llm=verdict(repository='acme/payroll'))
        repo, _why = terminal.guess_repo(s, out['task_id'], PROFILE)
        self.assertEqual(repo, 'acme/portal')

    def test_sender_project_evidence_supports_but_does_not_decide(self):
        """A mapped person asking about a different system: the verdict decides from the request, and an
        uncertain one asks - the relationship alone never forces the mapped repository."""
        s, seen = store(), []
        with mock.patch.object(ingest, '_spawn'): ingest.ingest_message(s, dict(MSG), llm=verdict(repository=None, needs=True, seen=seen))
        self.assertIn('supporting evidence', seen[0]['system'].lower())


class CheckoutPathTests(unittest.TestCase):
    def test_a_missing_checkout_is_a_visible_repository_choice_not_a_silent_fallback(self):
        s = store()
        p = mock.patch.object(server, 'store', s); p.start(); self.addCleanup(p.stop)
        with mock.patch.object(ingest, '_spawn'): out = ingest.ingest_message(s, dict(MSG), llm=verdict())
        c = TestClient(server.app)
        s.upsert_agent('coder', 'coding', 'cli', json.dumps({'cmd': 'claude', 'cwd_map': {'acme/payroll': 'C:/definitely/gone/payroll'}}))
        with mock.patch.object(server.hub_term, 'start_on_task', side_effect=ValueError('working directory does not exist: C:/definitely/gone/payroll')):
            r = c.post(f"/api/tasks/{out['task_id']}/dispatch", json={'agent': 'coder'})
        self.assertEqual(r.status_code, 200)
        self.assertEqual(r.json()['dispatch'], 'needs_repo'); self.assertIn('does not exist', r.json()['reason'])


if __name__ == '__main__':
    unittest.main()
