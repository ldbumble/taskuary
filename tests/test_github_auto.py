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
