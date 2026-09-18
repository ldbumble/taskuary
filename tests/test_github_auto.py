"""Per-repo auto-dispatch for GitHub items (channels.gh_auto_ok): off by default, or the team /
contributors / anyone, keyed on GitHub's own author_association; and the same answer for a
deferred row judged in a later process (ingest._gh_no_auto)."""
import json, unittest
from taskuary import channels, ingest
from taskuary.store import MemoryStore


def src(auto=None, private=None):
    cfg = {}
    if auto: cfg['auto'] = auto
    if private is not None: cfg['private'] = private
    return {'Channel': 'github', 'Address': 'org/repo', 'ConfigJson': json.dumps(cfg)}


class AutoPickerTests(unittest.TestCase):
    def test_off_by_default_for_everyone(self):
        for a in ('OWNER', 'MEMBER', 'CONTRIBUTOR', 'NONE', None):
            self.assertFalse(channels.gh_auto_ok(src(), a), a)
        self.assertFalse(channels.gh_auto_ok({'ConfigJson': 'not json'}, 'OWNER'))

    def test_team_is_owners_members_collaborators(self):
        for a in ('OWNER', 'member', 'COLLABORATOR'): self.assertTrue(channels.gh_auto_ok(src('team'), a), a)
        for a in ('CONTRIBUTOR', 'FIRST_TIME_CONTRIBUTOR', 'NONE', None): self.assertFalse(channels.gh_auto_ok(src('team'), a), a)

    def test_contributors_adds_merged_authors_and_anyone_is_everyone(self):
        self.assertTrue(channels.gh_auto_ok(src('contributors'), 'CONTRIBUTOR'))
        self.assertFalse(channels.gh_auto_ok(src('contributors'), 'FIRST_TIME_CONTRIBUTOR'))
        self.assertTrue(channels.gh_auto_ok(src('anyone'), 'NONE'))

    def test_a_deferred_row_recovers_the_association_from_its_head_line(self):
        s = MemoryStore()
        s.save_source({**src('team'), 'Active': 1, 'Owner': 'me'}, 't')
        row = lambda assoc: {'Channel': 'github', 'SourceName': 'org/repo',
                             'BodyText': f'[pull request by kai - association: {assoc}]\nfixes the thing'}
        self.assertFalse(ingest._gh_no_auto(s, row('MEMBER')))        # may dispatch
        self.assertTrue(ingest._gh_no_auto(s, row('NONE')))           # waits for the owner
        self.assertTrue(ingest._gh_no_auto(s, {'Channel': 'github', 'SourceName': 'other/repo', 'BodyText': '[issue by x - association: OWNER]'}))
        self.assertFalse(ingest._gh_no_auto(s, {'Channel': 'email'}))


if __name__ == '__main__': unittest.main()


class ADeadRepoDoesNotBlindTheOthersTests(unittest.TestCase):
    """A renamed or deleted repo answers 404 for ever. The github branch had no guard of its own, so
    that error escaped the whole source loop and every repo listed AFTER it went unpolled - silently,
    on every cycle (the owner, 2026-09-18: "channel poll failed (github): 404 ... /FckSignups/issues").
    Outlook already had this guard; github did not."""

    def test_a_404_repo_is_reported_and_the_next_repo_is_still_polled(self):
        import json
        from unittest import mock
        from taskuary import channels
        from taskuary.store import MemoryStore
        s = MemoryStore()
        c = s.get_connector_by_type('github')
        s.save_connector({'ConnectorId': c['ConnectorId'], 'Active': 1, 'Roles': 'trigger', 'Secret': 'tok'}, 't')
        for repo in ('ldbumble/GoneForever', 'ldbumble/taskuary'):
            s.save_source({'Channel': 'github', 'Address': repo, 'Owner': 'me', 'Active': 1,
                           'ConnectorId': c['ConnectorId'], 'ConfigJson': json.dumps({'issues': 'work'})}, 't')
        polled = []

        def issues(store, src, tok, since, llm, file_only):
            polled.append(src['Address'])
            if src['Address'].endswith('GoneForever'):
                raise RuntimeError('404 Client Error: Not Found for url: .../GoneForever/issues')
            return 0

        with mock.patch.object(channels, 'ingest_github_issues', side_effect=issues), \
             mock.patch.object(channels, 'gh_modes', return_value=('work',)):
            channels._poll_one(s, s.get_connector(c['ConnectorId'], with_secret=True), False, 0, None, False)
        self.assertEqual(polled, ['ldbumble/GoneForever', 'ldbumble/taskuary'],
                         'the live repo must still be polled after the dead one')
        said = str((s.get_connector(c['ConnectorId']) or {}).get('LastError') or '')
        self.assertIn('GoneForever', said, 'the card has to name the repo that is gone')
        self.assertIn('no such repository', said)
        # the watermarks: the live repo moves on, the dead one stays put so nothing is stepped over
        by_addr = {r['Address']: r for r in s.list_sources(active_only=False) if r['Channel'] == 'github'}
        self.assertIsNotNone(by_addr['ldbumble/taskuary']['LastPolledAt'])
        self.assertIsNone(by_addr['ldbumble/GoneForever']['LastPolledAt'])
